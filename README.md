# AutoCAD Room Annotation Tool

A production-style Python desktop application that reads room data from a
CSV or Excel spreadsheet, links it to room polygons in AutoCAD, and inserts
formatted annotations with full polygon linkage — without overwriting the
original file.

---

## Features

- **Polygon linkage** — each annotation is linked to its room polygon via XData
- **Building validation** — extracts building ID from DWG filename, filters spreadsheet
- **Single-pass scan** — TEXT/MTEXT + closed polylines collected in one ModelSpace iteration
- **Text→Polygon association** — ray-casting point-in-polygon with smallest-area selection
- **Nearest-polygon fallback** — configurable centroid-distance fallback when containment fails
- **Deduplication** — detects existing annotations via XData to avoid duplicates on re-run
- Supports **CSV**, **XLS**, and **XLSX** input files
- Robust **column name normalization** (spaces, hyphens, underscores, mixed case)
- **Auto-detects** Room Identifier and Building Identifier columns
- **Case-insensitive, trimmed** matching between spreadsheet and drawing
- Inserts formatted **MTEXT** on dedicated layer (`ROOM_INFO_AI`) in **green**
- **Saves a new file** (`originalname_updated.dwg`) — original is never modified
- Dark-themed **Tkinter GUI** with live log output and progress updates

---

## Prerequisites

| Requirement | Notes |
|---|---|
| **Windows** | AutoCAD COM automation requires Windows |
| **AutoCAD** | Any version with COM/ActiveX interface (2010+) |
| **Python 3.10+** | Uses modern type hint syntax (`X \| Y`) |

---

## Setup

### 1. Clone or download the project

```bash
git clone https://github.com/your-username/autocad-room-annotation.git
cd autocad-room-annotation
```

### 2. Create and activate a virtual environment

```bash
python -m venv .venv
.venv\Scripts\activate
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

> **Note:** If COM calls fail, run as Administrator:
> ```bash
> python -m pywin32_postinstall
> ```

---

## Running the Application

```bash
python main.py
```

---

## Workflow

| Step | Action |
|---|---|
| **1** | Select spreadsheet (CSV/XLS/XLSX) |
| **2** | Select AutoCAD DWG — building ID is extracted from first 4 characters |
| **3** | Choose **Room Identifier Column** and **Building Column** (auto-detected) |
| **4** | Check columns to insert as annotations |
| **5** | Click **Run Annotation** |
| **6** | Pipeline: filter by building → scan drawing → associate texts with polygons → match → insert |
| **7** | Updated drawing saved as `<name>_updated.dwg` |

---

## Building Identifier Validation

The first 4 characters of the DWG filename are the building identifier.

| Filename | Building ID |
|---|---|
| `ENGR_floor1.dwg` | `ENGR` |
| `SCI2_floor2.dwg` | `SCI2` |
| `0132_LAB_01.dwg` | `0132` |

The spreadsheet is filtered to only rows matching this building ID before
room matching occurs. This prevents cross-building annotation errors.

---

## Spreadsheet Header Row

For **Excel** files, the actual header row is configurable (default: **3rd row**, index 2).
For **CSV** files, the default is row 0. Both are set in `config.py`:

```python
EXCEL_HEADER_ROW = 2   # 3rd row
CSV_HEADER_ROW = 0     # 1st row
```

---

## Project Structure

```
project_root/
├── main.py                 # Entry point — launches the GUI
├── config.py               # All configurable constants
├── ui.py                   # Tkinter GUI (AppUI class)
├── spreadsheet_loader.py   # CSV / XLS / XLSX reading
├── autocad_scanner.py      # Single-pass AutoCAD ModelSpace scanner
├── polygon_matcher.py      # Geometry + text→polygon + room matching
├── annotation_writer.py    # MTEXT insertion with XData linkage
├── metadata_utils.py       # XData read/write helpers
├── utils.py                # Normalization, heuristics, geometry primitives
├── requirements.txt        # Python dependencies
└── README.md               # This file
```

---

## Text → Polygon Association

For each room identifier TEXT/MTEXT:

1. **Bounding box pre-filter** — skip polygons whose bbox doesn't contain the text point
2. **Point-in-polygon test** — ray-casting algorithm on remaining candidates
3. **Smallest area wins** — if multiple polygons contain the point, pick the tightest
4. **Nearest fallback** — if none contain the point, use nearest centroid (configurable)

---

## Annotation ↔ Polygon Linkage (XData)

Each inserted MTEXT carries AutoCAD XData under the application name `ROOM_INFO_AI`:

| XData Field | Content |
|---|---|
| Application | `ROOM_INFO_AI` |
| Room ID | e.g. `101` |
| Polygon Handle | AutoCAD entity handle of the linked polygon |
| Building ID | e.g. `ENGR` |
| Text Handle | Handle of the source room identifier text |
| Match Method | `contains` or `nearest` |
| Annotation Type | `room_info` |

### Querying the linkage later

```python
from metadata_utils import read_xdata

# Given an annotation entity from AutoCAD:
meta = read_xdata(annotation_entity)
if meta:
    print(f"Room: {meta.room_id}")
    print(f"Polygon handle: {meta.polygon_handle}")
    print(f"Building: {meta.building_id}")
    print(f"Method: {meta.match_method}")

    # Retrieve the polygon by handle:
    polygon = doc.HandleToObject(meta.polygon_handle)
    print(f"Polygon area: {polygon.Area}")
```

---

## Room Identifier Detection Heuristics

Text is flagged as a room identifier if:
- Not empty, length ≤ 20, ≤ 3 words
- Contains at least 1 digit
- Matches `^[A-Za-z0-9]([A-Za-z0-9\-]*[A-Za-z0-9])?$`

**Pass:** `101`, `102A`, `B201`, `LAB-101`
**Fail:** `"This is a title"`, `"Exit"`, `"Men's Restroom"`

All constants in `config.py`.

---

## Configuration (`config.py`)

| Constant | Default | Description |
|---|---|---|
| `EXCEL_HEADER_ROW` | `2` | 0-indexed header row for Excel |
| `CSV_HEADER_ROW` | `0` | 0-indexed header row for CSV |
| `BUILDING_ID_LENGTH` | `4` | Characters from filename for building ID |
| `OUTPUT_LAYER` | `ROOM_INFO_AI` | Annotation layer name |
| `ANNOTATION_COLOR` | `3` | AutoCAD color index (green) |
| `VERTICAL_SPACING_MULTIPLIER` | `1.6` | Line spacing below room ID |
| `MTEXT_WIDTH_FACTOR` | `25.0` | MTEXT width = height × factor |
| `MIN_POLYGON_AREA` | `1.0` | Ignore degenerate polygons |
| `ENABLE_NEAREST_FALLBACK` | `True` | Use nearest polygon when none contains text |
| `MAX_NEAREST_DISTANCE` | `500.0` | Max centroid distance for fallback |
| `SCAN_PROGRESS_INTERVAL` | `2000` | Log progress every N entities |

---

## Assumptions and Limitations

- AutoCAD must be **installed and licensed** on the machine.
- Room identifiers must be **standalone TEXT or MTEXT** (not block attributes).
- Room polygons must be **closed LWPOLYLINE or 2dPolyline** entities.
- Only **Model Space** is scanned.
- First occurrence of each room ID is used for annotation placement.
- XData persistence depends on the DWG format version supporting it.

---

## Future Improvements

1. **Block attribute scanning** — read room IDs from block attributes
2. **Preview table** — show text→polygon→spreadsheet matches before writing
3. **Export match report** — CSV of matched/unmatched rooms
4. **Fuzzy matching** — edit-distance fallback for near-identical room IDs
5. **Multi-sheet Excel** — prompt for sheet selection
6. **Paper Space support** — scan Paper Space viewports
7. **Sidecar JSON** — additional external mapping file as backup

---

## License

MIT — free to use and modify.
