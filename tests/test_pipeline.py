"""
test_pipeline.py
----------------
End-to-end offline runs: spreadsheet + DXF → annotated DXF (no AutoCAD).
"""

import unittest

import ezdxf

from annotation_writer import write_annotations
from autocad_scanner import scan_drawing
from metadata_utils import read_xdata
from tests.helpers import ROOMS_CSV, TempDirTestCase, make_plan, run_pipeline
from utils import polygon_area


class TestPipeline(TempDirTestCase):

    def setUp(self):
        super().setUp()
        self.plan = make_plan(self.path("0132_TEST.dxf"))
        self.sheet = self.write_text("rooms.csv", ROOMS_CSV)

    def _run_and_save(self, drawing, name):
        scan, summary, doc, inserted = run_pipeline(drawing, self.sheet)
        out = self.path(name)
        doc.saveas(out)
        return scan, summary, inserted, ezdxf.readfile(out)

    def test_annotations_written(self):
        scan, summary, inserted, out = self._run_and_save(self.plan, "out.dxf")
        self.assertEqual(inserted, 3)
        self.assertEqual(summary.unmatched_drawing, [])
        msp = out.modelspace()

        blocks = {}
        for ins in msp.query("INSERT"):
            self.assertEqual(ins.dxf.layer, "ROOM_DATA")
            meta = read_xdata(ins)
            blocks[ins.dxf.name] = ([(a.dxf.tag, a.dxf.text, a.dxf.height) for a in ins.attribs],
                                    meta.room_id, meta.building_id, meta.match_method)
        # building 9999's row for room 101 must not be used
        self.assertEqual(blocks, {
            "ROOM_BLOCK_101": ([("DEPARTMENT", "Eng", 4.0)], "101", "0132", "contains"),
            "ROOM_BLOCK_102": ([("DEPARTMENT", "Admin", 6.0)], "102", "0132", "contains"),
            "ROOM_BLOCK_103": ([("DEPARTMENT", "Lab", 5.0)], "103", "0132", "contains"),
        })

        # XData polygon handles point at the room polygons, not the floor outline
        polys = {e.dxf.handle: e for e in msp.query("LWPOLYLINE")}
        for ins in msp.query("INSERT"):
            pts = polys[read_xdata(ins).polygon_handle].get_points(format="xy")
            self.assertAlmostEqual(polygon_area(list(pts)), 10000.0)

        outlines = msp.query('*[layer=="ROOM_BLOCK_OUTLINE"]')
        self.assertEqual(len(outlines), 3)
        self.assertEqual({e.dxftype() for e in outlines}, {"LWPOLYLINE"})

    def test_drawing_content_preserved(self):
        _, _, _, out = self._run_and_save(self.plan, "out.dxf")
        msp = out.modelspace()
        self.assertEqual(out.dxfversion, "AC1032")      # 2018 format kept (B3)
        self.assertEqual(len(msp.query("HATCH")), 1)
        self.assertEqual(len(msp.query("MTEXT")), 2)

    def test_rerun_adds_no_duplicates_B2(self):
        self._run_and_save(self.plan, "run1.dxf")
        scan2, _, inserted2, out2 = self._run_and_save(self.path("run1.dxf"), "run2.dxf")
        self.assertEqual(scan2.existing_annotation_room_ids, {"101", "102", "103"})
        self.assertEqual(len(scan2.polygons), 4)          # outline copies not rescanned
        self.assertEqual(inserted2, 0)
        self.assertEqual(len(out2.modelspace().query("INSERT")), 3)

    def test_r12_input_still_works(self):
        plan = make_plan(self.path("0132_R12.dxf"), version="R12")
        _, _, inserted, out = self._run_and_save(plan, "out12.dxf")
        self.assertEqual(inserted, 3)
        self.assertEqual({e.dxftype() for e in out.modelspace().query(
            '*[layer=="ROOM_BLOCK_OUTLINE"]')}, {"POLYLINE"})

    def test_nothing_to_write_returns_drawing_B13(self):
        scan = scan_drawing(self.plan)
        doc, inserted = write_annotations(self.plan, [], scan.room_texts, "0132", set())
        self.assertIsInstance(doc, ezdxf.document.Drawing)
        self.assertEqual(inserted, 0)


if __name__ == "__main__":
    unittest.main()
