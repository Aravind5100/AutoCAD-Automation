# AutoCAD Room Annotation Tool — Project Context

> Full knowledge file for this repository: why it exists, how it was built, what went wrong,
> what was decided, where it stands, and **where the last working session stopped** (§0).
> Written so a new chat (Claude or human) can continue without the old conversation.
>
> **Evidence labels:** **[verified]** = checked by reading or running code/files ·
> **[history]** = from git commits or old docs · **[inferred]** = reasoned, not confirmed — treat as a hypothesis.
>
> Last updated: **2026-10-07** (D19: three output layers + optional detail columns).

---

## 0. Where we left off (read this first)

### 0.1 Current state
- **Branch `main`** (GitHub default branch since the owner switched it; verified 2026-10-07) holds the current
  app: **PySide6 (Qt) desktop window**, matched rooms written on **THREE layers** (D19, 2026-10-07).
- For each matched room the output drawing gets: a **copy of the room outline** on `ROOM_OUTLINES`, a **TEXT
  "tag" with the key `Building-Floor-Room`** (e.g. `0036-1-022`) inside the room on `ROOM_KEYS`, and — only
  if the user ticked detail columns (the "Room details" multi-select drop-down in step 2) — one TEXT per ticked column (e.g. Room Name)
  under the key on `ROOM_DETAILS`. All three names are editable in the app.
- **Tests:** 91 offline tests pass (2 AutoCAD tests skipped unless enabled; 2 expected failures = open issues
  B10/B11). The 2 real-AutoCAD integration tests pass (`run_tests.bat acad`).
- **Verified on the owner's real data** (see §0.3): building 0036 → 62 rooms written, 9–15 s per run
  (3-layer version with Room Name ticked: 62 written, 15 s, 5 "needs check": the 4 below + `009B`).

### 0.2 Pending / next steps (owner had not decided yet)
1. **Rebuild the supervisor package.** `Room_Layer_Tool_v2.0.zip` (in the repo folder, gitignored) and `dist/`
   were built **before** D16/D19 — they still create **one layer per room**. Rebuild (as v2.1 or later) once the
   owner is happy with the 3-layer output (recipe in §10.6). The owner has not said whether v2.0 was already sent.
2. **The owner has not yet looked at the 3-layer output (D19) in AutoCAD.**
3. **ArcGIS workflow not verified by anyone in this project.** The documented flow (polygon + annotation
   feature classes filtered to the room layer → spatial join → join spreadsheet on the key) is reasoned, not tested.
4. **UI ideas not done:** after-run buttons (open result in AutoCAD / open folder / export results CSV) —
   offered, not chosen. Layer filter for reading room labels/outlines — offered.
5. **Branch tidy-up (owner's call):** `ui-pyside6` is 2 commits behind `main` (can be deleted or fast-forwarded);
   `dev_exe` = stable Tkinter version with **per-room layers** (pre-D16); `master`/`dev_mtext` = initial commit.
   `ui.py` (Tkinter) + `tests/test_ui.py` still live on `main`, reachable via `main.py --tk`, excluded from the exe.
6. **Open issues** still unfixed: B10 (Excel numeric building codes lose leading zeros), B11 (room-ID heuristic
   false positives/negatives), B14 (nearest-centroid fallback in raw units). See §8.
7. Optional: move `AutoCAD_Project_Learning_Report.docx` into a `docs/` folder (it describes the project as of
   2026-09-29 morning — blocks/R12 era — and is a historical report, not current documentation).

### 0.3 Owner's real data (on the owner's PC; never commit these)
| Item | Path / facts |
|---|---|
| Spreadsheet | `C:\Users\akompal\Downloads\Room_Data.xlsx` — 4.6 MB, **36,367 rows × 30 columns**, header on row 3. Columns include `Building Identifier`, `Floor Code`, `Room Identifier`, `Building Name`, `Square Feet`, `Department Name`, `Room Name`, … The sheet's first row is building `0Z96`. |
| Drawing | `C:\Users\akompal\Downloads\0036_Maintenance_01.dwg` — building **0036**, floor code **`1`**; room labels are **two-line MTEXT** (room number over area, e.g. `022` / `170`) on layer `A-AREA-IDEN`; room outlines are LWPOLYLINEs on `A-AREA-PLINE` (63). ~5,700 entities. |
| Result (one-layer version) | 62 rooms written; 4 "needs check" (key label doesn't fit: `STAIR1`, `SHAFT1`, `SHAFT2`, `CORR6`); 4 drawing labels not in sheet (`18`, `48`, `80` = area figures; `ELECT1` — sheet has `ELEC1`); 15 sheet rows for 0036 not in this drawing; 81 result rows. |
| Old outputs in Downloads | `0036_Maintenance_01_annotated.dwg` (owner's run of the **per-room-layer** version); `0036_Maintenance_01.dxf` and `0036_Maintenance_01_annotated.dwg.dxf` = leftovers from an old version, safe to delete (owner told; not deleted by Claude). |

### 0.4 How the owner likes to work (from the session)
- Explain in **plain language**, then act. For design decisions offer **2–4 options with a recommendation**;
  the owner picks. Don't silently change behaviour.
- Pattern used throughout: implement → test (offline + real AutoCAD when relevant) → update README +
  this file → **commit and push** after each completed piece. The owner approved this pattern each time;
  when in doubt, ask before committing/pushing.
- Keep a **stable version untouched** when experimenting (that's why `dev_exe` and branches exist).
- AutoCAD in tests: only synthetic/scratch files; restore AutoCAD settings; leave the owner's open drawings
  alone; never quit an AutoCAD the owner started. The owner's AutoCAD 2023 is often open.
- The owner closes app windows themselves; "launch it" = run `main.py` in the background and confirm the window.

---

## 1. TL;DR

A Windows desktop tool (**Python + PySide6/Qt**; older Tkinter window on `dev_exe` and via `main.py --tk`) that takes:

- a **spreadsheet** of room data (CSV / XLS / XLSX), and
- an **AutoCAD floor plan** (DWG, or DXF),

finds the room-number labels and room-boundary polygons in the drawing, matches each room to its spreadsheet row
(only rows of the drawing's building), and writes every matched room onto **three layers** (names editable in the
app): a **copy of the room outline** (`ROOM_OUTLINES`), a **TEXT with its key** `[Building]-[Floor]-[Room]`
(values exactly as in the spreadsheet row, e.g. `0036-1-022`; `ROOM_KEYS`) and optional **detail TEXTs** with the
values of user-ticked columns such as Room Name (`ROOM_DETAILS`). All carry XData linking them to the source polygon
and label. In ArcGIS, the key annotations are spatially joined to the polygons of the outlines layer.

Output: a new DWG (or DXF) wherever the user chooses (Save As dialog; starts in Documents; the input file can never be
chosen). The original drawing is never modified. AutoCAD is used only (over COM) to convert DWG ↔ DXF; all drawing
reading/writing is done with **ezdxf**. Distributed to others as a **standalone `Room Layer Tool.exe`** (PyInstaller) in a ZIP.

Output model history: MTEXT notes (v1) → attributed blocks (v2) → one layer per room (2026-09-29, D14) →
one layer for all rooms (2026-10-01, D16) → **outlines / keys / details layers (2026-10-07, D19)**.

---

## 2. Why this project exists

**The problem [inferred]:** facilities/space-management teams keep room data in spreadsheets; floor plans live in
AutoCAD; getting room data into drawings and then into ArcGIS (campus GIS) is manual, slow and error-prone.
Context: author email `@GMU.EDU`; drawings named by 4-character building code (`0036_Maintenance_01.dwg`,
`0132_SATELLITE DISH LAB ANNEX_01.dwg`); one spreadsheet covers the whole campus.

**Goal:** pick a spreadsheet and a drawing, check the Room/Building/Floor columns, click one button → a drawing whose
rooms carry a `Building-Floor-Room` key that ArcGIS can join to the facilities table.

**Requirements [history + owner]:**
1. Never overwrite the original drawing; user chooses where to save (D13).
2. Only use spreadsheet rows for the drawing's own building.
3. Link each written entity to its source polygon/label (XData).
4. Re-running must not create duplicates.
5. Output must suit **ArcGIS**: the owner says ArcGIS reads **one layer** (D16).
6. Usable by non-developers (GUI, results table, standalone exe, plain README).

---

## 3. Technology

| Layer | Technology | Version [verified] | Why |
|---|---|---|---|
| Language | Python | 3.13.14 in `.venv` (code needs 3.10+) | Data + CAD libraries |
| GUI (`main`) | **PySide6 (Qt 6)** — `qt_ui.py`, light/dark QSS themes (colorhunt palette #FEF5ED / #D3E4CD / #ADC2A9 / #99A799 + darker sage #4F5F4F for title text, owner 2026-10-07), QThreads | PySide6-Essentials 6.11.2 (77 MB wheel) | Owner: desktop tool for 1–2 users; Qt for a results table + modern look. FastAPI+React was discussed and **rejected** (adds a server, Node build, upload/download; no desktop benefit) |
| GUI (legacy) | Tkinter/ttk — `ui.py` (`main.py --tk`; default on `dev_exe`) | stdlib | Kept as the stable fallback |
| Spreadsheets | pandas + openpyxl + xlrd | pandas **3.0.1**, openpyxl 3.1.5, xlrd 2.0.2 | Standard |
| DXF read/write | **ezdxf** | 1.4.3 | Pure Python; no AutoCAD needed for entity work |
| DWG ↔ DXF | AutoCAD COM via **pywin32** | pywin32 311 | DWG is closed; AutoCAD converts reliably |
| AutoCAD | AutoCAD 2023 on the dev PC (`AutoCAD.Application.24`) | — | The supervisor's PC needs AutoCAD for DWG |
| Packaging | **PyInstaller** one-folder exe (`build_exe.spec`) + ZIP with `packaging/README.md` | pyinstaller 6.19.0 (dev-only, not in requirements.txt) | No Python needed on the target PC (owner choice) |
| Geometry | hand-written ray casting / shoelace / centroid / bbox (`utils.py`) | — | No shapely |
| Tests | stdlib `unittest` (`tests/`, `run_tests.bat`) | — | No extra dependency |

`requirements.txt`: pandas>=2.0.0, openpyxl>=3.1.0, xlrd>=2.0.1, pywin32>=306, ezdxf>=1.0.0, PySide6-Essentials>=6.7.

---

## 4. Architecture

### 4.1 Pipeline (`pipeline.run`, called by the Qt window on a `RunWorker` QThread)

```
RunRequest(df, drawing_path, output_path, room_col, building_col, floor_col, building_id,
           layers=OutputLayers(outlines, keys, details), detail_cols=[...])
  1 Filter spreadsheet to building_id (BEFORE AutoCAD; 0 rows → RunStopped)
  2 [DWG only] dwg_converter.dwg_to_dxf(dwg, work_dir)
        _acad_session: Dispatch AutoCAD (launches it if not running), Visible=True,
        save + set FILEDIA/CMDDIA/PROXYNOTICE = 0 (blank anchor drawing if none open), restore on exit
        copy DWG into a private temp work_dir → open the copy read-only → SaveAs 2018 DXF (code 65) → close
        the user's open drawings are never touched; warns if the drawing is open with unsaved changes
        every COM call via _call (retries RPC_E_CALL_REJECTED / AttributeError while AutoCAD is busy, 60 s)
  3 autocad_scanner.scan_drawing(dxf)  (ezdxf, one pass over modelspace)
        TEXT/MTEXT → room label if is_room_identifier(); multi-line MTEXT → first line that looks like a room ID
        label_bbox measured with ezdxf.bbox (for tag placement); MTEXT size from char_height
        entities carrying our XData (outline copies / tags from earlier runs) → existing room IDs (dedup), skipped
        closed 2D LWPOLYLINE/POLYLINE, area ≥ 1 → room polygon candidates (3D polylines + legacy outline layer skipped)
        ScanResult.doc keeps the parsed drawing (the writer reuses it); 0 labels → RunStopped
  4 polygon_matcher.associate_texts_with_polygons: bbox prefilter → ray cast → smallest containing polygon
        ("contains"); else nearest centroid ≤ 500 units ("nearest")
  5 polygon_matcher.match_rooms(..., [building_col, floor_col, room_col] + detail_cols): strip+lowercase exact match,
        first occurrence wins; unmatched lists both ways; 0 matches → RunStopped
  6 annotation_writer.write_room_layers(scan.doc, ..., outcomes=[...], layers=req.layers, detail_cols=...)
        ensure the layers (outlines 3 green, keys 2 yellow, details 4 cyan — details only if columns ticked);
        per matched room: key = build_room_key(row values as-is)
        outline copy (LWPOLYLINE; POLYLINE if R12) on outlines + key TEXT on keys + one TEXT per non-empty
        ticked column on details; XData on all (annotation_type room_outline / room_key / room_detail;
        details also carry the column name)
        placement: key + detail lines as one stacked block — under / above the room label, or centred in the
        room, at 100/75/50% of the label height — first spot fully inside the polygon; else the first spot whose
        start is inside; else under the label. If the block never fits, the key is placed alone that way
        (same as without details) and the details are stacked under it (→ needs_check)
        RoomOutcome per room: created / skipped (already has a key, no polygon, empty key part) / failed;
        needs_check (nearest link, tag doesn't fit, polygon shared by 2+ labels)
  7 [DWG] dxf_doc_to_dwg → temp DXF in work_dir → AutoCAD SaveAs native 2018 DWG (code 64) | [DXF] doc.saveas
  work_dir is always removed (finally). is_cancelled() is checked between steps → RunCancelled, nothing saved.
→ RunResult(created, matched, sheet_rows, labels_found, polygons_found, rows=[ResultRow(room, key, status, note, needs_check)])
  rows also include "not in spreadsheet" (drawing labels) and "not in drawing" (sheet rows of this building)
```
The Tkinter `ui.py` has its **own copy** of this flow (`AppUI._run_annotation`), always using the default
layers `ROOM_OUTLINES` + `ROOM_KEYS` and no details (owner chose to leave the Tk window as is).

### 4.2 Module map

| File | Responsibility |
|---|---|
| `main.py` | Entry point: Qt window; `--tk` → Tkinter window; `--selftest [report] [drawing sheet building output]` → `selftest.py` |
| `qt_ui.py` | PySide6 `MainWindow`: **1 Files** (spreadsheet, drawing, editable Building ID), **2 Columns & output** (Room/Building/Floor combos, key preview for the chosen building, **Outlines / Keys / Details layer** boxes validated by
`layer_name_problem`, must differ, remembered), **Room details** (`MultiSelectDropdown`: button + menu of QCheckBoxes, stays open while ticking, remembered; a QComboBox with checkable items did not register clicks on Windows), **▶ Write Room Keys** / Cancel, step progress bar, **Results** tab (Room / Key / Status / Note; filter All / Created / Needs check / Skipped/failed / Not matched; summary line), **Log** tab, ☾/☀ theme toggle. `SheetLoader` + `RunWorker` QThreads; QSettings `RoomAnnotator/RoomLayerTool` (theme, layer_outlines/keys/details, detail_cols, browse_dir, output_dir). Pure helpers: `check_output_path`, `default_output_dir`, `status_label`, `row_matches_filter`, `stylesheet` |
| `pipeline.py` | UI-independent run (§4.1): `RunRequest`, `RunResult`, `ResultRow`, `RunStopped`, `RunCancelled` |
| `selftest.py` | `--selftest`: library check, built-in synthetic DXF job, AutoCAD registry check (doesn't start AutoCAD); optional real headless job; writes a report or shows a dialog |
| `ui.py` | Legacy Tkinter `AppUI` (same pipeline inline; fixed default layers, no details) |
| `config.py` | Tunables: header rows (Excel row 3), `SPREADSHEET_CACHE_DIR`, `BUILDING_ID_LENGTH`, `ROOM_OUTLINE/KEY/DETAIL_LAYER_DEFAULT`, `ROOM_KEY_SEPARATOR`, `ROOM_*_LAYER_COLOR`, `ROOM_TAG_GAP_FACTOR`, `LAYER_NAME_FORBIDDEN_CHARS`, `LEGACY_OUTLINE_LAYERS`, heuristics, polygon limits, `XDATA_APP_NAME`, AutoCAD save codes (`ACAD_DXF_FORMAT=65`, `ACAD_DWG_FORMAT=64`), `COM_RETRY_SECONDS`, `OUTPUT_SUFFIX` |
| `spreadsheet_loader.py` | `load_spreadsheet(path, use_cache=False)` — dtype=str, trims cells, drops blank rows (pandas 2/3 safe); pickle cache keyed by path+size+mtime+header rows (the UI uses it: 36k-row xlsx 13–25 s → 0.1 s) |
| `utils.py` | Column normalisation; building-ID extract/detect/filter; floor-column detect; `is_room_identifier`; geometry; `build_room_key` (as-is); `layer_name_problem` |
| `dwg_converter.py` | `dwg_to_dxf`, `dxf_doc_to_dwg`, `make_work_dir`/`remove_work_dir`, `_acad_session`, `_call`, `_close`, `_warn_if_unsaved` |
| `autocad_scanner.py` | `RoomText` (incl. `label_bbox`), `RoomPolygon`, `ScanResult` (incl. `doc`), `scan_drawing` |
| `polygon_matcher.py` | `TextPolygonAssociation`, `RoomMatch`, `MatchSummary`; association + matching |
| `annotation_writer.py` | `write_room_layers` (name kept from the per-room-layer era), `OutputLayers`, `RoomOutcome` (`key`, `status`, `note`, `needs_check`) |
| `metadata_utils.py` | `AnnotationMetadata` (`annotation_type` OUTLINE/KEY/DETAIL, optional `field`), `register_xdata_app`, `write_xdata`, `read_xdata` |
| `build_exe.spec` | PyInstaller 6 one-folder build of the Qt app → `dist\Room Layer Tool\Room Layer Tool.exe` (no UPX, Tkinter excluded, ezdxf data bundled) |
| `packaging/README.md` | Short install/usage guide shipped inside the ZIP (for the supervisor) |
| `setup.bat` / `run.bat` | Source setup (venv + pip incl. PySide6) and launch |
| `tests/` + `run_tests.bat` | 91 offline tests + `test_acad_integration.py` (opt-in) |
| `README.md` | Developer/user README for the source version |
| `CLAUDE.md` | Imports this file |
| `AutoCAD_Project_Learning_Report.docx` | 31-page learning report written 2026-09-29 (historical snapshot) |

### 4.3 Output contract (what is written into the drawing)

| Item | Value |
|---|---|
| Layers | outlines `ROOM_OUTLINES` (colour 3 green), keys `ROOM_KEYS` (2 yellow), details `ROOM_DETAILS` (4 cyan, only created when detail columns are ticked); names from the app |
| Per matched room | closed **copy** of its polygon (outlines) + **TEXT = key** inside the room (keys) + one **TEXT per non-empty ticked column**, stacked under the key, in column order (details) |
| Key | `<Building>-<Floor>-<Room>` with values **exactly as in the spreadsheet** (trimmed only), e.g. `0036-1-022`, `0132-01-101` |
| Tag size | the room label's text height, shrunk to 75%/50% if needed to fit (key and details share one size) |
| XData | app `ROOM_INFO_AI` on every written entity: `room_id, polygon_handle, building_id, text_handle, match_method, annotation_type` (`room_outline` / `room_key` / `room_detail`; `room_layer` in drawings from before D19) + `field` (column name, details only) |
| Not written | blocks, attributes, rectangles; unmatched rooms; rooms without a polygon |
| Originals | untouched (layers, polygons, labels) |
| ArcGIS (documented, **not verified**) | Polygon feature class filtered to the outlines layer + Annotation feature class filtered to the keys layer → spatial join (key annotation inside polygon) → join facilities table on the key |

XData handles stay valid through DXF → DWG [verified with AutoCAD 2023].

---

## 5. Timeline

| When (2026) | What happened |
|---|---|
| ~Mar 16–17 | v0 pure-COM prototype (MTEXT under labels). |
| Mar 27 `c53698c` | v1 modular COM version: polygon association, XData, building filter, dedup, MTEXT output. (`master`, `dev_mtext` still here.) |
| Mar 30 `b6578c2` | v2 ezdxf migration; attributed blocks for ArcGIS; PyInstaller spec. |
| Mar 31 `d00322d` | v3 dialog suppression, setup/run.bat, ZIP distribution (`AutoCAD_Room_Annotator_v1.0.zip`, since deleted). |
| Sep 29 | Repo analysis (5 passes), `PROJECT_CONTEXT.md`, `CLAUDE.md`, 31-page learning report (.docx via Word COM). |
| Sep 29 `4084005` | Group 1: 2018 DXF/DWG instead of R12 (B1, B3), MTEXT `plain_text()` (B8), user-chosen output location. |
| Sep 29 `0bdac87` | Groups 2+3: dedup (B2), pandas-3 cleaning (B5), private work dir (B4), copy-before-convert (B9), sysvar restore (B7, B19), busy retry (B18), Tk thread-safe dialogs (B6). |
| Sep 29 `74c0aa1` | Group 4: unittest suite + `run_tests.bat`. |
| Sep 29 `6e402c0` | D14: one layer per room named `Building-Floor-Room` instead of blocks. |
| Sep 29 `311f451` | Real-data fixes: two-line MTEXT labels (3/62 → 62/62 matched), visible key TEXT, spreadsheet cache + background load, single drawing read. `dev_exe` stops here. |
| Sep 30 `f536d2d` | PySide6 window + `pipeline.py` on branch `ui-pyside6`. |
| Sep 30 `a862917` | Standalone exe + `--selftest` + `packaging/README.md`; `Room_Layer_Tool_v2.0.zip` built (per-room layers). |
| Sep 30 `cee06fa` | Dead-code cleanup; loose files removed (build/, old ZIP, caches). |
| Oct 1 | `main` created from `ui-pyside6` and pushed. |
| Oct 1 `63a28a4` | **D16: all rooms on one layer** (`ROOM_KEYS`, editable), key text as-is, "Write Room Keys", Results "Key" column. |
| Oct 1 `4dc3c21` | The AutoCAD integration test always cleans up its temp folder. |
| by Oct 7 | The owner switched the GitHub default branch to `main`. |
| Oct 7 `df4763b` | This file rewritten as a handoff; README project structure updated. |
| Oct 7 | **D19: three layers** (outlines / keys / details) + optional detail columns picked in the app. |

---

## 6. Decisions (and why)

| # | Decision | Why | Source |
|---|---|---|---|
| D1 | Desktop app in Python (Tkinter originally) | Runs where AutoCAD runs | history |
| D2 | Geometry links labels to rooms: smallest containing polygon, nearest-centroid fallback ≤ 500 | Floor outlines contain every label | history |
| D3 | Building ID = first 4 chars of the file name (now **editable** in the Qt UI); filter the sheet first | Campus-wide sheet | history / owner |
| D4 | XData metadata on written entities | Traceability + dedup | history |
| D5 | ezdxf for entity work; COM only for conversion | Speed, robustness, testability [inferred] | history |
| D7 | 2018 DXF/DWG (codes 65/64), not R12 | R12 degraded drawings (B3) | code |
| D8 | **Standalone exe** (PyInstaller) + ZIP for other people | Owner: the supervisor shouldn't need Python | owner 2026-09-30 |
| D9 | Suppress AutoCAD dialogs during conversion, then restore | Modal dialogs block COM | history + fix |
| D10 | Single-pass scan into dataclasses | Speed, separation | history |
| D11 | Spreadsheets read as text | Keep IDs like `0101`, `102A` | code |
| D12 | Excel header row 3 by default | Institutional reports have title rows | history |
| D13 | The user chooses the output location (Save As, starts in Documents, refuses the input) | Owner | owner |
| D14 | ~~One layer per room~~ (superseded by D16) | ArcGIS better with layers than blocks | owner |
| D15 | PySide6 UI on a branch, stable Tk kept on `dev_exe`; features: results table, editable Building ID, Cancel, light/dark + bigger fonts | Owner | owner |
| D16 | **One layer for all rooms** (default `ROOM_KEYS`, editable), outline copy + key TEXT per room; key as-is | Owner: "that's how ArcGIS reads" | owner 2026-10-01 |
| D17 | Visible key tag inside each room (shrinks for small rooms) | The owner couldn't see anything new in the drawing | owner 2026-09-29 |
| D18 | Filter by building before starting AutoCAD | A wrong building ID fails in <1 s | Claude, accepted |
| D19 | **Three layers**: outline copies (`ROOM_OUTLINES`), key tags (`ROOM_KEYS`), optional details (`ROOM_DETAILS`) with values of user-ticked spreadsheet columns, one TEXT each, stacked under the key; all 3 names editable; Tk window left as is | Owner: separate outlines from tags; generic place for room name etc. Separate TEXTs (not MTEXT) because ArcGIS reads TEXT more reliably | owner 2026-10-07 |

---

## 7. Problems met and how they were solved

| Problem | Solution |
|---|---|
| The output "DWG" was really R12 DXF; the R12 round trip degraded drawings | Save codes 64/65 (verified with the AutoCAD type library + real files) |
| Dedup never worked (non-iterable XData, swallowed error) | `read_xdata`; detect our entities by XData |
| pandas 3 broke cell trimming | Value-wise strip, blank-row drop |
| Leftover DXF next to the input; the user's open drawing re-pointed; AutoCAD settings left changed | Private temp work dir, convert a copy, save/restore sysvars (with a blank anchor drawing) |
| AutoCAD busy → rejected calls / AttributeError on name lookup | `_call` retry wrapper |
| Real labels are two-line MTEXT (number over area) → 3/62 matched | Use the line that looks like a room ID → 62/62 |
| Nothing visible in the output | Key TEXT tag inside each room, smart placement |
| 36k-row spreadsheet took 13–25 s and froze the UI | Background load + pickle cache (0.1 s) + library preload |
| One 520 s conversion | AutoCAD was blocked (modal state); the rerun took 21 s; first open after idle ≈ 19 s, warm ≈ 4 s |
| Qt off-screen screenshots showed boxes | `QT_QPA_FONTDIR=C:/Windows/Fonts` |
| Scripted Qt runs "hung" | Modal `QMessageBox` waiting for a click — patch it in tests |
| Tests leaked temp folders (work dir, QSettings, failed tearDown) | Fixed with cleanup / sync / finally |

---

## 8. Open issues

| ID | Status | Issue |
|---|---|---|
| B1–B9, B13, B15, B17–B19 | ✅ fixed (2026-09-29/30) | See git history; regression tests exist |
| B12 | ➖ obsolete | Block-name collisions (no blocks now) |
| B16 | ✅ 2026-10-07 | README drift — README updated for Qt + one layer + project structure; keep it in sync |
| **B10** | open 🟡 | Excel numeric building codes lose leading zeros (`132` vs `0132`) → rows filtered out. `expectedFailure` test exists. Fix idea: zero-pad numeric building values to `BUILDING_ID_LENGTH`, or warn. |
| **B11** | open 🟡 | Room-ID heuristic: false positives (`1ST FLOOR`, `LEVEL 2`, `STAIR 3`, `2024`), false negatives (`LOBBY`). Harmless unless a false positive matches a sheet ID. Fix idea: label-layer filter (real labels are on `A-AREA-IDEN`) or match against spreadsheet IDs. `expectedFailure` test exists. |
| **B14** | open 🟡 | Nearest fallback uses centroid distance in raw drawing units; concave rooms' centroids can be outside. |
| B20 | note | Intermittent real-AutoCAD test failure seen once (end-of-test check of open drawings/settings) — likely the owner using AutoCAD during the test; not reproduced in 3 reruns. |

---

## 9. Delivered / proved / useful

**Delivered:** Qt desktop app; standalone exe + self-test; ZIP for a supervisor (v2.0 — needs a v2.1 rebuild); one-layer
ArcGIS-oriented output with visible keys; per-room results table; 87 + 2 tests; README, packaging README, learning report.

**Proved on real data:** 62/62 rooms of building 0036 matched and written (also with the 3-layer output); conversions produce real 2018 DWGs
(`AC1032`); originals untouched; XData links survive conversion; the packaged exe gives identical tag positions to source.

**Not proved:** ArcGIS import/join; behaviour on the supervisor's PC; accuracy across other buildings/floors.

---

## 10. Working on this repo

### 10.1 Run
```bash
.venv/Scripts/python.exe main.py            # Qt window (or run.bat)
.venv/Scripts/python.exe main.py --tk       # legacy Tkinter window
.venv/Scripts/python.exe main.py --selftest report.txt
```
DWG needs AutoCAD (COM `AutoCAD.Application`; `Dispatch` launches it if closed). DXF needs no AutoCAD — use DXF in tests.

### 10.2 Conventions
- Module docstring with a `----` underline; `# ---` section banners; NumPy-style docstrings; `from __future__ import annotations`;
  `_log(fn, msg)` helpers; dataclasses between stages; all tunables in `config.py`.
- Qt: touch widgets only on the GUI thread (signals from QThreads). Tk: worker → `root.after`.
- `.gitattributes`: py/md/txt LF, bat CRLF. Never commit drawings, spreadsheets, `dist/`, `build/` or ZIPs.

### 10.3 Tests
```bash
.venv/Scripts/python.exe -W ignore::DeprecationWarning -m unittest discover -s tests -t .       # offline ~10 s
RUN_ACAD_TESTS=1 .venv/Scripts/python.exe -m unittest tests.test_acad_integration              # real AutoCAD ~1 min
```
Windows: `run_tests.bat` / `run_tests.bat acad`. Helpers in `tests/helpers.py`: `make_plan()` (3 rooms in a floor
outline, R2018/R12), `run_pipeline()`, `room_key_labels()`, `room_key_polygons()` (grouped by key), `tool_layers()`,
`EXPECTED_KEYS`, `ROOMS_CSV`. Qt tests run off-screen (`QT_QPA_PLATFORM=offscreen`) with QMessageBox patched.

### 10.4 Gotchas
- ezdxf: `entity.xdata` isn't iterable → `get_xdata`/`read_xdata`; R12 rejects LWPOLYLINE/MTEXT; `Insert.attribs` is a list.
- AutoCAD busy → `RPC_E_CALL_REJECTED` or `AttributeError: AutoCAD.Application.<member>` → always use `dwg_converter._call`.
- Sysvars need an open drawing ("Failed to get the Document object" on the Start tab).
- A COM call blocks while AutoCAD shows a modal dialog or is mid-command.
- `AcSaveAsType`: 1 = R12 DXF, 64 = 2018 DWG (= acNative), 65 = 2018 DXF.
- Cold imports of pandas/openpyxl can take 10–14 s on this PC (disk/AV).
- Git Bash: running scripts from `$TMP` (`/tmp/...`) hung at start-up — use Windows paths. Escaped `\n` / `\\`
  inside shell heredocs got mangled several times — write edit scripts to a file instead.
- Off-screen Qt screenshots: `QT_QPA_PLATFORM=offscreen` + `QT_QPA_FONTDIR=C:/Windows/Fonts`, then `window.grab().save()`.

### 10.5 Branches
`main` (current, GitHub default) · `ui-pyside6` (2 commits behind main) · `dev_exe` (stable Tkinter, per-room layers) ·
`dev_mtext` / `master` (initial commit).

### 10.6 Build and package the standalone app
```bash
.venv/Scripts/python.exe -m PyInstaller build_exe.spec --noconfirm --clean     # ~2 min → dist\Room Layer Tool\
"dist/Room Layer Tool/Room Layer Tool.exe" --selftest selftest.txt             # expect RESULT: PASS
```
Then ZIP `dist\Room Layer Tool\*` under a top folder `Room Layer Tool/` **plus** `packaging\README.md` as
`Room Layer Tool/README.md` → `Room_Layer_Tool_v2.1.zip` (≈70 MB; gitignored pattern `Room_Layer_Tool_*.zip`).
Verify: unzip to a fresh folder and run `--selftest`; optionally a real job:
`--selftest report.txt <drawing> <spreadsheet> <building> <output>`. Share via OneDrive/Drive (too big for email).
Unsigned exe → Windows SmartScreen "More info → Run anyway" (documented in the packaging README).

---

## 11. Conversation log (2026-09-29 → 2026-10-07), in order
1. "Understand this repo" → overview + first issues.
2. Deep 5-pass analysis → this file + `CLAUDE.md`.
3. 20–30 page learning report → `AutoCAD_Project_Learning_Report.docx` (built with Word COM; 31 pages).
4. Commit/push; list of design decisions; blocks vs layers discussion.
5. Main code concerns → groups 1–5 plan. Group 1 (+ Save As location), tested with real AutoCAD; groups 2+3; group 4 tests.
6. Owner: "use layers, key = Building-Floor-Room" → D14 (per-room layers, Floor column).
7. "Can't see the tag / app slow / change UI" → two-line MTEXT fix, visible tags, cache, speed work.
8. UI toolkit discussion (Tkinter vs ttkbootstrap vs PySide6 vs FastAPI+React) → PySide6 on a branch (D15).
9. "Share with supervisor" → standalone exe + self-test + packaging README + `Room_Layer_Tool_v2.0.zip`.
10. Repo check for loose/dead files → cleanup.
11. "Move PySide6 to GitHub" → `main` created; the owner later made it the default branch.
12. "Separate layers or one layer?" → owner: **one layer** (D16), outline copy + key text, layer name editable.
13. Confirmed current behaviour: one layer + a tag per room. Then: this file updated for the handoff (2026-10-07).
14. "Most urgent first" → docs committed (`df4763b`); the v2.1 rebuild was stopped by the owner for a design change:
    **D19** — outlines, key tags and details on separate layers; details = spreadsheet columns ticked in the app.
