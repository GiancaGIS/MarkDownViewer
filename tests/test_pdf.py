from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from tests.qt_support import APP
from PyQt6.QtCore import QEvent, QObject, QSettings, QTimer, QUrl, pyqtSignal
from PyQt6.QtGui import QPageLayout
from PyQt6.QtWidgets import QDialog, QDialogButtonBox, QFileDialog, QScrollArea

from src.main_window import MainWindow
from src.pdf_export import PdfExporter
from src.pdf_options import PdfOptions, PdfOptionsDialog
from src.renderer import MarkdownRenderer


class PdfPage(QObject):
    loadFinished = pyqtSignal(bool)
    renderProcessTerminated = pyqtSignal(object, int)

    def __init__(self):
        super().__init__()
        self.config = MagicMock()
        self.html = ""
        self.readiness = {"ready": True, "broken": False, "diagramError": False}
        self.callback = None
        self.layout = None

    def settings(self):
        return self.config

    def setHtml(self, html, url):
        self.html, self.url = html, url

    def runJavaScript(self, script, callback):
        callback(self.readiness)

    def printToPdf(self, callback, layout):
        self.callback, self.layout = callback, layout

    def triggerAction(self, action):
        pass


class PdfTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.root = Path(self.folder.name)
        self.settings = QSettings(str(self.root / "settings.ini"), QSettings.Format.IniFormat)
        self.exporter = PdfExporter()
        self.page = PdfPage()
        self.page_patch = patch("src.pdf_export.QWebEnginePage", return_value=self.page)
        self.page_patch.start()
        self.results = []
        self.exporter.finished.connect(self.results.append)

    def tearDown(self):
        self.exporter.cancel()
        self.exporter.deleteLater()
        self.page_patch.stop()
        APP.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        self.folder.cleanup()

    def start(self, options=None):
        return self.exporter.start("# Snapshot\n\nOriginal content.", "Snapshot", QUrl.fromLocalFile(str(self.root) + "/"), self.root / "output.pdf", options or PdfOptions())

    def test_page_options_persist_and_have_correct_physical_geometry(self):
        options = PdfOptions(paper="Letter", landscape=True, left=22, font_size=12.5)
        options.save(self.settings)
        self.assertEqual(PdfOptions.load(self.settings), options)
        layout = options.page_layout()
        self.assertEqual(layout.orientation(), QPageLayout.Orientation.Landscape)
        self.assertAlmostEqual(layout.fullRect().width(), 279.4, places=1)
        self.assertEqual(layout.margins().left(), 22)
        self.settings.setValue("pdf/font_size", "nan")
        self.settings.setValue("pdf/top", -100)
        self.settings.setValue("pdf/paper", "invalid")
        loaded = PdfOptions.load(self.settings)
        self.assertEqual((loaded.font_size, loaded.top, loaded.paper), (11, 20, "A4"))
        with patch("src.pdf_options.supports_page_numbers", return_value=False):
            self.assertFalse(PdfOptions.load(self.settings).page_numbers)

    def test_pdf_style_is_independent_of_theme_and_escapes_font_and_title(self):
        renderer = MarkdownRenderer("dark")
        renderer.typography = type(renderer.typography)(preview_size=28, preview_width=1200)
        text = renderer.to_pdf_document("# Text", "Title </style>", PdfOptions(font='bad"</style><script>'))
        self.assertNotIn('bad"</style><script>', text)
        self.assertNotIn("<title>Title </style>", text)
        self.assertNotIn("font-size: 28px", text)
        self.assertNotIn("cdn.jsdelivr.net", text)
        diagram = renderer.to_pdf_document("```mermaid\ngraph LR\n A-->B\n```", "Diagram", PdfOptions())
        self.assertIn("cdn.jsdelivr.net", diagram)

    def test_resources_are_ready_before_printing_and_save_is_atomic(self):
        destination = self.root / "output.pdf"
        destination.write_bytes(b"previous PDF")
        self.assertTrue(self.start(PdfOptions(paper="Letter", landscape=True)))
        self.assertFalse(self.start())
        self.assertIsNone(self.page.callback)
        self.page.loadFinished.emit(True)
        self.assertIsNotNone(self.page.callback)
        self.assertEqual(destination.read_bytes(), b"previous PDF")
        self.page.callback(b"%PDF-1.4\nnew PDF\n%%EOF")
        self.assertTrue(self.results[0].success)
        self.assertEqual(destination.read_bytes(), b"%PDF-1.4\nnew PDF\n%%EOF")
        self.assertFalse(self.exporter.busy)

    def test_missing_images_and_diagrams_fail_without_overwriting(self):
        destination = self.root / "output.pdf"
        destination.write_bytes(b"keep original")
        for broken_image, diagram_error in ((True, False), (False, True)):
            self.start()
            self.page.readiness = {"ready": True, "broken": broken_image, "diagramError": diagram_error}
            self.page.loadFinished.emit(True)
            self.assertEqual(self.results[-1].error, "pdf_resources_failed")
            self.assertEqual(destination.read_bytes(), b"keep original")
            self.assertIsNone(self.page.callback)

    def test_waiting_resources_and_timeout_are_bounded(self):
        self.start()
        self.page.readiness = {"ready": False}
        self.page.loadFinished.emit(True)
        self.assertIsNone(self.page.callback)
        self.exporter._timeout.timeout.emit()
        self.assertEqual(self.results[-1].error, "pdf_timeout")
        self.assertFalse(self.exporter.busy)

    def test_cancel_ignores_late_print_callback(self):
        self.start()
        self.page.loadFinished.emit(True)
        callback = self.page.callback
        self.exporter.cancel()
        callback(b"%PDF-1.4\nlate result")
        self.assertFalse((self.root / "output.pdf").exists())
        self.assertFalse(self.results)

    def test_invalid_print_data_and_write_failure_preserve_existing_pdf(self):
        destination = self.root / "output.pdf"
        destination.write_bytes(b"original")
        self.start()
        self.page.loadFinished.emit(True)
        self.page.callback(b"")
        self.assertFalse(self.results[-1].success)
        self.assertEqual(destination.read_bytes(), b"original")
        self.start()
        self.page.loadFinished.emit(True)
        with patch("src.pdf_export.write_bytes_atomic", side_effect=OSError("disk full")):
            self.page.callback(b"%PDF-1.4\nvalid data")
        self.assertEqual(self.results[-1].error, "pdf_write_failed")
        self.assertEqual(destination.read_bytes(), b"original")

    def test_export_keeps_snapshot_when_active_document_changes(self):
        with patch("src.main_window.QSettings", return_value=self.settings):
            window = MainWindow()
        window.editor.setPlainText("# Original document")
        window.editor.document().setModified(False)
        options_dialog = MagicMock()
        options_dialog.exec.return_value = QDialog.DialogCode.Accepted
        options_dialog.options.return_value = PdfOptions()
        try:
            with patch("src.main_window.PdfOptionsDialog", return_value=options_dialog), patch.object(QFileDialog, "getSaveFileName", return_value=(str(self.root / "snapshot.pdf"), "")):
                window.export_pdf()
            self.assertFalse(window.actions["export_pdf"].isEnabled())
            window.new_file()
            window.editor.setPlainText("# Different document")
            self.assertIn("Original document", self.page.html)
            self.assertNotIn("Different document", self.page.html)
            self.page.loadFinished.emit(True)
            self.page.callback(b"%PDF-1.4\nsnapshot")
            self.assertEqual(window.editor.toPlainText(), "# Different document")
            self.assertTrue(window.actions["export_pdf"].isEnabled())
        finally:
            for editor in window.document_paths:
                editor.document().setModified(False)
            window.close()
            window.deleteLater()
            APP.sendPostedEvents(None, QEvent.Type.DeferredDelete)

    def test_pdf_dialog_cancel_does_not_start_export(self):
        with patch("src.main_window.QSettings", return_value=self.settings):
            window = MainWindow()
        try:
            dialog = PdfOptionsDialog(window)
            dialog.resize(420, 450)
            dialog.show()
            APP.processEvents()
            self.assertTrue(dialog.numbers.isVisible())  # In scrollable content if needed.
            scroll = dialog.findChild(QScrollArea)
            self.assertEqual(scroll.horizontalScrollBar().maximum(), 0)
            buttons = dialog.findChild(QDialogButtonBox)
            self.assertTrue(dialog.rect().contains(buttons.geometry()))
            dialog.close()
            with patch("src.main_window.PdfOptionsDialog") as factory:
                factory.return_value.exec.return_value = QDialog.DialogCode.Rejected
                with patch.object(window.pdf_exporter, "start") as start:
                    window.export_pdf()
                    start.assert_not_called()
        finally:
            window.close()
            window.deleteLater()
            APP.sendPostedEvents(None, QEvent.Type.DeferredDelete)
