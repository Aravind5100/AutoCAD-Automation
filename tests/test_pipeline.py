"""
test_pipeline.py
----------------
End-to-end offline runs: spreadsheet + DXF → DXF with room outlines, keys and
details on their own layers (no AutoCAD).
"""

import unittest

import ezdxf

from annotation_writer import OutputLayers, write_room_layers
from autocad_scanner import scan_drawing
from metadata_utils import read_xdata
from tests.helpers import (
    EXPECTED_KEYS,
    ROOMS_CSV,
    TempDirTestCase,
    make_plan,
    detail_labels,
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

    def _run_and_save(self, drawing, name, sheet=None, log=None, detail_cols=()):
        scan, summary, doc, created = run_pipeline(drawing, sheet or self.sheet, log=log,
                                                   detail_cols=detail_cols)
        out = self.path(name)
        doc.saveas(out)
        return scan, summary, created, ezdxf.readfile(out)

    def test_outlines_and_keys_on_their_own_layers(self):
        _, summary, created, out = self._run_and_save(self.plan, "out.dxf")
        self.assertEqual(created, 3)
        self.assertEqual(summary.unmatched_drawing, [])
        layers = room_key_polygons(out)
        # values as-is from the spreadsheet: floor "01" and "1" are kept as written,
        # and building 9999's row for room 101 is not used
        self.assertEqual(set(layers), set(EXPECTED_KEYS))
        self.assertEqual(tool_layers(out), {"ROOM_OUTLINES", "ROOM_KEYS"})
        self.assertNotIn("ROOM_DETAILS", out.layers)               # no detail columns picked
        for name in EXPECTED_KEYS:
            self.assertNotIn(name, out.layers)                      # no per-room layers
        for name, room in EXPECTED_KEYS.items():
            [poly] = layers[name]
            self.assertEqual(poly.dxf.layer, "ROOM_OUTLINES")
            self.assertEqual(room_key_labels(out)[name][0].dxf.layer, "ROOM_KEYS")
            self.assertEqual(poly.dxftype(), "LWPOLYLINE")
            self.assertTrue(poly.closed)
            self.assertAlmostEqual(polygon_area(list(poly.get_points(format="xy"))), 10000.0)
            meta = read_xdata(poly)
            self.assertEqual((meta.room_id, meta.building_id, meta.match_method,
                              meta.annotation_type), (room, "0132", "contains", "room_outline"))

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

    def test_rerun_replaces_earlier_output_without_duplicates(self):
        self._run_and_save(self.plan, "0132_run1.dxf")    # building ID comes from the file name
        scan2, _, created2, out2 = self._run_and_save(self.path("0132_run1.dxf"), "run2.dxf")
        self.assertEqual(scan2.existing_annotation_room_ids, {"101", "102", "103"})
        self.assertEqual(len(scan2.previous_output), 6)   # 3 outline copies + 3 key labels
        self.assertEqual(len(scan2.polygons), 4)          # copies not rescanned as rooms
        self.assertEqual(len(scan2.room_texts), 3)        # key labels not rescanned as rooms
        self.assertEqual(created2, 3)                     # written again, not skipped
        self.assertEqual({k: len(v) for k, v in room_key_labels(out2).items()},
                         {k: 1 for k in EXPECTED_KEYS})
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

    def test_detail_columns_on_details_layer_under_the_key(self):
        scan, _, created, out = self._run_and_save(self.plan, "0132_out.dxf",
                                                   detail_cols=["Department", "Floor"])
        self.assertEqual(created, 3)
        self.assertEqual(tool_layers(out), {"ROOM_OUTLINES", "ROOM_KEYS", "ROOM_DETAILS"})
        details = detail_labels(out)
        keys = {read_xdata(t[0]).room_id: t[0] for t in room_key_labels(out).values()}
        expected = {"101": ["Eng", "01"], "102": ["Admin", "01"], "103": ["Lab", "1"]}
        for room, values in expected.items():
            texts = details[room]
            self.assertEqual([t.dxf.text for t in texts], values)       # in column order
            self.assertEqual([read_xdata(t).field for t in texts], ["Department", "Floor"])
            self.assertEqual({t.dxf.layer for t in texts}, {"ROOM_DETAILS"})
            key = keys[room]
            self.assertLess(texts[0].dxf.insert.y, key.dxf.insert.y)     # under the key
            self.assertAlmostEqual(texts[0].dxf.insert.x, key.dxf.insert.x)
        # re-run with other details: detail labels are not mistaken for room labels,
        # and the earlier details are replaced
        scan2, _, created2, out2 = self._run_and_save(self.path("0132_out.dxf"), "out2.dxf",
                                                      detail_cols=["Department"])
        self.assertEqual((len(scan2.room_texts), created2), (3, 3))
        self.assertEqual({r: [t.dxf.text for t in ts] for r, ts in detail_labels(out2).items()},
                         {"101": ["Eng"], "102": ["Admin"], "103": ["Lab"]})

    def test_rerun_can_add_details_and_rename_layers(self):
        self._run_and_save(self.plan, "run1.dxf")                       # no details
        from polygon_matcher import associate_texts_with_polygons, match_rooms
        from spreadsheet_loader import load_spreadsheet
        cols = ["Building ID", "Floor", "Room Number"]
        scan = scan_drawing(self.path("run1.dxf"))
        assoc = associate_texts_with_polygons(scan.room_texts, scan.polygons)
        summary = match_rooms(scan.room_texts, assoc, load_spreadsheet(self.sheet),
                              "Room Number", cols + ["Department"])
        outcomes, logs = [], []
        layers = OutputLayers(outlines="A-ROOMS", keys="A-KEYS", details="A-INFO")
        doc, created = write_room_layers(scan.doc, summary.results, scan.room_texts, *cols,
                                         "0132", scan.previous_output, log_fn=logs.append,
                                         outcomes=outcomes, layers=layers,
                                         detail_cols=["Department"])
        self.assertEqual(created, 3)
        self.assertEqual(tool_layers(doc), {"A-ROOMS", "A-KEYS", "A-INFO"})
        for old in ("ROOM_OUTLINES", "ROOM_KEYS"):                   # emptied -> removed
            self.assertNotIn(old, doc.layers)
        self.assertEqual(sum(len(t) for t in detail_labels(doc).values()), 3)
        self.assertTrue(all("earlier run" in o.note and not o.needs_check for o in outcomes))
        self.assertTrue(any("Removed 6 entities" in m for m in logs), logs)

    def test_rerun_keeps_layers_still_in_use(self):
        doc = ezdxf.readfile(make_plan(self.path("0132_L.dxf")))
        doc.saveas(self.path("0132_L.dxf"))
        self._run_and_save(self.path("0132_L.dxf"), "run1.dxf")
        run1 = ezdxf.readfile(self.path("run1.dxf"))
        run1.modelspace().add_line((0, 0), (1, 1), dxfattribs={"layer": "ROOM_KEYS"})  # user's own
        run1.saveas(self.path("run1.dxf"))
        from polygon_matcher import associate_texts_with_polygons, match_rooms
        from spreadsheet_loader import load_spreadsheet
        cols = ["Building ID", "Floor", "Room Number"]
        scan = scan_drawing(self.path("run1.dxf"))
        summary = match_rooms(scan.room_texts,
                              associate_texts_with_polygons(scan.room_texts, scan.polygons),
                              load_spreadsheet(self.sheet), "Room Number", cols)
        doc, _ = write_room_layers(scan.doc, summary.results, scan.room_texts, *cols, "0132",
                                   scan.previous_output,
                                   layers=OutputLayers(outlines="A-ROOMS", keys="A-KEYS"))
        self.assertIn("ROOM_KEYS", doc.layers)                       # still holds the line
        self.assertNotIn("ROOM_OUTLINES", doc.layers)

    def test_room_labelled_twice_is_reported(self):
        doc = ezdxf.new("R2018")
        msp = doc.modelspace()
        msp.add_lwpolyline([(0, 0), (100, 0), (100, 100), (0, 100)], close=True)
        msp.add_text("101", dxfattribs={"insert": (10, 80), "height": 5})
        msp.add_text("101", dxfattribs={"insert": (10, 20), "height": 5})   # same room again
        doc.saveas(self.path("0132_DUP.dxf"))
        _, summary, created, _ = self._run_and_save(self.path("0132_DUP.dxf"), "o.dxf")
        self.assertEqual(created, 1)
        self.assertEqual(summary.repeated_labels, ["101"])

    def test_empty_detail_value_left_out(self):
        sheet = self.write_text("s.csv", "Building ID,Floor,Room Number,Room Name\n"
                                         "0132,01,101,Office\n0132,01,102,\n0132,1,103,Lab\n")
        _, _, created, out = self._run_and_save(self.plan, "o.dxf", sheet=sheet,
                                                detail_cols=["Room Name"])
        self.assertEqual(created, 3)
        self.assertEqual({r: [t.dxf.text for t in ts] for r, ts in detail_labels(out).items()},
                         {"101": ["Office"], "103": ["Lab"]})

    def test_details_that_do_not_fit_flag_the_room(self):
        doc = ezdxf.new("R2018")
        msp = doc.modelspace()
        room = [(0, 0), (60, 0), (60, 12), (0, 12)]        # room for the key, not 3 more lines
        msp.add_lwpolyline(room, close=True)
        msp.add_text("101", dxfattribs={"insert": (3, 7), "height": 4})
        doc.saveas(self.path("0132_SM.dxf"))
        sheet = self.write_text("s.csv", "Building ID,Floor,Room Number,A,B,C\n"
                                         "0132,01,101,Alpha,Bravo,Charlie\n")
        outcomes = []
        from polygon_matcher import associate_texts_with_polygons, match_rooms
        from spreadsheet_loader import load_spreadsheet
        scan = scan_drawing(self.path("0132_SM.dxf"))
        assoc = associate_texts_with_polygons(scan.room_texts, scan.polygons)
        cols = ["Building ID", "Floor", "Room Number"]
        summary = match_rooms(scan.room_texts, assoc, load_spreadsheet(sheet), "Room Number",
                              cols + ["A", "B", "C"])
        doc, created = write_room_layers(scan.doc, summary.results, scan.room_texts, *cols,
                                         "0132", set(), outcomes=outcomes,
                                         detail_cols=["A", "B", "C"])
        [o] = outcomes
        self.assertEqual(created, 1)
        self.assertTrue(o.needs_check)
        self.assertIn("detail labels do not fit", o.note)
        [key] = room_key_labels(doc)["0132-01-101"]
        self.assertTrue(point_in_polygon(key.dxf.insert.x, key.dxf.insert.y, room))  # key still placed well

    def test_custom_layer_names(self):
        from polygon_matcher import associate_texts_with_polygons, match_rooms
        from spreadsheet_loader import load_spreadsheet
        cols = ["Building ID", "Floor", "Room Number"]
        scan = scan_drawing(self.plan)
        assoc = associate_texts_with_polygons(scan.room_texts, scan.polygons)
        summary = match_rooms(scan.room_texts, assoc, load_spreadsheet(self.sheet),
                              "Room Number", cols)
        layers = OutputLayers(outlines="A-AREA-ROOMS", keys="A-AREA-KEYS", details="A-AREA-INFO")
        doc, created = write_room_layers(scan.doc, summary.results, scan.room_texts, *cols,
                                         "0132", set(), layers=layers)
        self.assertEqual(created, 3)
        self.assertEqual(tool_layers(doc), {"A-AREA-ROOMS", "A-AREA-KEYS"})
        self.assertNotIn("ROOM_KEYS", doc.layers)
        self.assertNotIn("ROOM_OUTLINES", doc.layers)

    def test_nothing_to_write_returns_drawing(self):
        scan = scan_drawing(self.plan)
        doc, created = write_room_layers(self.plan, [], [], "B", "F", "R", "0132",
                                         scan.previous_output)
        self.assertIsInstance(doc, ezdxf.document.Drawing)
        self.assertEqual(created, 0)


if __name__ == "__main__":
    unittest.main()
