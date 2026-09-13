#!/usr/bin/env python3
"""Check that the frozen inputs still hold the identity recorded for them.

**The source for these digests is ``data/data.md``.** Keeping a second, machine-readable copy
elsewhere would leave it ambiguous which one is authoritative, so this script parses that table
directly rather than duplicating it.

Until 2026-09-12 the digests were recorded but never verified. Recording and verifying are
different acts, and the first does not license the language of the second; this script closes that
gap.

Five checks:

1. ``data/data.md`` parses as expected -- **exactly four rows**, 64 hex digits, integer sizes.
   A parser that silently yields nothing would pass against any repository at all.
2. Each file in ``data/raw/`` matches its recorded SHA-256 and byte size.
3. ``data/raw/`` holds **no file absent from the table**, so an input cannot be added unrecorded.
4. **Cross-checks against pins written by the completed run itself**, which are independent of
   ``data/data.md``: ``bank_annotation.jsonl`` against ``artifacts[...].sha256`` in the run
   manifest, and ``env/uv.lock`` against ``env_pins.uv_lock_sha256``.
5. **Content-addressed comparison with the upstream blobs.** Checks 1-3 establish only that the
   record and the shipped bytes agree with each other -- an integrity check closed inside this
   repository. Comparing against the blob identifiers in ``analysis/freeze-provenance.json`` is
   what establishes that the shipped bytes are the bytes registered upstream. With
   ``--upstream-repo`` the blobs and commit times are checked against a clone as well.

   One input differs in kind: the forensic record's upstream commit is a **relocation**, not the
   run that produced it. For that file, history witnesses content but not age, and the output
   marks the distinction rather than leaving it to be discovered.

Usage:
    python analysis/scripts/verify_data_hashes.py
    python analysis/scripts/verify_data_hashes.py --upstream-repo /path/to/upstream/clone
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
    sha256_of,    upstream_repository_url,
)

#: Start of the `## raw/` section, and the next `## ` heading.
RAW_SECTION_START_RE = re.compile(r"^##\s+raw/")
NEXT_SECTION_RE = re.compile(r"^##\s+")

#: A table row: | `<file>` | `<origin>` | `<sha256>` | <n> bytes | <date> | <licence> |
RAW_ROW_RE = re.compile(
    r"^\|\s*`(?P<name>[^`]+)`\s*\|"
    r"[^|]*\|"
    r"\s*`(?P<sha256>[0-9a-f]{64})`\s*\|"
    r"\s*(?P<size>[\d,]+)\s*bytes\s*\|"
)

#: How many frozen inputs this repository carries. Pinned so a change is noticed.
EXPECTED_RAW_ROWS = 4

#: Non-data files permitted inside `data/raw/`.
RAW_DIR_ALLOWLIST = frozenset({".gitkeep"})


@dataclass(frozen=True)
class RawEntry:
    """One row of the raw table in `data/data.md`."""

    name: str
    sha256: str
    size: int


def parse_raw_table(data_md: Path) -> tuple[RawEntry, ...]:
    """Parse the table in the `## raw/` section of `data/data.md`.

    Raises:
        SystemExit: if the row count differs from what is expected. A parser that silently
            yields nothing would pass against any repository.
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
            f"{data_md}: parsed {len(entries)} rows from the `## raw/` table, expected "
            f"{EXPECTED_RAW_ROWS}. Either the table format changed, or the set of frozen "
            "inputs did"
        )
    return tuple(entries)


def check_raw_files(repo_root: Path, entries: tuple[RawEntry, ...]) -> list[str]:
    """Compare each frozen input against its recorded SHA-256 and size."""
    problems: list[str] = []
    raw_dir = repo_root / "data" / "raw"
    for entry in entries:
        path = raw_dir / entry.name
        if not path.is_file():
            problems.append(f"data/raw/{entry.name}: file is missing")
            continue
        actual_size = path.stat().st_size
        actual_sha = sha256_of(path)
        if actual_size != entry.size:
            problems.append(
                f"data/raw/{entry.name}: size mismatch "
                f"(recorded={entry.size} actual={actual_size})"
            )
        if actual_sha != entry.sha256:
            problems.append(
                f"data/raw/{entry.name}: SHA-256 mismatch "
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
    """Check that `data/raw/` holds no file absent from the table."""
    recorded = {entry.name for entry in entries} | set(RAW_DIR_ALLOWLIST)
    raw_dir = repo_root / "data" / "raw"
    unrecorded = sorted(
        path.name for path in raw_dir.iterdir() if path.name not in recorded
    )
    if unrecorded:
        return [
            f"data/raw/ holds files not recorded in data/data.md: {unrecorded}"
        ]
    return []


def check_upstream_pins(
    repo_root: Path, entries: tuple[RawEntry, ...]
) -> list[str]:
    """Cross-check against the independent pins written by the run manifest."""
    problems: list[str] = []
    manifest: dict[str, Any] = load_json(
        repo_root / "data" / "raw" / "cproper-manifest.json"
    )

    by_name = {entry.name: entry for entry in entries}

    annotation = by_name.get("bank_annotation.jsonl")
    if annotation is None:
        problems.append("data/data.md has no row for bank_annotation.jsonl")
    else:
        pinned = manifest["artifacts"]["bank_annotation.jsonl"]["sha256"]
        if pinned != annotation.sha256:
            problems.append(
                "bank_annotation.jsonl: data/data.md and the manifest pin disagree "
                f"(data.md={annotation.sha256} manifest={pinned})"
            )
        else:
            print(
                "[data-hash] OK bank_annotation.jsonl matches the artifacts pin in "
                "the run manifest"
            )

    lock_path = repo_root / "env" / "uv.lock"
    if not lock_path.is_file():
        problems.append("env/uv.lock is missing")
    else:
        actual = sha256_of(lock_path)
        pinned = manifest["env_pins"]["uv_lock_sha256"]
        if actual != pinned:
            problems.append(
                "env/uv.lock: differs from env_pins.uv_lock_sha256 in the run manifest "
                f"(manifest={pinned} actual={actual})"
            )
        else:
            print(
                f"[data-hash] OK env/uv.lock is the lockfile the run used "
                f"({actual[:12]}…)"
            )
    return problems


def check_frozen_input_provenance(
    repo_root: Path, upstream: Path | None
) -> list[str]:
    """Establish that each frozen input is **the blob of its upstream commit**.

    The checks above compare this repository against its own record, which establishes only that
    the record and the shipped bytes agree. Comparing blob identifiers is what establishes that
    the shipped bytes are the bytes registered upstream. The identifier is content-addressed, so
    this needs neither network access nor git.
    """
    problems: list[str] = []
    provenance = load_json(repo_root / "analysis" / "freeze-provenance.json")

    recorded_paths = set()
    for entry in provenance["frozen_inputs"]:
        shipped = repo_root / entry["shipped_path"]
        recorded_paths.add(Path(entry["shipped_path"]).name)
        if not shipped.is_file():
            problems.append(f"frozen input is missing: {entry['shipped_path']}")
            continue
        actual = git_blob_sha1(shipped.read_bytes())
        if actual != entry["blob_sha1"]:
            problems.append(
                f"{entry['shipped_path']}: blob identifier differs from the record for "
                f"upstream {entry['upstream_commit'][:7]} "
                f"(expected={entry['blob_sha1']} actual={actual})"
            )
            continue
        kind = entry["provenance_kind"]
        marker = (
            "run artifact"
            if kind == "run_artifact"
            else "relocation only: content, not age"
        )
        print(
            f"[data-hash] OK {Path(entry['shipped_path']).name:<28} "
            f"= blob at upstream {entry['upstream_commit'][:7]} ({marker})"
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

    # Every frozen input on disk must also carry a provenance entry.
    raw_dir = repo_root / "data" / "raw"
    shipped_names = {
        path.name
        for path in raw_dir.iterdir()
        if path.is_file() and path.name not in RAW_DIR_ALLOWLIST
    }
    missing = sorted(shipped_names - recorded_paths)
    if missing:
        problems.append(
            f"frozen inputs with no entry in freeze-provenance.json: {missing}"
        )

    if upstream is None:
        print(
            "[data-hash] note: the blob comparison runs offline, but commit dates are "
            f"confirmed by following {upstream_repository_url(repo_root)} "
            "(--upstream-repo turns that into a machine check)"
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
        help="repository root",
    )
    parser.add_argument(
        "--upstream-repo",
        type=Path,
        default=None,
        help=(
            "a clone of the upstream repository; when given, the blobs and commit times of "
            "the frozen inputs are checked against it too (the default path is offline)"
        ),
    )
    args = parser.parse_args(argv)
    repo_root: Path = args.repo_root

    data_md = repo_root / "data" / "data.md"
    if not data_md.is_file():
        _die(f"the source of the digests is missing: {data_md}")

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

    print("[data-hash] OK: the frozen inputs match the record in data/data.md")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
