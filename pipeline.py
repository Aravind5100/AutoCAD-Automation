"""
pipeline.py
-----------
The room-layer pipeline as one UI-independent function, so any front end
(Tkinter, Qt, tests) can run it and show its progress.

    request  →  filter spreadsheet by building  →  DWG→DXF (AutoCAD, DWG only)
             →  scan  →  label↔polygon  →  label↔spreadsheet  →  room layers
             →  save DXF / DXF→DWG (AutoCAD)  →  RunResult (+ one row per room)

Progress is reported through two callbacks (``log(message, level)`` and
``step(text)``); ``is_cancelled()`` is checked between steps. A COM call
that is already running cannot be interrupted, so a cancel takes effect
when the current step finishes. Nothing is written when a run is cancelled.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

import pandas as pd

from annotation_writer import CREATED, SKIPPED, OutputLayers, RoomOutcome, write_room_layers
from autocad_scanner import scan_drawing
from polygon_matcher import associate_texts_with_polygons, match_rooms
from utils import filter_dataframe_by_building

# Status of rows that never reached the writer
NOT_IN_SHEET = "not in spreadsheet"
NOT_IN_DRAWING = "not in drawing"

INFO, SUCCESS, WARN, ERROR = "INFO", "SUCCESS", "WARN", "ERROR"


class RunCancelled(Exception):
    """Raised when ``is_cancelled()`` returns True between steps."""


class RunStopped(Exception):
    """The run cannot continue for an expected, user-fixable reason."""


@dataclass
class RunRequest:
    df: pd.DataFrame                # the whole spreadsheet (not yet filtered)
    drawing_path: str               # .dwg or .dxf
    output_path: str                # where to save the result (same extension)
    room_col: str
    building_col: str
    floor_col: str
    building_id: str                # e.g. "0036"; the user may have corrected it
    layers: OutputLayers = field(default_factory=OutputLayers)   # outlines / keys / details
    detail_cols: list[str] = field(default_factory=list)          # written on the details layer


@dataclass
class ResultRow:
    """One line of the per-room results table."""
    room: str
    key: str = ""
    status: str = ""                # created / skipped / failed / not in spreadsheet / not in drawing
    note: str = ""
    needs_check: bool = False


@dataclass
class RunResult:
    output_path: str
    building_id: str
    sheet_rows: int = 0             # spreadsheet rows for this building
    labels_found: int = 0
    polygons_found: int = 0
    matched: int = 0
    created: int = 0
    rows: list[ResultRow] = field(default_factory=list)

    def count(self, status: str) -> int:
        return sum(1 for r in self.rows if r.status == status)


def run(
    request: RunRequest,
    log: Callable[[str, str], None] = lambda msg, level=INFO: None,
    step: Callable[[str], None] = lambda text: None,
    is_cancelled: Callable[[], bool] = lambda: False,
) -> RunResult:
    """Run the whole pipeline. Raises RunStopped, RunCancelled, or conversion/scan errors."""
    from dwg_converter import dxf_doc_to_dwg, dwg_to_dxf, make_work_dir, remove_work_dir

    def checkpoint(text: str):
        if is_cancelled():
            raise RunCancelled()
        step(text)
        log(text, INFO)

    plain_log = lambda msg: log(msg, WARN if "WARNING" in msg else INFO)
    req = request
    result = RunResult(output_path=req.output_path, building_id=req.building_id)

    # --- building filter first: cheap, and avoids an AutoCAD round trip for nothing
    checkpoint(f"Filtering spreadsheet for building {req.building_id}...")
    sheet = filter_dataframe_by_building(req.df, req.building_col, req.building_id)
    result.sheet_rows = len(sheet)
    if sheet.empty:
        raise RunStopped(f"No spreadsheet rows have {req.building_col} = {req.building_id}.\n"
                         "Check the Building ID.")
    log(f"  {len(sheet)} rows for building {req.building_id} (of {len(req.df)})", SUCCESS)

    is_dwg = req.drawing_path.lower().endswith(".dwg")
    work_dir = make_work_dir() if is_dwg else None
    try:
        if is_dwg:
            checkpoint("Converting DWG to DXF (AutoCAD)...")
            dxf_path = dwg_to_dxf(req.drawing_path, work_dir, log_fn=plain_log)
        else:
            dxf_path = req.drawing_path

        checkpoint("Scanning the drawing...")
        scan = scan_drawing(dxf_path, log_fn=plain_log)
        result.labels_found, result.polygons_found = len(scan.room_texts), len(scan.polygons)
        if not scan.room_texts:
            raise RunStopped("No room numbers were found in the drawing.")

        checkpoint("Linking room labels to room outlines...")
        assoc = associate_texts_with_polygons(scan.room_texts, scan.polygons, log_fn=plain_log)

        checkpoint("Matching rooms to the spreadsheet...")
        key_cols = [req.building_col, req.floor_col, req.room_col]
        summary = match_rooms(scan.room_texts, assoc, sheet, req.room_col,
                              key_cols + [c for c in req.detail_cols if c not in key_cols])
        result.matched = summary.matched_count
        log(f"  Matched rooms: {summary.matched_count}", SUCCESS)
        if summary.matched_count == 0:
            raise RunStopped("None of the room numbers in the drawing match the spreadsheet.\n"
                             "Check the Room column.")

        checkpoint("Writing the room layers...")
        outcomes: list[RoomOutcome] = []
        doc, result.created = write_room_layers(
            scan.doc, summary.results, scan.room_texts, req.building_col, req.floor_col,
            req.room_col, req.building_id, scan.existing_annotation_room_ids,
            log_fn=plain_log, outcomes=outcomes, layers=req.layers, detail_cols=req.detail_cols,
        )
        result.rows = _result_rows(outcomes, summary)

        if is_dwg:
            checkpoint("Saving as DWG (AutoCAD)...")
            dxf_doc_to_dwg(doc, req.output_path, work_dir, log_fn=plain_log)
        else:
            checkpoint("Saving the DXF...")
            doc.saveas(req.output_path)
    finally:
        remove_work_dir(work_dir)

    log(f"Done -- {result.created} rooms written. Saved to {req.output_path}", SUCCESS)
    return result


def _result_rows(outcomes: list[RoomOutcome], summary) -> list[ResultRow]:
    rows = [ResultRow(o.room_id, o.key, o.status, o.note, o.needs_check) for o in outcomes]
    rows += [ResultRow(r, status=NOT_IN_SHEET, note="room label in the drawing has no spreadsheet row")
             for r in summary.unmatched_drawing]
    rows += [ResultRow(r, status=NOT_IN_DRAWING, note="spreadsheet row has no room label in the drawing")
             for r in summary.unmatched_sheet]
    return rows


__all__ = ["run", "RunRequest", "OutputLayers", "RunResult", "ResultRow", "RunCancelled", "RunStopped",
           "CREATED", "SKIPPED", "NOT_IN_SHEET", "NOT_IN_DRAWING",
           "INFO", "SUCCESS", "WARN", "ERROR"]
