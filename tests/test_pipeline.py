"""
test_pipeline.py
----------------
End-to-end offline runs: spreadsheet + DXF → DXF with room layers (no AutoCAD).
"""

import unittest

import ezdxf

from annotation_writer import write_room_layers
from autocad_scanner import scan_drawing
from metadata_utils import read_xdata
from tests.helpers import (
    EXPECTED_LAYERS,
    ROOMS_CSV,
    TempDirTestCase,
    make_plan,
    room_layer_polygons,
    run_pipeline,
)
from utils import polygon_area


class TestRoomLayers(TempDirTestCase):

    def setUp(self):
        super().setUp()
        self.plan = make_plan(self.path("0132_TEST.dxf"))
        self.sheet = self.write_text("rooms.csv", ROOMS_CSV)

    def _run_and_save(self, drawing, name, sheet=None, log=None):
        scan, summary, doc, created = run_pipeline(drawing, sheet or self.sheet, log=log)
        out = self.path(name)
        doc.saveas(out)
        return scan, summary, created, ezdxf.readfile(out)

    def test_one_layer_per_room_named_building_floor_room(self):
        _, summary, created, out = self._run_and_save(self.plan, "out.dxf")
        self.assertEqual(created, 3)
        self.assertEqual(summary.unmatched_drawing, [])
        layers = room_layer_polygons(out)
        # values as-is from the spreadsheet: floor "01" and "1" are kept as written,
        # and building 9999's row for room 101 is not used
        self.assertEqual(set(layers), set(EXPECTED_LAYERS))
        for name, room in EXPECTED_LAYERS.items():
            self.assertIn(name, out.layers)
            [poly] = layers[name]
            self.assertEqual(poly.dxftype(), "LWPOLYLINE")
            self.assertTrue(poly.closed)
            self.assertAlmostEqual(polygon_area(list(poly.get_points(format="xy"))), 10000.0)
            meta = read_xdata(poly)
            self.assertEqual((meta.room_id, meta.building_id, meta.match_method,
                              meta.annotation_type), (room, "0132", "contains", "room_layer"))

    def test_no_blocks_and_originals_untouched(self):
        original = ezdxf.readfile(self.plan)
        orig_layers = {e.dxf.handle: e.dxf.layer for e in original.modelspace()}
        _, _, _, out = self._run_and_save(self.plan, "out.dxf")
        msp = out.modelspace()
        self.assertEqual(len(msp.query("INSERT")), 0)
        for e in msp:
            if e.dxf.handle in orig_layers:          # every original entity kept its layer
                self.assertEqual(e.dxf.layer, orig_layers[e.dxf.handle])
        self.assertEqual(len(msp), len(orig_layers) + 3)   # only the 3 copies were added

    def test_source_polygon_handle_links_to_the_room(self):
        _, _, _, out = self._run_and_save(self.plan, "out.dxf")
        by_handle = {e.dxf.handle: e for e in out.modelspace()}
        for polys in room_layer_polygons(out).values():
            source = by_handle[read_xdata(polys[0]).polygon_handle]
            self.assertEqual(list(source.get_points(format="xy")),
                             list(polys[0].get_points(format="xy")))
            self.assertIsNone(read_xdata(source))       # the original carries no XData

    def test_drawing_content_preserved(self):
        _, _, _, out = self._run_and_save(self.plan, "out.dxf")
        msp = out.modelspace()
        self.assertEqual(out.dxfversion, "AC1032")      # 2018 format kept (B3)
        self.assertEqual(len(msp.query("HATCH")), 1)
        self.assertEqual(len(msp.query("MTEXT")), 2)

    def test_rerun_adds_no_duplicates(self):
        self._run_and_save(self.plan, "run1.dxf")
        scan2, _, created2, out2 = self._run_and_save(self.path("run1.dxf"), "run2.dxf")
        self.assertEqual(scan2.existing_annotation_room_ids, {"101", "102", "103"})
        self.assertEqual(len(scan2.polygons), 4)          # copies not rescanned as rooms
        self.assertEqual(created2, 0)
        self.assertEqual({k: len(v) for k, v in room_layer_polygons(out2).items()},
                         {k: 1 for k in EXPECTED_LAYERS})

    def test_empty_floor_value_skips_room_with_warning(self):
        sheet = self.write_text("s.csv", "Building ID,Floor,Room Number\n"
                                         "0132,01,101\n0132,,102\n0132,01,103\n")
        logs = []
        _, _, created, out = self._run_and_save(self.plan, "o.dxf", sheet=sheet,
                                                log=logs.append)
        self.assertEqual(created, 2)
        self.assertEqual(set(room_layer_polygons(out)), {"0132-01-101", "0132-01-103"})
        self.assertTrue(any("empty" in m and "102" in m for m in logs), logs)

    def test_forbidden_layer_characters_replaced(self):
        doc = ezdxf.new("R2018")
        msp = doc.modelspace()
        msp.add_lwpolyline([(0, 0), (100, 0), (100, 100), (0, 100)], close=True)
        msp.add_text("B1-101", dxfattribs={"insert": (50, 50), "height": 5})
        doc.saveas(self.path("0132_X.dxf"))
        sheet = self.write_text("s.csv", "Building ID,Floor,Room Number\n0132,B1/2,B1-101\n")
        _, _, created, out = self._run_and_save(self.path("0132_X.dxf"), "o.dxf", sheet=sheet)
        self.assertEqual(created, 1)
        self.assertEqual(set(room_layer_polygons(out)), {"0132-B1_2-B1-101"})

    def test_room_without_polygon_skipped_with_warning(self):
        doc = ezdxf.new("R2018")
        doc.modelspace().add_text("101", dxfattribs={"insert": (50, 50), "height": 5})
        doc.saveas(self.path("0132_NP.dxf"))
        logs = []
        _, summary, created, out = self._run_and_save(self.path("0132_NP.dxf"), "o.dxf",
                                                      log=logs.append)
        self.assertEqual((summary.matched_count, created), (1, 0))
        self.assertTrue(any("no room boundary" in m for m in logs), logs)

    def test_r12_input_still_works(self):
        plan = make_plan(self.path("0132_R12.dxf"), version="R12")
        _, _, created, out = self._run_and_save(plan, "out12.dxf")
        self.assertEqual(created, 3)
        layers = room_layer_polygons(out)
        self.assertEqual(set(layers), set(EXPECTED_LAYERS))
        self.assertEqual({p[0].dxftype() for p in layers.values()}, {"POLYLINE"})

    def test_nothing_to_write_returns_drawing(self):
        scan = scan_drawing(self.plan)
        doc, created = write_room_layers(self.plan, [], "B", "F", "R", "0132",
                                         scan.existing_annotation_room_ids)
        self.assertIsInstance(doc, ezdxf.document.Drawing)
        self.assertEqual(created, 0)


if __name__ == "__main__":
    unittest.main()
