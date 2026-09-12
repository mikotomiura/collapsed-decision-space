"""来歴検査の共有部品 (`verify_data_hashes.py` / `verify_threshold_freeze.py`).

同梱ファイルが上流の公開リポジトリの **どの commit の bytes なのか**を、
ネットワークも git の実行も無しで確かめるための道具を置く。git の blob 識別子は
内容アドレスなので、**bytes が同じなら識別子も同じ**という性質だけに依っている。

`--upstream-repo` を渡したときにだけ使う git 補助もここに置く (既定はオフライン)。
"""

from __future__ import annotations

import hashlib
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def git_blob_sha1(data: bytes) -> str:
    """git が同じ内容に付ける blob 識別子を、git 無しで計算する."""
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
    """git の ``%cI`` (offset 付き ISO) を、記録側と同じ Z 表記へ正規化する."""
    return (
        datetime.fromisoformat(iso)
        .astimezone(timezone.utc)
        .strftime("%Y-%m-%dT%H:%M:%SZ")
    )


def git(repo: Path, *args: str) -> tuple[int, str]:
    """上流 clone に対して読み取り専用の git を呼ぶ."""
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
    """上流の当該 commit で、そのパスの blob が記録どおりであることを確かめる."""
    code, blob = git(upstream, "rev-parse", f"{commit}:{upstream_path}")
    if code != 0:
        return [f"--upstream-repo: {commit[:7]}:{upstream_path} を解決できない"]
    if blob != expected_blob:
        return [
            f"上流 {commit[:7]}:{upstream_path} の blob が記録と違う "
            f"(recorded={expected_blob} upstream={blob})"
        ]
    return []


def check_upstream_commit_time(
    upstream: Path, commit: str, expected_utc: str
) -> list[str]:
    """上流 commit の時刻が記録どおりであることを確かめる."""
    code, committed_at = git(upstream, "log", "-1", "--format=%cI", commit)
    if code != 0:
        return [f"--upstream-repo: commit {commit[:7]} の日時を取得できない"]
    if to_utc(committed_at) != expected_utc:
        return [
            f"commit {commit[:7]} の日時が記録と違う "
            f"(recorded={expected_utc} upstream={to_utc(committed_at)})"
        ]
    return []
