from __future__ import annotations

import jinja2
import pytest

from mailer import render_row


def test_renders_known_placeholders() -> None:
    assert render_row("Hello {{name}}!", {"name": "Alice"}) == "Hello Alice!"


def test_renders_empty_string_value_as_empty() -> None:
    assert render_row("Value: [{{note}}]", {"note": ""}) == "Value: []"


def test_raises_on_undefined_placeholder() -> None:
    with pytest.raises(jinja2.exceptions.UndefinedError):
        render_row("Hello {{Naem}}!", {"name": "Alice"})
