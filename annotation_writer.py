"""
annotation_writer.py
--------------------
Writes **room layers** into a DXF file using **ezdxf**, for ArcGIS.

Each matched room gets:
  a. A layer named ``<Building>-<Floor>-<Room>`` (e.g. ``0132-01-101``), with
     the three values taken as-is from the matched spreadsheet row.
  b. A copy of the room's boundary polygon on that layer. The original
     polygon and its layer are left untouched.
  c. XData on the copy linking it to the source polygon and room label
     (also used to skip rooms that already have a layer on a re-run).

In ArcGIS each room polygon then carries its key in the Layer field, which
can be joined to the facilities spreadsheet.
"""

from __future__ import annotations

import os
from typing import Callable

import ezdxf

from config import ROOM_LAYER_COLOR
from metadata_utils import AnnotationMetadata, register_xdata_app, write_xdata
from utils import build_room_key, normalize_room_id

_LIST_LIMIT = 10    # max room IDs listed per warning in the log


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def write_room_layers(
    dxf_path: str,
    matches: list,
    building_col: str,
    floor_col: str,
    room_col: str,
    building_id: str,
    existing_annotation_ids: set[str],
    log_fn: Callable[[str], None] | None = None,
) -> tuple[ezdxf.document.Drawing, int]:
    """Copy each matched room's polygon onto its own ``Building-Floor-Room`` layer.

    Parameters
    ----------
    dxf_path : str
        Path to the DXF file (produced by dwg_converter).
    matches : list[RoomMatch]
        From polygon_matcher.match_rooms; ``row_data`` must contain
        *building_col*, *floor_col* and *room_col*.
    building_col, floor_col, room_col : str
        Spreadsheet columns that make up the layer name.
    building_id : str
        Building identifier (from the filename) for metadata.
    existing_annotation_ids : set[str]
        Normalised room IDs that already have a room layer (for dedup).
    log_fn : callable, optional

    Returns
    -------
    (annotated_doc, created_count)
        The annotated in-memory drawing; the caller saves or converts it.
    """
    abs_path = os.path.abspath(dxf_path)
    _log(log_fn, f"Opening DXF for room layers: {os.path.basename(abs_path)}")
    try:
        doc = ezdxf.readfile(abs_path)
    except Exception as exc:
        raise RuntimeError(f"Failed to read DXF file:\n{abs_path}\nError: {exc}") from exc

    msp = doc.modelspace()
    register_xdata_app(doc)

    created = 0
    already_done: list[str] = []
    no_polygon: list[str] = []
    missing_key: list[str] = []
    nearest: list[str] = []
    failed: list[str] = []
    rooms_by_polygon: dict[str, list[str]] = {}

    for match in matches:
        if not match.matched:
            continue

        if normalize_room_id(match.room_id) in existing_annotation_ids:
            already_done.append(match.room_id)
            continue

        if len(match.polygon_vertices) < 3:
            no_polygon.append(match.room_id)
            continue

        row = match.row_data
        layer_name = build_room_key(row.get(building_col), row.get(floor_col),
                                    row.get(room_col))
        if layer_name is None:
            missing_key.append(match.room_id)
            continue

        try:
            _ensure_layer(doc, layer_name, ROOM_LAYER_COLOR)
            copy = _add_polygon(doc, msp, match.polygon_vertices, layer_name)
            meta = AnnotationMetadata(
                room_id=match.room_id,
                polygon_handle=match.polygon_handle,
                building_id=building_id,
                text_handle=match.text_handle,
                match_method=match.match_method,
            )
            if not write_xdata(copy, meta):
                _log(log_fn, f"  WARNING: Could not attach metadata (XData) for {match.room_id}")
        except Exception as exc:
            failed.append(f"{match.room_id} ({exc})")
            continue

        created += 1
        rooms_by_polygon.setdefault(match.polygon_handle, []).append(match.room_id)
        if match.match_method == "nearest":
            nearest.append(match.room_id)

    _log(log_fn, f"  Room layers created: {created}")
    _log_list(log_fn, already_done, "rooms skipped -- a room layer already exists", warn=False)
    _log_list(log_fn, no_polygon, "rooms skipped -- no room boundary polygon found")
    _log_list(log_fn, missing_key,
              f"rooms skipped -- empty '{building_col}', '{floor_col}' or '{room_col}' value")
    _log_list(log_fn, failed, "rooms failed")
    _log_list(log_fn, nearest,
              "rooms linked to the NEAREST polygon (label outside any polygon) -- please check")
    shared = [f"{', '.join(r)}" for r in rooms_by_polygon.values() if len(r) > 1]
    _log_list(log_fn, shared, "polygons shared by more than one room label -- please check")

    return doc, created


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _add_polygon(doc, msp, vertices: list[tuple[float, float]], layer: str):
    """Add a closed copy of *vertices* on *layer*; LWPOLYLINE unless the DXF is R12."""
    attribs = {"layer": layer}
    if doc.dxfversion > "AC1009":
        return msp.add_lwpolyline(vertices, close=True, dxfattribs=attribs)
    return msp.add_polyline2d(vertices, close=True, dxfattribs=attribs)


def _ensure_layer(doc, layer_name: str, color: int) -> None:
    """Create the layer if it doesn't exist."""
    if layer_name not in doc.layers:
        doc.layers.add(layer_name, color=color)


def _log_list(log_fn, items: list[str], what: str, warn: bool = True) -> None:
    if not items:
        return
    shown = ", ".join(items[:_LIST_LIMIT])
    more = f" (+{len(items) - _LIST_LIMIT} more)" if len(items) > _LIST_LIMIT else ""
    prefix = "WARNING: " if warn else ""
    _log(log_fn, f"  {prefix}{len(items)} {what}: {shown}{more}")


# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

def _log(fn, msg: str) -> None:
    if fn is not None:
        fn(msg)
