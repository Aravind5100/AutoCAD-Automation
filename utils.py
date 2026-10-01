"""
utils.py
--------
Shared utility helpers: column name normalization, room identifier
detection heuristics, building identifier logic, geometry primitives,
and general-purpose string helpers.
"""

import math
import os
import re

from config import (
    BUILDING_ID_LENGTH,
    LAYER_NAME_FORBIDDEN_CHARS,
    MIN_POLYGON_AREA,
    ROOM_ID_MAX_LENGTH,
    ROOM_ID_MAX_WORDS,
    ROOM_ID_MIN_DIGITS,
    ROOM_KEY_SEPARATOR,
)


# ---------------------------------------------------------------------------
# Column name normalization
# ---------------------------------------------------------------------------

def normalize_col(name: str) -> str:
    """Normalize a column name for robust fuzzy comparison.

    Steps: strip → lowercase → replace [-_.] with space →
    collapse whitespace → remove non-alphanumeric/space.
    """
    if not isinstance(name, str):
        name = str(name)
    name = name.strip().lower()
    name = re.sub(r"[-_.]", " ", name)
    name = re.sub(r"\s+", " ", name)
    name = re.sub(r"[^a-z0-9 ]", "", name)
    return name.strip()


# ---------------------------------------------------------------------------
# Building identifier helpers
# ---------------------------------------------------------------------------

_BUILDING_COL_CANDIDATES: set[str] = {
    "building", "building id", "building identifier",
    "bldg", "bldg id", "bldg identifier",
    "buildingid", "buildingidentifier",
    "bldgid", "bldgidentifier",
}


def extract_building_id(dwg_path: str) -> str:
    """First *BUILDING_ID_LENGTH* characters of the DWG filename, uppercased.

    Example: ``ENGR_floor1.dwg`` → ``ENGR``
    """
    basename = os.path.basename(dwg_path)
    name_only = os.path.splitext(basename)[0]
    return name_only[:BUILDING_ID_LENGTH].upper()


def detect_building_column(columns: list[str]) -> str | None:
    """Return the original column name that represents a building identifier."""
    for col in columns:
        if normalize_col(col) in _BUILDING_COL_CANDIDATES:
            return col
    return None


def filter_dataframe_by_building(df, building_col: str, building_id: str):
    """Return rows of *df* where *building_col* matches *building_id*
    (case-insensitive, stripped).
    """
    mask = (
        df[building_col].astype(str).str.strip().str.upper()
        == building_id.upper()
    )
    return df.loc[mask].reset_index(drop=True)


# ---------------------------------------------------------------------------
# Floor code helpers
# ---------------------------------------------------------------------------

_FLOOR_COL_CANDIDATES: set[str] = {
    "floor", "floor code", "floor id", "floor no", "floor number", "floor level",
    "floorcode", "floorid", "floorno", "floornumber",
    "flr", "flr code", "flr id", "flrcode", "flrid",
    "level", "level code", "level id",
}


def detect_floor_column(columns: list[str]) -> str | None:
    """Return the original column name that represents a floor code."""
    for col in columns:
        if normalize_col(col) in _FLOOR_COL_CANDIDATES:
            return col
    return None


# ---------------------------------------------------------------------------
# Room identifier detection heuristics
# ---------------------------------------------------------------------------

_ROOM_ID_PATTERN: re.Pattern = re.compile(
    r"^[A-Za-z0-9]([A-Za-z0-9\-]*[A-Za-z0-9])?$"
)


def is_room_identifier(text: str) -> bool:
    """Return True if *text* looks like a room identifier.

    Heuristics: not empty, length ≤ MAX, word count ≤ MAX,
    contains at least MIN digits, matches alphanumeric+hyphen pattern.

    Examples that pass: 101, 102A, B201, LAB-101
    """
    if not text or not text.strip():
        return False
    text = text.strip()
    if len(text) > ROOM_ID_MAX_LENGTH:
        return False
    words = text.split()
    if len(words) > ROOM_ID_MAX_WORDS:
        return False
    if sum(1 for ch in text if ch.isdigit()) < ROOM_ID_MIN_DIGITS:
        return False
    candidate = "".join(words)
    return bool(_ROOM_ID_PATTERN.match(candidate))


def normalize_room_id(value) -> str:
    """Strip + lowercase a room identifier for case-insensitive matching."""
    if value is None:
        return ""
    return str(value).strip().lower()


# ---------------------------------------------------------------------------
# Geometry primitives  (2-D, for polygon association)
# ---------------------------------------------------------------------------

def point_in_polygon(px: float, py: float,
                     vertices: list[tuple[float, float]]) -> bool:
    """Ray-casting algorithm.  Returns True if (px, py) is inside the polygon
    defined by *vertices* (list of (x, y) tuples, not closed — i.e. the last
    vertex is NOT a duplicate of the first).
    """
    n = len(vertices)
    inside = False
    j = n - 1
    for i in range(n):
        xi, yi = vertices[i]
        xj, yj = vertices[j]
        if ((yi > py) != (yj > py)) and \
           (px < (xj - xi) * (py - yi) / (yj - yi) + xi):
            inside = not inside
        j = i
    return inside


def polygon_area(vertices: list[tuple[float, float]]) -> float:
    """Shoelace formula — returns the unsigned area of a simple polygon."""
    n = len(vertices)
    if n < 3:
        return 0.0
    area = 0.0
    j = n - 1
    for i in range(n):
        area += (vertices[j][0] + vertices[i][0]) * \
                (vertices[j][1] - vertices[i][1])
        j = i
    return abs(area) / 2.0


def polygon_centroid(vertices: list[tuple[float, float]]) -> tuple[float, float]:
    """Return (cx, cy) centroid of a simple polygon."""
    n = len(vertices)
    if n == 0:
        return (0.0, 0.0)
    cx = cy = signed_area = 0.0
    j = n - 1
    for i in range(n):
        cross = vertices[j][0] * vertices[i][1] - \
                vertices[i][0] * vertices[j][1]
        signed_area += cross
        cx += (vertices[j][0] + vertices[i][0]) * cross
        cy += (vertices[j][1] + vertices[i][1]) * cross
        j = i
    signed_area /= 2.0
    if abs(signed_area) < 1e-10:
        # Degenerate — fall back to arithmetic mean
        cx = sum(v[0] for v in vertices) / n
        cy = sum(v[1] for v in vertices) / n
        return (cx, cy)
    cx /= 6.0 * signed_area
    cy /= 6.0 * signed_area
    return (cx, cy)


def polygon_bbox(
    vertices: list[tuple[float, float]],
) -> tuple[float, float, float, float]:
    """Return (min_x, min_y, max_x, max_y)."""
    xs = [v[0] for v in vertices]
    ys = [v[1] for v in vertices]
    return (min(xs), min(ys), max(xs), max(ys))


def bbox_contains_point(
    bbox: tuple[float, float, float, float], px: float, py: float,
) -> bool:
    """Quick check — is (px, py) inside the axis-aligned bounding box?"""
    return bbox[0] <= px <= bbox[2] and bbox[1] <= py <= bbox[3]


def distance_point_to_point(
    x1: float, y1: float, x2: float, y2: float,
) -> float:
    """Euclidean distance between two 2-D points."""
    return math.sqrt((x2 - x1) ** 2 + (y2 - y1) ** 2)


def is_valid_room_polygon(
    vertices: list[tuple[float, float]], closed: bool,
) -> bool:
    """Return True if the polygon is a plausible room boundary."""
    if not closed:
        return False
    if len(vertices) < 3:
        return False
    return polygon_area(vertices) >= MIN_POLYGON_AREA


# ---------------------------------------------------------------------------
# Room layer key
# ---------------------------------------------------------------------------

def layer_name_problem(name: str) -> str | None:
    """Why *name* cannot be used as an AutoCAD layer name, or None if it can."""
    name = (name or "").strip()
    if not name:
        return "Enter a layer name."
    bad = sorted({c for c in name if c in LAYER_NAME_FORBIDDEN_CHARS})
    if bad:
        return f"A layer name cannot contain {' '.join(bad)}"
    if len(name) > 255:
        return "A layer name can be at most 255 characters."
    return None


def build_room_key(building, floor, room) -> str | None:
    """Build the room key ``<building>-<floor>-<room>``, written as text in the drawing.

    Values are used exactly as in the spreadsheet (only surrounding whitespace
    is trimmed), so the key matches the facilities data for joins. Returns
    None when any part is empty, because the key would then be ambiguous.

    Examples: ``("0132", "01", "101")`` → ``0132-01-101``;
    ``("0132", "1", "LAB/2")`` → ``0132-1-LAB/2``
    """
    parts = ["" if v is None else str(v).strip() for v in (building, floor, room)]
    if not all(parts):
        return None
    return ROOM_KEY_SEPARATOR.join(parts)
