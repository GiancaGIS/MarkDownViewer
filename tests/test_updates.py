from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tests.qt_support import APP
from PyQt6.QtCore import QEvent, QIODevice, QObject, QSettings, Qt, QTimer
from PyQt6.QtNetwork import QNetworkReply, QNetworkRequest
from PyQt6.QtTest import QTest

from src.config import GITHUB_REPOSITORY, VERSION
from src.main_window import MainWindow
from src.preferences import PreferencesDialog
from src.updates import CHECK_TIMEOUT_MS, MAX_RESPONSE_BYTES, RELEASE_API_URL, UpdateChecker, parse_release, version_tuple


def release_payload(tag="v2.0.0", **changes):
    data = {"tag_name": tag, "draft": False, "prerelease": False,
            "html_url": f"https://github.com/{GITHUB_REPOSITORY}/releases/tag/{tag}"}
    return data | changes


class Reply(QNetworkReply):
    """Only the network transport is replaced; signals and parsing stay real."""

    def __init__(self, parent):
        super().__init__(parent)
        self.pending = bytearray()
        self.setAttribute(QNetworkRequest.Attribute.HttpStatusCodeAttribute, 200)
        self.open(QIODevice.OpenModeFlag.ReadOnly | QIODevice.OpenModeFlag.Unbuffered)

    def readData(self, maximum):
        data = bytes(self.pending[:maximum])
        del self.pending[:maximum]
        return data

    def bytesAvailable(self):
        return len(self.pending) + super().bytesAvailable()

    def feed(self, data):
        self.pending.extend(data)
        self.readyRead.emit()

    def complete(self, data=b"", status=200, error=QNetworkReply.NetworkError.NoError):
        self.setAttribute(QNetworkRequest.Attribute.HttpStatusCodeAttribute, status)
        if error != QNetworkReply.NetworkError.NoError:
            self.setError(error, "network error")
        self.feed(data)
        if not self.isFinished():
            self.setFinished(True)
            self.finished.emit()

    def abort(self):
        self.setError(QNetworkReply.NetworkError.OperationCanceledError, "cancelled")
        self.setFinished(True)
        self.finished.emit()


class Network(QObject):
    def __init__(self):
        super().__init__()
        self.requests = []
        self.replies = []

    def get(self, request):
        self.requests.append(QNetworkRequest(request))
        reply = Reply(self)
        self.replies.append(reply)
        return reply


class VersionTests(unittest.TestCase):
    def test_numeric_comparison_and_supported_tag_forms(self):
        for tag, expected in (("1.10.0", (1, 10, 0)), ("v1.2.3", (1, 2, 3)),
                              ("V1.2", (1, 2, 0)), ("1.2.3+build.5", (1, 2, 3))):
            self.assertEqual(version_tuple(tag), expected)
        self.assertEqual(parse_release(release_payload("1.10.0"), "1.9.0").status, "available")
        for tag in ("v1.1.0", "1.0.3", "1.1.0+build.2"):
            self.assertEqual(parse_release(release_payload(tag), "1.1.0").status, "current")

    def test_drafts_prereleases_and_malformed_responses(self):
        for data in (release_payload(prerelease=True), release_payload(draft=True)):
            self.assertEqual(parse_release(data, VERSION).status, "no_release")
        for tag in ("1.2.0-rc.1", "release-2", "01.2.0", "1.2.3.4", None, 123):
            self.assertIsNone(version_tuple(tag))
            self.assertEqual(parse_release(release_payload(tag), VERSION).status, "error")
        for data in (None, [], {}, {"tag_name": []}):
            self.assertEqual(parse_release(data, VERSION).status, "error")
        for url in ("file:///bad.exe", "https://example.com/release", "https://github.com/other/repo/releases/tag/v2.0.0"):
            self.assertEqual(parse_release(release_payload(html_url=url), VERSION).status, "error")

    def test_installer_version_matches_application(self):
        installer = (Path(__file__).resolve().parents[1] / "installer.iss").read_text()
        self.assertIn(f'#define MyAppVersion "{VERSION}"', installer)
        self.assertIn(f'#define MyAppVersionInfo "{VERSION}.0"', installer)


class CheckerTests(unittest.TestCase):
    def setUp(self):
        self.network = Network()
        with patch("src.updates.QNetworkAccessManager", return_value=self.network):
            self.checker = UpdateChecker()
        self.results = []
        self.busy = []
        self.checker.finished.connect(self.results.append)
        self.checker.busy_changed.connect(self.busy.append)

    def tearDown(self):
        self.checker.cancel()
        self.checker.deleteLater()
        self.network.deleteLater()
        APP.sendPostedEvents(None, QEvent.Type.DeferredDelete)

    def test_async_request_streamed_response_and_duplicate_check(self):
        self.assertTrue(self.checker.check())
        self.assertFalse(self.checker.check())
        self.assertTrue(self.checker.busy)
        self.assertEqual(len(self.network.requests), 1)
        request = self.network.requests[0]
        self.assertEqual(request.url().toString(), RELEASE_API_URL)
        self.assertEqual(request.transferTimeout(), CHECK_TIMEOUT_MS)
        self.assertIn(VERSION.encode(), bytes(request.rawHeader(b"User-Agent")))
        encoded = json.dumps(release_payload()).encode()
        reply = self.network.replies[0]
        reply.feed(encoded[:30])
        self.assertFalse(self.results)
        reply.complete(encoded[30:])
        self.assertEqual(self.results[0].status, "available")
        self.assertEqual(self.results[0].release.version, "2.0.0")
        self.assertEqual(self.busy, [True, False])
        self.assertFalse(self.checker.busy)

    def test_http_errors_empty_release_and_invalid_json(self):
        for status, data, expected in ((404, b"{}", "no_release"), (403, b"{}", "error"),
                                        (500, b"{}", "error"), (200, b"not json", "error"),
                                        (200, b"\xff", "error")):
            self.checker.check()
            self.network.replies[-1].complete(data, status)
            self.assertEqual(self.results[-1].status, expected)
            self.assertFalse(self.checker.busy)

    def test_timeout_is_bounded_and_can_retry(self):
        self.checker.check()
        self.checker._timeout.start(20)
        QTest.qWait(60)
        self.assertEqual(self.results[-1].status, "error")
        self.assertFalse(self.checker.busy)
        self.assertTrue(self.checker.check())
        self.network.replies[-1].complete(json.dumps(release_payload(VERSION)).encode())
        self.assertEqual(self.results[-1].status, "current")

    def test_oversized_payload_aborts_and_cancel_is_silent(self):
        self.checker.check()
        self.network.replies[-1].feed(b"x" * (MAX_RESPONSE_BYTES + 1))
        self.assertEqual(self.results[-1].status, "error")
        self.checker.check()
        reply = self.network.replies[-1]
        self.checker.cancel()
        reply.finished.emit()
        self.assertEqual(len(self.results), 1)
        self.assertFalse(self.checker.busy)


class UpdateWindowTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.settings = QSettings(str(Path(self.folder.name) / "settings.ini"), QSettings.Format.IniFormat)
        with patch("src.main_window.QSettings", return_value=self.settings):
            self.window = MainWindow()
        self.network = Network()
        self.window.update_checker.network = self.network
        self.window.resize(1100, 700)
        self.window.show()
        self.window.activateWindow()
        APP.setActiveWindow(self.window)
        APP.processEvents()

    def tearDown(self):
        self.window.close()
        self.window.deleteLater()
        self.network.deleteLater()
        APP.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        self.folder.cleanup()

    def test_startup_once_and_automatic_failure_is_silent(self):
        self.window.check_updates_on_startup = False
        self.window.check_startup_updates()
        self.assertFalse(self.network.requests)
        self.window.check_updates_on_startup = True
        self.window.check_startup_updates()
        self.window.check_startup_updates()
        self.assertEqual(len(self.network.requests), 1)
        self.assertFalse(self.window.actions["check_updates"].isEnabled())
        self.network.replies[-1].complete(b"{}", 403)
        self.assertFalse(self.window.update_toast.isVisible())
        self.assertTrue(self.window.actions["check_updates"].isEnabled())
        self.assertNotEqual(self.window.statusBar().currentMessage(), self.window.tr("updates_unavailable"))

    def test_toast_focus_position_translation_dismiss_and_release_link(self):
        self.window.editor.setFocus()
        APP.processEvents()
        focus = APP.focusWidget()
        self.window.check_startup_updates()
        self.network.replies[-1].complete(json.dumps(release_payload()).encode())
        toast = self.window.update_toast
        self.assertTrue(toast.isVisible())
        self.assertIs(APP.focusWidget(), focus)
        self.assertIn("2.0.0", toast.message_label.text())
        self.window.resize(910, 512)
        APP.processEvents()
        self.assertTrue(self.window.centralWidget().geometry().contains(toast.geometry()))
        self.window.set_language("en")
        self.assertEqual(toast.title_label.text(), "Update available")
        QTest.mouseClick(toast.close_button, Qt.MouseButton.LeftButton)
        self.assertFalse(toast.isVisible())
        self.assertFalse(toast._timer.isActive())
        self.window.check_for_updates()
        self.network.replies[-1].complete(json.dumps(release_payload()).encode())
        self.assertEqual(toast._timer.interval(), 20_000)
        with patch("src.main_window.QDesktopServices.openUrl", return_value=True) as open_url:
            QTest.mouseClick(toast.open_button, Qt.MouseButton.LeftButton)
        self.assertEqual(open_url.call_args.args[0].toString(), release_payload()["html_url"])
        self.assertFalse(toast.isVisible())

    def test_manual_current_or_error_reports_status_and_close_cancels_request(self):
        self.window.actions["check_updates"].trigger()
        self.network.replies[-1].complete(json.dumps(release_payload(VERSION)).encode())
        self.assertEqual(self.window.statusBar().currentMessage(), self.window.tr("updates_current", version=VERSION))
        self.window.check_for_updates()
        self.network.replies[-1].complete(b"{}", 500)
        self.assertEqual(self.window.statusBar().currentMessage(), self.window.tr("updates_unavailable"))
        self.assertFalse(self.window.update_toast.isVisible())
        self.window.check_for_updates()
        self.window.close()
        self.assertFalse(self.window.update_checker.busy)
        self.assertFalse(self.window.update_toast.isVisible())

    def test_toast_expires_pauses_for_keyboard_focus_and_resumes_after_restore(self):
        self.window.on_update_check_finished(parse_release(release_payload(), VERSION))
        toast = self.window.update_toast
        toast.open_button.setFocus()
        APP.processEvents()
        self.assertIs(APP.focusWidget(), toast.open_button)
        with patch.object(toast, "underMouse", return_value=False), patch.object(self.window, "isActiveWindow", return_value=True):
            # Isolate focus state from WebEngine's asynchronous startup in offscreen Qt.
            with patch("src.toast.QApplication.focusWidget", return_value=toast.open_button):
                toast._timer.start(20)
                QTest.qWait(60)
                self.assertTrue(toast.isVisible())
            with patch("src.toast.QApplication.focusWidget", return_value=self.window.editor):
                toast._timer.start(20)
                QTest.qWait(60)
                self.assertFalse(toast.isVisible())
        self.window.on_update_check_finished(parse_release(release_payload(), VERSION))
        self.window.hide()
        self.window.show()
        APP.processEvents()
        self.assertTrue(toast._timer.isActive())
        self.assertEqual(toast._timer.interval(), 20_000)

    def test_startup_preference_is_saved(self):
        self.window.check_startup_updates()
        self.assertTrue(self.window.update_checker.busy)
        def dialog_factory(window):
            dialog = PreferencesDialog(window)
            dialog.check_updates.setChecked(False)
            QTimer.singleShot(0, dialog.accept)
            return dialog

        with patch("src.main_window.PreferencesDialog", side_effect=dialog_factory):
            self.window.show_preferences()
        self.assertFalse(self.window.check_updates_on_startup)
        self.assertFalse(self.window.update_checker.busy)
        self.assertFalse(self.settings.value("check_updates_on_startup", type=bool))
        self.window.check_startup_updates()
        self.assertEqual(len(self.network.requests), 1)


if __name__ == "__main__":
    unittest.main()
