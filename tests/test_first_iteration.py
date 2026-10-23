"""Run with: .venv/Scripts/python -m unittest discover -s tests -v."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tests.qt_support import APP

from PyQt6.QtCore import QEvent, QIODevice, QSaveFile, QSettings, Qt, QTimer
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication, QMessageBox

from src.main_window import MainWindow
from src.preferences import PreferencesDialog, Typography
from src.utils import write_text_atomic


class AtomicSaveTests(unittest.TestCase):
    def test_unicode_replacement_and_failed_write_preserve_original(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "nota.md"
            write_text_atomic(path, "# Città 🌍\n")
            self.assertEqual(path.read_text(encoding="utf-8"), "# Città 🌍\n")

            # A real QSaveFile stages bytes; inject a short write before commit.
            staged = QSaveFile(str(path))
            self.assertTrue(staged.open(QIODevice.OpenModeFlag.WriteOnly))
            staged.write(b"partial")
            with patch("src.utils.QSaveFile") as factory:
                factory.return_value = staged
                with patch.object(staged, "open", return_value=True), patch.object(staged, "write", return_value=1):
                    with self.assertRaises(OSError):
                        write_text_atomic(path, "replacement")
            staged.commit()
            self.assertEqual(path.read_text(encoding="utf-8"), "# Città 🌍\n")

    def test_invalid_destination_reports_failure(self):
        with tempfile.TemporaryDirectory() as folder:
            with self.assertRaises(OSError):
                write_text_atomic(Path(folder) / "missing" / "note.md", "text")


class WindowTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.root = Path(self.folder.name)
        self.settings = QSettings(str(self.root / "settings.ini"), QSettings.Format.IniFormat)
        self.settings_patch = patch("src.main_window.QSettings", return_value=self.settings)
        self.settings_patch.start()
        self.window = MainWindow()
        self.window.resize(1366, 768)
        self.window.show()
        APP.processEvents()

    def tearDown(self):
        for editor in self.window.document_paths:
            editor.document().setModified(False)
        self.window.close()
        self.window.deleteLater()
        APP.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        APP.processEvents()
        self.settings_patch.stop()
        self.folder.cleanup()

    def add_document(self, name, text):
        path = self.root / name
        path.write_text(text, encoding="utf-8")
        editor = self.window._create_document_tab(text, path)
        return editor, path

    def test_autosave_keeps_each_document_and_its_own_deadline(self):
        first, first_path = self.add_document("first.md", "first")
        first.insertPlainText("A")
        QTest.qWait(900)
        second, second_path = self.add_document("second.md", "second")
        second.insertPlainText("B")
        self.window.new_file()
        draft = self.window.editor
        draft.insertPlainText("unsaved draft")
        QTest.qWait(850)
        self.assertEqual(first_path.read_text(), "Afirst")
        self.assertEqual(second_path.read_text(), "second")
        QTest.qWait(850)
        self.assertEqual(second_path.read_text(), "Bsecond")
        self.assertIs(self.window.editor, draft)
        self.assertIsNone(self.window.current_path)
        self.assertTrue(draft.document().isModified())
        self.assertFalse(first.document().isModified())
        self.assertFalse(second.document().isModified())

    def test_disabling_autosave_cancels_pending_writes(self):
        editor, path = self.add_document("disabled.md", "original")
        editor.insertPlainText("changed ")
        self.window.toggle_autosave(False)
        QTest.qWait(1700)
        self.assertEqual(path.read_text(), "original")
        self.window.toggle_autosave(True)
        QTest.qWait(1700)
        self.assertEqual(path.read_text(), "changed original")

    def test_discarding_tab_cancels_its_autosave(self):
        editor, path = self.add_document("discard.md", "original")
        editor.insertPlainText("discarded ")
        with patch.object(QMessageBox, "question", return_value=QMessageBox.StandardButton.Discard):
            self.window.close_document_tab(self.window.document_tabs.indexOf(editor))
        QTest.qWait(1700)
        self.assertEqual(path.read_text(), "original")
        self.assertNotIn(editor, self.window.document_autosave_timers)

    def test_failed_save_keeps_dirty_document_and_original_file(self):
        editor, path = self.add_document("failure.md", "original")
        editor.insertPlainText("changed ")
        with patch("src.main_window.write_text_atomic", side_effect=OSError("disk full")):
            self.assertFalse(self.window._write_markdown(path, autosave=True))
        self.assertTrue(editor.document().isModified())
        self.assertEqual(path.read_text(), "original")

    def test_open_alias_reuses_tab_and_save_as_cannot_overwrite_open_document(self):
        editor, path = self.add_document("existing.md", "original")
        nested = self.root / "nested"
        nested.mkdir()
        self.window.open_file_path(nested / ".." / path.name)
        self.assertIs(self.window.editor, editor)
        self.assertEqual(self.window.document_tabs.count(), 2)
        self.window.new_file()
        draft = self.window.editor
        draft.insertPlainText("different document")
        with patch.object(QMessageBox, "critical"):
            self.assertFalse(self.window._write_markdown(path, autosave=False))
        self.assertEqual(path.read_text(), "original")
        self.assertIsNone(self.window.document_paths[draft])
        self.assertTrue(draft.document().isModified())

    def test_modes_reordered_tabs_and_find_shortcuts(self):
        first, _ = self.add_document("first.md", "alpha beta alpha")
        second, _ = self.add_document("second.md", "second")
        self.window.document_tabs.moveTab(2, 0)
        self.assertIs(self.window.editor, second)
        self.assertIs(self.window.document_tabs.pages.currentWidget(), second)
        self.window.document_tabs.setCurrentIndex(self.window.document_tabs.indexOf(first))
        self.window.set_view_mode("reading")
        self.assertFalse(self.window.editor_panel.isVisible())
        self.assertTrue(self.window.preview_panel.isVisible())
        self.assertTrue(self.window.document_tabs.isVisible())
        self.assertFalse(self.window.actions["bold"].isEnabled())
        self.window.actions["find"].trigger()
        self.assertEqual(self.window.view_mode, "split")
        self.assertTrue(self.window.find_bar.isVisible())
        self.window.find_box.setText("alpha")
        QTest.keyClick(self.window.find_box, Qt.Key.Key_Return)
        self.assertEqual(first.textCursor().selectedText(), "alpha")
        QTest.keyClick(self.window.find_box, Qt.Key.Key_Escape)
        APP.processEvents()
        self.assertFalse(self.window.find_bar.isVisible())
        self.window.set_view_mode("writing")
        self.assertFalse(self.window.preview_panel.isVisible())
        self.assertTrue(self.window.editor_panel.isVisible())
        self.window.apply_theme("dark")
        self.assertEqual(self.window.format_buttons["bold"].text(), "B")
        QTest.mouseClick(self.window.format_buttons["bold"], Qt.MouseButton.LeftButton)
        self.assertIn("**alpha**", first.toPlainText())
        close = self.window.document_tabs.tabButton(self.window.document_tabs.indexOf(second), self.window.document_tabs.ButtonPosition.RightSide)
        QTest.mouseClick(close, Qt.MouseButton.LeftButton)
        self.assertNotIn(second, self.window.document_paths)

    def test_preferences_apply_without_changing_document_and_persist(self):
        editor, _ = self.add_document("appearance.md", "# unchanged")

        def dialog_factory(window):
            dialog = PreferencesDialog(window)
            dialog.editor_size.setValue(18)
            dialog.preview_size.setValue(20)
            dialog.preview_spacing.setValue(1.8)
            dialog.theme.setCurrentIndex(dialog.theme.findData("dark"))
            dialog.language.setCurrentIndex(dialog.language.findData("en"))
            QTimer.singleShot(0, dialog.accept)
            return dialog

        with patch("src.main_window.PreferencesDialog", side_effect=dialog_factory):
            self.window.show_preferences()
        self.assertEqual(editor.font().pointSize(), 18)
        self.assertFalse(editor.document().isModified())
        self.assertEqual(editor.toPlainText(), "# unchanged")
        self.assertEqual(self.window.theme, "dark")
        self.assertEqual(self.window.actions["preferences"].text(), "Preferences…")
        self.assertEqual(Typography.load(self.settings), self.window.typography)
        self.assertIn("font-size: 20px", self.window.renderer._css())
        new_editor = self.window._create_document_tab("new")
        self.assertEqual(new_editor.font().pointSize(), 18)
        self.assertFalse(new_editor.document().isModified())

    def test_view_mode_persistence_preserves_split_proportions(self):
        self.window.set_view_mode("split")
        self.window.editor_preview_splitter.setSizes([400, 600])
        original_sizes = self.window.editor_preview_splitter.sizes()
        self.window.set_view_mode("reading")
        self.window.save_ui_settings()
        self.assertEqual(self.settings.value("editor_preview_splitter_sizes"), original_sizes)
        self.assertEqual(self.settings.value("view_mode"), "reading")
        self.window.restore_ui_settings()
        self.window.resize(1366, 768)
        APP.processEvents()
        self.window.set_view_mode("split")
        sizes = self.window.editor_preview_splitter.sizes()
        self.assertAlmostEqual(sizes[0] / sum(sizes), original_sizes[0] / sum(original_sizes), places=2)

    def test_preferences_cancel_and_invalid_stored_values(self):
        original = self.window.typography

        def dialog_factory(window):
            dialog = PreferencesDialog(window)
            dialog.editor_size.setValue(28)
            QTimer.singleShot(0, dialog.reject)
            return dialog

        with patch("src.main_window.PreferencesDialog", side_effect=dialog_factory):
            self.window.show_preferences()
        self.assertEqual(self.window.typography, original)
        for key, value in (("editor_size", "invalid"), ("preview_width", -1), ("preview_spacing", "nan")):
            self.settings.setValue(f"typography/{key}", value)
        self.assertEqual(Typography.load(self.settings), Typography())


if __name__ == "__main__":
    unittest.main()
