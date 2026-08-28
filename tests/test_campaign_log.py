from __future__ import annotations

from pathlib import Path

import pytest

import campaign_log


def test_csv_hash_is_stable_and_content_sensitive() -> None:
    a = campaign_log.csv_hash(b"a,b\n1,2\n")
    b = campaign_log.csv_hash(b"a,b\n1,2\n")
    c = campaign_log.csv_hash(b"a,b\n1,3\n")
    assert a == b
    assert a != c


def test_load_log_empty_when_no_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(campaign_log, "LOG_DIR", tmp_path / "logs")
    assert campaign_log.load_log("deadbeef") == []


def test_append_and_load_round_trip(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(campaign_log, "LOG_DIR", tmp_path / "logs")
    entries = [
        campaign_log.CampaignLogEntry(row_index=0, recipient="a@example.com", success=True),
        campaign_log.CampaignLogEntry(
            row_index=1, recipient="b@example.com", success=False, detail="oops"
        ),
    ]
    campaign_log.append_entries("deadbeef", entries)

    loaded = campaign_log.load_log("deadbeef")
    assert len(loaded) == 2
    assert campaign_log.sent_row_indices("deadbeef") == {0}


def test_append_accumulates_across_calls(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(campaign_log, "LOG_DIR", tmp_path / "logs")
    campaign_log.append_entries(
        "deadbeef",
        [campaign_log.CampaignLogEntry(row_index=0, recipient="a@example.com", success=True)],
    )
    campaign_log.append_entries(
        "deadbeef",
        [campaign_log.CampaignLogEntry(row_index=1, recipient="b@example.com", success=True)],
    )
    assert campaign_log.sent_row_indices("deadbeef") == {0, 1}


def test_clear_log_removes_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(campaign_log, "LOG_DIR", tmp_path / "logs")
    campaign_log.append_entries(
        "deadbeef",
        [campaign_log.CampaignLogEntry(row_index=0, recipient="a@example.com", success=True)],
    )
    campaign_log.clear_log("deadbeef")
    assert campaign_log.load_log("deadbeef") == []
