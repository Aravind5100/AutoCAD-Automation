"""
autocad_scanner.py
------------------
Connects to AutoCAD via COM, opens a DWG, and performs a **single-pass**
scan of ModelSpace to collect:

  1. Room identifier TEXT / MTEXT entities
  2. Closed polyline (room polygon) candidates

All entity properties are cached into plain Python dataclasses so that
no further COM round-trips are needed after scanning.
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass, field
from typing import Callable

import pythoncom
import win32com.client

from config import (
    DEFAULT_TEXT_HEIGHT,
    OUTPUT_LAYER,
    SCAN_PROGRESS_INTERVAL,
    XDATA_APP_NAME,
)
from utils import is_room_identifier, is_valid_room_polygon


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------

class AutoCADError(Exception):
    """Raised for any unrecoverable AutoCAD / COM error."""


# ---------------------------------------------------------------------------
# Scanned-entity dataclasses  (pure Python — no COM references)
# ---------------------------------------------------------------------------

@dataclass
class RoomText:
    """Cached properties of a TEXT / MTEXT entity that is a room identifier."""
    handle: str = ""
    entity_type: str = ""           # AcDbText | AcDbMText
    text: str = ""
    normalized_text: str = ""
    position: tuple[float, float, float] = (0.0, 0.0, 0.0)
    layer: str = ""
    text_height: float = DEFAULT_TEXT_HEIGHT
    text_style: str = ""


@dataclass
class RoomPolygon:
    """Cached properties of a closed polyline that may be a room boundary."""
    handle: str = ""
    entity_type: str = ""           # AcDbPolyline | AcDb2dPolyline
    layer: str = ""
    closed: bool = False
    vertices: list[tuple[float, float]] = field(default_factory=list)
    area: float = 0.0
    centroid: tuple[float, float] = (0.0, 0.0)
    bbox: tuple[float, float, float, float] = (0.0, 0.0, 0.0, 0.0)


@dataclass
class ScanResult:
    """Everything collected during a single-pass ModelSpace scan."""
    room_texts: list[RoomText] = field(default_factory=list)
    polygons: list[RoomPolygon] = field(default_factory=list)
    total_entities: int = 0
    existing_annotation_room_ids: set[str] = field(default_factory=set)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def scan_drawing(
    dwg_path: str,
    log_fn: Callable[[str], None] | None = None,
) -> ScanResult:
    """Open a DWG and scan ModelSpace for room texts and polygons.

    Parameters
    ----------
    dwg_path : str
        Absolute path to the DWG file.
    log_fn : callable, optional
        Accepts a single string for progress logging.

    Returns
    -------
    ScanResult
        Contains room_texts, polygons, total_entities, and
        existing_annotation_room_ids (for dedup).
    """
    _log(log_fn, "Connecting to AutoCAD...")
    acad = _get_acad_instance()

    _log(log_fn, f"Opening drawing: {os.path.basename(dwg_path)}")
    doc = _open_document(acad, dwg_path, read_only=False)

    # Wait for document to fully load
    model_space = _get_model_space(doc, log_fn)

    result = _scan_model_space(model_space, log_fn)

    _log(log_fn, f"  Room identifiers found : {len(result.room_texts)}")
    _log(log_fn, f"  Polygon candidates     : {len(result.polygons)}")
    if result.existing_annotation_room_ids:
        _log(log_fn, f"  Existing annotations   : {len(result.existing_annotation_room_ids)}")

    return result


# ---------------------------------------------------------------------------
# AutoCAD connection helpers
# ---------------------------------------------------------------------------

def _get_acad_instance():
    """Get or launch the AutoCAD COM application."""
    try:
        return win32com.client.Dispatch("AutoCAD.Application")
    except Exception as exc:
        raise AutoCADError(
            "Could not connect to AutoCAD. "
            "Please ensure AutoCAD is running.\n"
            f"Detail: {exc}"
        ) from exc


def _open_document(acad, dwg_path: str, read_only: bool = False):
    """Open a DWG and return the Document COM object."""
    abs_path = os.path.abspath(dwg_path)

    if not os.path.exists(abs_path):
        raise AutoCADError(
            f"Drawing file not found:\n{abs_path}\n\n"
            "Please verify the file path and try again."
        )

    # Check if already open
    existing = _find_open_document(acad, abs_path)
    if existing is not None:
        return existing

    try:
        return acad.Documents.Open(abs_path, read_only)
    except Exception as exc:
        raise AutoCADError(
            f"Failed to open drawing:\n{abs_path}\n\n"
            f"Error: {exc}\n\n"
            "Possible causes:\n"
            "  - File is locked or in use\n"
            "  - AutoCAD doesn't have read permission\n"
            "  - File is corrupted\n"
            "  - AutoCAD version incompatibility"
        ) from exc


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


def _get_model_space(doc, log_fn, max_retries: int = 3):
    """Access ModelSpace with retry logic for slow-loading documents."""
    for attempt in range(max_retries):
        try:
            return doc.ModelSpace
        except Exception as exc:
            if attempt < max_retries - 1:
                _log(log_fn, f"  Waiting for document to load (attempt {attempt + 2}/{max_retries})...")
                time.sleep(1)
            else:
                raise AutoCADError(
                    f"Failed to access ModelSpace after {max_retries} attempts.\n"
                    f"The document may be corrupted or unsupported.\n"
                    f"Detail: {exc}"
                ) from exc


# ---------------------------------------------------------------------------
# Single-pass ModelSpace scanner
# ---------------------------------------------------------------------------

_TEXT_TYPES = {"AcDbText", "AcDbMText"}
_POLY_TYPES = {"AcDbPolyline", "AcDb2dPolyline"}


def _scan_model_space(model_space, log_fn) -> ScanResult:
    """Iterate ModelSpace once, collecting texts + polygons + existing annotations."""
    total = model_space.Count
    _log(log_fn, f"  Scanning {total} model-space entities...")

    result = ScanResult(total_entities=total)
    progress = SCAN_PROGRESS_INTERVAL

    for i in range(total):
        if i > 0 and i % progress == 0:
            _log(log_fn, f"    ...scanned {i}/{total}")

        try:
            entity = model_space.Item(i)
            etype = entity.EntityName
        except Exception:
            continue

        # --- TEXT / MTEXT ---
        if etype in _TEXT_TYPES:
            _process_text_entity(entity, etype, result)

        # --- LWPOLYLINE / 2dPolyline ---
        elif etype in _POLY_TYPES:
            _process_polygon_entity(entity, etype, result)

    _log(log_fn, f"    ...scan complete ({total} entities)")
    return result


def _process_text_entity(entity, etype: str, result: ScanResult) -> None:
    """Extract properties from a TEXT/MTEXT entity and add to result."""
    try:
        text_val = str(entity.TextString).strip()
    except Exception:
        return

    # Check for existing annotations (dedup detection)
    try:
        layer = str(entity.Layer)
    except Exception:
        layer = ""

    if layer == OUTPUT_LAYER and etype == "AcDbMText":
        # This is an annotation we previously inserted — record for dedup
        _record_existing_annotation(entity, result)
        return

    if not is_room_identifier(text_val):
        return

    try:
        pos = _read_position(entity, etype)
        height = _read_height(entity, etype)
        style = _read_style(entity)
        handle = entity.Handle
    except Exception:
        return

    result.room_texts.append(RoomText(
        handle=str(handle),
        entity_type=etype,
        text=text_val,
        normalized_text=text_val.strip().lower(),
        position=pos,
        layer=layer,
        text_height=height,
        text_style=style,
    ))


def _process_polygon_entity(entity, etype: str, result: ScanResult) -> None:
    """Extract properties from a polyline entity and add to result if valid."""
    try:
        closed = bool(entity.Closed)
    except Exception:
        return

    if not closed:
        return

    try:
        coords = list(entity.Coordinates)
        handle = entity.Handle
        layer = str(entity.Layer)
    except Exception:
        return

    # LWPOLYLINE coords are flat: [x1,y1, x2,y2, ...]
    vertices = _coords_to_vertices(coords)

    if not is_valid_room_polygon(vertices, closed):
        return

    from utils import polygon_area, polygon_centroid, polygon_bbox

    area = polygon_area(vertices)
    centroid = polygon_centroid(vertices)
    bbox = polygon_bbox(vertices)

    result.polygons.append(RoomPolygon(
        handle=str(handle),
        entity_type=etype,
        layer=layer,
        closed=True,
        vertices=vertices,
        area=area,
        centroid=centroid,
        bbox=bbox,
    ))


def _record_existing_annotation(entity, result: ScanResult) -> None:
    """Check if an MTEXT on OUTPUT_LAYER has our XData and record its room_id."""
    try:
        from metadata_utils import read_xdata
        meta = read_xdata(entity)
        if meta and meta.room_id:
            result.existing_annotation_room_ids.add(meta.room_id.strip().lower())
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Property readers (minimal COM calls per entity)
# ---------------------------------------------------------------------------

def _read_position(entity, etype: str) -> tuple[float, float, float]:
    if etype == "AcDbMText":
        pt = entity.InsertionPoint
    else:
        pt = entity.InsertionPoint
    return (float(pt[0]), float(pt[1]), float(pt[2]) if len(pt) > 2 else 0.0)


def _read_height(entity, etype: str) -> float:
    try:
        return float(entity.Height)
    except Exception:
        return DEFAULT_TEXT_HEIGHT


def _read_style(entity) -> str:
    try:
        return str(entity.StyleName)
    except Exception:
        return ""


def _coords_to_vertices(coords: list) -> list[tuple[float, float]]:
    """Convert a flat coordinate list [x1,y1,x2,y2,...] to [(x1,y1), ...]."""
    vertices = []
    for i in range(0, len(coords) - 1, 2):
        vertices.append((float(coords[i]), float(coords[i + 1])))
    return vertices


# ---------------------------------------------------------------------------
# Logging helper
# ---------------------------------------------------------------------------

def _log(fn, msg: str) -> None:
    if fn is not None:
        fn(msg)
