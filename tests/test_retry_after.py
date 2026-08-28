from __future__ import annotations

from mailer import MAX_RETRY_WAIT_SECONDS, parse_retry_after


def test_integer_seconds_are_used() -> None:
    assert parse_retry_after("12", fallback=5) == 12


def test_absent_header_falls_back() -> None:
    assert parse_retry_after(None, fallback=5) == 5


def test_http_date_header_falls_back_instead_of_crashing() -> None:
    assert parse_retry_after("Wed, 21 Oct 2015 07:28:00 GMT", fallback=5) == 5


def test_garbage_header_falls_back() -> None:
    assert parse_retry_after("soon", fallback=5) == 5


def test_empty_header_falls_back() -> None:
    assert parse_retry_after("", fallback=5) == 5


def test_negative_value_is_floored_at_zero() -> None:
    assert parse_retry_after("-3", fallback=5) == 0


def test_absurdly_long_wait_is_capped() -> None:
    assert parse_retry_after("99999", fallback=5) == MAX_RETRY_WAIT_SECONDS
