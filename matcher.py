"""
matcher.py
----------
Matches room identifiers found in an AutoCAD drawing against rows
in a spreadsheet DataFrame, using normalized, case-insensitive comparison.
"""

from dataclasses import dataclass, field

import pandas as pd

from utils import normalize_room_id


@dataclass
class MatchResult:
    """Holds the outcome of matching one AutoCAD room to spreadsheet data.

    Attributes
    ----------
    drawing_room_id : str
        The original room identifier text found in the AutoCAD drawing.
    sheet_room_id : str
        The raw room identifier value from the spreadsheet row (may differ
        in casing/spacing from the drawing value).
    row_data : dict[str, str]
        Key-value pairs for the selected columns from the matched row.
    matched : bool
        True if a spreadsheet row was found for this room identifier.
    """

    drawing_room_id: str
    sheet_room_id: str = ""
    row_data: dict[str, str] = field(default_factory=dict)
    matched: bool = False


@dataclass
class MatchSummary:
    """Aggregate statistics produced by :func:`match_rooms`.

    Attributes
    ----------
    total_drawing_rooms : int
        Total unique room identifiers detected in the AutoCAD drawing.
    total_sheet_rooms : int
        Total rows in the spreadsheet (after deduplication on room id).
    matched_count : int
        Number of drawing rooms successfully matched to a spreadsheet row.
    unmatched_drawing : list[str]
        Drawing room IDs that had no matching spreadsheet row.
    unmatched_sheet : list[str]
        Spreadsheet room IDs that had no corresponding drawing room.
    results : list[MatchResult]
        Detailed per-room match results.
    """

    total_drawing_rooms: int = 0
    total_sheet_rooms: int = 0
    matched_count: int = 0
    unmatched_drawing: list[str] = field(default_factory=list)
    unmatched_sheet: list[str] = field(default_factory=list)
    results: list[MatchResult] = field(default_factory=list)


def match_rooms(
    drawing_room_ids: list[str],
    df: pd.DataFrame,
    room_id_column: str,
    selected_columns: list[str],
) -> MatchSummary:
    """Match AutoCAD room identifiers to spreadsheet rows.

    Matching is performed using normalized (lowercase + stripped) keys so
    that casing and extra whitespace differences are ignored.

    Parameters
    ----------
    drawing_room_ids : list[str]
        Room identifiers extracted from the AutoCAD drawing (original text).
    df : pd.DataFrame
        Spreadsheet data (rows as returned by :func:`file_loader.load_spreadsheet`).
    room_id_column : str
        The exact column name in *df* that holds room identifiers.
    selected_columns : list[str]
        Column names from *df* whose values should be included in annotation text.

    Returns
    -------
    MatchSummary
        Populated summary containing per-room :class:`MatchResult` objects and
        aggregate statistics.
    """
    summary = MatchSummary()

    # Build a normalized lookup: norm_key -> (original_value, Series row)
    sheet_lookup: dict[str, tuple[str, pd.Series]] = {}
    for _, row in df.iterrows():
        raw_val = str(row[room_id_column])
        norm_key = normalize_room_id(raw_val)
        if norm_key and norm_key not in sheet_lookup:
            sheet_lookup[norm_key] = (raw_val, row)

    summary.total_sheet_rooms = len(sheet_lookup)

    # Deduplicate drawing rooms while preserving order
    seen: set[str] = set()
    unique_drawing_ids: list[str] = []
    for rid in drawing_room_ids:
        norm = normalize_room_id(rid)
        if norm not in seen:
            seen.add(norm)
            unique_drawing_ids.append(rid)

    summary.total_drawing_rooms = len(unique_drawing_ids)

    matched_sheet_keys: set[str] = set()

    for drawing_id in unique_drawing_ids:
        norm_drawing = normalize_room_id(drawing_id)
        result = MatchResult(drawing_room_id=drawing_id)

        if norm_drawing in sheet_lookup:
            original_sheet_val, row = sheet_lookup[norm_drawing]
            result.sheet_room_id = original_sheet_val
            result.matched = True
            result.row_data = _extract_row_data(row, selected_columns)
            matched_sheet_keys.add(norm_drawing)
            summary.matched_count += 1
        else:
            summary.unmatched_drawing.append(drawing_id)

        summary.results.append(result)

    # Record spreadsheet rooms with no corresponding drawing room
    for norm_key, (raw_val, _) in sheet_lookup.items():
        if norm_key not in matched_sheet_keys:
            summary.unmatched_sheet.append(raw_val)

    return summary


def _extract_row_data(row: pd.Series, columns: list[str]) -> dict[str, str]:
    """Extract values for *columns* from *row* as a string dict.

    Parameters
    ----------
    row : pd.Series
        A single DataFrame row.
    columns : list[str]
        Column names to extract.

    Returns
    -------
    dict[str, str]
        Maps each column name to its string value from the row.
    """
    data: dict[str, str] = {}
    for col in columns:
        if col in row.index:
            val = row[col]
            data[col] = "" if pd.isna(val) or val == "" else str(val)
    return data
