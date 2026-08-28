from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

from mailer import CampaignConfig, send_via_graph


def make_response(
    status_code: int,
    json_data: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
) -> MagicMock:
    response = MagicMock()
    response.status_code = status_code
    response.headers = headers or {}
    response.json.return_value = json_data or {}
    response.text = "" if json_data is None else str(json_data)
    return response


def make_config() -> CampaignConfig:
    return CampaignConfig(client_id="cid", tenant_id="tid", sender_type="personal")


def test_success_on_200(mock_credential: MagicMock) -> None:
    session = MagicMock()
    session.request.return_value = make_response(200)

    success, detail = send_via_graph(session, mock_credential, {"subject": "hi"}, make_config())

    assert success is True
    assert detail == "Sent"


def test_retries_on_429_then_succeeds(mock_credential: MagicMock) -> None:
    session = MagicMock()
    session.request.side_effect = [
        make_response(429, headers={"Retry-After": "1"}),
        make_response(202),
    ]

    success, detail = send_via_graph(session, mock_credential, {"subject": "hi"}, make_config())

    assert success is True
    assert session.request.call_count == 2


def test_retries_on_503(mock_credential: MagicMock) -> None:
    session = MagicMock()
    session.request.side_effect = [
        make_response(503),
        make_response(200),
    ]

    success, detail = send_via_graph(session, mock_credential, {"subject": "hi"}, make_config())

    assert success is True
    assert session.request.call_count == 2


def test_immediate_failure_on_400(mock_credential: MagicMock) -> None:
    session = MagicMock()
    session.request.return_value = make_response(
        400, json_data={"error": {"message": "Bad request"}}
    )

    success, detail = send_via_graph(session, mock_credential, {"subject": "hi"}, make_config())

    assert success is False
    assert detail == "Bad request"
    assert session.request.call_count == 1


def test_failure_after_exhausted_retries(mock_credential: MagicMock) -> None:
    session = MagicMock()
    session.request.return_value = make_response(429)

    success, detail = send_via_graph(session, mock_credential, {"subject": "hi"}, make_config())

    assert success is False
    assert session.request.call_count == 3


def test_content_type_header_preserved_across_retries(mock_credential: MagicMock) -> None:
    session = MagicMock()
    session.request.side_effect = [
        make_response(503),
        make_response(200),
    ]

    send_via_graph(session, mock_credential, {"subject": "hi"}, make_config())

    for call in session.request.call_args_list:
        assert call.kwargs["headers"]["Content-Type"] == "application/json"
