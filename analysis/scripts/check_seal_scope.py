#!/usr/bin/env python3
"""Measure what the seal actually catches, by mutating the things it is supposed to protect.

A check that is never exercised is a check that might be vacuous. Running the evaluator once on the
real record shows that it produces *an* answer; running ``verify_seal.py`` once on an untouched
repository shows that it says OK. Neither shows that a tampered input would have produced anything
different. This script supplies the difference, in two families.

**Family 1 -- the decision rules.** Synthetic arm records are fed to
``apply_decision_rules.py`` and the branch it reaches is compared with the branch the case says it
should reach. Each record is an **independently written literal**: none is derived from
``seal/decision-rules.json``, because a fixture generated from the thing it tests agrees with it by
construction and so measures nothing.

**Family 2 -- the seal itself.** A copy of the sealed tree is made in a temporary directory, one
thing in it is changed, and ``verify_seal.py`` is run against that copy. The interesting cases are
not the obvious ones. Editing a sealed file fails on its hash, which is unsurprising; what has to
be shown is that **no single-place edit is consistent** -- that moving a threshold in the
manuscript alone fails the generated-text check, that moving it in the sealed rules alone fails the
hash, and that altering a hash recorded in the manifest fails whether or not the manifest's
self-hash is recomputed to match.

The scope of that phrase is worth pinning down, because it is easy to read as more. Regenerating
the rules, the renderer, this file and the manifest **together** passes every case below, and is
supposed to: it is what preparing a seal looks like. Nothing here distinguishes that from the same
act performed after the results are known. Only a copy held by someone else can.
``seal/protocol.md`` section 7 records that, at the time this file was sealed, there was no such
copy; whether one exists now is answered by whether ``seal/zenodo-witness.json`` is present and
by what step 14 of ``repro.sh`` reports, not by this sentence.

Both families carry **no-op controls** that must *not* fail, so that a checker which simply reports
failure on everything cannot pass this script. This is not a formality: a green result here means
nothing without them.

What this establishes: for each listed mutation, the evaluator reaches the stated branch, or
``verify_seal.py`` exits non-zero, or -- for a no-op -- it does not. What it does not: that the
rules are the right rules, or that the sealed files are old. Whether the branch definitions express
the intended science is a question for the protocol, not for this file.

Usage:  python analysis/scripts/check_seal_scope.py
"""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
from collections.abc import Callable
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

from collect_zenodo_witness import latest as collector_latest  # noqa: E402
from collect_zenodo_witness import main as collector_main  # noqa: E402
from verify_seal import SEALED_PATHS, canonical_self_hash  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[2]
EVALUATOR = REPO_ROOT / "analysis" / "scripts" / "apply_decision_rules.py"
SEAL_CHECKER = REPO_ROOT / "analysis" / "scripts" / "verify_seal.py"
RULES = REPO_ROOT / "seal" / "decision-rules.json"

#: The control arm as recorded by the completed run. Written out here as a literal rather than
#: read from data/raw, so that this file states what it assumes.
CONTROL_IN_BAND: dict[str, Any] = {
    "verdict": "NO_CHANNEL_CONFORMANCE",
    "rho_hat": 1.0,
    "power": 1.0,
    "tv_bar": 0.038065,
    "permutation_reject": False,
    "none_rate_max_observed": 0.123333,
}

#: A primary arm that reaches R1: valid apparatus, adequate power, estimate below the margin.
PRIMARY_R1: dict[str, Any] = {
    "verdict": "NO_CHANNEL_CONFORMANCE",
    "rho_hat": 0.875,
    "power": 0.95,
    "tv_bar": 0.052,
    "permutation_reject": False,
    "none_rate_max_observed": 0.2,
}


def _with(base: dict[str, Any], **changes: Any) -> dict[str, Any]:
    merged = dict(base)
    merged.update(changes)
    return merged


def _without(base: dict[str, Any], key: str) -> dict[str, Any]:
    merged = dict(base)
    del merged[key]
    return merged


#: (name, control, primary, expected branch or None for "must exit non-zero", why it matters)
CASES: tuple[tuple[str, dict[str, Any], dict[str, Any] | None, str | None, str], ...] = (
    # -- the control gate, one factor at a time -------------------------------------------- #
    (
        "R5 holds, primary reaches R1",
        CONTROL_IN_BAND,
        PRIMARY_R1,
        "R1",
        "the unmutated pair; if this does not reach R1 nothing below means anything",
    ),
    (
        "R5 fails on verdict",
        _with(CONTROL_IN_BAND, verdict="CHANNEL_CONFORMANCE_DETECTED"),
        PRIMARY_R1,
        "R5",
        "a differing control verdict must stop before the primary arm is read",
    ),
    (
        "R5 fails on rho_hat just below the band",
        _with(CONTROL_IN_BAND, rho_hat=0.7499),
        PRIMARY_R1,
        "R5",
        "the 0.75 bound is tighter than the 0.5 inside the scorer and must bite",
    ),
    (
        "R5 holds at rho_hat exactly on the bound",
        _with(CONTROL_IN_BAND, rho_hat=0.75),
        PRIMARY_R1,
        "R1",
        "the bound is inclusive; an off-by-one here would silently narrow the band",
    ),
    (
        "R5 fails on power",
        _with(CONTROL_IN_BAND, power=0.79),
        PRIMARY_R1,
        "R5",
        "the control arm's own power is part of the concordance band",
    ),
    (
        "R5 fails on the tv_bar tolerance while still below the margin",
        _with(CONTROL_IN_BAND, tv_bar=0.08),
        PRIMARY_R1,
        "R5",
        "0.08 < 0.10 but |0.08 - 0.038065| > 0.03: the tolerance is a separate condition "
        "from the margin, and collapsing the two would lose this case",
    ),
    (
        "R5 fails on tv_bar above the margin",
        _with(CONTROL_IN_BAND, tv_bar=0.15),
        PRIMARY_R1,
        "R5",
        "the margin condition must bite independently of the tolerance",
    ),
    (
        "R5 fails on permutation_reject",
        _with(CONTROL_IN_BAND, permutation_reject=True),
        PRIMARY_R1,
        "R5",
        "a control arm that rejects the nil null is not concordant",
    ),
    # -- the primary branches -------------------------------------------------------------- #
    (
        "R4 on collapsed support",
        CONTROL_IN_BAND,
        _with(PRIMARY_R1, rho_hat=0.375),
        "R4",
        "apparatus invalidity must be read before the estimate, not as a null",
    ),
    (
        "R4 on excessive none-rate",
        CONTROL_IN_BAND,
        _with(PRIMARY_R1, none_rate_max_observed=0.6),
        "R4",
        "the second disjunct of R4 must be reachable on its own",
    ),
    (
        "R3 on inadequate power",
        CONTROL_IN_BAND,
        _with(PRIMARY_R1, power=0.5),
        "R3",
        "an underpowered estimate must not fall through to R1 or R2",
    ),
    (
        "R3 does not fire at power exactly 0.8",
        CONTROL_IN_BAND,
        _with(PRIMARY_R1, power=0.8),
        "R1",
        "power_min is inclusive; the boundary decides between R3 and R1",
    ),
    (
        "R2 on an estimate at the margin",
        CONTROL_IN_BAND,
        _with(PRIMARY_R1, tv_bar=0.1),
        "R2",
        "the margin is exclusive for R1: exactly 0.10 is not below it",
    ),
    (
        "R2 on a rejected nil null below the margin",
        CONTROL_IN_BAND,
        _with(PRIMARY_R1, permutation_reject=True),
        "R2",
        "R2's disjunction must fire on rejection alone, with the estimate still small",
    ),
    (
        "R4 wins over R3 when both would fire",
        CONTROL_IN_BAND,
        _with(PRIMARY_R1, none_rate_max_observed=0.6, power=0.5),
        "R4",
        "the only genuine R4/R3 conflict: R4 fires on its none-rate disjunct while rho_hat "
        "stays above 0.5, so R3 fires too. The branches are not mutually exclusive as "
        "written and the sealed order is what removes the ambiguity. Reaching R4 through "
        "the rho_hat disjunct instead would NOT test the order, because R3 requires "
        "rho_hat >= 0.5 and so cannot fire at the same time -- an earlier version of this "
        "case made that mistake and passed under a deliberately reordered rule file",
    ),
    # -- malformed inputs are errors, not false predicates --------------------------------- #
    (
        "a missing quantity is an error",
        CONTROL_IN_BAND,
        _without(PRIMARY_R1, "rho_hat"),
        None,
        "a rule that silently evaluates False on a missing key is worse than no rule",
    ),
    (
        "a null quantity is an error",
        CONTROL_IN_BAND,
        _with(PRIMARY_R1, power=None),
        None,
        "null must not be coerced",
    ),
    (
        "a stringified number is an error",
        CONTROL_IN_BAND,
        _with(PRIMARY_R1, tv_bar="0.052"),
        None,
        "string comparison would have made this pass",
    ),
    (
        "a NaN is an error",
        CONTROL_IN_BAND,
        _with(PRIMARY_R1, tv_bar=float("nan")),
        None,
        "every comparison with NaN is False, so NaN would quietly walk to the last branch",
    ),
    (
        "an int where a bool is expected is an error",
        CONTROL_IN_BAND,
        _with(PRIMARY_R1, permutation_reject=0),
        None,
        "0 == False in Python; accepting it would let a malformed record satisfy R1",
    ),
    (
        "a bool where a number is expected is an error",
        CONTROL_IN_BAND,
        _with(PRIMARY_R1, rho_hat=True),
        None,
        "True == 1 in Python, which would pass every lower bound",
    ),
    # -- the control against over-strictness ------------------------------------------------ #
    (
        "no-op: reordering the keys changes nothing",
        dict(reversed(list(CONTROL_IN_BAND.items()))),
        dict(reversed(list(PRIMARY_R1.items()))),
        "R1",
        "a checker that failed on everything would pass every case above; this one "
        "must still succeed, and reach the same branch",
    ),
)


def _run(tmp: Path, control: dict[str, Any], primary: dict[str, Any] | None) -> tuple[int, str]:
    control_path = tmp / "control.json"
    control_path.write_text(json.dumps(control), encoding="utf-8")
    argv = [
        sys.executable,
        str(EVALUATOR),
        "--rules",
        str(RULES),
        "--control",
        str(control_path),
    ]
    if primary is not None:
        primary_path = tmp / "primary.json"
        primary_path.write_text(json.dumps(primary), encoding="utf-8")
        argv += ["--primary", str(primary_path)]
    out_path = tmp / "report.json"
    argv += ["--out", str(out_path)]

    completed = subprocess.run(argv, capture_output=True, text=True, check=False)
    if completed.returncode != 0:
        return completed.returncode, ""
    report = json.loads(out_path.read_text(encoding="utf-8"))
    return 0, report["branch"]


# ================================================================================================ #
# Family 2 -- the seal
# ================================================================================================ #

#: The sealed set, written out here **independently of the checker**. Importing ``SEALED_PATHS``
#: is fine for staging files, but it cannot answer "is the sealed set still the intended one":
#: shrinking that tuple and rebuilding the manifest would make every case below pass again. Two
#: places have to agree, so shrinking the seal takes two edits and one of them is this list.
EXPECTED_SEALED_SET: frozenset[str] = frozenset(
    {
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
    }
)

#: Files the seal checker reads that are not themselves sealed. ``main.md`` is here because the
#: generated-text check reads it; it is deliberately *not* sealed, since the manuscript grows a
#: completion report after the run and a seal that forbade that would be a seal nobody could keep.
UNSEALED_INPUTS: tuple[str, ...] = ("manuscript/main.md",)

#: A run manifest that agrees with ``seal/arm-spec.json`` on every field the spec calls a
#: not-minor deviation, for the **primary** arm. Written out here as literals rather than read
#: from the arm spec: a fixture copied from the file it is checking agrees with it whatever either
#: one says. The consequence is intended -- changing a frozen value in the arm spec breaks this
#: case, which is the correct outcome for a value that is not supposed to change.
CONFORMING_RUN_MANIFEST: dict[str, Any] = {
    "env_pins": {
        "model": "llama3.1:8b",
        "model_digest": "46e0c10c039e019119339687c3c1757cc81b9da49709a3b3924863ba87ca666e",
        "think": False,
        "ollama_version": "0.32.12",
        "python": "3.11.15",
        "uv_lock_sha256": "9cc70f9dc5d61f6c74c08dee4dd73815993861022a80781a75ef5d873860c0f7",
    },
    "run": {
        "seed": 20260708,
        "m_draws": 300,
        "k_contexts": 8,
        "context_ids": [f"cproper-ctx-{i}" for i in range(8)],
    },
    "bank_checksum": "5e991dd6340778196f79c3ba579224e41b55e27647c64ec3694b0648ca6f71fb",
}

#: The eleven frozen constants, as the run's verdict.json records them. Independently written for
#: the same reason as the manifest above.
CONFORMING_THRESHOLDS: dict[str, Any] = {
    "alpha": 0.05,
    "delta_tv_min": 0.1,
    "h_min_bits": 0.5,
    "k_contexts": 8.0,
    "k_min": 8.0,
    "m_draws": 300.0,
    "m_min": 300.0,
    "none_rate_max": 0.5,
    "power_min": 0.8,
    "rho_min": 0.5,
    "seed": 20260708.0,
}

#: A fragment of the generated rule block, quoted from the rendering rather than from the JSON.
#: Used to move a threshold in a carrier file without touching the sealed rules.
BLOCK_BEGIN = "<!-- BEGIN GENERATED FROM seal/decision-rules.json -- DO NOT EDIT BY HAND -->"
BLOCK_END = "<!-- END GENERATED FROM seal/decision-rules.json -->"

BAND_IN_RENDERED_TEXT = "`rho_hat` ≥ 0.75"
BAND_MOVED = "`rho_hat` ≥ 0.85"


def _stage(tmp: Path) -> Path:
    """Copy everything ``verify_seal.py`` reads into a scratch tree and return its root."""
    root = tmp / "tree"
    for rel in (*SEALED_PATHS, *UNSEALED_INPUTS, "seal/SEAL-MANIFEST.json"):
        source = REPO_ROOT / rel
        target = root / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
    return root


def _run_seal_checker(
    root: Path,
    run_manifest: Path | None = None,
    run_verdict: Path | None = None,
    witness: Path | None = None,
) -> tuple[int, str]:
    argv = [sys.executable, str(SEAL_CHECKER), "--repo-root", str(root)]
    if witness is not None:
        argv += ["--witness", str(witness)]
    if run_manifest is not None:
        argv += ["--run-manifest", str(run_manifest), "--arm", "primary"]
    if run_verdict is not None:
        argv += ["--run-verdict", str(run_verdict)]
    completed = subprocess.run(argv, capture_output=True, text=True, check=False)
    return completed.returncode, (completed.stdout + completed.stderr)


def _rewrite(root: Path, rel: str, old: str, new: str) -> None:
    path = root / rel
    text = path.read_text(encoding="utf-8")
    if text.count(old) < 1:
        raise AssertionError(f"{rel}: the mutation anchor is absent: {old!r}")
    path.write_text(text.replace(old, new, 1), encoding="utf-8", newline="\n")


def _rewrite_manifest(root: Path, mutate: Callable[[dict[str, Any]], None], reseal: bool) -> None:
    """Change the manifest, optionally recomputing its self-hash so it stays internally consistent."""
    path = root / "seal" / "SEAL-MANIFEST.json"
    manifest = json.loads(path.read_text(encoding="utf-8"))
    mutate(manifest)
    if reseal:
        manifest["self_sha256"] = canonical_self_hash(manifest)
    path.write_text(
        json.dumps(manifest, sort_keys=True, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def _rendered_block(root: Path) -> str:
    """The block the sealed rules render to, taken from the staged tree's own manuscript."""
    text = (root / "manuscript" / "main.md").read_text(encoding="utf-8")
    start = text.index(BLOCK_BEGIN)
    end = text.index(BLOCK_END) + len(BLOCK_END)
    return text[start:end]


def _drop_a_block_line(root: Path) -> None:
    """Remove one line from inside the generated block, leaving the markers in place."""
    path = root / "manuscript" / "main.md"
    lines = path.read_text(encoding="utf-8").splitlines()
    first = next(i for i, line in enumerate(lines) if line.startswith(BLOCK_BEGIN))
    last = next(i for i, line in enumerate(lines) if line.startswith(BLOCK_END))
    victim = next(
        i for i in range(first + 1, last) if lines[i].startswith("- **Satisfied when**")
    )
    del lines[victim]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")


def _bend_hash(digest: str) -> str:
    """Return a different but well-formed sha256, so the failure is a mismatch and not a parse error."""
    head = "0" if digest[0] != "0" else "1"
    return head + digest[1:]


def _touch_byte(root: Path, rel: str) -> None:
    path = root / rel
    path.write_bytes(path.read_bytes() + b"\n")


#: (name, mutation, expected diagnostic, why it matters)
#:
#: The fourth field is what makes this more than a count of red lights. A mutation that fails is
#: not evidence that the mutation was caught: while this file was being written, the staged copy
#: failed every case at once because the manifest was stale, and each negative case reported a
#: pass. Requiring the checker's own message to name the thing that was changed is what separates
#: "it exited non-zero" from "it noticed". ``None`` marks a control that must succeed.
SEAL_CASES: tuple[tuple[str, Callable[[Path], None], str | None, str], ...] = (
    (
        "the untouched tree",
        lambda root: None,
        None,
        "if the staged copy does not verify, every failure below is meaningless -- and the usual "
        "cause is that this file, which is itself sealed, was edited without rebuilding "
        "seal/SEAL-MANIFEST.json. Every other case then fails on that instead of on its own "
        "mutation, which is precisely what the expected-diagnostic field exists to expose",
    ),
    (
        "one byte added to a sealed file",
        lambda root: _touch_byte(root, "seal/protocol.md"),
        "seal/protocol.md: sha256",
        "the protocol is the text the deposit holds; a trailing newline is the smallest edit "
        "there is",
    ),
    (
        "a threshold moved in the sealed rules",
        lambda root: _rewrite(root, "seal/decision-rules.json", '"value": 0.75', '"value": 0.85'),
        "seal/decision-rules.json: sha256",
        "moving the R5 band after the fact is the specific thing the seal exists to prevent",
    ),
    (
        "the model digest changed in the arm spec",
        lambda root: _rewrite(
            root, "seal/arm-spec.json", '"model": "llama3.1:8b"', '"model": "llama3.1:70b"'
        ),
        "seal/arm-spec.json: sha256",
        "substituting a model is the first item on the not-minor-deviations list",
    ),
    (
        "a recorded hash altered, self-hash left alone",
        lambda root: _rewrite_manifest(
            root,
            lambda m: m["files"]["seal/protocol.md"].__setitem__(
                "sha256", _bend_hash(m["files"]["seal/protocol.md"]["sha256"])
            ),
            reseal=False,
        ),
        "self_sha256",
        "the manifest's own self-hash must cover the table of file hashes",
    ),
    (
        "a recorded hash altered and the self-hash recomputed to match",
        lambda root: _rewrite_manifest(
            root,
            lambda m: m["files"]["seal/protocol.md"].__setitem__(
                "sha256", _bend_hash(m["files"]["seal/protocol.md"]["sha256"])
            ),
            reseal=True,
        ),
        "seal/protocol.md: sha256",
        "an internally consistent manifest is not enough: the files themselves are hashed. "
        "Without this case the previous one could pass on the self-hash alone and the file "
        "comparison would never be exercised at all",
    ),
    (
        "a sealed path dropped from the manifest, self-hash recomputed",
        lambda root: _rewrite_manifest(
            root, lambda m: m["files"].pop("seal/arm-spec.json"), reseal=True
        ),
        "missing from the manifest",
        "the sealed set is declared in the checker, so quietly shrinking the manifest must fail",
    ),
    (
        "an unexpected path added to the manifest, self-hash recomputed",
        lambda root: _rewrite_manifest(
            root,
            lambda m: m["files"].__setitem__("seal/extra.json", {"sha256": "0" * 64, "size": 0}),
            reseal=True,
        ),
        "not expected",
        "the set must match in both directions, not merely contain what is expected",
    ),
    (
        "the band moved in the manuscript only",
        lambda root: _rewrite(root, "manuscript/main.md", BAND_IN_RENDERED_TEXT, BAND_MOVED),
        "manuscript/main.md: the rule text has drifted",
        "no sealed byte changes here. This is the case the hashes cannot see, and the reason the "
        "rule text is generated rather than written out a second time",
    ),
    (
        "the band moved in both carriers, sealed rules untouched",
        lambda root: (
            _rewrite(root, "manuscript/main.md", BAND_IN_RENDERED_TEXT, BAND_MOVED),
            _rewrite(root, "seal/protocol.md", BAND_IN_RENDERED_TEXT, BAND_MOVED),
        )
        and None,
        "seal/protocol.md: sha256",
        "editing both carriers consistently is still not consistent overall. The diagnostic "
        "named here is the hash and not the drift, because the protocol is sealed and the hash "
        "is reached first; this case therefore demonstrates the hash door, and the case above "
        "demonstrates the drift door. Neither one shows both",
    ),
    (
        "a branch label rewritten in the manuscript",
        lambda root: _rewrite(
            root, "manuscript/main.md", "**R1 — replication**", "**R1 — non-replication**"
        ),
        "manuscript/main.md: the rule text has drifted",
        "renaming a branch after the fact changes which claim the reader thinks was licensed",
    ),
    (
        "the generated block removed from the manuscript",
        lambda root: _rewrite(
            root,
            "manuscript/main.md",
            BLOCK_BEGIN,
            "",
        ),
        "expected exactly one generated block",
        "deleting the block must fail rather than vacuously satisfy a check that only compares "
        "what it happens to find",
    ),
    (
        "the generated block duplicated, the copy altered",
        lambda root: (root / "manuscript" / "main.md").write_text(
            (root / "manuscript" / "main.md").read_text(encoding="utf-8")
            + "\n"
            + _rendered_block(root).replace(BAND_IN_RENDERED_TEXT, BAND_MOVED)
            + "\n",
            encoding="utf-8",
            newline="\n",
        ),
        "expected exactly one generated block",
        "appending a second, altered copy leaves the first one intact, so a checker that finds "
        "the block and compares it would pass. The marker count is what refuses. This branch had "
        "no case until a review weakened the count test and nothing failed",
    ),
    (
        "a line deleted from inside the generated block",
        lambda root: _drop_a_block_line(root),
        "the rule text has drifted",
        "a deletion inside the block, as opposed to an edit. Any deletion shifts every later "
        "line, so this is caught by the line-by-line comparison and reports the first shifted "
        "line -- not by the length comparison, which the first draft of this case expected. That "
        "branch of _first_difference cannot be reached through the marker extraction at all",
    ),
    (
        "no-op: prose added to the manuscript outside the block",
        lambda root: (root / "manuscript" / "main.md").write_text(
            (root / "manuscript" / "main.md").read_text(encoding="utf-8")
            + "\nA sentence that touches nothing sealed.\n",
            encoding="utf-8",
            newline="\n",
        ),
        None,
        "the manuscript is not sealed, and a seal that forbade editing it would be one nobody "
        "could keep. If this case fails, the seal is too wide rather than too narrow",
    ),
)

#: A marker a case can put in the thresholds dict to say "run without --run-verdict at all",
#: rather than "run with these thresholds". Needed because the branch that refuses to skip the
#: threshold comparison cannot be reached by supplying any value.
OMIT_VERDICT_FILE = "__omit_verdict_file__"

#: The server times a conforming witness carries, as **literal spellings** written out here.
#:
#: Three properties are deliberate. The three ISO-8601 forms below -- a fractional-second offset,
#: a whole-second offset, and ``Z`` -- are what the two services actually return. One of them is
#: **later as a string and earlier as an instant** than the true maximum, so a checker that
#: compared these as text rather than as moments would fail the control case. And nothing here is
#: imported from the checker, so the fixture cannot agree with it by construction.
FIXTURE_RECORD_TIMES: tuple[tuple[str, str], ...] = (
    ("record.created", "2026-09-13T08:00:00.123456+00:00"),
    ("record.updated", "2026-09-13T08:05:00+00:00"),
)

#: Per-deposited-file times. The first file's ``updated`` is the true maximum; the second file's
#: is the string-later, instant-earlier decoy (18:45+10:00 is 08:45Z).
FIXTURE_FILE_TIMES: tuple[tuple[str, str], ...] = (
    ("created", "2026-09-13T08:01:00+00:00"),
    ("updated", "2026-09-13T08:02:00+00:00"),
)
FIXTURE_LATEST_FILE_UPDATED: str = "2026-09-13T09:30:00Z"
FIXTURE_DECOY_FILE_UPDATED: str = "2026-09-13T18:45:00+10:00"
FIXTURE_REGISTERED: str = "2026-09-13T08:10:00.000Z"

#: The latest of all of the above **as an instant**.
FIXTURE_LATEST: str = FIXTURE_LATEST_FILE_UPDATED


def _witness_for(root: Path, **overrides: Any) -> dict[str, Any]:
    """Build a conforming deposit witness for the staged tree, optionally spoiling one part.

    The fixture mirrors a real deposit: one deposited file per sealed path, named by its
    basename, with the archive's own listing carried alongside. That shape matters, because the
    checker requires the time sources and the per-file entries to answer to that listing; a
    fixture that carried only the parts the old checker read would pass for the wrong reason.
    """
    deposit_files: list[dict[str, Any]] = []
    entries: list[dict[str, Any]] = []
    sources: list[dict[str, str]] = [
        {"source": name, "value": value} for name, value in FIXTURE_RECORD_TIMES
    ]
    for index, rel in enumerate(sorted(SEALED_PATHS)):
        blob = (root / rel).read_bytes()
        digest = hashlib.md5(blob).hexdigest()  # noqa: S324
        key = Path(rel).name
        checksum = f"md5:{digest}"
        for field, value in FIXTURE_FILE_TIMES:
            if field == "updated":
                if index == 0:
                    value = FIXTURE_LATEST_FILE_UPDATED
                elif index == 1:
                    value = FIXTURE_DECOY_FILE_UPDATED
            sources.append({"source": f"files.{key}.{field}", "value": value})
        deposit_files.append(
            {
                "key": key,
                "checksum": checksum,
                "size": len(blob),
                "created": FIXTURE_FILE_TIMES[0][1],
                "updated": FIXTURE_FILE_TIMES[1][1],
            }
        )
        entries.append(
            {
                "sealed_path": rel,
                "checksum": checksum,
                "deposit_key": key,
                "size": len(blob),
            }
        )
    sources.append({"source": "datacite.registered", "value": FIXTURE_REGISTERED})

    if "drop" in overrides:
        entries = [e for e in entries if e["sealed_path"] != overrides["drop"]]
    if "corrupt" in overrides:
        for entry in entries:
            if entry["sealed_path"] == overrides["corrupt"]:
                entry["checksum"] = "md5:" + "0" * 32
    if "algorithm" in overrides:
        entries[0]["checksum"] = f"{overrides['algorithm']}:00"
    if "rehash" in overrides:
        # Re-record one entry under another algorithm, correctly computed from the local bytes.
        # This is the shape the fabricated witness had: locally right, never published anywhere.
        algorithm, rel = overrides["rehash"]
        for entry in entries:
            if entry["sealed_path"] == rel:
                blob = (root / rel).read_bytes()
                entry["checksum"] = f"{algorithm}:{hashlib.new(algorithm, blob).hexdigest()}"
    if "deposit_key" in overrides:
        rel, key = overrides["deposit_key"]
        for entry in entries:
            if entry["sealed_path"] == rel:
                entry["deposit_key"] = key
    if "relist_checksum" in overrides:
        key, checksum = overrides["relist_checksum"]
        for listed in deposit_files:
            if listed["key"] == key:
                listed["checksum"] = checksum
    if "relist_size" in overrides:
        key, size = overrides["relist_size"]
        for listed in deposit_files:
            if listed["key"] == key:
                listed["size"] = size

    if "drop_time_source" in overrides:
        sources = [s for s in sources if s["source"] != overrides["drop_time_source"]]
    if overrides.get("drop_file_times"):
        sources = [s for s in sources if not s["source"].startswith("files.")]
    if "retime" in overrides:
        name, value = overrides["retime"]
        for source in sources:
            if source["source"] == name:
                source["value"] = value
    if "add_time_source" in overrides:
        name, value = overrides["add_time_source"]
        sources.append({"source": name, "value": value})

    witness: dict[str, Any] = {
        "schema": overrides.get("schema", "cds-deposit-witness-1"),
        "record_api_url": "https://archive.invalid/api/records/000",
        "latest_server_time": overrides.get("anchor", FIXTURE_LATEST),
        "time_sources": sources,
        "deposit_files": deposit_files,
        "files": entries,
    }
    if "registry_reason" in overrides:
        witness["datacite_absent_reason"] = overrides["registry_reason"]
    if overrides.get("no_time_sources"):
        del witness["time_sources"]
    if overrides.get("no_deposit_files"):
        del witness["deposit_files"]
    return witness


#: (name, how to build the witness, expected diagnostic, why it matters)
#:
#: ``--witness`` is the outside half of the binding, and the history of these cases is the reason
#: to distrust a green light here. They were added because the sealed protocol described the
#: witness in the present tense while the code path had never run against anything. They were then
#: **rewritten**, because an independent review wrote a witness out of nothing -- digests computed
#: locally in an algorithm no archive publishes, timestamps from the year 2000, a per-file time
#: naming a file that did not exist, and the string "trust me" where a reason belonged -- and the
#: checker reported no problems at all. The cases below are one per hole that review opened, plus
#: the fabricated witness itself as a regression case.
#:
#: What none of them can establish is that a witness came from an archive. That is not a gap in
#: the fixtures; it is a property of an offline check, and it is stated in the manuscript rather
#: than patched over here.
WITNESS_CASES: tuple[tuple[str, Callable[[Path], dict[str, Any]], str | None, str], ...] = (
    (
        "a witness listing every sealed file with the right checksum",
        lambda root: _witness_for(root),
        None,
        "the conforming case; without it every rejection below could come from a broken fixture",
    ),
    (
        "a witness whose checksum for one file is wrong",
        lambda root: _witness_for(root, corrupt="seal/protocol.md"),
        "the deposit holds",
        "this is the whole purpose of a witness: the deposit and the working tree disagreeing",
    ),
    (
        "a witness that omits one sealed file",
        lambda root: _witness_for(root, drop="seal/arm-spec.json"),
        "no deposit witness",
        "a partial deposit attests to part of the seal, and silence about the rest must not read "
        "as attestation",
    ),
    (
        "a witness naming a checksum algorithm that does not exist",
        lambda root: _witness_for(root, algorithm="notahash"),
        "the archive publishes",
        "a malformed record must be an error rather than an unchecked entry",
    ),
    (
        "a witness with no entries at all",
        lambda root: {
            "schema": "cds-deposit-witness-1",
            "latest_server_time": "2026-09-13T00:00:00Z",
            "files": [],
        },
        "'files' must be a non-empty list",
        "an empty deposit must fail rather than vacuously agree",
    ),
    # --- the shape of the document, rather than one field in it ----------------------------- #
    (
        "the fabricated witness an independent review wrote out of nothing",
        lambda root: {
            "schema": "cds-deposit-witness-1",
            "latest_server_time": "2000-01-01T00:00:02Z",
            "datacite_absent_reason": "trust me",
            "time_sources": [
                {"source": "record.created", "value": "2000-01-01T00:00:00Z"},
                {"source": "record.updated", "value": "2000-01-01T00:00:01Z"},
                {"source": "files.fabricated.updated", "value": "2000-01-01T00:00:02Z"},
            ],
            "files": [
                {
                    "sealed_path": rel,
                    "checksum": "sha256:"
                    + hashlib.sha256((root / rel).read_bytes()).hexdigest(),
                }
                for rel in sorted(SEALED_PATHS)
            ],
        },
        "'deposit_files' must be a non-empty list",
        "this exact document passed every check that existed before it was written: locally "
        "correct digests in an algorithm no archive publishes, year-2000 times, a per-file time "
        "naming a file that is not in the record, and a reason field reading 'trust me'. It is "
        "kept verbatim so that the hole it found cannot reopen quietly",
    ),
    (
        "a witness carrying no deposit listing",
        lambda root: _witness_for(root, no_deposit_files=True),
        "'deposit_files' must be a non-empty list",
        "the listing is what the times and digests answer to. Without it the witness asserts a "
        "set of times that nothing constrains",
    ),
    (
        "a witness labelled with some other schema",
        lambda root: _witness_for(root, schema="something-else-1"),
        "expected 'cds-deposit-witness-1'",
        "the structure is checked as a whole, so a document of another shape must be refused "
        "rather than read for whichever fields happen to fit",
    ),
    (
        "a witness recording a correct digest in an algorithm no archive publishes",
        lambda root: _witness_for(root, rehash=("sha256", "seal/protocol.md")),
        "the archive publishes",
        "the digest agrees with the local bytes, which is exactly why it must still fail: "
        "agreement with oneself in a form nobody published is not agreement with anybody",
    ),
    (
        "a witness whose entry names a deposited file the listing does not hold",
        lambda root: _witness_for(root, deposit_key=("seal/protocol.md", "not-in-the-record")),
        "which the deposit listing does not hold",
        "a digest that names no particular deposited file floats free of the record, and a "
        "reader re-reading the record would have nothing to compare",
    ),
    (
        "a witness whose entry and listing record different checksums for the same file",
        lambda root: _witness_for(root, relist_checksum=("protocol.md", "md5:" + "0" * 32)),
        "were edited apart",
        "the entry and the listing are two statements about one deposited file. Editing one of "
        "them is the cheapest way to change what the witness says",
    ),
    (
        "a witness whose listing gives a file the wrong size",
        lambda root: _witness_for(root, relist_size=("protocol.md", 1)),
        "size of",
        "size is the second thing the archive publishes about a file, and checking only the "
        "digest leaves half the listing unexamined",
    ),
    # --- the anchor ------------------------------------------------------------------------- #
    # The cases above ask whether the deposit holds these bytes. These ask whether the time the
    # witness reports is the time its own contents imply. The two are independent: a witness can
    # be right about every file and still carry an anchor nobody computed.
    (
        "a witness reporting an anchor later than every time it carries",
        lambda root: _witness_for(root, anchor="2027-01-01T00:00:00Z"),
        "the latest time this witness carries",
        "the anchor is the one number the manuscript quotes from the deposit. If it is copied "
        "rather than recomputed, a witness whose files all agree can still date the deposit to "
        "whenever suits the claim",
    ),
    (
        "a witness carrying no server times at all",
        lambda root: _witness_for(root, no_time_sources=True),
        "'time_sources' must be a non-empty list",
        "an anchor with nothing under it is an assertion. Requiring the raw times is what lets "
        "the maximum be re-taken by someone else",
    ),
    (
        "a witness whose anchor includes the depositor-supplied publication date",
        lambda root: _witness_for(
            root, add_time_source=("publication_date", "2027-06-01T00:00:00Z")
        ),
        "supplied by the depositor",
        "the publication date is typed in by whoever fills the record in. Admitting it to the "
        "anchor would let the deposit be dated by its depositor, which is the whole property the "
        "outside half is supposed to supply",
    ),
    (
        "a witness anchored to a per-file time for a file that is not in the record",
        lambda root: _witness_for(
            root, add_time_source=("files.fabricated.updated", "2027-06-01T00:00:00Z")
        ),
        "answers to nothing in the deposit listing",
        "an invented source name is how an anchor moves without any real time changing. Before "
        "this case, one `files.` prefix was enough to satisfy the per-file requirement, so a "
        "witness could drop the real latest time and anchor to a file it made up",
    ),
    (
        "a witness that omits the record's own creation time",
        lambda root: _witness_for(root, drop_time_source="record.created"),
        "omits the time sources ['record.created']",
        "an anchor taken over a chosen subset is narrower than the one the design defines, and a "
        "narrower anchor reads as a stronger claim than was earned",
    ),
    (
        "a witness that omits the updated time of one deposited file",
        lambda root: _witness_for(root, drop_time_source="files.protocol.md.updated"),
        "omits the time sources ['files.protocol.md.updated']",
        "the listing implies one created and one updated time per file. Requiring the set rather "
        "than a sample is what stops the latest real timestamp being dropped",
    ),
    (
        "a witness that carries no per-file time",
        # The anchor is restated because dropping the file times moves the true maximum to the
        # registry time. A case that also got the anchor wrong would be two mutations at once,
        # and the diagnostic it was written to provoke would no longer be the only one available.
        lambda root: _witness_for(
            root, drop_file_times=True, anchor="2026-09-13T08:10:00.000Z"
        ),
        "'files.repro.sh.created'",
        "the editable window after publication allows a file to be replaced without the record's "
        "own timestamps moving, so a record-level anchor would miss exactly the change it exists "
        "to bound",
    ),
    (
        "a witness listing the same server time twice",
        lambda root: _witness_for(
            root, add_time_source=("record.created", "2026-09-13T08:00:00.123456+00:00")
        ),
        "appear more than once",
        "a listing that says one field twice cannot be read as an archive's answer, and a "
        "duplicate is how a second value for the same field gets in beside the first",
    ),
    (
        "a witness carrying a time with no timezone",
        # A non-maximal source is retimed on purpose: stripping the offset from the latest one
        # would also invalidate the anchor, and the case would then pass on either diagnostic.
        lambda root: _witness_for(root, retime=("record.updated", "2026-09-13T08:05:00")),
        "has no timezone",
        "the two services answer in different ISO-8601 spellings, so the anchor is a maximum "
        "over parsed instants. A value that cannot be placed on that line has to be an error "
        "rather than an entry that quietly sorts as text",
    ),
    (
        "a witness whose registry time is neither present nor accounted for",
        lambda root: _witness_for(root, drop_time_source="datacite.registered"),
        "nor a non-empty 'datacite_absent_reason'",
        "a registry that was not consulted is a legitimate state and a silently missing anchor "
        "is not. The difference is whether the reader is told",
    ),
    (
        "a witness accounting for the missing registry time with an empty string",
        lambda root: _witness_for(
            root, drop_time_source="datacite.registered", registry_reason="   "
        ),
        "nor a non-empty 'datacite_absent_reason'",
        "a truthiness test on this field would accept any value at all, so the declared-absence "
        "path would become a way to drop an anchor rather than a way to disclose one",
    ),
    (
        "a witness with no registry time but a stated reason for its absence",
        lambda root: _witness_for(
            root,
            drop_time_source="datacite.registered",
            registry_reason="the DOI had not been registered when this was collected",
        ),
        None,
        "the declared-absence path is a control, not an afterthought: if it failed, the only way "
        "to pass would be to consult the registry, and the honest narrower witness would be "
        "unshippable",
    ),
)


#: (name, mutation of (manifest, thresholds), expected diagnostic, why it matters)
#:
#: The first six cases below are the six categories ``seal/arm-spec.json`` calls not-minor
#: deviations. Every one of them is here because an independent review found that the checker
#: compared four of the six: a manifest naming a different model, with a zeroed digest and
#: ``delta_tv_min = 999``, came back as matching the sealed spec. A list of commitments with no
#: case per commitment is how that goes unnoticed.
RUN_MANIFEST_CASES: tuple[
    tuple[str, Callable[[dict[str, Any], dict[str, Any], str], None], str | None, str], ...
] = (
    (
        "a run manifest that names this seal and matches the arm spec",
        lambda m, th, seal_hash: m.__setitem__("sealed_manifest_sha256", seal_hash),
        None,
        "the conforming case; without it every rejection below could come from a broken fixture",
    ),
    (
        "1/6 a substituted model",
        lambda m, th, seal_hash: (
            m.__setitem__("sealed_manifest_sha256", seal_hash),
            m["env_pins"].__setitem__("model", "attacker:999b"),
        )
        and None,
        "model at env_pins.model",
        "substituting a model is the first item on the not-minor-deviations list, and it was one "
        "of the two the checker used to wave through",
    ),
    (
        "1/6 the same model, a different digest",
        lambda m, th, seal_hash: (
            m.__setitem__("sealed_manifest_sha256", seal_hash),
            m["env_pins"].__setitem__("model_digest", "0" * 64),
        )
        and None,
        "model_digest at env_pins.model_digest",
        "a model tag is a mutable label; the digest is what actually pins the weights",
    ),
    (
        "the think regime flipped",
        lambda m, th, seal_hash: (
            m.__setitem__("sealed_manifest_sha256", seal_hash),
            m["env_pins"].__setitem__("think", True),
        )
        and None,
        "think at env_pins.think",
        "the completed measurement was made with think disabled, and the estimand is not the "
        "same quantity with it enabled",
    ),
    (
        "2/6 a different backend version",
        lambda m, th, seal_hash: (
            m.__setitem__("sealed_manifest_sha256", seal_hash),
            m["env_pins"].__setitem__("ollama_version", "0.33.0"),
        )
        and None,
        "ollama_version at env_pins.ollama_version",
        "the control arm exists precisely to detect drift across this version change",
    ),
    (
        "3/6 a moved threshold",
        lambda m, th, seal_hash: (
            m.__setitem__("sealed_manifest_sha256", seal_hash),
            th.__setitem__("delta_tv_min", 999),
        )
        and None,
        "threshold delta_tv_min",
        "moving the materiality margin after the fact is the single change that most alters what "
        "the result means, and it was the other one the checker waved through",
    ),
    (
        "3/6 a threshold quietly dropped",
        lambda m, th, seal_hash: (
            m.__setitem__("sealed_manifest_sha256", seal_hash),
            th.pop("power_min"),
        )
        and None,
        "is sealed but not recorded",
        "a gate that stops being recorded is a gate that stops being applied",
    ),
    (
        "3/6 a threshold added after the fact",
        lambda m, th, seal_hash: (
            m.__setitem__("sealed_manifest_sha256", seal_hash),
            th.__setitem__("extra_gate", 1),
        )
        and None,
        "is not in the seal",
        "the comparison must run in both directions, or a new condition can be introduced with "
        "the run in hand",
    ),
    (
        "the thresholds recorded as an empty mapping",
        lambda m, th, seal_hash: (
            m.__setitem__("sealed_manifest_sha256", seal_hash),
            th.clear(),
        )
        and None,
        "is sealed but not recorded",
        "an empty block must fail per missing key rather than vacuously agree. The diagnostic "
        "named here is the per-key one, not \"has no 'thresholds' mapping\": an empty dict is "
        "still a mapping, and the first draft of this case expected the wrong message",
    ),
    (
        "no verdict supplied, so the thresholds go unchecked",
        lambda m, th, seal_hash: (
            m.__setitem__("sealed_manifest_sha256", seal_hash),
            th.__setitem__(OMIT_VERDICT_FILE, True),
        )
        and None,
        "--run-verdict was not given",
        "a check that can be skipped does not enforce a commitment. Omitting the verdict must "
        "fail rather than pass quietly, and nothing else here exercises that branch",
    ),
    (
        "4/6 a different seed",
        lambda m, th, seal_hash: (
            m.__setitem__("sealed_manifest_sha256", seal_hash),
            m["run"].__setitem__("seed", 12345),
        )
        and None,
        "seed at run.seed",
        "the seed is frozen; a re-run at another seed is a different study",
    ),
    (
        "5/6 a different M",
        lambda m, th, seal_hash: (
            m.__setitem__("sealed_manifest_sha256", seal_hash),
            m["run"].__setitem__("m_draws", 30),
        )
        and None,
        "m_draws at run.m_draws",
        "M and K are what the power worksheet was computed at",
    ),
    (
        "6/6 a substituted context bank",
        lambda m, th, seal_hash: (
            m.__setitem__("sealed_manifest_sha256", seal_hash),
            m.__setitem__("bank_checksum", "0" * 64),
        )
        and None,
        "bank_checksum at bank_checksum",
        "the bank is what makes the contexts frozen rather than merely eight of something",
    ),
    (
        "a run manifest naming a different seal",
        lambda m, th, seal_hash: m.__setitem__("sealed_manifest_sha256", _bend_hash(seal_hash)),
        "names seal",
        "a run that points at some other seal is not this pre-registration",
    ),
    (
        "a run manifest that names no seal at all",
        lambda m, th, seal_hash: None,
        "it does not name a seal",
        "silence must not read as agreement",
    ),
)


def _seal_hash_of(root: Path) -> str:
    manifest = json.loads((root / "seal" / "SEAL-MANIFEST.json").read_text(encoding="utf-8"))
    return str(manifest["self_sha256"])


def _judge(name: str, expected: str | None, why: str, code: int, output: str) -> str | None:
    """Return a problem string, or None when the case behaved as declared.

    Three ways a case can be wrong, and all three are checked: a control that failed, a mutation
    that was not noticed, and -- the one that is easy to omit -- a mutation that failed for some
    unrelated reason and would have been counted as caught.
    """
    trace = output.strip().replace("\n", "\n      ")
    if expected is None:
        if code != 0:
            return f"{name}: expected this to verify (reason: {why}) but it exited {code}:\n      {trace}"
        return None
    if code == 0:
        return f"{name}: expected a failure (reason: {why}) but the check reported OK"
    if expected not in output:
        return (
            f"{name}: the check did fail, but not for the stated reason. Expected the "
            f"diagnostic to mention {expected!r} (reason: {why}). What it said:\n      {trace}"
        )
    return None


def run_seal_family(tmp: Path) -> list[str]:
    problems: list[str] = []

    for index, (name, mutate, expected, why) in enumerate(SEAL_CASES):
        case_dir = tmp / f"seal-{index:02d}"
        case_dir.mkdir()
        root = _stage(case_dir)
        mutate(root)
        code, output = _run_seal_checker(root)
        problem = _judge(name, expected, why, code, output)
        if problem is not None:
            problems.append(problem)

    for index, (name, build_witness, expected, why) in enumerate(WITNESS_CASES):
        case_dir = tmp / f"witness-{index:02d}"
        case_dir.mkdir()
        root = _stage(case_dir)
        witness_path = case_dir / "witness.json"
        witness_path.write_text(json.dumps(build_witness(root), indent=2), encoding="utf-8")
        code, output = _run_seal_checker(root, witness=witness_path)
        problem = _judge(name, expected, why, code, output)
        if problem is not None:
            problems.append(problem)

    for index, (name, build, expected, why) in enumerate(RUN_MANIFEST_CASES):
        case_dir = tmp / f"manifest-{index:02d}"
        case_dir.mkdir()
        root = _stage(case_dir)
        manifest = json.loads(json.dumps(CONFORMING_RUN_MANIFEST))
        thresholds = json.loads(json.dumps(CONFORMING_THRESHOLDS))
        build(manifest, thresholds, _seal_hash_of(root))
        manifest_path = case_dir / "run-manifest.json"
        manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        if thresholds.pop(OMIT_VERDICT_FILE, False):
            verdict_path = None
        else:
            verdict_path = case_dir / "run-verdict.json"
            verdict_path.write_text(
                json.dumps({"thresholds": thresholds}, indent=2), encoding="utf-8"
            )
        code, output = _run_seal_checker(root, manifest_path, verdict_path)
        problem = _judge(name, expected, why, code, output)
        if problem is not None:
            problems.append(problem)

    return problems



# ================================================================================================ #
# Family 3 -- the collector, driven end to end against a synthetic archive
# ================================================================================================ #
#
# The two families above check the seal and the rules. Neither runs
# ``collect_zenodo_witness.py``, and that gap has a specific cost: the collector writes the witness
# and ``verify_seal.py`` reads it, so a tightening of the reader can leave the writer producing a
# document the run refuses. The place that would surface is **after the deposit**, where the sealed
# files can no longer be changed. So the collector is driven here, offline, against a response
# shaped like the archive's, and its output is handed to the sealed checker.
#
# The response below is built from the staged tree rather than recorded from the network. That is
# the right trade for this purpose -- the question is whether writer and reader agree on a shape,
# not what the archive actually holds -- and the shape itself was taken from a real unauthenticated
# read of the public API, recorded in the task notes.

#: Times the synthetic archive assigns. Same three ISO-8601 spellings, same decoy: the second
#: file's ``updated`` is later as a string and earlier as an instant than the true maximum.
ARCHIVE_RECORD_CREATED = "2026-09-13T08:00:00.123456+00:00"
ARCHIVE_RECORD_UPDATED = "2026-09-13T08:05:00+00:00"
ARCHIVE_FILE_CREATED = "2026-09-13T08:01:00+00:00"
ARCHIVE_FILE_UPDATED = "2026-09-13T08:02:00+00:00"
ARCHIVE_LATEST = "2026-09-13T09:30:00Z"
ARCHIVE_DECOY = "2026-09-13T18:45:00+10:00"
ARCHIVE_REGISTERED = "2026-09-13T08:10:00.000Z"


def _synthetic_archive(root: Path, omit: str | None = None) -> Callable[[str, float], Any]:
    """Return a reader that answers like the public API, for the files in the staged tree."""
    entries = []
    for index, rel in enumerate(sorted(SEALED_PATHS)):
        if rel == omit:
            continue
        blob = (root / rel).read_bytes()
        updated = ARCHIVE_FILE_UPDATED
        if index == 0:
            updated = ARCHIVE_LATEST
        elif index == 1:
            updated = ARCHIVE_DECOY
        entries.append(
            {
                "key": Path(rel).name,
                "checksum": f"md5:{hashlib.md5(blob).hexdigest()}",  # noqa: S324
                "size": len(blob),
                "created": ARCHIVE_FILE_CREATED,
                "updated": updated,
            }
        )

    # The identifiers below are deliberately **not DOI-shaped**. This file is sealed, so it
    # ships to an anonymous review unredacted, and the bundle's leak scan matches the shape
    # `10.<digits>/...` wherever it appears -- which is correct of it, since a DOI is identifying
    # when it is the author's own deposit and no pattern can tell that from a citation. A
    # plausible-looking fake here would therefore fail the bundle build, with nothing that could
    # be done about it short of breaking the seal. The collector only passes this string through
    # to a URL, and the reader below ignores the URL, so the shape is free.
    record = {
        "id": "000",
        "doi": "archive-invalid/000",
        "conceptdoi": "archive-invalid/999",
        "created": ARCHIVE_RECORD_CREATED,
        "updated": ARCHIVE_RECORD_UPDATED,
        "metadata": {"publication_date": "2026-09-13"},
    }

    def read(url: str, timeout: float) -> Any:
        if url.endswith("/files"):
            return {"entries": entries}
        if "/dois/" in url:
            return {"data": {"attributes": {"registered": ARCHIVE_REGISTERED}}}
        return record

    return read


def run_collector_family(tmp: Path) -> list[str]:
    """Drive the collector against a synthetic archive and check the round-trip and the refusal."""
    problems: list[str] = []

    # 1. The maximum is over instants, not strings. Asked of the collector directly, because the
    #    collector computes the anchor and the checker recomputes it: both have to agree, and a
    #    string comparison in either one is the same bug with two places to hide.
    spelled = [
        {"source": "a", "value": ARCHIVE_LATEST},
        {"source": "b", "value": ARCHIVE_DECOY},
    ]
    chosen = collector_latest(spelled)
    if chosen != ARCHIVE_LATEST:
        problems.append(
            "the collector's anchor is not the latest instant: it chose "
            f"{chosen!r} over {ARCHIVE_LATEST!r}. {ARCHIVE_DECOY!r} sorts later as text and "
            "earlier as a moment, which is what a string comparison gets wrong"
        )

    # 2. The round-trip. The collector writes a witness; the sealed checker must accept it.
    case_dir = tmp / "collector-roundtrip"
    case_dir.mkdir(parents=True, exist_ok=True)
    root = _stage(case_dir)
    out = case_dir / "witness.json"
    code = collector_main(
        [
            "--repo-root",
            str(root),
            "--record-api-url",
            "https://archive.invalid/api/records/000",
            "--datacite-api-base",
            "https://registry.invalid/dois",
            "--out",
            str(out),
        ],
        fetch=_synthetic_archive(root),
    )
    if code != 0:
        problems.append(f"the collector refused a complete synthetic deposit (exit {code})")
    elif not out.is_file():
        problems.append("the collector reported success but wrote no witness")
    else:
        seal_code, output = _run_seal_checker(root, witness=out)
        if seal_code != 0:
            trace = output.strip().replace("\n", "\n      ")
            problems.append(
                "the checker rejected the witness the collector wrote. Writer and reader "
                f"disagree about the shape of a witness:\n      {trace}"
            )

    # 3. The refusal. A deposit missing one sealed file must produce no witness at all, rather
    #    than a partial one that reads as complete.
    case_dir = tmp / "collector-partial"
    case_dir.mkdir(parents=True, exist_ok=True)
    root = _stage(case_dir)
    out = case_dir / "witness.json"
    code = collector_main(
        [
            "--repo-root",
            str(root),
            "--record-api-url",
            "https://archive.invalid/api/records/000",
            "--datacite-absent-reason",
            "not consulted in this fixture",
            "--out",
            str(out),
        ],
        fetch=_synthetic_archive(root, omit="seal/protocol.md"),
    )
    if code == 0:
        problems.append(
            "the collector accepted a deposit missing seal/protocol.md; a witness covering part "
            "of the seal would read as covering all of it"
        )
    if out.exists():
        problems.append(
            "the collector wrote a witness for an incomplete deposit. Refusing has to mean "
            "writing nothing, or the next run picks up the partial file"
        )
    return problems


def main() -> int:
    if not RULES.is_file():
        print(f"[scope] FAIL: the sealed rules are missing: {RULES}", file=sys.stderr)
        return 1
    if not (REPO_ROOT / "seal" / "SEAL-MANIFEST.json").is_file():
        print("[scope] FAIL: the seal manifest is missing; nothing to measure", file=sys.stderr)
        return 1

    problems: list[str] = []

    if set(SEALED_PATHS) != EXPECTED_SEALED_SET:
        missing = sorted(EXPECTED_SEALED_SET - set(SEALED_PATHS))
        extra = sorted(set(SEALED_PATHS) - EXPECTED_SEALED_SET)
        problems.append(
            "the sealed set has changed without this file being updated; "
            f"dropped from the checker: {missing}; added to the checker: {extra}. "
            "Both lists are meant to be edited together, so that narrowing the seal cannot be "
            "done in one place and then blessed by a rebuilt manifest"
        )

    with tempfile.TemporaryDirectory() as raw_tmp:
        tmp = Path(raw_tmp)
        rules_tmp = tmp / "rules"
        rules_tmp.mkdir()
        for name, control, primary, expected, why in CASES:
            code, branch = _run(rules_tmp, control, primary)
            if expected is None:
                if code == 0:
                    problems.append(
                        f"{name}: expected a non-zero exit (reason: {why}) but the "
                        f"evaluator succeeded and reported branch {branch!r}"
                    )
            elif code != 0:
                problems.append(
                    f"{name}: expected branch {expected!r} (reason: {why}) but the "
                    f"evaluator exited {code}"
                )
            elif branch != expected:
                problems.append(
                    f"{name}: expected branch {expected!r} (reason: {why}) but got {branch!r}"
                )

        problems.extend(run_seal_family(tmp))
        problems.extend(run_collector_family(tmp))

    if problems:
        print("[scope] FAIL", file=sys.stderr)
        for problem in problems:
            print(f"  - {problem}", file=sys.stderr)
        return 1

    rejected_rules = sum(1 for case in CASES if case[3] is None)
    seal_family = SEAL_CASES + RUN_MANIFEST_CASES + WITNESS_CASES
    controls = sum(1 for case in seal_family if case[2] is None)
    print(
        f"[scope] OK: {len(CASES)} decision-rule cases ({rejected_rules} of them required to be "
        f"rejected), and {len(seal_family)} seal and run-manifest cases of which {controls} are "
        f"controls that had to succeed and {len(seal_family) - controls} had to fail with a "
        "diagnostic naming what was changed. The collector was also driven end to end against a "
        "synthetic archive response, and the witness it wrote had to be one this checker "
        "accepts. This measures the reach of the checks, not the correctness of the rules."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
