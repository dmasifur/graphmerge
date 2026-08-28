from __future__ import annotations

from pathlib import Path

import pytest

import campaign_log


def _entry(index: int) -> campaign_log.CampaignLogEntry:
    return campaign_log.CampaignLogEntry(
        row_index=index, recipient=f"user{index}@example.com", success=True
    )


def test_append_does_not_read_back_existing_entries(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Appending must be O(1): it may not load-and-rewrite the whole log each time."""
    monkeypatch.setattr(campaign_log, "LOG_DIR", tmp_path / "logs")
    campaign_log.append_entries("deadbeef", [_entry(0)])

    def explode(_hash: str) -> list[campaign_log.CampaignLogEntry]:
        raise AssertionError("append_entries must not re-read the existing log")

    monkeypatch.setattr(campaign_log, "load_log", explode)
    campaign_log.append_entries("deadbeef", [_entry(1)])

    monkeypatch.undo()
    monkeypatch.setattr(campaign_log, "LOG_DIR", tmp_path / "logs")
    assert campaign_log.sent_row_indices("deadbeef") == {0, 1}


def test_truncated_trailing_line_does_not_destroy_the_log(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(campaign_log, "LOG_DIR", tmp_path / "logs")
    campaign_log.append_entries("deadbeef", [_entry(0), _entry(1)])

    path = campaign_log._log_path("deadbeef")
    with path.open("a", encoding="utf-8") as f:
        f.write('{"row_index": 2, "recipi')

    assert campaign_log.sent_row_indices("deadbeef") == {0, 1}
