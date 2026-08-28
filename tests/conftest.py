from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest


@pytest.fixture
def sample_row() -> dict[str, Any]:
    return {"To": "alice@example.com", "name": "Alice", "CC": "bob@example.com, carol@example.com"}


@pytest.fixture
def mock_credential() -> MagicMock:
    credential = MagicMock()
    credential.get_token.return_value = MagicMock(token="fake-token")
    return credential


@pytest.fixture(autouse=True)
def no_sleep(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("time.sleep", lambda *_args, **_kwargs: None)
