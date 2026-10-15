"""
spreadsheet_loader.py
---------------------
Load CSV / XLS / XLSX spreadsheets with configurable header rows,
normalised column handling, and robust error reporting.

Large Excel files are slow to parse (a 36,000-row workbook takes ~13 s), so
the cleaned result can be cached on disk and reused until the file changes.
"""

from __future__ import annotations

import glob
import hashlib
import os

import pandas as pd

from config import CSV_HEADER_ROW, EXCEL_HEADER_ROW, SPREADSHEET_CACHE_DIR
from utils import normalize_col


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------

class FileLoadError(Exception):
    """Raised when a spreadsheet cannot be loaded."""


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def load_spreadsheet(
    path: str,
    excel_header: int = EXCEL_HEADER_ROW,
    csv_header: int = CSV_HEADER_ROW,
    use_cache: bool = False,
) -> pd.DataFrame:
    """Load a spreadsheet file and return a cleaned DataFrame.

    Parameters
    ----------
    path : str
        File path (must be .csv, .xls, or .xlsx).
    excel_header : int
        0-indexed header row for Excel files (default from config).
    csv_header : int
        0-indexed header row for CSV files (default from config).
    use_cache : bool
        Reuse / store the cleaned result in SPREADSHEET_CACHE_DIR. The cache
        entry is tied to the file's path, size and modification time and to
        the header-row settings, so any change to the file is picked up.

    Returns
    -------
    pd.DataFrame
        Cleaned DataFrame with whitespace-stripped column names and values.

    Raises
    ------
    FileLoadError
        On missing file, unsupported extension, or parse failure.
    """
    if not os.path.isfile(path):
        raise FileLoadError(f"File not found: {path}")

    ext = os.path.splitext(path)[1].lower()

    cache_file = _cache_file(path, excel_header, csv_header) if use_cache else None
    if cache_file and os.path.isfile(cache_file):
        try:
            return pd.read_pickle(cache_file)
        except Exception:
            pass    # unreadable cache entry: fall back to parsing the file

    try:
        if ext == ".csv":
            df = _load_csv(path, csv_header)
        elif ext in (".xls", ".xlsx"):
            df = _load_excel(path, excel_header)
        else:
            raise FileLoadError(
                f"Unsupported file type '{ext}'. "
                "Supported: .csv, .xls, .xlsx"
            )
    except FileLoadError:
        raise
    except Exception as exc:
        raise FileLoadError(f"Failed to read '{os.path.basename(path)}': {exc}") from exc

    df = _clean_dataframe(df)
    if cache_file:
        _store_cache(df, cache_file)
    return df


# ---------------------------------------------------------------------------
# Cache
# ---------------------------------------------------------------------------

def _cache_file(path: str, excel_header: int, csv_header: int) -> str:
    """<cache dir>/<path hash>_<state hash>.pkl for the file's current state."""
    abs_path = os.path.normcase(os.path.abspath(path))
    st = os.stat(abs_path)
    path_key = hashlib.sha1(abs_path.encode("utf-8")).hexdigest()[:16]
    state = f"{st.st_size}|{st.st_mtime_ns}|{excel_header}|{csv_header}|{pd.__version__}"
    state_key = hashlib.sha1(state.encode("utf-8")).hexdigest()[:16]
    return os.path.join(SPREADSHEET_CACHE_DIR, f"{path_key}_{state_key}.pkl")


def _store_cache(df: pd.DataFrame, cache_file: str) -> None:
    """Save *df*, replacing older entries for the same spreadsheet. Best effort."""
    try:
        os.makedirs(SPREADSHEET_CACHE_DIR, exist_ok=True)
        path_key = os.path.basename(cache_file).split("_")[0]
        for old in glob.glob(os.path.join(SPREADSHEET_CACHE_DIR, f"{path_key}_*.pkl")):
            os.remove(old)
        df.to_pickle(cache_file)
    except OSError:
        pass


# ---------------------------------------------------------------------------
# Internal loaders
# ---------------------------------------------------------------------------

def _load_csv(path: str, header: int) -> pd.DataFrame:
    return pd.read_csv(path, header=header, dtype=str, keep_default_na=False)


def _load_excel(path: str, header: int) -> pd.DataFrame:
    return pd.read_excel(
        path, header=header, dtype=str, keep_default_na=False, engine=None,
    )


def _clean_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    """Drop unnamed columns, strip column names and string cell values."""
    # Drop columns with no name
    df = df.loc[:, ~df.columns.astype(str).str.startswith("Unnamed")]

    # Strip column name whitespace
    df.columns = [str(c).strip() for c in df.columns]

    # Strip whitespace from string cells. Checked per value, not per column
    # dtype: pandas 3 reads dtype=str as the "str" dtype, not object.
    df = df.copy()
    for col in df.columns:
        df[col] = df[col].map(lambda v: v.strip() if isinstance(v, str) else v)

    # Drop fully empty rows (keep_default_na=False makes blanks "" rather than NaN)
    def _is_blank(v) -> bool:
        return v is None or (isinstance(v, str) and v == "") or pd.isna(v)

    if len(df.columns):
        blank_rows = pd.concat([df[c].map(_is_blank) for c in df.columns], axis=1).all(axis=1)
        df = df.loc[~blank_rows]

    return df.reset_index(drop=True)


# ---------------------------------------------------------------------------
# Column inspection helpers
# ---------------------------------------------------------------------------

_ROOM_ID_HINTS: set[str] = {
    "room", "room id", "room identifier", "roomid",
    "room number", "room num", "roomnumber", "roomnum",
    "rm", "rm id", "rmid",
    "space", "space id", "spaceid",
}


def get_columns(df: pd.DataFrame) -> list[str]:
    """Return the list of column names."""
    return list(df.columns)


def find_room_id_column_suggestion(columns: list[str]) -> str | None:
    """Return the best-guess room-identifier column, or None."""
    for col in columns:
        if normalize_col(col) in _ROOM_ID_HINTS:
            return col
    return None
