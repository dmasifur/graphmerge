from __future__ import annotations

import pandas as pd

from mailer import find_missing_placeholders, normalize_columns, validate_recipients


def test_find_missing_placeholders_flags_typo() -> None:
    missing = find_missing_placeholders("Hi {{Naem}}", {"name"})
    assert missing == {"Naem"}


def test_find_missing_placeholders_case_insensitive_match() -> None:
    missing = find_missing_placeholders("Hi {{Name}}", {"name"})
    assert missing == set()


def test_validate_recipients_flags_bad_address() -> None:
    df = pd.DataFrame({"To": ["alice@example.com", "not-an-email"]})
    col_map = normalize_columns({"To"})
    problems = validate_recipients(df, col_map)
    assert len(problems) == 1
    assert "not-an-email" in problems[0]


def test_validate_recipients_flags_missing_recipient() -> None:
    df = pd.DataFrame({"To": ["alice@example.com", ""]})
    col_map = normalize_columns({"To"})
    problems = validate_recipients(df, col_map)
    assert len(problems) == 1
    assert "Row 2" in problems[0]


def test_validate_recipients_clean_data_no_problems() -> None:
    df = pd.DataFrame({"To": ["alice@example.com"], "CC": ["bob@example.com"]})
    col_map = normalize_columns({"To", "CC"})
    assert validate_recipients(df, col_map) == []
