# Room Layer Tool

Puts room information from a facilities spreadsheet into an AutoCAD floor plan, ready for ArcGIS.

For every room that appears in both the drawing and the spreadsheet, the tool writes a copy
of the room's outline and a text label with its key **`[Building]-[Floor]-[Room]`** (for
example `0036-1-022`). All rooms go on **one layer**, `ROOM_KEYS` by default. In ArcGIS the
key labels are joined to the room polygons that contain them, and from there to the spreadsheet.

The original drawing is never changed. The result is saved as a new file wherever you choose.

---

## What you need

- **Windows 10 or 11**
- **AutoCAD 2018 or later**, installed, for **DWG** drawings. The tool uses AutoCAD only to
  convert the file; you do not need to use AutoCAD yourself. **DXF** drawings work without AutoCAD.
- Nothing else. Python and all libraries are included.

## Install

1. **Unzip** the whole ZIP to a normal folder, for example `Documents\Room Layer Tool`.
   Do not run it from inside the ZIP.
2. Open the folder and double-click **`Room Layer Tool.exe`**.

Windows may show *"Windows protected your PC"* the first time, because the app is not
code-signed. Click **More info → Run anyway**. If your IT policy blocks unsigned apps,
ask IT to allow `Room Layer Tool.exe`.

To remove it, delete the folder.

## Use

1. **Files**
   - **Spreadsheet → Browse…**: the room data (Excel or CSV). A large workbook takes 15–25 s
     the first time; after that, the same file loads instantly.
   - **Drawing → Browse…**: the floor plan (DWG or DXF).
   - **Building ID** is filled in from the start of the drawing's file name
     (`0036_Maintenance_01.dwg` → `0036`). Correct it if needed.
2. **Columns & output**: check the **Room**, **Building** and **Floor** columns (normally
   detected automatically); the green text shows an example key. **Room layer** is the layer
   that receives every room (default `ROOM_KEYS`).
3. Click **▶ Write Room Keys** and choose where to save the result.
   For DWG files AutoCAD is started (or used, if already open) to convert the drawing;
   a floor plan takes about 10–20 seconds. **Cancel** stops after the current step and saves nothing.
4. Read the **Results** tab. Use **Show** to filter:

| Status | Meaning |
|---|---|
| ✓ Created | Outline copy and key text written |
| ⚠ Check | Written, but worth a look, e.g. the label does not fit inside a very small room |
| – Skipped / ✗ Failed | Not written; the Note says why (no room outline found, empty Floor value…) |
| ○ Not in spreadsheet | A room number in the drawing has no spreadsheet row, e.g. `ELECT1` vs `ELEC1` |
| ○ Not in drawing | A spreadsheet row has no room number in this drawing (often another floor) |

The **Log** tab shows every step. The ☾/☀ button (top right) switches between light and dark.

## In ArcGIS

Add the result drawing. Use its **Polygon** and **Annotation** feature classes limited to the
room layer (e.g. definition query `Layer = 'ROOM_KEYS'`), then **spatially join** the key
annotations to the polygons that contain them. To bring in other columns (department,
occupant, area…), join the spreadsheet on the key, built by combining its Building, Floor and
Room columns with `-`.

## If something goes wrong

- **Check that the app works on this computer.** Open a Command Prompt in the app folder and run:
  ```
  "Room Layer Tool.exe" --selftest selftest.txt
  ```
  Then open `selftest.txt`. It tests the libraries, runs a small built-in example and reports
  whether AutoCAD is installed. It does not touch your files and does not start AutoCAD.
  The last line should read `RESULT: PASS`.
- **"No spreadsheet rows have … = 0036"**: the Building ID or the Building column is wrong.
- **Few or no rooms matched**: check the Room column. Room numbers must be written the same
  way in the drawing and the spreadsheet (`022` is not `22`).
- **Seems stuck on "Converting DWG to DXF"**: switch to AutoCAD and close any open dialog
  box, then it continues.
- **"Could not save the DWG"**: the target file is probably open in AutoCAD. Close it there,
  or choose another name.

## Where the tool keeps things

- Your result: wherever you save it.
- Temporary files: a private folder in `%TEMP%` that is deleted after every run.
- Spreadsheet cache (for fast re-loading): `%LOCALAPPDATA%\RoomAnnotator\spreadsheet_cache`.
  It is safe to delete.
- Settings (theme, last folders): the Windows registry under `RoomAnnotator\RoomLayerTool`.
