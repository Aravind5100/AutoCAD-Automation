"""
test_pipeline.py
----------------
End-to-end offline runs: spreadsheet + DXF → DXF with room keys on one layer (no AutoCAD).
"""

import unittest

import ezdxf

from annotation_writer import write_room_layers
from autocad_scanner import scan_drawing
from metadata_utils import read_xdata
from tests.helpers import (
    EXPECTED_KEYS,
    ROOMS_CSV,
    TempDirTestCase,
    make_plan,
    room_key_labels,
    room_key_polygons,
    run_pipeline,
    tool_layers,
)
from utils import point_in_polygon, polygon_area


class TestRoomKeys(TempDirTestCase):

    def setUp(self):
        super().setUp()
        self.plan = make_plan(self.path("0132_TEST.dxf"))
        self.sheet = self.write_text("rooms.csv", ROOMS_CSV)

    def _run_and_save(self, drawing, name, sheet=None, log=None):
        scan, summary, doc, created = run_pipeline(drawing, sheet or self.sheet, log=log)
        out = self.path(name)
        doc.saveas(out)
        return scan, summary, created, ezdxf.readfile(out)

    def test_all_rooms_on_one_layer_with_building_floor_room_keys(self):
        _, summary, created, out = self._run_and_save(self.plan, "out.dxf")
        self.assertEqual(created, 3)
        self.assertEqual(summary.unmatched_drawing, [])
        layers = room_key_polygons(out)
        # values as-is from the spreadsheet: floor "01" and "1" are kept as written,
        # and building 9999's row for room 101 is not used
        self.assertEqual(set(layers), set(EXPECTED_KEYS))
        self.assertEqual(tool_layers(out), {"ROOM_KEYS"})          # one layer for every room
        self.assertIn("ROOM_KEYS", out.layers)
        for name in EXPECTED_KEYS:
            self.assertNotIn(name, out.layers)                      # no per-room layers
        for name, room in EXPECTED_KEYS.items():
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
        self.assertEqual(len(msp), len(orig_layers) + 6)   # 3 outline copies + 3 key labels

    def test_key_label_written_under_each_room_label(self):
        scan, _, _, out = self._run_and_save(self.plan, "out.dxf")
        labels = room_key_labels(out)
        self.assertEqual(set(labels), set(EXPECTED_KEYS))
        by_room = {t.text: t for t in scan.room_texts}
        for key, room in EXPECTED_KEYS.items():
            [tag] = labels[key]
            self.assertEqual(tag.dxf.text, key)
            self.assertEqual(read_xdata(tag).room_id, room)
            src = by_room[room]
            self.assertAlmostEqual(tag.dxf.height, src.text_height)
            self.assertLess(tag.dxf.insert.y + tag.dxf.height, src.label_bbox[1])   # below label
            self.assertAlmostEqual(tag.dxf.insert.x, src.label_bbox[0])

    def test_key_label_shrinks_to_fit_small_room(self):
        doc = ezdxf.new("R2018")
        msp = doc.modelspace()
        room = [(0, 0), (30, 0), (30, 40), (0, 40)]   # narrower than a full-size key (~38.5)
        msp.add_lwpolyline(room, close=True)
        msp.add_text("101", dxfattribs={"insert": (3, 25), "height": 5})
        doc.saveas(self.path("0132_SM.dxf"))
        _, _, created, out = self._run_and_save(self.path("0132_SM.dxf"), "o.dxf")
        [tag] = room_key_labels(out)["0132-01-101"]
        self.assertEqual(created, 1)
        self.assertLess(tag.dxf.height, 5)                    # scaled down
        self.assertTrue(point_in_polygon(tag.dxf.insert.x, tag.dxf.insert.y, room))

    def test_two_line_labels_use_the_room_number_line(self):
        doc = ezdxf.new("R2018")
        msp = doc.modelspace()
        msp.add_lwpolyline([(0, 0), (100, 0), (100, 100), (0, 100)], close=True)
        msp.add_lwpolyline([(100, 0), (200, 0), (200, 100), (100, 100)], close=True)
        msp.add_mtext("101\\P170", dxfattribs={"insert": (20, 80), "char_height": 5})     # number / area
        msp.add_mtext("OFFICE\\P102", dxfattribs={"insert": (120, 80), "char_height": 5})  # name / number
        doc.saveas(self.path("0132_ML.dxf"))
        scan, summary, created, out = self._run_and_save(self.path("0132_ML.dxf"), "o.dxf")
        self.assertEqual(sorted(t.text for t in scan.room_texts), ["101", "102"])
        self.assertEqual(created, 2)
        self.assertEqual(set(room_key_labels(out)), {"0132-01-101", "0132-01-102"})

    def test_source_polygon_handle_links_to_the_room(self):
        _, _, _, out = self._run_and_save(self.plan, "out.dxf")
        by_handle = {e.dxf.handle: e for e in out.modelspace()}
        for polys in room_key_polygons(out).values():
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
        self.assertEqual(len(scan2.room_texts), 3)        # key labels not rescanned as rooms
        self.assertEqual(created2, 0)
        self.assertEqual({k: len(v) for k, v in room_key_polygons(out2).items()},
                         {k: 1 for k in EXPECTED_KEYS})

    def test_empty_floor_value_skips_room_with_warning(self):
        sheet = self.write_text("s.csv", "Building ID,Floor,Room Number\n"
                                         "0132,01,101\n0132,,102\n0132,01,103\n")
        logs = []
        _, _, created, out = self._run_and_save(self.plan, "o.dxf", sheet=sheet,
                                                log=logs.append)
        self.assertEqual(created, 2)
        self.assertEqual(set(room_key_polygons(out)), {"0132-01-101", "0132-01-103"})
        self.assertTrue(any("empty" in m and "102" in m for m in logs), logs)

    def test_key_text_kept_exactly_as_in_spreadsheet(self):
        doc = ezdxf.new("R2018")
        msp = doc.modelspace()
        msp.add_lwpolyline([(0, 0), (100, 0), (100, 100), (0, 100)], close=True)
        msp.add_text("B1-101", dxfattribs={"insert": (50, 50), "height": 5})
        doc.saveas(self.path("0132_X.dxf"))
        sheet = self.write_text("s.csv", "Building ID,Floor,Room Number\n0132,B1/2,B1-101\n")
        _, _, created, out = self._run_and_save(self.path("0132_X.dxf"), "o.dxf", sheet=sheet)
        self.assertEqual(created, 1)
        self.assertEqual(set(room_key_polygons(out)), {"0132-B1/2-B1-101"})

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
        layers = room_key_polygons(out)
        self.assertEqual(set(layers), set(EXPECTED_KEYS))
        self.assertEqual({p[0].dxftype() for p in layers.values()}, {"POLYLINE"})

    def test_custom_layer_name(self):
        from polygon_matcher import associate_texts_with_polygons, match_rooms
        from spreadsheet_loader import load_spreadsheet
        cols = ["Building ID", "Floor", "Room Number"]
        scan = scan_drawing(self.plan)
        assoc = associate_texts_with_polygons(scan.room_texts, scan.polygons)
        summary = match_rooms(scan.room_texts, assoc, load_spreadsheet(self.sheet),
                              "Room Number", cols)
        doc, created = write_room_layers(scan.doc, summary.results, scan.room_texts, *cols,
                                         "0132", set(), layer="A-AREA-KEYS")
        self.assertEqual(created, 3)
        self.assertEqual(tool_layers(doc), {"A-AREA-KEYS"})
        self.assertNotIn("ROOM_KEYS", doc.layers)

    def test_nothing_to_write_returns_drawing(self):
        scan = scan_drawing(self.plan)
        doc, created = write_room_layers(self.plan, [], [], "B", "F", "R", "0132",
                                         scan.existing_annotation_room_ids)
        self.assertIsInstance(doc, ezdxf.document.Drawing)
        self.assertEqual(created, 0)


if __name__ == "__main__":
    unittest.main()
