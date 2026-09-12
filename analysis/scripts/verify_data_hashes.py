#!/usr/bin/env python3
"""凍結入力が ``data/data.md`` に記録された同一性を保っていることを検査する.

**hash の SSOT は ``data/data.md`` である。** 機械可読な複製ファイルを別に置くと、
人が読む provenance と機械が読む pin のどちらが正かが曖昧になるので、二重管理しない。
本スクリプトはその表を**パースして**照合する。

``data/data.md`` は 2026-09-12 時点で hash を**記録しただけ**で、照合はしていなかった
(``B-P1A-4``)。記録と照合は別の行為であり、記録だけで「検証した」と書くのは
``feedback_checker_handed_target_is_not_checked`` と同型である。本スクリプトが
その差を埋める。

検査する 5 つ:

1. ``data/data.md`` の ``## raw/`` 表が**想定どおりパースできる** (行数・64 桁 hex・
   サイズ整数)。表が壊れたら黙って 0 件で通る経路を塞ぐ。
2. ``data/raw/`` の各ファイルの SHA-256 とサイズが表と一致する。
3. ``data/raw/`` に**表に無いファイルが無い** (記録漏れの検出)。
4. **実走 manifest が持つ独立 pin との交差照合** — 自分の記録同士の照合で閉じないために、
   ``data/raw/cproper-manifest.json`` が持つ pin と突き合わせる:
     - ``bank_annotation.jsonl`` の SHA-256 ⇔ ``artifacts[...].sha256``
     - ``env/uv.lock`` の SHA-256 ⇔ ``env_pins.uv_lock_sha256``
5. **上流 blob との content-addressed 照合** — 1〜3 は「``data/data.md`` の記録と出荷物が
   一致する」ことしか言わない (repo 内で閉じた integrity check)。``analysis/freeze-provenance.json``
   の ``frozen_inputs`` が記録する **上流 commit の blob SHA-1** と突き合わせることで、
   同梱されている凍結入力が**上流に登録された bytes そのもの**であることまで言える。
   ``--upstream-repo`` を渡すと、上流の clone に対して blob と commit 日時も検査する。

   ★ ``es3-verdict-forensic.json`` だけは上流 commit が **実走ではなく移設**の commit である
   (``provenance_kind = "relocation"``)。この 1 件について git 履歴は記録の産出時刻を証言しない。
   検査はその区別を出力に明示する。

使い方:
    python analysis/scripts/verify_data_hashes.py
    python analysis/scripts/verify_data_hashes.py --upstream-repo /path/to/ERRE-Sandbox
"""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _provenance import (  # noqa: E402
    check_upstream_blob,
    check_upstream_commit_time,
    git_blob_sha1,
    load_json,
    sha256_of,
)

#: `## raw/` 節の開始と、次の `## ` 見出し。
RAW_SECTION_START_RE = re.compile(r"^##\s+raw/")
NEXT_SECTION_RE = re.compile(r"^##\s+")

#: 表の行: | `<file>` | `<origin>` | `<sha256>` | <n> bytes | <date> | <licence> |
RAW_ROW_RE = re.compile(
    r"^\|\s*`(?P<name>[^`]+)`\s*\|"
    r"[^|]*\|"
    r"\s*`(?P<sha256>[0-9a-f]{64})`\s*\|"
    r"\s*(?P<size>[\d,]+)\s*bytes\s*\|"
)

#: この repo が凍結入力として抱えているファイル数。増減したら気づけるように pin する。
EXPECTED_RAW_ROWS = 4

#: `data/raw/` に置くことを許す非データファイル。
RAW_DIR_ALLOWLIST = frozenset({".gitkeep"})


@dataclass(frozen=True)
class RawEntry:
    """`data/data.md` の raw 表 1 行."""

    name: str
    sha256: str
    size: int


def parse_raw_table(data_md: Path) -> tuple[RawEntry, ...]:
    """`data/data.md` の `## raw/` 節の表をパースする.

    Raises:
        SystemExit: 行数が想定と違うとき (パース失敗で空になった検査器は恒真になる)。
    """
    entries: list[RawEntry] = []
    in_section = False
    for line in data_md.read_text(encoding="utf-8").splitlines():
        if RAW_SECTION_START_RE.match(line):
            in_section = True
            continue
        if in_section and NEXT_SECTION_RE.match(line):
            break
        if not in_section:
            continue
        match = RAW_ROW_RE.match(line)
        if match is None:
            continue
        entries.append(
            RawEntry(
                name=match.group("name"),
                sha256=match.group("sha256"),
                size=int(match.group("size").replace(",", "")),
            )
        )

    if len(entries) != EXPECTED_RAW_ROWS:
        _die(
            f"{data_md}: `## raw/` 表からパースできた行が {len(entries)} 件で、"
            f"想定の {EXPECTED_RAW_ROWS} 件と違う。"
            "表の書式が変わったか、凍結入力が増減している"
        )
    return tuple(entries)


def check_raw_files(repo_root: Path, entries: tuple[RawEntry, ...]) -> list[str]:
    """各凍結入力の SHA-256 とサイズを照合する."""
    problems: list[str] = []
    raw_dir = repo_root / "data" / "raw"
    for entry in entries:
        path = raw_dir / entry.name
        if not path.is_file():
            problems.append(f"data/raw/{entry.name}: ファイルが無い")
            continue
        actual_size = path.stat().st_size
        actual_sha = sha256_of(path)
        if actual_size != entry.size:
            problems.append(
                f"data/raw/{entry.name}: サイズ不一致 "
                f"(recorded={entry.size} actual={actual_size})"
            )
        if actual_sha != entry.sha256:
            problems.append(
                f"data/raw/{entry.name}: SHA-256 不一致 "
                f"(recorded={entry.sha256} actual={actual_sha})"
            )
        if actual_size == entry.size and actual_sha == entry.sha256:
            print(
                f"[data-hash] OK {entry.name:<28} "
                f"{entry.sha256[:12]}… / {entry.size:,} bytes"
            )
    return problems


def check_no_unrecorded_files(
    repo_root: Path, entries: tuple[RawEntry, ...]
) -> list[str]:
    """`data/raw/` に表へ載っていないファイルが無いことを確かめる."""
    recorded = {entry.name for entry in entries} | set(RAW_DIR_ALLOWLIST)
    raw_dir = repo_root / "data" / "raw"
    unrecorded = sorted(
        path.name for path in raw_dir.iterdir() if path.name not in recorded
    )
    if unrecorded:
        return [
            f"data/raw/ に data/data.md へ記録されていないファイルがある: "
            f"{unrecorded}"
        ]
    return []


def check_upstream_pins(
    repo_root: Path, entries: tuple[RawEntry, ...]
) -> list[str]:
    """完了済み実走の manifest が持つ独立 pin と交差照合する."""
    problems: list[str] = []
    manifest: dict[str, Any] = load_json(
        repo_root / "data" / "raw" / "cproper-manifest.json"
    )

    by_name = {entry.name: entry for entry in entries}

    annotation = by_name.get("bank_annotation.jsonl")
    if annotation is None:
        problems.append("data/data.md に bank_annotation.jsonl の行が無い")
    else:
        pinned = manifest["artifacts"]["bank_annotation.jsonl"]["sha256"]
        if pinned != annotation.sha256:
            problems.append(
                "bank_annotation.jsonl: data/data.md と manifest の pin が食い違う "
                f"(data.md={annotation.sha256} manifest={pinned})"
            )
        else:
            print(
                "[data-hash] OK bank_annotation.jsonl は実走 manifest の "
                "artifacts pin と一致"
            )

    lock_path = repo_root / "env" / "uv.lock"
    if not lock_path.is_file():
        problems.append("env/uv.lock が無い")
    else:
        actual = sha256_of(lock_path)
        pinned = manifest["env_pins"]["uv_lock_sha256"]
        if actual != pinned:
            problems.append(
                "env/uv.lock: 実走 manifest の env_pins.uv_lock_sha256 と違う "
                f"(manifest={pinned} actual={actual})"
            )
        else:
            print(
                f"[data-hash] OK env/uv.lock は実走時の lockfile と同一 "
                f"({actual[:12]}…)"
            )
    return problems


def check_frozen_input_provenance(
    repo_root: Path, upstream: Path | None
) -> list[str]:
    """凍結入力が**上流 commit の blob そのもの**であることを確かめる.

    1〜4 の検査は ``data/data.md`` という自分の記録との照合であり、
    「記録と出荷物が一致する」ことしか言わない。ここで上流の blob 識別子と突き合わせて
    初めて「同梱物が上流に登録された bytes である」と言える。blob 識別子は内容アドレスなので
    ネットワークも git も要らない。
    """
    problems: list[str] = []
    provenance = load_json(repo_root / "analysis" / "freeze-provenance.json")

    recorded_paths = set()
    for entry in provenance["frozen_inputs"]:
        shipped = repo_root / entry["shipped_path"]
        recorded_paths.add(Path(entry["shipped_path"]).name)
        if not shipped.is_file():
            problems.append(f"凍結入力が無い: {entry['shipped_path']}")
            continue
        actual = git_blob_sha1(shipped.read_bytes())
        if actual != entry["blob_sha1"]:
            problems.append(
                f"{entry['shipped_path']}: blob SHA-1 が上流 "
                f"{entry['upstream_commit'][:7]} の記録と違う "
                f"(expected={entry['blob_sha1']} actual={actual})"
            )
            continue
        kind = entry["provenance_kind"]
        marker = "run artifact" if kind == "run_artifact" else "★ relocation のみ"
        print(
            f"[data-hash] OK {Path(entry['shipped_path']).name:<28} "
            f"= 上流 {entry['upstream_commit'][:7]} の blob ({marker})"
        )
        if upstream is not None:
            problems.extend(
                check_upstream_blob(
                    upstream,
                    entry["upstream_commit"],
                    entry["upstream_path"],
                    entry["blob_sha1"],
                )
            )
            problems.extend(
                check_upstream_commit_time(
                    upstream, entry["upstream_commit"], entry["upstream_commit_utc"]
                )
            )

    # data/data.md に載っている凍結入力は、来歴側にも 1 件残らず載っていること。
    raw_dir = repo_root / "data" / "raw"
    shipped_names = {
        path.name
        for path in raw_dir.iterdir()
        if path.is_file() and path.name not in RAW_DIR_ALLOWLIST
    }
    missing = sorted(shipped_names - recorded_paths)
    if missing:
        problems.append(
            f"freeze-provenance.json の frozen_inputs に来歴が無い凍結入力: {missing}"
        )

    if upstream is None:
        print(
            "[data-hash] note: 上流 blob との照合はオフラインで済むが、commit の日付は "
            f"{provenance['upstream']['repository']} を辿って確認する "
            "(--upstream-repo で機械検査できる)"
        )
    return problems


def _die(message: str) -> None:
    print(f"[data-hash] FAIL: {message}", file=sys.stderr)
    raise SystemExit(1)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=Path(__file__).resolve().parents[2],
        help="repo root",
    )
    parser.add_argument(
        "--upstream-repo",
        type=Path,
        default=None,
        help=(
            "上流 ERRE-Sandbox の clone。渡すと凍結入力の blob と commit 日時を"
            "上流に対しても検査する (既定はオフライン検査のみ)"
        ),
    )
    args = parser.parse_args(argv)
    repo_root: Path = args.repo_root

    data_md = repo_root / "data" / "data.md"
    if not data_md.is_file():
        _die(f"hash の SSOT が無い: {data_md}")

    entries = parse_raw_table(data_md)
    print(f"[data-hash] {len(entries)} rows parsed from data/data.md (## raw/)")

    problems: list[str] = []
    problems.extend(check_raw_files(repo_root, entries))
    problems.extend(check_no_unrecorded_files(repo_root, entries))
    problems.extend(check_upstream_pins(repo_root, entries))
    problems.extend(check_frozen_input_provenance(repo_root, args.upstream_repo))

    if problems:
        print("[data-hash] FAIL", file=sys.stderr)
        for problem in problems:
            print(f"  - {problem}", file=sys.stderr)
        return 1

    print("[data-hash] OK: 凍結入力は data/data.md の記録と一致する")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
