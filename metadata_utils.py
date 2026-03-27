"""
metadata_utils.py
-----------------
XData helpers for linking AutoCAD annotations to room polygons.

AutoCAD Extended Data (XData) lets us attach custom key-value metadata to any
entity.  This module provides read/write wrappers so that every annotation
inserted by this tool carries a machine-readable reference back to:
  - the room identifier
  - the polygon handle it represents
  - the building identifier
  - the source text handle
  - the association method (contains / nearest)
"""

from __future__ import annotations

from dataclasses import dataclass, field

import pythoncom
import win32com.client

from config import XDATA_APP_NAME


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

def register_xdata_app(doc) -> None:
    """Register the XData application name in the drawing if not present."""
    try:
        doc.RegisteredApplications.Add(XDATA_APP_NAME)
    except Exception:
        pass  # already registered — safe to ignore


# ---------------------------------------------------------------------------
# Write XData
# ---------------------------------------------------------------------------

def write_xdata(entity, meta: AnnotationMetadata) -> bool:
    """Attach *meta* as XData to *entity*.  Returns True on success."""
    try:
        xd_types = win32com.client.VARIANT(
            pythoncom.VT_ARRAY | pythoncom.VT_I2,
            [1001, 1000, 1000, 1000, 1000, 1000, 1000],
        )
        xd_values = win32com.client.VARIANT(
            pythoncom.VT_ARRAY | pythoncom.VT_VARIANT,
            [
                XDATA_APP_NAME,
                meta.room_id,
                meta.polygon_handle,
                meta.building_id,
                meta.text_handle,
                meta.match_method,
                meta.annotation_type,
            ],
        )
        entity.SetXData(xd_types, xd_values)
        return True
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Read XData
# ---------------------------------------------------------------------------

def read_xdata(entity) -> AnnotationMetadata | None:
    """Read our XData from *entity*.  Returns None if absent or unreadable."""
    try:
        xd_type = win32com.client.VARIANT(
            pythoncom.VT_BYREF | pythoncom.VT_VARIANT, None,
        )
        xd_value = win32com.client.VARIANT(
            pythoncom.VT_BYREF | pythoncom.VT_VARIANT, None,
        )
        entity.GetXData(XDATA_APP_NAME, xd_type, xd_value)

        values = list(xd_value.value)
        if len(values) < 7:
            return None

        return AnnotationMetadata(
            room_id=str(values[1]),
            polygon_handle=str(values[2]),
            building_id=str(values[3]),
            text_handle=str(values[4]),
            match_method=str(values[5]),
            annotation_type=str(values[6]),
        )
    except Exception:
        return None


def has_app_xdata(entity) -> bool:
    """Return True if *entity* carries XData for our application."""
    return read_xdata(entity) is not None
