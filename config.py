"""
config.py
---------
Centralised configuration constants for the AutoCAD Room Annotation tool.
All tuneable values live here so they can be adjusted without touching logic.
"""

import os


# ---------------------------------------------------------------------------
# Spreadsheet
# ---------------------------------------------------------------------------
EXCEL_HEADER_ROW: int = 2          # 0-indexed; 2 → 3rd row is the header
CSV_HEADER_ROW: int = 0            # 0-indexed; 0 → 1st row
# Parsed spreadsheets are cached here so re-loading an unchanged file is instant
SPREADSHEET_CACHE_DIR: str = os.path.join(
    os.environ.get("LOCALAPPDATA") or os.path.expanduser("~"),
    "RoomAnnotator", "spreadsheet_cache",
)

# ---------------------------------------------------------------------------
# Building identifier
# ---------------------------------------------------------------------------
BUILDING_ID_LENGTH: int = 4

# ---------------------------------------------------------------------------
# Room layer output (ArcGIS)
# ---------------------------------------------------------------------------
# Matched rooms are written on THREE layers (names editable in the app):
#   outlines  a copy of each room's outline
#   keys      a text label with the room key inside each room
#               <Building><SEP><Floor><SEP><Room>      e.g. 0132-01-101
#             (the three values as-is from the matched spreadsheet row)
#   details   optional: values of spreadsheet columns the user picks (e.g. Room
#             Name), one TEXT per value, stacked under the key label
ROOM_OUTLINE_LAYER_DEFAULT: str = "ROOM_OUTLINES"
ROOM_KEY_LAYER_DEFAULT: str = "ROOM_KEYS"
ROOM_DETAIL_LAYER_DEFAULT: str = "ROOM_DETAILS"
ROOM_KEY_SEPARATOR: str = "-"
ROOM_OUTLINE_LAYER_COLOR: int = 3  # AutoCAD colour index (3 = green)
ROOM_KEY_LAYER_COLOR: int = 2      # 2 = yellow
ROOM_DETAIL_LAYER_COLOR: int = 4   # 4 = cyan
# The key label goes just under the room label: same height as the room label,
# this many label-heights of gap below it (also the gap between detail lines)
ROOM_TAG_GAP_FACTOR: float = 0.5
# Characters AutoCAD does not allow in layer names (checked for the output layer names)
LAYER_NAME_FORBIDDEN_CHARS: str = '<>/\\":;?*|=`'
# Outline layers written by the old block-based versions; never room boundaries
LEGACY_OUTLINE_LAYERS: tuple[str, ...] = ("ROOM_BLOCK_OUTLINE",)
DEFAULT_TEXT_HEIGHT: float = 10.0

# ---------------------------------------------------------------------------
# Room identifier heuristics
# ---------------------------------------------------------------------------
ROOM_ID_MAX_LENGTH: int = 20
ROOM_ID_MIN_DIGITS: int = 1
ROOM_ID_MAX_WORDS: int = 3

# ---------------------------------------------------------------------------
# Polygon detection
# ---------------------------------------------------------------------------
MIN_POLYGON_AREA: float = 1.0           # ignore degenerate polygons
ENABLE_NEAREST_FALLBACK: bool = True     # use nearest polygon when none contains text
MAX_NEAREST_DISTANCE: float = 500.0      # max centroid distance for fallback

# ---------------------------------------------------------------------------
# Metadata / XData
# ---------------------------------------------------------------------------
XDATA_APP_NAME: str = "ROOM_INFO_AI"

# ---------------------------------------------------------------------------
# DWG ↔ DXF conversion
# ---------------------------------------------------------------------------
# AutoCAD AcSaveAsType codes (from the AutoCAD type library):
#   1 = R12 DXF (lossy — do not use), 64 = 2018 DWG (= acNative), 65 = 2018 DXF
ACAD_DXF_FORMAT: int = 65                # DWG -> DXF: 2018 DXF keeps the full drawing
ACAD_DWG_FORMAT: int = 64                # DXF -> DWG: native 2018 DWG
COM_RETRY_SECONDS: float = 60.0          # keep retrying calls AutoCAD rejects while busy

# ---------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------
OUTPUT_SUFFIX: str = "_annotated"        # suggested output name: <input>_annotated.<ext>

# ---------------------------------------------------------------------------
# Scan performance
# ---------------------------------------------------------------------------
SCAN_PROGRESS_INTERVAL: int = 2000       # log progress every N entities
