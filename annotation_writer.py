"""
annotation_writer.py
--------------------
Inserts MTEXT annotations into AutoCAD, linked to room polygons via XData.

Workflow
~~~~~~~~
1. Re-acquire the already-open document (opened during scanning).
2. Ensure the output layer exists.
3. Register the XData application name.
4. For each matched room:
   a. Skip if an annotation already exists (dedup).
   b. Insert MTEXT directly below the room identifier text.
   c. Attach XData linking the annotation to its polygon handle.
5. Save as a new ``_updated.dwg`` file.
"""

from __future__ import annotations

import os
from typing import Callable

import pythoncom
import win32com.client

from config import (
    ANNOTATION_COLOR,
    DEFAULT_TEXT_HEIGHT,
    MTEXT_WIDTH_FACTOR,
    OUTPUT_LAYER,
    VERTICAL_SPACING_MULTIPLIER,
)
from metadata_utils import AnnotationMetadata, register_xdata_app, write_xdata
from utils import build_output_path, format_mtext_content


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def write_annotations(
    dwg_path: str,
    matches: list,
    room_texts: list,
    building_id: str,
    existing_annotation_ids: set[str],
    log_fn: Callable[[str], None] | None = None,
) -> tuple[str, int]:
    """Insert annotations for matched rooms and save a new DWG.

    Parameters
    ----------
    dwg_path : str
        Original DWG path (document should already be open).
    matches : list[RoomMatch]
        From polygon_matcher.match_rooms — only matched entries are written.
    room_texts : list[RoomText]
        All scanned room texts (used to look up position / height).
    building_id : str
        Building identifier for metadata.
    existing_annotation_ids : set[str]
        Normalised room IDs that already have annotations (for dedup).
    log_fn : callable, optional

    Returns
    -------
    (output_path, inserted_count)
    """
    _log(log_fn, "Connecting to AutoCAD for annotation writing...")
    acad = win32com.client.Dispatch("AutoCAD.Application")
    doc = _find_open_document(acad, dwg_path)

    if doc is None:
        raise RuntimeError(
            f"Drawing not found open in AutoCAD:\n{dwg_path}\n"
            "It may have been closed between scanning and writing."
        )

    model_space = doc.ModelSpace

    _log(log_fn, "  Preparing output layer and metadata registration...")
    _ensure_layer(doc, OUTPUT_LAYER, ANNOTATION_COLOR)
    register_xdata_app(doc)

    # Build a quick lookup: normalised room_id → RoomText
    text_lookup: dict[str, object] = {}
    for rt in room_texts:
        key = rt.text.strip().lower()
        if key not in text_lookup:
            text_lookup[key] = rt

    inserted = 0
    skipped_dedup = 0

    for match in matches:
        if not match.matched or not match.row_data:
            continue

        norm_id = match.room_id.strip().lower()

        # Deduplication: skip if annotation already exists
        if norm_id in existing_annotation_ids:
            skipped_dedup += 1
            continue

        rt = text_lookup.get(norm_id)
        if rt is None:
            continue

        # Build MTEXT content
        content = format_mtext_content(match.row_data)
        if not content:
            continue

        # Compute insertion point: same X, below room text by spacing
        text_height = rt.text_height or DEFAULT_TEXT_HEIGHT
        x = rt.position[0]
        y = rt.position[1] - (text_height * VERTICAL_SPACING_MULTIPLIER)
        z = rt.position[2] if len(rt.position) > 2 else 0.0

        try:
            mtext_entity = _insert_mtext(
                model_space, x, y, z, content, text_height,
            )

            # Attach XData linking annotation to polygon
            meta = AnnotationMetadata(
                room_id=match.room_id,
                polygon_handle=match.polygon_handle,
                building_id=building_id,
                text_handle=match.text_handle,
                match_method=match.match_method,
            )
            write_xdata(mtext_entity, meta)

            inserted += 1
        except Exception as exc:
            _log(log_fn, f"  WARNING: Failed to insert annotation for {match.room_id}: {exc}")

    if skipped_dedup:
        _log(log_fn, f"  Skipped {skipped_dedup} rooms (annotations already exist)")

    # Save as new file
    output_path = build_output_path(dwg_path)
    _log(log_fn, f"  Saving updated drawing: {os.path.basename(output_path)}")
    try:
        doc.SaveAs(output_path)
    except Exception as exc:
        _log(log_fn, f"  WARNING: SaveAs failed, trying Save: {exc}")
        try:
            doc.Save()
            output_path = dwg_path
        except Exception:
            pass

    _log(log_fn, f"  Annotations inserted: {inserted}")
    return output_path, inserted


# ---------------------------------------------------------------------------
# AutoCAD helpers
# ---------------------------------------------------------------------------

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


def _ensure_layer(doc, layer_name: str, color: int) -> None:
    """Create the annotation layer if it doesn't exist."""
    try:
        layer = doc.Layers.Add(layer_name)
        layer.color = color
    except Exception:
        pass  # layer already exists


def _insert_mtext(
    model_space, x: float, y: float, z: float,
    content: str, text_height: float,
):
    """Insert a single MTEXT entity and return the COM reference."""
    insertion = win32com.client.VARIANT(
        pythoncom.VT_ARRAY | pythoncom.VT_R8, [x, y, z],
    )
    width = text_height * MTEXT_WIDTH_FACTOR

    mtext = model_space.AddMText(insertion, width, content)
    mtext.Height = text_height
    mtext.Layer = OUTPUT_LAYER
    return mtext


# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

def _log(fn, msg: str) -> None:
    if fn is not None:
        fn(msg)
