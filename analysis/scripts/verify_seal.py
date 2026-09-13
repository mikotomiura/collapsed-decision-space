#!/usr/bin/env python3
"""Check that the sealed files are the bytes the seal manifest says they are.

**Read this before relying on it.** This script establishes *internal consistency*: that the files
listed in ``seal/SEAL-MANIFEST.json`` hash to the values recorded there, that the manifest's own
self-hash is correct, and that the set of sealed paths is exactly the set this script expects.

It does **not** establish that the seal is old, or that nobody changed a sealed file and the
manifest together. An author with write access to this repository can do both in one commit, and no
check that lives inside the repository can see that. The external half of the binding is the
deposit: the archive publishes a per-file checksum for every file it holds, readable by anyone
without an account, and ``--witness`` compares the recorded deposit checksums against the same local
files. Only the two halves together say anything about a third party having seen these bytes.

The witness itself is bounded in a way worth stating plainly. Deposit records are editable by their
owner for a period after publication, with the identifier unchanged, so the deposit's timestamps
bound when the files were *last touched*, not when they were first written. The manuscript states
this rather than leaving the reader to discover it.

One further check runs here rather than in a step of its own, because it is part of the same
question. The decision rules exist once, in ``seal/decision-rules.json``; the protocol and the
manuscript carry a *generated* rendering of them between markers, and this script requires both
renderings to be exactly what the sealed file produces. A threshold edited in prose therefore
fails, and a threshold edited in the sealed file fails the hash above. Prose and rules cannot drift
apart, because there is only one of them.

What this establishes: the sealed bytes are internally consistent, the rule text the reader sees is
a function of them, and -- with ``--witness`` -- the bytes are identical to those the deposit holds.
What it does not: when they were written, or that no unreported run preceded them.

Usage:
    python analysis/scripts/verify_seal.py
    python analysis/scripts/verify_seal.py --witness seal/zenodo-witness.json
    python analysis/scripts/verify_seal.py --run-manifest data/raw/primary-manifest.json
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _provenance import load_json, sha256_of  # noqa: E402
from render_decision_rules import check as check_rule_text  # noqa: E402

MANIFEST_SCHEMA: str = "cds-seal-manifest-1"

#: The sealed set, declared here rather than read from the manifest.
#: Taking the list from the document being checked would let a dropped entry pass unnoticed;
#: keeping it here means adding to the seal requires editing the checker, which is the point.
#: There is no separate JSON-Schema file. The evaluator validates the rules structurally and
#: aborts on anything malformed, and the evaluator is itself sealed below; a schema document that
#: nothing executes would add a file to the seal without adding a check to the run.
#:
#: The renderer is sealed for the same reason the evaluator is. A renderer that could be changed
#: after the fact could be taught to emit whatever the manuscript happens to say, and the drift
#: check below would then pass against rules nobody follows.
SEALED_PATHS: tuple[str, ...] = (
    "seal/decision-rules.json",
    "seal/arm-spec.json",
    "seal/protocol.md",
    "analysis/scripts/apply_decision_rules.py",
    "analysis/scripts/check_decision_rules_scope.py",
    "analysis/scripts/render_decision_rules.py",
    "analysis/scripts/verify_seal.py",
    "analysis/freeze-provenance.json",
    "repro.sh",
)

#: How the manifest's self-hash is defined. Stated explicitly because a self-referential hash is
#: ambiguous unless the serialisation is pinned: sort keys, two-space indent, no ASCII escaping,
#: one trailing newline, UTF-8, and the ``self_sha256`` key removed before hashing.
CANONICALISATION: str = (
    "sha256 of json.dumps(manifest_without_self_sha256, sort_keys=True, indent=2, "
    'ensure_ascii=False) + "\\n", encoded as UTF-8'
)


def canonical_self_hash(manifest: dict[str, Any]) -> str:
    """Return the self-hash of ``manifest`` under :data:`CANONICALISATION`."""
    body = {key: value for key, value in manifest.items() if key != "self_sha256"}
    text = json.dumps(body, sort_keys=True, indent=2, ensure_ascii=False) + "\n"
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _die(message: str) -> None:
    print(f"[seal] FAIL: {message}", file=sys.stderr)
    raise SystemExit(1)


def _walk(source: dict[str, Any], dotted: str) -> Any:
    """Read a dotted path out of a nested mapping. A missing step is an error."""
    node: Any = source
    for step in dotted.split("."):
        if not isinstance(node, dict) or step not in node:
            return _MISSING
        node = node[step]
    return node


_MISSING = object()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    repo_root = Path(__file__).resolve().parents[2]
    parser.add_argument("--repo-root", type=Path, default=repo_root)
    parser.add_argument(
        "--witness",
        type=Path,
        help="A recorded deposit witness. Compares the deposit's per-file checksums with "
        "the local sealed files, and reports the latest server-assigned time it carries.",
    )
    parser.add_argument(
        "--run-manifest",
        type=Path,
        help="A run manifest. Checks that it names this seal and that the fields the "
        "arm spec calls not-minor-deviations agree with it.",
    )
    args = parser.parse_args()
    root: Path = args.repo_root

    manifest_path = root / "seal" / "SEAL-MANIFEST.json"
    if not manifest_path.is_file():
        _die(f"the seal manifest is missing: {manifest_path}")
    manifest = load_json(manifest_path)

    if manifest.get("schema") != MANIFEST_SCHEMA:
        _die(f"schema is {manifest.get('schema')!r}, expected {MANIFEST_SCHEMA!r}")

    recorded_self = manifest.get("self_sha256")
    computed_self = canonical_self_hash(manifest)
    if recorded_self != computed_self:
        _die(
            f"the manifest's self_sha256 is {recorded_self!r} but recomputing it under the "
            f"recorded canonicalisation gives {computed_self!r}"
        )

    files = manifest.get("files")
    if not isinstance(files, dict):
        _die("the manifest has no 'files' mapping")

    if set(files) != set(SEALED_PATHS):
        missing = sorted(set(SEALED_PATHS) - set(files))
        extra = sorted(set(files) - set(SEALED_PATHS))
        _die(
            "the sealed set does not match this checker's expectation; "
            f"missing from the manifest: {missing}; not expected: {extra}"
        )

    problems: list[str] = []
    for rel in SEALED_PATHS:
        target = root / rel
        if not target.is_file():
            problems.append(f"{rel}: sealed but not present")
            continue
        actual = sha256_of(target)
        expected = files[rel].get("sha256")
        if actual != expected:
            problems.append(f"{rel}: sha256 {actual} != sealed {expected}")

    if problems:
        print("[seal] FAIL", file=sys.stderr)
        for problem in problems:
            print(f"  - {problem}", file=sys.stderr)
        return 1

    print(f"[seal] OK: {len(SEALED_PATHS)} sealed files match, self-hash verified")

    # The rules are sealed as bytes above. This asks the separate question of whether what a
    # reader reads is those rules: the protocol and the manuscript carry a generated rendering,
    # and it must be the one the sealed file produces.
    drift = check_rule_text(root)
    if drift:
        problems.extend(drift)
    else:
        print("[seal] OK: the rule text in the protocol and the manuscript is generated from "
              "seal/decision-rules.json, not restated beside it")

    if args.witness is not None:
        problems.extend(_check_witness(root, args.witness, files))

    if args.run_manifest is not None:
        problems.extend(_check_run_manifest(root, args.run_manifest, computed_self))

    if problems:
        print("[seal] FAIL", file=sys.stderr)
        for problem in problems:
            print(f"  - {problem}", file=sys.stderr)
        return 1

    return 0


def _check_witness(root: Path, witness_path: Path, files: dict[str, Any]) -> list[str]:
    """Compare a recorded deposit witness with the local sealed files."""
    if not witness_path.is_file():
        return [f"the witness file is missing: {witness_path}"]
    witness = load_json(witness_path)
    entries = witness.get("files")
    if not isinstance(entries, list) or not entries:
        return [f"{witness_path.name}: 'files' must be a non-empty list"]

    problems: list[str] = []
    seen: set[str] = set()
    for entry in entries:
        rel = entry.get("sealed_path")
        checksum = entry.get("checksum")
        if rel is None or checksum is None:
            problems.append(f"{witness_path.name}: an entry lacks sealed_path or checksum")
            continue
        seen.add(rel)
        if rel not in files:
            problems.append(f"{witness_path.name}: {rel} is deposited but not sealed")
            continue
        algo, _, digest = str(checksum).partition(":")
        target = root / rel
        if not target.is_file():
            problems.append(f"{rel}: in the witness but not present locally")
            continue
        try:
            local = hashlib.new(algo, target.read_bytes()).hexdigest()
        except ValueError:
            problems.append(f"{witness_path.name}: unknown checksum algorithm {algo!r}")
            continue
        if local != digest:
            problems.append(
                f"{rel}: the deposit holds {algo}:{digest} but the local file is {algo}:{local}"
            )

    unwitnessed = sorted(set(files) - seen)
    if unwitnessed:
        problems.append(
            "these sealed files have no deposit witness, so nothing outside this "
            f"repository attests to them: {unwitnessed}"
        )

    if not problems:
        latest = witness.get("latest_server_time")
        print(
            f"[seal] OK: {len(seen)} sealed files match the deposit's own checksums; "
            f"latest server-assigned time {latest}"
        )
        print(
            "[seal]     that time bounds when the deposit last changed, not when the "
            "protocol was written, and not that no run preceded it"
        )
    return problems


def _check_run_manifest(root: Path, path: Path, seal_hash: str) -> list[str]:
    """Check that a run manifest names this seal and does not deviate from the arm spec."""
    if not path.is_file():
        return [f"the run manifest is missing: {path}"]
    run = load_json(path)
    problems: list[str] = []

    named = run.get("sealed_manifest_sha256")
    if named is None:
        problems.append(f"{path.name}: has no 'sealed_manifest_sha256'; it does not name a seal")
    elif named != seal_hash:
        problems.append(
            f"{path.name}: names seal {named} but this seal is {seal_hash}"
        )

    spec = load_json(root / "seal" / "arm-spec.json")
    field_map = spec["manifest_field_map"]
    checks: list[tuple[str, Any]] = [
        ("ollama_version", spec["environment"]["ollama_version"]),
        ("uv_lock_sha256", spec["environment"]["uv_lock_sha256"]),
        ("seed", spec["sampling"]["seed"]),
        ("m_draws", spec["sampling"]["m_draws"]),
        ("k_contexts", spec["sampling"]["k_contexts"]),
        ("context_ids", spec["context_bank"]["context_ids"]),
        ("bank_checksum", spec["context_bank"]["bank_checksum"]),
    ]
    for name, expected in checks:
        dotted = field_map[name]
        observed = _walk(run, dotted)
        if observed is _MISSING:
            problems.append(f"{path.name}: no field at {dotted} (for {name})")
        elif observed != expected:
            problems.append(
                f"{path.name}: {name} at {dotted} is {observed!r}, sealed as {expected!r} "
                "-- the arm spec lists this as a change that is not a minor deviation"
            )

    if not problems:
        print(f"[seal] OK: {path.name} names this seal and matches the sealed arm spec")
    return problems


if __name__ == "__main__":
    raise SystemExit(main())
