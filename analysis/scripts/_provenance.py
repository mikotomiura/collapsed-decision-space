"""Shared helpers for the provenance checks.

Used by `verify_data_hashes.py` and `verify_threshold_freeze.py` to establish which upstream
commit a shipped file's bytes came from, without network access and without running git. A git
blob identifier is content-addressed, so the whole argument rests on one property: identical
bytes produce an identical identifier.

The git helpers below are used only when `--upstream-repo` is supplied; the default path is
offline.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def git_blob_sha1(data: bytes) -> str:
    """Compute the blob identifier git would assign to this content, without invoking git."""
    header = f"blob {len(data)}\0".encode()
    return hashlib.sha1(header + data, usedforsecurity=False).hexdigest()


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        data: dict[str, Any] = json.load(handle)
    return data


def to_utc(iso: str) -> str:
    """Normalise git's ``%cI`` (ISO with offset) to the same Z notation the records use."""
    return (
        datetime.fromisoformat(iso)
        .astimezone(timezone.utc)
        .strftime("%Y-%m-%dT%H:%M:%SZ")
    )


def git(repo: Path, *args: str) -> tuple[int, str]:
    """Invoke git read-only against an upstream clone."""
    proc = subprocess.run(  # noqa: S603
        ["git", "-C", str(repo), *args],
        capture_output=True,
        text=True,
        check=False,
    )
    return proc.returncode, proc.stdout.strip()


def check_upstream_blob(
    upstream: Path, commit: str, upstream_path: str, expected_blob: str
) -> list[str]:
    """Check that the blob at that path and commit upstream is the one recorded."""
    code, blob = git(upstream, "rev-parse", f"{commit}:{upstream_path}")
    if code != 0:
        return [f"--upstream-repo: cannot resolve {commit[:7]}:{upstream_path}"]
    if blob != expected_blob:
        return [
            f"upstream blob at {commit[:7]}:{upstream_path} differs from the record "
            f"(recorded={expected_blob} upstream={blob})"
        ]
    return []


def check_upstream_commit_time(
    upstream: Path, commit: str, expected_utc: str
) -> list[str]:
    """Check that the upstream commit time is the one recorded."""
    code, committed_at = git(upstream, "log", "-1", "--format=%cI", commit)
    if code != 0:
        return [f"--upstream-repo: cannot read the commit time of {commit[:7]}"]
    if to_utc(committed_at) != expected_utc:
        return [
            f"commit time of {commit[:7]} differs from the record "
            f"(recorded={expected_utc} upstream={to_utc(committed_at)})"
        ]
    return []


def upstream_repository_url(repo_root: Path) -> str:
    """Return the upstream repository URL, for a diagnostic line rather than for a check.

    The URL used to live in ``analysis/freeze-provenance.json``. It moved out when that file was
    sealed: a repository URL names its owner, and a sealed file has to be shippable to an anonymous
    review unchanged, so that the reviewer's copy and the deposited copy are the same bytes.
    Nothing about the freeze depends on this string, so a missing file yields a description rather
    than an error.
    """
    links = repo_root / "analysis" / "upstream-links.json"
    if not links.is_file():
        return "the upstream repository"
    return str(load_json(links).get("repository", "the upstream repository"))
