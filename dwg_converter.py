"""
dwg_converter.py
----------------
Minimal AutoCAD COM wrapper for DWG ↔ DXF conversion only.

This module uses AutoCAD's COM interface solely for file format conversion:
  - DWG -> DXF  (so ezdxf can read it)
  - DXF -> DWG  (so the final output is a standard DWG)

All entity scanning and annotation writing is handled by ezdxf, not COM.

Side-effect rules
~~~~~~~~~~~~~~~~~
- Intermediate files live in a private work folder (``make_work_dir``),
  never next to the input drawing.
- The user's open drawings are never saved or re-pointed: a *copy* of the
  input DWG is opened and converted.
- Dialog-suppressing system variables are restored when conversion ends.
- Calls AutoCAD rejects while busy are retried; anything that still fails
  is logged instead of silently ignored.
"""

from __future__ import annotations

import os
import shutil
import tempfile
import time
from contextlib import contextmanager
from typing import Callable

import pywintypes
import win32com.client

from config import ACAD_DWG_FORMAT, ACAD_DXF_FORMAT, COM_RETRY_SECONDS

# HRESULTs AutoCAD returns while it is busy; the call should be retried
_BUSY_HRESULTS = {
    -2147418111,    # RPC_E_CALL_REJECTED ("Call was rejected by callee")
    -2147417846,    # RPC_E_SERVERCALL_RETRYLATER
}

# System variables that make AutoCAD show modal dialogs (which block COM)
_SUPPRESSED_SYSVARS = ("FILEDIA", "CMDDIA", "PROXYNOTICE")


class ConversionError(Exception):
    """Raised when DWG ↔ DXF conversion fails."""


# ---------------------------------------------------------------------------
# Work folder
# ---------------------------------------------------------------------------

def make_work_dir() -> str:
    """Create a private temporary folder for intermediate files."""
    return tempfile.mkdtemp(prefix="room_annotator_")


def remove_work_dir(work_dir: str | None) -> None:
    """Delete a folder created by :func:`make_work_dir`."""
    if work_dir:
        shutil.rmtree(work_dir, ignore_errors=True)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def dwg_to_dxf(
    dwg_path: str,
    work_dir: str,
    log_fn: Callable[[str], None] | None = None,
) -> str:
    """Convert a DWG file to DXF using AutoCAD COM.

    The DWG is copied into *work_dir* first, so a drawing the user has open
    in AutoCAD is never touched.

    Parameters
    ----------
    dwg_path : str
        Path to the source .dwg file.
    work_dir : str
        Folder for intermediate files (from :func:`make_work_dir`).
    log_fn : callable, optional

    Returns
    -------
    str
        Path to the generated .dxf file inside *work_dir*.
    """
    abs_path = os.path.abspath(dwg_path)
    if not os.path.exists(abs_path):
        raise ConversionError(f"DWG file not found:\n{abs_path}")

    base = os.path.splitext(os.path.basename(abs_path))[0]
    copy_path = os.path.join(work_dir, f"{base}_source.dwg")
    dxf_path = os.path.join(work_dir, f"{base}.dxf")

    _log(log_fn, "Connecting to AutoCAD for DWG -> DXF conversion...")
    with _acad_session(log_fn) as acad:
        _warn_if_unsaved(acad, abs_path, log_fn)
        shutil.copy2(abs_path, copy_path)

        _log(log_fn, f"  Opening a copy of: {os.path.basename(abs_path)}")
        try:
            doc = _call(lambda: acad.Documents.Open(copy_path, True))  # read-only
        except Exception as exc:
            raise ConversionError(f"AutoCAD could not open the drawing.\nError: {exc}") from exc

        try:
            _log(log_fn, "  Saving as DXF (AutoCAD 2018 format)...")
            _call(lambda: doc.SaveAs(dxf_path, ACAD_DXF_FORMAT))
        except Exception as exc:
            raise ConversionError(f"Failed to convert DWG to DXF.\nError: {exc}") from exc
        finally:
            _close(doc, log_fn)

    _log(log_fn, "  DWG -> DXF conversion complete.")
    return dxf_path


def dxf_doc_to_dwg(
    dxf_doc,
    output_dwg_path: str,
    work_dir: str,
    log_fn: Callable[[str], None] | None = None,
) -> str:
    """Convert an in-memory ezdxf document to DWG using AutoCAD COM.

    Parameters
    ----------
    dxf_doc : ezdxf.document.Drawing
        In-memory DXF document (from ezdxf.readfile or ezdxf.new).
    output_dwg_path : str
        Path where the output DWG should be saved.
    work_dir : str
        Folder for intermediate files (from :func:`make_work_dir`).
    log_fn : callable, optional

    Returns
    -------
    str
        Absolute path to the generated .dwg file.
    """
    abs_output = os.path.abspath(output_dwg_path)
    temp_dxf = os.path.join(work_dir, "annotated.dxf")

    try:
        dxf_doc.saveas(temp_dxf)
    except Exception as exc:
        raise ConversionError(f"Could not write the temporary DXF.\nError: {exc}") from exc

    _log(log_fn, "Connecting to AutoCAD for DXF -> DWG conversion...")
    with _acad_session(log_fn) as acad:
        try:
            doc = _call(lambda: acad.Documents.Open(temp_dxf, True))  # read-only
        except Exception as exc:
            raise ConversionError(f"AutoCAD could not open the annotated DXF.\nError: {exc}") from exc

        try:
            _log(log_fn, f"  Saving as DWG: {abs_output}")
            _call(lambda: doc.SaveAs(abs_output, ACAD_DWG_FORMAT))
        except Exception as exc:
            raise ConversionError(
                f"Could not save the DWG:\n{abs_output}\n\n"
                "Check that the folder is writable and the file is not open in AutoCAD.\n"
                f"Error: {exc}"
            ) from exc
        finally:
            _close(doc, log_fn)

    _log(log_fn, "  DXF -> DWG conversion complete.")
    return abs_output


# ---------------------------------------------------------------------------
# AutoCAD session: connect, suppress dialogs, always restore
# ---------------------------------------------------------------------------

@contextmanager
def _acad_session(log_fn=None):
    """Connect to AutoCAD with dialogs suppressed; restore them on exit.

    System variables can only be read or set through an open drawing. If
    AutoCAD has none open (Start tab), a blank drawing is opened for the
    duration and closed unsaved afterwards.
    """
    try:
        acad = win32com.client.Dispatch("AutoCAD.Application")
    except Exception as exc:
        raise ConversionError(
            "Could not connect to AutoCAD.\n"
            "Please ensure AutoCAD is installed and running.\n"
            f"Detail: {exc}"
        ) from exc

    try:
        _call(lambda: setattr(acad, "Visible", True))
    except Exception as exc:
        _log(log_fn, f"  WARNING: could not make AutoCAD visible: {exc}")

    anchor, anchor_is_ours = None, False
    saved: dict[str, object] = {}
    try:
        if _call(lambda: acad.Documents.Count) > 0:
            anchor = _call(lambda: acad.ActiveDocument)
        else:
            anchor = _call(lambda: acad.Documents.Add())
            anchor_is_ours = True
        for var in _SUPPRESSED_SYSVARS:
            saved[var] = _call(lambda: anchor.GetVariable(var))
            _call(lambda: anchor.SetVariable(var, 0))
        _log(log_fn, "  Suppressed AutoCAD dialogs (restored when finished).")
    except Exception as exc:
        _log(log_fn, f"  WARNING: could not suppress AutoCAD dialogs ({exc}). "
                     "If AutoCAD shows a dialog, dismiss it to continue.")

    try:
        yield acad
    finally:
        for var, value in saved.items():
            try:
                _call(lambda: anchor.SetVariable(var, value))
            except Exception as exc:
                _log(log_fn, f"  WARNING: could not restore {var} to {value} ({exc}). "
                             f"Type {var} in AutoCAD and set it to {value}.")
        if anchor_is_ours:
            _close(anchor, log_fn)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _call(fn):
    """Run a COM call, retrying while AutoCAD reports that it is busy.

    A busy AutoCAD shows up either as a busy HRESULT, or — when pywin32
    first has to look a member up by name — as an AttributeError naming
    the member (e.g. "AutoCAD.Application.Documents").
    """
    deadline = time.monotonic() + COM_RETRY_SECONDS
    while True:
        try:
            return fn()
        except pywintypes.com_error as exc:
            if exc.hresult not in _BUSY_HRESULTS or time.monotonic() >= deadline:
                raise
        except AttributeError:
            if time.monotonic() >= deadline:
                raise
        time.sleep(0.5)


def _close(doc, log_fn=None) -> None:
    """Close a drawing without saving; log (don't hide) a failure."""
    try:
        name = _call(lambda: doc.Name)
    except Exception:
        name = "drawing"
    try:
        _call(lambda: doc.Close(False))
    except Exception as exc:
        _log(log_fn, f"  WARNING: could not close {name} in AutoCAD ({exc}). "
                     "Close it manually without saving.")


def _warn_if_unsaved(acad, dwg_path: str, log_fn=None) -> None:
    """Log a warning if *dwg_path* is open in AutoCAD with unsaved changes."""
    target = os.path.normcase(os.path.abspath(dwg_path))
    try:
        for i in range(_call(lambda: acad.Documents.Count)):
            doc = _call(lambda: acad.Documents.Item(i))
            if os.path.normcase(_call(lambda: doc.FullName)) == target:
                if not _call(lambda: doc.Saved):
                    _log(log_fn, "  WARNING: this drawing has unsaved changes in AutoCAD. "
                                 "The last saved version on disk is used.")
                return
    except Exception:
        pass    # purely informational


def _log(fn, msg: str) -> None:
    if fn is not None:
        fn(msg)
