from __future__ import annotations

import pytest

from mailer import build_message, normalize_columns


def test_case_insensitive_recipient_lookup() -> None:
    row = {"to": "alice@example.com"}
    col_map = normalize_columns({"to"})
    message, large_paths = build_message(row, "Subject", "Body", col_map)
    assert message["toRecipients"] == [{"emailAddress": {"address": "alice@example.com"}}]
    assert large_paths == []


def test_email_column_used_when_to_absent() -> None:
    row = {"email": "bob@example.com"}
    col_map = normalize_columns({"email"})
    message, _ = build_message(row, "Subject", "Body", col_map)
    assert message["toRecipients"] == [{"emailAddress": {"address": "bob@example.com"}}]


def test_cc_and_bcc_assembled_and_stripped() -> None:
    row = {
        "To": "alice@example.com",
        "CC": "bob@example.com, carol@example.com",
        "BCC": "dave@example.com",
    }
    col_map = normalize_columns({"To", "CC", "BCC"})
    message, _ = build_message(row, "Subject", "Body", col_map)
    assert message["ccRecipients"] == [
        {"emailAddress": {"address": "bob@example.com"}},
        {"emailAddress": {"address": "carol@example.com"}},
    ]
    assert message["bccRecipients"] == [{"emailAddress": {"address": "dave@example.com"}}]


def test_absent_cc_bcc_produce_no_keys() -> None:
    row = {"To": "alice@example.com"}
    col_map = normalize_columns({"To"})
    message, _ = build_message(row, "Subject", "Body", col_map)
    assert "ccRecipients" not in message
    assert "bccRecipients" not in message


def test_missing_recipient_raises() -> None:
    row = {"name": "Alice"}
    col_map = normalize_columns({"name"})
    with pytest.raises(ValueError, match="Missing 'To' or 'email' value for this row"):
        build_message(row, "Subject", "Body", col_map)


def test_subject_and_body_rendered() -> None:
    row = {"To": "alice@example.com", "name": "Alice"}
    col_map = normalize_columns({"To", "name"})
    message, _ = build_message(row, "Hi {{name}}", "<p>Hello {{name}}</p>", col_map)
    assert message["subject"] == "Hi Alice"
    assert message["body"]["content"] == "<p>Hello Alice</p>"
