#!/usr/bin/env python3
"""Check that the sealed files are the bytes the seal manifest says they are.

**Read this before relying on it.** This script establishes *internal consistency*: that the files
listed in ``seal/SEAL-MANIFEST.json`` hash to the values recorded there, that the manifest's own
self-hash is correct, and that the set of sealed paths is exactly the set this script expects.

It does **not** establish that the seal is old, or that nobody changed a sealed file and the
manifest together. An author with write access to this repository can do both in one commit, and no
check that lives inside the repository can see that. The external half of the binding would be a
deposit: an archive publishes a per-file checksum for every file it holds, readable by anyone
without an account, and ``--witness`` compares those recorded checksums against the same local
files. Only the two halves together say anything about a third party having seen these bytes.

**Whether the external half exists is visible from the run, and this file asserts neither way.**
The witness is a file, ``seal/zenodo-witness.json``. ``repro.sh`` passes ``--witness`` when that
file is present and reports, loudly, that it is skipping the comparison when it is not -- so a
reader learns the answer from the run rather than from a sentence here, which would go stale the
moment the answer changed. ``analysis/scripts/collect_zenodo_witness.py`` writes that file by
reading the archive's public API, and is sealed for the same reason the evaluator is. It pairs
deposited files with sealed paths **by content**: each sealed file is hashed locally and matched
against the checksums the archive publishes, so the correspondence is not something the author
asserts.

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
a function of them, and -- with ``--witness`` -- a recorded deposit witness agrees with these bytes
and is closed against itself. What it does not: when they were written, that no unreported run
preceded them, or that the witness is what the archive returned. The last of those is reachable,
but only by re-reading the record, which is an online act and therefore not one of these steps.

Usage:
    python analysis/scripts/verify_seal.py
    python analysis/scripts/verify_seal.py --witness seal/zenodo-witness.json
    python analysis/scripts/verify_seal.py --run-manifest data/raw/primary-manifest.json
"""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import sys
from datetime import datetime
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
#:
#: ``_provenance.py`` is sealed because the three scripts above **import it**, and it holds the
#: SHA-256 implementation they all reach for. Sealing a checker while leaving the module that does
#: its hashing editable is not a seal; an independent review found exactly that gap here, and the
#: repair is not just this line but :func:`check_import_closure`, which fails if any sealed Python
#: file ever again imports a local module that is not itself sealed.
#:
#: ``collect_zenodo_witness.py`` is sealed because it is what produces the witness this script
#: reads. A collector that could be changed after the deposit could be taught to write down
#: whatever made the comparison below agree -- the same argument that seals the evaluator and the
#: renderer, applied to the one file that reaches outside the repository.
SEALED_PATHS: tuple[str, ...] = (
    "seal/decision-rules.json",
    "seal/arm-spec.json",
    "seal/protocol.md",
    "analysis/scripts/_provenance.py",
    "analysis/scripts/apply_decision_rules.py",
    "analysis/scripts/check_seal_scope.py",
    "analysis/scripts/collect_zenodo_witness.py",
    "analysis/scripts/render_decision_rules.py",
    "analysis/scripts/verify_seal.py",
    "analysis/freeze-provenance.json",
    "repro.sh",
)

#: The witness contract lives here, in the checker, rather than in the collector that writes the
#: file. The checker is what a reader runs; a collector that drifted from these names would then
#: produce a document the run rejects, which is the direction the mistake should fall in.
WITNESS_SCHEMA: str = "cds-deposit-witness-1"

#: The digest algorithm the archive publishes per file, and therefore the only one a witness may
#: record. Accepting any algorithm ``hashlib`` knows was a real hole rather than a hypothetical
#: one: a witness recording SHA-256 digests, computed locally and never published anywhere,
#: passed the comparison in full. The property being established is agreement with an outside
#: party, so the digest has to be in the form that party publishes.
DEPOSIT_ALGORITHM: str = "md5"

#: Time sources a witness may **not** use as part of its anchor, because the depositor supplies
#: them. A publication date is chosen when the record is filled in; treating it as a
#: server-assigned time would let the anchor be set to any date the depositor liked, which is
#: precisely the property the outside half exists to avoid. The collector records it under a
#: separate key so that its exclusion is visible rather than silent.
DEPOSITOR_SUPPLIED_TIME_SOURCES: frozenset[str] = frozenset(
    {"publication_date", "metadata.publication_date", "record.publication_date"}
)

#: Time sources a witness must carry. Without these the anchor could be narrowed to whichever
#: single field happened to be earliest, and a narrower anchor reads as a stronger claim.
REQUIRED_TIME_SOURCES: tuple[str, ...] = ("record.created", "record.updated")

#: The prefix the collector gives per-file times. At least one is required: the record's own
#: timestamps do not move when a file inside it is replaced, and file-level replacement is exactly
#: what the editable window after publication allows.
FILE_TIME_PREFIX: str = "files."

#: The registry time, and the key that has to name a reason when it is absent. Requiring one or
#: the other keeps a missing anchor declared instead of merely missing.
REGISTRY_TIME_SOURCE: str = "datacite.registered"
REGISTRY_ABSENT_KEY: str = "datacite_absent_reason"

#: How the manifest's self-hash is defined. Stated explicitly because a self-referential hash is
#: ambiguous unless the serialisation is pinned: sort keys, two-space indent, no ASCII escaping,
#: one trailing newline, UTF-8, and the ``self_sha256`` key removed before hashing.
CANONICALISATION: str = (
    "sha256 of json.dumps(manifest_without_self_sha256, sort_keys=True, indent=2, "
    'ensure_ascii=False) + "\\n", encoded as UTF-8'
)


def check_import_closure(root: Path) -> list[str]:
    """Require every local module a sealed Python file imports to be sealed as well.

    A hash over a checker says nothing if the checker calls out to a module nobody fixed. That was
    a real hole rather than a hypothetical one: ``verify_seal.py``, ``render_decision_rules.py``
    and ``apply_decision_rules.py`` all imported ``_provenance.py`` -- which supplies the SHA-256
    they hash with -- while ``_provenance.py`` sat outside the sealed set. Editing one file would
    have let every hash comparison in this script report agreement.

    Adding that file to the list closes the instance. This function closes the class: a sealed
    script that acquires a new local import fails the run until that import is sealed too. Only
    sibling modules are considered -- an import that resolves to the standard library or to the
    locked environment is out of scope here, and is covered instead by the lockfile whose digest
    the manuscript pins.
    """
    script_dir = root / "analysis" / "scripts"
    siblings = {path.stem for path in script_dir.glob("*.py")}
    sealed = set(SEALED_PATHS)
    problems: list[str] = []

    for rel in SEALED_PATHS:
        if not rel.endswith(".py"):
            continue
        source = root / rel
        if not source.is_file():
            continue  # the missing-file case is reported by the hash pass
        try:
            tree = ast.parse(source.read_text(encoding="utf-8"), filename=rel)
        except SyntaxError as exc:
            problems.append(f"{rel}: cannot be parsed, so its imports cannot be checked ({exc})")
            continue
        for node in ast.walk(tree):
            names: list[str] = []
            if isinstance(node, ast.Import):
                names = [alias.name.split(".")[0] for alias in node.names]
            elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                names = [node.module.split(".")[0]]
            for name in names:
                if name not in siblings:
                    continue
                needed = f"analysis/scripts/{name}.py"
                if needed not in sealed:
                    problems.append(
                        f"{rel} imports the local module {name!r}, which is not sealed. "
                        f"Add {needed} to SEALED_PATHS, or stop importing it: a sealed checker "
                        "that calls unsealed code is not sealed"
                    )
    return problems


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
        help="A run manifest. Checks that it names this seal and that every field the arm spec "
        "calls a not-minor deviation agrees with it. Requires --arm and --run-verdict.",
    )
    parser.add_argument(
        "--arm",
        choices=("control", "primary"),
        help="Which arm the run manifest belongs to. The model and its digest differ per arm, so "
        "inferring the arm from the manifest would let a mislabelled run match whichever arm it "
        "happened to resemble.",
    )
    parser.add_argument(
        "--run-verdict",
        type=Path,
        help="The verdict.json of the same run. The eleven thresholds live there rather than in "
        "the manifest, and they are compared from it.",
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

    # Held back until the end. Printing "OK" here and a failure three checks later reads, in a
    # CI log, as though the run passed and then something unrelated went wrong.
    passed: list[str] = [f"{len(SEALED_PATHS)} sealed files match, self-hash verified"]

    closure = check_import_closure(root)
    if closure:
        problems.extend(closure)
    else:
        sealed_python = sum(1 for rel in SEALED_PATHS if rel.endswith(".py"))
        passed.append(
            f"the {sealed_python} sealed Python files import no local module that is not "
            "itself sealed"
        )

    # The rules are sealed as bytes above. This asks the separate question of whether what a
    # reader reads is those rules: the protocol and the manuscript carry a generated rendering,
    # and it must be the one the sealed file produces.
    drift = check_rule_text(root)
    if drift:
        problems.extend(drift)
    else:
        passed.append(
            "the rule text in the protocol and the manuscript is generated from "
            "seal/decision-rules.json, not restated beside it"
        )

    if args.witness is not None:
        problems.extend(_check_witness(root, args.witness, files))

    if args.run_manifest is not None:
        if args.arm is None:
            problems.append("--run-manifest requires --arm: the model and digest differ per arm")
        else:
            problems.extend(
                _check_run_manifest(
                    root, args.run_manifest, computed_self, args.arm, args.run_verdict
                )
            )

    if problems:
        print("[seal] FAIL", file=sys.stderr)
        for problem in problems:
            print(f"  - {problem}", file=sys.stderr)
        return 1

    for line in passed:
        print(f"[seal] OK: {line}")
    return 0

def _check_witness(root: Path, witness_path: Path, files: dict[str, Any]) -> list[str]:
    """Compare a recorded deposit witness with the local sealed files.

    **What this can and cannot reach, stated before the checks rather than after.** This runs
    offline. It reads a file in this repository and compares it with other files in this
    repository. It therefore establishes that *the recorded witness and these bytes agree* -- and
    not that the witness transcribes anything an archive said. An independent review made the
    point by writing a witness out of nothing, with digests computed locally and invented
    timestamps, and watching it pass. The checks below are the repair for the part of that which
    is repairable offline; the wording in the manuscript is the repair for the part that is not.

    What is repairable offline is the witness's **internal closure**. The anchor must be the
    maximum of the times the witness carries; the times it carries must be exactly the ones the
    deposit listing it also carries would produce, one created and one updated per deposited file,
    with no invented name and no duplicate; and each sealed file's entry must agree with that
    listing on both the digest and the size. A hand edit can then no longer drop the latest real
    timestamp, invent a file to anchor to, or quietly narrow the maximum. It would have to forge
    the listing as well, consistently -- which leaves a document saying one thing and an archive
    saying another to anyone who looks.

    Looking is the step this cannot take. The witness records the public URL it was read from, and
    re-running ``collect_zenodo_witness.py`` against that URL reproduces the file; that is what
    turns a *recorded* external half into a *checked* one.
    """
    if not witness_path.is_file():
        return [f"the witness file is missing: {witness_path}"]
    witness = load_json(witness_path)
    name = witness_path.name

    if witness.get("schema") != WITNESS_SCHEMA:
        return [
            f"{name}: schema is {witness.get('schema')!r}, expected {WITNESS_SCHEMA!r}. The "
            "structure below is checked as a whole, so a document of some other shape is "
            "rejected rather than read for whichever parts happen to fit"
        ]

    deposited, problems = _deposit_listing(name, witness)
    problems.extend(_check_witness_files(root, name, witness, files, deposited))
    problems.extend(_check_witness_anchor(name, witness, deposited))
    if not problems:
        print(
            f"[seal] OK: the recorded witness agrees with all {len(files)} sealed files on the "
            f"{DEPOSIT_ALGORITHM} digest an archive publishes for them, and its anchor "
            f"{witness.get('latest_server_time')} is the latest of the "
            f"{len(witness.get('time_sources', []))} server times it carries"
        )
        print(
            "[seal]     This check is offline. It says the record and these bytes agree, not "
            "that the record is what the archive returned; re-run collect_zenodo_witness.py "
            f"against {witness.get('record_api_url')} to check that half"
        )
    return problems


def _deposit_listing(name: str, witness: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    """Return the deposit listing the witness carries, keyed by deposited file name.

    The listing is what makes the rest of the witness answerable to something: the time sources
    have to be the ones it implies, and the per-file digests have to be the ones it records. A
    witness without it could assert any set of times it liked.
    """
    entries = witness.get("deposit_files")
    if not isinstance(entries, list) or not entries:
        return {}, [
            f"{name}: 'deposit_files' must be a non-empty list. It is the archive's own listing, "
            "and without it the times and digests below answer to nothing"
        ]
    listing: dict[str, Any] = {}
    problems: list[str] = []
    for entry in entries:
        if not isinstance(entry, dict):
            problems.append(f"{name}: a deposit_files entry is not an object: {entry!r}")
            continue
        key = entry.get("key")
        if not isinstance(key, str) or not key:
            problems.append(f"{name}: a deposit_files entry has no name: {entry!r}")
            continue
        if key in listing:
            problems.append(f"{name}: the deposit listing names {key!r} more than once")
            continue
        listing[key] = entry
    return listing, problems


def _check_witness_anchor(
    name: str, witness: dict[str, Any], deposited: dict[str, Any]
) -> list[str]:
    """Require the anchor to be the maximum of exactly the times the deposit listing implies."""
    sources = witness.get("time_sources")
    if not isinstance(sources, list) or not sources:
        return [
            f"{name}: 'time_sources' must be a non-empty list. The anchor is defined as a "
            "maximum over the server-assigned times, so a witness that carries none of them "
            "reports a time nothing can check"
        ]

    # The names the listing implies, built here rather than read out of the witness. A set taken
    # from the document being checked agrees with whatever that document happens to contain,
    # which is the failure this whole file is arranged to avoid.
    expected_names = {"record.created", "record.updated"}
    for key in deposited:
        expected_names.add(f"{FILE_TIME_PREFIX}{key}.created")
        expected_names.add(f"{FILE_TIME_PREFIX}{key}.updated")

    problems: list[str] = []
    parsed: list[tuple[datetime, str]] = []
    counted: dict[str, int] = {}
    for entry in sources:
        if not isinstance(entry, dict):
            problems.append(f"{name}: a time source is not an object: {entry!r}")
            continue
        source = entry.get("source")
        value = entry.get("value")
        if not isinstance(source, str) or not isinstance(value, str):
            problems.append(f"{name}: a time source lacks a string source or value: {entry!r}")
            continue
        counted[source] = counted.get(source, 0) + 1
        if source in DEPOSITOR_SUPPLIED_TIME_SOURCES:
            problems.append(
                f"{name}: the time source {source!r} is supplied by the depositor rather than "
                "assigned by the server, so it cannot be part of the anchor"
            )
            continue
        if source != REGISTRY_TIME_SOURCE and source not in expected_names:
            problems.append(
                f"{name}: the time source {source!r} answers to nothing in the deposit listing. "
                "An invented name is how an anchor is moved without any real time changing"
            )
            continue
        try:
            moment = datetime.fromisoformat(value)
        except ValueError:
            problems.append(
                f"{name}: the time source {source!r} carries {value!r}, which is not an "
                "ISO-8601 timestamp"
            )
            continue
        if moment.tzinfo is None:
            problems.append(
                f"{name}: the time source {source!r} carries {value!r}, which has no timezone, "
                "so it cannot be ordered against the others"
            )
            continue
        parsed.append((moment, value))

    repeated = sorted(source for source, count in counted.items() if count > 1)
    if repeated:
        problems.append(
            f"{name}: these time sources appear more than once: {repeated}. A listing that "
            "disagrees with itself about one field cannot be read as an archive's answer"
        )
    absent = sorted(expected_names - set(counted))
    if absent:
        problems.append(
            f"{name}: the anchor omits the time sources {absent}. The deposit listing implies "
            "one created and one updated time per deposited file; a maximum over a chosen "
            "subset is a narrower claim than the anchor is defined to make"
        )
    if REGISTRY_TIME_SOURCE not in counted:
        reason = witness.get(REGISTRY_ABSENT_KEY)
        if not isinstance(reason, str) or not reason.strip():
            problems.append(
                f"{name}: neither a {REGISTRY_TIME_SOURCE!r} time source nor a non-empty "
                f"{REGISTRY_ABSENT_KEY!r} explaining its absence. An anchor may be narrower than "
                "the design allows for, but not silently"
            )

    if parsed:
        expected = max(parsed, key=lambda pair: pair[0])[1]
        recorded = witness.get("latest_server_time")
        if recorded != expected:
            problems.append(
                f"{name}: latest_server_time is {recorded!r}, but the latest time this witness "
                f"carries is {expected!r}. The anchor is recomputed here rather than read"
            )
    return problems


def _check_witness_files(
    root: Path,
    name: str,
    witness: dict[str, Any],
    files: dict[str, Any],
    deposited: dict[str, Any],
) -> list[str]:
    """Require every sealed file to be witnessed, and to agree with the deposit listing.

    Four things have to line up for one entry: the digest is in the algorithm the archive
    publishes; it is the digest of the local bytes; the deposited file it names is in the listing;
    and the listing records the same digest and size for that file. The third is what stops a
    digest floating free of any particular deposited file, and the fourth is what stops the entry
    and the listing being edited apart.
    """
    entries = witness.get("files")
    if not isinstance(entries, list) or not entries:
        return [f"{name}: 'files' must be a non-empty list"]

    problems: list[str] = []
    seen: set[str] = set()
    claimed: dict[str, str] = {}
    for entry in entries:
        if not isinstance(entry, dict):
            problems.append(f"{name}: a files entry is not an object: {entry!r}")
            continue
        rel = entry.get("sealed_path")
        checksum = entry.get("checksum")
        if rel is None or checksum is None:
            problems.append(f"{name}: an entry lacks sealed_path or checksum")
            continue
        seen.add(rel)
        if rel not in files:
            problems.append(f"{name}: {rel} is deposited but not sealed")
            continue
        algo, _, digest = str(checksum).partition(":")
        if algo != DEPOSIT_ALGORITHM:
            problems.append(
                f"{name}: {rel} is recorded as {algo!r}, but the archive publishes "
                f"{DEPOSIT_ALGORITHM!r}. A digest in another algorithm cannot have come from the "
                "listing this witness claims to transcribe, whatever it agrees with locally"
            )
            continue
        target = root / rel
        if not target.is_file():
            problems.append(f"{rel}: in the witness but not present locally")
            continue
        local = hashlib.new(algo, target.read_bytes(), usedforsecurity=False).hexdigest()
        if local != digest:
            problems.append(
                f"{rel}: the deposit holds {algo}:{digest} but the local file is {algo}:{local}"
            )
            continue

        key = entry.get("deposit_key")
        if not isinstance(key, str) or key not in deposited:
            problems.append(
                f"{name}: {rel} names the deposited file {key!r}, which the deposit listing does "
                "not hold. Every witnessed file has to be some particular file in the record"
            )
            continue
        if key in claimed:
            problems.append(
                f"{name}: the deposited file {key!r} is claimed by both {claimed[key]} and "
                f"{rel}. One deposited file cannot be the witness for two sealed paths"
            )
            continue
        claimed[key] = str(rel)
        listed = deposited[key]
        if listed.get("checksum") != checksum:
            problems.append(
                f"{name}: {rel} records {checksum!r} while the deposit listing records "
                f"{listed.get('checksum')!r} for {key!r}. The entry and the listing were edited "
                "apart"
            )
        listed_size = listed.get("size")
        actual_size = target.stat().st_size
        if listed_size != actual_size:
            problems.append(
                f"{name}: the deposit listing gives {key!r} a size of {listed_size!r}, but "
                f"{rel} is {actual_size} bytes"
            )

    unwitnessed = sorted(set(files) - seen)
    if unwitnessed:
        problems.append(
            "these sealed files have no deposit witness, so nothing outside this "
            f"repository attests to them: {unwitnessed}"
        )
    return problems


def _check_run_manifest(
    root: Path, path: Path, seal_hash: str, arm: str, verdict_path: Path | None
) -> list[str]:
    """Check that a run manifest names this seal and deviates from the arm spec in nothing.

    **All six categories, not four.** An earlier version of this function compared the backend
    version, the lockfile, the seed, M, K, the context ids and the bank checksum -- and skipped the
    model, the model digest and the thresholds, while the arm spec and the manuscript both said all
    six were checked. An independent review handed it a manifest naming ``attacker:999b`` with a
    zeroed digest and ``delta_tv_min = 999`` and got ``matches the sealed arm spec``. Two of the
    three omissions were the ones that matter most.

    The model and the digest are per arm, so the arm has to be named; guessing it from the manifest
    would let a mislabelled run pick whichever arm it happened to match. The thresholds are not in a
    run manifest at all -- they are in the run's ``verdict.json`` -- so they are compared from
    there, and refusing to check them silently is why ``--run-verdict`` is required rather than
    optional.
    """
    if not path.is_file():
        return [f"the run manifest is missing: {path}"]
    run = load_json(path)
    problems: list[str] = []

    named = run.get("sealed_manifest_sha256")
    if named is None:
        problems.append(f"{path.name}: has no 'sealed_manifest_sha256'; it does not name a seal")
    elif named != seal_hash:
        problems.append(f"{path.name}: names seal {named} but this seal is {seal_hash}")

    spec = load_json(root / "seal" / "arm-spec.json")
    field_map = spec["manifest_field_map"]
    if arm not in spec["arms"]:
        return problems + [f"unknown arm {arm!r}; the spec declares {sorted(spec['arms'])}"]
    arm_spec = spec["arms"][arm]

    expected: list[tuple[str, str, Any]] = [
        (name, field_map["shared"][name], value)
        for name, value in (
            ("ollama_version", spec["environment"]["ollama_version"]),
            ("uv_lock_sha256", spec["environment"]["uv_lock_sha256"]),
            ("python", spec["environment"]["python"]),
            ("seed", spec["sampling"]["seed"]),
            ("m_draws", spec["sampling"]["m_draws"]),
            ("k_contexts", spec["sampling"]["k_contexts"]),
            ("context_ids", spec["context_bank"]["context_ids"]),
            ("bank_checksum", spec["context_bank"]["bank_checksum"]),
        )
    ]
    expected += [
        (f"{arm}.{name}", field_map["per_arm"][name], arm_spec[key])
        for name, key in (("model", "model"), ("model_digest", "model_digest"), ("think", "think"))
    ]

    for name, dotted, want in expected:
        observed = _walk(run, dotted)
        if observed is _MISSING:
            problems.append(f"{path.name}: no field at {dotted} (for {name})")
        elif observed != want:
            problems.append(
                f"{path.name}: {name} at {dotted} is {observed!r}, sealed as {want!r} "
                "-- the arm spec lists this as a change that is not a minor deviation"
            )

    problems.extend(_check_thresholds(spec, verdict_path))

    if not problems:
        print(
            f"[seal] OK: {path.name} names this seal, and the {arm} arm's model, digest, think "
            f"regime, environment, sampling plan, context bank and all "
            f"{len(_sealed_thresholds(spec))} thresholds match the sealed arm spec"
        )
    return problems


def _sealed_thresholds(spec: dict[str, Any]) -> dict[str, Any]:
    """The eleven frozen constants, without the prose key that sits beside them."""
    return {key: value for key, value in spec["thresholds"].items() if key != "note"}


def _check_thresholds(spec: dict[str, Any], verdict_path: Path | None) -> list[str]:
    """Compare every sealed threshold with the ones the run recorded.

    Required, not optional. A run whose thresholds nobody looked at is exactly the run this seal
    exists to make impossible, so the absence of the file is a failure rather than a skip.
    """
    sealed = _sealed_thresholds(spec)
    if verdict_path is None:
        return [
            "--run-verdict was not given, so the eleven thresholds were not compared. The arm "
            "spec names changing a threshold as a change that is not a minor deviation; a check "
            "that can be skipped does not enforce that"
        ]
    if not verdict_path.is_file():
        return [f"the run verdict is missing: {verdict_path}"]
    verdict = load_json(verdict_path)
    observed = verdict.get("thresholds")
    if not isinstance(observed, dict):
        return [f"{verdict_path.name}: has no 'thresholds' mapping"]

    problems: list[str] = []
    for key in sorted(set(sealed) | set(observed)):
        if key not in observed:
            problems.append(f"{verdict_path.name}: threshold {key!r} is sealed but not recorded")
        elif key not in sealed:
            problems.append(
                f"{verdict_path.name}: threshold {key!r} was recorded but is not in the seal, so "
                "a threshold was added after the fact"
            )
        elif float(observed[key]) != float(sealed[key]):
            problems.append(
                f"{verdict_path.name}: threshold {key} is {observed[key]!r}, sealed as "
                f"{sealed[key]!r}"
            )
    return problems


if __name__ == "__main__":
    raise SystemExit(main())
