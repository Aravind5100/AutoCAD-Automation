"""
polygon_matcher.py
------------------
Associates room-identifier TEXT entities with room-boundary polygons,
then matches them against spreadsheet data.

Association strategy
~~~~~~~~~~~~~~~~~~~~
1. For each room text, find all polygons whose bounding box contains the
   text insertion point (fast pre-filter).
2. Among those, run a full point-in-polygon test.
3. If multiple polygons contain the point, choose the **smallest** by area
   (the tightest room boundary).
4. If none contain the point and ``ENABLE_NEAREST_FALLBACK`` is True,
   pick the nearest polygon by centroid distance (within MAX_NEAREST_DISTANCE).
"""

from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

from config import ENABLE_NEAREST_FALLBACK, MAX_NEAREST_DISTANCE
from utils import (
    bbox_contains_point,
    distance_point_to_point,
    normalize_room_id,
    point_in_polygon,
)


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class TextPolygonAssociation:
    """Result of associating one room text with a polygon."""
    room_id: str = ""
    text_handle: str = ""
    polygon_handle: str = ""            # "" if unassociated
    match_method: str = ""              # "contains" | "nearest" | ""
    polygon_area: float = 0.0
    polygon_centroid: tuple[float, float] = (0.0, 0.0)
    polygon_vertices: list[tuple[float, float]] = field(default_factory=list)
    confidence: float = 0.0            # 0.0–1.0


@dataclass
class RoomMatch:
    """Full match: room text + polygon + spreadsheet data."""
    room_id: str = ""
    text_handle: str = ""
    polygon_handle: str = ""
    match_method: str = ""
    polygon_area: float = 0.0
    polygon_vertices: list[tuple[float, float]] = field(default_factory=list)
    sheet_room_id: str = ""
    row_data: dict[str, str] = field(default_factory=dict)
    matched: bool = False


@dataclass
class MatchSummary:
    """Aggregate statistics for the full pipeline."""
    total_texts: int = 0
    texts_with_polygon: int = 0
    texts_without_polygon: int = 0
    total_sheet_rows: int = 0
    matched_count: int = 0
    unmatched_drawing: list[str] = field(default_factory=list)
    unmatched_sheet: list[str] = field(default_factory=list)
    associations: list[TextPolygonAssociation] = field(default_factory=list)
    results: list[RoomMatch] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Text → Polygon association
# ---------------------------------------------------------------------------

def associate_texts_with_polygons(
    room_texts: list,
    polygons: list,
    log_fn=None,
) -> list[TextPolygonAssociation]:
    """Associate each room text with its best-matching polygon.

    Parameters
    ----------
    room_texts : list[RoomText]
        From autocad_scanner.
    polygons : list[RoomPolygon]
        From autocad_scanner.
    log_fn : callable, optional

    Returns
    -------
    list[TextPolygonAssociation]
        One entry per room text, in the same order.
    """
    _log(log_fn, f"  Associating {len(room_texts)} texts with {len(polygons)} polygons...")

    associations: list[TextPolygonAssociation] = []
    contained = 0
    nearest = 0
    unmatched = 0

    for rt in room_texts:
        px, py = rt.position[0], rt.position[1]
        assoc = TextPolygonAssociation(
            room_id=rt.text,
            text_handle=rt.handle,
        )

        # --- Step 1: containment (bbox pre-filter + full test) ---
        candidates = []
        for poly in polygons:
            if not bbox_contains_point(poly.bbox, px, py):
                continue
            if point_in_polygon(px, py, poly.vertices):
                candidates.append(poly)

        if candidates:
            # Pick the smallest containing polygon
            best = min(candidates, key=lambda p: p.area)
            assoc.polygon_handle = best.handle
            assoc.match_method = "contains"
            assoc.polygon_area = best.area
            assoc.polygon_centroid = best.centroid
            assoc.polygon_vertices = best.vertices
            assoc.confidence = 1.0
            contained += 1

        elif ENABLE_NEAREST_FALLBACK and polygons:
            # --- Step 2: nearest centroid fallback ---
            best_dist = float("inf")
            best_poly = None
            for poly in polygons:
                d = distance_point_to_point(px, py, *poly.centroid)
                if d < best_dist:
                    best_dist = d
                    best_poly = poly
            if best_poly and best_dist <= MAX_NEAREST_DISTANCE:
                assoc.polygon_handle = best_poly.handle
                assoc.match_method = "nearest"
                assoc.polygon_area = best_poly.area
                assoc.polygon_centroid = best_poly.centroid
                assoc.polygon_vertices = best_poly.vertices
                assoc.confidence = max(0.0, 1.0 - best_dist / MAX_NEAREST_DISTANCE)
                nearest += 1
            else:
                unmatched += 1
        else:
            unmatched += 1

        associations.append(assoc)

    _log(log_fn, f"    Contained: {contained}  |  Nearest: {nearest}  |  Unmatched: {unmatched}")
    return associations


# ---------------------------------------------------------------------------
# Room matching (drawing ↔ spreadsheet)
# ---------------------------------------------------------------------------

def match_rooms(
    room_texts: list,
    associations: list[TextPolygonAssociation],
    df: pd.DataFrame,
    room_id_column: str,
    selected_columns: list[str],
) -> MatchSummary:
    """Match room texts (with polygon associations) to spreadsheet rows.

    Parameters
    ----------
    room_texts : list[RoomText]
    associations : list[TextPolygonAssociation]
        Same length and order as *room_texts*.
    df : pd.DataFrame
        Already filtered by building.
    room_id_column : str
        Column name for room IDs in the spreadsheet.
    selected_columns : list[str]
        Columns to include in annotation text.

    Returns
    -------
    MatchSummary
    """
    summary = MatchSummary(
        total_texts=len(room_texts),
        associations=associations,
    )

    # Count polygon associations
    summary.texts_with_polygon = sum(1 for a in associations if a.polygon_handle)
    summary.texts_without_polygon = summary.total_texts - summary.texts_with_polygon

    # Build normalised spreadsheet lookup
    sheet_lookup: dict[str, tuple[str, pd.Series]] = {}
    for _, row in df.iterrows():
        raw_val = str(row[room_id_column])
        norm_key = normalize_room_id(raw_val)
        if norm_key and norm_key not in sheet_lookup:
            sheet_lookup[norm_key] = (raw_val, row)

    summary.total_sheet_rows = len(sheet_lookup)

    # Deduplicate drawing rooms while preserving order
    seen: set[str] = set()
    matched_sheet_keys: set[str] = set()

    for rt, assoc in zip(room_texts, associations):
        norm = normalize_room_id(rt.text)
        if norm in seen:
            continue
        seen.add(norm)

        result = RoomMatch(
            room_id=rt.text,
            text_handle=rt.handle,
            polygon_handle=assoc.polygon_handle,
            match_method=assoc.match_method,
            polygon_area=assoc.polygon_area,
            polygon_vertices=assoc.polygon_vertices,
        )

        if norm in sheet_lookup:
            raw_val, row = sheet_lookup[norm]
            result.sheet_room_id = raw_val
            result.matched = True
            result.row_data = _extract_row_data(row, selected_columns)
            matched_sheet_keys.add(norm)
            summary.matched_count += 1
        else:
            summary.unmatched_drawing.append(rt.text)

        summary.results.append(result)

    # Unmatched spreadsheet rows
    for norm_key, (raw_val, _) in sheet_lookup.items():
        if norm_key not in matched_sheet_keys:
            summary.unmatched_sheet.append(raw_val)

    return summary


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _extract_row_data(row: pd.Series, columns: list[str]) -> dict[str, str]:
    data: dict[str, str] = {}
    for col in columns:
        if col in row.index:
            val = row[col]
            data[col] = "" if pd.isna(val) or val == "" else str(val)
    return data


def _log(fn, msg: str) -> None:
    if fn is not None:
        fn(msg)
