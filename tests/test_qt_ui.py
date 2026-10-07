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

from tests.helpers import ROOMS_CSV, TempDirTestCase, make_plan

# Building 0132 on one floor only, so the Floor box fills itself in
QT_ROOMS_CSV = ROOMS_CSV.replace("0132,1,103", "0132,01,103")
QT_KEYS = {"0132-01-101", "0132-01-102", "0132-01-103"}


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
        self.win.load_sheet(self.write_text("rooms.csv", QT_ROOMS_CSV), wait=True)
        self.win.set_drawing(make_plan(self.path("0132_TEST.dxf")))


class TestSetup(QtTestCase):

    def test_run_disabled_until_ready(self):
        self.assertFalse(self.win.run_btn.isEnabled())
        self.ready_window()
        self.assertEqual(self.win.columns(), ("Room Number", "Building ID", "Floor"))
        self.assertEqual(self.win.building_edit.text(), "0132")
        self.assertEqual(self.win.floor_id(), "01")               # the building's only floor
        self.assertEqual(self.win.preview.text(), "e.g.  0132-01-101")
        self.assertTrue(self.win.run_btn.isEnabled())
        self.assertFalse(self.win.cancel_btn.isEnabled())

    def test_preview_follows_edited_building_id(self):
        self.ready_window()
        self.win.building_edit.setText("9999")
        self.assertEqual(self.win.preview.text(), "e.g.  9999-01-101")
        self.win.building_edit.setText("")
        self.assertFalse(self.win.run_btn.isEnabled())

    def test_floor_must_be_chosen_when_building_has_several(self):
        self.win.load_sheet(self.write_text("rooms.csv", ROOMS_CSV + "0132,2,201,Lab\n"), wait=True)
        self.win.set_drawing(make_plan(self.path("0132_TEST.dxf")))
        combo = self.win.floor_id_combo
        self.assertEqual([combo.itemText(i) for i in range(combo.count())], ["01", "1", "2"])
        self.assertEqual(self.win.floor_id(), "")
        self.assertFalse(self.win.run_btn.isEnabled())
        self.assertIn("Floor", self.win.run_btn.toolTip())
        combo.setCurrentText("1")
        self.assertTrue(self.win.run_btn.isEnabled())
        self.assertEqual(self.win.preview.text(), "e.g.  0132-1-103")
        self.win.start_run(self.path("out.dxf"), wait=True)
        self.assertEqual([r.key for r in self.win.result.rows if r.status == "created"],
                         ["0132-1-103"])                           # only floor 1 rows used
        self.win.building_edit.setText("9999")                    # one floor: picked for you
        self.assertEqual(self.win.floor_id(), "01")

    def test_same_column_twice_blocks_run(self):
        self.ready_window()
        self.win.floor_combo.setCurrentText("Room Number")
        self.assertFalse(self.win.run_btn.isEnabled())
        self.assertIn("three different columns", self.win.run_btn.toolTip())

    def test_layer_boxes_validated_and_remembered(self):
        self.ready_window()
        self.assertEqual(self.win.layer_names(), {"outlines": "ROOM_OUTLINES", "keys": "ROOM_KEYS",
                                                  "details": "ROOM_DETAILS"})
        edits = self.win.layer_edits
        edits["keys"].setText("BAD:NAME")
        self.assertFalse(self.win.run_btn.isEnabled())
        self.assertIn("Keys layer", self.win.run_btn.toolTip())
        edits["keys"].setText("room_outlines")                    # same as outlines (any case)
        self.assertIn("different names", self.win.run_btn.toolTip())
        edits["keys"].setText("A-AREA-KEYS")
        edits["details"].setText("")                              # unused: no details picked
        self.assertTrue(self.win.run_btn.isEnabled())
        self.win.set_detail_columns(["Department"])
        self.assertIn("Details layer", self.win.run_btn.toolTip())
        edits["details"].setText("A-AREA-INFO")
        self.assertTrue(self.win.run_btn.isEnabled())
        self.win.start_run(self.path("out.dxf"), wait=True)
        self.assertEqual(self.win.settings.value("layer_keys"), "A-AREA-KEYS")
        self.assertEqual(self.win.settings.value("layer_details"), "A-AREA-INFO")

    def test_detail_columns_listed_and_remembered(self):
        self.ready_window()
        combo = self.win.detail_combo
        self.assertEqual(combo.items(), ["Building ID", "Floor", "Room Number", "Department"])
        self.assertEqual(self.win.detail_columns(), [])
        self.assertIn("None", combo.summary())
        self.win.set_detail_columns(["Department", "Floor"])
        self.assertEqual(self.win.detail_columns(), ["Floor", "Department"])   # sheet order
        self.assertEqual(combo.summary(), "Floor, Department")
        box = next(b for b in combo.boxes() if b.text() == "Department")
        box.click()                                       # a click on a checkbox ticks it
        self.assertEqual(self.win.detail_columns(), ["Floor"])
        box.click()
        self.assertEqual(self.win.detail_columns(), ["Floor", "Department"])
        self.assertEqual(combo.text(), "Floor, Department")
        self.win.set_detail_columns(["Department"])
        self.win.start_run(self.path("out.dxf"), wait=True)
        self.assertEqual(self.win.result.created, 3)
        win2 = qt_ui.MainWindow(self.settings)                   # next session
        win2.load_sheet(self.path("rooms.csv"), wait=True)
        self.assertEqual(win2.detail_columns(), ["Department"])
        win2.deleteLater()

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
        self.assertTrue(QT_KEYS <= layers)
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
