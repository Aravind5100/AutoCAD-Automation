"""
test_matcher.py
---------------
Label → polygon association and label → spreadsheet matching.
"""

import unittest

import pandas as pd

from autocad_scanner import RoomPolygon, RoomText
from polygon_matcher import associate_texts_with_polygons, match_rooms
from utils import polygon_area, polygon_bbox, polygon_centroid


def poly(handle, pts):
    return RoomPolygon(handle=handle, closed=True, vertices=pts, area=polygon_area(pts),
                       centroid=polygon_centroid(pts), bbox=polygon_bbox(pts))


def text(value, x, y, handle=""):
    return RoomText(handle=handle or f"T{value}", text=value, position=(x, y, 0.0))


ROOM_A = poly("A", [(0, 0), (100, 0), (100, 100), (0, 100)])
FLOOR = poly("F", [(-10, -10), (400, -10), (400, 400), (-10, 400)])
ROOM_FAR = poly("C", [(1000, 0), (1100, 0), (1100, 100), (1000, 100)])


class TestAssociation(unittest.TestCase):

    def test_smallest_containing_polygon_wins(self):
        [a] = associate_texts_with_polygons([text("101", 50, 50)], [FLOOR, ROOM_A])
        self.assertEqual((a.polygon_handle, a.match_method, a.confidence), ("A", "contains", 1.0))
        self.assertEqual(a.polygon_vertices, ROOM_A.vertices)

    def test_nearest_fallback_within_distance(self):
        [a] = associate_texts_with_polygons([text("101", 1050, 150)], [ROOM_FAR])
        self.assertEqual((a.polygon_handle, a.match_method), ("C", "nearest"))
        self.assertAlmostEqual(a.confidence, 1 - 100 / 500)

    def test_too_far_is_unassociated(self):
        [a] = associate_texts_with_polygons([text("101", 5000, 5000)], [ROOM_FAR])
        self.assertEqual((a.polygon_handle, a.match_method), ("", ""))


class TestMatching(unittest.TestCase):

    def setUp(self):
        self.df = pd.DataFrame({"Room": ["101", " 102a ", "104", "101"],
                                "Dept": ["Eng", "Admin", "Ghost", "Duplicate row"]})
        self.texts = [text("101", 50, 50), text("102A", 0, 0), text("103", 0, 0),
                      text("101", 60, 60, handle="T101b")]
        self.assoc = associate_texts_with_polygons(self.texts, [ROOM_A])

    def test_match_summary(self):
        s = match_rooms(self.texts, self.assoc, self.df, "Room", ["Dept"])
        matched = {r.room_id: r.row_data for r in s.results if r.matched}
        self.assertEqual(matched, {"101": {"Dept": "Eng"}, "102A": {"Dept": "Admin"}})
        self.assertEqual(s.matched_count, 2)
        self.assertEqual(s.unmatched_drawing, ["103"])
        self.assertEqual(s.unmatched_sheet, ["104"])
        # first occurrence wins, on both sides
        self.assertEqual([r.text_handle for r in s.results if r.room_id == "101"], ["T101"])
        self.assertEqual(s.total_sheet_rows, 3)


if __name__ == "__main__":
    unittest.main()
