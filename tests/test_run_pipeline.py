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
