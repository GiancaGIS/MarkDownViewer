from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tests.qt_support import APP
from PyQt6.QtCore import QEvent, QSettings, Qt, QTimer
from PyQt6.QtTest import QSignalSpy, QTest
from src.main_window import MainWindow


class LayoutTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.root = Path(self.folder.name)
        self.settings = QSettings(str(self.root / "settings.ini"), QSettings.Format.IniFormat)
        with patch("src.main_window.QSettings", return_value=self.settings):
            self.window = MainWindow()
        self.window.resize(1366, 768)
        self.window.show()
        APP.setActiveWindow(self.window)
        APP.processEvents()

    def tearDown(self):
        for editor in self.window.document_paths:
            editor.document().setModified(False)
        self.window.close()
        self.window.deleteLater()
        APP.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        self.folder.cleanup()

    def test_empty_workspace_and_single_section_navigation(self):
        panel = self.window.workspace_panel
        self.assertTrue(panel.tree.isHidden())
        self.assertTrue(panel.empty_open_button.isVisible())
        self.assertTrue(panel.isVisible())
        QTest.mouseClick(self.window.navigation.buttons["outline"], Qt.MouseButton.LeftButton)
        self.assertEqual(panel.tabs.currentWidget(), panel.outline_list)
        self.assertFalse(panel.search_box.isVisible())
        QTest.mouseClick(self.window.navigation.buttons["outline"], Qt.MouseButton.LeftButton)
        self.assertFalse(panel.isVisible())
        QTest.mouseClick(self.window.navigation.buttons["recent"], Qt.MouseButton.LeftButton)
        self.assertTrue(panel.recent_list.isVisible())
        self.assertFalse(panel.outline_list.isVisible())

    def test_narrow_navigation_search_and_selection_return_space_to_document(self):
        path = self.root / "note.md"
        path.write_text("# Note\nA needle in the workspace\n", encoding="utf-8")
        self.window.set_workspace(self.root)
        self.window.resize(910, 620)
        APP.processEvents()
        self.assertFalse(self.window.workspace_panel.isVisible())
        QTest.keyClick(self.window.editor, Qt.Key.Key_F, Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.ShiftModifier)
        self.assertTrue(self.window.workspace_panel.search_box.isVisible())
        self.window.workspace_panel.search_box.setText("needle")
        QTest.keyClick(self.window.workspace_panel.search_box, Qt.Key.Key_Return)
        results = self.window.workspace_panel.results_list
        self.assertEqual(results.count(), 1)
        results.itemDoubleClicked.emit(results.item(0))
        self.assertEqual(self.window.current_path, path.resolve())
        self.assertFalse(self.window.workspace_panel.isVisible())
        self.window.resize(1366, 768)
        APP.processEvents()
        self.assertTrue(self.window.workspace_panel.isVisible())

    def test_split_adapts_and_preserves_horizontal_and_vertical_proportions(self):
        self.window.set_view_mode("split")
        splitter = self.window.editor_preview_splitter
        self.assertEqual(splitter.orientation(), Qt.Orientation.Horizontal)
        splitter.setSizes([400, 600])
        first = splitter.sizes()
        self.window.resize(910, 620)
        APP.processEvents()
        self.assertEqual(splitter.orientation(), Qt.Orientation.Vertical)
        self.assertGreater(self.window.preview.height(), 120)
        self.assertGreater(self.window.editor.height(), 120)
        splitter.setSizes([240, 310])
        vertical = splitter.sizes()
        self.window.set_view_mode("reading")
        self.window.set_view_mode("split")
        restored = splitter.sizes()
        self.assertAlmostEqual(restored[0] / sum(restored), vertical[0] / sum(vertical), places=2)
        self.window.resize(1366, 768)
        APP.processEvents()
        self.assertEqual(splitter.orientation(), Qt.Orientation.Horizontal)
        restored = splitter.sizes()
        self.assertAlmostEqual(restored[0] / sum(restored), first[0] / sum(first), places=2)

    def test_compact_chrome_and_readable_writing_column(self):
        self.window.resize(1600, 900)
        self.window.set_view_mode("writing")
        APP.processEvents()
        editor = self.window.editor
        target = editor.fontMetrics().horizontalAdvance("M") * 88
        self.assertLessEqual(editor.viewport().width(), target + 24)
        self.assertGreater(editor._horizontal_inset, 0)
        self.assertGreater(editor.viewport().height(), self.window.height() * 0.8)
        self.assertFalse(editor.horizontalScrollBar().isVisible())
        button = self.window.format_buttons["bold"]
        self.assertGreaterEqual(button.height(), button.fontMetrics().height())
        self.window.set_view_mode("split")
        self.assertEqual(editor._horizontal_inset, 0)

    def test_many_tabs_and_menu_shortcuts_remain_accessible(self):
        for index in range(16):
            self.window._create_document_tab(f"Document {index}")
        self.window.resize(910, 620)
        APP.processEvents()
        tabs = self.window.document_tabs
        self.assertTrue(tabs.isVisible())
        self.assertTrue(tabs.rect().intersects(tabs.tabRect(tabs.currentIndex())))
        self.assertFalse(self.window.menuBar().isVisible())
        count = tabs.count()
        QTest.keyClick(self.window.editor, Qt.Key.Key_N, Qt.KeyboardModifier.ControlModifier)
        self.assertEqual(tabs.count(), count + 1)
        shown = QSignalSpy(self.window.application_menu.aboutToShow)
        QTimer.singleShot(50, self.window.application_menu.close)
        QTest.keyClick(self.window.editor, Qt.Key.Key_F10)
        self.assertEqual(len(shown), 1)

    def test_auto_collapse_does_not_overwrite_sidebar_preference(self):
        self.window.resize(910, 620)
        APP.processEvents()
        self.window.save_ui_settings()
        self.assertTrue(self.settings.value("sidebar_visible", type=bool))
        self.window.resize(1366, 768)
        APP.processEvents()
        self.window.toggle_sidebar()
        self.window.resize(910, 620)
        self.window.resize(1366, 768)
        APP.processEvents()
        self.assertFalse(self.window.workspace_panel.isVisible())
        self.window.save_ui_settings()
        self.assertFalse(self.settings.value("sidebar_visible", type=bool))
