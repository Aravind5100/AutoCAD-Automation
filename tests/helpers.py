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

# Room keys the plan + ROOMS_CSV must produce (values used as-is) -> room
EXPECTED_KEYS = {"0132-01-101": "101", "0132-01-102": "102", "0132-1-103": "103"}


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
                 building_col="Building ID", floor_col="Floor", room_col="Room Number",
                 detail_cols=()):
    """Scan → associate → match → write, as ``AppUI._run_annotation`` does.

    Returns (scan, summary, annotated_doc, created_count).
    """
    df = load_spreadsheet(sheet_path)
    df = filter_dataframe_by_building(df, building_col, extract_building_id(drawing_path))
    scan = scan_drawing(drawing_path, log_fn=log)
    assoc = associate_texts_with_polygons(scan.room_texts, scan.polygons, log_fn=log)
    summary = match_rooms(scan.room_texts, assoc, df, room_col,
                          [building_col, floor_col, room_col, *detail_cols])
    doc, created = write_room_layers(
        scan.doc, summary.results, scan.room_texts, building_col, floor_col, room_col,
        "0132", scan.existing_annotation_room_ids, log_fn=log, detail_cols=detail_cols,
    )
    return scan, summary, doc, created


def room_key_labels(doc) -> dict[str, list]:
    """{room key: [key TEXT entities]} written by the tool (found by their XData)."""
    from metadata_utils import KEY, read_xdata
    result: dict[str, list] = {}
    for e in doc.modelspace().query("TEXT"):
        meta = read_xdata(e)
        if meta is not None and meta.annotation_type == KEY:
            result.setdefault(e.dxf.text, []).append(e)
    return result


def room_key_polygons(doc) -> dict[str, list]:
    """{room key: [outline copies]} written by the tool; the key comes from the
    key label of the same room (both carry the room ID in their XData)."""
    from metadata_utils import read_xdata
    key_of_room = {read_xdata(t).room_id: key
                   for key, texts in room_key_labels(doc).items() for t in texts}
    result: dict[str, list] = {}
    for e in doc.modelspace().query("LWPOLYLINE POLYLINE"):
        meta = read_xdata(e)
        if meta is not None:
            result.setdefault(key_of_room.get(meta.room_id, meta.room_id), []).append(e)
    return result


def detail_labels(doc) -> dict[str, list]:
    """{room ID: [detail TEXT entities, top to bottom]} written by the tool."""
    from metadata_utils import DETAIL, read_xdata
    result: dict[str, list] = {}
    for e in doc.modelspace().query("TEXT"):
        meta = read_xdata(e)
        if meta is not None and meta.annotation_type == DETAIL:
            result.setdefault(meta.room_id, []).append(e)
    for texts in result.values():
        texts.sort(key=lambda t: -t.dxf.insert.y)
    return result


def tool_layers(doc) -> set[str]:
    """Layers of every entity written by the tool."""
    from metadata_utils import read_xdata
    return {e.dxf.layer for e in doc.modelspace() if read_xdata(e) is not None}
