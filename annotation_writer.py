"""
annotation_writer.py
--------------------
Writes the **room layers** into a DXF file using **ezdxf**, for ArcGIS.

Every matched room gets, each on its own layer (names editable in the app):
  a. outlines layer (default ``ROOM_OUTLINES``) -- a copy of the room's
     boundary polygon. The original polygon and its layer are left untouched.
  b. keys layer (default ``ROOM_KEYS``) -- a text label with the room key
     ``<Building>-<Floor>-<Room>`` (e.g. ``0132-01-101``, values as-is from the
     matched spreadsheet row), next to the room label, inside the room where
     it fits.
  c. details layer (default ``ROOM_DETAILS``, only when the user picked detail
     columns) -- one text label per picked column (e.g. Room Name), stacked
     under the key label.
All carry XData linking them to the source polygon and room label (also used
to skip rooms that already have a key on a re-run).

In ArcGIS the outlines layer gives the room polygons and the keys layer the
key annotations; a spatial join puts each key on the polygon that contains it.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Callable, Sequence

import ezdxf

from config import (
    DEFAULT_TEXT_HEIGHT,
    ROOM_DETAIL_LAYER_COLOR,
    ROOM_DETAIL_LAYER_DEFAULT,
    ROOM_KEY_LAYER_COLOR,
    ROOM_KEY_LAYER_DEFAULT,
    ROOM_OUTLINE_LAYER_COLOR,
    ROOM_OUTLINE_LAYER_DEFAULT,
    ROOM_TAG_GAP_FACTOR,
)
from metadata_utils import DETAIL, KEY, OUTLINE, AnnotationMetadata, register_xdata_app, write_xdata
from utils import build_room_key, normalize_room_id, point_in_polygon, polygon_centroid

_LIST_LIMIT = 10    # max room IDs listed per warning in the log
_TEXT_WIDTH_FACTOR = 0.7    # estimated character width, in text heights
_TAG_SCALES = (1.0, 0.75, 0.5)    # key label sizes tried, relative to the room label


# ---------------------------------------------------------------------------
# Output layers
# ---------------------------------------------------------------------------

@dataclass
class OutputLayers:
    """Names of the three layers the tool writes."""
    outlines: str = ROOM_OUTLINE_LAYER_DEFAULT
    keys: str = ROOM_KEY_LAYER_DEFAULT
    details: str = ROOM_DETAIL_LAYER_DEFAULT


# ---------------------------------------------------------------------------
# Per-room outcome (for results tables)
# ---------------------------------------------------------------------------

CREATED, SKIPPED, FAILED = "created", "skipped", "failed"


@dataclass
class RoomOutcome:
    """What happened to one matched room."""
    room_id: str
    key: str = ""                   # the Building-Floor-Room key, if one was built
    status: str = CREATED           # CREATED | SKIPPED | FAILED
    note: str = ""                  # reason for a skip/failure, or what to check
    needs_check: bool = False       # created, but worth a look (nearest link, label outside...)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def write_room_layers(
    drawing,
    matches: list,
    room_texts: list,
    building_col: str,
    floor_col: str,
    room_col: str,
    building_id: str,
    existing_annotation_ids: set[str],
    log_fn: Callable[[str], None] | None = None,
    outcomes: list | None = None,
    layers: OutputLayers | None = None,
    detail_cols: Sequence[str] = (),
) -> tuple[ezdxf.document.Drawing, int]:
    """Write each matched room's outline copy, key label and detail labels.

    Parameters
    ----------
    drawing : ezdxf.document.Drawing or str
        The drawing already read by the scanner (``ScanResult.doc``), or a
        path to the DXF file.
    matches : list[RoomMatch]
        From polygon_matcher.match_rooms; ``row_data`` must contain
        *building_col*, *floor_col*, *room_col* and every *detail_cols* column.
    room_texts : list[RoomText]
        Scanned room labels (position, height and extent of each label).
    building_col, floor_col, room_col : str
        Spreadsheet columns that make up the room key.
    building_id : str
        Building identifier (from the filename) for metadata.
    existing_annotation_ids : set[str]
        Normalised room IDs that already have a key in the drawing (for dedup).
    log_fn : callable, optional
    outcomes : list, optional
        If given, one :class:`RoomOutcome` per matched room is appended.
    layers : OutputLayers, optional
        Layer names for outline copies, key labels and detail labels.
    detail_cols : sequence of str
        Spreadsheet columns whose values are written on the details layer
        (empty values are left out). Nothing goes on that layer when empty.

    Returns
    -------
    (annotated_doc, created_count)
        The annotated in-memory drawing; the caller saves or converts it.
    """
    if isinstance(drawing, str):
        abs_path = os.path.abspath(drawing)
        _log(log_fn, f"Opening DXF for room layers: {os.path.basename(abs_path)}")
        try:
            doc = ezdxf.readfile(abs_path)
        except Exception as exc:
            raise RuntimeError(f"Failed to read DXF file:\n{abs_path}\nError: {exc}") from exc
    else:
        doc = drawing

    msp = doc.modelspace()
    register_xdata_app(doc)
    layers = layers or OutputLayers()
    detail_cols = list(detail_cols)
    _ensure_layer(doc, layers.outlines, ROOM_OUTLINE_LAYER_COLOR)
    _ensure_layer(doc, layers.keys, ROOM_KEY_LAYER_COLOR)
    if detail_cols:
        _ensure_layer(doc, layers.details, ROOM_DETAIL_LAYER_COLOR)
    labels = {rt.handle: rt for rt in room_texts}

    created = 0
    already_done: list[str] = []
    no_polygon: list[str] = []
    missing_key: list[str] = []
    nearest: list[str] = []
    failed: list[str] = []
    rooms_by_polygon: dict[str, list[str]] = {}
    results: dict[str, RoomOutcome] = {}     # room_id -> outcome, in match order

    def outcome(room_id, **kw):
        results[room_id] = RoomOutcome(room_id=room_id, **kw)

    for match in matches:
        if not match.matched:
            continue

        row = match.row_data
        key = build_room_key(row.get(building_col), row.get(floor_col), row.get(room_col))

        if normalize_room_id(match.room_id) in existing_annotation_ids:
            already_done.append(match.room_id)
            outcome(match.room_id, key=key or "", status=SKIPPED,
                    note="already has a room key in the drawing")
            continue

        if len(match.polygon_vertices) < 3:
            no_polygon.append(match.room_id)
            outcome(match.room_id, key=key or "", status=SKIPPED,
                    note="no room boundary polygon found")
            continue

        if key is None:
            missing_key.append(match.room_id)
            outcome(match.room_id, status=SKIPPED,
                    note=f"empty {building_col} / {floor_col} / {room_col} value")
            continue

        details = [(col, str(row.get(col) or "").strip()) for col in detail_cols]
        details = [(col, value) for col, value in details if value]
        try:
            copy = _add_polygon(doc, msp, match.polygon_vertices, layers.outlines)
            texts, fits = _add_labels(msp, labels.get(match.text_handle), key,
                                      [value for _, value in details],
                                      match.polygon_vertices, layers)
            written = [(copy, OUTLINE, "")]
            if texts:
                written.append((texts[0], KEY, ""))
                written += [(t, DETAIL, col) for t, (col, _) in zip(texts[1:], details)]
            for entity, role, col in written:
                meta = AnnotationMetadata(
                    room_id=match.room_id,
                    polygon_handle=match.polygon_handle,
                    building_id=building_id,
                    text_handle=match.text_handle,
                    match_method=match.match_method,
                    annotation_type=role,
                    field=col,
                )
                if not write_xdata(entity, meta):
                    _log(log_fn, f"  WARNING: Could not attach metadata (XData) for {match.room_id}")
        except Exception as exc:
            failed.append(f"{match.room_id} ({exc})")
            outcome(match.room_id, key=key, status=FAILED, note=str(exc))
            continue

        created += 1
        rooms_by_polygon.setdefault(match.polygon_handle, []).append(match.room_id)
        notes = []
        if match.match_method == "nearest":
            nearest.append(match.room_id)
            notes.append("label is outside any polygon; linked to the nearest one")
        if texts and not fits:
            notes.append("key label does not fit inside the room" if len(texts) == 1
                         else "key / detail labels do not fit inside the room")
        outcome(match.room_id, key=key, note="; ".join(notes),
                needs_check=bool(notes))

    _log(log_fn, f"  Rooms written: {created} -- outline copies on {layers.outlines}, "
                 f"key labels on {layers.keys}"
                 + (f", {', '.join(detail_cols)} on {layers.details}" if detail_cols else ""))
    _log_list(log_fn, already_done, "rooms skipped -- already have a room key", warn=False)
    _log_list(log_fn, no_polygon, "rooms skipped -- no room boundary polygon found")
    _log_list(log_fn, missing_key,
              f"rooms skipped -- empty '{building_col}', '{floor_col}' or '{room_col}' value")
    _log_list(log_fn, failed, "rooms failed")
    _log_list(log_fn, nearest,
              "rooms linked to the NEAREST polygon (label outside any polygon) -- please check")
    shared = [r for r in rooms_by_polygon.values() if len(r) > 1]
    _log_list(log_fn, [", ".join(r) for r in shared],
              "polygons shared by more than one room label -- please check")
    for rooms in shared:
        for room_id in rooms:
            o = results[room_id]
            o.note = "; ".join(filter(None, [o.note, f"polygon shared with {', '.join(r for r in rooms if r != room_id)}"]))
            o.needs_check = True

    if outcomes is not None:
        outcomes.extend(results.values())
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


def _add_labels(msp, label, key: str, details: list[str],
                room: list[tuple[float, float]], layers: OutputLayers):
    """Write *key* (keys layer) and *details* (details layer, one line each)
    as a block of text lines near the room label, inside the room where possible.

    Returns (text_entities, fits) -- key first, then the details; *fits* is
    False when no spot kept every line inside the room polygon.

    Candidate spots, in order: under the whole room label, above it, centred
    in the room -- first at the room label's text height, then smaller (for
    small rooms). The first spot where every line fits inside the room
    polygon wins; otherwise the first full-size spot where the block at least
    starts inside; otherwise under the label. If the block with details never
    fits, the key is placed on its own that way and the details go under it.
    """
    if label is None:
        return [], True
    full_height = label.text_height or DEFAULT_TEXT_HEIGHT
    gap = full_height * ROOM_TAG_GAP_FACTOR
    if label.label_bbox is not None:
        left, bottom, _, top = label.label_bbox
    else:
        left, bottom = label.position[0], label.position[1]
        top = bottom + full_height
    cx, cy = polygon_centroid(room)

    def stack(count, height, x, block_top):
        """Insert points of *count* lines stacked down from (x, block_top)."""
        return [(x, block_top - (i + 1) * height - i * gap) for i in range(count)]

    def candidates(lines, height):
        widths = [height * _TEXT_WIDTH_FACTOR * len(t) for t in lines]    # estimated
        block = len(lines) * height + (len(lines) - 1) * gap
        width = max(widths)
        return widths, [
            stack(len(lines), height, left, bottom - gap),                # under the label
            stack(len(lines), height, left, top + gap + block),           # above the label
            stack(len(lines), height, cx - width / 2, cy + block / 2),    # centred in the room
        ]

    def fits(points, widths, height):
        return all(point_in_polygon(px, py, room)
                   for (x, y), w in zip(points, widths)
                   for px, py in ((x, y), (x + w, y), (x, y + height), (x + w, y + height)))

    def place(lines):
        """(insert points, height, fits) for *lines*."""
        for scale in _TAG_SCALES:
            height = full_height * scale
            widths, spots = candidates(lines, height)
            for points in spots:
                if fits(points, widths, height):
                    return points, height, True
        _, spots = candidates(lines, full_height)
        points = next((p for p in spots if point_in_polygon(*p[0], room)), spots[0])
        return points, full_height, False

    lines = [key] + details
    points, height, ok = place(lines)
    if not ok and details:
        (key_point,), height, _ = place([key])
        points = stack(len(lines), height, key_point[0], key_point[1] + height)
    texts = [_text(msp, t, height, p, layers.keys if i == 0 else layers.details)
             for i, (t, p) in enumerate(zip(lines, points))]
    return texts, ok


def _text(msp, text: str, height: float, insert: tuple[float, float], layer: str):
    return msp.add_text(text, height=height, dxfattribs={"layer": layer, "insert": insert})


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
