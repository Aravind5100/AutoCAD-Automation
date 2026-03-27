"""
file_loader.py
--------------
Handles reading spreadsheet data from CSV, XLS, and XLSX files using pandas.
Returns a cleaned DataFrame and the list of original column names.
"""

import os
from pathlib import Path

import pandas as pd

from utils import normalize_col, EXCEL_HEADER_ROW, CSV_HEADER_ROW


SUPPORTED_EXTENSIONS = {".csv", ".xls", ".xlsx"}


class FileLoadError(Exception):
    """Raised when a spreadsheet file cannot be loaded."""


def load_spreadsheet(
    file_path: str,
    excel_header_row: int | None = None,
    csv_header_row: int | None = None,
) -> pd.DataFrame:
    """Load a CSV, XLS, or XLSX file and return a pandas DataFrame.

    Column names are preserved exactly as they appear in the file.
    All cells are read as strings (object dtype) to avoid type coercion
    issues when comparing room identifiers.

    Parameters
    ----------
    file_path : str
        Absolute or relative path to the spreadsheet file.
    excel_header_row : int or None
        0-indexed row number containing column headers for Excel files.
        Defaults to ``utils.EXCEL_HEADER_ROW`` (2 = 3rd row).
    csv_header_row : int or None
        0-indexed row number containing column headers for CSV files.
        Defaults to ``utils.CSV_HEADER_ROW`` (0 = 1st row).

    Returns
    -------
    pd.DataFrame
        DataFrame with original column names intact.

    Raises
    ------
    FileLoadError
        If the file does not exist, has an unsupported extension, or
        cannot be parsed.
    """
    if excel_header_row is None:
        excel_header_row = EXCEL_HEADER_ROW
    if csv_header_row is None:
        csv_header_row = CSV_HEADER_ROW

    path = Path(file_path)

    if not path.exists():
        raise FileLoadError(f"File not found: {file_path}")

    ext = path.suffix.lower()
    if ext not in SUPPORTED_EXTENSIONS:
        raise FileLoadError(
            f"Unsupported file type '{ext}'. "
            f"Supported types: {', '.join(sorted(SUPPORTED_EXTENSIONS))}"
        )

    try:
        if ext == ".csv":
            df = _load_csv(path, header_row=csv_header_row)
        else:
            df = _load_excel(path, header_row=excel_header_row)
    except FileLoadError:
        raise
    except Exception as exc:
        raise FileLoadError(f"Failed to read '{path.name}': {exc}") from exc

    if df.empty:
        raise FileLoadError(f"The file '{path.name}' is empty or has no data rows.")

    # Drop columns whose name is NaN (happens when header row has blank cells)
    df = df.loc[:, df.columns.notna()]

    # Strip whitespace from column names and all string cells
    df.columns = [str(c).strip() for c in df.columns]
    for col in df.columns:
        df[col] = df[col].map(lambda v: v.strip() if isinstance(v, str) else v)

    return df


def _load_csv(path: Path, header_row: int = 0) -> pd.DataFrame:
    """Try common CSV encodings and return the parsed DataFrame."""
    encodings = ["utf-8-sig", "utf-8", "latin-1", "cp1252"]
    last_exc = None
    for enc in encodings:
        try:
            df = pd.read_csv(
                path, dtype=str, encoding=enc,
                keep_default_na=False, header=header_row,
            )
            return df
        except UnicodeDecodeError as exc:
            last_exc = exc
    raise FileLoadError(
        f"Could not decode '{path.name}' with any known encoding."
    ) from last_exc


def _load_excel(path: Path, header_row: int = 2) -> pd.DataFrame:
    """Load the first sheet of an XLS/XLSX workbook.

    Parameters
    ----------
    path : Path
        Path to the workbook.
    header_row : int
        0-indexed row number that contains column headers.
        Default 2 = 3rd row (common in enterprise Excel exports).
    """
    try:
        df = pd.read_excel(
            path, dtype=str, keep_default_na=False, header=header_row,
        )
        return df
    except Exception as exc:
        raise FileLoadError(f"Could not read Excel file '{path.name}': {exc}") from exc


# ---------------------------------------------------------------------------
# Column inspection helpers
# ---------------------------------------------------------------------------

def get_columns(df: pd.DataFrame) -> list[str]:
    """Return the list of column names as they appear in the DataFrame."""
    return list(df.columns)


def get_column_display_map(df: pd.DataFrame) -> dict[str, str]:
    """Return a dict mapping display label -> original column name.

    The display label is the original column name (shown in the UI).
    This keeps UI display clean while allowing internal lookup by original name.
    """
    return {col: col for col in df.columns}


def find_room_id_column_suggestion(columns: list[str]) -> str | None:
    """Suggest the most likely Room Identifier column from a list of column names.

    Uses normalized comparison against common synonyms. Returns the original
    column name string, or None if no candidate is found.

    Parameters
    ----------
    columns : list[str]
        Original column names from the spreadsheet.

    Returns
    -------
    str or None
        The original column name that best matches a room identifier synonym.
    """
    synonyms = [
        "room identifier",
        "room id",
        "roomid",
        "room number",
        "room no",
        "room num",
        "space id",
        "space identifier",
        "space number",
        "unit id",
        "unit number",
    ]
    for col in columns:
        norm = normalize_col(col)
        if norm in synonyms:
            return col
    return None
