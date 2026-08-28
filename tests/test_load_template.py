from __future__ import annotations

import io

import docx

from mailer import load_template


def test_loads_html_as_utf8_text() -> None:
    raw = b"<p>Hello {{name}}</p>"
    assert load_template("template.html", raw) == "<p>Hello {{name}}</p>"


def test_loads_txt_as_utf8_text() -> None:
    raw = b"Hello {{name}}"
    assert load_template("template.txt", raw) == "Hello {{name}}"


def test_loads_docx_and_converts_to_html() -> None:
    document = docx.Document()
    document.add_paragraph("Hello {{name}}, welcome!")
    buffer = io.BytesIO()
    document.save(buffer)

    html = load_template("template.docx", buffer.getvalue())

    assert "{{name}}" in html
    assert "<p>" in html
