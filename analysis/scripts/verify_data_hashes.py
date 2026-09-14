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

A sixth concern arrived with the prospective arms. Their verdicts land in ``data/raw/`` as well,
and checks 3 and 5 above would reject them: they are not frozen inputs, they carry no row in the
table, and they cannot carry a provenance entry, because ``analysis/freeze-provenance.json`` is
sealed and they are written long after it. They are therefore excluded from the frozen-input
checks by name. **An exclusion is a hole**, so they are given checks of their own rather than left
unexamined, and the exclusion is closed to exactly two names. See :data:`PROSPECTIVE_OUTPUTS`.

Usage:
    python analysis/scripts/verify_data_hashes.py
    python analysis/scripts/verify_data_hashes.py --upstream-repo /path/to/upstream/clone
"""

from __future__ import annotations

import argparse
import contextlib
import hashlib
import io
import json
import re
import sys
import tempfile
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

#: What the prospective arms write into `data/raw/`, and what `repro.sh` step 13 reads.
#:
#: These are **results, not frozen inputs**, and the distinction is the whole reason they are
#: named here. A frozen input is a file that existed before the seal and is pinned by its digest
#: in `data/data.md` and by its upstream blob in the sealed `analysis/freeze-provenance.json`.
#: A prospective verdict is produced by a run that happens after the seal, so it can appear in
#: neither: the provenance file is sealed, and a digest cannot be recorded in advance for a
#: quantity that has not been measured.
#:
#: The exclusion is closed to these two names. Any other unrecorded file in `data/raw/` fails
#: exactly as before. Because excluding a file from every check would leave it unexamined --
#: the failure this repository keeps finding, where handing a checker an empty target quietly
#: removes the comparison while the run stays green -- the excluded files get
#: :func:`check_prospective_outputs` instead.
PROSPECTIVE_OUTPUTS = frozenset({"control-verdict.json", "primary-verdict.json"})

#: The heading of the section in `data/data.md` that describes the files above. Deliberately not
#: matching :data:`RAW_SECTION_START_RE`, so the frozen-input table parser cannot wander into it.
PROSPECTIVE_SECTION_START_RE = re.compile(r"^##\s+Prospective outputs in\s+`?raw/")

#: Inside that section, the lines that *name* the files, as opposed to the prose around them:
#: `- ``data/raw/<name>`` -- ...`. Restricting the extraction to this shape lets the prose mention
#: other filenames (the driver's own output, the frozen verdict it must not be a copy of) without
#: the name-set check misreading them as entries.
PROSPECTIVE_ENTRY_RE = re.compile(r"^-\s+`data/raw/(?P<name>[A-Za-z0-9_.-]+)`")


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
    repo_root: Path, entries: tuple[RawEntry, ...], prospective: frozenset[str]
) -> list[str]:
    """Check that `data/raw/` holds no file absent from the table.

    ``prospective`` is passed rather than read from the module so that the self-check can run
    this function with the exclusion emptied. An exclusion whose effect is never measured is
    indistinguishable from one that is doing nothing.
    """
    recorded = {entry.name for entry in entries} | set(RAW_DIR_ALLOWLIST) | prospective
    raw_dir = repo_root / "data" / "raw"
    unrecorded = sorted(
        path.name for path in raw_dir.iterdir() if path.name not in recorded
    )
    if unrecorded:
        return [
            f"data/raw/ holds files not recorded in data/data.md: {unrecorded}"
        ]
    return []


def check_prospective_outputs(
    repo_root: Path, entries: tuple[RawEntry, ...], prospective: frozenset[str]
) -> list[str]:
    """Check the files the frozen-input checks were told to skip.

    Two properties, both outcome-neutral -- neither says anything about which branch the rules
    will reach, and neither could be satisfied only by a result of a particular shape:

    1. the file parses as a JSON **object**, so that step 13 has something its evaluator can
       read by key rather than failing deep inside the sealed script;
    2. the file is **not a byte-for-byte copy of a frozen input**. This one is not hypothetical.
       Copying ``cproper-verdict.json`` into both arms satisfies the control gate and stops at
       R1, producing a full decision report and a green run out of a file that predates the
       prospective design entirely. It is the shortest path from nothing to an apparently
       reported result, and it is closed here.

    What is *not* checked: that the numbers are right, or that they came from the declared
    models. That is the driver's ``--verify`` and the sealed ``verify_seal.py --run-manifest``,
    which compare the run manifest against the seal. Landing a verdict is not a substitute for
    having verified it, and this function does not pretend otherwise.
    """
    problems: list[str] = []
    raw_dir = repo_root / "data" / "raw"
    frozen_by_sha = {entry.sha256: entry.name for entry in entries}

    present = sorted(name for name in prospective if (raw_dir / name).is_file())
    for name in present:
        path = raw_dir / name
        try:
            parsed = json.loads(path.read_text(encoding="utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            problems.append(f"data/raw/{name}: not readable as JSON ({exc})")
            continue
        if not isinstance(parsed, dict):
            problems.append(
                f"data/raw/{name}: parses as {type(parsed).__name__}, not a JSON object. "
                "The sealed evaluator reads quantities by key"
            )
            continue
        digest = sha256_of(path)
        if digest in frozen_by_sha:
            problems.append(
                f"data/raw/{name}: byte-for-byte identical to the frozen input "
                f"{frozen_by_sha[digest]}. A prospective arm cannot have produced a file that "
                "existed before the seal; this is a copy, not a result"
            )
            continue
        print(f"[data-hash] OK {name:<28} prospective result, distinct from every frozen input")

    missing = sorted(set(prospective) - set(present))
    if present and missing:
        print(
            f"[data-hash] note: {len(present)} of {len(prospective)} prospective verdicts are "
            f"present; still absent: {missing}. Step 13 stays guarded until both exist"
        )
    return problems


def check_prospective_section(repo_root: Path, prospective: frozenset[str]) -> list[str]:
    """Require `data/data.md` to describe exactly the files the exclusion covers.

    The constant is the authority and the document follows it, not the other way round. Reading
    the exclusion *out of* the document would mean one prose line could license any file at all
    into `data/raw/`; comparing the two in both directions means the document cannot drift from
    what the code does, and widening the exclusion takes an edit in more than one place.
    """
    data_md = repo_root / "data" / "data.md"
    named: set[str] = set()
    in_section = False
    for line in data_md.read_text(encoding="utf-8").splitlines():
        if PROSPECTIVE_SECTION_START_RE.match(line):
            in_section = True
            continue
        if in_section and NEXT_SECTION_RE.match(line):
            break
        if not in_section:
            continue
        match = PROSPECTIVE_ENTRY_RE.match(line)
        if match is not None:
            named.add(match.group("name"))

    if not in_section:
        return [
            "data/data.md has no 'Prospective outputs in `raw/`' section, so the files "
            f"excluded from the frozen-input checks ({sorted(prospective)}) are undocumented"
        ]
    if named != set(prospective):
        return [
            "data/data.md and PROSPECTIVE_OUTPUTS disagree about which files are prospective "
            f"outputs (document={sorted(named)} code={sorted(prospective)})"
        ]
    print(
        f"[data-hash] OK data/data.md documents exactly the {len(named)} excluded "
        "prospective outputs"
    )
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
    repo_root: Path, upstream: Path | None, prospective: frozenset[str]
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

    # Every frozen input on disk must also carry a provenance entry. The prospective outputs are
    # excluded here as well as in check_no_unrecorded_files: they are written after the sealed
    # provenance file, so requiring an entry for them would require editing a sealed file.
    raw_dir = repo_root / "data" / "raw"
    shipped_names = {
        path.name
        for path in raw_dir.iterdir()
        if path.is_file()
        and path.name not in RAW_DIR_ALLOWLIST
        and path.name not in prospective
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


#: The exclusion written out a second time, as literal names. This is a **pin**, not a second
#: source: :data:`EXPECTED_RAW_ROWS` is pinned the same way and for the same reason, so that a
#: change is noticed rather than absorbed. Widening the exclusion now takes an edit in three
#: places -- here, in :data:`PROSPECTIVE_OUTPUTS`, and in `data/data.md` -- and all three are
#: compared against one another. That is the friction a check which *suppresses other checks*
#: ought to have.
_PINNED_PROSPECTIVE_NAMES: tuple[str, ...] = (
    "control-verdict.json",
    "primary-verdict.json",
)

#: Fixture bytes for the self-check. Written as literals, never derived from the constants under
#: test: a fixture built out of :data:`PROSPECTIVE_OUTPUTS` would follow that set wherever it
#: moved, and would report success against a set that had been widened to anything at all.
_FIXTURE_FROZEN_A = b'{"fixture": "frozen-a"}\n'
_FIXTURE_FROZEN_B = b'{"fixture": "frozen-b"}\n'
_FIXTURE_PROSPECTIVE_A = b'{"verdict": "FIXTURE", "tv_bar": 0.5}\n'
_FIXTURE_PROSPECTIVE_B = b'{"verdict": "FIXTURE", "tv_bar": 0.25}\n'

_FIXTURE_DATA_MD = """# fixture

## Prospective outputs in `raw/` (not frozen inputs)

- `data/raw/control-verdict.json` -- fixture
- `data/raw/primary-verdict.json` -- fixture

## next
"""


def _fixture_entries() -> tuple[RawEntry, ...]:
    """The two frozen inputs the fixture repository claims to carry."""
    return (
        RawEntry(
            name="frozen-a.json",
            sha256=hashlib.sha256(_FIXTURE_FROZEN_A).hexdigest(),
            size=len(_FIXTURE_FROZEN_A),
        ),
        RawEntry(
            name="frozen-b.json",
            sha256=hashlib.sha256(_FIXTURE_FROZEN_B).hexdigest(),
            size=len(_FIXTURE_FROZEN_B),
        ),
    )


def _fixture_repo(
    root: Path,
    files: dict[str, bytes],
    data_md: str,
    provenance_for: dict[str, bytes] | None = None,
) -> Path:
    """Build a throwaway repository holding exactly ``files`` under `data/raw/`.

    ``provenance_for`` names the files that get an entry in the fixture's
    `analysis/freeze-provenance.json`. The blob identifiers are computed from the fixture bytes
    with the same content-addressing the real file records, so that the only difference between
    the control and the mutation below is the exclusion itself, not a blob mismatch standing in
    for it.
    """
    raw_dir = root / "data" / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)
    for name, blob in files.items():
        (raw_dir / name).write_bytes(blob)
    (root / "data" / "data.md").write_text(data_md, encoding="utf-8", newline="\n")
    if provenance_for is not None:
        (root / "analysis").mkdir(parents=True, exist_ok=True)
        record = {
            "frozen_inputs": [
                {
                    "shipped_path": f"data/raw/{name}",
                    "upstream_path": f"upstream/{name}",
                    "upstream_commit": "0" * 40,
                    "upstream_commit_utc": "2026-01-01T00:00:00Z",
                    "provenance_kind": "run_artifact",
                    "blob_sha1": git_blob_sha1(blob),
                }
                for name, blob in provenance_for.items()
            ]
        }
        (root / "analysis" / "freeze-provenance.json").write_text(
            json.dumps(record, indent=2) + "\n", encoding="utf-8", newline="\n"
        )
    return root


def _expect(
    problems: list[str], *, label: str, fires: bool, because: str = ""
) -> list[str]:
    """Compare one self-check case against what it was supposed to do.

    ``because`` is matched against the reported text. A mutation that fails for a reason other
    than the one it was written to provoke is not evidence about the guard it was aimed at, and
    reporting it as a kill would overstate what the sweep establishes.
    """
    reported = bool(problems)
    joined = " | ".join(problems)
    if reported != fires:
        expected = "report a problem" if fires else "report nothing"
        return [f"self-check {label}: expected to {expected}, got {problems!r}"]
    if fires and because and because not in joined:
        return [
            f"self-check {label}: fired, but not for the expected reason "
            f"(wanted text containing {because!r}, got {joined!r})"
        ]
    return []


def check_guards_fire() -> list[str]:
    """Measure what the guards above actually catch, on every run.

    ``repro.sh`` is sealed, so a mutation sweep cannot be added to it as a step, and this
    repository has no test suite: the reviewer's one command is the only place a sweep can run.
    ``check_claim_boundary.py`` carries its positive control the same way and for the same
    reason. Each case below was confirmed by breaking the guard it aims at and watching it stop
    firing.

    The checks under test print an ``OK`` line per file they accept. Those lines are swallowed
    here: a fixture's output that reached the log would read exactly like a statement about this
    repository's own inputs, which is not a confusion worth risking to save a redirect.
    """
    with contextlib.redirect_stdout(io.StringIO()):
        problems = _run_guard_cases()
    if not problems:
        print(
            "[data-hash] OK self-check: 6 mutations caught, 5 controls clean "
            "(the exclusion permits exactly two named files, on both sides, and nothing else)"
        )
    return problems


def _run_guard_cases() -> list[str]:
    """The cases themselves. Separated so the caller can silence fixture output."""
    problems: list[str] = []
    entries = _fixture_entries()
    exclusion = frozenset(_PINNED_PROSPECTIVE_NAMES)
    frozen_files = {
        "frozen-a.json": _FIXTURE_FROZEN_A,
        "frozen-b.json": _FIXTURE_FROZEN_B,
    }
    landed = {
        **frozen_files,
        "control-verdict.json": _FIXTURE_PROSPECTIVE_A,
        "primary-verdict.json": _FIXTURE_PROSPECTIVE_B,
    }

    if set(_PINNED_PROSPECTIVE_NAMES) != set(PROSPECTIVE_OUTPUTS):
        problems.append(
            "self-check pin: PROSPECTIVE_OUTPUTS is "
            f"{sorted(PROSPECTIVE_OUTPUTS)}, pinned as "
            f"{sorted(_PINNED_PROSPECTIVE_NAMES)}. Widening the set of files that may sit in "
            "data/raw/ unrecorded is a deliberate act; update the pin to make it one"
        )

    with tempfile.TemporaryDirectory() as tmp:
        root = _fixture_repo(Path(tmp) / "landed", landed, _FIXTURE_DATA_MD)

        # P1 -- the arrangement this change exists to permit reports nothing.
        problems += _expect(
            check_no_unrecorded_files(root, entries, exclusion),
            label="P1 landed verdicts are permitted",
            fires=False,
        )
        # M1 -- and it is the exclusion that permits them, not something else.
        problems += _expect(
            check_no_unrecorded_files(root, entries, frozenset()),
            label="M1 exclusion emptied",
            fires=True,
            because="control-verdict.json",
        )
        # P2 -- the frozen inputs are still compared against their recorded digests, and a
        # single altered byte is still caught. The exclusion did not loosen this.
        problems += _expect(
            check_raw_files(root, entries),
            label="P2 frozen inputs match their digests",
            fires=False,
        )
        (root / "data" / "raw" / "frozen-a.json").write_bytes(
            _FIXTURE_FROZEN_A.replace(b"frozen-a", b"frozen-X")
        )
        problems += _expect(
            check_raw_files(root, entries),
            label="P2' one altered byte in a frozen input",
            fires=True,
            because="SHA-256 mismatch",
        )
        # The document must name exactly the excluded files, in both directions.
        problems += _expect(
            check_prospective_section(root, exclusion),
            label="P3 document names the excluded files",
            fires=False,
        )
        problems += _expect(
            check_prospective_section(root, frozenset({"control-verdict.json"})),
            label="M2 document names more than the code excludes",
            fires=True,
            because="disagree",
        )

    with tempfile.TemporaryDirectory() as tmp:
        # M3 -- an unrelated unrecorded file still fails. The exclusion is closed to two names.
        stray = {**landed, "stray-input.json": b'{"fixture": "stray"}\n'}
        root = _fixture_repo(Path(tmp) / "stray", stray, _FIXTURE_DATA_MD)
        reported = check_no_unrecorded_files(root, entries, exclusion)
        problems += _expect(
            reported,
            label="M3 unrelated unrecorded file",
            fires=True,
            because="stray-input.json",
        )
        if any("verdict.json" in problem for problem in reported):
            problems.append(
                "self-check M3: the stray file was reported together with the prospective "
                f"verdicts, so the exclusion is not being applied at all: {reported!r}"
            )

    with tempfile.TemporaryDirectory() as tmp:
        # M4 -- the shortest route from nothing to an apparently reported result: copy a frozen
        # verdict into both arms. Closed.
        copied = {**frozen_files, "control-verdict.json": _FIXTURE_FROZEN_A}
        root = _fixture_repo(Path(tmp) / "copied", copied, _FIXTURE_DATA_MD)
        problems += _expect(
            check_prospective_outputs(root, entries, exclusion),
            label="M4 prospective verdict copied from a frozen input",
            fires=True,
            because="byte-for-byte identical",
        )

    with tempfile.TemporaryDirectory() as tmp:
        # M5 -- a landed file that is not a JSON object. The sealed evaluator reads by key.
        malformed = {**frozen_files, "control-verdict.json": b"[1, 2, 3]\n"}
        root = _fixture_repo(Path(tmp) / "malformed", malformed, _FIXTURE_DATA_MD)
        problems += _expect(
            check_prospective_outputs(root, entries, exclusion),
            label="M5 landed file is not a JSON object",
            fires=True,
            because="not a JSON object",
        )

    with tempfile.TemporaryDirectory() as tmp:
        # P4 -- and the well-formed, distinct case reports nothing.
        root = _fixture_repo(Path(tmp) / "ok", landed, _FIXTURE_DATA_MD)
        problems += _expect(
            check_prospective_outputs(root, entries, exclusion),
            label="P4 well-formed prospective verdicts",
            fires=False,
        )

    with tempfile.TemporaryDirectory() as tmp:
        # The provenance check enforces the same rule from the other side: every shipped input
        # must have an entry in the sealed provenance file. The prospective outputs are excluded
        # there too, and both exclusions have to be right -- fixing only one leaves a run that
        # passes here and fails on the day the verdicts land. An independent review pointed out
        # that this function was not being exercised at all, which is why these two cases exist.
        root = _fixture_repo(
            Path(tmp) / "prov", landed, _FIXTURE_DATA_MD, provenance_for=frozen_files
        )
        problems += _expect(
            check_frozen_input_provenance(root, None, exclusion),
            label="P5 provenance accepts the landed verdicts",
            fires=False,
        )
        problems += _expect(
            check_frozen_input_provenance(root, None, frozenset()),
            label="M6 provenance exclusion emptied",
            fires=True,
            because="no entry in freeze-provenance.json",
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

    # Run first. Every verdict below is only worth what the guards producing it are worth, and a
    # harness that has stopped catching its own mutations should say so before, not after.
    problems: list[str] = check_guards_fire()

    problems.extend(check_raw_files(repo_root, entries))
    problems.extend(check_no_unrecorded_files(repo_root, entries, PROSPECTIVE_OUTPUTS))
    problems.extend(check_prospective_outputs(repo_root, entries, PROSPECTIVE_OUTPUTS))
    problems.extend(check_prospective_section(repo_root, PROSPECTIVE_OUTPUTS))
    problems.extend(check_upstream_pins(repo_root, entries))
    problems.extend(
        check_frozen_input_provenance(repo_root, args.upstream_repo, PROSPECTIVE_OUTPUTS)
    )

    if problems:
        print("[data-hash] FAIL", file=sys.stderr)
        for problem in problems:
            print(f"  - {problem}", file=sys.stderr)
        return 1

    print("[data-hash] OK: the frozen inputs match the record in data/data.md")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
