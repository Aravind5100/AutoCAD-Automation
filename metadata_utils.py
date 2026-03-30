"""
metadata_utils.py
-----------------
XData helpers for linking AutoCAD annotations to room polygons,
plus ArcGIS-safe naming utilities.

Uses **ezdxf** for all XData read/write operations (no COM).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

import ezdxf

from config import BLOCK_NAME_PREFIX, XDATA_APP_NAME


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class AnnotationMetadata:
    """Metadata stored as XData on each annotation entity."""
    room_id: str = ""
    polygon_handle: str = ""
    building_id: str = ""
    text_handle: str = ""
    match_method: str = ""          # "contains" | "nearest" | ""
    annotation_type: str = "room_info"


# ---------------------------------------------------------------------------
# XData application registration
# ---------------------------------------------------------------------------

def register_xdata_app(doc: ezdxf.document.Drawing) -> None:
    """Register the XData application name in the drawing if not present."""
    try:
        appids = doc.appids
        if XDATA_APP_NAME not in appids:
            appids.new(XDATA_APP_NAME)
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Write XData (ezdxf)
# ---------------------------------------------------------------------------

def write_xdata(entity, meta: AnnotationMetadata) -> bool:
    """Attach *meta* as XData to *entity*.  Returns True on success."""
    try:
        # ezdxf XData format: list of (group_code, value) tuples
        xdata_list = [
            (1000, meta.room_id),
            (1000, meta.polygon_handle),
            (1000, meta.building_id),
            (1000, meta.text_handle),
            (1000, meta.match_method),
            (1000, meta.annotation_type),
        ]
        entity.set_xdata(XDATA_APP_NAME, xdata_list)
        return True
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Read XData (ezdxf)
# ---------------------------------------------------------------------------

def read_xdata(entity) -> AnnotationMetadata | None:
    """Read our XData from *entity*.  Returns None if absent or unreadable."""
    try:
        xdata = entity.get_xdata(XDATA_APP_NAME)
        if xdata is None or len(xdata) < 6:
            return None

        # xdata is a list of (group_code, value) tuples
        return AnnotationMetadata(
            room_id=str(xdata[0][1]),
            polygon_handle=str(xdata[1][1]),
            building_id=str(xdata[2][1]),
            text_handle=str(xdata[3][1]),
            match_method=str(xdata[4][1]),
            annotation_type=str(xdata[5][1]),
        )
    except Exception:
        return None


def has_app_xdata(entity) -> bool:
    """Return True if *entity* carries XData for our application."""
    return read_xdata(entity) is not None


# ---------------------------------------------------------------------------
# ArcGIS-safe naming helpers
# ---------------------------------------------------------------------------

def normalize_block_name(name: str) -> str:
    """Convert *name* to an ArcGIS-safe block name.

    Rules: alphanumeric + underscore only, uppercased, max 255 chars.
    Prefixed with BLOCK_NAME_PREFIX.

    Example: ``"101-A"`` -> ``"ROOM_BLOCK_101_A"``
    """
    safe = re.sub(r"[^A-Za-z0-9]", "_", name.strip()).upper()
    safe = re.sub(r"_+", "_", safe).strip("_")
    full = f"{BLOCK_NAME_PREFIX}_{safe}"
    return full[:255]


def tag_from_column(col_name: str) -> str:
    """Convert a spreadsheet column name to an ArcGIS-safe attribute TAG.

    Rules: alphanumeric + underscore only, uppercased, max 30 chars.
    No spaces, no special characters.

    Example: ``"Occupied By"`` -> ``"OCCUPIED_BY"``
    """
    safe = re.sub(r"[^A-Za-z0-9]", "_", col_name.strip()).upper()
    safe = re.sub(r"_+", "_", safe).strip("_")
    return safe[:30]
