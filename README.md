# AutoCAD Room Annotation Tool

A Python desktop application that reads room data from a spreadsheet (CSV/Excel),
scans an AutoCAD DWG drawing for room identifiers and polygons, matches them,
and copies each matched room's boundary onto its own **ArcGIS-ready layer** named
`[Building]-[Floor]-[Room]` (e.g. `0132-01-101`) — without overwriting the original file.

---

## Table of Contents

1. [Quick Start (5 Minutes)](#quick-start-5-minutes)
2. [Requirements](#requirements)
3. [Detailed Setup Instructions](#detailed-setup-instructions)
4. [Running the Application](#running-the-application)
5. [Step-by-Step Usage Guide](#step-by-step-usage-guide)
6. [How It Works](#how-it-works)
7. [Input File Requirements](#input-file-requirements)
8. [Output Files](#output-files)
9. [ArcGIS Compatibility](#arcgis-compatibility)
10. [Configuration](#configuration)
11. [Troubleshooting & Error Handling](#troubleshooting--error-handling)
12. [Project Structure](#project-structure)
13. [Assumptions and Limitations](#assumptions-and-limitations)

---

## Quick Start (5 Minutes)

```
1. Unzip the folder to any location (e.g. C:\Tools\AutoCAD-Annotator\)
2. Double-click  setup.bat        (one-time setup — installs dependencies)
3. Open AutoCAD and load your DWG file
4. Double-click  run.bat           (launches the application)
5. Select your spreadsheet and DWG file, check the Room / Building / Floor columns, click "Run Annotation"
6. Choose where to save the result (suggested name: <original_name>_annotated.dwg)
```

That's it. See below for detailed instructions if anything goes wrong.

---

## Requirements

### Required Software

| Software | Version | Why It's Needed |
|---|---|---|
| **Windows** | 10 or 11 | AutoCAD COM automation only works on Windows |
| **AutoCAD** | 2018 or later | Must be installed, licensed, and **running** before you start |
| **Python** | 3.10 or later | The application is written in Python |

### How to Check if Python is Installed

Open **Command Prompt** (press `Win+R`, type `cmd`, press Enter) and type:

```
python --version
```

You should see something like `Python 3.12.4`. If you get an error:

1. Download Python from https://www.python.org/downloads/
2. **IMPORTANT:** During installation, check the box **"Add Python to PATH"**
3. Restart your computer after installation

### How to Check AutoCAD

- AutoCAD must be **installed and licensed** (not a trial that has expired).
- AutoCAD must be **open and running** before you start the annotation tool.
- Any version from AutoCAD 2018 onward should work.

---

## Detailed Setup Instructions

### Step 1: Unzip the Folder

Unzip `AutoCAD_Room_Annotator.zip` to a folder on your computer. For example:

```
C:\Tools\AutoCAD-Annotator\
```

You should see these files inside:

```
AutoCAD-Annotator/
  setup.bat              <-- Run this first (one time only)
  run.bat                <-- Run this to start the app
  main.py
  config.py
  ui.py
  requirements.txt
  ... (other .py files)
  README.md              <-- This file
```

### Step 2: Run setup.bat (One Time Only)

1. **Double-click `setup.bat`**
2. A terminal window will open and show progress:
   - `[1/4] Checking Python installation...`
   - `[2/4] Creating virtual environment...`
   - `[3/4] Installing dependencies...`
   - `[4/4] Verifying installation...`
3. Wait for the message: **"Setup Complete!"**
4. Press any key to close the window.

**If setup fails**, see the [Troubleshooting](#troubleshooting--error-handling) section below.

> **Note:** You only need to run `setup.bat` once. After that, just use `run.bat`.

### Step 3: Verify Setup Worked

After setup, you should have a new `.venv` folder inside the project directory.
This contains all the Python dependencies. Do not delete this folder.

---

## Running the Application

### Every Time You Want to Use It:

1. **Open AutoCAD** (needed for DWG files; DXF files work without it).
2. **Double-click `run.bat`**
3. The **Room Layer Tool** window appears (light theme; switch with the ☾ Dark / ☀ Light
   button, top right — your choice is remembered).

> The previous Tkinter window is still available: `.venv\Scripts\python.exe main.py --tk`

### If run.bat Shows a Warning About AutoCAD

The script checks if AutoCAD is running. If it shows:

```
WARNING: AutoCAD does not appear to be running.
```

Open AutoCAD first, then press any key in the terminal to continue.

---

## Step-by-Step Usage Guide

### 1. Files

- **Spreadsheet → Browse…** — CSV, XLS or XLSX with a room-number column. Large Excel files
  take a while the first time (a 36,000-row workbook ≈ 15–25 s); the window stays usable and
  shows `✓ 36,367 rows` when done. The same unchanged file then loads instantly.
- **Drawing (DWG / DXF) → Browse…** — the floor plan.
- **Building ID** — filled in from the first 4 characters of the drawing's file name
  (`0132_SATELLITE DISH LAB ANNEX_01.dwg` → `0132`). **Edit it** if the file name is different.

### 2. Columns

The **Room**, **Building** and **Floor** columns are detected automatically (e.g. "Room
Identifier", "Building Identifier", "Floor Code"); change them in the drop-downs if needed.
They must be three different columns. The green preview shows a real layer name for the
building you are processing, e.g. `e.g.  0036-1-001`.

### 3. Create Room Layers

**Create Room Layers** is enabled once everything above is set (hover over it to see what is
missing). Click it and choose **where to save** the result (suggested name
`<original_name>_annotated.dwg`, starting in your Documents folder — the original drawing
cannot be chosen).

The progress bar and status line follow each step:
1. Filter the spreadsheet to the Building ID (a wrong ID stops here, before AutoCAD is used)
2. Convert DWG to DXF (AutoCAD, on a temporary copy)
3. Scan the drawing for room labels and room outlines
4. Link each label to its room outline
5. Match rooms to the spreadsheet
6. Copy each matched room's outline onto its `Building-Floor-Room` layer and write the key
   as a text label inside the room
7. Convert back to DWG and save it where you chose

**Cancel** stops the run after the current step; nothing is saved.

### 4. Results

The **Results** tab lists every room, with a filter (**Show**) and a summary line:

| Status | Meaning |
|---|---|
| ✓ Created | Layer and key label written |
| ⚠ Check | Created, but worth a look — e.g. the key label does not fit inside a very small room, the label was linked to the nearest outline, or two labels share one outline |
| – Skipped / ✗ Failed | No layer written; the Note says why (no outline found, empty Floor value, already done…) |
| ○ Not in spreadsheet | A room label in the drawing has no spreadsheet row (e.g. `ELECT1` vs `ELEC1`) |
| ○ Not in drawing | A spreadsheet row for this building has no label in this drawing (often another floor) |

The **Log** tab has the full step-by-step log.

### 6. Check the Output

The annotated DWG is saved where you chose in step 5; the full path is shown
in the log and the completion message. The original file is **never modified**.

---

## How It Works

### Pipeline Overview

```
DWG File (input)
  |
  v
[AutoCAD COM: SaveAs DXF]     -- AutoCAD converts to DXF format
  |
  v
[ezdxf: Scan DXF]             -- Python reads TEXT, MTEXT, POLYLINE entities
  |
  v
[Match rooms to polygons]     -- Point-in-polygon test links text to boundaries
  |
  v
[Match rooms to spreadsheet]  -- Room IDs matched case-insensitively
  |
  v
[ezdxf: Room layers]         -- Room polygon copies on Building-Floor-Room layers
  |
  v
[AutoCAD COM: SaveAs DWG]     -- AutoCAD converts back to DWG format
  |
  v
DWG File (output: *_annotated.dwg)
```

### Text-to-Polygon Association

For each room identifier found in the drawing:

1. **Bounding box pre-filter** — skip polygons that clearly don't contain the text
2. **Point-in-polygon test** — ray-casting algorithm on remaining candidates
3. **Smallest area wins** — if multiple polygons contain the point, pick the tightest room boundary
4. **Nearest fallback** — if no polygon contains the text, use nearest centroid (configurable)

### Room Identifier Detection

For multi-line labels (e.g. the room number with the area underneath, or a room name
above the number), the first line that looks like a room identifier is used.

Text entities are flagged as room identifiers if:
- Not empty, length ≤ 20 characters, ≤ 3 words
- Contains at least 1 digit
- Matches pattern: `101`, `102A`, `B201`, `LAB-101`
- Does NOT match: `"This is a title"`, `"Exit"`, `"Men's Restroom"`

### Building ID Validation

| DWG Filename | Extracted Building ID |
|---|---|
| `0132_SATELLITE DISH LAB.dwg` | `0132` |
| `ENGR_floor1.dwg` | `ENGR` |
| `SCI2_floor2.dwg` | `SCI2` |

The spreadsheet is filtered to only rows matching this building ID before matching occurs.

---

## Input File Requirements

### Spreadsheet

- **Formats:** CSV, XLS, or XLSX
- **Required columns:** At minimum, a room identifier column and a building identifier column
- **Header row:**
  - Excel files: default is the **3rd row** (index 2). Change in `config.py` if needed.
  - CSV files: default is the **1st row** (index 0).
- Column names are normalized automatically (spaces, hyphens, underscores, mixed case all handled)

### DWG Drawing

- Room identifiers must be **standalone TEXT or MTEXT entities** (not inside blocks)
- Room boundaries must be **closed POLYLINE or LWPOLYLINE entities**
- Only **Model Space** is scanned (Paper Space is ignored)
- AutoCAD must be running and able to open the file

---

## Output Files

| File | Description |
|---|---|
| `<name>_annotated.dwg` (name and folder are your choice) | The original drawing plus one `Building-Floor-Room` layer per matched room, saved as a native AutoCAD 2018 DWG. |

The original DWG is **never modified**, and nothing is written next to it:

- Conversion works on a **copy** of the drawing in a private temporary folder,
  which is deleted when the run ends.
- If the drawing is **open in AutoCAD**, it is left untouched. If it has unsaved
  changes, the log warns you that the last **saved** version was used — save first
  if you want those changes included.
- AutoCAD's dialog settings (FILEDIA, CMDDIA, PROXYNOTICE) are switched off only
  while converting and **restored** afterwards.

**Running again is safe:** rooms that already have a room layer in the drawing
are skipped (the log reports how many).

---

## ArcGIS Compatibility

Room data is delivered through **layers**, which ArcGIS handles better than blocks when
it imports a CAD drawing. Every matched room gets its own layer:

```
<Building>-<Floor>-<Room>        e.g.  0132-01-101
```

- The three values are taken **as-is** from the matched spreadsheet row (so `01` stays
  `01`, and `1` stays `1`), which keeps the name identical to your facilities data.
- The layer holds a **copy** of the room's boundary polygon and a **text label with the
  key**, placed just under the room number so you can see which rooms were processed.
  The original polygon, room label and the drawing's own layers are not changed.
- Characters AutoCAD does not allow in layer names (`< > / \ " : ; ? * | = `` ` ``) are
  replaced with `_`.
- No blocks or attribute values are written.

### How to Use It in ArcGIS

1. **Add Data** → select the annotated `.dwg` file → choose its **Polygon** feature class.
2. Each room polygon's **Layer** field holds its key, e.g. `0132-01-101`.
3. To bring in other spreadsheet columns (department, occupant, area, ...), **join** your
   spreadsheet to the polygons on that key. Build the same key in the spreadsheet by
   combining the Building, Floor and Room columns with `-`.

### When a Room Is Skipped

The log lists every room that did not get a layer, and why:

| Log message | Meaning |
|---|---|
| no room boundary polygon found | The room label is not inside (or near) any closed polyline |
| empty Building / Floor / Room value | One of the three spreadsheet values is blank |
| a room layer already exists | The drawing was already processed for this room |

It also flags rooms worth checking: labels linked to the **nearest** polygon (label outside
any polygon) and polygons that contain **more than one** room label.

---

## Configuration

All tuneable values are in `config.py`. You can edit this file with any text editor (Notepad works).

### Spreadsheet Settings

| Constant | Default | Description |
|---|---|---|
| `EXCEL_HEADER_ROW` | `2` | 0-indexed header row for Excel (2 = 3rd row) |
| `CSV_HEADER_ROW` | `0` | 0-indexed header row for CSV (0 = 1st row) |
| `BUILDING_ID_LENGTH` | `4` | Number of characters from filename for building ID |
| `SPREADSHEET_CACHE_DIR` | `%LOCALAPPDATA%\RoomAnnotator\spreadsheet_cache` | Parsed spreadsheets are cached here; an unchanged file loads instantly the next time |

### Room Layers

| Constant | Default | Description |
|---|---|---|
| `ROOM_KEY_SEPARATOR` | `-` | Separator between Building, Floor and Room in layer names |
| `ROOM_LAYER_COLOR` | `3` | AutoCAD color index of the room layers (3 = green) |
| `ROOM_TAG_GAP_FACTOR` | `0.5` | Gap between the room label and the key label, in label heights |

### Polygon Detection

| Constant | Default | Description |
|---|---|---|
| `MIN_POLYGON_AREA` | `1.0` | Ignore polygons smaller than this |
| `ENABLE_NEAREST_FALLBACK` | `True` | Use nearest polygon when none contains text |
| `MAX_NEAREST_DISTANCE` | `500.0` | Max centroid distance for nearest fallback |

---

## Troubleshooting & Error Handling

### Setup Issues

#### "Python is not installed or not in your PATH"

- Install Python 3.10+ from https://www.python.org/downloads/
- **Check "Add Python to PATH"** during installation
- Restart your computer after installing
- Run `setup.bat` again

#### "Failed to create virtual environment"

- Make sure you have write permissions to the folder
- Try running Command Prompt as Administrator:
  ```
  cd C:\Tools\AutoCAD-Annotator
  python -m venv .venv
  ```

#### "Failed to install dependencies"

- Check your internet connection (dependencies are downloaded from the internet)
- If behind a corporate proxy, ask your IT department for pip proxy settings
- Try running manually:
  ```
  .venv\Scripts\pip.exe install -r requirements.txt
  ```

### Runtime Issues

#### "Could not connect to AutoCAD"

- **AutoCAD must be open and running** before you start the tool
- Make sure AutoCAD is fully loaded (wait for the command prompt to appear)
- If AutoCAD is open but the tool can't connect, try closing and reopening AutoCAD

#### "DWG file not found"

- Make sure the file path doesn't contain unusual characters
- Try copying the DWG to a simple path like `C:\Drawings\`

#### Application Hangs at "Converting DWG -> DXF"

This means AutoCAD has a **dialog box open** that is blocking the conversion.

**Fix:**
1. **Alt+Tab** to AutoCAD
2. Look for any popup dialog (save prompt, security warning, proxy graphics notice)
3. **Click OK / Cancel / Close** on the dialog
4. The application should resume automatically

**Prevent this in the future:**
- Close all other drawings in AutoCAD before running the tool
- Dismiss any AutoCAD startup dialogs before starting

#### "No room identifiers found in the drawing"

This means the scanner didn't detect any room number text. Possible causes:
- Room numbers are inside **block attributes** instead of standalone text (not supported yet)
- Room numbers don't match the detection pattern (must contain at least 1 digit)
- The drawing uses **Paper Space** (only Model Space is scanned)
- Room text is on a frozen or off layer

#### "No spreadsheet rows match building"

- Check that your DWG filename starts with the correct building code (first 4 characters)
- Check that your spreadsheet has a building column with matching values
- Building matching is **case-insensitive**

#### "No rooms matched"

- The room IDs in the spreadsheet don't match the text in the drawing
- Check for leading/trailing spaces in the spreadsheet
- Check for different formatting (e.g., `Room 101` in spreadsheet vs `101` in drawing)
- Matching is **case-insensitive** and **whitespace-trimmed**

#### "WARNING: ... rooms skipped" or "... rooms failed"

- See **When a Room Is Skipped** under ArcGIS Compatibility for what each message means
- The log lists the affected room numbers
- This is non-fatal — other rooms still get their layers

### Still Having Issues?

1. Check the **application log panel** at the bottom of the window — it shows detailed progress
2. Look for `WARNING` or `ERROR` messages in the log
3. Try with a simpler DWG file first to verify the setup works
4. Make sure AutoCAD is not in the middle of a command (press `Escape` in AutoCAD first)

---

## Project Structure

```
AutoCAD-Annotator/
  setup.bat                 # One-time setup script (creates venv, installs deps)
  run.bat                   # Launch script (starts the GUI application)
  main.py                   # Entry point - launches the Tkinter GUI
  config.py                 # All configurable constants (edit with Notepad)
  ui.py                     # Tkinter GUI (dark theme, log panel, progress bar)
  dwg_converter.py          # DWG <-> DXF conversion via AutoCAD COM (minimal)
  autocad_scanner.py        # Scans DXF for room texts, polygons, existing room layers
  polygon_matcher.py        # Associates room text with room polygons + spreadsheet
  annotation_writer.py      # Copies room polygons onto Building-Floor-Room layers
  metadata_utils.py         # XData linking each copy to its source polygon
  spreadsheet_loader.py     # CSV / XLS / XLSX file loading
  utils.py                  # Normalization, heuristics, geometry helpers
  requirements.txt          # Python package dependencies
  run_tests.bat             # Runs the automated tests
  tests/                    # Automated tests (unittest)
  README.md                 # This file
```

### Running the Tests

After `setup.bat`, double-click **`run_tests.bat`** (or run it from a command prompt).
It runs the offline tests, which need no AutoCAD and take a few seconds:

```
run_tests.bat
```

To also test the real AutoCAD conversion (AutoCAD must be installed; it works on
temporary test drawings only and restores AutoCAD's settings afterwards):

```
run_tests.bat acad
```

A result ending in `OK` means everything passed. "Expected failures" are tests for
known, not-yet-fixed limitations; they are reported but do not fail the run.

---

## Assumptions and Limitations

- **Windows only** — AutoCAD COM automation requires Windows.
- **AutoCAD must be installed and licensed** — the tool uses AutoCAD for DWG/DXF conversion.
- **AutoCAD must be running** — start AutoCAD before launching the tool.
- Room identifiers must be **standalone TEXT or MTEXT** entities (not block attributes).
- Room polygons must be **closed POLYLINE or LWPOLYLINE** entities.
- Only **Model Space** is scanned (Paper Space is ignored).
- The first occurrence of each room ID in the drawing is used.
- Rooms must have a **Floor** value in the spreadsheet to get a layer.
- The **first 4 characters** of the DWG filename are used as the building identifier.
- The original DWG file is **never modified** — output is always a new file, saved where you choose.

---

## License

MIT — free to use and modify.
