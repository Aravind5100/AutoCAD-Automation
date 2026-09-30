"""
qt_ui.py
--------
PySide6 (Qt) desktop window for the Room Layer tool.

    1  Files     spreadsheet, drawing, editable Building ID
    2  Columns   Room / Building / Floor + live layer-name preview
    Run          Create Room Layers / Cancel, step progress
    Results      one row per room (created / needs check / skipped / not matched)
    Log          full colour-coded log

All work runs on QThreads (spreadsheet loading, the pipeline); widgets are
only touched on the GUI thread, through signals. The pipeline itself lives
in ``pipeline.py`` and knows nothing about Qt.
"""

from __future__ import annotations

import os
import threading
import time

from PySide6.QtCore import QSettings, Qt, QThread, Signal
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QComboBox,
    QFileDialog,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from config import OUTPUT_SUFFIX, ROOM_KEY_SEPARATOR
from utils import (
    build_room_key,
    detect_building_column,
    detect_floor_column,
    extract_building_id,
    filter_dataframe_by_building,
)

APP_NAME = "Room Layer Tool"

# ---------------------------------------------------------------------------
# Themes
# ---------------------------------------------------------------------------

THEMES = {
    "light": dict(bg="#f5f6f8", card="#ffffff", text="#1f2328", muted="#5f6b7a",
                  border="#d8dee4", input="#ffffff", alt="#f6f8fa", accent="#2563eb",
                  accent_hover="#1d4ed8", on_accent="#ffffff", success="#1a7f37",
                  warn="#9a6700", error="#cf222e", info="#0969da"),
    "dark": dict(bg="#1e1e2e", card="#27273a", text="#e6e6f0", muted="#a6adc8",
                 border="#3b3b52", input="#313145", alt="#2c2c40", accent="#89b4fa",
                 accent_hover="#a6c8ff", on_accent="#1e1e2e", success="#a6e3a1",
                 warn="#f9c97c", error="#f38ba8", info="#89dceb"),
}

_QSS = """
QWidget {{ background: {bg}; color: {text}; font-size: 10.5pt; }}
QGroupBox {{ background: {card}; border: 1px solid {border}; border-radius: 8px;
            margin-top: 14px; padding: 14px 12px 10px 12px; font-weight: 600; }}
QGroupBox::title {{ subcontrol-origin: margin; left: 12px; padding: 0 4px; color: {accent}; }}
QGroupBox QLabel {{ background: transparent; }}
QLabel#title {{ font-size: 16pt; font-weight: 700; }}
QLabel#muted, QLabel#hint {{ color: {muted}; }}
QLabel#preview {{ color: {success}; font-family: Consolas; font-size: 11pt; }}
QLineEdit, QComboBox, QPlainTextEdit, QTableWidget {{
    background: {input}; border: 1px solid {border}; border-radius: 5px; padding: 4px 6px; }}
QLineEdit:read-only {{ color: {muted}; }}
QComboBox QAbstractItemView {{ background: {input}; selection-background-color: {accent};
                              selection-color: {on_accent}; }}
QPushButton, QToolButton {{ background: {card}; border: 1px solid {border}; border-radius: 5px;
                            padding: 5px 14px; }}
QPushButton:hover, QToolButton:hover {{ border-color: {accent}; }}
QPushButton:disabled {{ color: {muted}; }}
QPushButton#primary {{ background: {accent}; color: {on_accent}; border: none; font-weight: 700;
                      padding: 8px 22px; }}
QPushButton#primary:hover {{ background: {accent_hover}; }}
QPushButton#primary:disabled {{ background: {border}; color: {muted}; }}
QProgressBar {{ border: 1px solid {border}; border-radius: 5px; background: {input};
               text-align: center; height: 18px; }}
QProgressBar::chunk {{ background: {accent}; border-radius: 4px; }}
QTabWidget::pane {{ border: 1px solid {border}; border-radius: 6px; background: {card}; }}
QTabBar::tab {{ background: {bg}; padding: 6px 16px; border: 1px solid {border};
               border-bottom: none; border-top-left-radius: 6px; border-top-right-radius: 6px; }}
QTabBar::tab:selected {{ background: {card}; color: {accent}; font-weight: 600; }}
QTableWidget {{ alternate-background-color: {alt}; gridline-color: {border}; }}
QHeaderView::section {{ background: {alt}; border: none; border-bottom: 1px solid {border};
                       padding: 5px; font-weight: 600; }}
"""


def stylesheet(theme: str) -> str:
    return _QSS.format(**THEMES[theme])


# ---------------------------------------------------------------------------
# Results table: status → label and colour
# ---------------------------------------------------------------------------

FILTERS = ["All rooms", "Created", "Needs check", "Skipped / failed", "Not matched"]


def status_label(row) -> tuple[str, str]:
    """(text, theme colour key) shown in the Status column for a ResultRow."""
    if row.status == "created":
        return ("⚠ Check", "warn") if row.needs_check else ("✓ Created", "success")
    if row.status == "skipped":
        return "– Skipped", "muted"
    if row.status == "failed":
        return "✗ Failed", "error"
    return "○ " + row.status.capitalize(), "info"          # not in spreadsheet / drawing


def row_matches_filter(row, filter_name: str) -> bool:
    if filter_name == "Created":
        return row.status == "created"
    if filter_name == "Needs check":
        return row.status == "created" and row.needs_check
    if filter_name == "Skipped / failed":
        return row.status in ("skipped", "failed")
    if filter_name == "Not matched":
        return row.status in ("not in spreadsheet", "not in drawing")
    return True


# ---------------------------------------------------------------------------
# Output location rules (same as the Tk version)
# ---------------------------------------------------------------------------

def default_output_dir(last_dir: str | None) -> str:
    """Last folder used, else Documents, else the home folder — never the input's folder."""
    if last_dir and os.path.isdir(last_dir):
        return last_dir
    documents = os.path.join(os.path.expanduser("~"), "Documents")
    return documents if os.path.isdir(documents) else os.path.expanduser("~")


def check_output_path(input_path: str, chosen: str) -> tuple[str | None, str | None]:
    """Return (path with the input's extension, None) or (None, reason it is refused)."""
    ext = os.path.splitext(input_path)[1].lower()
    path = chosen if os.path.splitext(chosen)[1].lower() == ext else chosen + ext
    if os.path.normcase(os.path.abspath(path)) == os.path.normcase(os.path.abspath(input_path)):
        return None, "The original drawing cannot be overwritten.\nChoose another name or folder."
    return path, None


# ---------------------------------------------------------------------------
# Worker threads
# ---------------------------------------------------------------------------

class SheetLoader(QThread):
    loaded = Signal(object, float)          # DataFrame, seconds
    failed = Signal(str)

    def __init__(self, path: str):
        super().__init__()
        self.path = path

    def run(self):
        from spreadsheet_loader import FileLoadError, load_spreadsheet
        start = time.monotonic()
        try:
            df = load_spreadsheet(self.path, use_cache=True)
        except FileLoadError as exc:
            self.failed.emit(str(exc))
        else:
            self.loaded.emit(df, time.monotonic() - start)


class RunWorker(QThread):
    log = Signal(str, str)                  # message, level
    step = Signal(str, int)                 # text, step number (1-based)
    finished_ok = Signal(object)            # RunResult
    stopped = Signal(str)                   # expected stop (no rows, no matches...)
    cancelled = Signal()
    failed = Signal(str)

    def __init__(self, request):
        super().__init__()
        self.request = request
        self._cancel = threading.Event()
        self._steps = 0

    def cancel(self):
        self._cancel.set()

    def _on_step(self, text: str):
        self._steps += 1
        self.step.emit(text, self._steps)

    def run(self):
        import pythoncom
        import pipeline
        pythoncom.CoInitialize()            # AutoCAD COM from this thread
        try:
            result = pipeline.run(self.request, log=self.log.emit, step=self._on_step,
                                  is_cancelled=self._cancel.is_set)
        except pipeline.RunCancelled:
            self.cancelled.emit()
        except pipeline.RunStopped as exc:
            self.stopped.emit(str(exc))
        except Exception as exc:            # conversion / scan errors, anything unexpected
            self.failed.emit(str(exc))
        else:
            self.finished_ok.emit(result)
        finally:
            pythoncom.CoUninitialize()


def _preload_libraries():
    """Import the heavy libraries in the background (first import is slow)."""
    try:
        import ezdxf  # noqa: F401
        import openpyxl  # noqa: F401
        import pandas  # noqa: F401
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Main window
# ---------------------------------------------------------------------------

class MainWindow(QMainWindow):

    def __init__(self, settings: QSettings | None = None):
        super().__init__()
        self.settings = settings or QSettings("RoomAnnotator", "RoomLayerTool")
        self.theme = self.settings.value("theme", "light")
        if self.theme not in THEMES:
            self.theme = "light"
        self.df = None
        self.loader: SheetLoader | None = None
        self.worker: RunWorker | None = None
        self.result = None

        self.setWindowTitle(APP_NAME)
        self.resize(1000, 820)
        self.setMinimumSize(820, 640)
        self._build()
        self._apply_theme()
        self._update_state()
        threading.Thread(target=_preload_libraries, daemon=True).start()

    # ----------------------------------------------------------- layout
    def _build(self):
        root = QWidget()
        outer = QVBoxLayout(root)
        outer.setContentsMargins(18, 14, 18, 14)
        outer.setSpacing(10)
        self.setCentralWidget(root)

        header = QHBoxLayout()
        title = QLabel(APP_NAME)
        title.setObjectName("title")
        subtitle = QLabel("Spreadsheet rooms → Building-Floor-Room layers for ArcGIS")
        subtitle.setObjectName("muted")
        self.theme_btn = QToolButton()
        self.theme_btn.clicked.connect(self._toggle_theme)
        header.addWidget(title)
        header.addSpacing(12)
        header.addWidget(subtitle, 0, Qt.AlignBottom)
        header.addStretch()
        header.addWidget(self.theme_btn)
        outer.addLayout(header)

        # 1 Files
        files = QGroupBox("1   Files")
        grid = QGridLayout(files)
        grid.setColumnStretch(1, 1)
        self.sheet_edit = self._path_row(grid, 0, "Spreadsheet", self._browse_sheet)
        self.sheet_state = QLabel()
        grid.addWidget(self.sheet_state, 0, 3)
        self.drawing_edit = self._path_row(grid, 1, "Drawing (DWG / DXF)", self._browse_drawing)
        grid.addWidget(QLabel("Building ID"), 2, 0)
        self.building_edit = QLineEdit()
        self.building_edit.setFixedWidth(120)
        self.building_edit.setPlaceholderText("e.g. 0036")
        self.building_edit.textChanged.connect(self._update_preview)
        hint = QLabel("filled from the file name — edit it if the file name is different")
        hint.setObjectName("hint")
        row = QHBoxLayout()
        row.addWidget(self.building_edit)
        row.addWidget(hint)
        row.addStretch()
        grid.addLayout(row, 2, 1, 1, 3)
        outer.addWidget(files)

        # 2 Columns
        cols = QGroupBox("2   Columns")
        cgrid = QGridLayout(cols)
        self.room_combo = self._combo(cgrid, 0, 0, "Room")
        self.building_combo = self._combo(cgrid, 0, 2, "Building")
        self.floor_combo = self._combo(cgrid, 0, 4, "Floor")
        sep = ROOM_KEY_SEPARATOR
        cgrid.addWidget(QLabel(f"Layer name:  [Building]{sep}[Floor]{sep}[Room]"), 1, 0, 1, 3)
        self.preview = QLabel()
        self.preview.setObjectName("preview")
        cgrid.addWidget(self.preview, 1, 3, 1, 3)
        outer.addWidget(cols)

        # Run row
        run_row = QHBoxLayout()
        self.run_btn = QPushButton("▶  Create Room Layers")
        self.run_btn.setObjectName("primary")
        self.run_btn.clicked.connect(self._start_run)
        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.clicked.connect(self._cancel_run)
        self.progress = QProgressBar()
        self.progress.setTextVisible(False)
        self.status = QLabel("Choose a spreadsheet and a drawing to begin.")
        self.status.setObjectName("muted")
        run_row.addWidget(self.run_btn)
        run_row.addWidget(self.cancel_btn)
        run_row.addWidget(self.progress, 1)
        outer.addLayout(run_row)
        outer.addWidget(self.status)

        # Results / Log tabs
        self.tabs = QTabWidget()
        results = QWidget()
        rlay = QVBoxLayout(results)
        bar = QHBoxLayout()
        self.filter_combo = QComboBox()
        self.filter_combo.addItems(FILTERS)
        self.filter_combo.currentTextChanged.connect(self._apply_filter)
        self.summary = QLabel("No results yet.")
        self.summary.setObjectName("muted")
        bar.addWidget(QLabel("Show"))
        bar.addWidget(self.filter_combo)
        bar.addSpacing(12)
        bar.addWidget(self.summary, 1)
        rlay.addLayout(bar)
        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["Room", "Layer", "Status", "Note"])
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().setVisible(False)
        hdr = self.table.horizontalHeader()
        for i, mode in enumerate((QHeaderView.ResizeToContents, QHeaderView.ResizeToContents,
                                  QHeaderView.ResizeToContents, QHeaderView.Stretch)):
            hdr.setSectionResizeMode(i, mode)
        rlay.addWidget(self.table)
        self.tabs.addTab(results, "Results")
        self.log_view = QPlainTextEdit()
        self.log_view.setReadOnly(True)
        self.log_view.setFont(QFont("Consolas", 9))
        self.tabs.addTab(self.log_view, "Log")
        outer.addWidget(self.tabs, 1)

    def _path_row(self, grid, r, label, handler) -> QLineEdit:
        grid.addWidget(QLabel(label), r, 0)
        edit = QLineEdit()
        edit.setReadOnly(True)
        edit.setPlaceholderText("not selected")
        grid.addWidget(edit, r, 1)
        btn = QPushButton("Browse…")
        btn.clicked.connect(handler)
        grid.addWidget(btn, r, 2)
        return edit

    def _combo(self, grid, r, c, label) -> QComboBox:
        grid.addWidget(QLabel(label), r, c)
        combo = QComboBox()
        combo.setMinimumWidth(180)
        combo.currentTextChanged.connect(self._update_preview)
        grid.addWidget(combo, r, c + 1)
        return combo

    # ----------------------------------------------------------- theme
    def _toggle_theme(self):
        self.theme = "dark" if self.theme == "light" else "light"
        self.settings.setValue("theme", self.theme)
        self._apply_theme()

    def _apply_theme(self):
        self.setStyleSheet(stylesheet(self.theme))
        self.theme_btn.setText("☾  Dark" if self.theme == "light" else "☀  Light")
        if self.result is not None:
            self._fill_table(self.result.rows)

    def color(self, key: str) -> QColor:
        return QColor(THEMES[self.theme][key])

    # ----------------------------------------------------------- files
    def _browse_sheet(self):
        path, _ = QFileDialog.getOpenFileName(self, "Select Spreadsheet", self._browse_dir(),
                                              "Spreadsheets (*.xlsx *.xls *.csv);;All files (*.*)")
        if path:
            self.load_sheet(path)

    def _browse_drawing(self):
        path, _ = QFileDialog.getOpenFileName(self, "Select Drawing", self._browse_dir(),
                                              "AutoCAD drawings (*.dwg *.dxf);;All files (*.*)")
        if path:
            self.set_drawing(path)

    def _browse_dir(self) -> str:
        return self.settings.value("browse_dir", "") or default_output_dir(None)

    def set_drawing(self, path: str):
        path = os.path.normpath(path)
        self.settings.setValue("browse_dir", os.path.dirname(path))
        self.drawing_edit.setText(path)
        self.building_edit.setText(extract_building_id(path))
        self.log(f"Drawing: {path}  (Building ID {self.building_edit.text()})")
        self._update_state()

    def load_sheet(self, path: str, wait: bool = False):
        path = os.path.normpath(path)
        self.settings.setValue("browse_dir", os.path.dirname(path))
        self.sheet_edit.setText(path)
        self.df = None
        self.sheet_state.setText("loading…")
        self.set_status("Loading spreadsheet… large files take a while the first time.")
        self.log(f"Loading spreadsheet: {path}")
        self.loader = SheetLoader(path)
        self.loader.loaded.connect(self._sheet_loaded)
        self.loader.failed.connect(self._sheet_failed)
        self.loader.start()
        if wait:                                            # tests
            self.loader.wait()
            QApplication.processEvents()
        self._update_state()

    def _sheet_loaded(self, df, seconds: float):
        self.df = df
        columns = list(df.columns)
        self.sheet_state.setText(f"✓ {len(df):,} rows")
        self.log(f"Loaded {len(df):,} rows, {len(columns)} columns in {seconds:.1f} s.", "SUCCESS")
        from spreadsheet_loader import find_room_id_column_suggestion
        guesses = ((self.room_combo, find_room_id_column_suggestion(columns)),
                   (self.building_combo, detect_building_column(columns)),
                   (self.floor_combo, detect_floor_column(columns)))
        for combo, guess in guesses:
            combo.blockSignals(True)
            combo.clear()
            combo.addItems(columns)
            combo.setCurrentIndex(columns.index(guess) if guess in columns else -1)
            combo.blockSignals(False)
        missing = [n for n, (_, g) in zip(("Room", "Building", "Floor"), guesses) if g is None]
        if missing:
            self.log(f"Please choose the {', '.join(missing)} column(s) in step 2.", "WARN")
        self.set_status("Spreadsheet loaded.")
        self._update_preview()
        self._update_state()

    def _sheet_failed(self, message: str):
        self.sheet_state.setText("✗ failed")
        self.log(message, "ERROR")
        self.set_status("The spreadsheet could not be loaded.")
        QMessageBox.critical(self, "Spreadsheet", message)
        self._update_state()

    # ----------------------------------------------------------- columns
    def columns(self) -> tuple[str, str, str]:
        return (self.room_combo.currentText(), self.building_combo.currentText(),
                self.floor_combo.currentText())

    def _update_preview(self, *_):
        room, bldg, floor = self.columns()
        text = ""
        if self.df is not None and not self.df.empty and all((room, bldg, floor)):
            # Show a room of the building being processed, not just row 1 of the sheet
            building = self.building_edit.text().strip()
            rows = filter_dataframe_by_building(self.df, bldg, building) if building else self.df
            if rows.empty:
                text = f"no rows for building {building} in the {bldg} column"
            else:
                first = rows.iloc[0]
                key = build_room_key(first[bldg], first[floor], first[room])
                text = f"e.g.  {key}" if key else "e.g.  (a value is empty)"
        self.preview.setText(text)
        self._update_state()

    # ----------------------------------------------------------- run
    def _problem(self) -> str | None:
        """Why the run cannot start yet, or None."""
        if self.loader is not None and self.loader.isRunning():
            return "The spreadsheet is still loading."
        if self.df is None:
            return "Choose a spreadsheet."
        if not self.drawing_edit.text():
            return "Choose a drawing."
        room, bldg, floor = self.columns()
        if not all((room, bldg, floor)):
            return "Choose the Room, Building and Floor columns."
        if len({room, bldg, floor}) < 3:
            return "Room, Building and Floor must be three different columns."
        if not self.building_edit.text().strip():
            return "Enter the Building ID."
        return None

    def _running(self) -> bool:
        return self.worker is not None and self.worker.isRunning()

    def _update_state(self, *_):
        running = self._running()
        problem = self._problem()
        self.run_btn.setEnabled(not running and problem is None)
        self.run_btn.setToolTip(problem or "")
        self.cancel_btn.setEnabled(running)
        for w in (self.building_edit, self.room_combo, self.building_combo, self.floor_combo):
            w.setEnabled(not running)

    def ask_output_path(self) -> str | None:
        drawing = self.drawing_edit.text()
        base, ext = os.path.splitext(os.path.basename(drawing))
        start = os.path.join(default_output_dir(self.settings.value("output_dir", "")),
                             f"{base}{OUTPUT_SUFFIX}{ext.lower()}")
        kind = "DWG" if ext.lower() == ".dwg" else "DXF"
        while True:
            chosen, _ = QFileDialog.getSaveFileName(self, "Save Result As", start,
                                                    f"{kind} files (*{ext.lower()})")
            if not chosen:
                return None
            path, problem = check_output_path(drawing, chosen)
            if problem:
                QMessageBox.warning(self, "Choose Another Name", problem)
                start = chosen
                continue
            self.settings.setValue("output_dir", os.path.dirname(path))
            return path

    def _start_run(self):
        if self._problem() or self._running():
            return
        output = self.ask_output_path()
        if not output:
            self.set_status("Cancelled — no output location chosen.")
            return
        self.start_run(output)

    def start_run(self, output_path: str, wait: bool = False):
        import pipeline
        room, bldg, floor = self.columns()
        request = pipeline.RunRequest(
            df=self.df, drawing_path=self.drawing_edit.text(), output_path=output_path,
            room_col=room, building_col=bldg, floor_col=floor,
            building_id=self.building_edit.text().strip(),
        )
        self.result = None
        self._fill_table([])
        self.summary.setText("Running…")
        is_dwg = request.drawing_path.lower().endswith(".dwg")
        self.progress.setRange(0, 7 if is_dwg else 6)
        self.progress.setValue(0)
        self.log("─" * 60, "INFO")
        self.worker = RunWorker(request)
        self.worker.log.connect(self.log)
        self.worker.step.connect(self._on_step)
        self.worker.finished_ok.connect(self._on_finished)
        self.worker.stopped.connect(self._on_stopped)
        self.worker.cancelled.connect(self._on_cancelled)
        self.worker.failed.connect(self._on_failed)
        self.worker.finished.connect(self._update_state)
        self.worker.start()
        self._update_state()
        if wait:                                            # tests
            self.worker.wait()
            QApplication.processEvents()

    def _cancel_run(self):
        if self._running():
            self.worker.cancel()
            self.cancel_btn.setEnabled(False)
            self.set_status("Cancelling after the current step…")

    def _on_step(self, text: str, number: int):
        self.progress.setValue(number - 1)
        self.set_status(text)

    def _on_finished(self, result):
        self.result = result
        self.progress.setValue(self.progress.maximum())
        self._fill_table(result.rows)
        self.tabs.setCurrentIndex(0)
        self.set_status(f"Done — {result.created} room layers created.  "
                        f"Saved as {os.path.basename(result.output_path)}")
        self.status.setToolTip(result.output_path)
        QMessageBox.information(self, APP_NAME, f"{result.created} room layers created.\n\n"
                                                f"Saved to:\n{result.output_path}")

    def _on_stopped(self, message: str):
        self._end_run("Stopped — " + message.splitlines()[0], "WARN", message)
        QMessageBox.warning(self, APP_NAME, message)

    def _on_cancelled(self):
        self._end_run("Cancelled — nothing was saved.", "WARN")

    def _on_failed(self, message: str):
        self._end_run("Failed — see the Log tab.", "ERROR", message)
        QMessageBox.critical(self, APP_NAME, message)

    def _end_run(self, status: str, level: str, detail: str | None = None):
        self.progress.setValue(0)
        self.summary.setText("No results.")
        self.log(detail or status, level)
        self.set_status(status)

    # ----------------------------------------------------------- results
    def _fill_table(self, rows):
        self.table.setSortingEnabled(False)
        self.table.setRowCount(len(rows))
        for r, row in enumerate(rows):
            text, color_key = status_label(row)
            for c, value in enumerate((row.room, row.layer, text, row.note)):
                item = QTableWidgetItem(value)
                if c == 2:
                    item.setForeground(self.color(color_key))
                item.setData(Qt.UserRole, row)
                self.table.setItem(r, c, item)
        self.table.setSortingEnabled(True)
        self.table.sortByColumn(0, Qt.AscendingOrder)
        if rows and self.result is not None:
            res = self.result
            checks = sum(1 for x in rows if x.status == "created" and x.needs_check)
            self.summary.setText(
                f"{res.created} created ({checks} to check) · "
                f"{res.count('skipped') + res.count('failed')} skipped/failed · "
                f"{res.count('not in spreadsheet')} labels not in spreadsheet · "
                f"{res.count('not in drawing')} rows not in drawing")
        self._apply_filter()

    def _apply_filter(self, *_):
        name = self.filter_combo.currentText()
        for r in range(self.table.rowCount()):
            row = self.table.item(r, 0).data(Qt.UserRole)
            self.table.setRowHidden(r, not row_matches_filter(row, name))

    # ----------------------------------------------------------- log/status
    def log(self, message: str, level: str = "INFO"):
        key = {"SUCCESS": "success", "WARN": "warn", "ERROR": "error"}.get(level, "text")
        color = THEMES[self.theme][key]
        safe = message.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        self.log_view.appendHtml(f'<span style="color:{color}; white-space:pre">{safe}</span>')

    def set_status(self, text: str):
        self.status.setText(text)

    def closeEvent(self, event):
        if self._running():
            QMessageBox.information(self, APP_NAME, "A run is in progress. Cancel it first.")
            event.ignore()
            return
        if self.loader is not None:
            self.loader.wait()
        event.accept()


def main() -> int:
    app = QApplication.instance() or QApplication([])
    app.setApplicationName(APP_NAME)
    app.setFont(QFont("Segoe UI", 10))
    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
