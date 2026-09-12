#!/usr/bin/env python3
"""Establish, in a form a reader can check, that the thresholds were frozen before the run.

A reader is entitled to ask whether the materiality margin was chosen after seeing the result. The
answer is split into two parts, and their scopes are deliberately not blended.

1. **The values agree.** The frozen constants in the vendored apparatus match the ``thresholds``
   recorded in the completed run's ``verdict.json``. Two of the recorded entries are run parameters
   rather than module constants, and those are compared against the run manifest instead.
2. **The bytes are the same (content-addressed).** Each shipped file that carries a threshold --
   and the whole 69-module apparatus closure -- is shown to be **the blob of the upstream commit**
   named in ``analysis/freeze-provenance.json``, by recomputing the git blob identifier
   (the SHA-1 over a ``blob <size>`` header, a NUL byte, and the content). This needs
   neither network access nor git.

**What the two do not establish**: the commit *dates*. Those are a property of the public upstream
repository, confirmed by following the URLs in ``freeze-provenance.json``. "The thresholds were
frozen before the run" is the conjunction of the values, the bytes and the dates; no one of them
carries it alone. Passing ``--upstream-repo <path>`` turns the third into a machine check against a
clone, and the default path stays offline.

Usage:
    python analysis/scripts/verify_threshold_freeze.py
    python analysis/scripts/verify_threshold_freeze.py --upstream-repo /path/to/upstream/clone
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime
from pathlib import Path
from types import ModuleType
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _provenance import (  # noqa: E402
    check_upstream_blob,
    check_upstream_commit_time,
    git,
    git_blob_sha1,
    load_json,
)

#: Tolerance for float comparison; verdict.json holds values quantised to six decimals.
FLOAT_TOL = 1e-9


def _values_agree(left: Any, right: Any) -> bool:
    if isinstance(left, bool) or isinstance(right, bool):
        return left is right
    if isinstance(left, (int, float)) and isinstance(right, (int, float)):
        return abs(float(left) - float(right)) <= FLOAT_TOL
    return bool(left == right)


def check_apparatus_closure(
    repo_root: Path, provenance: dict[str, Any], upstream: Path | None
) -> list[str]:
    """Establish that every vendored apparatus file is the blob of its upstream commit.

    The manuscript describes the apparatus as an import closure reproduced byte for byte from
    upstream. Checking only the two files that carry thresholds would leave the other sixty-seven
    as an unchecked shadow, so the blob identifier of every file in the closure is compared.
    """
    problems: list[str] = []
    closure = provenance["apparatus_closure"]
    shipped_root = repo_root / closure["shipped_prefix"]
    recorded = {entry["path"] for entry in closure["files"]}

    if len(closure["files"]) != closure["file_count"]:
        problems.append(
            f"apparatus_closure: file_count={closure['file_count']} but the files list "
            f"holds {len(closure['files'])} entries"
        )

    for entry in closure["files"]:
        shipped = shipped_root / entry["path"]
        if not shipped.is_file():
            problems.append(
                f"missing from the apparatus: "
                f"{closure['shipped_prefix']}{entry['path']}"
            )
            continue
        actual = git_blob_sha1(shipped.read_bytes())
        if actual != entry["blob_sha1"]:
            problems.append(
                f"{closure['shipped_prefix']}{entry['path']}: blob identifier differs "
                f"from the record for upstream {closure['upstream_commit'][:7]} "
                f"(expected={entry['blob_sha1']} actual={actual})"
            )
        elif upstream is not None:
            problems.extend(
                check_upstream_blob(
                    upstream,
                    closure["upstream_commit"],
                    closure["upstream_prefix"] + entry["path"],
                    entry["blob_sha1"],
                )
            )

    on_disk = {
        path.relative_to(shipped_root).as_posix()
        for path in shipped_root.rglob("*.py")
    }
    unrecorded = sorted(on_disk - recorded)
    if unrecorded:
        problems.append(
            f"apparatus files with no provenance entry: {unrecorded}. A file added to the "
            "closure must also be recorded in freeze-provenance.json"
        )

    if not problems:
        suffix = "" if upstream is None else " (also checked against an upstream clone)"
        print(
            f"[freeze] closure OK {closure['file_count']} files "
            f"== blobs at upstream {closure['upstream_commit'][:7]}{suffix}"
        )
    return problems


def check_blob_identity(repo_root: Path, provenance: dict[str, Any]) -> list[str]:
    """Establish that a shipped file is the blob of the commit that froze it."""
    problems: list[str] = []
    for entry in provenance["frozen_files"]:
        shipped = repo_root / entry["shipped_path"]
        if not shipped.is_file():
            problems.append(
                f"shipped file is missing: {entry['shipped_path']}"
            )
            continue
        actual = git_blob_sha1(shipped.read_bytes())
        expected = entry["blob_sha1"]
        if actual != expected:
            problems.append(
                f"{entry['shipped_path']}: blob identifier differs from the record for "
                f"freeze commit {entry['freeze_commit'][:7]} "
                f"(expected={expected} actual={actual})"
            )
        else:
            print(
                f"[freeze] blob OK  {entry['shipped_path']} "
                f"== {expected[:12]}… @ {entry['freeze_commit'][:7]} "
                f"({entry['freeze_commit_utc']})"
            )
    return problems


def load_shipped_module(shipped: Path, module_name: str) -> ModuleType:
    """Build a module by evaluating the **shipped bytes** directly.

    ``import_module`` is avoided because a stale ``__pycache__`` can make the imported value
    disagree with the file on disk. That was observed: immediately after restoring a shipped file,
    the disk held ``0.10`` while the import returned ``0.15``. What is evaluated here is the same
    bytes that :func:`check_blob_identity` verified, so the value check and the byte check read
    one source rather than two.
    """
    source = shipped.read_bytes()
    module = ModuleType(module_name)
    module.__file__ = str(shipped)
    module.__package__ = module_name.rpartition(".")[0]
    code = compile(source, str(shipped), "exec")
    # `@dataclass` looks the module up in `sys.modules`, so registering it before exec is
    # required. Registering also means that a module importing another of these reads the same
    # verified bytes.
    sys.modules[module_name] = module
    try:
        exec(code, module.__dict__)  # noqa: S102
    except Exception:
        sys.modules.pop(module_name, None)
        raise
    return module


def check_threshold_values(
    repo_root: Path, provenance: dict[str, Any], verdict: dict[str, Any]
) -> list[str]:
    """Compare the frozen constants with the thresholds recorded in verdict.json."""
    problems: list[str] = []
    apparatus = repo_root / "analysis" / "apparatus"
    if str(apparatus) not in sys.path:
        sys.path.insert(0, str(apparatus))

    thresholds = verdict["thresholds"]
    covered: set[str] = set()

    for entry in provenance["frozen_files"]:
        shipped = repo_root / entry["shipped_path"]
        if not shipped.is_file():
            problems.append(f"shipped file is missing: {entry['shipped_path']}")
            continue
        module = load_shipped_module(shipped, entry["module"])
        for threshold_key, constant_name in entry["threshold_map"].items():
            if threshold_key not in thresholds:
                problems.append(
                    f"verdict.json thresholds has no {threshold_key}"
                )
                continue
            constant_value = getattr(module, constant_name)
            recorded = thresholds[threshold_key]
            covered.add(threshold_key)
            if not _values_agree(constant_value, recorded):
                problems.append(
                    f"MISMATCH {threshold_key}: "
                    f"{entry['module']}.{constant_name}={constant_value} "
                    f"vs verdict.json={recorded}"
                )
            else:
                print(
                    f"[freeze] value OK {threshold_key:>14} = {recorded} "
                    f"({constant_name})"
                )

    uncovered = sorted(set(thresholds) - covered)
    expected_uncovered = sorted(provenance["run_parameter_map"])
    if uncovered != expected_uncovered:
        problems.append(
            "the recorded thresholds not matched against a constant are not the ones "
            f"expected (expected={expected_uncovered} found={uncovered}). Check whether a "
            "threshold was added silently"
        )
    return problems


def check_run_parameters(
    provenance: dict[str, Any], verdict: dict[str, Any], manifest: dict[str, Any]
) -> list[str]:
    """Compare the run parameters with the run section of the manifest."""
    problems: list[str] = []
    thresholds = verdict["thresholds"]
    run = manifest["run"]
    for threshold_key, run_key in provenance["run_parameter_map"].items():
        if not _values_agree(thresholds[threshold_key], run[run_key]):
            problems.append(
                f"MISMATCH {threshold_key}: verdict.json={thresholds[threshold_key]} "
                f"vs manifest.json run.{run_key}={run[run_key]}"
            )
        else:
            print(
                f"[freeze] run   OK {threshold_key:>14} = {run[run_key]} "
                "(manifest.run)"
            )
    return problems


def check_recorded_ordering(provenance: dict[str, Any]) -> list[str]:
    """Check that the recorded freeze times precede the recorded run time.

    This tests the **internal consistency of the record**, not the dates themselves. The dates are
    confirmed against the public upstream repository, which `--upstream-repo` automates.
    """
    problems: list[str] = []
    run_at = datetime.fromisoformat(
        provenance["run_commit"]["commit_utc"].replace("Z", "+00:00")
    )
    for entry in provenance["frozen_files"]:
        froze_at = datetime.fromisoformat(
            entry["freeze_commit_utc"].replace("Z", "+00:00")
        )
        if froze_at >= run_at:
            problems.append(
                f"{entry['shipped_path']}: the recorded freeze time "
                f"{froze_at.isoformat()} is later than the run commit "
                f"{run_at.isoformat()}"
            )
        else:
            delta = run_at - froze_at
            print(
                f"[freeze] recorded-order OK "
                f"{entry['shipped_path'].split('/')[-1]}: frozen {delta} before the run"
            )
    return problems


def check_upstream(upstream: Path, provenance: dict[str, Any]) -> list[str]:
    """Additionally check blobs, dates and ancestry against an upstream clone (optional)."""
    problems: list[str] = []
    run_commit = provenance["run_commit"]["commit"]

    code, _ = git(upstream, "cat-file", "-e", f"{run_commit}^{{commit}}")
    if code != 0:
        return [
            f"--upstream-repo {upstream}: run commit {run_commit[:7]} not found"
        ]

    problems.extend(
        check_upstream_commit_time(
            upstream, run_commit, provenance["run_commit"]["commit_utc"]
        )
    )

    for entry in provenance["frozen_files"]:
        commit = entry["freeze_commit"]
        problems.extend(
            check_upstream_blob(
                upstream, commit, entry["upstream_path"], entry["blob_sha1"]
            )
        )
        problems.extend(
            check_upstream_commit_time(upstream, commit, entry["freeze_commit_utc"])
        )
        code, _ = git(upstream, "merge-base", "--is-ancestor", commit, run_commit)
        if code != 0:
            problems.append(
                f"freeze commit {commit[:7]} is not an ancestor of the run commit "
                f"{run_commit[:7]}"
            )
        else:
            print(
                f"[freeze] upstream OK {commit[:7]} is an ancestor of "
                f"{run_commit[:7]}; blob and time match the record"
            )
    return problems


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
            "a clone of the upstream repository; when given, blobs, commit times and "
            "ancestry are checked against it too (the default path is offline)"
        ),
    )
    args = parser.parse_args(argv)
    repo_root: Path = args.repo_root

    provenance = load_json(repo_root / "analysis" / "freeze-provenance.json")
    verdict = load_json(repo_root / "data" / "raw" / "cproper-verdict.json")
    manifest = load_json(repo_root / "data" / "raw" / "cproper-manifest.json")

    problems: list[str] = []
    problems.extend(check_blob_identity(repo_root, provenance))
    problems.extend(
        check_apparatus_closure(repo_root, provenance, args.upstream_repo)
    )
    problems.extend(check_threshold_values(repo_root, provenance, verdict))
    problems.extend(check_run_parameters(provenance, verdict, manifest))
    problems.extend(check_recorded_ordering(provenance))

    if args.upstream_repo is not None:
        problems.extend(check_upstream(args.upstream_repo, provenance))
    else:
        print(
            "[freeze] note: offline checks only. Commit dates are confirmed by following "
            f"{provenance['upstream']['repository']} "
            "(--upstream-repo turns that into a machine check)"
        )

    if problems:
        print("[freeze] FAIL", file=sys.stderr)
        for problem in problems:
            print(f"  - {problem}", file=sys.stderr)
        return 1

    print("[freeze] OK: values agree and the shipped bytes are the upstream blobs")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
