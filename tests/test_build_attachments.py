from __future__ import annotations

import base64
from pathlib import Path

from mailer import build_attachments, classify_attachments, resolve_attachment_paths


def test_resolve_splits_and_renders_paths(tmp_path: Path) -> None:
    raw = "{{dir}}/a.txt; {{dir}}/b.txt"
    paths = resolve_attachment_paths(raw, {"dir": str(tmp_path)})
    assert paths == [f"{tmp_path}/a.txt", f"{tmp_path}/b.txt"]


def test_classify_reports_missing_files(tmp_path: Path) -> None:
    existing = tmp_path / "exists.txt"
    existing.write_text("hi")
    absent = tmp_path / "missing.txt"
    small, large, missing = classify_attachments([str(existing), str(absent)])
    assert small == [str(existing)]
    assert large == []
    assert missing == [str(absent)]


def test_classify_separates_large_files(tmp_path: Path) -> None:
    small_file = tmp_path / "small.bin"
    small_file.write_bytes(b"x" * 100)
    large_file = tmp_path / "large.bin"
    large_file.write_bytes(b"x" * (4 * 1024 * 1024))

    small, large, missing = classify_attachments([str(small_file), str(large_file)])
    assert small == [str(small_file)]
    assert large == [str(large_file)]
    assert missing == []


def test_build_attachments_encodes_content(tmp_path: Path) -> None:
    file_path = tmp_path / "note.txt"
    file_path.write_text("hello world")

    attachments = build_attachments([str(file_path)])

    assert len(attachments) == 1
    attachment = attachments[0]
    assert attachment["name"] == "note.txt"
    assert base64.b64decode(attachment["contentBytes"]) == b"hello world"


def test_build_attachments_multiple_paths_preserve_order(tmp_path: Path) -> None:
    first = tmp_path / "first.txt"
    second = tmp_path / "second.txt"
    first.write_text("1")
    second.write_text("2")

    attachments = build_attachments([str(first), str(second)])

    assert [a["name"] for a in attachments] == ["first.txt", "second.txt"]
