"""
test_qt_ui.py
-------------
The PySide6 window, run off-screen with scripted dialogs (DXF input, no AutoCAD).
Skipped when PySide6 is not installed.
"""

import os
import unittest
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PySide6.QtCore import QSettings
    from PySide6.QtWidgets import QApplication
    import qt_ui
    HAS_QT = True
except ImportError:          # PySide6 not installed (stable Tkinter setup)
    HAS_QT = False

from tests.helpers import EXPECTED_KEYS, ROOMS_CSV, TempDirTestCase, make_plan


@unittest.skipUnless(HAS_QT, "PySide6 not installed")
class QtTestCase(TempDirTestCase):

    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        super().setUp()
        patches = [mock.patch.object(qt_ui.QMessageBox, name) for name in
                   ("information", "warning", "critical")]
        self.boxes = {p.attribute: p.start() for p in patches}
        for p in patches:
            self.addCleanup(p.stop)
        self.settings = QSettings(self.path("settings.ini"), QSettings.IniFormat)
        self.win = qt_ui.MainWindow(self.settings)

    def tearDown(self):
        # Flush QSettings and destroy the window *before* the temp folder is removed;
        # otherwise Qt writes settings.ini afterwards and recreates the folder.
        self.settings.sync()
        self.win.deleteLater()
        QApplication.processEvents()
        super().tearDown()

    def ready_window(self):
        self.win.load_sheet(self.write_text("rooms.csv", ROOMS_CSV), wait=True)
        self.win.set_drawing(make_plan(self.path("0132_TEST.dxf")))


class TestSetup(QtTestCase):

    def test_run_disabled_until_ready(self):
        self.assertFalse(self.win.run_btn.isEnabled())
        self.ready_window()
        self.assertEqual(self.win.columns(), ("Room Number", "Building ID", "Floor"))
        self.assertEqual(self.win.building_edit.text(), "0132")
        self.assertEqual(self.win.preview.text(), "e.g.  0132-01-101")
        self.assertTrue(self.win.run_btn.isEnabled())
        self.assertFalse(self.win.cancel_btn.isEnabled())

    def test_preview_follows_edited_building_id(self):
        self.ready_window()
        self.win.building_edit.setText("9999")
        self.assertEqual(self.win.preview.text(), "e.g.  9999-01-101")
        self.win.building_edit.setText("")
        self.assertFalse(self.win.run_btn.isEnabled())

    def test_same_column_twice_blocks_run(self):
        self.ready_window()
        self.win.floor_combo.setCurrentText("Room Number")
        self.assertFalse(self.win.run_btn.isEnabled())
        self.assertIn("three different columns", self.win.run_btn.toolTip())

    def test_room_layer_box_validated_and_remembered(self):
        self.ready_window()
        self.assertEqual(self.win.layer_edit.text(), "ROOM_KEYS")
        self.win.layer_edit.setText("BAD:NAME")
        self.assertFalse(self.win.run_btn.isEnabled())
        self.assertIn("Room layer", self.win.run_btn.toolTip())
        self.win.layer_edit.setText("A-AREA-KEYS")
        self.assertTrue(self.win.run_btn.isEnabled())
        self.win.start_run(self.path("out.dxf"), wait=True)
        self.assertEqual(self.win.settings.value("layer_name"), "A-AREA-KEYS")

    def test_theme_toggle_is_remembered(self):
        start = self.win.theme
        self.win._toggle_theme()
        self.assertNotEqual(self.win.theme, start)
        self.assertEqual(self.win.settings.value("theme"), self.win.theme)
        self.assertIn(qt_ui.THEMES[self.win.theme]["bg"], self.win.styleSheet())


class TestRun(QtTestCase):

    def test_full_run_fills_results_table(self):
        self.ready_window()
        out = self.path("out.dxf")
        self.win.start_run(out, wait=True)
        self.assertTrue(os.path.exists(out))
        self.assertEqual(self.win.result.created, 3)
        table = self.win.table
        layers = {table.item(r, 1).text() for r in range(table.rowCount())}
        self.assertTrue(set(EXPECTED_KEYS) <= layers)
        self.boxes["information"].assert_called_once()
        self.win.filter_combo.setCurrentText("Not matched")
        visible = [r for r in range(table.rowCount()) if not table.isRowHidden(r)]
        self.assertEqual(visible, [])                       # every sheet row was matched

    def test_wrong_building_shows_warning_and_writes_nothing(self):
        self.ready_window()
        self.win.building_edit.setText("5555")
        self.win.start_run(self.path("out.dxf"), wait=True)
        self.boxes["warning"].assert_called_once()
        self.assertFalse(os.path.exists(self.path("out.dxf")))
        self.assertIn("Stopped", self.win.status.text())


class TestOutputRules(unittest.TestCase):

    @unittest.skipUnless(HAS_QT, "PySide6 not installed")
    def test_check_output_path(self):
        src = r"C:\Drawings\0132_LAB.dwg"
        self.assertEqual(qt_ui.check_output_path(src, r"D:\Out\r"), (r"D:\Out\r.dwg", None))
        path, problem = qt_ui.check_output_path(src, r"c:\drawings\0132_lab.DWG")
        self.assertIsNone(path)
        self.assertIn("cannot be overwritten", problem)

    @unittest.skipUnless(HAS_QT, "PySide6 not installed")
    def test_default_dir_never_none(self):
        self.assertTrue(os.path.isdir(qt_ui.default_output_dir(None)))
        self.assertTrue(os.path.isdir(qt_ui.default_output_dir(r"C:\definitely\missing")))


if __name__ == "__main__":
    unittest.main()
