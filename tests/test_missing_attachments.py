from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from mailer import build_message, normalize_columns, validate_attachments


def test_build_message_refuses_to_send_with_a_missing_attachment(tmp_path: Path) -> None:
    row = {"To": "alice@example.com", "Attachments": str(tmp_path / "nope.pdf")}
    col_map = normalize_columns({"To", "Attachments"})
    with pytest.raises(ValueError, match="nope.pdf"):
        build_message(row, "Subject", "Body", col_map)


def test_build_message_succeeds_when_attachment_exists(tmp_path: Path) -> None:
    attachment = tmp_path / "report.pdf"
    attachment.write_text("data")
    row = {"To": "alice@example.com", "Attachments": str(attachment)}
    col_map = normalize_columns({"To", "Attachments"})
    message, large_paths = build_message(row, "Subject", "Body", col_map)
    assert [a["name"] for a in message["attachments"]] == ["report.pdf"]
    assert large_paths == []


def test_validate_attachments_reports_missing_paths_per_row(tmp_path: Path) -> None:
    present = tmp_path / "here.pdf"
    present.write_text("data")
    df = pd.DataFrame(
        {
            "To": ["a@example.com", "b@example.com"],
            "Attachments": [str(present), str(tmp_path / "gone.pdf")],
        }
    )
    col_map = normalize_columns({"To", "Attachments"})

    problems = validate_attachments(df, col_map)

    assert len(problems) == 1
    assert "Row 2" in problems[0]
    assert "gone.pdf" in problems[0]


def test_validate_attachments_clean_when_all_present(tmp_path: Path) -> None:
    present = tmp_path / "here.pdf"
    present.write_text("data")
    df = pd.DataFrame({"To": ["a@example.com"], "Attachments": [str(present)]})
    col_map = normalize_columns({"To", "Attachments"})
    assert validate_attachments(df, col_map) == []


def test_validate_attachments_ignores_rows_without_attachments() -> None:
    df = pd.DataFrame({"To": ["a@example.com"], "Attachments": [""]})
    col_map = normalize_columns({"To", "Attachments"})
    assert validate_attachments(df, col_map) == []
