from __future__ import annotations

from mailer import (
    build_message,
    normalize_columns,
    render_row,
    render_text,
    resolve_attachment_paths,
)


def test_render_row_escapes_html_in_values() -> None:
    rendered = render_row("<p>Hi {{name}}</p>", {"name": "<script>alert(1)</script>"})
    assert "<script>" not in rendered
    assert "&lt;script&gt;" in rendered


def test_render_row_leaves_template_markup_intact() -> None:
    rendered = render_row("<p><b>Hi {{name}}</b></p>", {"name": "Alice"})
    assert rendered == "<p><b>Hi Alice</b></p>"


def test_render_row_escapes_ampersand_in_value() -> None:
    assert render_row("{{company}}", {"company": "Ben & Jerry"}) == "Ben &amp; Jerry"


def test_render_text_does_not_escape() -> None:
    assert render_text("{{company}}", {"company": "Ben & Jerry"}) == "Ben & Jerry"


def test_subject_is_not_html_escaped() -> None:
    row = {"To": "a@example.com", "company": "Ben & Jerry"}
    col_map = normalize_columns({"To", "company"})
    message, _ = build_message(row, "News from {{company}}", "<p>hi</p>", col_map)
    assert message["subject"] == "News from Ben & Jerry"


def test_body_is_html_escaped() -> None:
    row = {"To": "a@example.com", "company": "Ben & Jerry"}
    col_map = normalize_columns({"To", "company"})
    message, _ = build_message(row, "Subject", "<p>{{company}}</p>", col_map)
    assert message["body"]["content"] == "<p>Ben &amp; Jerry</p>"


def test_attachment_paths_are_not_html_escaped() -> None:
    paths = resolve_attachment_paths("/docs/{{folder}}/report.pdf", {"folder": "R&D"})
    assert paths == ["/docs/R&D/report.pdf"]
