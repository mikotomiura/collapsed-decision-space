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
be shown is that there is **no consistent edit** -- that moving a threshold in the manuscript alone
fails the generated-text check, that moving it in the sealed rules alone fails the hash, and that
altering a hash recorded in the manifest fails whether or not the manifest's self-hash is
recomputed to match.

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

import json
import shutil
import subprocess
import sys
import tempfile
from collections.abc import Callable
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

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

#: Files the seal checker reads that are not themselves sealed. ``main.md`` is here because the
#: generated-text check reads it; it is deliberately *not* sealed, since the manuscript grows a
#: completion report after the run and a seal that forbade that would be a seal nobody could keep.
UNSEALED_INPUTS: tuple[str, ...] = ("manuscript/main.md",)

#: A run manifest that agrees with ``seal/arm-spec.json`` on every field the spec calls a
#: not-minor deviation. Written out here as literals rather than read from the arm spec: a fixture
#: copied from the file it is checking agrees with it whatever either one says. The consequence is
#: intended -- changing a frozen value in the arm spec breaks this case, which is the correct
#: outcome for a value that is not supposed to change.
CONFORMING_RUN_MANIFEST: dict[str, Any] = {
    "env_pins": {
        "model": "llama3.1:8b",
        "qwen3_model_digest": "500a1f067a9f782620b40bee6f7b0c89e17ae61f686b92c24933e4ca4b2b8b41",
        "ollama_version": "0.32.12",
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

#: A fragment of the generated rule block, quoted from the rendering rather than from the JSON.
#: Used to move a threshold in a carrier file without touching the sealed rules.
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


def _run_seal_checker(root: Path, run_manifest: Path | None = None) -> tuple[int, str]:
    argv = [sys.executable, str(SEAL_CHECKER), "--repo-root", str(root)]
    if run_manifest is not None:
        argv += ["--run-manifest", str(run_manifest)]
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
        "there is no consistent edit of the carriers alone. The diagnostic named here is the "
        "hash rather than the drift, because the protocol is sealed and the hash is reached "
        "first -- the point of the case is that both doors are shut, not which one is nearer",
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
            "<!-- BEGIN GENERATED FROM seal/decision-rules.json -- DO NOT EDIT BY HAND -->",
            "",
        ),
        "expected exactly one generated block",
        "deleting the block must fail rather than vacuously satisfy a check that only compares "
        "what it happens to find",
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

#: (name, how to build the run manifest, expected diagnostic, why it matters)
RUN_MANIFEST_CASES: tuple[
    tuple[str, Callable[[dict[str, Any], str], None], str | None, str], ...
] = (
    (
        "a run manifest that names this seal and matches the arm spec",
        lambda manifest, seal_hash: manifest.__setitem__("sealed_manifest_sha256", seal_hash),
        None,
        "the conforming case; without it every rejection below could come from a broken fixture",
    ),
    (
        "a run manifest naming a different seal",
        lambda manifest, seal_hash: manifest.__setitem__(
            "sealed_manifest_sha256", _bend_hash(seal_hash)
        ),
        "names seal",
        "a run that points at some other seal is not this pre-registration",
    ),
    (
        "a run manifest that names no seal at all",
        lambda manifest, seal_hash: None,
        "it does not name a seal",
        "silence must not read as agreement",
    ),
    (
        "a run under a different backend version",
        lambda manifest, seal_hash: (
            manifest.__setitem__("sealed_manifest_sha256", seal_hash),
            manifest["env_pins"].__setitem__("ollama_version", "0.33.0"),
        )
        and None,
        "ollama_version at env_pins.ollama_version",
        "changing the backend version is the second item on the not-minor-deviations list, and "
        "the whole point of writing that list into a file was that it be checked",
    ),
    (
        "a run at a different seed",
        lambda manifest, seal_hash: (
            manifest.__setitem__("sealed_manifest_sha256", seal_hash),
            manifest["run"].__setitem__("seed", 12345),
        )
        and None,
        "seed at run.seed",
        "the seed is frozen; a re-run at another seed is a different study",
    ),
    (
        "a run over a substituted context bank",
        lambda manifest, seal_hash: (
            manifest.__setitem__("sealed_manifest_sha256", seal_hash),
            manifest.__setitem__("bank_checksum", "0" * 64),
        )
        and None,
        "bank_checksum at bank_checksum",
        "the bank is what makes the contexts frozen rather than merely eight of something",
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

    for index, (name, build, expected, why) in enumerate(RUN_MANIFEST_CASES):
        case_dir = tmp / f"manifest-{index:02d}"
        case_dir.mkdir()
        root = _stage(case_dir)
        manifest = json.loads(json.dumps(CONFORMING_RUN_MANIFEST))
        build(manifest, _seal_hash_of(root))
        manifest_path = case_dir / "run-manifest.json"
        manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        code, output = _run_seal_checker(root, manifest_path)
        problem = _judge(name, expected, why, code, output)
        if problem is not None:
            problems.append(problem)

    return problems


def main() -> int:
    if not RULES.is_file():
        print(f"[scope] FAIL: the sealed rules are missing: {RULES}", file=sys.stderr)
        return 1
    if not (REPO_ROOT / "seal" / "SEAL-MANIFEST.json").is_file():
        print("[scope] FAIL: the seal manifest is missing; nothing to measure", file=sys.stderr)
        return 1

    problems: list[str] = []
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

    if problems:
        print("[scope] FAIL", file=sys.stderr)
        for problem in problems:
            print(f"  - {problem}", file=sys.stderr)
        return 1

    rejected_rules = sum(1 for case in CASES if case[3] is None)
    seal_family = SEAL_CASES + RUN_MANIFEST_CASES
    controls = sum(1 for case in seal_family if case[2] is None)
    print(
        f"[scope] OK: {len(CASES)} decision-rule cases ({rejected_rules} of them required to be "
        f"rejected), and {len(seal_family)} seal and run-manifest cases of which {controls} are "
        f"controls that had to succeed and {len(seal_family) - controls} had to fail with a "
        "diagnostic naming what was changed. This measures the reach of the checks, not the "
        "correctness of the rules."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
