"""
pipeline.py
-----------
The room-layer pipeline as one UI-independent function, so any front end
(Tkinter, Qt, tests) can run it and show its progress.

    request  →  filter spreadsheet by building (+ floor)  →  DWG→DXF (AutoCAD, DWG only)
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

from annotation_writer import (
    CREATED,
    SKIPPED,
    OutputLayers,
    RoomOutcome,
    layers_with_drawing_content,
    write_room_layers,
)
from autocad_scanner import scan_drawing
from polygon_matcher import apply_leading_zero_matches, associate_texts_with_polygons, match_rooms
from utils import filter_dataframe_by_building, filter_dataframe_by_value, normalize_room_id

# Status of rows that never reached the writer
NOT_IN_SHEET = "not in spreadsheet"
NOT_IN_DRAWING = "not in drawing"

INFO, SUCCESS, WARN, ERROR = "INFO", "SUCCESS", "WARN", "ERROR"

# Answers to confirm_leading_zeros: which room number the key uses
USE_DRAWING, USE_SHEET = "drawing", "sheet"


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
    floor_id: str = ""              # the floor this drawing shows, e.g. "1"; "" = all floors
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
    leading_zero_matches: list[str] = field(default_factory=list)   # confirmed drawing labels

    def count(self, status: str) -> int:
        return sum(1 for r in self.rows if r.status == status)


def run(
    request: RunRequest,
    log: Callable[[str, str], None] = lambda msg, level=INFO: None,
    step: Callable[[str], None] = lambda text: None,
    is_cancelled: Callable[[], bool] = lambda: False,
    confirm_leading_zeros: Callable[[list[tuple[str, str]]], str | None] | None = None,
) -> RunResult:
    """Run the whole pipeline. Raises RunStopped, RunCancelled, or conversion/scan errors.

    *confirm_leading_zeros* is asked what to do with room labels that match a
    spreadsheet room only when leading zeros are ignored (drawing ``015``, sheet
    ``15``); it gets the (drawing, sheet) pairs and returns USE_DRAWING (key uses
    ``015``), USE_SHEET (key uses ``15``) or None (skip, they stay unmatched).
    Without it they are skipped.
    """
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
    if req.floor_id:
        sheet = filter_dataframe_by_value(sheet, req.floor_col, req.floor_id)
        if sheet.empty:
            raise RunStopped(f"Building {req.building_id} has no spreadsheet rows with "
                             f"{req.floor_col} = {req.floor_id}.\nCheck the Floor.")
        log(f"  {len(sheet)} rows on floor {req.floor_id}", SUCCESS)
    result.sheet_rows = len(sheet)
    # The same room number twice in these rows: only the first row is used
    ids = sheet[req.room_col].map(normalize_room_id)
    repeated = sorted(set(sheet.loc[ids.duplicated() & (ids != ""), req.room_col]))
    if repeated:
        where = f"floor {req.floor_id}" if req.floor_id else "this building (choose a floor)"
        log(f"  WARNING: {len(repeated)} room numbers appear more than once on {where}; "
            f"the first row is used for: {', '.join(repeated[:10])}"
            + (f" (+{len(repeated) - 10} more)" if len(repeated) > 10 else ""), WARN)

    is_dwg = req.drawing_path.lower().endswith(".dwg")
    work_dir = make_work_dir() if is_dwg else None
    try:
        if is_dwg:
            checkpoint("Converting DWG to DXF (AutoCAD)...")
            dxf_path = dwg_to_dxf(req.drawing_path, work_dir, log_fn=plain_log)
        else:
            dxf_path = req.drawing_path

        checkpoint("Scanning the drawing...")
        scan = scan_drawing(dxf_path, log_fn=plain_log, known_room_ids=sheet[req.room_col])
        result.labels_found, result.polygons_found = len(scan.room_texts), len(scan.polygons)
        if not scan.room_texts:
            raise RunStopped("No room numbers were found in the drawing.")
        # Output layers must not be layers the drawing itself uses (B30)
        out_layers = [req.layers.outlines, req.layers.keys]
        if req.detail_cols:
            out_layers.append(req.layers.details)
        clash = layers_with_drawing_content(scan.doc, out_layers)
        if clash:
            raise RunStopped(
                f"The drawing already uses layer{'s' if len(clash) > 1 else ''} "
                f"{', '.join(clash)} for its own content.\n"
                "Writing there would mix the room keys with it. "
                "Choose other layer names in step 2.")

        checkpoint("Linking room labels to room outlines...")
        assoc = associate_texts_with_polygons(scan.room_texts, scan.polygons, log_fn=plain_log)

        checkpoint("Matching rooms to the spreadsheet...")
        key_cols = [req.building_col, req.floor_col, req.room_col]
        summary = match_rooms(scan.room_texts, assoc, sheet, req.room_col,
                              key_cols + [c for c in req.detail_cols if c not in key_cols])
        zero_pairs = [(label, value) for label, value, _ in summary.leading_zero_matches]
        if zero_pairs:
            shown = ", ".join(f"{a} = {b}" for a, b in zero_pairs[:10])
            choice = confirm_leading_zeros(zero_pairs) if confirm_leading_zeros else None
            if choice in (USE_DRAWING, USE_SHEET):
                applied = apply_leading_zero_matches(summary)
                if choice == USE_DRAWING:                  # the key shows the drawing's number
                    labels = {label for label, _ in applied}
                    for match in summary.results:
                        if match.room_id in labels:
                            match.row_data[req.room_col] = match.room_id
                result.leading_zero_matches = [label for label, _ in applied]
                which = "drawing" if choice == USE_DRAWING else "spreadsheet"
                log(f"  {len(applied)} rooms matched ignoring leading zeros (confirmed; keys use "
                    f"the {which} number): {shown}", WARN)
            else:
                log(f"  {len(zero_pairs)} room labels would match if leading zeros were ignored "
                    f"(not used): {shown}", WARN)
        if is_cancelled():
            raise RunCancelled()
        result.matched = summary.matched_count
        log(f"  Matched rooms: {summary.matched_count}", SUCCESS)
        if summary.matched_count == 0:
            raise RunStopped("None of the room numbers in the drawing match the spreadsheet.\n"
                             "Check the Room column.")

        checkpoint("Writing the room layers...")
        outcomes: list[RoomOutcome] = []
        doc, result.created = write_room_layers(
            scan.doc, summary.results, scan.room_texts, req.building_col, req.floor_col,
            req.room_col, req.building_id, scan.previous_output,
            log_fn=plain_log, outcomes=outcomes, layers=req.layers, detail_cols=req.detail_cols,
        )
        result.rows = _result_rows(outcomes, summary, result.leading_zero_matches)
        if summary.secondary_ignored:
            log(f"  {len(summary.secondary_ignored)} texts under a room number (e.g. area figures) "
                f"were not treated as rooms", INFO)
        if summary.repeated_labels:
            log(f"  WARNING: {len(summary.repeated_labels)} room numbers are labelled more than "
                f"once in the drawing; only the first label is used: "
                f"{', '.join(sorted(set(summary.repeated_labels))[:10])}", WARN)

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


def _result_rows(outcomes: list[RoomOutcome], summary, zero_matched=()) -> list[ResultRow]:
    repeated = {normalize_room_id(r) for r in summary.repeated_labels}
    zero_matched = set(zero_matched)
    for o in outcomes:              # the room that was written: point at the extra label
        if normalize_room_id(o.room_id) in repeated:
            o.note = "; ".join(filter(None, [o.note, "labelled more than once in the drawing"]))
            o.needs_check = o.needs_check or o.status == CREATED
        if o.room_id in zero_matched:
            o.note = "; ".join(filter(None, [o.note, "leading zeros differ from the spreadsheet "
                                                     "(match confirmed)"]))
            o.needs_check = o.needs_check or o.status == CREATED
    rows = [ResultRow(o.room_id, o.key, o.status, o.note, o.needs_check) for o in outcomes]
    rows += [ResultRow(r, status=SKIPPED,
                       note="room number labelled again in the drawing; only the first label is used")
             for r in summary.repeated_labels]
    rows += [ResultRow(r, status=NOT_IN_SHEET, note="room label in the drawing has no spreadsheet row")
             for r in summary.unmatched_drawing]
    rows += [ResultRow(r, status=NOT_IN_DRAWING, note="spreadsheet row has no room label in the drawing")
             for r in summary.unmatched_sheet]
    return rows


__all__ = ["run", "RunRequest", "OutputLayers", "USE_DRAWING", "USE_SHEET", "RunResult", "ResultRow", "RunCancelled", "RunStopped",
           "CREATED", "SKIPPED", "NOT_IN_SHEET", "NOT_IN_DRAWING",
           "INFO", "SUCCESS", "WARN", "ERROR"]
