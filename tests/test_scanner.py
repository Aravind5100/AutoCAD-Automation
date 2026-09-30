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

    def test_missing_file(self):
        with self.assertRaises(AutoCADError):
            scan_drawing(self.path("nope.dxf"))


class TestExistingAnnotations(TempDirTestCase):
    """Duplicate prevention input (B2 regression tests)."""

    def test_all_annotation_styles_detected(self):
        doc = ezdxf.new("R2018")
        msp = doc.modelspace()
        register_xdata_app(doc)
        # current style: block on ROOM_DATA with XData
        doc.blocks.new("ROOM_BLOCK_101")
        ins = msp.add_blockref("ROOM_BLOCK_101", (0, 0), dxfattribs={"layer": "ROOM_DATA"})
        write_xdata(ins, AnnotationMetadata(room_id="101", polygon_handle="AB"))
        # v1 style: MTEXT on ROOM_INFO_AI with XData
        mt = msp.add_mtext("Dept: Eng", dxfattribs={"layer": "ROOM_INFO_AI"})
        write_xdata(mt, AnnotationMetadata(room_id="102"))
        # XData stripped by another tool: ROOM_IDENTIFIER attribute fallback
        blk = doc.blocks.new("X")
        blk.add_attdef("ROOM_IDENTIFIER", (0, 0))
        ins2 = msp.add_blockref("X", (0, 0), dxfattribs={"layer": "ROOM_DATA"})
        ins2.add_attrib("ROOM_IDENTIFIER", " 103 ", (0, 0))
        # a block on another layer is not ours
        other = msp.add_blockref("ROOM_BLOCK_101", (0, 0), dxfattribs={"layer": "0"})
        write_xdata(other, AnnotationMetadata(room_id="999"))
        doc.saveas(self.path("a.dxf"))

        scan = scan_drawing(self.path("a.dxf"))
        self.assertEqual(scan.existing_annotation_room_ids, {"101", "102", "103"})


if __name__ == "__main__":
    unittest.main()
