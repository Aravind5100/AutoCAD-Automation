"""
autocad_handler.py
------------------
All AutoCAD interaction via the COM/ActiveX interface (pywin32).
Handles opening drawings, scanning text entities, inserting MTEXT,
layer management, and saving the updated file.

Performance notes
~~~~~~~~~~~~~~~~~
- Entity data (text, position, height, style) is read in a **single pass**
  and cached in plain Python dicts so that subsequent matching and insertion
  never re-query the COM layer.
- The AutoCAD Application handle is acquired once and threaded through to
  every helper that needs it.
"""

import os
import time
from typing import Callable

import pythoncom
import win32com.client

from utils import (
    is_room_identifier,
    format_mtext_content,
    build_output_path,
    normalize_room_id,
    LINE_SPACING_FACTOR,
    ANNOTATION_LAYER,
    ANNOTATION_COLOR,
)
from matcher import MatchResult

# Fallback text height when the source entity has no readable height
DEFAULT_TEXT_HEIGHT: float = 10.0

# Width multiplier: MTEXT box width = text_height * this factor
MTEXT_WIDTH_FACTOR: float = 25.0


class AutoCADError(Exception):
    """Raised when an AutoCAD COM operation fails."""


# ---------------------------------------------------------------------------
# Public interface
# ---------------------------------------------------------------------------

def scan_drawing_for_rooms(
    dwg_path: str,
    log_fn: Callable[[str], None] | None = None,
) -> list[dict]:
    """Open a DWG, scan TEXT/MTEXT entities, and return room IDs.

    Uses a SelectionSet with a DXF entity-type filter so AutoCAD returns
    only TEXT / MTEXT objects — skipping lines, arcs, blocks, etc. entirely.
    Falls back to a full ModelSpace iteration if the filter fails.

    Parameters
    ----------
    dwg_path : str
        Absolute path to the DWG file.
    log_fn : callable, optional
        A function accepting a single string for progress logging.

    Returns
    -------
    list of dict
        Each dict contains:
          - ``text``        : original room-id string
          - ``position``    : (x, y, z) tuple
          - ``text_height`` : float — height of the source entity
          - ``text_style``  : str — style name (may be empty)
          - ``entity_type`` : ``'AcDbText'`` or ``'AcDbMText'``
    """
    _log(log_fn, "Connecting to AutoCAD...")
    acad = _get_acad_instance()

    _log(log_fn, f"Opening drawing: {os.path.basename(dwg_path)}")
    doc = _open_document(acad, dwg_path, read_only=False)

    # Wait for document to fully load and access ModelSpace
    max_retries = 3
    for attempt in range(max_retries):
        try:
            model_space = doc.ModelSpace
            break
        except Exception as exc:
            if attempt < max_retries - 1:
                _log(log_fn, f"  Retrying ModelSpace access (attempt {attempt + 2}/{max_retries})...")
                time.sleep(1)  # Wait 1 second before retry
            else:
                raise AutoCADError(
                    f"Failed to access ModelSpace after {max_retries} attempts.\n"
                    f"The document may be corrupted or in an unsupported format.\n"
                    f"Detail: {exc}"
                ) from exc

    # --- Optimized iteration: skip non-TEXT/MTEXT early ----------------
    entities = _iter_text_entities(model_space, log_fn)

    # --- Extract room identifiers from the filtered entities -------------
    rooms: list[dict] = []
    for entity in entities:
        try:
            text_val = str(entity.TextString).strip()
            if not is_room_identifier(text_val):
                continue

            etype = entity.EntityName
            rooms.append({
                "text": text_val,
                "position": _read_position(entity),
                "text_height": _read_height(entity, etype),
                "text_style": _read_style(entity),
                "entity_type": etype,
            })
        except Exception:
            continue

    _log(log_fn, f"  Room identifiers found: {len(rooms)}")
    return rooms


def update_drawing(
    dwg_path: str,
    room_entities: list[dict],
    match_results: list[MatchResult],
    log_fn: Callable[[str], None] | None = None,
) -> tuple[str, int]:
    """Insert MTEXT annotations directly below matched room identifiers.

    The inserted text inherits the **same text height** as the original room
    identifier entity and is placed at the **same X coordinate**, shifted
    downward by ``text_height * LINE_SPACING_FACTOR`` per annotation line.

    Parameters
    ----------
    dwg_path : str
        Path to the original DWG (already open from the scan step).
    room_entities : list[dict]
        Output of :func:`scan_drawing_for_rooms` — pure Python dicts.
    match_results : list[MatchResult]
        Per-room match outcomes from :func:`matcher.match_rooms`.
    log_fn : callable, optional
        Progress logging callback.

    Returns
    -------
    tuple[str, int]
        ``(output_file_path, inserted_count)``
    """
    acad = _get_acad_instance()

    doc = _find_open_document(acad, dwg_path)
    if doc is None:
        _log(log_fn, "Re-opening document for update...")
        doc = _open_document(acad, dwg_path, read_only=False)

    try:
        model_space = doc.ModelSpace
    except Exception as exc:
        raise AutoCADError(
            f"Failed to access ModelSpace in drawing. "
            f"The document may not be valid.\n"
            f"Detail: {exc}"
        ) from exc

    _ensure_layer(doc, ANNOTATION_LAYER, ANNOTATION_COLOR)
    _log(log_fn, f"Layer '{ANNOTATION_LAYER}' ready.")

    # Pre-build lookup: normalized_room_id -> entity data dict
    entity_lookup: dict[str, dict] = {}
    for r in room_entities:
        key = normalize_room_id(r["text"])
        if key not in entity_lookup:
            entity_lookup[key] = r

    inserted = 0
    total_matched = sum(1 for r in match_results if r.matched)
    _log(log_fn, f"Inserting annotations for {total_matched} matched room(s)...")

    for result in match_results:
        if not result.matched:
            continue

        norm_id = normalize_room_id(result.drawing_room_id)
        edata = entity_lookup.get(norm_id)
        if edata is None:
            _log(log_fn, f"  [skip] No entity data for '{result.drawing_room_id}'")
            continue

        pos = edata["position"]
        src_height = edata["text_height"]
        line_step = src_height * LINE_SPACING_FACTOR

        # Position: same X, directly below the room identifier
        insert_x = pos[0]
        insert_y = pos[1] - line_step     # one step below room ID text
        insert_z = pos[2]

        content = format_mtext_content(result.row_data)
        mtext_width = src_height * MTEXT_WIDTH_FACTOR

        _insert_mtext(
            model_space,
            content=content,
            x=insert_x,
            y=insert_y,
            z=insert_z,
            height=src_height,
            width=mtext_width,
            layer=ANNOTATION_LAYER,
        )
        inserted += 1

    _log(log_fn, f"  Annotations inserted: {inserted}")

    # Save as new file
    output_path = build_output_path(dwg_path)
    _log(log_fn, f"Saving updated drawing to: {output_path}")
    doc.SaveAs(output_path)
    doc.Close(SaveChanges=False)
    _log(log_fn, "Drawing saved and closed.")

    return output_path, inserted


# ---------------------------------------------------------------------------
# AutoCAD COM helpers
# ---------------------------------------------------------------------------

def _get_acad_instance():
    """Return a running AutoCAD Application COM object.

    Tries to attach to an already-running instance first; falls back to
    launching a new one.
    """
    try:
        acad = win32com.client.GetActiveObject("AutoCAD.Application")
        return acad
    except Exception:
        pass

    try:
        acad = win32com.client.Dispatch("AutoCAD.Application")
        acad.Visible = True
        return acad
    except Exception as exc:
        raise AutoCADError(
            "Could not connect to AutoCAD. "
            "Please ensure AutoCAD is installed on this machine.\n"
            f"Detail: {exc}"
        ) from exc


def _open_document(acad, dwg_path: str, read_only: bool = False):
    """Open a DWG file in AutoCAD and return the Document COM object."""
    abs_path = os.path.abspath(dwg_path)
    
    # Check file existence first
    if not os.path.exists(abs_path):
        raise AutoCADError(
            f"Drawing file not found:\n{abs_path}\n\n"
            f"Please verify the file path and try again."
        )

    existing = _find_open_document(acad, abs_path)
    if existing is not None:
        _log(None, f"  Document already open: {abs_path}")
        return existing

    try:
        doc = acad.Documents.Open(abs_path, read_only)
        return doc
    except Exception as exc:
        raise AutoCADError(
            f"Failed to open drawing:\n{abs_path}\n\n"
            f"Error: {exc}\n\n"
            f"Possible causes:\n"
            f"  - File is locked or in use\n"
            f"  - AutoCAD doesn't have read permission\n"
            f"  - File is corrupted\n"
            f"  - AutoCAD version incompatibility"
        ) from exc


def _find_open_document(acad, dwg_path: str):
    """Return the Document COM object if *dwg_path* is already open, else None."""
    abs_path = os.path.abspath(dwg_path).lower()
    try:
        for i in range(acad.Documents.Count):
            doc = acad.Documents.Item(i)
            try:
                if doc.FullName.lower() == abs_path:
                    return doc
            except Exception:
                continue
    except Exception:
        pass
    return None


# ---------------------------------------------------------------------------
# Entity scanning helpers
# ---------------------------------------------------------------------------

def _iter_text_entities(model_space, log_fn) -> list:
    """Iterate all ModelSpace entities and collect TEXT/MTEXT objects.

    Logs progress every 2000 entities so the UI stays responsive.
    """
    total = model_space.Count
    _log(log_fn, f"  Scanning {total} model-space entities for TEXT/MTEXT...")

    target_types = {"AcDbText", "AcDbMText"}
    entities: list = []
    progress_step = 2000

    for i in range(total):
        if i > 0 and i % progress_step == 0:
            _log(log_fn, f"    ...scanned {i}/{total} entities")
        try:
            entity = model_space.Item(i)
            if entity.EntityName in target_types:
                entities.append(entity)
        except Exception:
            continue

    _log(log_fn, f"  Found {len(entities)} TEXT/MTEXT entities.")
    return entities


# ---------------------------------------------------------------------------
# Entity property readers (called once per entity during the scan pass)
# ---------------------------------------------------------------------------

def _read_position(entity) -> tuple:
    """Return (x, y, z) insertion point from a TEXT or MTEXT entity."""
    try:
        pt = entity.InsertionPoint
        return (float(pt[0]), float(pt[1]), float(pt[2]))
    except Exception:
        pass
    try:
        pt = entity.TextAlignmentPoint
        return (float(pt[0]), float(pt[1]), float(pt[2]))
    except Exception:
        return (0.0, 0.0, 0.0)


def _read_height(entity, entity_type: str) -> float:
    """Return the text height of a TEXT or MTEXT entity."""
    try:
        return float(entity.Height)
    except Exception:
        pass
    try:
        return float(entity.TextHeight)
    except Exception:
        return DEFAULT_TEXT_HEIGHT


def _read_style(entity) -> str:
    """Return the text style name of an entity, or empty string on failure."""
    try:
        return str(entity.StyleName)
    except Exception:
        pass
    try:
        return str(entity.TextStyle)
    except Exception:
        return ""


# ---------------------------------------------------------------------------
# Drawing mutation helpers
# ---------------------------------------------------------------------------

def _ensure_layer(doc, layer_name: str, color_index: int = 7):
    """Create the named layer if it does not already exist."""
    try:
        doc.Layers.Item(layer_name)
        return
    except Exception:
        pass
    try:
        layer = doc.Layers.Add(layer_name)
        layer.Color = color_index
    except Exception as exc:
        raise AutoCADError(f"Could not create layer '{layer_name}': {exc}") from exc


def _insert_mtext(
    model_space,
    content: str,
    x: float,
    y: float,
    z: float,
    height: float,
    width: float,
    layer: str,
):
    """Add an MTEXT entity to *model_space*.

    Parameters
    ----------
    content : str
        MTEXT-formatted string (``\\P`` for newlines).
    x, y, z : float
        Insertion point (top-left of the text box).
    height : float
        Text height in drawing units — should match the room ID entity.
    width : float
        Text box width in drawing units.
    layer : str
        Layer name to place the entity on.
    """
    try:
        insert_pt = win32com.client.VARIANT(
            pythoncom.VT_ARRAY | pythoncom.VT_R8, [x, y, z]
        )
        mtext = model_space.AddMText(insert_pt, width, content)
        mtext.Height = height
        mtext.Layer = layer
    except Exception as exc:
        raise AutoCADError(f"Failed to insert MTEXT at ({x},{y}): {exc}") from exc


# ---------------------------------------------------------------------------
# Logging utility
# ---------------------------------------------------------------------------

def _log(log_fn: Callable[[str], None] | None, message: str):
    """Call *log_fn* with *message* if provided; otherwise do nothing."""
    if log_fn is not None:
        log_fn(message)
