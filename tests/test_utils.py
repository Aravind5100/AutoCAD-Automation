"""
test_utils.py
-------------
Column normalisation, building ID, room-identifier heuristic, geometry.
"""

import unittest

from utils import (
    build_room_key,
    detect_building_column,
    detect_floor_column,
    extract_building_id,
    is_room_identifier,
    normalize_col,
    normalize_room_id,
    point_in_polygon,
    polygon_area,
    polygon_bbox,
    polygon_centroid,
)

SQUARE = [(0, 0), (10, 0), (10, 10), (0, 10)]
L_SHAPE = [(0, 0), (10, 0), (10, 1), (1, 1), (1, 10), (0, 10)]


class TestNormalisation(unittest.TestCase):

    def test_column_variants_normalise_alike(self):
        for name in ("Room Number", "room_number", "ROOM-NUMBER", " Room.Number# "):
            self.assertEqual(normalize_col(name), "room number", name)

    def test_building_column_detected(self):
        self.assertEqual(detect_building_column(["Room", "BLDG_ID", "Dept"]), "BLDG_ID")
        self.assertIsNone(detect_building_column(["Room", "Dept"]))

    def test_building_id_is_first_four_chars_uppercased(self):
        self.assertEqual(extract_building_id(r"C:\x\0132_SATELLITE DISH LAB.dwg"), "0132")
        self.assertEqual(extract_building_id("engr_floor1.dxf"), "ENGR")

    def test_room_id_normalisation(self):
        self.assertEqual(normalize_room_id(" 102A "), "102a")
        self.assertEqual(normalize_room_id(None), "")


class TestRoomIdentifier(unittest.TestCase):

    def test_accepts_room_numbers(self):
        for text in ("101", "102A", "B201", "LAB-101", "A1"):
            self.assertTrue(is_room_identifier(text), text)

    def test_rejects_non_room_text(self):
        for text in ("", "N", "EXIT", "LOBBY", "12'-6\"", "101 / 102", "Men's Restroom",
                     "x" * 21 + "1"):
            self.assertFalse(is_room_identifier(text), text)

    @unittest.expectedFailure
    def test_known_false_positives_B11(self):
        """B11 (open): labels such as these are accepted as room numbers."""
        for text in ("1ST FLOOR", "LEVEL 2", "SCALE 1", "STAIR 3"):
            self.assertFalse(is_room_identifier(text), text)


class TestGeometry(unittest.TestCase):

    def test_area_and_bbox(self):
        self.assertEqual(polygon_area(SQUARE), 100.0)
        self.assertEqual(polygon_area(L_SHAPE), 19.0)
        self.assertEqual(polygon_bbox(L_SHAPE), (0, 0, 10, 10))

    def test_point_in_polygon(self):
        self.assertTrue(point_in_polygon(5, 5, SQUARE))
        self.assertFalse(point_in_polygon(15, 5, SQUARE))
        self.assertTrue(point_in_polygon(0.5, 5, L_SHAPE))
        self.assertFalse(point_in_polygon(5, 5, L_SHAPE))    # inside the notch

    def test_centroid(self):
        self.assertEqual(polygon_centroid(SQUARE), (5.0, 5.0))
        cx, cy = polygon_centroid(L_SHAPE)
        # the centroid of an L-shaped room lies outside the room (B14)
        self.assertFalse(point_in_polygon(cx, cy, L_SHAPE))

    def test_degenerate_centroid_falls_back_to_mean(self):
        self.assertEqual(polygon_centroid([(0, 0), (2, 0), (4, 0)]), (2.0, 0.0))


class TestRoomKey(unittest.TestCase):

    def test_values_joined_as_is(self):
        self.assertEqual(build_room_key("0132", "01", "101"), "0132-01-101")
        self.assertEqual(build_room_key("0132", "1", "102A"), "0132-1-102A")
        self.assertEqual(build_room_key(" engr ", "B1", "LAB-101"), "engr-B1-LAB-101")

    def test_forbidden_layer_characters_replaced(self):
        self.assertEqual(build_room_key("0132", "1/2", 'R<1>:"x"'), "0132-1_2-R_1___x_")

    def test_empty_part_gives_none(self):
        for parts in (("", "01", "101"), ("0132", " ", "101"), ("0132", "01", None)):
            self.assertIsNone(build_room_key(*parts), parts)

    def test_floor_column_detected(self):
        self.assertEqual(detect_floor_column(["Bldg", "Floor_Code", "Room"]), "Floor_Code")
        self.assertEqual(detect_floor_column(["Bldg", "FLR", "Room"]), "FLR")
        self.assertIsNone(detect_floor_column(["Bldg", "Room"]))


if __name__ == "__main__":
    unittest.main()
