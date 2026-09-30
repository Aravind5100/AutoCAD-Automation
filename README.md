# AutoCAD Room Annotation Tool

A Python desktop application that reads room data from a spreadsheet (CSV/Excel),
scans an AutoCAD DWG drawing for room identifiers and polygons, matches them,
and inserts ArcGIS-compatible attributed block annotations — without overwriting
the original file.

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
5. Select your spreadsheet, DWG file, choose columns, click "Run Annotation"
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

1. **Open AutoCAD** and load your DWG drawing.
2. **Double-click `run.bat`**
3. The application window will appear.

### If run.bat Shows a Warning About AutoCAD

The script checks if AutoCAD is running. If it shows:

```
WARNING: AutoCAD does not appear to be running.
```

Open AutoCAD first, then press any key in the terminal to continue.

---

## Step-by-Step Usage Guide

### 1. Select Your Spreadsheet

Click **"Browse"** next to the spreadsheet field and select your file:
- Supported formats: **CSV**, **XLS**, **XLSX**
- The spreadsheet must contain a column with room numbers (e.g., `1000`, `1001`, `102A`)

### 2. Select Your DWG File

Click **"Browse"** next to the drawing field and select your `.dwg` file.
- The building ID is automatically extracted from the **first 4 characters** of the filename.
- Example: `0132_SATELLITE DISH LAB ANNEX_01.dwg` → Building ID = `0132`

### 3. Choose Column Mappings

The application will auto-detect columns:
- **Room Identifier Column** — the column containing room numbers (e.g., "Room ID", "Room Number")
- **Building Column** — the column containing building codes (e.g., "Building ID", "Bldg")

### 4. Select Columns to Annotate

Check the boxes for which spreadsheet columns you want inserted into the drawing.
For example: Department, Occupied By, Square Footage, etc.

### 5. Click "Run Annotation"

You will be asked **where to save** the annotated drawing (suggested name:
`<original_name>_annotated.dwg`, starting in your Documents folder).
The original drawing cannot be chosen as the target.

The tool will then:
1. Convert DWG to DXF (temporarily, using AutoCAD)
2. Scan the drawing for room texts and room boundary polygons
3. Match room texts to polygons (point-in-polygon test)
4. Match rooms to spreadsheet data
5. Insert attributed block annotations
6. Convert back to DWG and save it to the location you chose

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
[ezdxf: Insert blocks]        -- Attributed blocks + outlines added to DXF
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
| `<name>_annotated.dwg` (name and folder are your choice) | The annotated drawing with all block inserts, saved as a native AutoCAD 2018 DWG. |

The original DWG is **never modified**, and nothing is written next to it:

- Conversion works on a **copy** of the drawing in a private temporary folder,
  which is deleted when the run ends.
- If the drawing is **open in AutoCAD**, it is left untouched. If it has unsaved
  changes, the log warns you that the last **saved** version was used — save first
  if you want those changes included.
- AutoCAD's dialog settings (FILEDIA, CMDDIA, PROXYNOTICE) are switched off only
  while converting and **restored** afterwards.

**Running again is safe:** rooms that already have an annotation in the drawing
are skipped (the log reports how many).

---

## ArcGIS Compatibility

Annotations are inserted as **AutoCAD attributed blocks** (INSERT entities with ATTRIB attributes).
When this DWG is imported into ArcGIS, room attributes appear as structured fields in the attribute table.

### How to Import in ArcGIS

1. **Add Data** → select the `_annotated.dwg` file
2. Choose the `ROOM_DATA` layer (this contains the block inserts)
3. **Open Attribute Table** → all room fields are populated automatically

### Example Attribute Table in ArcGIS

| ROOM_ID | DEPARTMENT | OCCUPIED_BY | BUILDING |
|---------|-----------|-------------|----------|
| 1000 | Engineering | John Smith | 0132 |
| 1001 | Admin | Jane Doe | 0132 |

### What Gets Created per Room

- **Block definition:** `ROOM_BLOCK_<ROOM_ID>` with one attribute per selected column
- **Block insert:** Placed on `ROOM_DATA` layer at the room text position
- **Outline:** Closed polyline on `ROOM_BLOCK_OUTLINE` layer matching room polygon shape
- **XData:** `ROOM_INFO_AI` metadata on the block insert for internal querying

### ArcGIS Naming Rules Enforced

- Block names: alphanumeric + underscore only, max 255 characters
- Attribute tags: alphanumeric + underscore only, max 30 characters
- Layer names: alphanumeric + underscore only
- Static attributed blocks only (no dynamic blocks)
- Original coordinate system preserved exactly

---

## Configuration

All tuneable values are in `config.py`. You can edit this file with any text editor (Notepad works).

### Spreadsheet Settings

| Constant | Default | Description |
|---|---|---|
| `EXCEL_HEADER_ROW` | `2` | 0-indexed header row for Excel (2 = 3rd row) |
| `CSV_HEADER_ROW` | `0` | 0-indexed header row for CSV (0 = 1st row) |
| `BUILDING_ID_LENGTH` | `4` | Number of characters from filename for building ID |

### Annotation Appearance

| Constant | Default | Description |
|---|---|---|
| `ANNOTATION_COLOR` | `3` | AutoCAD color index (3 = green) |
| `DEFAULT_TEXT_HEIGHT` | `10.0` | Fallback text height if not detected |
| `ATTR_LINE_SPACING` | `1.6` | Vertical spacing between attribute lines |
| `BLOCK_PADDING` | `0.5` | Padding inside outline rectangle |

### Polygon Detection

| Constant | Default | Description |
|---|---|---|
| `MIN_POLYGON_AREA` | `1.0` | Ignore polygons smaller than this |
| `ENABLE_NEAREST_FALLBACK` | `True` | Use nearest polygon when none contains text |
| `MAX_NEAREST_DISTANCE` | `500.0` | Max centroid distance for nearest fallback |

### Layer Names

| Constant | Default | Description |
|---|---|---|
| `BLOCK_LAYER` | `ROOM_DATA` | Layer for block inserts and attributes |
| `BLOCK_OUTLINE_LAYER` | `ROOM_BLOCK_OUTLINE` | Layer for room outlines |

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

#### "WARNING: Failed to insert block for ..."

- Usually a DXF format compatibility issue
- Check the application log for the specific error message
- This is non-fatal — other rooms will still be annotated

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
  autocad_scanner.py        # Scans DXF for room texts, polygons, existing blocks
  polygon_matcher.py        # Associates room text with room polygons + spreadsheet
  annotation_writer.py      # Inserts attributed blocks with polygon outlines
  metadata_utils.py         # XData read/write for annotation metadata
  spreadsheet_loader.py     # CSV / XLS / XLSX file loading
  utils.py                  # Normalization, heuristics, geometry helpers
  matcher.py                # Legacy matching utilities
  autocad_handler.py        # Legacy AutoCAD COM handler (unused in current version)
  file_loader.py            # File type detection and loading
  requirements.txt          # Python package dependencies
  README.md                 # This file
```

---

## Assumptions and Limitations

- **Windows only** — AutoCAD COM automation requires Windows.
- **AutoCAD must be installed and licensed** — the tool uses AutoCAD for DWG/DXF conversion.
- **AutoCAD must be running** — start AutoCAD before launching the tool.
- Room identifiers must be **standalone TEXT or MTEXT** entities (not block attributes).
- Room polygons must be **closed POLYLINE or LWPOLYLINE** entities.
- Only **Model Space** is scanned (Paper Space is ignored).
- The first occurrence of each room ID is used for annotation placement.
- The **first 4 characters** of the DWG filename are used as the building identifier.
- The original DWG file is **never modified** — output is always a new file, saved where you choose.

---

## License

MIT — free to use and modify.
