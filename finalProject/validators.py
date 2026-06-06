"""
validators.py
-------------
Input validation helpers for the Nutrition-Cost Finder API.

Each function returns either None (valid) or a human-readable error string
(invalid). Callers decide the appropriate HTTP status code — typically 422
for semantically invalid input that is otherwise well-formed.
"""

import re

# BLS Average Prices series IDs always start with "APU"
BLS_SERIES_ID_RE = r"^APU[A-Z0-9]+$"

VALID_SORT_FIELDS = {"protein_per_dollar", "calories_per_dollar", "fiber_per_dollar"}


def validate_series_id(series_id: str) -> str | None:
    """
    Return an error message if series_id is semantically invalid, else None.
    Does not check whether the ID exists in the dataset.

    Valid format: APU followed by alphanumeric characters (e.g. APU0000706111).
    """
    if not re.match(BLS_SERIES_ID_RE, series_id):
        return (
            f"'{series_id}' is not a valid BLS AP series ID. "
            "Expected format: APU followed by alphanumeric characters (e.g. APU0000706111)."
        )
    return None


def validate_fdc_id(fdc_id: str) -> str | None:
    """
    Return an error message if fdc_id is semantically invalid, else None.
    Does not check whether the ID exists in the dataset.

    Valid format: numeric string (e.g. 321358).
    """
    if not fdc_id.isdigit():
        return (
            f"'{fdc_id}' is not a valid FDC ID. "
            "Expected a numeric string (e.g. 321358)."
        )
    return None


def validate_fdc_ids_list(raw: str) -> tuple[list[str], str | None]:
    """
    Parse and validate a comma-separated fdc_ids string.
    Returns (parsed_list, error_message). error_message is None on success.
    """
    parts = [f.strip() for f in raw.split(",") if f.strip()]
    if not parts:
        return [], "fdc_ids must contain at least one ID."
    if len(parts) > 25:
        return [], "Maximum 25 fdc_ids per request."
    invalid = [p for p in parts if not p.isdigit()]
    if invalid:
        return [], f"Non-numeric FDC IDs: {', '.join(invalid)}. All IDs must be numeric strings."
    return parts, None


def validate_years(raw: str) -> tuple[int | None, str | None]:
    """
    Parse and validate the `years` query param.
    Returns (value, error_message). error_message is None on success.
    """
    try:
        val = int(raw)
    except ValueError:
        return None, f"'years' must be an integer, got '{raw}'."
    if val <= 0:
        return None, f"'years' must be a positive integer, got {val}."
    if val > 30:
        return None, f"'years' cannot exceed 30, got {val}."
    return val, None


def validate_sort_by(sort_by: str) -> str | None:
    """
    Return an error message if sort_by is not a recognised metric, else None.
    """
    if sort_by not in VALID_SORT_FIELDS:
        return (
            f"Invalid sort_by '{sort_by}'. "
            f"Must be one of: {', '.join(sorted(VALID_SORT_FIELDS))}."
        )
    return None
