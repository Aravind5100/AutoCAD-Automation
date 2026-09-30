"""
helpers.py
----------
Shared fixtures: synthetic floor plans and spreadsheets built with ezdxf,
plus a helper that runs the offline pipeline exactly as ``ui.py`` does.
"""

from __future__ import annotations

import os
import shutil
import tempfile
import unittest

import ezdxf

from annotation_writer import write_room_layers
from autocad_scanner import scan_drawing
from polygon_matcher import associate_texts_with_polygons, match_rooms
from spreadsheet_loader import load_spreadsheet
from utils import extract_building_id, filter_dataframe_by_building

ROOMS_CSV = (
    "Building ID,Floor,Room Number,Department\n"
    "0132,01,101,Eng\n"
    "0132,01,102,Admin\n"
    "0132,1,103,Lab\n"
    "9999,01,101,Other building\n"
)

# Layer names the plan + ROOMS_CSV must produce (values used as-is)
EXPECTED_LAYERS = {"0132-01-101": "101", "0132-01-102": "102", "0132-1-103": "103"}


class TempDirTestCase(unittest.TestCase):
    """TestCase with a fresh temporary folder in ``self.tmp``."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="room_annotator_test_")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def path(self, name: str) -> str:
        return os.path.join(self.tmp, name)

    def write_text(self, name: str, content: str) -> str:
        p = self.path(name)
        with open(p, "w", encoding="utf-8") as f:
            f.write(content)
        return p


def make_plan(path: str, version: str = "R2018") -> str:
    """Three 100x100 rooms (101 MTEXT, 102 MTEXT, 103 TEXT) inside a floor outline.

    Uses the MTEXT formatting codes that broke the old regex cleaner, and a
    HATCH to check that modern content survives.
    """
    doc = ezdxf.new(version)
    msp = doc.modelspace()
    for x0 in (0, 100, 200):
        _add_closed(msp, [(x0, 0), (x0 + 100, 0), (x0 + 100, 100), (x0, 100)], version)
    _add_closed(msp, [(-10, -10), (310, -10), (310, 300), (-10, 300)], version)  # floor
    if version == "R12":
        msp.add_text("101", dxfattribs={"insert": (50, 50), "height": 4})
        msp.add_text("102", dxfattribs={"insert": (150, 50), "height": 6})
    else:
        msp.add_mtext(r"\pxqc;101", dxfattribs={"insert": (50, 50), "char_height": 4})
        msp.add_mtext(r"{\fArial|b0|i0|c0|p34;102}",
                      dxfattribs={"insert": (150, 50), "char_height": 6})
        hatch = msp.add_hatch(color=2)
        hatch.paths.add_polyline_path([(0, 0), (10, 0), (10, 10)], is_closed=True)
    msp.add_text("103", dxfattribs={"insert": (250, 50), "height": 5})
    doc.saveas(path)
    return path


def _add_closed(msp, points, version):
    if version == "R12":
        msp.add_polyline2d(points, close=True)
    else:
        msp.add_lwpolyline(points, close=True)


def run_pipeline(drawing_path: str, sheet_path: str, log=None,
                 building_col="Building ID", floor_col="Floor", room_col="Room Number"):
    """Scan → associate → match → write, as ``AppUI._run_annotation`` does.

    Returns (scan, summary, annotated_doc, created_count).
    """
    df = load_spreadsheet(sheet_path)
    df = filter_dataframe_by_building(df, building_col, extract_building_id(drawing_path))
    scan = scan_drawing(drawing_path, log_fn=log)
    assoc = associate_texts_with_polygons(scan.room_texts, scan.polygons, log_fn=log)
    summary = match_rooms(scan.room_texts, assoc, df, room_col,
                          [building_col, floor_col, room_col])
    doc, created = write_room_layers(
        scan.doc, summary.results, scan.room_texts, building_col, floor_col, room_col,
        "0132", scan.existing_annotation_room_ids, log_fn=log,
    )
    return scan, summary, doc, created


def room_layer_polygons(doc) -> dict[str, list]:
    """{layer name: [polygon entities]} for every layer written by the tool."""
    return _ours(doc, "LWPOLYLINE POLYLINE")


def room_layer_labels(doc) -> dict[str, list]:
    """{layer name: [key TEXT entities]} for every layer written by the tool."""
    return _ours(doc, "TEXT")


def _ours(doc, query: str) -> dict[str, list]:
    from metadata_utils import read_xdata
    result: dict[str, list] = {}
    for e in doc.modelspace().query(query):
        if read_xdata(e) is not None:
            result.setdefault(e.dxf.layer, []).append(e)
    return result
