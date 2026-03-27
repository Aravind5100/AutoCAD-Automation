# AutoCAD Room Annotation Tool — Detailed Documentation

## Table of Contents

1. [Overview](#overview)
2. [System Requirements](#system-requirements)
3. [Project Structure](#project-structure)
4. [Module Reference](#module-reference)
5. [Data Flow & Pipeline](#data-flow--pipeline)
6. [Spreadsheet Handling](#spreadsheet-handling)
7. [Building Identifier Validation](#building-identifier-validation)
8. [AutoCAD Scanning](#autocad-scanning)
9. [Text-to-Polygon Association](#text-to-polygon-association)
10. [Room Matching](#room-matching)
11. [Annotation Writing & Polygon Linkage](#annotation-writing--polygon-linkage)
12. [XData Metadata System](#xdata-metadata-system)
13. [Deduplication](#deduplication)
14. [Geometry Engine](#geometry-engine)
15. [Configuration Reference](#configuration-reference)
16. [GUI Overview](#gui-overview)
17. [Error Handling](#error-handling)
18. [Performance Optimisations](#performance-optimisations)
19. [Querying Annotations Later](#querying-annotations-later)
20. [Known Limitations](#known-limitations)

---

## Overview

This is a **Windows desktop application** built in Python that automates the
process of annotating AutoCAD floor-plan drawings with data from a spreadsheet.

**Core capability:**
Given a spreadsheet containing room data (occupant, department, area, etc.) and
an AutoCAD DWG file containing room identifier text and room boundary polygons,
the tool:

1. Reads and filters the spreadsheet by building identifier.
2. Scans the AutoCAD drawing for room identifier text and room polygons.
3. Spatially associates each room identifier with its enclosing polygon.
4. Matches room identifiers to spreadsheet rows.
5. Inserts formatted MTEXT annotations directly below each room identifier.
6. Links each annotation to its room polygon via AutoCAD XData metadata.
7. Saves the result as a new DWG file (original is never modified).

---

## System Requirements

| Requirement       | Detail                                                    |
|-------------------|-----------------------------------------------------------|
| Operating System  | Windows (required for AutoCAD COM automation)             |
| AutoCAD           | Any version exposing the COM/ActiveX interface (2010+)    |
| Python            | 3.10 or later (uses `X | Y` union type syntax)           |
| Python packages   | `pandas`, `openpyxl`, `xlrd`, `pywin32` (see `requirements.txt`) |

---

## Project Structure

```
AutoCAD Automation/
├── main.py                 Entry point — launches the Tkinter GUI
├── config.py               All configurable constants (one file to tune)
├── ui.py                   Tkinter/ttk GUI — file pickers, dropdowns, log, progress
├── spreadsheet_loader.py   Reads CSV / XLS / XLSX with configurable header rows
├── autocad_scanner.py      Single-pass ModelSpace scan (text + polygons)
├── polygon_matcher.py      Text→polygon association + room↔spreadsheet matching
├── annotation_writer.py    Inserts MTEXT with XData linkage, dedup, layer management
├── metadata_utils.py       XData read/write helpers for annotation↔polygon links
├── utils.py                Column normalization, room ID heuristics, geometry primitives
├── requirements.txt        Python dependencies
├── README.md               Quick-start guide
└── DOCUMENTATION.md        This file — full detailed documentation
```

### Legacy files (from prior version, no longer imported)

| File                | Replaced by                                  |
|---------------------|----------------------------------------------|
| `file_loader.py`    | `spreadsheet_loader.py`                      |
| `autocad_handler.py`| `autocad_scanner.py` + `annotation_writer.py` |
| `matcher.py`        | `polygon_matcher.py`                         |

---

## Module Reference

### `config.py`

Centralised constants. Every tuneable value lives here so that no logic files
need editing for configuration changes.

Key constants:

| Constant                      | Default          | Purpose                                         |
|-------------------------------|------------------|-------------------------------------------------|
| `EXCEL_HEADER_ROW`           | `2`              | 0-indexed row for Excel column headers          |
| `CSV_HEADER_ROW`             | `0`              | 0-indexed row for CSV column headers            |
| `BUILDING_ID_LENGTH`         | `4`              | Characters extracted from DWG filename           |
| `OUTPUT_LAYER`               | `"ROOM_INFO_AI"` | AutoCAD layer for annotations                   |
| `ANNOTATION_COLOR`           | `3`              | AutoCAD colour index (3 = green)                |
| `DEFAULT_TEXT_HEIGHT`        | `10.0`           | Fallback text height if entity has none          |
| `MTEXT_WIDTH_FACTOR`        | `25.0`           | MTEXT width = text_height × this factor         |
| `VERTICAL_SPACING_MULTIPLIER`| `1.6`           | Y offset = text_height × this below room ID     |
| `MIN_POLYGON_AREA`          | `1.0`            | Ignore polygons smaller than this                |
| `ENABLE_NEAREST_FALLBACK`   | `True`           | Use nearest polygon when none contains text      |
| `MAX_NEAREST_DISTANCE`      | `500.0`          | Max centroid distance for nearest fallback        |
| `XDATA_APP_NAME`            | `"ROOM_INFO_AI"` | Registered XData application name                |
| `SCAN_PROGRESS_INTERVAL`    | `2000`           | Log scan progress every N entities               |

---

### `utils.py`

Shared utility functions used across modules.

**Column normalization:**
- `normalize_col(name)` — lowercase, strip, replace `[-_.]` with spaces, remove special chars
- `find_column(columns, target)` — find a column by normalised name
- `build_col_map(columns)` — build normalised → original mapping

**Building identifier:**
- `extract_building_id(dwg_path)` — first 4 chars of filename, uppercased
- `detect_building_column(columns)` — scan columns for known building column names
- `filter_dataframe_by_building(df, col, id)` — filter rows by building ID

**Room identifier heuristics:**
- `is_room_identifier(text)` — returns True if text looks like a room ID
- `normalize_room_id(value)` — strip + lowercase for matching

**Geometry primitives (2D):**
- `point_in_polygon(px, py, vertices)` — ray-casting containment test
- `polygon_area(vertices)` — shoelace formula
- `polygon_centroid(vertices)` — signed-area weighted centroid
- `polygon_bbox(vertices)` — axis-aligned bounding box
- `bbox_contains_point(bbox, px, py)` — fast bbox pre-filter
- `distance_point_to_point(x1, y1, x2, y2)` — Euclidean distance
- `is_valid_room_polygon(vertices, closed)` — closed + positive area check

**Text formatting:**
- `format_mtext_content(fields)` — dict → MTEXT string with `\P` line breaks
- `build_output_path(path)` — append `_updated` before extension

---

### `spreadsheet_loader.py`

Reads spreadsheets with configurable header rows and cleans the data.

**Public functions:**
- `load_spreadsheet(path, excel_header, csv_header)` — returns a cleaned `pd.DataFrame`
- `get_columns(df)` — list of column names
- `find_room_id_column_suggestion(columns)` — auto-detect room ID column

**Cleaning steps:**
1. Drop unnamed/empty columns
2. Strip whitespace from column names
3. Strip whitespace from string cell values
4. Drop fully empty rows

**Supported formats:**
- `.csv` — uses `pd.read_csv` with `header=CSV_HEADER_ROW`
- `.xls` / `.xlsx` — uses `pd.read_excel` with `header=EXCEL_HEADER_ROW`
- Default Excel header = row index 2 (the 3rd row), because enterprise
  spreadsheets often have title/metadata in rows 1–2

---

### `autocad_scanner.py`

Connects to AutoCAD via COM and scans ModelSpace in a **single pass**.

**Dataclasses returned (pure Python, no COM references):**

```
RoomText
  ├── handle          (str)  — entity handle
  ├── entity_type     (str)  — "AcDbText" or "AcDbMText"
  ├── text            (str)  — raw text string
  ├── normalized_text (str)  — lowercased/stripped
  ├── position        (tuple) — (x, y, z) insertion point
  ├── layer           (str)
  ├── text_height     (float)
  └── text_style      (str)

RoomPolygon
  ├── handle          (str)
  ├── entity_type     (str)  — "AcDbPolyline" or "AcDb2dPolyline"
  ├── layer           (str)
  ├── closed          (bool)
  ├── vertices        (list[tuple[float, float]])
  ├── area            (float)
  ├── centroid        (tuple[float, float])
  └── bbox            (tuple[float, float, float, float])

ScanResult
  ├── room_texts                  (list[RoomText])
  ├── polygons                    (list[RoomPolygon])
  ├── total_entities              (int)
  └── existing_annotation_room_ids (set[str])  — for dedup
```

**Scan logic (single pass through ModelSpace):**

```
for each entity in ModelSpace:
    if entity is TEXT or MTEXT:
        if on OUTPUT_LAYER and is MTEXT → record as existing annotation (dedup)
        else if passes is_room_identifier() → cache as RoomText
    elif entity is closed LWPOLYLINE or 2dPolyline:
        if is_valid_room_polygon() → cache as RoomPolygon
    else:
        skip
```

**Connection helpers:**
- `_get_acad_instance()` — `win32com.client.Dispatch("AutoCAD.Application")`
- `_open_document(acad, path)` — opens DWG or finds it already open
- `_get_model_space(doc)` — retries up to 3 times with 1-second delay for slow loads

---

### `polygon_matcher.py`

Two-phase logic: spatial association then spreadsheet matching.

**Phase A — Text→Polygon Association:**

For each `RoomText`, find the best matching `RoomPolygon`:

```
Step 1:  Bounding-box pre-filter (fast O(1) check)
         → skip polygons whose bbox doesn't contain the text point

Step 2:  Full ray-casting point-in-polygon test
         → find all polygons that actually contain the point

Step 3:  If multiple contain it → pick the SMALLEST by area
         (the tightest room boundary, not a floor outline)

Step 4:  If none contain it AND ENABLE_NEAREST_FALLBACK is True:
         → pick the nearest polygon by centroid distance
         → only if distance ≤ MAX_NEAREST_DISTANCE
```

Each association produces a `TextPolygonAssociation`:
```
TextPolygonAssociation
  ├── room_id          (str)
  ├── text_handle      (str)
  ├── polygon_handle   (str)   — "" if unassociated
  ├── match_method     (str)   — "contains" | "nearest" | ""
  ├── polygon_area     (float)
  ├── polygon_centroid (tuple)
  └── confidence       (float) — 1.0 for contains, decays with distance for nearest
```

**Phase B — Room Matching (drawing ↔ spreadsheet):**

```
1. Build normalised lookup from spreadsheet: { norm_room_id → (raw_value, row) }
2. For each unique room text in drawing:
   a. Normalise the room ID
   b. Look up in spreadsheet
   c. If found → extract selected column values → mark as matched
   d. If not found → add to unmatched list
3. Return MatchSummary with counts + result list
```

`MatchSummary` dataclass:
```
MatchSummary
  ├── total_texts            (int)
  ├── total_polygons         (int)
  ├── texts_with_polygon     (int)
  ├── texts_without_polygon  (int)
  ├── total_sheet_rows       (int)
  ├── matched_count          (int)
  ├── unmatched_drawing      (list[str])
  ├── unmatched_sheet        (list[str])
  ├── associations           (list[TextPolygonAssociation])
  └── results                (list[RoomMatch])
```

---

### `annotation_writer.py`

Writes annotations back into AutoCAD with polygon linkage.

**Workflow:**

```
1. Re-acquire the already-open document via COM
2. Create/verify the ROOM_INFO_AI layer (green)
3. Register the ROOM_INFO_AI XData application name
4. For each matched room:
   a. Check dedup — skip if annotation already exists for this room
   b. Compute insertion point:
      - Same X as room identifier text
      - Y = room_text_Y - (text_height × VERTICAL_SPACING_MULTIPLIER)
   c. Insert MTEXT:
      - Content: formatted field labels and values (e.g. "Department: Admin")
      - Height: same as source room identifier text
      - Width: text_height × MTEXT_WIDTH_FACTOR
      - Layer: ROOM_INFO_AI
   d. Attach XData to the MTEXT entity (see XData section)
5. SaveAs → <original>_updated.dwg
```

---

### `metadata_utils.py`

Handles AutoCAD XData (Extended Data) for annotation↔polygon linkage.

**`AnnotationMetadata` dataclass:**
```
AnnotationMetadata
  ├── room_id          (str)  — e.g. "101"
  ├── polygon_handle   (str)  — AutoCAD entity handle of linked polygon
  ├── building_id      (str)  — e.g. "ENGR"
  ├── text_handle      (str)  — handle of source room identifier text
  ├── match_method     (str)  — "contains" or "nearest"
  └── annotation_type  (str)  — "room_info"
```

**Functions:**
- `register_xdata_app(doc)` — registers the app name in the drawing
- `write_xdata(entity, meta)` — attaches metadata as XData type codes
- `read_xdata(entity)` — reads XData back into `AnnotationMetadata`
- `has_app_xdata(entity)` — quick check for presence

**XData type codes used:**
```
1001  Application name  "ROOM_INFO_AI"
1000  String            room_id
1000  String            polygon_handle
1000  String            building_id
1000  String            text_handle
1000  String            match_method
1000  String            annotation_type
```

---

### `ui.py`

Tkinter/ttk GUI with dark theme.

**Layout sections:**
1. **Header** — title and subtitle
2. **Step 1 — Select Files** — spreadsheet + DWG file pickers, building ID display
3. **Step 2 — Configure Columns** — Room Identifier dropdown, Building Column
   dropdown, field checklist with Select All / Deselect All
4. **Run Section** — Run Annotation button, progress bar, status label
5. **Log / Results** — scrollable text area with colour-coded tags (INFO, SUCCESS,
   WARN, ERROR, HEADER), Clear Log button

**Threading:**
- The annotation pipeline runs in a daemon thread to keep the GUI responsive
- `pythoncom.CoInitialize()` / `CoUninitialize()` called in the worker thread
  (required for COM in non-main threads)
- All GUI updates use `root.after(0, ...)` for thread safety

---

### `main.py`

Entry point. Creates the Tk root window, enables Windows High-DPI awareness,
creates `AppUI`, centres the window on screen, and starts `mainloop()`.

---

## Data Flow & Pipeline

```
┌─────────────────────────────────────────────────────┐
│                    USER INPUT                        │
│  Spreadsheet (CSV/XLS/XLSX)  +  AutoCAD DWG file    │
└──────────────┬──────────────────────┬────────────────┘
               │                      │
               ▼                      ▼
     ┌─────────────────┐    ┌──────────────────┐
     │ spreadsheet_     │    │ extract_building_ │
     │ loader.py        │    │ id() from filename│
     │ → pd.DataFrame   │    │ → "0132"          │
     └────────┬────────┘    └────────┬──────────┘
              │                      │
              ▼                      ▼
     ┌──────────────────────────────────────┐
     │ filter_dataframe_by_building()       │
     │ → filtered DataFrame (one building)  │
     └──────────────────┬───────────────────┘
                        │
                        ▼
     ┌──────────────────────────────────────┐
     │ autocad_scanner.scan_drawing()       │
     │ Single-pass ModelSpace scan          │
     │ → ScanResult:                        │
     │     room_texts[]                     │
     │     polygons[]                       │
     │     existing_annotation_room_ids{}   │
     └──────────────────┬───────────────────┘
                        │
                        ▼
     ┌──────────────────────────────────────┐
     │ polygon_matcher.associate_texts_     │
     │ with_polygons()                      │
     │ → TextPolygonAssociation[]           │
     │   (room_id ↔ polygon_handle)         │
     └──────────────────┬───────────────────┘
                        │
                        ▼
     ┌──────────────────────────────────────┐
     │ polygon_matcher.match_rooms()        │
     │ Drawing rooms ↔ Spreadsheet rows     │
     │ → MatchSummary (results, counts)     │
     └──────────────────┬───────────────────┘
                        │
                        ▼
     ┌──────────────────────────────────────┐
     │ annotation_writer.write_annotations()│
     │ Insert MTEXT + attach XData          │
     │ → (output_path, inserted_count)      │
     └──────────────────┬───────────────────┘
                        │
                        ▼
     ┌──────────────────────────────────────┐
     │ SaveAs → <name>_updated.dwg          │
     │ Original file is never modified      │
     └─────────────────────────────────────┘
```

---

## Spreadsheet Handling

### Header Row Convention

Enterprise spreadsheets often have title/metadata in the first rows.
The application defaults to:

- **Excel:** Header on row 3 (0-indexed = 2)
- **CSV:** Header on row 1 (0-indexed = 0)

Both are configurable in `config.py`.

### Column Name Normalization

Column names are normalised for robust matching regardless of formatting:

| Original Column       | Normalised Form      |
|----------------------|---------------------|
| `Room Identifier`    | `room identifier`   |
| `room_identifier`    | `room identifier`   |
| `ROOM-IDENTIFIER`    | `room identifier`   |
| `Room Identifier#`   | `room identifier`   |
| `Building ID`        | `building id`       |
| `BLDG_ID`            | `bldg id`           |

Normalisation steps: strip → lowercase → replace `[-_.]` with spaces →
collapse whitespace → remove non-alphanumeric.

### Auto-Detection

The app auto-detects:
- **Room Identifier column** — matches against known names: `room`, `room id`,
  `room identifier`, `roomid`, `rm`, `space id`, etc.
- **Building column** — matches against: `building`, `building id`, `bldg`,
  `bldg id`, etc.

Both can be overridden via the dropdown selectors in the GUI.

---

## Building Identifier Validation

The first 4 characters of the DWG filename are the building identifier.

```
0132_SATELLITE DISH LAB ANNEX_01.dwg  →  building_id = "0132"
ENGR_floor1.dwg                        →  building_id = "ENGR"
```

**Before any room matching occurs:**
1. Extract building ID from the DWG filename
2. Detect the building column in the spreadsheet
3. Filter spreadsheet to only rows where `building_col == building_id`
4. If no rows match → cancel with clear error message

This prevents accidental cross-building annotation errors when a spreadsheet
contains data for multiple buildings.

---

## AutoCAD Scanning

### Connection

The application connects to AutoCAD using COM:
```python
acad = win32com.client.Dispatch("AutoCAD.Application")
```

It will attach to a running instance or launch AutoCAD if needed.

### Document Opening

1. Check if the DWG is already open → reuse it
2. If not, open via `acad.Documents.Open(path)`
3. Retry ModelSpace access up to 3 times (1-second delay) for slow-loading files

### Single-Pass Entity Scan

The scanner iterates through ModelSpace **once**, categorising each entity:

| Entity Type | Action |
|---|---|
| `AcDbText` or `AcDbMText` | Check if room ID → cache `RoomText` |
| `AcDbMText` on `ROOM_INFO_AI` layer | Record as existing annotation (dedup) |
| `AcDbPolyline` (closed) | Validate → cache `RoomPolygon` |
| `AcDb2dPolyline` (closed) | Validate → cache `RoomPolygon` |
| Everything else | Skip immediately |

For each **text entity**, the following properties are read in one batch:
- `TextString`, `InsertionPoint`, `Height`, `StyleName`, `Handle`, `Layer`

For each **polygon entity**:
- `Coordinates` (flat array → converted to vertex tuples)
- `Closed`, `Handle`, `Layer`
- Derived: `area`, `centroid`, `bbox` (computed in Python, not via COM)

Progress is logged every 2000 entities (configurable).

---

## Text-to-Polygon Association

This is the spatial linking step that determines which polygon each room
identifier belongs to.

### Algorithm

```
For each RoomText (px, py = insertion point):

  1. BOUNDING BOX PRE-FILTER (fast)
     For each polygon, check: bbox contains (px, py)?
     Skip if not.

  2. FULL POINT-IN-POLYGON TEST (ray-casting)
     Among bbox-passing polygons, test: point inside polygon?
     Collect all containing polygons.

  3. SMALLEST AREA SELECTION
     If multiple polygons contain the point:
       → Choose the one with the smallest area.
     Rationale: The tightest boundary is the room polygon,
     not a larger floor outline or building outline.

  4. NEAREST FALLBACK (optional)
     If no polygon contains the point AND fallback is enabled:
       → Find the polygon with the nearest centroid.
       → Accept only if distance ≤ MAX_NEAREST_DISTANCE.
       → Confidence decays linearly with distance.
```

### Confidence Scoring

| Method     | Confidence |
|------------|-----------|
| Contains   | 1.0       |
| Nearest    | `1.0 - (distance / MAX_NEAREST_DISTANCE)` |
| Unmatched  | 0.0       |

---

## Room Matching

After text→polygon association, rooms are matched against the spreadsheet:

1. Build a normalised lookup from the filtered spreadsheet:
   `{ "101" → (raw_value, row_data) }`
2. For each unique room text in the drawing:
   - Normalise: strip whitespace, lowercase
   - Look up in the spreadsheet
   - If found → extract the user-selected column values
   - If not found → add to unmatched list
3. Deduplicate: if a room ID appears multiple times in the drawing, only
   the first occurrence is used for annotation placement.

---

## Annotation Writing & Polygon Linkage

### MTEXT Placement

Each annotation is positioned **directly below** the room identifier text:

```
┌─────────────────────────────┐
│       Room Polygon          │
│                             │
│   101                       │  ← Room identifier (existing TEXT)
│   Department: Engineering   │  ← Annotation (new MTEXT)
│   Occupied By: John Smith   │
│   Room Area: 230 sqft       │
│                             │
└─────────────────────────────┘
```

**Placement rules:**
- **X position:** Same as the room identifier text
- **Y position:** `room_text_Y - (text_height × 1.6)` (configurable)
- **Text height:** Inherited from the room identifier text entity
- **MTEXT width:** `text_height × 25.0` (configurable)
- **Layer:** `ROOM_INFO_AI`
- **Content format:** `"Label: Value\PLabel: Value\P..."` (MTEXT `\P` = newline)

### XData Attachment

After inserting the MTEXT, XData is attached containing:
- Room ID
- Polygon handle (the entity handle of the linked polygon)
- Building ID
- Text handle (the entity handle of the source room ID text)
- Match method ("contains" or "nearest")
- Annotation type ("room_info")

This makes every annotation **queryable** — you can later find an annotation
and programmatically retrieve its linked polygon.

### Save Behaviour

The updated drawing is saved as `<original_name>_updated.dwg` in the same
directory. The original file is **never** modified.

---

## XData Metadata System

AutoCAD Extended Data (XData) is a standard mechanism for attaching custom
metadata to any entity. It persists when the DWG is saved and reopened.

### How It Works

1. **Register application name:** `doc.RegisteredApplications.Add("ROOM_INFO_AI")`
2. **Write XData:** `entity.SetXData(type_codes, values)`
3. **Read XData:** `entity.GetXData("ROOM_INFO_AI", types_out, values_out)`

### XData Structure Per Annotation

```
Index  Type Code  Content
0      1001       "ROOM_INFO_AI"       ← application name (required first)
1      1000       "101"                ← room_id
2      1000       "4A2B"               ← polygon_handle
3      1000       "0132"               ← building_id
4      1000       "3F1C"               ← text_handle
5      1000       "contains"           ← match_method
6      1000       "room_info"          ← annotation_type
```

---

## Deduplication

Running the tool multiple times on the same drawing will **not** create
duplicate annotations.

### How Dedup Works

1. During the scan phase, the scanner identifies MTEXT entities on the
   `ROOM_INFO_AI` layer.
2. For each, it reads the XData to extract the `room_id`.
3. These room IDs are collected in `existing_annotation_room_ids`.
4. During the write phase, any room that already has an annotation is skipped.
5. The log reports how many rooms were skipped due to existing annotations.

---

## Geometry Engine

All geometry computations are implemented in pure Python in `utils.py`.
No external geometry libraries are required.

### Point-in-Polygon (Ray Casting)

Cast a horizontal ray from the test point to infinity. Count how many polygon
edges the ray crosses. Odd count = inside, even count = outside.

```python
def point_in_polygon(px, py, vertices):
    n = len(vertices)
    inside = False
    j = n - 1
    for i in range(n):
        xi, yi = vertices[i]
        xj, yj = vertices[j]
        if ((yi > py) != (yj > py)) and
           (px < (xj - xi) * (py - yi) / (yj - yi) + xi):
            inside = not inside
        j = i
    return inside
```

### Polygon Area (Shoelace Formula)

```
Area = |Σ (x_j + x_i)(y_j - y_i)| / 2
```

### Polygon Centroid

Weighted by the signed area of each triangular strip:
```
C_x = Σ (x_i + x_j) × cross / (6 × signed_area)
C_y = Σ (y_i + y_j) × cross / (6 × signed_area)
```

### Bounding Box

Simple min/max of all vertex X and Y coordinates. Used as a fast pre-filter
before the full point-in-polygon test.

---

## Configuration Reference

All values are in `config.py`. Change them there; no other files need editing.

### Spreadsheet Settings

| Constant           | Default | Description                                    |
|--------------------|---------|------------------------------------------------|
| `EXCEL_HEADER_ROW` | `2`     | Excel header row (0-indexed). 2 = 3rd row      |
| `CSV_HEADER_ROW`   | `0`     | CSV header row (0-indexed). 0 = 1st row        |

### Building ID

| Constant              | Default | Description                          |
|-----------------------|---------|--------------------------------------|
| `BUILDING_ID_LENGTH`  | `4`     | Characters from DWG filename start   |

### Annotation Output

| Constant                       | Default          | Description                          |
|--------------------------------|------------------|--------------------------------------|
| `OUTPUT_LAYER`                 | `"ROOM_INFO_AI"` | Layer for all inserted annotations   |
| `ANNOTATION_COLOR`             | `3`              | AutoCAD colour index (green)         |
| `DEFAULT_TEXT_HEIGHT`          | `10.0`           | Fallback height if entity has none   |
| `MTEXT_WIDTH_FACTOR`          | `25.0`           | MTEXT width = height × factor        |
| `VERTICAL_SPACING_MULTIPLIER` | `1.6`            | Y offset below room ID text          |

### Polygon Detection

| Constant                   | Default | Description                               |
|----------------------------|---------|-------------------------------------------|
| `MIN_POLYGON_AREA`        | `1.0`   | Ignore polygons smaller than this         |
| `ENABLE_NEAREST_FALLBACK` | `True`  | Use nearest centroid when no containment  |
| `MAX_NEAREST_DISTANCE`    | `500.0` | Max distance for nearest fallback         |

### XData / Metadata

| Constant         | Default          | Description                 |
|------------------|------------------|-----------------------------|
| `XDATA_APP_NAME` | `"ROOM_INFO_AI"` | Registered application name |

### Performance

| Constant                  | Default | Description                       |
|---------------------------|---------|-----------------------------------|
| `SCAN_PROGRESS_INTERVAL`  | `2000`  | Log progress every N entities     |

---

## GUI Overview

The GUI is built with Tkinter + ttk and uses a dark colour scheme.

### Sections

1. **Header** — Application title
2. **Step 1 — Select Files**
   - Spreadsheet file picker (CSV/XLS/XLSX)
   - DWG file picker
   - Detected Building ID display
3. **Step 2 — Configure Columns**
   - Room Identifier column dropdown (auto-detected)
   - Building Identifier column dropdown (auto-detected)
   - Scrollable checklist of columns to include in annotations
   - Select All / Deselect All buttons
4. **Run Section**
   - Run Annotation button
   - Indeterminate progress bar
   - Status label
5. **Log / Results**
   - Colour-coded scrollable text log
   - Clear Log button

### Status Messages During Run

```
Filtering rows for building 0132...
Scanning AutoCAD drawing...
  Scanning 14532 model-space entities...
  ...scanned 2000/14532
  ...scanned 4000/14532
  Room identifiers found : 47
  Polygon candidates     : 312
Associating texts with room polygons...
  Contained: 41  |  Nearest: 4  |  Unmatched: 2
Matching rooms to spreadsheet data...
Writing annotations to drawing...
  Saving updated drawing: 0132_LAB_updated.dwg
  Annotations inserted: 38
Done — 38 annotations inserted.
```

---

## Error Handling

The application handles errors at every stage with clear messages:

| Scenario                                 | Behaviour                                        |
|------------------------------------------|--------------------------------------------------|
| No spreadsheet selected                  | Warning dialog before run                        |
| No DWG selected                          | Warning dialog before run                        |
| Spreadsheet read failure                 | Error dialog with detail                         |
| Unsupported file type                    | Error: "Supported: .csv, .xls, .xlsx"            |
| Room identifier column not selected      | Warning dialog                                   |
| Building column not selected             | Warning dialog                                   |
| No rows match building ID                | Error + cancel: "No rows match building XXXX"    |
| AutoCAD not running / not installed      | Error: "Could not connect to AutoCAD"            |
| DWG file not found                       | Error with full path                             |
| DWG fails to open                        | Error with possible causes listed                |
| ModelSpace not accessible                | Retry 3×, then error                             |
| No room identifiers found in drawing     | Warning + stop                                   |
| No matched rooms                         | Warning + stop                                   |
| Annotation write failure (single room)   | Warning logged, continues with other rooms       |
| SaveAs failure                           | Falls back to Save, logs warning                 |
| Unexpected error                         | Full exception in error dialog + log             |

---

## Performance Optimisations

1. **Single-pass scan** — ModelSpace is iterated exactly once. Text entities and
   polygon entities are categorised and cached simultaneously.

2. **No retained COM references** — All entity data is extracted into Python
   dataclasses immediately. The matcher and writer never re-query the COM layer.

3. **Bounding-box pre-filter** — Before running the O(n) ray-casting algorithm
   on a polygon's vertices, a simple O(1) bbox check eliminates most candidates.

4. **Worker thread** — The annotation pipeline runs in a background thread so
   the GUI remains responsive throughout.

5. **COM initialisation** — `pythoncom.CoInitialize()` is called once at the
   start of the worker thread and `CoUninitialize()` at the end.

6. **Batch writes** — All annotations are computed first, then written in
   sequence. No interleaved read-write cycles.

7. **Early entity-type skip** — During scanning, entities that are not
   TEXT/MTEXT/LWPOLYLINE are skipped immediately with no property reads.

---

## Querying Annotations Later

After the tool has run, you can programmatically query annotation→polygon
relationships from any Python script:

```python
import win32com.client
from metadata_utils import read_xdata

# Connect to AutoCAD and get the document
acad = win32com.client.Dispatch("AutoCAD.Application")
doc = acad.ActiveDocument
model_space = doc.ModelSpace

# Iterate through entities on the annotation layer
for i in range(model_space.Count):
    entity = model_space.Item(i)
    if entity.Layer == "ROOM_INFO_AI" and entity.EntityName == "AcDbMText":
        meta = read_xdata(entity)
        if meta:
            print(f"Room: {meta.room_id}")
            print(f"Building: {meta.building_id}")
            print(f"Polygon handle: {meta.polygon_handle}")
            print(f"Match method: {meta.match_method}")

            # Retrieve the actual polygon entity by handle
            polygon = doc.HandleToObject(meta.polygon_handle)
            print(f"Polygon area: {polygon.Area}")
            print(f"Polygon layer: {polygon.Layer}")
            print()
```

---

## Known Limitations

1. **Block attributes** — Room identifiers inside block references (attribute
   values) are not scanned. Only standalone TEXT/MTEXT is detected.

2. **Model Space only** — Paper Space / Layout viewports are not scanned.

3. **Polygon types** — Only closed LWPOLYLINE (`AcDbPolyline`) and
   `AcDb2dPolyline` are detected. Other boundary representations (HATCH,
   REGION, 3DSOLID) are not included.

4. **XData size limit** — AutoCAD limits XData to 16 KB per entity. The
   metadata stored by this tool is well under that limit.

5. **Single-sheet Excel** — Only the first sheet is read. Multi-sheet
   workbooks require the relevant data on the first sheet.

6. **COM requirement** — The application only runs on Windows with AutoCAD
   installed. There is no cross-platform or headless mode.

7. **First occurrence** — If a room ID appears multiple times in the drawing
   (e.g., in a legend), only the first is annotated.
