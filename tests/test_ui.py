"""
test_ui.py
----------
Save-location prompt, thread-safe dialogs, and a full offline run of
``AppUI._run_annotation`` with DXF input. File dialogs are scripted.
"""

import os
import unittest
from unittest import mock

import ezdxf

from tests.helpers import (
    EXPECTED_LAYERS,
    ROOMS_CSV,
    TempDirTestCase,
    make_plan,
    room_layer_polygons,
)

try:
    import tkinter as tk
    _root = tk.Tk()
    _root.withdraw()
    _root.destroy()
    HAS_DISPLAY = True
except Exception:       # no display available (e.g. CI without a desktop)
    HAS_DISPLAY = False

import ui
from spreadsheet_loader import load_spreadsheet


@unittest.skipUnless(HAS_DISPLAY, "Tk needs a display")
class UITestCase(TempDirTestCase):

    def setUp(self):
        super().setUp()
        self.root = tk.Tk()
        self.root.withdraw()
        self.app = ui.AppUI(self.root)

    def tearDown(self):
        self.root.destroy()
        super().tearDown()


class TestAskOutputPath(UITestCase):

    SRC = r"C:\Drawings\0132_LAB.dwg"

    def _ask(self, answers, src=SRC):
        with mock.patch.object(ui.filedialog, "asksaveasfilename",
                               side_effect=answers) as dialog, \
                mock.patch.object(ui.messagebox, "showerror") as err:
            result = self.app._ask_output_path(src)
        return result, dialog, err

    def test_starts_outside_source_folder_with_suggested_name(self):
        result, dialog, _ = self._ask([""])
        self.assertIsNone(result)                               # cancelled
        kw = dialog.call_args.kwargs
        self.assertNotEqual(os.path.normcase(kw["initialdir"]), os.path.normcase(r"C:\Drawings"))
        self.assertEqual(kw["initialfile"], "0132_LAB_annotated.dwg")
        self.assertEqual(kw["filetypes"], [("DWG files", "*.dwg")])

    def test_original_refused_then_extension_added(self):
        result, dialog, err = self._ask([r"c:\drawings\0132_lab.DWG", r"D:\Out\result"])
        self.assertEqual(result, r"D:\Out\result.dwg")
        self.assertEqual(dialog.call_count, 2)
        err.assert_called_once()

    def test_remembers_last_folder(self):
        folder = self.tmp
        self._ask([os.path.join(folder, "a.dwg")])
        _, dialog, _ = self._ask([""])
        self.assertEqual(dialog.call_args.kwargs["initialdir"], folder)

    def test_dxf_input_stays_dxf(self):
        result, dialog, _ = self._ask([r"D:\Out\x"], src=r"C:\Drawings\0132.dxf")
        self.assertEqual(result, r"D:\Out\x.dxf")
        self.assertEqual(dialog.call_args.kwargs["filetypes"], [("DXF files", "*.dxf")])


class TestColumns(UITestCase):

    def test_columns_detected_and_key_previewed(self):
        sheet = self.write_text("rooms.csv", ROOMS_CSV)
        with mock.patch.object(self.app, "_log"):
            self.app._load_spreadsheet_columns(sheet, background=False)
        self.assertEqual((self.app._room_id_col.get(), self.app._building_col.get(),
                          self.app._floor_col.get()), ("Room Number", "Building ID", "Floor"))
        self.assertEqual(self.app._key_example.cget("text"), "First row -> 0132-01-101")

    def test_same_column_twice_refused(self):
        self.app._spreadsheet_path.set("s.csv")
        self.app._dwg_path.set("0132_X.dwg")
        self.app._df = load_spreadsheet(self.write_text("rooms.csv", ROOMS_CSV))
        for var, value in ((self.app._room_id_col, "Room Number"),
                           (self.app._building_col, "Building ID"),
                           (self.app._floor_col, "Room Number")):
            var.set(value)
        with mock.patch.object(ui.messagebox, "showwarning") as warn, \
                mock.patch.object(self.app, "_ask_output_path") as ask:
            self.app._on_run()
        warn.assert_called_once()
        ask.assert_not_called()


class TestRunAnnotation(UITestCase):

    def test_dialog_scheduled_on_main_thread_B6(self):
        with mock.patch.object(self.root, "after") as after:
            self.app._dialog("info", "t", "m")
        after.assert_called_once()

    def test_full_offline_run(self):
        plan = make_plan(self.path("0132_TEST.dxf"))
        df = load_spreadsheet(self.write_text("rooms.csv", ROOMS_CSV))
        out = os.path.join(self.tmp, "out", "result.dxf")
        os.makedirs(os.path.dirname(out))
        logs, dialogs = [], []
        before = sorted(os.listdir(self.tmp))
        with mock.patch.object(self.app, "_log", lambda m, tag="INFO": logs.append((tag, m))), \
                mock.patch.object(self.app, "_dialog", lambda *a: dialogs.append(a[:2])):
            self.app._run_annotation(plan, df, "Room Number", "Building ID",
                                     "Floor", out)
        self.assertTrue(os.path.exists(out))
        self.assertEqual(dialogs, [("info", "Complete")])
        self.assertTrue(any("Room layers created  : 3" in m for _, m in logs), logs)
        self.assertEqual(set(room_layer_polygons(ezdxf.readfile(out))), set(EXPECTED_LAYERS))
        self.assertEqual(sorted(os.listdir(self.tmp)), before)   # nothing new beside input
        self.assertFalse([m for t, m in logs if t == "ERROR"])


if __name__ == "__main__":
    unittest.main()
