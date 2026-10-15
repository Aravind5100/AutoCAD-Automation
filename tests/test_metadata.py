"""
test_metadata.py
----------------
XData round trip.
"""

import unittest

import ezdxf

from metadata_utils import (
    AnnotationMetadata,
    read_xdata,
    register_xdata_app,
    write_xdata,
)


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
