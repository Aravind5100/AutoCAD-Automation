"""
test_converter.py
-----------------
dwg_converter's AutoCAD session handling, tested against a fake AutoCAD
(B7, B18, B19 regression tests). No AutoCAD needed.
"""

import os
import unittest
from unittest import mock

import pywintypes

import dwg_converter as dc

BUSY = pywintypes.com_error(-2147418111, "Call was rejected by callee.", None, None)


class FakeDoc:
    def __init__(self, app, name, busy=0):
        self.app, self.Name, self.busy = app, name, busy

    def GetVariable(self, var):
        return self.app.sysvars[var]

    def SetVariable(self, var, value):
        if self.busy:                       # rejected `busy` times, then accepted
            self.busy -= 1
            raise BUSY
        self.app.sysvars[var] = value

    def Close(self, save):
        self.app.open.remove(self)


class FakeDocuments:
    def __init__(self, app):
        self.app = app

    @property
    def Count(self):
        return len(self.app.open)

    def Add(self):
        doc = FakeDoc(self.app, "Drawing1.dwg")
        self.app.open.append(doc)
        return doc


class FakeAcad:
    def __init__(self, open_names=(), busy=0):
        self.sysvars = {"FILEDIA": 1, "CMDDIA": 1, "PROXYNOTICE": 1}
        self.Visible = False
        self.open = [FakeDoc(self, n, busy) for n in open_names]
        self.Documents = FakeDocuments(self)

    @property
    def ActiveDocument(self):
        return self.open[-1]


class TestSession(unittest.TestCase):

    def _session(self, acad):
        seen, logs = {}, []
        with mock.patch.object(dc.win32com.client, "Dispatch", return_value=acad):
            with dc._acad_session(logs.append):
                seen.update(acad.sysvars)
        return seen, logs

    def test_no_drawing_open_uses_and_closes_blank_anchor_B19(self):
        acad = FakeAcad()
        during, _ = self._session(acad)
        self.assertEqual(during, {"FILEDIA": 0, "CMDDIA": 0, "PROXYNOTICE": 0})
        self.assertEqual(acad.sysvars, {"FILEDIA": 1, "CMDDIA": 1, "PROXYNOTICE": 1})
        self.assertEqual(acad.open, [])
        self.assertTrue(acad.Visible)

    def test_user_drawing_left_open_and_values_restored_B7(self):
        acad = FakeAcad(["Plan.dwg"])
        acad.sysvars["CMDDIA"] = 0            # a user preference must be kept as-is
        self._session(acad)
        self.assertEqual(acad.sysvars, {"FILEDIA": 1, "CMDDIA": 0, "PROXYNOTICE": 1})
        self.assertEqual([d.Name for d in acad.open], ["Plan.dwg"])

    def test_busy_calls_are_retried_B18(self):
        acad = FakeAcad(["Plan.dwg"], busy=3)
        during, _ = self._session(acad)
        self.assertEqual(during["FILEDIA"], 0)
        self.assertEqual(acad.sysvars["FILEDIA"], 1)

    def test_restore_failure_is_logged(self):
        acad = FakeAcad(["Plan.dwg"])
        logs = []
        with mock.patch.object(dc.win32com.client, "Dispatch", return_value=acad):
            with dc._acad_session(logs.append):
                acad.open[0].SetVariable = mock.Mock(side_effect=RuntimeError("gone"))
        self.assertTrue(any("could not restore FILEDIA" in m for m in logs), logs)

    def test_connection_failure_raises_conversion_error(self):
        with mock.patch.object(dc.win32com.client, "Dispatch", side_effect=OSError("no")):
            with self.assertRaises(dc.ConversionError):
                with dc._acad_session():
                    pass


class TestCallAndClose(unittest.TestCase):

    def test_retry_then_give_up(self):
        with mock.patch.object(dc, "COM_RETRY_SECONDS", 0.3):
            with self.assertRaises(pywintypes.com_error):
                dc._call(mock.Mock(side_effect=BUSY))
            with self.assertRaises(AttributeError):
                dc._call(mock.Mock(side_effect=AttributeError("AutoCAD.Application.Documents")))

    def test_attribute_error_while_busy_is_retried(self):
        fn = mock.Mock(side_effect=[AttributeError("AutoCAD.Application.Documents"), 42])
        self.assertEqual(dc._call(fn), 42)

    def test_other_errors_raised_immediately(self):
        fn = mock.Mock(side_effect=pywintypes.com_error(-1, "other", None, None))
        with self.assertRaises(pywintypes.com_error):
            dc._call(fn)
        self.assertEqual(fn.call_count, 1)

    def test_close_failure_logged_not_raised(self):
        doc = mock.Mock(Name="stuck.dxf")
        doc.Close.side_effect = pywintypes.com_error(-5, "nope", None, None)
        logs = []
        dc._close(doc, logs.append)
        self.assertIn("could not close stuck.dxf", logs[0])


class TestWorkDir(unittest.TestCase):

    def test_make_and_remove(self):
        work = dc.make_work_dir()
        with open(os.path.join(work, "x.dxf"), "w") as f:
            f.write("x")
        dc.remove_work_dir(work)
        self.assertFalse(os.path.exists(work))
        dc.remove_work_dir(None)            # no-op

    def test_missing_input_dwg(self):
        work = dc.make_work_dir()
        self.addCleanup(dc.remove_work_dir, work)
        with self.assertRaises(dc.ConversionError):
            dc.dwg_to_dxf(r"C:\definitely\missing.dwg", work)


if __name__ == "__main__":
    unittest.main()
