#!/usr/bin/env python3
"""Held-out check of a post-hoc hypothesis: more ``None`` destinations with the channel on.

The hypothesis was formed by looking at the completed run (``data/raw/bank_annotation.jsonl``:
``None`` in 124 of 2400 channel-off draws and 206 of 2400 channel-on draws, on > off in 8 of 8
contexts). This script tests it on the two prospective arms. The specification is
``analysis/heldout-stay/SPEC.ja.md``; every parameter comes from
``analysis/heldout-stay/freeze.json`` or from the sealed ``seal/arm-spec.json``, and nothing that
decides the outcome is defined here twice.

Modes
-----
``--self-test``
    Positive, negative and fixture controls on known data only, including an end-to-end pass of
    synthetic arms through the same assembly the run uses, and the run guards against a throwaway
    git repository. The prospective arms are never read in this mode.
``--mutations``
    Copies this script into a temporary tree, breaks it in one place at a time, and requires
    ``--self-test`` of the broken copy to fail **for the stated reason**. No-op controls must pass.
``--run``
    The single execution on the prospective arms. It refuses unless the freeze commit is the last
    commit that touched the frozen files, those files are tracked and unmodified, the commit is on
    a remote, and no result or log exists yet. Nothing about the outcome is printed until both
    ``result.json`` and ``run.log`` have been created.
``--verify``
    Recomputes ``result.json`` from ``data/prospective/``, requires byte equality with it and with
    ``run.log``, and requires the recorded freeze commit to still be the last commit that touched
    the frozen files. While no run has landed it reports SKIPPED, which is not the same as passed.

What this establishes, and what it does not, is stated in SPEC.ja.md. Two limits are worth
repeating next to the code. The channel-on block ran before the channel-off block in every context,
so a difference is not separated from execution order, and the exact level of the test itself
assumes the draws within a context are exchangeable with respect to execution position. And a
freeze commit shows that the specification existed before the result; it does not show that
nobody had looked, and "once" is kept by these guards and by the published history, not proven.

Usage:  python analysis/scripts/heldout_stay_check.py --self-test [--cproper-records PATH]
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import shutil
import subprocess
import sys
import tempfile
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from fractions import Fraction
from itertools import combinations
from pathlib import Path
from typing import Any

import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "analysis" / "apparatus"))

from erre_sandbox.cognition.parse import (  # noqa: E402
    MAX_RAW_PLAN_BYTES,
    _extract_json_object,
    parse_llm_plan,
)

SPEC_REL = "analysis/heldout-stay"
SHIPPED_DIR = REPO_ROOT / "data" / "prospective"
COMPLETED_ANNOTATION = REPO_ROOT / "data" / "raw" / "bank_annotation.jsonl"

#: Everything whose bytes at the freeze commit constitute "the frozen specification": the text, the
#: parameters, this script, the workflow that runs it, the vendored parser and what it imports, the
#: locked environment, the sealed arm spec the meaning gate reads, and the positive-control input.
FROZEN_PATHS: tuple[str, ...] = (
    "analysis/heldout-stay/SPEC.ja.md",
    "analysis/heldout-stay/freeze.json",
    "analysis/scripts/heldout_stay_check.py",
    ".github/workflows/heldout-stay.yml",
    "analysis/apparatus",
    "env/pyproject.toml",
    "env/uv.lock",
    "seal/arm-spec.json",
    "data/raw/bank_annotation.jsonl",
)

ARMS: tuple[str, str] = ("control", "primary")
CONDITIONS: tuple[str, str] = ("on", "off")
ZONES: tuple[str, ...] = ("agora", "chashitsu", "garden", "peripatos", "study")
#: The six categories of the secondary analysis: the five zones, then ``None``.
CATEGORY_INDEX: dict[str | None, int] = {**{z: i for i, z in enumerate(ZONES)}, None: len(ZONES)}
ANNOTATION_KEYS = frozenset(
    {"frozen_ctx_id", "condition", "mc_index", "pre_bias_destination_zone", "resolved_from"}
)
RECORD_KEYS = frozenset(
    {
        "condition",
        "frozen_ctx_id",
        "mc_index",
        "pre_bias_destination_zone",
        "raw_response",
        "sampling",
        "system_prompt",
        "user_prompt",
    }
)
INPUT_FILES: tuple[str, ...] = ("run_annotation.jsonl", "run_records.jsonl", "run-manifest.json")
CLASSES: tuple[str, ...] = ("N_str", "N_json", "K", "Z", "S", "F")
EXPLICIT_NULL = frozenset({"N_str", "N_json"})


# --------------------------------------------------------------------------- #
# Freeze and sealed expectations
# --------------------------------------------------------------------------- #


def load_freeze(root: Path = REPO_ROOT) -> dict[str, Any]:
    return json.loads((root / SPEC_REL / "freeze.json").read_text("utf-8"))


def alpha_of(freeze: dict[str, Any]) -> Fraction:
    return Fraction(freeze["alpha"])


def expectations(arm: str, freeze: dict[str, Any], root: Path = REPO_ROOT) -> dict[str, Any]:
    """What the meaning gate (I3) requires of an arm, read from the sealed arm spec and freeze.json."""
    spec = json.loads((root / "seal" / "arm-spec.json").read_text("utf-8"))
    return {
        "arm": arm,
        "model": spec["arms"][arm]["model"],
        "model_digest": spec["arms"][arm]["model_digest"],
        "think": spec["arms"][arm]["think"],
        "ollama_version": spec["environment"]["ollama_version"],
        "bank_checksum": spec["context_bank"]["bank_checksum"],
        "context_ids": spec["context_bank"]["context_ids"],
        "k_contexts": spec["sampling"]["k_contexts"],
        "m_draws": spec["sampling"]["m_draws"],
        "seed": spec["sampling"]["seed"],
        "sampling": freeze["semantics"]["sampling"],
    }


# --------------------------------------------------------------------------- #
# Reading
# --------------------------------------------------------------------------- #


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def jsonl(data: bytes) -> list[dict[str, Any]]:
    lines = data.decode("utf-8").split("\n")
    if lines and lines[-1] == "":
        lines.pop()
    return [json.loads(line) for line in lines]


def canonical(rows: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    """Rows in (context, on-before-off, mc_index) order, whatever order they arrived in."""
    return sorted(
        rows,
        key=lambda r: (r["frozen_ctx_id"], CONDITIONS.index(r["condition"]), r["mc_index"]),
    )


# --------------------------------------------------------------------------- #
# The outcome and the classifier
# --------------------------------------------------------------------------- #


def is_none(row: dict[str, Any]) -> bool:
    """The primary outcome: the apparatus recorded no destination."""
    return row["pre_bias_destination_zone"] is None


def classify(raw: str) -> str:
    """How a draw recorded as ``None`` expresses its destination, read from the raw response.

    ``N_str``: the string "null" (after strip and casefold). ``N_json``: JSON null. ``K``: no
    ``destination_zone`` key (the parser's default is ``None``, so this can be a valid plan).
    ``Z``: a zone name, so the plan failed on spelling or on another field. ``S``: any other
    value. ``F``: no JSON object, malformed JSON, not an object, or over the parser's size limit.
    The steps are the apparatus parser's own, stopped where it would fail.
    """
    if len(raw) > MAX_RAW_PLAN_BYTES:
        return "F"
    block = _extract_json_object(raw)
    if block is None:
        return "F"
    try:
        payload = json.loads(block)
    except json.JSONDecodeError:
        return "F"
    if not isinstance(payload, dict):
        return "F"
    if "destination_zone" not in payload:
        return "K"
    value = payload["destination_zone"]
    if value is None:
        return "N_json"
    if isinstance(value, str):
        folded = value.strip().casefold()
        if folded == "null":
            return "N_str"
        if folded in ZONES:
            return "Z"
    return "S"


def reparsed_zone(raw: str) -> str | None:
    """What the apparatus records for ``raw``: the parsed destination, or ``None``."""
    plan = parse_llm_plan(raw)
    if plan is None or plan.destination_zone is None:
        return None
    return plan.destination_zone.value


# --------------------------------------------------------------------------- #
# The exact stratified test
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class Stratum:
    key: str
    n_on: int
    n_total: int
    successes: int
    on_successes: int


def strata_of(rows: Iterable[dict[str, Any]], indicator: Callable[[dict[str, Any]], bool]) -> list[Stratum]:
    counts: dict[str, list[int]] = {}
    for row in rows:
        key = row["frozen_ctx_id"]
        cell = counts.setdefault(key, [0, 0, 0, 0])
        y = indicator(row)
        on = row["condition"] == "on"
        cell[0] += on
        cell[1] += 1
        cell[2] += y
        cell[3] += y and on
    return [Stratum(key, *counts[key]) for key in sorted(counts)]


@dataclass(frozen=True)
class NullDistribution:
    """Exact distribution of T = sum of on-side successes, given every stratum's margins.

    ``weights[i]`` is proportional to P(T = offset + i); the constant is ``denominator``. Integers
    throughout, so the tail probabilities are exact fractions and identical on every platform.
    """

    offset: int
    weights: tuple[int, ...]
    denominator: int

    def upper(self, t: int) -> Fraction:
        return Fraction(sum(w for i, w in enumerate(self.weights) if self.offset + i >= t), self.denominator)

    def lower(self, t: int) -> Fraction:
        return Fraction(sum(w for i, w in enumerate(self.weights) if self.offset + i <= t), self.denominator)

    @property
    def t_max(self) -> int:
        return self.offset + len(self.weights) - 1


def _stratum_weights(s: Stratum, psi: Fraction = Fraction(1)) -> tuple[int, list[int]]:
    """Integer weights proportional to P(X = lo + i) under common odds ratio ``psi``.

    ``psi = num/den`` enters as ``num**x * den**(hi - x)``, which keeps the ratios of a Fisher
    noncentral hypergeometric while staying in integers. At ``psi = 1`` the weights sum to
    ``comb(n_total, successes)`` (Vandermonde), the central hypergeometric.
    """
    lo = max(0, s.successes - (s.n_total - s.n_on))
    hi = min(s.successes, s.n_on)
    num, den = psi.numerator, psi.denominator
    return lo, [
        math.comb(s.n_on, x) * math.comb(s.n_total - s.n_on, s.successes - x) * num**x * den ** (hi - x)
        for x in range(lo, hi + 1)
    ]


def _convolve(a: list[int], b: list[int]) -> list[int]:
    out = [0] * (len(a) + len(b) - 1)
    for i, x in enumerate(a):
        if x == 0:
            continue
        for j, y in enumerate(b):
            out[i + j] += x * y
    return out


def null_distribution(strata: list[Stratum]) -> NullDistribution:
    offset, weights, denominator = 0, [1], 1
    for s in strata:
        lo, w = _stratum_weights(s)
        offset += lo
        weights = _convolve(weights, w)
        denominator *= math.comb(s.n_total, s.successes)
    return NullDistribution(offset, tuple(weights), denominator)


def rejects(p: Fraction, alpha: Fraction) -> bool:
    return p <= alpha


@dataclass(frozen=True)
class TestResult:
    t_obs: int
    successes: int
    t_max: int
    p_upper: Fraction
    p_lower: Fraction
    p_min: Fraction

    def testable(self, alpha: Fraction) -> bool:
        """I7: whether the most extreme arrangement could reach alpha at all."""
        return rejects(self.p_min, alpha)


def stratified_test(strata: list[Stratum]) -> TestResult:
    null = null_distribution(strata)
    t_obs = sum(s.on_successes for s in strata)
    return TestResult(
        t_obs=t_obs,
        successes=sum(s.successes for s in strata),
        t_max=null.t_max,
        p_upper=null.upper(t_obs),
        p_lower=null.lower(t_obs),
        p_min=null.upper(null.t_max),
    )


def critical_value(null: NullDistribution, alpha: Fraction) -> int:
    """The smallest t whose upper tail is at most alpha."""
    for t in range(null.offset, null.t_max + 1):
        if rejects(null.upper(t), alpha):
            return t
    return null.t_max + 1


def exact_power(strata: list[Stratum], psi: Fraction, alpha: Fraction) -> Fraction:
    """P(T >= t_crit) when every stratum has common odds ratio ``psi`` (Fisher noncentral)."""
    t_crit = critical_value(null_distribution(strata), alpha)
    offset, dist, total = 0, [1], 1
    for s in strata:
        lo, w = _stratum_weights(s, psi)
        offset += lo
        dist = _convolve(dist, w)
        total *= sum(w)
    return Fraction(sum(v for i, v in enumerate(dist) if offset + i >= t_crit), total)


def mantel_haenszel(strata: list[Stratum]) -> tuple[Fraction | None, float | None, float | None]:
    """Common odds ratio (on vs off), with the Robins-Breslow-Greenland 95% interval."""
    sr = ss = Fraction(0)
    prs = psqr = qss = 0.0
    for s in strata:
        a = s.on_successes
        b = s.n_on - a
        c = s.successes - a
        d = s.n_total - s.n_on - c
        n = s.n_total
        r, q = Fraction(a * d, n), Fraction(b * c, n)
        p_, q_ = (a + d) / n, (b + c) / n
        sr += r
        ss += q
        prs += p_ * float(r)
        psqr += p_ * float(q) + q_ * float(r)
        qss += q_ * float(q)
    if sr == 0 or ss == 0:
        return None, None, None
    fr, fs = float(sr), float(ss)
    var = prs / (2 * fr**2) + psqr / (2 * fr * fs) + qss / (2 * fs**2)
    half = 1.959963984540054 * math.sqrt(var)
    log_or = math.log(fr / fs)
    return sr / ss, math.exp(log_or - half), math.exp(log_or + half)


# --------------------------------------------------------------------------- #
# The secondary analysis: six-category mean TV, stratified permutation
# --------------------------------------------------------------------------- #


def _tv(on: np.ndarray, off: np.ndarray) -> float:
    k = len(CATEGORY_INDEX)
    a = np.bincount(on, minlength=k).astype(np.float64) / on.shape[0]
    b = np.bincount(off, minlength=k).astype(np.float64) / off.shape[0]
    return float(0.5 * np.sum(np.abs(a - b)))


def tv6(rows: list[dict[str, Any]], *, replicates: int, seed: int, decimals: int) -> dict[str, str]:
    """Mean over contexts of TV(on, off) on five zones plus ``None``; bank_scorer's permutation."""
    by_ctx: dict[str, dict[str, list[int]]] = {}
    for row in canonical(rows):
        cell = by_ctx.setdefault(row["frozen_ctx_id"], {"on": [], "off": []})
        cell[row["condition"]].append(CATEGORY_INDEX[row["pre_bias_destination_zone"]])
    pairs = [(np.array(by_ctx[c]["on"]), np.array(by_ctx[c]["off"])) for c in sorted(by_ctx)]
    observed = sum(_tv(on, off) for on, off in pairs) / len(pairs)
    rng = np.random.default_rng(seed)
    pooled = [np.concatenate([on, off]) for on, off in pairs]
    n_on = [on.shape[0] for on, _ in pairs]
    null = np.empty(replicates, dtype=np.float64)
    for b in range(replicates):
        total = 0.0
        for pool, k in zip(pooled, n_on, strict=True):
            perm = rng.permutation(pool)
            total += _tv(perm[:k], perm[k:])
        null[b] = round(total / len(pairs), decimals)
    ge = int(np.sum(null >= round(observed, decimals)))
    return {
        "observed": f"{observed:.6f}",
        "null_mean": f"{float(np.mean(null)):.6f}",
        "null_p95": f"{float(np.quantile(null, 0.95)):.6f}",
        "p_value": f"{(ge + 1) / (replicates + 1):.6f}",
    }


# --------------------------------------------------------------------------- #
# Integrity gates I1-I6 (a failure is a defect: STOP, not an outcome)
# --------------------------------------------------------------------------- #


def integrity(
    files: dict[str, bytes],
    *,
    pins: dict[str, dict[str, Any]],
    expect: dict[str, Any],
    known: dict[str, Any],
) -> tuple[list[str], list[dict[str, Any]], list[dict[str, Any]]]:
    """Return (problems, annotation rows, record rows). Stops at the first gate that fails."""
    # I1 -- the bytes are the bytes that were pinned.
    problems = [
        f"I1: {name} sha256 {sha256(files[name])[:12]} != pin {pins[name]['sha256'][:12]}"
        for name in INPUT_FILES
        if sha256(files[name]) != pins[name]["sha256"] or len(files[name]) != pins[name]["bytes"]
    ]
    if problems:
        return problems, [], []

    annotation = jsonl(files["run_annotation.jsonl"])
    records = jsonl(files["run_records.jsonl"])
    contexts, m = list(expect["context_ids"]), int(expect["m_draws"])

    # I2 -- the structure the design says, in the order it says.
    expected = [(c, cond, i) for c in sorted(contexts) for cond in CONDITIONS for i in range(m)]
    for name, rows, keys in (("annotation", annotation, ANNOTATION_KEYS), ("records", records, RECORD_KEYS)):
        if len(rows) != len(expected):
            problems.append(f"I2: {name} has {len(rows)} rows, expected {len(expected)}")
            continue
        bad_keys = sum(1 for r in rows if set(r) != keys)
        if bad_keys:
            problems.append(f"I2: {name} has {bad_keys} rows with unexpected keys")
            continue
        order = [(r["frozen_ctx_id"], r["condition"], r["mc_index"]) for r in rows]
        if order != expected:
            problems.append(f"I2: {name} is not (context, on block then off block, mc_index) ordered")
        bad_zones = sum(1 for r in rows if r["pre_bias_destination_zone"] not in CATEGORY_INDEX)
        if bad_zones:
            problems.append(f"I2: {name} has {bad_zones} rows with an unknown zone value")
    if problems:
        return problems, [], []

    # I3 -- the files mean what the specification says: which arm, which model, which bank, which
    # sampling per condition, and one prompt per context shared by both conditions.
    problems = meaning_problems(files, records, expect)
    if problems:
        return problems, [], []

    # I4 -- annotation and records describe the same draws.
    mismatched = sum(
        1
        for a, r in zip(annotation, records, strict=True)
        if a["pre_bias_destination_zone"] != r["pre_bias_destination_zone"]
    )
    if mismatched:
        return [f"I4: {mismatched} draws where annotation and records disagree"], [], []

    # I5 -- the apparatus parser, rerun on the raw text, reproduces every recorded value.
    unreproduced = sum(1 for r in records if reparsed_zone(r["raw_response"]) != r["pre_bias_destination_zone"])
    if unreproduced:
        return [f"I5: {unreproduced} draws whose raw response does not reparse to the recorded value"], [], []

    # I6 -- the values declared as known before the freeze are the values in the file.
    total = sum(1 for r in annotation if is_none(r))
    cell_max = max(
        sum(1 for r in annotation if r["frozen_ctx_id"] == c and r["condition"] == cond and is_none(r))
        for c in contexts
        for cond in CONDITIONS
    )
    if total != known["none_total"]:
        problems.append(f"I6: None total {total} != declared {known['none_total']}")
    if f"{cell_max / m:.6f}" != known["cell_none_rate_max"]:
        problems.append(f"I6: cell None-rate max {cell_max / m:.6f} != declared {known['cell_none_rate_max']}")
    return problems, annotation, records


def meaning_problems(files: dict[str, bytes], records: list[dict[str, Any]], expect: dict[str, Any]) -> list[str]:
    manifest = json.loads(files["run-manifest.json"])
    pins = manifest.get("env_pins", {})
    run = manifest.get("run", {})
    observed = {
        "arm": manifest.get("arm"),
        "model": pins.get("model"),
        "model_digest": pins.get("model_digest"),
        "think": pins.get("think"),
        "ollama_version": pins.get("ollama_version"),
        "bank_checksum": manifest.get("bank_checksum"),
        "context_ids": run.get("context_ids"),
        "k_contexts": run.get("k_contexts"),
        "m_draws": run.get("m_draws"),
        "seed": run.get("seed"),
    }
    problems = [f"I3: manifest {key} = {observed[key]!r}, expected {expect[key]!r}" for key in observed if observed[key] != expect[key]]
    artifacts = manifest.get("artifacts", {})
    for name in ("run_annotation.jsonl", "run_records.jsonl"):
        if artifacts.get(name, {}).get("sha256") != sha256(files[name]):
            problems.append(f"I3: manifest does not record the digest of {name}")
    wrong_sampling = sum(1 for r in records if r["sampling"] != expect["sampling"][r["condition"]])
    if wrong_sampling:
        problems.append(f"I3: {wrong_sampling} draws whose sampling is not the one declared for their condition")
    prompts: dict[str, set[tuple[str, str]]] = {}
    for r in records:
        prompts.setdefault(r["frozen_ctx_id"], set()).add((r["system_prompt"], r["user_prompt"]))
    varied = sorted(c for c, p in prompts.items() if len(p) != 1)
    if varied:
        problems.append(f"I3: contexts whose prompt differs between draws or conditions: {varied}")
    return problems


# --------------------------------------------------------------------------- #
# The interpretation table
# --------------------------------------------------------------------------- #


def evaluate_row(
    *,
    integrity_ok: bool,
    control_testable: bool,
    control_p: Fraction,
    primary_testable: bool,
    primary_p: Fraction,
    alpha: Fraction,
) -> str:
    """The row of the frozen table. Fixed sequence: primary is confirmatory only after control."""
    if not integrity_ok:
        return "STOP"
    if not control_testable:
        return "E"
    if not rejects(control_p, alpha):
        return "C" if primary_testable and rejects(primary_p, alpha) else "D"
    if not primary_testable:
        return "B_prime"
    return "A" if rejects(primary_p, alpha) else "B"


def explicit_null_modifier(*, confirmed: bool, null_p: Fraction, alpha: Fraction) -> bool:
    """IUT: the explicit-null wording only if the None test was confirmed and this test rejects too."""
    return confirmed and rejects(null_p, alpha)


def reverse_modifier(*, p_lower: Fraction, alpha: Fraction) -> bool:
    return rejects(p_lower, alpha)


# --------------------------------------------------------------------------- #
# One arm, and the assembly of both
# --------------------------------------------------------------------------- #


def _e6(x: Fraction | float) -> str:
    return f"{float(x):.6e}"


def _rate(rows: list[dict[str, Any]], cond: str, keep: Callable[[int], bool]) -> float:
    chosen = [r for r in rows if r["condition"] == cond and keep(r["mc_index"])]
    return sum(1 for r in chosen if is_none(r)) / len(chosen)


def describe_arm(
    annotation: list[dict[str, Any]],
    records: list[dict[str, Any]] | None,
    *,
    freeze: dict[str, Any],
) -> dict[str, Any]:
    annotation = canonical(annotation)
    strata = strata_of(annotation, is_none)
    test = stratified_test(strata)
    mh, lo, hi = mantel_haenszel(strata)
    on_total = sum(s.n_on for s in strata)
    off_total = sum(s.n_total - s.n_on for s in strata)
    on_y = test.t_obs
    off_y = test.successes - on_y
    cells = {s.key: {"on": s.on_successes, "off": s.successes - s.on_successes} for s in strata}
    half = freeze["design"]["m_draws"] // 2
    drift = {
        cond: {
            "first_half": f"{_rate(annotation, cond, lambda i: i < half):.6f}",
            "second_half": f"{_rate(annotation, cond, lambda i: i >= half):.6f}",
        }
        for cond in CONDITIONS
    }
    out: dict[str, Any] = {
        "none": {
            "on": on_y,
            "off": off_y,
            "on_rate": f"{on_y / on_total:.6f}",
            "off_rate": f"{off_y / off_total:.6f}",
            "rate_difference": f"{on_y / on_total - off_y / off_total:.6f}",
            "per_context": cells,
            "contexts_on_gt_off": sum(1 for c in cells.values() if c["on"] > c["off"]),
            "contexts_tie": sum(1 for c in cells.values() if c["on"] == c["off"]),
            "contexts_on_lt_off": sum(1 for c in cells.values() if c["on"] < c["off"]),
            "mh_odds_ratio": None if mh is None else f"{float(mh):.6f}",
            "mh_ci95": None if lo is None else [f"{lo:.6f}", f"{hi:.6f}"],
            "block_halves": drift,
        },
        "test": {
            "t_obs": test.t_obs,
            "t_max": test.t_max,
            "p_upper": _e6(test.p_upper),
            "p_lower": _e6(test.p_lower),
            "p_min": _e6(test.p_min),
        },
        "tv6": tv6(
            annotation,
            replicates=freeze["tv6"]["replicates"],
            seed=freeze["tv6"]["seed"],
            decimals=freeze["tv6"]["compare_decimals"],
        ),
    }
    exact: dict[str, TestResult] = {"test": test}
    if records is not None:
        raw_of = {(r["frozen_ctx_id"], r["condition"], r["mc_index"]): r["raw_response"] for r in records}
        classes = {
            (a["frozen_ctx_id"], a["condition"], a["mc_index"]): classify(
                raw_of[(a["frozen_ctx_id"], a["condition"], a["mc_index"])]
            )
            for a in annotation
            if is_none(a)
        }
        table = {k: {cond: 0 for cond in CONDITIONS} for k in CLASSES}
        by_context = {s.key: {k: {cond: 0 for cond in CONDITIONS} for k in CLASSES} for s in strata}
        for (ctx, cond, _), k in classes.items():
            table[k][cond] += 1
            by_context[ctx][k][cond] += 1

        def explicit_null(row: dict[str, Any]) -> bool:
            return classes.get((row["frozen_ctx_id"], row["condition"], row["mc_index"])) in EXPLICIT_NULL

        null_test = stratified_test(strata_of(annotation, explicit_null))
        out["classes"] = table
        out["classes_per_context"] = by_context
        out["explicit_null_test"] = {
            "t_obs": null_test.t_obs,
            "successes": null_test.successes,
            "p_upper": _e6(null_test.p_upper),
            "p_min": _e6(null_test.p_min),
        }
        exact["explicit_null"] = null_test
    return {"summary": out, "exact": exact}


def assemble(arms: dict[str, dict[str, Any]], *, freeze: dict[str, Any], freeze_commit: str) -> dict[str, Any]:
    alpha = alpha_of(freeze)
    control, primary = arms["control"]["exact"], arms["primary"]["exact"]
    c_test, p_test = control["test"], primary["test"]
    c_ok, p_ok = c_test.testable(alpha), p_test.testable(alpha)
    row = evaluate_row(
        integrity_ok=True,
        control_testable=c_ok,
        control_p=c_test.p_upper,
        primary_testable=p_ok,
        primary_p=p_test.p_upper,
        alpha=alpha,
    )
    confirmed = {"control": row in {"A", "B", "B_prime"}, "primary": row == "A"}
    modifiers = {
        arm: {
            "explicit_null": explicit_null_modifier(
                confirmed=confirmed[arm], null_p=arms[arm]["exact"]["explicit_null"].p_upper, alpha=alpha
            ),
            "reverse": reverse_modifier(p_lower=arms[arm]["exact"]["test"].p_lower, alpha=alpha),
        }
        for arm in ARMS
    }
    rows = {r["id"]: r for r in freeze["rows"]}
    return {
        "schema": "heldout-stay-result-1",
        "freeze_commit": freeze_commit,
        "alpha": freeze["alpha"],
        "gates": {
            "control": {"integrity": "PASS", "I7_testable": c_ok},
            "primary": {"integrity": "PASS", "I7_testable": p_ok},
        },
        "arms": {arm: arms[arm]["summary"] for arm in ARMS},
        "confirmatory": {
            "control_tested": c_ok,
            "control_rejected": confirmed["control"],
            "primary_tested": confirmed["control"] and p_ok,
            "primary_rejected": confirmed["primary"],
        },
        "row": rows[row],
        "modifiers": modifiers,
    }


def serialise(result: dict[str, Any]) -> bytes:
    return (json.dumps(result, sort_keys=True, indent=2, ensure_ascii=False) + "\n").encode("utf-8")


def render_log(result: dict[str, Any]) -> str:
    """The run log is a function of the result, so --verify can hold the two to each other."""
    lines = [f"[heldout] run at freeze commit {result['freeze_commit']}"]
    lines += [f"[heldout] {arm}: integrity gates I1-I6 passed" for arm in ARMS]
    for arm in ARMS:
        a = result["arms"][arm]
        lines.append(
            f"[heldout] {arm}: None on {a['none']['on']} / off {a['none']['off']}; "
            f"T = {a['test']['t_obs']}, p_upper = {a['test']['p_upper']}, p_lower = {a['test']['p_lower']}; "
            f"I7 testable = {result['gates'][arm]['I7_testable']}"
        )
        lines.append(
            f"[heldout] {arm}: explicit-null test p_upper = {a['explicit_null_test']['p_upper']}; "
            f"classes = {json.dumps(a['classes'], sort_keys=True)}"
        )
        lines.append(f"[heldout] {arm}: TV6 (secondary) = {json.dumps(a['tv6'], sort_keys=True)}")
    lines.append(f"[heldout] confirmatory = {json.dumps(result['confirmatory'], sort_keys=True)}")
    lines.append(f"[heldout] row = {result['row']['id']}")
    lines.append(f"[heldout] modifiers = {json.dumps(result['modifiers'], sort_keys=True)}")
    lines.append("[heldout] result.json written")
    return "\n".join(lines) + "\n"


def verify_problems(recorded_result: bytes, recorded_log: bytes | None, recomputed: dict[str, Any]) -> list[str]:
    problems = []
    if serialise(recomputed) != recorded_result:
        problems.append("result.json differs from the recomputation")
    if recorded_log is None:
        problems.append("run.log is missing")
    elif render_log(recomputed).encode("utf-8") != recorded_log:
        problems.append("run.log is not what the recorded result renders to")
    return problems


# --------------------------------------------------------------------------- #
# Binding the run to the freeze commit
# --------------------------------------------------------------------------- #


def _git(root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True, check=False)


def binding_problems(freeze_commit: str, *, root: Path, frozen: tuple[str, ...]) -> list[str]:
    """The freeze commit exists, HEAD descends from it, and nothing frozen has changed since."""
    if _git(root, "cat-file", "-e", f"{freeze_commit}^{{commit}}").returncode != 0:
        return [f"freeze commit {freeze_commit} does not exist"]
    full = _git(root, "rev-parse", freeze_commit).stdout.strip()
    problems = []
    if _git(root, "merge-base", "--is-ancestor", full, "HEAD").returncode != 0:
        problems.append("HEAD does not descend from the freeze commit")
    last = _git(root, "log", "-1", "--format=%H", "--", *frozen).stdout.strip()
    if last != full:
        problems.append(f"the freeze commit is not the last commit that touched the frozen files (that is {last[:12]})")
    untracked = [p for p in frozen if _git(root, "ls-files", "--error-unmatch", "--", p).returncode != 0]
    if untracked:
        problems.append(f"frozen paths not tracked by git: {untracked}")
    return problems


def run_guards(freeze_commit: str, *, root: Path, frozen: tuple[str, ...]) -> list[str]:
    problems = binding_problems(freeze_commit, root=root, frozen=frozen)
    if problems and problems[0].endswith("does not exist"):
        return problems
    if _git(root, "status", "--porcelain", "--untracked-files=no").stdout.strip():
        problems.append("tracked files are modified; commit or stash them first")
    if not _git(root, "branch", "-r", "--contains", freeze_commit).stdout.strip():
        problems.append("the freeze commit is not on any remote branch; push it first")
    for name in ("result.json", "run.log"):
        if (root / SPEC_REL / name).exists():
            problems.append(f"{SPEC_REL}/{name} already exists; the run happens once")
    return problems


# --------------------------------------------------------------------------- #
# Computing, running once, verifying
# --------------------------------------------------------------------------- #


def compute(
    inputs: dict[str, Path], freeze: dict[str, Any], freeze_commit: str, root: Path = REPO_ROOT
) -> tuple[dict[str, Any] | None, list[str]]:
    """Silent: returns (result, []) or, when an integrity gate fails, (None, the STOP lines)."""
    arms: dict[str, dict[str, Any]] = {}
    for arm in ARMS:
        files = {name: (inputs[arm] / name).read_bytes() for name in INPUT_FILES}
        problems, annotation, records = integrity(
            files, pins=freeze["inputs"][arm], expect=expectations(arm, freeze, root), known=freeze["known"][arm]
        )
        if problems:
            lines = [f"[heldout] run at freeze commit {freeze_commit}"]
            lines += [f"[heldout] STOP  {arm}: {line}" for line in problems]
            lines.append("[heldout] row = STOP (an integrity gate failed; nothing is interpreted)")
            return None, lines
        arms[arm] = describe_arm(annotation, records, freeze=freeze)
    return assemble(arms, freeze=freeze, freeze_commit=freeze_commit), []


def run(freeze_commit: str, inputs: dict[str, Path]) -> int:
    problems = run_guards(freeze_commit, root=REPO_ROOT, frozen=FROZEN_PATHS)
    if problems:
        for line in problems:
            print(f"[heldout] REFUSED: {line}", file=sys.stderr)
        return 2
    full = _git(REPO_ROOT, "rev-parse", freeze_commit).stdout.strip()
    result, stop = compute(inputs, load_freeze(), full)
    spec_dir = REPO_ROOT / SPEC_REL
    # Nothing about the outcome is shown before both files exist: an interruption leaves no
    # half-seen result behind.
    if result is None:
        with (spec_dir / "run.log").open("x", encoding="utf-8", newline="\n") as log:
            log.write("\n".join(stop) + "\n")
        print("\n".join(stop))
        return 1
    with (spec_dir / "result.json").open("xb") as out:
        out.write(serialise(result))
    text = render_log(result)
    with (spec_dir / "run.log").open("x", encoding="utf-8", newline="\n") as log:
        log.write(text)
    print(text, end="")
    return 0


def verify(root: Path = REPO_ROOT) -> int:
    result_path, log_path = root / SPEC_REL / "result.json", root / SPEC_REL / "run.log"
    if not result_path.exists() and not log_path.exists():
        print("[heldout] SKIPPED --verify: no result.json or run.log (no run has landed)")
        print("[heldout]           a skipped check was not made; it did not succeed")
        return 0
    if not result_path.exists():
        print("[heldout] FAIL  --verify: run.log exists without result.json (the run stopped at a gate)")
        return 1
    recorded = result_path.read_bytes()
    freeze_commit = json.loads(recorded)["freeze_commit"]
    problems = binding_problems(freeze_commit, root=root, frozen=FROZEN_PATHS)
    result, stop = compute({arm: SHIPPED_DIR / arm for arm in ARMS}, load_freeze(root), freeze_commit, root)
    if result is None:
        problems += stop
    else:
        problems += verify_problems(recorded, log_path.read_bytes() if log_path.exists() else None, result)
    for line in problems:
        print(f"[heldout] FAIL  --verify: {line}")
    if problems:
        return 1
    print("[heldout] OK    --verify: result.json and run.log recomputed byte for byte from data/prospective/")
    return 0


# --------------------------------------------------------------------------- #
# Self-test
# --------------------------------------------------------------------------- #

#: Synthetic raw responses with the zone the apparatus records and the class this script assigns,
#: written out by hand. Not derived from parse_llm_plan or classify: a fixture computed by the code
#: under test agrees with it by construction.
RAW_FIXTURES: tuple[tuple[str, str | None, str | None], ...] = (
    ('{"thought": "t", "destination_zone": "study"}', "study", None),
    ('{"thought": "t", "destination_zone": "garden"}', "garden", None),
    ('{"thought": "t", "destination_zone": "null"}', None, "N_str"),
    ('{"thought": "t", "destination_zone": " NULL "}', None, "N_str"),
    ('{"thought": "t", "destination_zone": null}', None, "N_json"),
    ('{"thought": "t"}', None, "K"),
    ('{"thought": "t", "destination_zone": "Study"}', None, "Z"),
    ('{"thought": "t", "destination_zone": "study", "valence_delta": 5}', None, "Z"),
    ('{"thought": "t", "destination_zone": "study", "mood": "calm"}', None, "Z"),
    ('{"thought": "t", "destination_zone": "library"}', None, "S"),
    ('{"thought": "t", "destination_zone": 3}', None, "S"),
    ("no json here", None, "F"),
    ('{"thought": "t", "destination_zone": ', None, "F"),
    ('```json\n{"thought": "t", "destination_zone": "agora"}\n```', "agora", None),
)

_SAMPLING = {
    "on": {"repeat_penalty": 1.0, "temperature": 0.82, "top_p": 0.94},
    "off": {"repeat_penalty": 1.0, "temperature": 0.7, "top_p": 0.9},
}


def _arm_files(cells: dict[tuple[str, str], list[int]], contexts: list[str]) -> tuple[dict[str, bytes], dict[str, Any]]:
    """Files for a synthetic arm whose draws are RAW_FIXTURES indices, and matching expectations."""
    annotation, records = [], []
    for ctx in contexts:
        for cond in CONDITIONS:
            for mc, idx in enumerate(cells[(ctx, cond)]):
                raw, zone, _ = RAW_FIXTURES[idx]
                base = {"frozen_ctx_id": ctx, "condition": cond, "mc_index": mc, "pre_bias_destination_zone": zone}
                annotation.append({**base, "resolved_from": "pre_bias_direct_parse"})
                records.append(
                    {**base, "raw_response": raw, "sampling": _SAMPLING[cond], "system_prompt": f"s-{ctx}", "user_prompt": "u"}
                )
    ann = "".join(json.dumps(r) + "\n" for r in annotation).encode("utf-8")
    rec = "".join(json.dumps(r) + "\n" for r in records).encode("utf-8")
    m = len(cells[(contexts[0], "on")])
    expect = {
        "arm": "control",
        "model": "m",
        "model_digest": "d",
        "think": False,
        "ollama_version": "v",
        "bank_checksum": "b",
        "context_ids": contexts,
        "k_contexts": len(contexts),
        "m_draws": m,
        "seed": 1,
        "sampling": _SAMPLING,
    }
    manifest = {
        "arm": "control",
        "bank_checksum": "b",
        "env_pins": {"model": "m", "model_digest": "d", "think": False, "ollama_version": "v"},
        "run": {"context_ids": contexts, "k_contexts": len(contexts), "m_draws": m, "seed": 1},
        "artifacts": {"run_annotation.jsonl": {"sha256": sha256(ann)}, "run_records.jsonl": {"sha256": sha256(rec)}},
    }
    files = {"run_annotation.jsonl": ann, "run_records.jsonl": rec, "run-manifest.json": (json.dumps(manifest) + "\n").encode()}
    return files, expect


def _pins(files: dict[str, bytes]) -> dict[str, dict[str, Any]]:
    return {name: {"sha256": sha256(data), "bytes": len(data)} for name, data in files.items()}


def _replace_line(data: bytes, index: int, edit: Callable[[dict[str, Any]], None]) -> bytes:
    lines = data.decode("utf-8").split("\n")
    row = json.loads(lines[index])
    edit(row)
    lines[index] = json.dumps(row)
    return "\n".join(lines).encode("utf-8")


def _manifest_edit(files: dict[str, bytes], edit: Callable[[dict[str, Any]], None]) -> dict[str, bytes]:
    manifest = json.loads(files["run-manifest.json"])
    edit(manifest)
    return {**files, "run-manifest.json": (json.dumps(manifest) + "\n").encode()}


class Checks:
    def __init__(self) -> None:
        self.passed: list[str] = []
        self.failed: list[str] = []
        self.skipped: list[str] = []

    def expect(self, code: str, condition: bool, detail: str) -> None:
        if condition:
            self.passed.append(code)
            print(f"[heldout] OK    {code}: {detail}")
        else:
            self.failed.append(code)
            print(f"[heldout] FAIL  {code}: {detail}")

    def skip(self, code: str, reason: str) -> None:
        self.skipped.append(code)
        print(f"[heldout] SKIPPED {code}: {reason}")


def self_test(freeze: dict[str, Any], cproper_records: Path | None) -> int:
    checks = Checks()
    alpha = alpha_of(freeze)
    pc = freeze["positive_control"]

    # --- Positive control: the completed run. The counts are the audit's; the p value, MH odds
    # ratio and TV6 were also recomputed by an independent implementation (SPEC.ja.md section 15).
    data = COMPLETED_ANNOTATION.read_bytes()
    checks.expect("PC-input", sha256(data) == pc["annotation_sha256"], "completed-run annotation matches its pin")
    rows = canonical(jsonl(data))
    strata = strata_of(rows, is_none)
    test = stratified_test(strata)
    on_y, off_y = test.t_obs, test.successes - test.t_obs
    checks.expect("PC-counts", (on_y, off_y) == (pc["on_none"], pc["off_none"]), f"on {on_y} / off {off_y}")
    gt = sum(1 for s in strata if 2 * s.on_successes > s.successes)
    checks.expect("PC-contexts", (len(strata), gt) == (pc["contexts"], pc["contexts_on_gt_off"]), f"{gt}/{len(strata)} on > off")
    checks.expect("PC-p-golden", _e6(test.p_upper) == pc["p_upper"], f"p_upper {_e6(test.p_upper)} (golden {pc['p_upper']})")
    checks.expect("PC-reject", rejects(test.p_upper, alpha), "the completed run's own direction rejects at alpha")
    mh, _, _ = mantel_haenszel(strata)
    checks.expect("PC-mh", mh is not None and f"{float(mh):.6f}" == pc["mh_odds_ratio"], f"MH OR {None if mh is None else float(mh):.6f}")
    t6 = tv6(rows, replicates=freeze["tv6"]["replicates"], seed=freeze["tv6"]["seed"], decimals=freeze["tv6"]["compare_decimals"])
    checks.expect("PC-tv6", t6["observed"] == pc["tv6_observed"] and float(t6["p_value"]) <= float(pc["tv6_p_max"]), f"TV6 {t6}")

    # --- Declared power: the numbers in SPEC.ja.md come from this code, not from elsewhere.
    for entry in freeze["declared_power"]["values"]:
        got = declared_power(freeze, entry["arm"], Fraction(entry["psi"]), alpha)
        checks.expect("DECL-power", f"{float(got):.6f}" == entry["power"], f"{entry['arm']} psi={entry['psi']} power {float(got):.6f}")

    # --- Hand-computable oracles, independent of the code under test.
    # Two 2x2 tables (a, b / c, d) = (3, 1 / 1, 3) and (2, 2 / 1, 3), n = 8 each:
    # MH = (9/8 + 6/8) / (1/8 + 2/8) = 5.
    hand_mh, _, _ = mantel_haenszel([Stratum("s1", 4, 8, 4, 3), Stratum("s2", 4, 8, 3, 2)])
    checks.expect("FIX-mh-hand", hand_mh == Fraction(5), f"MH on the hand-worked tables = {hand_mh} (5 by hand)")
    # on = {0: 1/2, 1: 1/4, None: 1/4}, off = {0: 1/4, 1: 3/4}: TV = (1/4 + 1/2 + 1/4) / 2 = 1/2.
    hand_tv = _tv(np.array([0, 0, 1, 5]), np.array([0, 1, 1, 1]))
    checks.expect("FIX-tv-hand", hand_tv == 0.5, f"TV on the hand-worked pair = {hand_tv} (0.5 by hand)")
    # The exact null's first two moments against the hypergeometric formulas.
    null = null_distribution(strata)
    mean = sum((Fraction((null.offset + i) * w, null.denominator) for i, w in enumerate(null.weights)), Fraction(0))
    second = sum((Fraction((null.offset + i) ** 2 * w, null.denominator) for i, w in enumerate(null.weights)), Fraction(0))
    want_mean = sum((Fraction(s.successes * s.n_on, s.n_total) for s in strata), Fraction(0))
    want_var = sum(
        (
            Fraction(s.successes * s.n_on * (s.n_total - s.n_on) * (s.n_total - s.successes), s.n_total**2 * (s.n_total - 1))
            for s in strata
        ),
        Fraction(0),
    )
    checks.expect("FIX-null-moments", mean == want_mean and second - mean**2 == want_var, "exact null mean and variance equal the formulas")
    # The exact distribution against brute-force enumeration on a case small enough to list. The
    # enumeration fixes the successes and lists the on-sets; the exact code fixes the on-set size
    # and counts the successes. Different counts, the same hypergeometric probabilities.
    brute: dict[int, int] = {}
    for on_a in combinations(range(5), 3):
        for on_b in combinations(range(4), 2):
            t = sum(1 for i in on_a if i < 2) + sum(1 for i in on_b if i < 3)
            brute[t] = brute.get(t, 0) + 1
    small = null_distribution([Stratum("a", 3, 5, 2, 0), Stratum("b", 2, 4, 3, 0)])
    listed = {small.offset + i: Fraction(w, small.denominator) for i, w in enumerate(small.weights) if w}
    enumerated = {t: Fraction(n, sum(brute.values())) for t, n in brute.items()}
    checks.expect("FIX-exact-enum", listed == enumerated, f"{listed} vs {enumerated}")

    # --- Negative control: labels shuffled within context, so the null holds by construction.
    # (That the exact size is at most alpha follows from how the critical value is chosen; it is a
    # sanity check, not an independent calibration. The shuffle is the independent one.)
    size = null.upper(critical_value(null, alpha))
    checks.expect("NC-size", size <= alpha, f"exact size {float(size):.6f} <= alpha {float(alpha):.6f}")
    nc = freeze["negative_control"]
    by_ctx = {s.key: np.array([is_none(r) for r in rows if r["frozen_ctx_id"] == s.key], dtype=bool) for s in strata}
    # Shuffling within a context leaves every margin as it was, so one exact null serves all.
    rejected_at = {t: rejects(null.upper(t), alpha) for t in range(null.offset, null.t_max + 1)}
    reject = 0
    for k in range(nc["replicates"]):
        rng = np.random.default_rng(np.random.SeedSequence([nc["seed"], k]))
        t = 0
        for s in strata:
            perm = rng.permutation(by_ctx[s.key])
            t += int(perm[: s.n_on].sum())
        reject += rejected_at[t]
    rate = reject / nc["replicates"]
    lo_band, hi_band = (float(Fraction(x)) for x in nc["band"])
    checks.expect("NC-band", lo_band <= rate <= hi_band, f"rejection rate {rate:.4f} in [{lo_band}, {hi_band}]")
    se = math.sqrt(float(size) * (1 - float(size)) / nc["replicates"])
    checks.expect("NC-mc-exact", abs(rate - float(size)) <= 4 * se, f"|{rate:.4f} - {float(size):.4f}| <= 4 SE ({4 * se:.4f})")

    # --- The classifier and the reparse, on hand-written fixtures.
    wrong = [raw for raw, zone, cls in RAW_FIXTURES if reparsed_zone(raw) != zone or (zone is None and classify(raw) != cls)]
    checks.expect("FIX-classifier", not wrong, f"{len(RAW_FIXTURES)} fixtures; wrong: {wrong}")

    # --- Integrity gates: a clean synthetic arm passes, and each corruption trips its own gate.
    # None rows by hand: c0 on = fixtures 2, 4; c0 off = 5; c1 on = 6, 9; c1 off = 10, 11, 12.
    # 8 in all, and the fullest cell holds 3 of 3.
    cells = {("c0", "on"): [2, 4, 0], ("c0", "off"): [0, 1, 5], ("c1", "on"): [6, 9, 13], ("c1", "off"): [10, 11, 12]}
    files, expect = _arm_files(cells, ["c0", "c1"])
    known = {"none_total": 8, "cell_none_rate_max": "1.000000"}
    problems, _, _ = integrity(files, pins=_pins(files), expect=expect, known=known)
    checks.expect("FIX-clean", not problems, f"clean synthetic arm: {problems}")
    ann, rec = "run_annotation.jsonl", "run_records.jsonl"
    rewrite_manifest_digests = lambda f: _manifest_edit(  # noqa: E731
        f, lambda m: m["artifacts"].update({ann: {"sha256": sha256(f[ann])}, rec: {"sha256": sha256(f[rec])}})
    )
    corruptions: tuple[tuple[str, dict[str, bytes], bool, dict[str, Any], dict[str, Any]], ...] = (
        ("I1", {**files, "run-manifest.json": files["run-manifest.json"] + b" "}, False, expect, known),
        ("I2", rewrite_manifest_digests({**files, ann: _replace_line(files[ann], 1, lambda r: r.update(mc_index=0))}), True, expect, known),
        ("I3-model", _manifest_edit(files, lambda m: m["env_pins"].update(model="other")), True, expect, known),
        ("I3-sampling", rewrite_manifest_digests({**files, rec: _replace_line(files[rec], 0, lambda r: r.update(sampling=_SAMPLING["off"]))}), True, expect, known),
        ("I3-prompt", rewrite_manifest_digests({**files, rec: _replace_line(files[rec], 3, lambda r: r.update(user_prompt="u2"))}), True, expect, known),
        ("I4", rewrite_manifest_digests({**files, ann: _replace_line(files[ann], 0, lambda r: r.update(pre_bias_destination_zone="agora"))}), True, expect, known),
        ("I5", rewrite_manifest_digests({**files, rec: _replace_line(files[rec], 0, lambda r: r.update(raw_response='{"thought": "t", "destination_zone": "garden"}'))}), True, expect, known),
        ("I6", files, True, expect, {**known, "none_total": 7}),
        ("I6-cell", files, True, expect, {**known, "cell_none_rate_max": "0.666667"}),
    )
    for name, f, repin, exp, kn in corruptions:
        problems, _, _ = integrity(f, pins=_pins(f) if repin else _pins(files), expect=exp, known=kn)
        prefix = name.split("-")[0] + ":"
        checks.expect(f"FIX-{name}", bool(problems) and problems[0].startswith(prefix), f"corruption for {name}: {problems}")

    # --- I7: reachability depends on the margins only.
    tiny = stratified_test([Stratum("a", 300, 600, 2, 2)])
    ample = stratified_test([Stratum("a", 300, 600, 30, 15)])
    checks.expect("FIX-I7", not tiny.testable(alpha) and ample.testable(alpha), f"p_min {float(tiny.p_min):.4f} / {float(ample.p_min):.2e}")

    # --- The table, against literal expectations written independently of evaluate_row.
    lo_p, hi_p = Fraction(1, 1000), Fraction(1, 2)
    table = (
        (dict(integrity_ok=False, control_testable=True, control_p=lo_p, primary_testable=True, primary_p=lo_p), "STOP"),
        (dict(integrity_ok=True, control_testable=False, control_p=hi_p, primary_testable=True, primary_p=lo_p), "E"),
        (dict(integrity_ok=True, control_testable=True, control_p=lo_p, primary_testable=True, primary_p=lo_p), "A"),
        (dict(integrity_ok=True, control_testable=True, control_p=lo_p, primary_testable=True, primary_p=hi_p), "B"),
        (dict(integrity_ok=True, control_testable=True, control_p=lo_p, primary_testable=False, primary_p=hi_p), "B_prime"),
        (dict(integrity_ok=True, control_testable=True, control_p=hi_p, primary_testable=True, primary_p=lo_p), "C"),
        (dict(integrity_ok=True, control_testable=True, control_p=hi_p, primary_testable=True, primary_p=hi_p), "D"),
        (dict(integrity_ok=True, control_testable=True, control_p=alpha, primary_testable=True, primary_p=alpha), "A"),
    )
    for kwargs, want in table:
        got = evaluate_row(alpha=alpha, **kwargs)
        checks.expect("ROW", got == want, f"{want} expected, {got} evaluated")
    checks.expect(
        "MOD-null",
        not explicit_null_modifier(confirmed=True, null_p=hi_p, alpha=alpha)
        and explicit_null_modifier(confirmed=True, null_p=lo_p, alpha=alpha)
        and not explicit_null_modifier(confirmed=False, null_p=lo_p, alpha=alpha),
        "IUT: both conditions are required",
    )
    checks.expect("MOD-reverse", reverse_modifier(p_lower=lo_p, alpha=alpha) and not reverse_modifier(p_lower=hi_p, alpha=alpha), "lower tail at alpha")
    row_ids = {r["id"] for r in freeze["rows"]}
    checks.expect("ROW-ids", row_ids == {"STOP", "A", "B", "B_prime", "C", "D", "E"}, f"frozen rows {sorted(row_ids)}")

    # --- End to end: synthetic arms through describe_arm and assemble, the path --run takes.
    for name, arms_spec, want_row, want_mod in END_TO_END:
        fast = {**_fast(freeze), "design": {**freeze["design"], "m_draws": 40}}
        described = {}
        for arm, spec in arms_spec.items():
            ann_rows, rec_rows = _e2e_rows(spec)
            described[arm] = describe_arm(ann_rows, rec_rows, freeze=fast)
        result = assemble(described, freeze=fast, freeze_commit="0" * 40)
        got = (result["row"]["id"], result["modifiers"])
        checks.expect("E2E", got == (want_row, want_mod), f"{name}: {got[0]} {got[1]} (expected {want_row} {want_mod})")
        if name == END_TO_END[0][0]:
            recorded, log = serialise(result), render_log(result).encode("utf-8")
            tampered = recorded.replace(b'"t_obs": ', b'"t_obs": 1', 1)
            checks.expect(
                "FIX-verify",
                not verify_problems(recorded, log, result)
                and bool(verify_problems(tampered, log, result))
                and bool(verify_problems(recorded, log + b"x", result))
                and bool(verify_problems(recorded, None, result)),
                "verify accepts the recomputed pair and rejects a tampered result, a tampered log and a missing log",
            )

    # --- No-op: the order rows arrive in does not change the result.
    shuffled = list(rows)
    np.random.default_rng(1).shuffle(shuffled)  # type: ignore[arg-type]
    base_arm = describe_arm(rows, None, freeze=_fast(freeze))["summary"]
    moved_arm = describe_arm(shuffled, None, freeze=_fast(freeze))["summary"]
    checks.expect("NOOP-order", base_arm == moved_arm, "row order does not change the summary")

    # --- The run guards, against a throwaway repository with a throwaway remote.
    guard_problems = _guard_selftest()
    checks.expect("FIX-guards", not guard_problems, f"guard scenarios: {guard_problems or 'all as expected'}")

    # --- The specification text carries every frozen row, modifier and forbidden claim verbatim.
    spec = (REPO_ROOT / SPEC_REL / "SPEC.ja.md").read_text("utf-8")
    texts = [r[k] for r in freeze["rows"] for k in ("when", "can_say", "cannot_say", "revision")]
    texts += [m["text"] for m in freeze["modifiers"]] + list(freeze["forbidden_claims"])
    missing = [t for t in texts if t not in spec]
    checks.expect("SPEC-drift", not missing, f"{len(texts)} frozen texts; missing from SPEC.ja.md: {missing}")

    # --- The completed run's raw records, when available locally (not shipped; see SPEC.ja.md).
    if cproper_records is None:
        checks.skip("PC-records", "completed-run bank_records.jsonl not given (it is not shipped)")
    else:
        raw = cproper_records.read_bytes()
        if sha256(raw) != pc["records_sha256"]:
            checks.expect("PC-records", False, "completed-run records do not match their pin")
        else:
            records = jsonl(raw)
            unreproduced = sum(1 for r in records if reparsed_zone(r["raw_response"]) != r["pre_bias_destination_zone"])
            classes = [classify(r["raw_response"]) for r in records if r["pre_bias_destination_zone"] is None]
            counts = {k: classes.count(k) for k in CLASSES if classes.count(k)}
            checks.expect("PC-records", unreproduced == 0 and counts == pc["records_classes"], f"unreproduced {unreproduced}; classes {counts}")

    print(
        f"[heldout] self-test: {len(checks.passed)} passed, {len(checks.failed)} failed, "
        f"{len(checks.skipped)} skipped{(' (' + ', '.join(checks.skipped) + ')') if checks.skipped else ''}"
    )
    if checks.skipped:
        print("[heldout]           a skipped check was not made; it did not succeed")
    return 1 if checks.failed else 0


#: Synthetic two-arm scenarios, 2 contexts x 40 draws per cell, as (code, count) runs per cell.
#: Codes: "null" = the string "null" (explicit null), "lib" = "library" (not explicit), "study".
#: The expected rows and modifiers are written by hand from the scenario, not by running the code.
_STRONG_NULL = {"on": [("null", 20), ("study", 20)], "off": [("null", 2), ("study", 38)]}
_STRONG_LIB = {"on": [("lib", 20), ("study", 20)], "off": [("lib", 2), ("study", 38)]}
_WEAK = {"on": [("null", 5), ("study", 35)], "off": [("null", 5), ("study", 35)]}
_REVERSED = {"on": [("null", 2), ("study", 38)], "off": [("null", 20), ("study", 20)]}
END_TO_END: tuple[tuple[str, dict[str, dict[str, list[tuple[str, int]]]], str, dict[str, dict[str, bool]]], ...] = (
    (
        "both strong; control explicit null, primary other values",
        {"control": _STRONG_NULL, "primary": _STRONG_LIB},
        "A",
        {"control": {"explicit_null": True, "reverse": False}, "primary": {"explicit_null": False, "reverse": False}},
    ),
    (
        "control weak, primary strong",
        {"control": _WEAK, "primary": _STRONG_NULL},
        "C",
        {"control": {"explicit_null": False, "reverse": False}, "primary": {"explicit_null": False, "reverse": False}},
    ),
    (
        "control reversed, primary weak",
        {"control": _REVERSED, "primary": _WEAK},
        "D",
        {"control": {"explicit_null": False, "reverse": True}, "primary": {"explicit_null": False, "reverse": False}},
    ),
)
_E2E_RAW = {
    "null": ('{"thought": "t", "destination_zone": "null"}', None),
    "lib": ('{"thought": "t", "destination_zone": "library"}', None),
    "study": ('{"thought": "t", "destination_zone": "study"}', "study"),
}


def _e2e_rows(spec: dict[str, list[tuple[str, int]]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    annotation, records = [], []
    for ctx in ("e0", "e1"):
        for cond in CONDITIONS:
            codes = [code for code, n in spec[cond] for _ in range(n)]
            for mc, code in enumerate(codes):
                raw, zone = _E2E_RAW[code]
                base = {"frozen_ctx_id": ctx, "condition": cond, "mc_index": mc, "pre_bias_destination_zone": zone}
                annotation.append({**base, "resolved_from": "pre_bias_direct_parse"})
                records.append({**base, "raw_response": raw})
    return annotation, records


def _guard_selftest() -> list[str]:
    """Run the guards against a real, throwaway git repository and report what went unexpected."""
    unexpected: list[str] = []
    frozen = ("spec.txt", "tree")
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        work, remote = Path(tmp) / "work", Path(tmp) / "remote.git"
        work.mkdir()
        (work / SPEC_REL).mkdir(parents=True)
        (work / "tree").mkdir()

        def git(*args: str) -> None:
            done = _git(work, *args)
            if done.returncode != 0:
                raise RuntimeError(f"git {' '.join(args)}: {done.stderr.strip()}")

        _git(Path(tmp), "init", "-q", "--bare", str(remote))
        git("init", "-q")
        git("config", "user.email", "t@example.invalid")
        git("config", "user.name", "t")
        git("config", "commit.gpgsign", "false")
        (work / "spec.txt").write_text("frozen\n", encoding="utf-8")
        (work / "tree" / "a.txt").write_text("a\n", encoding="utf-8")
        (work / "other.txt").write_text("o\n", encoding="utf-8")
        git("add", "-A")
        git("commit", "-q", "-m", "freeze")
        freeze = _git(work, "rev-parse", "HEAD").stdout.strip()

        def case(name: str, want: str | None) -> None:
            problems = run_guards(freeze, root=work, frozen=frozen)
            if want is None and problems:
                unexpected.append(f"{name}: refused ({problems})")
            elif want is not None and not any(want in p for p in problems):
                unexpected.append(f"{name}: expected '{want}', got {problems}")

        case("not pushed", "not on any remote")
        git("remote", "add", "origin", str(remote))
        git("push", "-q", "origin", "HEAD:refs/heads/main")
        git("fetch", "-q", "origin")
        case("clean and pushed", None)
        (work / "other.txt").write_text("changed\n", encoding="utf-8")
        git("commit", "-q", "-am", "not frozen")
        case("a later commit that leaves the frozen files alone", None)
        (work / "tree" / "a.txt").write_text("edited\n", encoding="utf-8")
        case("a frozen file edited, not committed", "tracked files are modified")
        git("commit", "-q", "-am", "edit frozen")
        case("a frozen file edited and committed", "not the last commit that touched the frozen files")
        git("reset", "-q", "--hard", "HEAD~1")
        (work / SPEC_REL / "result.json").write_text("{}\n", encoding="utf-8")
        case("a result already exists", "already exists")
    return unexpected


def declared_power(freeze: dict[str, Any], arm: str, psi: Fraction, alpha: Fraction) -> Fraction:
    """Power under common odds ratio ``psi``, from the arm's known None total split evenly."""
    total = freeze["known"][arm]["none_total"]
    contexts = len(freeze["design"]["contexts"])
    m = freeze["design"]["m_draws"]
    base, extra = divmod(total, contexts)
    strata = [Stratum(f"c{i}", m, 2 * m, base + (1 if i < extra else 0), 0) for i in range(contexts)]
    return exact_power(strata, psi, alpha)


def _fast(freeze: dict[str, Any]) -> dict[str, Any]:
    return {**freeze, "tv6": {**freeze["tv6"], "replicates": 200}}


# --------------------------------------------------------------------------- #
# Mutations
# --------------------------------------------------------------------------- #

_SELF = "analysis/scripts/heldout_stay_check.py"

#: (name, file, old, new, expected diagnostic or None for a no-op control, why)
MUTATIONS: tuple[tuple[str, str, str, str, str | None, str], ...] = (
    ("decision negated", _SELF, "    return p <= alpha\n", "    return p > alpha\n", "FAIL  PC-reject", "the decision line itself"),
    ("direction reversed", _SELF, "        p_upper=null.upper(t_obs),\n", "        p_upper=null.lower(t_obs),\n", "FAIL  PC-p-golden", "a lower-tail p in the upper-tail slot"),
    ("condition labels swapped", _SELF, '        on = row["condition"] == "on"\n', '        on = row["condition"] == "off"\n', "FAIL  PC-counts", "on and off exchanged when counting"),
    ("stratification removed", _SELF, '        key = row["frozen_ctx_id"]\n', '        key = "pooled"\n', "FAIL  PC-contexts", "one stratum instead of one per context"),
    ("None counted as a destination", _SELF, '    return row["pre_bias_destination_zone"] is None\n', '    return row["pre_bias_destination_zone"] is not None\n', "FAIL  PC-counts", "the outcome inverted"),
    ("I1 pin check removed", _SELF, '        if sha256(files[name]) != pins[name]["sha256"] or len(files[name]) != pins[name]["bytes"]\n', "        if False\n", "FAIL  FIX-I1", "bytes that are not the pinned bytes must stop the run"),
    ("I2 order check removed", _SELF, "        if order != expected:\n", "        if False:\n", "FAIL  FIX-I2", "a duplicated mc_index must stop the run"),
    ("I3 manifest check removed", _SELF, " for key in observed if observed[key] != expect[key]]\n", " for key in observed if False]\n", "FAIL  FIX-I3-model", "a manifest naming another model must stop the run"),
    ("I3 sampling check removed", _SELF, "    if wrong_sampling:\n", "    if False:\n", "FAIL  FIX-I3-sampling", "a draw under the other condition's sampling must stop the run"),
    ("I3 prompt check removed", _SELF, "    if varied:\n", "    if False:\n", "FAIL  FIX-I3-prompt", "a prompt that differs within a context must stop the run"),
    ("I4 join check removed", _SELF, "    if mismatched:\n", "    if False:\n", "FAIL  FIX-I4", "annotation and records that disagree must stop the run"),
    ("I5 reparse check removed", _SELF, "    if unreproduced:\n        return [", "    if False:\n        return [", "FAIL  FIX-I5", "an altered raw response must stop the run"),
    ("I6 declared total not checked", _SELF, '    if total != known["none_total"]:\n', "    if False:\n", "FAIL  FIX-I6", "a declared value that does not match must stop the run"),
    ("I6 declared cell maximum not checked", _SELF, '    if f"{cell_max / m:.6f}" != known["cell_none_rate_max"]:\n', "    if False:\n", "FAIL  FIX-I6-cell", "the second declared value is checked too"),
    ("I7 reachability ignored", _SELF, "        return rejects(self.p_min, alpha)\n", "        return True\n", "FAIL  FIX-I7", "an arm that cannot reach alpha reported as testable"),
    ("fixed sequence bypassed", _SELF, "    if not rejects(control_p, alpha):\n", "    if False:\n", "FAIL  ROW", "primary confirmatory without control"),
    ("IUT second condition dropped", _SELF, "    return confirmed and rejects(null_p, alpha)\n", "    return confirmed\n", "FAIL  MOD-null", "the explicit-null wording on the None test alone"),
    ("arms swapped in assembly", _SELF, '    control, primary = arms["control"]["exact"], arms["primary"]["exact"]\n', '    control, primary = arms["primary"]["exact"], arms["control"]["exact"]\n', "FAIL  E2E", "the control's p used for primary and the reverse"),
    ("explicit-null modifier fed the None test", _SELF, 'null_p=arms[arm]["exact"]["explicit_null"].p_upper, alpha=alpha\n', 'null_p=arms[arm]["exact"]["test"].p_upper, alpha=alpha\n', "FAIL  E2E", "the IUT's second test replaced by the first"),
    ("verify stops comparing the result", _SELF, "    if serialise(recomputed) != recorded_result:\n", "    if False:\n", "FAIL  FIX-verify", "a tampered result.json must fail --verify"),
    ("freeze binding stops checking later edits", _SELF, "    if last != full:\n", "    if False:\n", "FAIL  FIX-guards", "a frozen file changed after the freeze must be refused"),
    ("alpha loosened in freeze.json", "analysis/heldout-stay/freeze.json", '"alpha": "1/40"', '"alpha": "1/20"', "FAIL  NC-band", "the negative control's rejection rate leaves its band"),
    (
        "a frozen row text edited in SPEC only",
        "analysis/heldout-stay/SPEC.ja.md",
        "held-out では再現しなかった",
        "held-out では再現しなかったとは言えない",
        "FAIL  SPEC-drift",
        "SPEC.ja.md and freeze.json must say the same thing",
    ),
    (
        "comment edited (no-op control)",
        _SELF,
        "# The secondary analysis: six-category mean TV, stratified permutation\n",
        "# The secondary analysis (six categories), stratified permutation\n",
        None,
        "must not fail; if it does, the checker fails on anything",
    ),
)

_TREE: tuple[str, ...] = (
    _SELF,
    "analysis/heldout-stay/freeze.json",
    "analysis/heldout-stay/SPEC.ja.md",
    "data/raw/bank_annotation.jsonl",
    "seal/arm-spec.json",
)


def mutations(cproper_records: Path | None) -> int:
    caught, missed, wrong_reason, broken_controls, invalid = [], [], [], [], []
    for name, rel, old, new, expected, why in MUTATIONS:
        original = (REPO_ROOT / rel).read_text("utf-8")
        if original.count(old) != 1:
            invalid.append(f"{name}: the text to replace occurs {original.count(old)} times, not once")
            continue
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            root = Path(tmp)
            for path in _TREE:
                (root / path).parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(REPO_ROOT / path, root / path)
            shutil.copytree(
                REPO_ROOT / "analysis" / "apparatus",
                root / "analysis" / "apparatus",
                ignore=shutil.ignore_patterns("__pycache__"),
            )
            (root / rel).write_text(original.replace(old, new), encoding="utf-8", newline="\n")
            argv = [sys.executable, str(root / _SELF), "--self-test"]
            if cproper_records is not None:
                argv += ["--cproper-records", str(cproper_records)]
            # The child prints Japanese frozen text; without this a Windows console encoding
            # decides the bytes, and a decode error would read as a caught mutation.
            env = {**os.environ, "PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8"}
            done = subprocess.run(argv, capture_output=True, text=True, encoding="utf-8", env=env, check=False)
        output = done.stdout + done.stderr
        if expected is None:
            (broken_controls if done.returncode != 0 else caught).append(name)
            status = "control failed" if done.returncode != 0 else "control clean"
        elif done.returncode == 0:
            missed.append(name)
            status = "NOT caught"
        elif expected not in output:
            wrong_reason.append(f"{name}: exit {done.returncode}, expected '{expected}'; tail: {output.strip()[-300:]}")
            status = "caught for another reason"
        else:
            caught.append(name)
            status = f"caught ({expected})"
        print(f"[heldout] mutation {name!r}: {status} -- {why}")
    for line in invalid + wrong_reason:
        print(f"[heldout] FAIL  {line}")
    ok = not (missed or wrong_reason or broken_controls or invalid)
    print(
        f"[heldout] mutations: {len(MUTATIONS)} cases, {len(missed)} not caught, "
        f"{len(wrong_reason)} caught for another reason, {len(broken_controls)} controls failed, "
        f"{len(invalid)} invalid"
    )
    return 0 if ok else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--self-test", action="store_true")
    mode.add_argument("--mutations", action="store_true")
    mode.add_argument("--run", action="store_true")
    mode.add_argument("--verify", action="store_true")
    parser.add_argument("--cproper-records", type=Path, help="completed-run bank_records.jsonl (local only)")
    parser.add_argument("--freeze-commit", help="--run: the commit that froze the specification")
    parser.add_argument("--control-dir", type=Path, help="--run: directory holding the control arm's files")
    parser.add_argument("--primary-dir", type=Path, help="--run: directory holding the primary arm's files")
    args = parser.parse_args(argv)
    if args.self_test:
        return self_test(load_freeze(), args.cproper_records)
    if args.mutations:
        return mutations(args.cproper_records)
    if args.verify:
        return verify()
    if not (args.freeze_commit and args.control_dir and args.primary_dir):
        parser.error("--run needs --freeze-commit, --control-dir and --primary-dir")
    return run(args.freeze_commit, {"control": args.control_dir, "primary": args.primary_dir})


if __name__ == "__main__":
    raise SystemExit(main())
