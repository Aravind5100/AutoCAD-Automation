"""
ui.py
-----
Tkinter-based GUI for the AutoCAD Room Annotation tool.
Manages the full workflow:
  Step 1 - File selection (spreadsheet + DWG)
  Step 2 - Column selection (room, building and floor columns)
  Step 3 - Preview & run the update process
  Step 4 - Display summary results
"""

import os
import threading
import time
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

import pythoncom

from config import OUTPUT_SUFFIX
from config import ROOM_KEY_SEPARATOR, ROOM_LAYER_DEFAULT
from utils import (
    detect_building_column,
    detect_floor_column,
    extract_building_id,
    filter_dataframe_by_building,
    build_room_key,
)


# ---------------------------------------------------------------------------
# Colour palette
# ---------------------------------------------------------------------------
BG_DARK = "#1e1e2e"
BG_PANEL = "#2a2a3e"
BG_CARD = "#313145"
FG_PRIMARY = "#cdd6f4"
FG_SECONDARY = "#a6adc8"
FG_ACCENT = "#89b4fa"
FG_SUCCESS = "#a6e3a1"
FG_WARN = "#fab387"
FG_ERROR = "#f38ba8"
BTN_BG = "#585b70"
BTN_ACTIVE = "#6c7086"
ENTRY_BG = "#45475a"
SCROLLBAR_BG = "#45475a"


def _preload_libraries():
    """Import pandas / openpyxl / ezdxf in the background (first import is slow)."""
    try:
        import ezdxf  # noqa: F401
        import openpyxl  # noqa: F401
        import pandas  # noqa: F401
    except Exception:
        pass    # a real import error surfaces when the library is used


class AppUI:
    """Main application window."""

    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("AutoCAD Room Annotation Tool")
        self.root.geometry("880x820")
        self.root.minsize(780, 700)
        self.root.configure(bg=BG_DARK)

        # State
        self._spreadsheet_path = tk.StringVar()
        self._dwg_path = tk.StringVar()
        self._room_id_col = tk.StringVar()
        self._building_col = tk.StringVar()
        self._floor_col = tk.StringVar()
        self._building_id = tk.StringVar()
        self._df = None
        self._columns: list[str] = []
        self._running = False
        self._last_output_dir: str | None = None
        self._loading = False

        self._build_ui()

        # Warm up the heavy libraries while the user picks files, so loading the
        # spreadsheet and the first run don't pay for it
        threading.Thread(target=_preload_libraries, daemon=True).start()

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self):
        outer = tk.Frame(self.root, bg=BG_DARK, padx=16, pady=12)
        outer.pack(fill=tk.BOTH, expand=True)

        self._build_header(outer)
        self._build_file_section(outer)
        self._build_columns_section(outer)
        self._build_run_section(outer)
        self._build_log_section(outer)

    def _build_header(self, parent):
        header = tk.Frame(parent, bg=BG_DARK)
        header.pack(fill=tk.X, pady=(0, 10))
        tk.Label(header, text="AutoCAD Room Annotation Tool",
                 bg=BG_DARK, fg=FG_ACCENT,
                 font=("Segoe UI", 17, "bold")).pack(side=tk.LEFT)
        tk.Label(header, text="Annotate DWG rooms from spreadsheet data",
                 bg=BG_DARK, fg=FG_SECONDARY,
                 font=("Segoe UI", 9)).pack(side=tk.LEFT, padx=(12, 0), pady=(6, 0))

    def _build_file_section(self, parent):
        card = self._card(parent, "Step 1 -- Select Files")

        # Spreadsheet row
        r1 = tk.Frame(card, bg=BG_CARD)
        r1.pack(fill=tk.X, pady=(0, 6))
        tk.Label(r1, text="Spreadsheet:", bg=BG_CARD, fg=FG_PRIMARY,
                 font=("Segoe UI", 9, "bold"), width=14, anchor="w").pack(side=tk.LEFT)
        tk.Entry(r1, textvariable=self._spreadsheet_path, bg=ENTRY_BG, fg=FG_PRIMARY,
                 insertbackground=FG_PRIMARY, relief=tk.FLAT, font=("Segoe UI", 9),
                 state="readonly").pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 6))
        self._btn(r1, "Browse...", self._browse_spreadsheet).pack(side=tk.LEFT)

        # DWG row
        r2 = tk.Frame(card, bg=BG_CARD)
        r2.pack(fill=tk.X, pady=(0, 6))
        tk.Label(r2, text="AutoCAD DWG:", bg=BG_CARD, fg=FG_PRIMARY,
                 font=("Segoe UI", 9, "bold"), width=14, anchor="w").pack(side=tk.LEFT)
        tk.Entry(r2, textvariable=self._dwg_path, bg=ENTRY_BG, fg=FG_PRIMARY,
                 insertbackground=FG_PRIMARY, relief=tk.FLAT, font=("Segoe UI", 9),
                 state="readonly").pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 6))
        self._btn(r2, "Browse...", self._browse_dwg).pack(side=tk.LEFT)

        # Building ID display
        r3 = tk.Frame(card, bg=BG_CARD)
        r3.pack(fill=tk.X)
        tk.Label(r3, text="Building ID:", bg=BG_CARD, fg=FG_PRIMARY,
                 font=("Segoe UI", 9, "bold"), width=14, anchor="w").pack(side=tk.LEFT)
        self._building_lbl = tk.Label(r3, textvariable=self._building_id,
                                      bg=BG_CARD, fg=FG_SUCCESS,
                                      font=("Segoe UI", 10, "bold"))
        self._building_lbl.pack(side=tk.LEFT)

    def _build_columns_section(self, parent):
        card = self._card(parent, "Step 2 -- Configure Columns")

        # Room Identifier dropdown
        self._room_id_combo = self._column_row(card, "Room Identifier:", self._room_id_col)

        # Building Identifier column dropdown
        self._building_col_combo = self._column_row(card, "Building Column:", self._building_col)

        # Floor Code column dropdown
        self._floor_col_combo = self._column_row(card, "Floor Column:", self._floor_col)

        self._style_combobox()

        # What gets written
        sep = ROOM_KEY_SEPARATOR
        tk.Label(
            card,
            text=(f"Each matched room gets an outline copy and a key text on layer "
                  f"{ROOM_LAYER_DEFAULT}\n"
                  f"key = [Building]{sep}[Floor]{sep}[Room]   e.g.  0132{sep}01{sep}101"),
            bg=BG_CARD, fg=FG_SECONDARY, font=("Segoe UI", 9), justify=tk.LEFT,
        ).pack(anchor="w", pady=(4, 0))
        self._key_example = tk.Label(card, text="", bg=BG_CARD, fg=FG_SUCCESS,
                                     font=("Consolas", 9), justify=tk.LEFT)
        self._key_example.pack(anchor="w")
        for var in (self._room_id_col, self._building_col, self._floor_col):
            var.trace_add("write", lambda *_: self._update_key_example())

    def _column_row(self, card, label: str, variable: tk.StringVar) -> ttk.Combobox:
        row = tk.Frame(card, bg=BG_CARD)
        row.pack(fill=tk.X, pady=(0, 6))
        tk.Label(row, text=label, bg=BG_CARD, fg=FG_PRIMARY, width=16, anchor="w",
                 font=("Segoe UI", 9, "bold")).pack(side=tk.LEFT, padx=(0, 8))
        combo = ttk.Combobox(row, textvariable=variable, state="disabled",
                             font=("Segoe UI", 9), width=30)
        combo.pack(side=tk.LEFT)
        return combo

    def _update_key_example(self):
        """Show the layer name the first spreadsheet row would get."""
        cols = (self._building_col.get(), self._floor_col.get(), self._room_id_col.get())
        if self._df is None or self._df.empty or not all(c in self._df.columns for c in cols):
            self._key_example.configure(text="")
            return
        row = self._df.iloc[0]
        key = build_room_key(row[cols[0]], row[cols[1]], row[cols[2]])
        self._key_example.configure(
            text=f"First row -> {key}" if key else "First row -> (a value is empty)")

    def _build_run_section(self, parent):
        row = tk.Frame(parent, bg=BG_DARK)
        row.pack(fill=tk.X, pady=(6, 4))

        self._run_btn = tk.Button(
            row, text="Run Annotation", command=self._on_run,
            bg=FG_ACCENT, fg=BG_DARK,
            activebackground="#74c7ec", activeforeground=BG_DARK,
            font=("Segoe UI", 10, "bold"),
            relief=tk.FLAT, padx=20, pady=6, cursor="hand2",
        )
        self._run_btn.pack(side=tk.LEFT)

        self._progress = ttk.Progressbar(row, mode="indeterminate", length=200)
        self._progress.pack(side=tk.LEFT, padx=(16, 0))

        self._status_lbl = tk.Label(row, text="", bg=BG_DARK, fg=FG_SECONDARY,
                                    font=("Segoe UI", 9))
        self._status_lbl.pack(side=tk.LEFT, padx=(10, 0))

    def _build_log_section(self, parent):
        card = self._card(parent, "Log / Results", expand=True)

        text_frame = tk.Frame(card, bg=BG_CARD)
        text_frame.pack(fill=tk.BOTH, expand=True)

        scrollbar = ttk.Scrollbar(text_frame)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        self._log_text = tk.Text(
            text_frame, bg=BG_PANEL, fg=FG_PRIMARY,
            font=("Consolas", 9), relief=tk.FLAT, wrap=tk.WORD,
            state=tk.DISABLED, yscrollcommand=scrollbar.set,
        )
        self._log_text.pack(fill=tk.BOTH, expand=True)
        scrollbar.config(command=self._log_text.yview)

        self._log_text.tag_configure("INFO", foreground=FG_PRIMARY)
        self._log_text.tag_configure("SUCCESS", foreground=FG_SUCCESS)
        self._log_text.tag_configure("WARN", foreground=FG_WARN)
        self._log_text.tag_configure("ERROR", foreground=FG_ERROR)
        self._log_text.tag_configure("HEADER", foreground=FG_ACCENT,
                                     font=("Consolas", 9, "bold"))

        btn_row = tk.Frame(card, bg=BG_CARD)
        btn_row.pack(fill=tk.X, pady=(6, 0))
        self._btn(btn_row, "Clear Log", self._clear_log, small=True).pack(side=tk.RIGHT)

    # ------------------------------------------------------------------
    # Widget helpers
    # ------------------------------------------------------------------

    def _card(self, parent, title: str, expand: bool = False) -> tk.Frame:
        fill_mode = tk.BOTH if expand else tk.X
        wrapper = tk.LabelFrame(
            parent, text=f"  {title}  ",
            bg=BG_PANEL, fg=FG_ACCENT,
            font=("Segoe UI", 9, "bold"),
            relief=tk.GROOVE, bd=1, padx=10, pady=8,
        )
        wrapper.pack(fill=fill_mode, expand=expand, pady=(0, 8))
        inner = tk.Frame(wrapper, bg=BG_CARD, padx=10, pady=8)
        inner.pack(fill=tk.BOTH, expand=True)
        return inner

    def _btn(self, parent, text: str, command, small: bool = False) -> tk.Button:
        return tk.Button(
            parent, text=text, command=command,
            bg=BTN_BG, fg=FG_PRIMARY,
            activebackground=BTN_ACTIVE, activeforeground=FG_PRIMARY,
            font=("Segoe UI", 8 if small else 9),
            relief=tk.FLAT,
            padx=8 if small else 12, pady=2 if small else 4,
            cursor="hand2",
        )

    def _style_combobox(self):
        style = ttk.Style()
        style.theme_use("clam")
        style.configure("TCombobox",
                        fieldbackground=ENTRY_BG, background=BTN_BG,
                        foreground=FG_PRIMARY, arrowcolor=FG_PRIMARY,
                        selectbackground=ENTRY_BG, selectforeground=FG_PRIMARY)
        style.configure("TScrollbar", background=SCROLLBAR_BG,
                        troughcolor=BG_PANEL, arrowcolor=FG_SECONDARY)
        style.configure("TProgressbar", background=FG_ACCENT, troughcolor=BG_PANEL)

    # ------------------------------------------------------------------
    # File browsing
    # ------------------------------------------------------------------

    def _browse_spreadsheet(self):
        path = filedialog.askopenfilename(
            title="Select Spreadsheet",
            filetypes=[
                ("Spreadsheet files", "*.csv *.xls *.xlsx"),
                ("CSV files", "*.csv"),
                ("Excel files", "*.xls *.xlsx"),
                ("All files", "*.*"),
            ],
        )
        if not path:
            return
        self._spreadsheet_path.set(path)
        self._load_spreadsheet_columns(path)

    def _browse_dwg(self):
        path = filedialog.askopenfilename(
            title="Select AutoCAD Drawing",
            filetypes=[
                ("AutoCAD files", "*.dwg *.dxf"),
                ("DWG files", "*.dwg"),
                ("DXF files", "*.dxf"),
                ("All files", "*.*"),
            ],
        )
        if not path:
            return
        self._dwg_path.set(path)
        self._log("DWG file selected: " + path, tag="INFO")

        bid = extract_building_id(path)
        self._building_id.set(bid)
        self._log(f"Detected Building Identifier: {bid}", tag="SUCCESS")
        self._set_status(f"Building: {bid}")

    # ------------------------------------------------------------------
    # Spreadsheet column loading
    # ------------------------------------------------------------------

    def _load_spreadsheet_columns(self, path: str, background: bool = True):
        """Load *path* (on a worker thread unless *background* is False)."""
        self._loading = True
        self._set_status("Loading spreadsheet... (large files take a while the first time)")
        self._log(f"Loading spreadsheet: {path}", tag="INFO")
        if background:
            threading.Thread(target=self._load_spreadsheet_worker,
                             args=(path, True), daemon=True).start()
        else:
            self._load_spreadsheet_worker(path, False)

    def _load_spreadsheet_worker(self, path: str, from_thread: bool):
        from spreadsheet_loader import FileLoadError, load_spreadsheet

        start = time.monotonic()
        try:
            df = load_spreadsheet(path, use_cache=True)
        except FileLoadError as exc:
            result = lambda err=exc: self._on_spreadsheet_failed(err)
        else:
            elapsed = time.monotonic() - start
            result = lambda: self._on_spreadsheet_loaded(df, elapsed)
        if from_thread:
            self.root.after(0, result)
        else:
            result()

    def _on_spreadsheet_failed(self, exc):
        self._loading = False
        self._log(f"ERROR: {exc}", tag="ERROR")
        self._set_status("Spreadsheet could not be loaded.")
        messagebox.showerror("File Load Error", str(exc))

    def _on_spreadsheet_loaded(self, df, elapsed: float):
        from spreadsheet_loader import find_room_id_column_suggestion, get_columns

        self._loading = False
        self._df = df
        self._columns = get_columns(df)
        self._log(f"Loaded {len(df)} rows, {len(self._columns)} columns "
                  f"in {elapsed:.1f} s.", tag="SUCCESS")
        self._set_status(f"Spreadsheet loaded -- {len(self._columns)} columns.")

        # Room Identifier dropdown
        self._room_id_combo.configure(state="readonly", values=self._columns)
        suggestion = find_room_id_column_suggestion(self._columns)
        if suggestion:
            self._room_id_col.set(suggestion)
            self._log(f"Auto-detected Room Identifier column: '{suggestion}'", tag="SUCCESS")
        elif self._columns:
            self._room_id_col.set(self._columns[0])

        # Building column dropdown
        self._building_col_combo.configure(state="readonly", values=self._columns)
        bld_suggestion = detect_building_column(self._columns)
        if bld_suggestion:
            self._building_col.set(bld_suggestion)
            self._log(f"Auto-detected Building column: '{bld_suggestion}'", tag="SUCCESS")
        elif self._columns:
            self._building_col.set(self._columns[0])

        # Floor column dropdown
        self._floor_col_combo.configure(state="readonly", values=self._columns)
        floor_suggestion = detect_floor_column(self._columns)
        if floor_suggestion:
            self._floor_col.set(floor_suggestion)
            self._log(f"Auto-detected Floor column: '{floor_suggestion}'", tag="SUCCESS")
        else:
            self._floor_col.set("")
            self._log("No Floor column detected -- please choose it in Step 2.", tag="WARN")

        self._update_key_example()

    # ------------------------------------------------------------------
    # Run button
    # ------------------------------------------------------------------

    def _on_run(self):
        if self._running:
            return
        if self._loading:
            messagebox.showinfo("Please Wait", "The spreadsheet is still loading.")
            return

        if not self._spreadsheet_path.get():
            messagebox.showwarning("Missing Input", "Please select a spreadsheet file.")
            return
        if not self._dwg_path.get():
            messagebox.showwarning("Missing Input", "Please select an AutoCAD DWG file.")
            return
        if self._df is None:
            messagebox.showwarning("Missing Input", "Spreadsheet not loaded yet.")
            return

        room_id_col = self._room_id_col.get()
        if not room_id_col:
            messagebox.showwarning("Missing Input", "Please select the Room Identifier column.")
            return

        building_col = self._building_col.get()
        if not building_col:
            messagebox.showwarning("Missing Input", "Please select the Building Identifier column.")
            return

        floor_col = self._floor_col.get()
        if not floor_col:
            messagebox.showwarning("Missing Input", "Please select the Floor column.")
            return

        if len({room_id_col, building_col, floor_col}) < 3:
            messagebox.showwarning(
                "Check Columns",
                "Room, Building and Floor must be three different columns.",
            )
            return

        output_path = self._ask_output_path(self._dwg_path.get())
        if not output_path:
            self._log("Run cancelled -- no output location chosen.", tag="WARN")
            return

        self._set_running(True)
        thread = threading.Thread(
            target=self._run_annotation,
            args=(
                self._dwg_path.get(),
                self._df.copy(),
                room_id_col,
                building_col,
                floor_col,
                output_path,
            ),
            daemon=True,
        )
        thread.start()

    def _ask_output_path(self, input_path: str) -> str | None:
        """Ask where to save the annotated drawing. Returns None if cancelled.

        The dialog never starts in the input drawing's folder, and the
        original drawing itself is refused as a target.
        """
        base, ext = os.path.splitext(os.path.basename(input_path))
        ext = ext.lower()
        kind = "DWG" if ext == ".dwg" else "DXF"

        initial_dir = self._last_output_dir
        if not initial_dir or not os.path.isdir(initial_dir):
            documents = os.path.join(os.path.expanduser("~"), "Documents")
            initial_dir = documents if os.path.isdir(documents) else os.path.expanduser("~")

        input_norm = os.path.normcase(os.path.abspath(input_path))
        while True:
            path = filedialog.asksaveasfilename(
                title="Save Annotated Drawing As",
                initialdir=initial_dir,
                initialfile=f"{base}{OUTPUT_SUFFIX}{ext}",
                defaultextension=ext,
                filetypes=[(f"{kind} files", f"*{ext}")],
                confirmoverwrite=True,
            )
            if not path:
                return None
            if os.path.splitext(path)[1].lower() != ext:
                path += ext
            if os.path.normcase(os.path.abspath(path)) == input_norm:
                messagebox.showerror(
                    "Choose Another Name",
                    "The original drawing cannot be overwritten.\n"
                    "Please choose a different file name or folder.",
                )
                initial_dir = os.path.dirname(path)
                continue
            self._last_output_dir = os.path.dirname(path)
            return path

    def _run_annotation(self, dwg_path, df, room_id_col, building_col,
                        floor_col, output_path):
        """Worker thread: full annotation pipeline."""
        from autocad_scanner import AutoCADError, scan_drawing
        from polygon_matcher import associate_texts_with_polygons, match_rooms
        from annotation_writer import write_room_layers
        from dwg_converter import (
            ConversionError, dwg_to_dxf, dxf_doc_to_dwg, make_work_dir, remove_work_dir,
        )

        pythoncom.CoInitialize()
        work_dir = make_work_dir()   # intermediate files only; deleted below
        try:
            self._log("=" * 56, tag="HEADER")
            self._log("Starting AutoCAD Room Annotation", tag="HEADER")
            self._log("=" * 56, tag="HEADER")
            self._log(f"Output will be saved to: {output_path}", tag="INFO")

            # --- Phase 0: DWG -> DXF conversion (if needed) ---
            is_dwg = dwg_path.lower().endswith(".dwg")
            if is_dwg:
                self._set_status("Converting DWG to DXF...")
                self._log("Converting DWG -> DXF via AutoCAD...", tag="INFO")
                try:
                    dxf_path = dwg_to_dxf(dwg_path, work_dir, log_fn=self._log)
                except ConversionError as exc:
                    self._log(f"Conversion ERROR: {exc}", tag="ERROR")
                    self._set_status("Error -- DWG conversion failed.")
                    self._dialog("error", "Conversion Error", str(exc))
                    return
            else:
                dxf_path = dwg_path

            # --- Phase 1: Building validation ---
            building_id = extract_building_id(dwg_path)
            self._log(f"Building Identifier: {building_id}", tag="INFO")

            self._set_status(f"Filtering rows for building {building_id}...")
            self._log(f"Filtering spreadsheet by building column '{building_col}' = {building_id}...", tag="INFO")
            filtered_df = filter_dataframe_by_building(df, building_col, building_id)

            if filtered_df.empty:
                self._log(
                    f"No spreadsheet rows match building {building_id}. Update cancelled.",
                    tag="ERROR",
                )
                self._set_status(f"Stopped -- no rows for building {building_id}.")
                self._dialog(
                    "warning",
                    "No Matching Rows",
                    f"No spreadsheet rows match building {building_id}.\n"
                    "Update cancelled.",
                )
                return

            self._log(
                f"  Rows after filter: {len(filtered_df)} (of {len(df)} total)",
                tag="SUCCESS",
            )

            # --- Phase 2: Scan DXF ---
            self._set_status("Scanning drawing (ezdxf)...")
            self._log("Scanning DXF for room texts and polygons...", tag="INFO")
            scan = scan_drawing(dxf_path, log_fn=self._log)

            if not scan.room_texts:
                self._log(
                    "WARNING: No room identifiers found in the drawing.",
                    tag="WARN",
                )
                self._set_status("Stopped -- no rooms detected.")
                return

            # --- Phase 3: Associate texts with polygons ---
            self._set_status("Associating texts with room polygons...")
            self._log("Associating room texts with polygons...", tag="INFO")
            associations = associate_texts_with_polygons(
                scan.room_texts, scan.polygons, log_fn=self._log,
            )

            # --- Phase 4: Match with spreadsheet ---
            self._set_status("Matching rooms to spreadsheet data...")
            self._log("Matching rooms to spreadsheet...", tag="INFO")
            summary = match_rooms(
                scan.room_texts, associations, filtered_df,
                room_id_col, [building_col, floor_col, room_id_col],
            )

            # --- Preview ---
            self._log("\nPre-write preview:", tag="HEADER")
            self._log(f"  Building             : {building_id}")
            self._log(f"  Room texts found     : {summary.total_texts}")
            self._log(f"  Polygons found       : {len(scan.polygons)}")
            self._log(f"  Texts with polygon   : {summary.texts_with_polygon}")
            self._log(f"  Texts without polygon: {summary.texts_without_polygon}")
            self._log(f"  Spreadsheet rows     : {summary.total_sheet_rows}")
            self._log(f"  Matched rooms        : {summary.matched_count}", tag="SUCCESS")
            unmatched_count = len(summary.unmatched_drawing)
            if unmatched_count:
                self._log(f"  Unmatched drawing    : {unmatched_count}", tag="WARN")
                for uid in summary.unmatched_drawing[:10]:
                    self._log(f"    - {uid}", tag="WARN")
                if unmatched_count > 10:
                    self._log(f"    ... and {unmatched_count - 10} more", tag="WARN")

            if summary.matched_count == 0:
                self._log(
                    "WARNING: No rooms matched. Check Room Identifier values.",
                    tag="WARN",
                )
                self._set_status("Stopped -- no matches found.")
                return

            # --- Phase 5: Write room layers to in-memory DXF ---
            self._set_status("Writing room keys...")
            self._log(f"Writing room outlines and keys to layer {ROOM_LAYER_DEFAULT}...", tag="INFO")
            annotated_dxf_doc, inserted = write_room_layers(
                scan.doc,               # reuse the drawing the scanner already read
                summary.results,
                scan.room_texts,
                building_col,
                floor_col,
                room_id_col,
                building_id,
                scan.existing_annotation_room_ids,
                log_fn=self._log,
            )

            # --- Phase 5b: Convert annotated DXF to DWG (no intermediate file) ---
            if is_dwg:
                self._set_status("Converting to DWG...")
                self._log("Converting annotated DXF -> DWG...", tag="INFO")
                try:
                    output_path = dxf_doc_to_dwg(annotated_dxf_doc, output_path, work_dir, log_fn=self._log)
                except ConversionError as exc:
                    self._log(f"DXF->DWG conversion failed: {exc}", tag="ERROR")
                    self._set_status("Error -- DXF->DWG conversion failed.")
                    self._dialog("error", "Conversion Error", str(exc))
                    return
            else:
                # If input was DXF, save the annotated DXF
                self._log(f"Saving annotated DXF: {output_path}", tag="INFO")
                try:
                    annotated_dxf_doc.saveas(output_path)
                except Exception as exc:
                    self._log(f"Failed to save annotated DXF: {exc}", tag="ERROR")
                    self._set_status("Error -- could not save output.")
                    self._dialog("error", "Save Error", f"Could not save:\n{output_path}\n\n{exc}")
                    return

            # --- Phase 6: Summary ---
            self._log("\n" + "=" * 56, tag="HEADER")
            self._log("SUMMARY", tag="HEADER")
            self._log("=" * 56, tag="HEADER")
            self._log(f"  Building             : {building_id}")
            self._log(f"  Rows after filter    : {len(filtered_df)}")
            self._log(f"  Room texts found     : {summary.total_texts}")
            self._log(f"  Polygons found       : {len(scan.polygons)}")
            self._log(f"  Text-polygon links   : {summary.texts_with_polygon}")
            self._log(f"  Matched rooms        : {summary.matched_count}", tag="SUCCESS")
            self._log(
                f"  Unmatched rooms      : {unmatched_count}",
                tag="WARN" if unmatched_count else "INFO",
            )
            self._log(f"  Rooms written        : {inserted}", tag="SUCCESS")
            self._log(f"  Output file          : {output_path}", tag="SUCCESS")
            self._log("=" * 56, tag="HEADER")

            self._set_status(f"Done -- {inserted} rooms written.")
            self._dialog(
                "info",
                "Complete",
                f"Room keys complete!\n\n"
                f"Building        : {building_id}\n"
                f"Polygon links   : {summary.texts_with_polygon}\n"
                f"Matched rooms   : {summary.matched_count}\n"
                f"Rooms written   : {inserted} (layer {ROOM_LAYER_DEFAULT})\n"
                f"Output saved to :\n{output_path}",
            )

        except AutoCADError as exc:
            self._log(f"AutoCAD ERROR: {exc}", tag="ERROR")
            self._set_status("Error -- see log.")
            self._dialog("error", "AutoCAD Error", str(exc))

        except Exception as exc:
            self._log(f"Unexpected error: {exc}", tag="ERROR")
            self._set_status("Unexpected error -- see log.")
            self._dialog("error", "Error", f"An unexpected error occurred:\n{exc}")

        finally:
            remove_work_dir(work_dir)
            self._set_running(False)
            pythoncom.CoUninitialize()

    # ------------------------------------------------------------------
    # UI state helpers (thread-safe)
    # ------------------------------------------------------------------

    def _dialog(self, kind: str, title: str, message: str):
        """Show a message box from any thread (Tk calls must run on the main thread)."""
        show = {"info": messagebox.showinfo,
                "warning": messagebox.showwarning,
                "error": messagebox.showerror}[kind]
        self.root.after(0, lambda: show(title, message))

    def _set_running(self, running: bool):
        def _update():
            self._running = running
            state = tk.DISABLED if running else tk.NORMAL
            self._run_btn.configure(state=state)
            if running:
                self._progress.start(12)
            else:
                self._progress.stop()
        self.root.after(0, _update)

    def _set_status(self, text: str):
        self.root.after(0, lambda: self._status_lbl.configure(text=text))

    def _log(self, message: str, tag: str = "INFO"):
        def _append():
            self._log_text.configure(state=tk.NORMAL)
            self._log_text.insert(tk.END, message + "\n", tag)
            self._log_text.see(tk.END)
            self._log_text.configure(state=tk.DISABLED)
        self.root.after(0, _append)

    def _clear_log(self):
        self._log_text.configure(state=tk.NORMAL)
        self._log_text.delete("1.0", tk.END)
        self._log_text.configure(state=tk.DISABLED)
