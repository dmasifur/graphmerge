from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path

LOG_DIR = Path(".graphmerge_logs")


@dataclass
class CampaignLogEntry:
    row_index: int
    recipient: str
    success: bool
    detail: str = ""
    timestamp: str = ""


def csv_hash(raw_bytes: bytes) -> str:
    return hashlib.sha256(raw_bytes).hexdigest()


def _log_path(hash_: str) -> Path:
    return LOG_DIR / f"{hash_}.jsonl"


def load_log(hash_: str) -> list[CampaignLogEntry]:
    """Read the campaign log, skipping any line left incomplete by an interrupted run."""
    path = _log_path(hash_)
    if not path.exists():
        return []

    entries = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            entries.append(CampaignLogEntry(**json.loads(line)))
        except (json.JSONDecodeError, TypeError):
            continue
    return entries


def append_entries(hash_: str, new_entries: list[CampaignLogEntry]) -> None:
    """Append entries to this campaign's log.

    One line of JSON per entry, opened in append mode, so cost stays constant
    per email instead of rewriting the whole log on every send. Concurrent
    writers interleave lines rather than clobbering each other's history.
    """
    if not new_entries:
        return

    LOG_DIR.mkdir(exist_ok=True)
    now = datetime.now(UTC).isoformat()
    with _log_path(hash_).open("a", encoding="utf-8") as f:
        for entry in new_entries:
            record = asdict(entry)
            record["timestamp"] = record.get("timestamp") or now
            f.write(json.dumps(record) + "\n")


def sent_row_indices(hash_: str) -> set[int]:
    """Row indices that have already been sent successfully for this campaign."""
    return {e.row_index for e in load_log(hash_) if e.success}


def clear_log(hash_: str) -> None:
    path = _log_path(hash_)
    if path.exists():
        path.unlink()
