"""
test_run_pipeline.py
--------------------
pipeline.run: the UI-independent pipeline (results rows, stops, cancel).
"""

import os
import unittest

import pipeline
from spreadsheet_loader import load_spreadsheet
from tests.helpers import EXPECTED_KEYS, ROOMS_CSV, TempDirTestCase, make_plan


class TestPipelineRun(TempDirTestCase):

    def setUp(self):
        super().setUp()
        self.plan = make_plan(self.path("0132_TEST.dxf"))
        self.df = load_spreadsheet(self.write_text("rooms.csv", ROOMS_CSV + "0132,01,104,Ghost\n"))

    def request(self, **kw):
        args = dict(df=self.df, drawing_path=self.plan, output_path=self.path("out.dxf"),
                    room_col="Room Number", building_col="Building ID", floor_col="Floor",
                    building_id="0132")
        args.update(kw)
        return pipeline.RunRequest(**args)

    def test_results_rows_and_steps(self):
        steps, logs = [], []
        res = pipeline.run(self.request(), log=lambda m, lvl: logs.append((lvl, m)),
                           step=steps.append)
        self.assertTrue(os.path.exists(self.path("out.dxf")))
        self.assertEqual((res.created, res.matched, res.sheet_rows), (3, 3, 4))
        rows = {r.room: r for r in res.rows}
        for key, room in EXPECTED_KEYS.items():
            self.assertEqual((rows[room].key, rows[room].status), (key, "created"))
        self.assertEqual(rows["104"].status, pipeline.NOT_IN_DRAWING)
        self.assertEqual(steps[0], "Filtering spreadsheet for building 0132...")
        self.assertEqual(len(steps), 6)                   # DXF input: no AutoCAD steps
        self.assertFalse([m for lvl, m in logs if lvl == pipeline.ERROR])

    def test_layers_and_details_from_request(self):
        import ezdxf
        from tests.helpers import detail_labels, tool_layers
        layers = pipeline.OutputLayers(outlines="0132-ROOMS", keys="0132-KEYS", details="0132-INFO")
        pipeline.run(self.request(layers=layers, detail_cols=["Department"]))
        out = ezdxf.readfile(self.path("out.dxf"))
        self.assertEqual(tool_layers(out), {"0132-ROOMS", "0132-KEYS", "0132-INFO"})
        self.assertEqual(detail_labels(out)["102"][0].dxf.text, "Admin")

    def test_floor_filter(self):
        res = pipeline.run(self.request(floor_id="01"))
        self.assertEqual((res.created, res.sheet_rows), (2, 3))  # 101, 102 (+104 not in drawing)
        rows = {r.room: r for r in res.rows}
        self.assertEqual(rows["103"].status, pipeline.NOT_IN_SHEET)   # 103 is on floor "1"
        with self.assertRaises(pipeline.RunStopped):
            pipeline.run(self.request(floor_id="7"))

    def test_same_room_on_two_floors_uses_the_chosen_floor(self):
        df = load_spreadsheet(self.write_text("two.csv", "Building ID,Floor,Room Number\n"
                                                         "0132,01,101\n0132,02,101\n"))
        logs = []
        res = pipeline.run(self.request(df=df), log=lambda m, lvl: logs.append((lvl, m)))
        self.assertTrue(any(lvl == pipeline.WARN and "101" in m and "choose a floor" in m
                            for lvl, m in logs), logs)                # ambiguous without a floor
        res = pipeline.run(self.request(df=df, floor_id="02"))
        self.assertEqual([r.key for r in res.rows if r.status == "created"], ["0132-02-101"])

    def test_room_labelled_twice_gives_a_result_row(self):
        import ezdxf
        doc = ezdxf.readfile(self.plan)
        label = next(t for t in doc.modelspace().query("TEXT MTEXT") if "101" in t.plain_text())
        doc.modelspace().add_text("101", dxfattribs={"insert": label.dxf.insert, "height": 5})
        doc.saveas(self.plan)
        logs = []
        res = pipeline.run(self.request(), log=lambda m, lvl: logs.append((lvl, m)))
        rows = [r for r in res.rows if r.room == "101"]
        self.assertEqual(sorted(r.status for r in rows), ["created", "skipped"])
        created = next(r for r in rows if r.status == "created")
        self.assertTrue(created.needs_check)
        self.assertIn("labelled more than once", created.note)
        self.assertTrue(any(lvl == pipeline.WARN and "labelled more than once" in m
                            for lvl, m in logs), logs)

    def test_wrong_building_stops_before_any_work(self):
        with self.assertRaises(pipeline.RunStopped):
            pipeline.run(self.request(building_id="9876"))
        self.assertFalse(os.path.exists(self.path("out.dxf")))

    def test_edited_building_id_is_used(self):
        # file name says 0132, but the user corrected the building to 9999
        res = pipeline.run(self.request(building_id="9999"))
        self.assertEqual((res.created, res.sheet_rows), (1, 1))
        self.assertEqual([r.key for r in res.rows if r.status == "created"], ["9999-01-101"])

    def test_cancel_writes_nothing(self):
        calls = []

        def cancelled():
            calls.append(1)
            return len(calls) >= 3                         # cancel before the 3rd step

        with self.assertRaises(pipeline.RunCancelled):
            pipeline.run(self.request(), is_cancelled=cancelled)
        self.assertFalse(os.path.exists(self.path("out.dxf")))

    def test_no_matches_stops(self):
        df = load_spreadsheet(self.write_text("s.csv", "Building ID,Floor,Room Number\n0132,01,999\n"))
        with self.assertRaises(pipeline.RunStopped):
            pipeline.run(self.request(df=df))


if __name__ == "__main__":
    unittest.main()
