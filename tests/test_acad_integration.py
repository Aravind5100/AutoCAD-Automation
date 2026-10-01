"""
test_acad_integration.py
------------------------
Real AutoCAD round trip. Skipped unless RUN_ACAD_TESTS=1 is set, because it
drives the AutoCAD installed on this machine (works on synthetic files only
and restores AutoCAD's dialog settings).

    set RUN_ACAD_TESTS=1 && .venv\\Scripts\\python.exe -m unittest tests.test_acad_integration
"""

import os
import unittest

import ezdxf

from metadata_utils import read_xdata
from tests.helpers import (
    EXPECTED_KEYS,
    ROOMS_CSV,
    TempDirTestCase,
    make_plan,
    room_key_polygons,
    run_pipeline,
)

RUN = os.environ.get("RUN_ACAD_TESTS") == "1"


@unittest.skipUnless(RUN, "set RUN_ACAD_TESTS=1 to run against real AutoCAD")
class TestAutoCADRoundTrip(TempDirTestCase):

    def setUp(self):
        super().setUp()
        import pythoncom
        import win32com.client
        import dwg_converter as dc
        pythoncom.CoInitialize()
        self.dc = dc
        self.acad = win32com.client.Dispatch("AutoCAD.Application")
        self.sysvars_before = self._sysvars()
        self.docs_before = self._doc_names()

        # a real DWG input made from the synthetic plan
        src = make_plan(self.path("src.dxf"))
        os.makedirs(self.path("in"))
        self.dwg = self.path(os.path.join("in", "0132_ACADTEST.dwg"))
        doc = dc._call(lambda: self.acad.Documents.Open(src, True))
        dc._call(lambda: doc.SaveAs(self.dwg, dc.ACAD_DWG_FORMAT))
        dc._close(doc)
        self.sheet = self.write_text("rooms.csv", ROOMS_CSV)

    def tearDown(self):
        import pythoncom
        self.assertEqual(self._sysvars(), self.sysvars_before, "AutoCAD settings changed")
        self.assertEqual(self._doc_names(), self.docs_before, "drawings left open")
        pythoncom.CoUninitialize()
        super().tearDown()

    # -- helpers ----------------------------------------------------------
    def _doc_names(self):
        c = self.dc._call
        return sorted(c(lambda i=i: self.acad.Documents.Item(i)).FullName
                      for i in range(c(lambda: self.acad.Documents.Count)))

    def _sysvars(self):
        c = self.dc._call
        if c(lambda: self.acad.Documents.Count):
            doc = c(lambda: self.acad.ActiveDocument)
            return {v: c(lambda: doc.GetVariable(v)) for v in self.dc._SUPPRESSED_SYSVARS}
        doc = c(lambda: self.acad.Documents.Add())
        try:
            return {v: c(lambda: doc.GetVariable(v)) for v in self.dc._SUPPRESSED_SYSVARS}
        finally:
            self.dc._close(doc)

    def _convert(self, out_name):
        work = self.dc.make_work_dir()
        try:
            dxf = self.dc.dwg_to_dxf(self.dwg, work)
            _, _, annotated, inserted = run_pipeline(dxf, self.sheet)
            out = self.dc.dxf_doc_to_dwg(annotated, self.path(out_name), work)
        finally:
            self.dc.remove_work_dir(work)
        self.assertFalse(os.path.exists(work))
        return out, inserted

    def _read_dwg(self, dwg):
        check = self.path("check.dxf")
        doc = self.dc._call(lambda: self.acad.Documents.Open(dwg, True))
        self.dc._call(lambda: doc.SaveAs(check, self.dc.ACAD_DXF_FORMAT))
        self.dc._close(doc)
        return ezdxf.readfile(check)

    # -- tests ------------------------------------------------------------
    def test_round_trip_produces_real_dwg_with_annotations(self):
        before = sorted(os.listdir(os.path.dirname(self.dwg)))
        out, inserted = self._convert("result.dwg")
        self.assertEqual(inserted, 3)
        with open(out, "rb") as f:
            self.assertEqual(f.read(6), b"AC1032")                     # B1
        self.assertEqual(sorted(os.listdir(os.path.dirname(self.dwg))), before)  # B4

        check = self._read_dwg(out)
        msp = check.modelspace()
        handles = {e.dxf.handle for e in msp}
        layers = room_key_polygons(check)
        self.assertEqual(set(layers), set(EXPECTED_KEYS))             # room keys survive
        self.assertIn("ROOM_KEYS", check.layers)                       # the one room layer
        for name, room in EXPECTED_KEYS.items():
            self.assertEqual(layers[name][0].dxf.layer, "ROOM_KEYS")
            meta = read_xdata(layers[name][0])
            self.assertEqual(meta.room_id, room)
            self.assertIn(meta.polygon_handle, handles)                 # polygon link holds
        self.assertEqual(len(msp.query("INSERT")), 0)
        self.assertEqual(len(msp.query("HATCH")), 1)                    # B3

    def test_open_drawing_with_unsaved_changes_untouched_B9(self):
        import pythoncom
        import win32com.client
        c = self.dc._call
        user_doc = c(lambda: self.acad.Documents.Open(self.dwg, False))
        centre = win32com.client.VARIANT(pythoncom.VT_ARRAY | pythoncom.VT_R8, [5, 5, 0])
        c(lambda: user_doc.ModelSpace.AddCircle(centre, 2))
        try:
            self._convert("result.dwg")
            self.assertEqual(c(lambda: user_doc.FullName), self.dwg)
            self.assertFalse(c(lambda: user_doc.Saved))
        finally:
            self.dc._close(user_doc)


if __name__ == "__main__":
    unittest.main()
