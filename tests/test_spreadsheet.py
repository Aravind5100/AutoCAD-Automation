"""
test_spreadsheet.py
-------------------
Loading and cleaning CSV / Excel input (B5 regression tests).
"""

import os
import time
import unittest
from unittest import mock

import openpyxl

import spreadsheet_loader
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


class TestCache(TempDirTestCase):

    def setUp(self):
        super().setUp()
        patcher = mock.patch.object(spreadsheet_loader, "SPREADSHEET_CACHE_DIR",
                                    self.path("cache"))
        patcher.start()
        self.addCleanup(patcher.stop)
        self.sheet = self.write_text("s.csv", "Room,Dept\n101,Eng\n")

    def test_second_load_comes_from_cache(self):
        first = load_spreadsheet(self.sheet, use_cache=True)
        self.assertEqual(len(os.listdir(self.path("cache"))), 1)
        with mock.patch.object(spreadsheet_loader, "_load_csv") as parse:
            second = load_spreadsheet(self.sheet, use_cache=True)
        parse.assert_not_called()
        self.assertTrue(first.equals(second))

    def test_changed_file_is_reparsed_and_old_entry_replaced(self):
        load_spreadsheet(self.sheet, use_cache=True)
        time.sleep(0.05)
        with open(self.sheet, "a", encoding="utf-8") as f:
            f.write("102,Admin\n")
        df = load_spreadsheet(self.sheet, use_cache=True)
        self.assertEqual(list(df["Room"]), ["101", "102"])
        self.assertEqual(len(os.listdir(self.path("cache"))), 1)

    def test_cache_off_by_default(self):
        load_spreadsheet(self.sheet)
        self.assertFalse(os.path.exists(self.path("cache")))


class TestColumnSuggestion(unittest.TestCase):

    def test_room_column_suggested(self):
        self.assertEqual(find_room_id_column_suggestion(["Bldg", "Room_Number", "Dept"]),
                         "Room_Number")
        self.assertIsNone(find_room_id_column_suggestion(["Bldg", "Dept"]))


if __name__ == "__main__":
    unittest.main()
