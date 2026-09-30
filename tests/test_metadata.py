"""
test_metadata.py
----------------
ArcGIS-safe naming and XData round trip.
"""

import unittest

import ezdxf

from metadata_utils import (
    AnnotationMetadata,
    normalize_block_name,
    read_xdata,
    register_xdata_app,
    tag_from_column,
    write_xdata,
)


class TestNaming(unittest.TestCase):

    def test_block_names(self):
        self.assertEqual(normalize_block_name("101-A"), "ROOM_BLOCK_101_A")
        self.assertEqual(normalize_block_name(" b 201 "), "ROOM_BLOCK_B_201")
        self.assertLessEqual(len(normalize_block_name("9" * 400)), 255)

    def test_tags(self):
        self.assertEqual(tag_from_column("Occupied By"), "OCCUPIED_BY")
        self.assertEqual(tag_from_column("Sq.Ft."), "SQ_FT")
        self.assertLessEqual(len(tag_from_column("a very long column name " * 3)), 30)

    @unittest.expectedFailure
    def test_distinct_rooms_get_distinct_blocks_B12(self):
        """B12 (open): 101-A, 101 A and 101_A collide on one block name."""
        names = {normalize_block_name(r) for r in ("101-A", "101 A", "101_A")}
        self.assertEqual(len(names), 3)


class TestXData(unittest.TestCase):

    def test_round_trip(self):
        doc = ezdxf.new("R2018")
        register_xdata_app(doc)
        ref = doc.modelspace().add_line((0, 0), (1, 1))
        meta = AnnotationMetadata(room_id="101", polygon_handle="2D", building_id="0132",
                                  text_handle="3F", match_method="contains")
        self.assertTrue(write_xdata(ref, meta))
        self.assertEqual(read_xdata(ref), meta)

    def test_missing_xdata_reads_as_none(self):
        line = ezdxf.new("R2018").modelspace().add_line((0, 0), (1, 1))
        self.assertIsNone(read_xdata(line))


if __name__ == "__main__":
    unittest.main()
