"""
config.py
---------
Centralised configuration constants for the AutoCAD Room Annotation tool.
All tuneable values live here so they can be adjusted without touching logic.
"""

# ---------------------------------------------------------------------------
# Spreadsheet
# ---------------------------------------------------------------------------
EXCEL_HEADER_ROW: int = 2          # 0-indexed; 2 → 3rd row is the header
CSV_HEADER_ROW: int = 0            # 0-indexed; 0 → 1st row

# ---------------------------------------------------------------------------
# Building identifier
# ---------------------------------------------------------------------------
BUILDING_ID_LENGTH: int = 4

# ---------------------------------------------------------------------------
# AutoCAD annotation output
# ---------------------------------------------------------------------------
OUTPUT_LAYER: str = "ROOM_INFO_AI"
ANNOTATION_COLOR: int = 3          # AutoCAD colour index (3 = green)
DEFAULT_TEXT_HEIGHT: float = 10.0
MTEXT_WIDTH_FACTOR: float = 25.0   # MTEXT width = text_height × this
VERTICAL_SPACING_MULTIPLIER: float = 1.6

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
# Attributed block inserts (ArcGIS-compatible)
# ---------------------------------------------------------------------------
BLOCK_NAME_PREFIX: str = "ROOM_BLOCK"         # prefix for block definition names
BLOCK_LAYER: str = "ROOM_DATA"                # layer for block inserts
BLOCK_OUTLINE_LAYER: str = "ROOM_BLOCK_OUTLINE"  # layer for outline rectangle
ATTR_TEXT_HEIGHT_FACTOR: float = 1.0          # attr height = room text height × this
ATTR_LINE_SPACING: float = 1.6               # vertical spacing between attributes
BLOCK_PADDING: float = 0.5                   # padding inside outline rectangle
ARCGIS_SAFE_LAYER: str = "ROOM_DATA"         # ArcGIS-safe layer name

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
