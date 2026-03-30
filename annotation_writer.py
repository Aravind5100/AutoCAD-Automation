"""
annotation_writer.py
--------------------
Inserts **attributed block** annotations into a DXF file using **ezdxf**
so that ArcGIS can read room data as structured field attributes.

Each matched room gets:
  a. A block definition with one ATTDEF per selected column.
  b. A block insert (INSERT) at the room text position.
  c. Attribute values populated from the spreadsheet.
  d. An outline LWPOLYLINE rectangle around the attributes.
  e. XData on the block insert for internal querying.

The public function signature is kept compatible with the UI pipeline.
"""

from __future__ import annotations

import os
from typing import Callable

import ezdxf
from ezdxf.math import Vec3

from config import (
    ANNOTATION_COLOR,
    ATTR_LINE_SPACING,
    ATTR_TEXT_HEIGHT_FACTOR,
    BLOCK_LAYER,
    BLOCK_OUTLINE_LAYER,
    BLOCK_PADDING,
    DEFAULT_TEXT_HEIGHT,
)
from metadata_utils import (
    AnnotationMetadata,
    normalize_block_name,
    register_xdata_app,
    write_xdata,
)
from utils import build_attribute_map, build_output_path


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def write_annotations(
    dxf_path: str,
    matches: list,
    room_texts: list,
    building_id: str,
    existing_annotation_ids: set[str],
    log_fn: Callable[[str], None] | None = None,
) -> tuple[str, int]:
    """Insert attributed block annotations and save the DXF.

    Parameters
    ----------
    dxf_path : str
        Path to the DXF file (produced by dwg_converter).
    matches : list[RoomMatch]
        From polygon_matcher.match_rooms.
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
    abs_path = os.path.abspath(dxf_path)
    _log(log_fn, f"Opening DXF for annotation: {os.path.basename(abs_path)}")

    try:
        doc = ezdxf.readfile(abs_path)
    except Exception as exc:
        raise RuntimeError(
            f"Failed to read DXF file:\n{abs_path}\nError: {exc}"
        ) from exc

    msp = doc.modelspace()

    _log(log_fn, "  Preparing layers and metadata registration...")
    _ensure_layer(doc, BLOCK_LAYER, ANNOTATION_COLOR)
    _ensure_layer(doc, BLOCK_OUTLINE_LAYER, ANNOTATION_COLOR)
    register_xdata_app(doc)

    # Build a quick lookup: normalised room_id -> RoomText
    text_lookup: dict[str, object] = {}
    for rt in room_texts:
        key = rt.text.strip().lower()
        if key not in text_lookup:
            text_lookup[key] = rt

    # Collect selected columns from the first matched entry
    selected_columns: list[str] = []
    for match in matches:
        if match.matched and match.row_data:
            selected_columns = list(match.row_data.keys())
            break

    if not selected_columns:
        _log(log_fn, "  WARNING: No matched rows with data to insert.")
        output_path = _build_dxf_output_path(dxf_path)
        return output_path, 0

    # Track created block definitions
    created_blocks: set[str] = set()

    inserted = 0
    skipped_dedup = 0

    for match in matches:
        if not match.matched or not match.row_data:
            continue

        norm_id = match.room_id.strip().lower()

        if norm_id in existing_annotation_ids:
            skipped_dedup += 1
            continue

        rt = text_lookup.get(norm_id)
        if rt is None:
            continue

        text_height = (rt.text_height or DEFAULT_TEXT_HEIGHT) * ATTR_TEXT_HEIGHT_FACTOR
        attr_map = build_attribute_map(selected_columns, match.row_data)
        if not attr_map:
            continue

        ins_x = rt.position[0]
        ins_y = rt.position[1] - (text_height * ATTR_LINE_SPACING)
        ins_z = rt.position[2] if len(rt.position) > 2 else 0.0

        block_name = normalize_block_name(match.room_id)

        try:
            # --- a. Block definition ---
            if block_name not in created_blocks:
                if block_name not in doc.blocks:
                    _create_block_def(
                        doc, block_name, ins_x, ins_y,
                        attr_map, text_height,
                    )
                created_blocks.add(block_name)

            # --- b. Block insert + c. Set attribute values ---
            block_ref = _insert_block_with_attribs(
                msp, doc, block_name, ins_x, ins_y, ins_z,
                attr_map,
            )

            # --- d. Outline (polygon shape or rectangle fallback) ---
            _draw_outline(
                msp, match.polygon_vertices, ins_x, ins_y, len(attr_map), text_height,
            )

            # --- e. XData ---
            meta = AnnotationMetadata(
                room_id=match.room_id,
                polygon_handle=match.polygon_handle,
                building_id=building_id,
                text_handle=match.text_handle,
                match_method=match.match_method,
            )
            write_xdata(block_ref, meta)

            inserted += 1

        except Exception as exc:
            _log(log_fn, f"  WARNING: Failed to insert block for {match.room_id}: {exc}")

    if skipped_dedup:
        _log(log_fn, f"  Skipped {skipped_dedup} rooms (annotations already exist)")

    # Return the in-memory DXF document (don't save to disk)
    # The caller will handle DXF->DWG conversion
    _log(log_fn, f"  Block annotations inserted: {inserted}")
    return doc, inserted


# ---------------------------------------------------------------------------
# Block definition (ezdxf)
# ---------------------------------------------------------------------------

def _create_block_def(
    doc, block_name: str,
    origin_x: float, origin_y: float,
    attr_map: list[tuple[str, str, str]],
    text_height: float,
) -> None:
    """Create a block definition with one ATTDEF per attribute."""
    block = doc.blocks.new(name=block_name)

    for i, (tag, prompt, default_val) in enumerate(attr_map):
        y_offset = -(i * text_height * ATTR_LINE_SPACING)
        block.add_attdef(
            tag=tag,
            insert=(0, y_offset, 0),
            dxfattribs={
                "height": text_height,
                "prompt": prompt,
                "layer": BLOCK_LAYER,
            },
        )


# ---------------------------------------------------------------------------
# Block insert + attribute population (ezdxf)
# ---------------------------------------------------------------------------

def _insert_block_with_attribs(
    msp, doc, block_name: str,
    x: float, y: float, z: float,
    attr_map: list[tuple[str, str, str]],
):
    """Insert a block reference and fill its attributes. Returns the INSERT entity."""
    block_ref = msp.add_blockref(
        block_name,
        insert=(x, y, z),
        dxfattribs={"layer": BLOCK_LAYER},
    )

    # Build tag -> value map
    tag_to_value: dict[str, str] = {}
    for tag, _prompt, value in attr_map:
        tag_to_value[tag.upper()] = value

    # Add ATTRIB entities from the block's ATTDEFs
    block_def = doc.blocks.get(block_name)
    if block_def is not None:
        for attdef in block_def.query("ATTDEF"):
            tag = attdef.dxf.tag.upper()
            value = tag_to_value.get(tag, "")
            block_ref.add_attrib(
                tag=attdef.dxf.tag,
                text=value,
                insert=(
                    x + attdef.dxf.insert.x,
                    y + attdef.dxf.insert.y,
                    z,
                ),
                dxfattribs={
                    "height": attdef.dxf.height,
                    "layer": BLOCK_LAYER,
                },
            )

    return block_ref


# ---------------------------------------------------------------------------
# Outline rectangle (ezdxf)
# ---------------------------------------------------------------------------

def _draw_outline(
    msp,
    polygon_vertices: list[tuple[float, float]],
    x: float, y: float,
    num_fields: int,
    text_height: float,
) -> None:
    """Draw the room polygon as an outline. Falls back to rectangle if no polygon."""
    # If polygon vertices provided, draw the actual room shape
    if polygon_vertices and len(polygon_vertices) >= 3:
        points = [(vx, vy, 0) for vx, vy in polygon_vertices]
        try:
            msp.add_lwpolyline(
                points,
                close=True,
                dxfattribs={"layer": BLOCK_OUTLINE_LAYER},
            )
        except Exception:
            # Fallback to POLYLINE for older DXF versions
            msp.add_polyline2d(
                points,
                dxfattribs={"layer": BLOCK_OUTLINE_LAYER},
            ).close()
    else:
        # Fallback: draw a rectangle around the block attributes
        padding = BLOCK_PADDING * text_height
        estimated_width = text_height * 25.0

        x_min = x - padding
        x_max = x + estimated_width + padding
        y_max = y + text_height + padding
        y_min = y - (num_fields * text_height * ATTR_LINE_SPACING) - padding

        points = [
            (x_min, y_max, 0),
            (x_max, y_max, 0),
            (x_max, y_min, 0),
            (x_min, y_min, 0),
        ]
        try:
            msp.add_lwpolyline(
                points,
                close=True,
                dxfattribs={"layer": BLOCK_OUTLINE_LAYER},
            )
        except Exception:
            msp.add_polyline2d(
                points,
                dxfattribs={"layer": BLOCK_OUTLINE_LAYER},
            ).close()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _ensure_layer(doc, layer_name: str, color: int) -> None:
    """Create the layer if it doesn't exist."""
    try:
        if layer_name not in doc.layers:
            doc.layers.add(layer_name, color=color)
    except Exception:
        pass


def _build_dxf_output_path(dxf_path: str) -> str:
    """``plan.dxf`` -> ``plan_updated.dxf``"""
    base, ext = os.path.splitext(dxf_path)
    return f"{base}_updated{ext}"


# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

def _log(fn, msg: str) -> None:
    if fn is not None:
        fn(msg)
