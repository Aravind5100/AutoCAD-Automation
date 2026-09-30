"""
dwg_converter.py
----------------
Minimal AutoCAD COM wrapper for DWG ↔ DXF conversion only.

This module uses AutoCAD's COM interface solely for file format conversion:
  - DWG -> DXF  (so ezdxf can read it)
  - DXF -> DWG  (so the final output is a standard DWG)

All entity scanning and annotation writing is handled by ezdxf, not COM.
"""

from __future__ import annotations

import os
import time
from typing import Callable

import pythoncom
import win32com.client

from config import ACAD_DWG_FORMAT, ACAD_DXF_FORMAT


class ConversionError(Exception):
    """Raised when DWG ↔ DXF conversion fails."""


def dwg_to_dxf(
    dwg_path: str,
    log_fn: Callable[[str], None] | None = None,
) -> str:
    """Convert a DWG file to DXF using AutoCAD COM.

    Parameters
    ----------
    dwg_path : str
        Absolute path to the source .dwg file.
    log_fn : callable, optional

    Returns
    -------
    str
        Absolute path to the generated .dxf file (same directory).
    """
    abs_path = os.path.abspath(dwg_path)
    if not os.path.exists(abs_path):
        raise ConversionError(f"DWG file not found:\n{abs_path}")

    base, _ = os.path.splitext(abs_path)
    dxf_path = f"{base}.dxf"

    _log(log_fn, "Connecting to AutoCAD for DWG -> DXF conversion...")

    try:
        acad = win32com.client.Dispatch("AutoCAD.Application")
    except Exception as exc:
        raise ConversionError(
            "Could not connect to AutoCAD.\n"
            "Please ensure AutoCAD is running.\n"
            f"Detail: {exc}"
        ) from exc

    _prepare_acad(acad, log_fn)

    doc = None
    opened_by_us = False

    try:
        # Check if already open
        doc = _find_open_document(acad, abs_path)
        if doc is None:
            _log(log_fn, f"  Opening: {os.path.basename(abs_path)}")
            doc = acad.Documents.Open(abs_path, True)  # read-only
            opened_by_us = True
        else:
            _log(log_fn, f"  Using already-open document")

        _log(log_fn, f"  Saving as DXF: {os.path.basename(dxf_path)}")
        doc.SaveAs(dxf_path, ACAD_DXF_FORMAT)
        _log(log_fn, "  DWG -> DXF conversion complete.")

    except ConversionError:
        raise
    except Exception as exc:
        raise ConversionError(
            f"Failed to convert DWG to DXF.\n"
            f"Error: {exc}"
        ) from exc
    finally:
        if opened_by_us and doc is not None:
            try:
                doc.Close(False)  # don't save changes
            except Exception:
                pass

    return dxf_path


def dxf_doc_to_dwg(
    dxf_doc,
    output_dwg_path: str,
    log_fn: Callable[[str], None] | None = None,
) -> str:
    """Convert an in-memory ezdxf document to DWG using AutoCAD COM.

    Parameters
    ----------
    dxf_doc : ezdxf.document.Drawing
        In-memory DXF document (from ezdxf.readfile or ezdxf.new).
    output_dwg_path : str
        Absolute path where the output DWG should be saved.
    log_fn : callable, optional

    Returns
    -------
    str
        Absolute path to the generated .dwg file.
    """
    abs_output = os.path.abspath(output_dwg_path)
    temp_dxf = f"{os.path.splitext(abs_output)[0]}_temp.dxf"

    _log(log_fn, "Connecting to AutoCAD for DXF -> DWG conversion...")

    try:
        acad = win32com.client.Dispatch("AutoCAD.Application")
    except Exception as exc:
        raise ConversionError(
            "Could not connect to AutoCAD.\n"
            "Please ensure AutoCAD is running.\n"
            f"Detail: {exc}"
        ) from exc

    _prepare_acad(acad, log_fn)

    doc = None
    opened_by_us = False

    try:
        # Save in-memory DXF to temporary file
        _log(log_fn, f"  Saving temporary DXF: {os.path.basename(temp_dxf)}")
        dxf_doc.saveas(temp_dxf)

        # Open temp DXF in AutoCAD and save as DWG
        _log(log_fn, f"  Opening DXF: {os.path.basename(temp_dxf)}")
        doc = acad.Documents.Open(temp_dxf, True)  # read-only
        opened_by_us = True

        _log(log_fn, f"  Saving as DWG: {os.path.basename(abs_output)}")
        doc.SaveAs(abs_output, ACAD_DWG_FORMAT)
        _log(log_fn, "  DXF -> DWG conversion complete.")

        return abs_output

    except Exception as exc:
        raise ConversionError(
            f"DXF -> DWG conversion failed:\n{exc}"
        ) from exc

    finally:
        if doc is not None and opened_by_us:
            try:
                doc.Close(False)
            except Exception:
                pass
        # Clean up temporary DXF
        try:
            if os.path.exists(temp_dxf):
                os.remove(temp_dxf)
        except Exception:
            pass


def dxf_to_dwg(
    dxf_path: str,
    log_fn: Callable[[str], None] | None = None,
) -> str:
    """Convert a DXF file back to DWG using AutoCAD COM.

    Parameters
    ----------
    dxf_path : str
        Absolute path to the source .dxf file.
    log_fn : callable, optional

    Returns
    -------
    str
        Absolute path to the generated .dwg file.
    """
    abs_path = os.path.abspath(dxf_path)
    if not os.path.exists(abs_path):
        raise ConversionError(f"DXF file not found:\n{abs_path}")

    base, _ = os.path.splitext(abs_path)
    dwg_path = f"{base}.dwg"

    _log(log_fn, "Connecting to AutoCAD for DXF -> DWG conversion...")

    try:
        acad = win32com.client.Dispatch("AutoCAD.Application")
    except Exception as exc:
        raise ConversionError(
            "Could not connect to AutoCAD.\n"
            f"Detail: {exc}"
        ) from exc

    _prepare_acad(acad, log_fn)

    try:
        _log(log_fn, f"  Opening DXF: {os.path.basename(abs_path)}")
        doc = acad.Documents.Open(abs_path, False)

        _log(log_fn, f"  Saving as DWG: {os.path.basename(dwg_path)}")
        doc.SaveAs(dwg_path)  # default format = DWG

        doc.Close(False)
        _log(log_fn, "  DXF -> DWG conversion complete.")

    except ConversionError:
        raise
    except Exception as exc:
        raise ConversionError(
            f"Failed to convert DXF to DWG.\n"
            f"Error: {exc}"
        ) from exc

    return dwg_path


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _prepare_acad(acad, log_fn=None) -> None:
    """Make AutoCAD visible and suppress dialogs that cause COM to hang."""
    try:
        acad.Visible = True
        _log(log_fn, "  AutoCAD is visible.")
    except Exception:
        pass

    try:
        # FILEDIA=0 suppresses file-related dialog boxes
        doc = acad.ActiveDocument
        if doc is not None:
            doc.SetVariable("FILEDIA", 0)
            doc.SetVariable("CMDDIA", 0)
            # Suppress proxy graphics warning
            doc.SetVariable("PROXYNOTICE", 0)
            _log(log_fn, "  Suppressed AutoCAD dialogs (FILEDIA=0, PROXYNOTICE=0).")
    except Exception:
        pass


def _find_open_document(acad, dwg_path: str):
    """Return the Document COM object if already open, else None."""
    abs_lower = os.path.abspath(dwg_path).lower()
    try:
        for i in range(acad.Documents.Count):
            doc = acad.Documents.Item(i)
            try:
                if doc.FullName.lower() == abs_lower:
                    return doc
            except Exception:
                continue
    except Exception:
        pass
    return None


def _log(fn, msg: str) -> None:
    if fn is not None:
        fn(msg)
