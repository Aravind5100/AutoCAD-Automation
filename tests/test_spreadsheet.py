"""
test_spreadsheet.py
-------------------
Loading and cleaning CSV / Excel input (B5 regression tests).
"""

import unittest

import openpyxl

from spreadsheet_loader import (
    FileLoadError,
    find_room_id_column_suggestion,
    load_spreadsheet,
)
from tests.helpers import TempDirTestCase


class TestCsv(TempDirTestCase):

    def test_values_trimmed_and_blank_rows_dropped_B5(self):
        p = self.write_text("s.csv", "Building ID,Room Number,Department\n"
                                     "0132 , 101 ,  Eng \n,,\n  ,  , \n0132,0101,Admin\n")
        rows = load_spreadsheet(p).to_dict("records")
        self.assertEqual(rows, [
            {"Building ID": "0132", "Room Number": "101", "Department": "Eng"},
            {"Building ID": "0132", "Room Number": "0101", "Department": "Admin"},
        ])

    def test_unnamed_columns_dropped(self):
        p = self.write_text("s.csv", "Room,,Dept\n101,x,Eng\n")
        self.assertEqual(list(load_spreadsheet(p).columns), ["Room", "Dept"])

    def test_errors(self):
        with self.assertRaises(FileLoadError):
            load_spreadsheet(self.path("missing.csv"))
        with self.assertRaises(FileLoadError):
            load_spreadsheet(self.write_text("s.txt", "a,b\n"))


class TestExcel(TempDirTestCase):

    def _workbook(self, rows):
        wb = openpyxl.Workbook()
        for r in rows:
            wb.active.append(r)
        p = self.path("s.xlsx")
        wb.save(p)
        return p

    def test_header_on_third_row_and_numbers_as_text(self):
        p = self._workbook([["Facilities Report"], ["Generated 2026"],
                            ["Bldg", "Room", "Dept"],
                            ["0132", 101, " Lab "], [None, None, None], ["0132", 103.0, None]])
        self.assertEqual(load_spreadsheet(p).to_dict("records"), [
            {"Bldg": "0132", "Room": "101", "Dept": "Lab"},
            {"Bldg": "0132", "Room": "103", "Dept": ""},
        ])

    @unittest.expectedFailure
    def test_numeric_building_code_keeps_leading_zero_B10(self):
        """B10 (open): a building code typed as a number loses its leading zero."""
        p = self._workbook([["t"], ["t"], ["Bldg", "Room"], [132, "101"]])
        self.assertEqual(load_spreadsheet(p)["Bldg"].iloc[0], "0132")


class TestColumnSuggestion(unittest.TestCase):

    def test_room_column_suggested(self):
        self.assertEqual(find_room_id_column_suggestion(["Bldg", "Room_Number", "Dept"]),
                         "Room_Number")
        self.assertIsNone(find_room_id_column_suggestion(["Bldg", "Dept"]))


if __name__ == "__main__":
    unittest.main()
