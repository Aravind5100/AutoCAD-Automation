"""
spreadsheet_loader.py
---------------------
Load CSV / XLS / XLSX spreadsheets with configurable header rows,
normalised column handling, and robust error reporting.
"""

from __future__ import annotations

import os

import pandas as pd

from config import CSV_HEADER_ROW, EXCEL_HEADER_ROW
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

    return _clean_dataframe(df)


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
