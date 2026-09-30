"""
selftest.py
-----------
``Room Layer Tool.exe --selftest [report.txt]`` — checks that the installed
app works on this computer, without touching any real files:

  1. the libraries load (pandas, openpyxl, ezdxf, pywin32, Qt)
  2. a small synthetic floor plan + spreadsheet go through the full
     pipeline (DXF, so AutoCAD is not needed) and produce the expected layer
  3. whether AutoCAD is registered on this computer (it is NOT started)

Optionally, a real job can be run headlessly (used to test a build):
``--selftest report.txt <drawing> <spreadsheet> <building id> <output>``

The report is written to *report.txt* if given, otherwise shown in a window.
"""

from __future__ import annotations

import os
import platform
import shutil
import sys
import tempfile
import time
import traceback


def _check_libraries(out: list[str]) -> bool:
    ok = True
    for name in ("pandas", "openpyxl", "ezdxf", "win32com.client", "PySide6.QtWidgets"):
        try:
            module = __import__(name, fromlist=["_"])
            version = getattr(module, "__version__", "")
            out.append(f"  OK    {name} {version}".rstrip())
        except Exception as exc:
            out.append(f"  FAIL  {name}: {exc}")
            ok = False
    return ok


def _check_pipeline(out: list[str]) -> bool:
    import ezdxf
    import pipeline
    from spreadsheet_loader import load_spreadsheet

    work = tempfile.mkdtemp(prefix="room_layer_selftest_")
    try:
        doc = ezdxf.new("R2018")
        msp = doc.modelspace()
        msp.add_lwpolyline([(0, 0), (100, 0), (100, 100), (0, 100)], close=True)
        msp.add_mtext("101\\P170", dxfattribs={"insert": (20, 80), "char_height": 5})
        plan = os.path.join(work, "0132_SELFTEST.dxf")
        doc.saveas(plan)
        sheet = os.path.join(work, "rooms.csv")
        with open(sheet, "w", encoding="utf-8") as f:
            f.write("Building ID,Floor,Room\n0132,01,101\n")
        result = pipeline.run(pipeline.RunRequest(
            df=load_spreadsheet(sheet), drawing_path=plan,
            output_path=os.path.join(work, "out.dxf"), room_col="Room",
            building_col="Building ID", floor_col="Floor", building_id="0132"))
        layers = [r.layer for r in result.rows if r.status == "created"]
        if layers == ["0132-01-101"] and os.path.exists(os.path.join(work, "out.dxf")):
            out.append("  OK    synthetic plan -> layer 0132-01-101 created")
            return True
        out.append(f"  FAIL  synthetic plan produced {layers}")
        return False
    except Exception:
        out.append("  FAIL  pipeline error:\n" + traceback.format_exc())
        return False
    finally:
        shutil.rmtree(work, ignore_errors=True)


def _check_autocad(out: list[str]) -> None:
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CLASSES_ROOT, r"AutoCAD.Application\CurVer") as key:
            out.append(f"  OK    AutoCAD registered ({winreg.QueryValue(key, None)})")
    except OSError:
        out.append("  WARN  AutoCAD not found — DWG files need AutoCAD; DXF files still work")


def _real_job(out: list[str], drawing: str, sheet: str, building: str, output: str) -> bool:
    import pythoncom
    import pipeline
    from spreadsheet_loader import load_spreadsheet

    pythoncom.CoInitialize()
    try:
        start = time.monotonic()
        df = load_spreadsheet(sheet, use_cache=True)
        from utils import detect_building_column, detect_floor_column
        from spreadsheet_loader import find_room_id_column_suggestion
        cols = list(df.columns)
        result = pipeline.run(pipeline.RunRequest(
            df=df, drawing_path=drawing, output_path=output,
            room_col=find_room_id_column_suggestion(cols),
            building_col=detect_building_column(cols),
            floor_col=detect_floor_column(cols), building_id=building))
        out.append(f"  OK    real job: {result.created} layers, {len(result.rows)} result rows, "
                   f"{time.monotonic() - start:.1f} s -> {output}")
        return True
    except Exception:
        out.append("  FAIL  real job:\n" + traceback.format_exc())
        return False
    finally:
        pythoncom.CoUninitialize()


def main(argv: list[str]) -> int:
    report_path = argv[0] if argv else None
    out = [f"Room Layer Tool self-test — {time.strftime('%Y-%m-%d %H:%M')}",
           f"Windows {platform.version()} | Python {platform.python_version()} | "
           f"{'packaged app' if getattr(sys, 'frozen', False) else 'source'}", ""]
    ok = _check_libraries(out)
    ok = _check_pipeline(out) and ok
    _check_autocad(out)
    if len(argv) == 5:
        ok = _real_job(out, *argv[1:]) and ok
    out += ["", "RESULT: " + ("PASS" if ok else "FAIL")]
    text = "\n".join(out)

    if report_path:
        with open(report_path, "w", encoding="utf-8") as f:
            f.write(text + "\n")
    else:
        from PySide6.QtWidgets import QApplication, QMessageBox
        app = QApplication.instance() or QApplication([])  # noqa: F841
        box = QMessageBox(QMessageBox.Information if ok else QMessageBox.Warning,
                          "Room Layer Tool — self-test", text)
        box.exec()
    return 0 if ok else 1
