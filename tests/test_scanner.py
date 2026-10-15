"""
test_scanner.py
---------------
Reading room labels, room polygons and existing annotations from a DXF.
"""

import unittest

import ezdxf

from autocad_scanner import AutoCADError, scan_drawing
from metadata_utils import AnnotationMetadata, register_xdata_app, write_xdata
from tests.helpers import TempDirTestCase, make_plan


class TestLabelsAndPolygons(TempDirTestCase):

    def test_modern_plan(self):
        scan = scan_drawing(make_plan(self.path("0132_A.dxf")))
        labels = [(t.text, t.entity_type, t.text_height) for t in scan.room_texts]
        # MTEXT is read via plain_text() (B8) and sized from char_height
        self.assertEqual(labels, [("101", "MTEXT", 4.0), ("102", "MTEXT", 6.0),
                                  ("103", "TEXT", 5.0)])
        self.assertEqual(len(scan.polygons), 4)
        self.assertEqual({p.entity_type for p in scan.polygons}, {"LWPOLYLINE"})
        self.assertEqual(scan.unreadable_entities, 0)

    def test_r12_plan_still_supported(self):
        scan = scan_drawing(make_plan(self.path("0132_R12.dxf"), version="R12"))
        self.assertEqual([t.text for t in scan.room_texts], ["101", "102", "103"])
        self.assertEqual({p.entity_type for p in scan.polygons}, {"POLYLINE"})

    def test_non_room_geometry_ignored(self):
        doc = ezdxf.new("R2018")
        msp = doc.modelspace()
        msp.add_polyline3d([(0, 0, 0), (50, 0, 5), (50, 50, 0)], close=True)   # 3D
        msp.add_lwpolyline([(0, 0), (10, 0), (10, 10)], close=False)            # open
        msp.add_lwpolyline([(0, 0), (0.5, 0), (0.5, 0.5)], close=True)         # tiny
        msp.add_lwpolyline([(0, 0), (9, 0), (9, 9), (0, 9)], close=True,
                           dxfattribs={"layer": "ROOM_BLOCK_OUTLINE"})         # our outline
        msp.add_text("TITLE SHEET", dxfattribs={"insert": (0, 0)})
        doc.saveas(self.path("x.dxf"))
        scan = scan_drawing(self.path("x.dxf"))
        self.assertEqual(scan.polygons, [])
        self.assertEqual(scan.room_texts, [])

    def test_multiline_mtext_uses_room_number_line(self):
        doc = ezdxf.new("R2018")
        msp = doc.modelspace()
        msp.add_mtext("022\\P170", dxfattribs={"insert": (0, 0), "char_height": 5})
        msp.add_mtext("OFFICE\\P103", dxfattribs={"insert": (0, 50), "char_height": 5})
        msp.add_mtext("{\\fArial|b0;017BA}\\P40", dxfattribs={"insert": (0, 90)})
        doc.saveas(self.path("m.dxf"))
        scan = scan_drawing(self.path("m.dxf"))
        self.assertEqual([t.text for t in scan.room_texts], ["022", "103", "017BA"])
        box = scan.room_texts[0].label_bbox
        self.assertLess(box[1], -5)          # two lines tall: bottom is well below the insert

    def test_missing_file(self):
        with self.assertRaises(AutoCADError):
            scan_drawing(self.path("nope.dxf"))


class TestExistingRoomLayers(TempDirTestCase):
    """Duplicate prevention input: room-layer copies from a previous run."""

    def test_copies_recorded_and_not_treated_as_rooms(self):
        doc = ezdxf.new("R2018")
        msp = doc.modelspace()
        register_xdata_app(doc)
        square = [(0, 0), (100, 0), (100, 100), (0, 100)]
        msp.add_lwpolyline(square, close=True)                       # the real room
        copy = msp.add_lwpolyline(square, close=True, dxfattribs={"layer": "0132-01-101"})
        write_xdata(copy, AnnotationMetadata(room_id="101", polygon_handle="AB"))
        # old block-based output is no longer treated as an existing annotation
        doc.blocks.new("ROOM_BLOCK_102")
        ins = msp.add_blockref("ROOM_BLOCK_102", (0, 0), dxfattribs={"layer": "ROOM_DATA"})
        write_xdata(ins, AnnotationMetadata(room_id="102"))
        doc.saveas(self.path("a.dxf"))

        scan = scan_drawing(self.path("a.dxf"))
        self.assertEqual(scan.existing_annotation_room_ids, {"101"})
        self.assertEqual(len(scan.polygons), 1)


if __name__ == "__main__":
    unittest.main()
