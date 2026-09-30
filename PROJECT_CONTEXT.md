# AutoCAD Room Annotation Tool — Project Context

> Full knowledge file for this repository: why it exists, how it was planned and built,
> what went wrong, what was decided, and where it stands. Written for Claude (and humans)
> picking the project up cold.
>
> **Evidence labels** used below:
> **[verified]** = checked by reading code / running code on 2026-09-29 ·
> **[history]** = taken from git commits or the deleted `DOCUMENTATION.md` ·
> **[inferred]** = reasoned from circumstantial evidence, not written down anywhere — treat as a hypothesis.

---

## 1. TL;DR

A Windows desktop tool (Python + Tkinter) that takes:

- a **spreadsheet** of room data (CSV / XLS / XLSX, e.g. department, occupant, area), and
- an **AutoCAD floor plan** (DWG, or DXF),

finds the room-number labels and room-boundary polygons in the drawing, matches each room to its
spreadsheet row, and writes the chosen spreadsheet columns into the drawing as **ArcGIS-readable
attributed blocks** (INSERT + ATTRIB), plus a room-outline copy and XData metadata.
Output: a new DWG (or DXF) at a location the user picks in a Save As dialog (suggested name `<name>_annotated.<ext>`, starting in Documents). The input file is never overwritten and cannot be chosen as the target.

AutoCAD itself is only used (over COM) to convert DWG ↔ DXF. All drawing reading and writing is
done in pure Python with **ezdxf**.

---

## 2. Why this project exists

**The problem [inferred from docs + sample names]:** Facilities / space-management teams keep room
data (who occupies a room, which department, square footage) in spreadsheets, while floor plans live
in AutoCAD. Getting that data into the drawings — and from there into ArcGIS for campus GIS —
is manual: open each drawing, find each room, type the values. It is slow, error-prone, and has to be
redone whenever the spreadsheet changes.

Context clues: the author's email is `@GMU.EDU`, and the example filename in the docs is
`0132_SATELLITE DISH LAB ANNEX_01.dwg` (4-digit building code + building name). That points to a
university facilities / GIS setting where drawings are named by building number and one spreadsheet covers many buildings.

**The goal:** point the tool at a spreadsheet and a drawing, pick columns, click Run → get an annotated drawing
whose room data shows up as fields in the ArcGIS attribute table.

**Requirements that shaped the design [history]:**

1. Never overwrite the original drawing.
2. Only use spreadsheet rows for the drawing's own building (the spreadsheet covers many buildings).
3. Tie each annotation to its room polygon so it can be queried later (XData with polygon handle).
4. Re-running should not create duplicates.
5. Output must import cleanly into **ArcGIS** (attributed blocks, safe names, tags ≤ 30 chars).
6. Must be usable by non-developers (GUI, setup/run scripts, troubleshooting README).

---

## 3. Technology

| Layer | Technology | Version in `.venv` [verified] | Why |
|---|---|---|---|
| Language | Python | 3.13.14 (README says 3.10+; code uses `X \| Y` types) | Fast to build; good CAD and data libraries |
| GUI | Tkinter / ttk (`clam` theme, custom dark palette) | stdlib | No extra dependency; ships with Python |
| Spreadsheets | pandas + openpyxl (xlsx) + xlrd (xls) | pandas **3.0.1**, openpyxl 3.1.5, xlrd 2.0.2 | Standard |
| DXF read/write | **ezdxf** | 1.4.3 | Pure-Python, fast, no AutoCAD needed for entity work |
| DWG ↔ DXF | AutoCAD COM automation via **pywin32** (`win32com.client`, `pythoncom`) | pywin32 311 | DWG is a closed format; AutoCAD is the reliable converter |
| AutoCAD | AutoCAD 2023 installed on dev machine (`AutoCAD.Application.24`) | — | README claims 2018+ |
| Packaging | PyInstaller (`build_exe.spec`) → replaced by ZIP + `setup.bat`/`run.bat` | pyinstaller 6.19.0 | See decision D7 |
| Geometry | Hand-written (ray casting, shoelace, centroid, bbox) in `utils.py` | — | Avoid shapely/numpy dependency |

`requirements.txt`: `pandas>=2.0.0, openpyxl>=3.1.0, xlrd>=2.0.1, pywin32>=306, ezdxf>=1.0.0` (no upper pins — see issue B5).

---

## 4. Architecture

### 4.1 Pipeline (current code, `ui.py::_run_annotation`, runs on a worker thread)

```
User picks: spreadsheet, drawing, room-ID column, building column, columns to insert
        │
Phase 0 │ dwg_converter.dwg_to_dxf(dwg, work_dir)   [only if input is .dwg]
        │   _acad_session: Dispatch → save+zero FILEDIA/CMDDIA/PROXYNOTICE (blank anchor drawing if none open)
        │   → copy DWG into private work_dir → open copy read-only → SaveAs(work_dir/<name>.dxf, 65)
        │   → close → restore sysvars. User's open drawings are never touched. All COM calls via _call (busy retry)
Phase 1 │ utils.extract_building_id()  first 4 chars of filename, uppercased
        │ utils.filter_dataframe_by_building()  stop if 0 rows
Phase 2 │ autocad_scanner.scan_drawing()  ezdxf.readfile, one pass over modelspace:
        │   TEXT/MTEXT → is_room_identifier() → RoomText
        │   closed LWPOLYLINE/POLYLINE, area ≥ 1.0 → RoomPolygon (vertices, area, centroid, bbox)
        │   INSERT on ROOM_DATA → existing annotation IDs (dedup — BROKEN, see B2)
        │   stop if no room texts
Phase 3 │ polygon_matcher.associate_texts_with_polygons()
        │   bbox prefilter → ray-cast → smallest containing polygon ("contains", conf 1.0)
        │   else nearest centroid ≤ 500 units ("nearest", conf = 1 - d/500)
Phase 4 │ polygon_matcher.match_rooms()   strip+lowercase exact match; first drawing occurrence wins
        │   stop if 0 matches
Phase 5 │ annotation_writer.write_annotations()   re-reads the DXF with ezdxf, returns (Drawing, count)
        │   per matched room: block def ROOM_BLOCK_<ID> (ATTDEF per column) → INSERT on ROOM_DATA
        │   placed at label X, label Y − h×1.6 → ATTRIBs → outline copy on ROOM_BLOCK_OUTLINE
        │   → XData ROOM_INFO_AI
Phase 5b│ .dwg input: dwg_converter.dxf_doc_to_dwg(doc, out, work_dir)  temp DXF in work_dir → open → SaveAs(out, 64)
        │ work_dir (tempfile.mkdtemp) is removed in _run_annotation's finally
        │ .dxf input: doc.saveas(out)      (out = path chosen in AppUI._ask_output_path before the run starts)
Phase 6 │ summary to log + messagebox
```

### 4.2 Module map

| File | Responsibility | Notes |
|---|---|---|
| `main.py` | Entry point; DPI awareness; centre window | |
| `ui.py` | `AppUI`: 4-step GUI, validation, worker thread, whole pipeline orchestration | Log/status updates are marshalled via `root.after`; **messageboxes are not** (B6) |
| `config.py` | Every tunable constant | Some constants are dead (see §8) |
| `spreadsheet_loader.py` | `load_spreadsheet` (dtype=str, keep_default_na=False), `_clean_dataframe`, room-ID column guess | Excel header row = **3rd row** by default (enterprise reports have title rows) |
| `utils.py` | Column normalisation, building-ID logic, MTEXT code stripping, room-ID heuristic, geometry, attribute-map builder | |
| `dwg_converter.py` | AutoCAD COM conversion only: `dwg_to_dxf`, `dxf_doc_to_dwg`, (unused) `dxf_to_dwg`, `_prepare_acad` | |
| `autocad_scanner.py` | ezdxf single-pass scan → `RoomText`, `RoomPolygon`, `ScanResult` dataclasses | `AutoCADError` name kept from COM era |
| `polygon_matcher.py` | `TextPolygonAssociation`, `RoomMatch`, `MatchSummary`; spatial association + sheet matching | O(texts × polygons) — fine for floor plans |
| `annotation_writer.py` | Blocks, attribs, outlines, XData via ezdxf | Returns an in-memory `Drawing`, **not** a path (docstring is stale) |
| `metadata_utils.py` | `AnnotationMetadata`, XData write/read, ArcGIS-safe `normalize_block_name` / `tag_from_column` | |
| `setup.bat` / `run.bat` | End-user setup (venv + pip) and launch (warns if `acad.exe` not running) | |
| `tests/` + `run_tests.bat` | unittest suite (56 tests): utils, metadata, spreadsheet, scanner, matcher, pipeline, converter (fake COM), UI (scripted dialogs); `test_acad_integration.py` runs only with `RUN_ACAD_TESTS=1` / `run_tests.bat acad` | Known open issues B10/B11/B12 are `expectedFailure` tests — they start "unexpectedly passing" when fixed |
| `build_exe.spec` | PyInstaller one-folder GUI build | Untracked in working tree (re-added after being deleted in d00322d) |

### 4.3 What gets written into the drawing (output contract)

| Item | Value |
|---|---|
| Layers created | `ROOM_DATA` (block inserts + attribs), `ROOM_BLOCK_OUTLINE` (outlines), colour 3 (green) |
| Block definition | `ROOM_BLOCK_<ROOM_ID>` — non-alphanumerics → `_`, uppercased, ≤ 255 chars |
| Attribute tags | from column names: non-alphanumerics → `_`, uppercased, ≤ 30 chars (`"Occupied By"` → `OCCUPIED_BY`); prompt = original column name |
| Insert point | room label X; label Y − text_height × 1.6; attrib lines spaced text_height × 1.6 |
| Outline | copy of the associated room polygon (POLYLINE in R12); fallback rectangle ~25 × text height wide if no polygon |
| XData app | `ROOM_INFO_AI`, six 1000-strings in order: `room_id, polygon_handle, building_id, text_handle, match_method, annotation_type("room_info")` |

Handles in XData are handles in the intermediate DXF. [verified 2026-09-29 with AutoCAD 2023] they stay valid in the
final DWG: after DXF → DWG → DXF, every XData polygon handle still pointed at the room polygon.

---

## 5. How the project evolved (timeline) [history + file mtimes]

| When (2026) | Version | What happened |
|---|---|---|
| ~Mar 16–17 | **v0** (pre-git) | Pure COM prototype: `autocad_handler.py` (SelectionSet text scan, `AddMText`, save `_updated.dwg`), `matcher.py`, `file_loader.py`. Plain text-under-label annotation, no polygon awareness. |
| Mar 27 | **v1** — `c53698c` initial commit | Modular rewrite: scanner / polygon_matcher / annotation_writer / metadata_utils / config. Added **polygon association**, **XData linkage**, **building filter**, **dedup**, dark GUI, 929-line `DOCUMENTATION.md`. Still 100% COM, output = **MTEXT** on `ROOM_INFO_AI`. Branches `master` and `dev_mtext` (remote default branch) still point here. |
| Mar 27 (code) / Mar 30 (commit) | **v2** — `b6578c2` "ezdxf migration + standalone exe build" | Switched scanning and writing to **ezdxf** on a DXF made by AutoCAD; output switched from MTEXT to **ArcGIS attributed blocks**; outlines follow the real room polygon; MTEXT formatting stripper added; PyInstaller spec added. `.gitignore` gained `debug_saveas.py, debug_polys.py, debug_scan.py, debug_scan2.py, test_full_pipeline.py` — traces of the debugging done here. |
| Mar 31 | **v3** — `d00322d` (pushed 2026-09-29) | Fixed COM hangs by suppressing AutoCAD dialogs (`_prepare_acad`); **dropped the exe** in favour of ZIP + `setup.bat`/`run.bat`; README rewritten as an end-user guide; removed stale docs. `AutoCAD_Room_Annotator_v1.0.zip` built 13:50 (gitignored). |
| Sep 29 | `7f31ea3`, `41957a8` | Legacy v0 files removed, `build_exe.spec` restored, `.gitignore` trimmed; PROJECT_CONTEXT.md, CLAUDE.md and the learning report added. |
| Sep 29 | group-1 fix | 2018 DXF/DWG conversion (B1, B3), MTEXT via `plain_text()` + `char_height` fix (B8), 2D-only POLYLINE filter, user-chosen output location (D13). |
| Sep 29 | groups 2+3 | Dedup fixed (B2) and outline copies ignored on re-scan; pandas-3-safe cleaning (B5); private work dir + copy-before-convert (B4, B9); sysvars saved/restored with anchor drawing (B7, B19); busy-call retry `_call` (B18); dialogs marshalled to Tk main thread (B6); writer returns a Drawing (B13). Verified offline, with fake COM, and against AutoCAD 2023. |
| Sep 29 | group 4 | `tests/` unittest suite + `run_tests.bat` (B17): 56 offline tests + 2 opt-in real-AutoCAD tests, all passing. |

Branch note: there is **no `main` branch** — local branches are `master`, `dev_mtext`, `dev_exe`; remote default is `dev_mtext`.

---

## 6. Decisions made (and why)

| # | Decision | Rationale | Evidence |
|---|---|---|---|
| D1 | Python + Tkinter desktop app | Runs where AutoCAD runs (Windows desktop); no server; stdlib GUI | history |
| D2 | Match labels to rooms by **geometry**: point-in-polygon, **smallest containing polygon wins**, nearest-centroid fallback ≤ 500 | Floor/building outlines also contain every label; the tightest one is the room. Fallback covers labels placed just outside. Confidence stored for audit | history (DOCUMENTATION.md) |
| D3 | Building ID = first 4 chars of DWG filename; filter spreadsheet before matching; abort if 0 rows | Prevents cross-building mistakes when one sheet covers campus | history |
| D4 | Metadata in **XData** (`ROOM_INFO_AI`) with polygon + text handles | Standard AutoCAD mechanism; survives save; queryable later | history |
| D5 | **Migrate from COM entity access to ezdxf** (keep COM only for conversion) | [inferred] COM is one cross-process call per property (slow on large drawings), fragile (busy/rejected calls, modal dialogs), and returns raw MTEXT formatting codes (the stripper's comment says "returned by AutoCAD COM TextString"). ezdxf is fast, testable offline, deterministic | commit msg says *what*, not *why* |
| D6 | Output **attributed blocks** instead of MTEXT | ArcGIS turns block attributes into attribute-table fields; MTEXT is just text | history (README ArcGIS section) |
| D7 | ~~Convert through **R12 DXF**~~ → **2018 DXF / native DWG** since 2026-09-29 (`ACAD_DXF_FORMAT = 65`, `ACAD_DWG_FORMAT = 64`) | R12 was [inferred] chosen for easy scanning but degraded the whole drawing (B3). MTEXT is now read with ezdxf `MText.plain_text()` | code |
| D13 | User chooses the **output location** (Save As dialog, starts in Documents, remembers last folder, refuses the input file) | Owner decision 2026-09-29: don't save next to the original by default | code |
| D8 | Distribute as **ZIP + setup.bat/run.bat**, not a PyInstaller exe | [inferred] exe build of pywin32/pandas is large and brittle and trips antivirus; ZIP + venv is transparent. d00322d: "replaced by ZIP distribution". Branch `dev_exe` + re-added spec suggests this is still open | history |
| D9 | Suppress AutoCAD dialogs (FILEDIA/CMDDIA/PROXYNOTICE = 0) | Modal dialogs block COM calls forever ("hangs at Converting DWG → DXF") | history (d00322d, README troubleshooting) |
| D10 | Single-pass scan into plain dataclasses; no live entity references after scan | Performance and separation (matcher/writer never touch the CAD layer) | history |
| D11 | All strings (`dtype=str`, `keep_default_na=False`) for spreadsheets | Keep room IDs like `0101`, `102A` intact | code |
| D12 | Excel header default = row 3 | Enterprise reports have 2 title rows | history |

---

## 7. Issues hit during development and how they were tackled [history + inferred]

| Issue | Tackled by |
|---|---|
| COM scanning slow / fragile on large drawings | Single-pass scan + caching (v1); then replaced COM scanning with ezdxf (v2) |
| ModelSpace not ready right after open | Retry 3× with 1 s delay (v1 COM scanner; gone after v2) |
| MTEXT labels came back with formatting codes (`{\fArial|b0;101}`) so room IDs failed the heuristic | `strip_mtext_formatting` regex (v2); replaced by ezdxf `plain_text()` on 2026-09-29 |
| Labels nearer a floor outline than a room / outlines nesting | Smallest-area containing polygon rule |
| Plain MTEXT useless in ArcGIS | Attributed blocks with ArcGIS-safe names (v2) |
| `LWPOLYLINE requires DXF R2000` when writing outlines into an R12 doc | `try: add_lwpolyline except: add_polyline2d(...).close()` fallback [verified: ezdxf raises `DXFVersionError` for LWPOLYLINE and MTEXT in R12] |
| AutoCAD modal dialogs hanging the conversion | `_prepare_acad` + README "Alt+Tab and dismiss dialog" guidance (v3) |
| Non-developer install friction / exe problems | ZIP + `setup.bat` (checks Python ≥ 3.10, venv, pip, import check) + `run.bat` (checks venv and `acad.exe`) (v3) |
| Re-runs creating duplicates | XData-based dedup (designed v1, ported v2 — **but the ezdxf port is broken**, B2) |

---

## 8. Open issues — verified on 2026-09-29

Severity: 🔴 wrong output / data loss · 🟠 incorrect behaviour · 🟡 robustness / hygiene

| ID | Sev | Issue | Evidence | Suggested fix |
|---|---|---|---|---|
| **B1** ✅ fixed 2026-09-29 | 🔴 | `dxf_doc_to_dwg` calls `doc.SaveAs(abs_output, 1)` with comment "1 = DWG format" (`dwg_converter.py:150`). In the AutoCAD 2023 type library **`1 = acR12_dxf`**; `acNative = ac2018_dwg = 64`. So the "DWG" output is requested in **R12 DXF format**. | [verified] enum read from `acax24enu.tlb`. Runtime verified 2026-09-29 with AutoCAD 2023: output header `AC1032` (real 2018 DWG); 2018 DXF keeps HATCH/MTEXT/LWPOLYLINE. | `doc.SaveAs(abs_output)` (native) or `64`; then check the output file header begins `AC10xx`, not `0\nSECTION`. |
| **B2** ✅ fixed 2026-09-29 | 🔴 | **Dedup never works.** Scanner does `for appid, tags in entity.xdata` (`autocad_scanner.py:259, 282`) → `TypeError: 'XData' object is not iterable`, swallowed by `except Exception: pass`. Even with the correct API, `get_xdata()` excludes the 1001 app tag, so `tags[1]` would be the **polygon handle**, not the room ID. Re-running on an annotated drawing adds duplicate blocks + outlines. | [verified] built an annotated R12 DXF, rescanned → `existing_annotation_room_ids == set()` | `xd = entity.get_xdata(XDATA_APP_NAME)` → `xd[0].value`; or reuse `metadata_utils.read_xdata`. Also: outline copies on `ROOM_BLOCK_OUTLINE` are rescanned as room polygons — skip that layer. |
| **B3** ✅ fixed 2026-09-29 | 🔴 | **Round-trip through R12 degrades the whole drawing** (no LWPOLYLINE, MTEXT exploded, no hatch associativity / dynamic blocks / modern objects; `$INSUNITS` not exported). Output is a lossy copy of the original plus annotations. | [verified] ezdxf R12 limits; ezdxf warns "Drawing units ($INSUNITS) are not exported for DXF R12" | Convert via `ac2018_dxf` (65) and ezdxf ≥ R2000; LWPOLYLINE/MTEXT paths already exist. Re-test the MTEXT stripper (B8) then. |
| **B4** ✅ fixed 2026-09-29 | 🟠 | Intermediate `<name>.dxf` from `dwg_to_dxf` is **never deleted** and **silently overwrites** any existing same-name DXF. README says "no intermediate DXF files are left behind". | [verified] code | Write to a temp dir; delete in `finally`. |
| **B5** ✅ fixed 2026-09-29 | 🟠 | **pandas 3.x** reads `dtype=str` as the new `str` dtype, so `if df[col].dtype == object` (`spreadsheet_loader.py:103`) is false → **cell values are never stripped**; `'  Eng '` is written to the drawing. Blank rows aren't dropped either (empty strings aren't NaN). `setup.bat` installs latest pandas → fresh installs hit this. | [verified] pandas 3.0.1 in `.venv`, end-to-end test | Strip with `df[col].str.strip()` regardless of dtype; drop rows where all values `== ""`; or pin `pandas<3`. |
| **B6** ✅ fixed 2026-09-29 | 🟠 | `messagebox.*` called from the worker thread (`ui.py:481, 500, 587, 617, 630, 635`). Tkinter is not thread-safe → occasional hangs/crashes. | [verified] code | Wrap in `self.root.after(0, ...)`. |
| **B7** ✅ fixed 2026-09-29 | 🟠 | `_prepare_acad` sets FILEDIA/CMDDIA/PROXYNOTICE = 0 on the user's AutoCAD and **never restores** them. These are registry-persisted → the user's AutoCAD keeps file dialogs off afterwards. | [verified] code; sysvar persistence is AutoCAD behaviour | Read old values first, restore in `finally`. |
| **B8** ✅ fixed 2026-09-29 | 🟠 | MTEXT stripper: lowercase `\p` is in the toggle group, so paragraph codes like `\pxqc;101` become `xqc;101` → fail the room-ID check → room silently missed. `\P` becomes "" not " " (`Line1\PLine2` → `Line1Line2`, docstring says `Line1 Line2`). Only matters for DXF input today (R12 has no MTEXT) but matters after B3's fix. | [verified] ran function | Handle `\p...;` as a sized code; replace `\P` with space; or use `ezdxf`'s `MText.plain_text()`. |
| **B9** ✅ fixed 2026-09-29 | 🟠 | If the drawing is **already open** in AutoCAD (which the README tells users to do), `dwg_to_dxf` calls `SaveAs` on the user's open document, which re-points that document to the R12 `.dxf` [inferred AutoCAD SaveAs semantics]. | code | Open a separate read-only copy, or use `doc.Export`/`WBLOCK`-style copy. |
| **B10** | 🟡 | Excel numeric building codes lose leading zeros: cell `132` (number) → `'132'` ≠ `'0132'` → rows filtered out. | [verified] openpyxl test | Zero-pad numeric building values to `BUILDING_ID_LENGTH`, or warn. |
| **B11** | 🟡 | Room-ID heuristic false positives: `"1ST FLOOR"`, `"LEVEL 2"`, `"SCALE 1"`, `"STAIR 3"`, `"UP 18R"`, `"2024"` all pass; `"Room 101"` passes but will not match sheet `"101"`. False negatives: `"LOBBY"`, `"101 / 102"`. Harmless unless a false positive matches a sheet ID. | [verified] ran function | Optional label-layer filter; configurable regex. |
| **B12** | 🟡 | Existing `ROOM_BLOCK_<ID>` definition is reused as-is → newly selected columns silently dropped. `"101-A"`, `"101 A"`, `"101_A"` collide to one block name. | [verified] code + ran | Name blocks by column-set hash or redefine. |
| **B13** ✅ fixed 2026-09-29 | 🟡 | `write_annotations` returns `(Drawing, n)` normally but `(str, 0)` when nothing to write → caller would crash on `.saveas`. Guarded in practice by the `matched_count == 0` stop. Docstring still says it returns a path. | [verified] code (`annotation_writer.py:109, 184`) | Return `(doc, 0)`. |
| **B14** | 🟡 | Nearest fallback uses centroid distance in raw drawing units (500 means very different things in mm vs inches); L-shaped rooms have centroids outside the room. | [verified] L-shape test | Distance to polygon edge; unit-aware threshold. |
| **B15** | 🟡 | Dead code/config left from the COM/MTEXT era (partly cleaned 2026-09-29: `dxf_to_dwg`, `_prepare_acad`, `_build_dxf_output_path`, `strip_mtext_formatting`, `Vec3`/`time` imports removed; `read_xdata` now used). Still left: `format_mtext_content`, `build_output_path`, `has_app_xdata`, `find_column`, `build_col_map`; constants `OUTPUT_LAYER` (still used only for legacy MTEXT dedup), `MTEXT_WIDTH_FACTOR`, `VERTICAL_SPACING_MULTIPLIER`, `DXF_VERSION`, `ARCGIS_SAFE_LAYER`; unused imports (`time`, `Vec3`, `build_output_path`). | [verified] grep | Remove after fixing B2. |
| **B16** | 🟡 | README drift: still lists the deleted legacy files; claims no intermediate DXF (B4); ArcGIS example table shows `ROOM_ID`/`BUILDING` fields that only exist if the user ticks those columns (building ID lives in XData, not attributes). | [verified] | Update README. |
| **B17** ✅ fixed 2026-09-29 | 🟡 | No automated tests; no sample data in repo. | [verified] | See §10.3 for an offline test recipe. |
| **B18** ✅ fixed 2026-09-29 | 🟠 | When AutoCAD is busy, COM calls fail with `RPC_E_CALL_REJECTED` ("Call was rejected by callee"). `dwg_converter` wraps `doc.Close` / `SetVariable` in `except: pass`, so a rejected `Close` silently **leaves the converted drawing open** in AutoCAD. | [verified 2026-09-29] AutoCAD 2023 test left `<name>.dxf` open | Retry on `RPC_E_CALL_REJECTED` (small retry helper or a COM message filter) and log failures. |
| **B19** ✅ fixed 2026-09-29 | 🟡 | `_prepare_acad` needs an open drawing (`ActiveDocument`) to set FILEDIA/CMDDIA/PROXYNOTICE. When AutoCAD sits on the Start tab with no drawing open, suppression is **silently skipped** for the DWG → DXF step. | [verified 2026-09-29] `Documents.Count == 0` → "Failed to get the Document object" | Set sysvars after opening the drawing, and restore them afterwards (see B7). |

---

## 9. What the project delivered, proved, and why it's useful

**Delivered**
- A working GUI tool that runs spreadsheet → drawing annotation end to end on DXF input (verified offline in this analysis),
  and on DWG input via AutoCAD (developer-tested per commit history; output format subject to B1/B3).
- `AutoCAD_Room_Annotator_v1.0.zip`: end-user package with `setup.bat`, `run.bat`, and a troubleshooting README.
- ArcGIS-ready output structure: attributed blocks on `ROOM_DATA`, safe names, per-room XData linking annotation → polygon → source label → building.
- A reusable pure-Python geometry/association core (`utils.py`, `polygon_matcher.py`) with no CAD dependency.

**Proved (demonstrated by the implementation)**
- Room labels can be reliably tied to room boundaries with **geometry alone** (smallest containing polygon), with no manual tagging — verified on synthetic plans (rooms nested in a floor outline associate correctly).
- AutoCAD is only needed as a **format converter**; all entity work can run in ezdxf, making the core fast and testable without AutoCAD.
- Spreadsheet room data can become **structured GIS attributes** (not just visual text) through standard AutoCAD block attributes.
- Not proved/measured: no timing benchmarks, accuracy stats on real drawings, or ArcGIS import screenshots are in the repo.

**Why it's helpful**
- Turns a room-by-room manual CAD edit into a single run; re-runnable when the spreadsheet changes (once B2 is fixed).
- Building filter and "never overwrite input" make it safe for a campus-wide spreadsheet.
- The log (matched / unmatched in drawing / unmatched in sheet) doubles as a **data-quality report** between the facilities spreadsheet and the drawings.
- XData linkage lets later scripts find each room's polygon from its annotation.

---

## 10. Working on this repo (instructions for Claude)

### 10.1 Run
```bash
.venv/Scripts/python.exe main.py          # dev (Git Bash); or run.bat for end-user flow
```
DWG input requires AutoCAD installed (COM `AutoCAD.Application`); DXF input needs **no AutoCAD** — use DXF for testing.

### 10.2 Conventions
- Module header docstring with a `----` underline; `# ---` section banners; NumPy-style docstrings; `from __future__ import annotations`; `_log(fn, msg)` helper per module; dataclasses for data passed between stages.
- All tunables go in `config.py`.
- UI work on the worker thread must go through `self.root.after(0, ...)`.
- `.gitattributes`: `.py/.md/.txt` = LF, `.bat` = CRLF, `.dwg` binary. `*.dwg`, `*.dxf`, the ZIP are gitignored — never commit drawings.

### 10.3 Tests
```bash
.venv/Scripts/python.exe -W ignore::DeprecationWarning -m unittest discover -s tests -t .   # offline, ~10 s
RUN_ACAD_TESTS=1 .venv/Scripts/python.exe -m unittest tests.test_acad_integration          # real AutoCAD, ~1 min
```
(Windows: `run_tests.bat` / `run_tests.bat acad`.) `tests/helpers.py` has `make_plan()` (synthetic 3-room plan in a
floor outline, R2018 or R12) and `run_pipeline()` (the same stage sequence as `AppUI._run_annotation`). Add a test for
every behaviour change; turn an `expectedFailure` into a normal test when fixing its issue. The integration tests assert
in `tearDown` that AutoCAD's sysvars and open drawings are unchanged.

### 10.4 Gotchas
- ezdxf: `entity.xdata` is an `XData` object (not iterable); use `entity.get_xdata(app)` / `has_xdata(app)` (or `metadata_utils.read_xdata`). R12 docs reject LWPOLYLINE and MTEXT (`DXFVersionError`). `Insert.attribs` is a list — use `get_attrib(tag)`.
- AutoCAD busy: calls fail with `RPC_E_CALL_REJECTED`, **or** — when pywin32 must look a member up by name — with `AttributeError: AutoCAD.Application.<member>`. Wrap every COM call in `dwg_converter._call`. AutoCAD is busiest right after a drawing is closed (returning to the Start tab).
- System variables need an open drawing; with none open, `ActiveDocument` raises "Failed to get the Document object".
- Shell quirk seen on this machine: running test scripts from Git Bash `$TMP` (`/tmp/...`) hung at start-up; run them by Windows path (e.g. the session scratchpad) instead.
- AutoCAD `AcSaveAsType`: 1 = R12 DXF, 12/13 = 2000 DWG/DXF, 24/25 = 2004, 36/37 = 2007, 48/49 = 2010, 60/61 = 2013, 64/65 = 2018; `acNative` = 64.
- COM from a thread needs `pythoncom.CoInitialize()` / `CoUninitialize()` (already done in `_run_annotation`).
- `win32com.client.Dispatch` will *launch* AutoCAD if it is not running (slow); the README asks users to start it first.
- Git: work happens on `dev_exe` (tracks `origin/dev_exe`). There is no `main` branch; remote default is `dev_mtext` (still at the initial commit). Ask before committing/pushing.

### 10.5 Open questions for the owner
1. Exe (PyInstaller, `dev_exe` branch, re-added spec) or ZIP distribution — which is final?
2. Was R12 chosen deliberately (e.g. an ArcGIS or older-tool requirement), or only for scan convenience? (Decides the B1/B3 fix.)
3. Should the building ID also be written as a block attribute so it shows in ArcGIS?
4. Is annotating an already-annotated drawing an expected workflow (B2 priority)?
