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
                      text("101", 60, 10, handle="T101b")]     # not stacked under the first
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
        self.assertEqual(s.repeated_labels, ["101"])

    def test_leading_zero_matches_offered_only_when_unique(self):
        from polygon_matcher import apply_leading_zero_matches
        texts = [text("015", 50, 50), text("016", 10, 10), text("16", 60, 10), text("7", 90, 90)]
        assoc = associate_texts_with_polygons(texts, [ROOM_A])
        df = pd.DataFrame({"Room": ["15", "016", "0016", "07", "007"]})
        s = match_rooms(texts, assoc, df, "Room", ["Room"])
        # 015 = 15 is unique; 016 matches exactly, leaving 16 = 0016 unique;
        # 7 has two sheet candidates (07, 007) so it is not offered
        self.assertEqual([(a, b) for a, b, _ in s.leading_zero_matches],
                         [("015", "15"), ("16", "0016")])
        self.assertEqual(s.matched_count, 1)                     # 016 matched exactly
        self.assertEqual(apply_leading_zero_matches(s), [("015", "15"), ("16", "0016")])
        self.assertEqual(s.matched_count, 3)
        match = next(r for r in s.results if r.room_id == "015")
        self.assertEqual((match.matched, match.row_data), (True, {"Room": "15"}))
        self.assertNotIn("015", s.unmatched_drawing)
        self.assertNotIn("15", s.unmatched_sheet)

    def test_area_figure_under_another_room_number_does_not_win(self):
        # Room 102D shows its area "102" under its number; room 102 is elsewhere.
        room_102d = poly("D", [(0, 0), (100, 0), (100, 100), (0, 100)])
        room_102 = poly("E", [(200, 0), (300, 0), (300, 100), (200, 100)])
        texts = [text("102", 20, 35, handle="area"),              # first in the drawing
                 text("102D", 20, 50, handle="num102D"),
                 text("102", 220, 50, handle="num102"),
                 text("189", 220, 35, handle="area102")]          # area of room 102
        assoc = associate_texts_with_polygons(texts, [room_102d, room_102])
        df = pd.DataFrame({"Room": ["102", "102D"]})
        s = match_rooms(texts, assoc, df, "Room", [])
        by_room = {r.room_id: (r.text_handle, r.polygon_handle) for r in s.results if r.matched}
        self.assertEqual(by_room, {"102": ("num102", "E"), "102D": ("num102D", "D")})
        self.assertEqual(s.repeated_labels, [])                  # the area copy is not reported
        self.assertEqual(s.unmatched_drawing, [])                # "189" is an area, not a room
        self.assertEqual(s.secondary_ignored, ["189"])


if __name__ == "__main__":
    unittest.main()
