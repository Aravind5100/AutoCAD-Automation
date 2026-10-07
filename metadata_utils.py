"""
metadata_utils.py
-----------------
XData helpers for linking everything the tool writes (outline copies, key
labels, detail labels) back to the source room polygon and room label.

Uses **ezdxf** for all XData read/write operations (no COM).
"""

from __future__ import annotations

from dataclasses import dataclass

import ezdxf

from config import XDATA_APP_NAME


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class AnnotationMetadata:
    """Metadata stored as XData on each entity the tool writes."""
    room_id: str = ""
    polygon_handle: str = ""
    building_id: str = ""
    text_handle: str = ""
    match_method: str = ""          # "contains" | "nearest" | ""
    annotation_type: str = ""       # OUTLINE | KEY | DETAIL ("room_layer" before the 3-layer split)
    field: str = ""                 # DETAIL only: the spreadsheet column the value comes from


# annotation_type values
OUTLINE, KEY, DETAIL = "room_outline", "room_key", "room_detail"


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
        if meta.field:
            xdata_list.append((1000, meta.field))
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
            field=str(xdata[6][1]) if len(xdata) > 6 else "",
        )
    except Exception:
        return None
