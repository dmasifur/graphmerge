from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import requests

from mailer import _upload_large_attachment
from tests.test_send_via_graph import make_response


def _session_with_upload_url(put_side_effect: list[object]) -> MagicMock:
    session = MagicMock()
    session.request.return_value = make_response(
        201, json_data={"uploadUrl": "https://upload.example.com/session"}
    )
    session.put.side_effect = put_side_effect
    return session


def test_chunk_upload_retries_transient_failure(
    tmp_path: Path, mock_credential: MagicMock
) -> None:
    path = tmp_path / "big.bin"
    path.write_bytes(b"x" * 1024)
    session = _session_with_upload_url([make_response(503), make_response(201)])

    ok, detail = _upload_large_attachment(
        session, mock_credential, "https://graph/draft", str(path)
    )

    assert ok is True
    assert session.put.call_count == 2


def test_chunk_upload_retries_network_error(tmp_path: Path, mock_credential: MagicMock) -> None:
    path = tmp_path / "big.bin"
    path.write_bytes(b"x" * 1024)
    session = _session_with_upload_url(
        [requests.ConnectionError("dropped"), make_response(201)]
    )

    ok, _ = _upload_large_attachment(session, mock_credential, "https://graph/draft", str(path))

    assert ok is True
    assert session.put.call_count == 2


def test_chunk_upload_gives_up_after_max_retries(
    tmp_path: Path, mock_credential: MagicMock
) -> None:
    path = tmp_path / "big.bin"
    path.write_bytes(b"x" * 1024)
    session = _session_with_upload_url([make_response(503)] * 5)

    ok, detail = _upload_large_attachment(
        session, mock_credential, "https://graph/draft", str(path)
    )

    assert ok is False
    assert session.put.call_count == 3
    assert "503" in detail


def test_chunk_upload_does_not_retry_client_error(
    tmp_path: Path, mock_credential: MagicMock
) -> None:
    path = tmp_path / "big.bin"
    path.write_bytes(b"x" * 1024)
    session = _session_with_upload_url([make_response(400)] * 5)

    ok, _ = _upload_large_attachment(session, mock_credential, "https://graph/draft", str(path))

    assert ok is False
    assert session.put.call_count == 1


def test_chunk_upload_never_sends_authorization_header(
    tmp_path: Path, mock_credential: MagicMock
) -> None:
    """The upload URL is pre-authenticated; adding a bearer token breaks it."""
    path = tmp_path / "big.bin"
    path.write_bytes(b"x" * 1024)
    session = _session_with_upload_url([make_response(201)])

    _upload_large_attachment(session, mock_credential, "https://graph/draft", str(path))

    for call in session.put.call_args_list:
        assert "Authorization" not in call.kwargs["headers"]
