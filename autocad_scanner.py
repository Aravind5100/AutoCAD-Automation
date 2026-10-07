"""
autocad_scanner.py
------------------
Uses **ezdxf** to scan a DXF file and collect:

  1. Room identifier TEXT / MTEXT entities
  2. Closed polyline (room polygon) candidates
  3. Entities written by an earlier run of the tool (found by their XData),
     so the writer can replace them

The DXF file is produced from the original DWG by ``dwg_converter.py``.
All entity properties are cached into plain Python dataclasses.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Callable

import ezdxf
from ezdxf import bbox as ezdxf_bbox

from config import (
    DEFAULT_TEXT_HEIGHT,
    LEGACY_OUTLINE_LAYERS,
    SCAN_PROGRESS_INTERVAL,
    XDATA_APP_NAME,
)
from metadata_utils import read_xdata
from utils import (
    is_room_identifier,
    is_valid_room_polygon,
    normalize_room_id,
    polygon_area,
    polygon_bbox,
    polygon_centroid,
)


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------

class AutoCADError(Exception):
    """Raised for any unrecoverable file / scan error."""


# ---------------------------------------------------------------------------
# Scanned-entity dataclasses  (pure Python)
# ---------------------------------------------------------------------------

@dataclass
class RoomText:
    """Cached properties of a TEXT / MTEXT entity that is a room identifier."""
    handle: str = ""
    entity_type: str = ""           # TEXT | MTEXT
    text: str = ""
    normalized_text: str = ""
    position: tuple[float, float, float] = (0.0, 0.0, 0.0)
    layer: str = ""
    text_height: float = DEFAULT_TEXT_HEIGHT
    text_style: str = ""
    # (min_x, min_y, max_x, max_y) of the whole label, or None if it could not be measured
    label_bbox: tuple[float, float, float, float] | None = None


@dataclass
class RoomPolygon:
    """Cached properties of a closed polyline that may be a room boundary."""
    handle: str = ""
    entity_type: str = ""           # LWPOLYLINE | POLYLINE
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
    # Outline copies / key and detail labels from an earlier run (live entities of *doc*)
    previous_output: list = field(default_factory=list, repr=False, compare=False)
    unreadable_entities: int = 0    # TEXT/MTEXT/polylines that raised while reading
    # The parsed drawing, so the writer can reuse it instead of reading the file again
    doc: object = field(default=None, repr=False, compare=False)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def scan_drawing(
    dxf_path: str,
    log_fn: Callable[[str], None] | None = None,
) -> ScanResult:
    """Scan a DXF file for room texts and polygons using ezdxf.

    Parameters
    ----------
    dxf_path : str
        Absolute path to the DXF file.
    log_fn : callable, optional
        Accepts a single string for progress logging.

    Returns
    -------
    ScanResult
        Contains room_texts, polygons, total_entities, and
        existing_annotation_room_ids and previous_output (output of an
        earlier run, replaced by the writer).
    """
    abs_path = os.path.abspath(dxf_path)
    if not os.path.exists(abs_path):
        raise AutoCADError(f"DXF file not found:\n{abs_path}")

    _log(log_fn, f"Reading DXF: {os.path.basename(abs_path)}")
    try:
        doc = ezdxf.readfile(abs_path)
    except Exception as exc:
        raise AutoCADError(
            f"Failed to read DXF file:\n{abs_path}\n"
            f"Error: {exc}"
        ) from exc

    msp = doc.modelspace()
    entities = list(msp)
    total = len(entities)

    _log(log_fn, f"  Scanning {total} model-space entities...")
    result = ScanResult(total_entities=total, doc=doc)

    for i, entity in enumerate(entities):
        if i > 0 and i % SCAN_PROGRESS_INTERVAL == 0:
            _log(log_fn, f"    ...scanned {i}/{total}")

        etype = entity.dxftype()

        if etype in ("TEXT", "MTEXT"):
            _process_text_entity(entity, etype, result)

        elif etype in ("LWPOLYLINE", "POLYLINE"):
            _process_polygon_entity(entity, etype, result)

    _log(log_fn, f"    ...scan complete ({total} entities)")
    _log(log_fn, f"  Room identifiers found : {len(result.room_texts)}")
    _log(log_fn, f"  Polygon candidates     : {len(result.polygons)}")
    if result.previous_output:
        _log(log_fn, f"  Earlier run's output   : {len(result.previous_output)} entities "
                     f"({len(result.existing_annotation_room_ids)} rooms) -- will be replaced")
    if result.unreadable_entities:
        _log(log_fn, f"  WARNING: {result.unreadable_entities} text/polyline entities "
                     "could not be read and were skipped")

    return result


# ---------------------------------------------------------------------------
# Entity processors
# ---------------------------------------------------------------------------

def _process_text_entity(entity, etype: str, result: ScanResult) -> None:
    """Extract properties from a TEXT/MTEXT entity and add to result."""
    # Our own key / detail labels from an earlier run are not room labels
    if _record_existing_annotation(entity, result):
        return

    try:
        if etype == "MTEXT":
            text_val = _mtext_room_line(entity)
        else:
            text_val = str(entity.dxf.text).strip()
    except Exception:
        result.unreadable_entities += 1
        return

    layer = entity.dxf.layer if entity.dxf.hasattr("layer") else ""

    if not is_room_identifier(text_val):
        return

    try:
        if etype == "MTEXT":
            ins = entity.dxf.insert
        else:
            ins = entity.dxf.insert
        pos = (float(ins[0]), float(ins[1]),
               float(ins[2]) if len(ins) > 2 else 0.0)
    except Exception:
        pos = (0.0, 0.0, 0.0)

    # TEXT stores its size as "height", MTEXT as "char_height"
    height_attr = "char_height" if etype == "MTEXT" else "height"
    try:
        height = (float(entity.dxf.get(height_attr))
                  if entity.dxf.hasattr(height_attr) else DEFAULT_TEXT_HEIGHT)
    except Exception:
        height = DEFAULT_TEXT_HEIGHT

    try:
        style = entity.dxf.style if entity.dxf.hasattr("style") else ""
    except Exception:
        style = ""

    handle = entity.dxf.handle if entity.dxf.hasattr("handle") else ""

    result.room_texts.append(RoomText(
        handle=str(handle),
        entity_type=etype,
        text=text_val,
        normalized_text=text_val.strip().lower(),
        position=pos,
        layer=layer,
        text_height=height,
        text_style=style,
        label_bbox=_label_bbox(entity),
    ))


def _mtext_room_line(entity) -> str:
    """Return the line of a multi-line MTEXT label that holds the room number.

    Room labels often stack the number over other text (``022`` over the
    area ``170``, or ``OFFICE`` over ``101``): the first line that looks like
    a room identifier is used; otherwise the first line.
    """
    # plain_text() removes inline formatting codes and turns paragraph
    # breaks into newlines; \~ (non-breaking space) is left literal
    plain = entity.plain_text().replace("\\~", " ")
    lines = [" ".join(line.split()) for line in plain.splitlines()]
    lines = [line for line in lines if line]
    for line in lines:
        if is_room_identifier(line):
            return line
    return lines[0] if lines else ""


def _label_bbox(entity) -> tuple[float, float, float, float] | None:
    """Extent of the whole label (all lines), used to place the key tag under it."""
    try:
        box = ezdxf_bbox.extents([entity], fast=True)
        if not box.has_data:
            return None
        return (box.extmin.x, box.extmin.y, box.extmax.x, box.extmax.y)
    except Exception:
        return None


def _process_polygon_entity(entity, etype: str, result: ScanResult) -> None:
    """Extract properties from a polyline entity and add to result if valid."""
    try:
        closed = entity.is_closed
        # POLYLINE also covers 3D polylines and meshes; only 2D ones are rooms
        if etype == "POLYLINE" and not entity.is_2d_polyline:
            return
    except Exception:
        result.unreadable_entities += 1
        return

    layer = entity.dxf.layer if entity.dxf.hasattr("layer") else ""
    # Outlines from the old block-based versions are not room boundaries
    if layer in LEGACY_OUTLINE_LAYERS:
        return
    # A polygon carrying our XData is an outline copy from an earlier run:
    # record it (the writer replaces it) instead of scanning it as a room
    if _record_existing_annotation(entity, result):
        return

    if not closed:
        return

    try:
        if etype == "LWPOLYLINE":
            vertices = [(float(p[0]), float(p[1])) for p in entity.get_points(format="xy")]
        else:
            # POLYLINE (2D) entity — vertices have .dxf.location (Vec3)
            vertices = [(float(v.dxf.location.x), float(v.dxf.location.y))
                        for v in entity.vertices]
    except Exception:
        result.unreadable_entities += 1
        return

    handle = entity.dxf.handle if entity.dxf.hasattr("handle") else ""

    if not is_valid_room_polygon(vertices, closed):
        return

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


def _record_existing_annotation(entity, result: ScanResult) -> bool:
    """If *entity* carries our XData, record it and its room_id and return True."""
    meta = read_xdata(entity)
    if meta is None:
        return False
    result.previous_output.append(entity)
    room_id = normalize_room_id(meta.room_id)
    if room_id:
        result.existing_annotation_room_ids.add(room_id)
    return True


# ---------------------------------------------------------------------------
# Logging helper
# ---------------------------------------------------------------------------

def _log(fn, msg: str) -> None:
    if fn is not None:
        fn(msg)
