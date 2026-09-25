"""Shared pieces of the post hoc simulation (B3): the declared grid, the bases, the directions.

Everything here is read from ``analysis/autopsy/grid.json`` and from shipped data. Probabilities are
kept as exact fractions until a draw is made, so that "the channel-on distribution is at total
variation delta from the channel-off one" is checked exactly rather than to a tolerance.
"""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
import sys
from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "analysis" / "apparatus"))
sys.path.insert(0, str(REPO_ROOT / "analysis" / "scripts"))

import numpy as np  # noqa: E402
from erre_sandbox.integration.embodied.bank_power import (  # noqa: E402
    _perturb_to_delta_tv,
)

GRID_PATH = REPO_ROOT / "analysis" / "autopsy" / "grid.json"
POSTHOC_DIR = REPO_ROOT / "data" / "posthoc"
DECLARATION_TAG = "autopsy-b3-declared"

#: The sealed files whose behaviour the simulation depends on. Their digests go into the manifest,
#: so that a result can be read next to the bytes that produced it.
SEALED_INPUTS: tuple[str, ...] = (
    "analysis/apparatus/erre_sandbox/integration/embodied/bank_scorer.py",
    "analysis/apparatus/erre_sandbox/integration/embodied/bank_power.py",
    "analysis/scripts/apply_decision_rules.py",
    "seal/decision-rules.json",
)

RUN_FILES: dict[str, str] = {
    "completed": "data/raw/bank_annotation.jsonl",
    "control": "data/prospective/control/run_annotation.jsonl",
}

CONDITIONS: tuple[str, str] = ("on", "off")


#: Files whose bytes at the declaration tag bind every output: the grid, the code that turns it
#: into numbers and applies the reading rules, the data the bases are built from, and the lockfile
#: that fixes the random-number implementation (Codex review HIGH-2 / MEDIUM-6).
DECLARED_FILES: tuple[str, ...] = (
    "analysis/autopsy/grid.json",
    "analysis/autopsy/_common.py",
    "analysis/autopsy/simulate.py",
    "analysis/autopsy/side_analyses.py",
    "analysis/autopsy/render.py",
    "data/raw/bank_annotation.jsonl",
    "data/prospective/control/run_annotation.jsonl",
    "data/derived/collapse-and-floor.json",
    "env/uv.lock",
    *SEALED_INPUTS,
)
DEVIATIONS_PATH = REPO_ROOT / "analysis" / "autopsy" / "DEVIATIONS.md"


def _git(*args: str) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(["git", *args], cwd=REPO_ROOT, capture_output=True, check=False)


WAIVER_LINE = re.compile(r"^- \*\*Waives\*\*: `([^`]+)`$")


def waived_paths(deviations: str) -> set[str]:
    """The paths a deviation ledger waives: only lines of the exact form ``- **Waives**: `path```.

    A path mentioned anywhere else in the ledger's prose waives nothing. (DV-2: an earlier version
    matched any backticked mention, so a file cited in an explanation was waived by accident.)
    """
    return {m.group(1) for line in deviations.splitlines() if (m := WAIVER_LINE.match(line))}


def binding_problems(
    declared: dict[str, bytes | None], current: dict[str, bytes | None], waived: set[str]
) -> tuple[list[str], list[str]]:
    """Compare declared and current bytes of every bound file. Returns (problems, waived notes).

    ``None`` means the file does not exist (at the tag, or in the working tree). A difference or an
    absence is a problem unless the path is waived; a waiver that covers nothing is a problem too,
    so the ledger cannot carry stale entries that would silently cover a later change.
    """
    problems: list[str] = []
    notes: list[str] = []
    for relative in DECLARED_FILES:
        if declared[relative] is not None and declared[relative] == current[relative]:
            continue
        if relative in waived:
            notes.append(relative)
            continue
        problems.append(f"{relative} differs from the declared bytes and no waiver names it")
    for relative in sorted(waived - set(DECLARED_FILES)):
        problems.append(f"DEVIATIONS.md waives {relative}, which is not a bound file")
    for relative in sorted(waived & set(DECLARED_FILES)):
        if declared[relative] is not None and declared[relative] == current[relative]:
            problems.append(f"DEVIATIONS.md waives {relative}, which does not differ")
    return problems, notes


def declaration_commit() -> str:
    """The commit the declaration tag points at, after checking the binding. Exits on failure.

    Every file in :data:`DECLARED_FILES` must be byte-identical to its copy at the tagged commit,
    unless a ``Waives`` line of ``DEVIATIONS.md`` names it, and the tagged commit must be an
    ancestor of ``HEAD``.
    """
    rev = _git("rev-parse", "--verify", f"refs/tags/{DECLARATION_TAG}^{{commit}}")
    if rev.returncode != 0:
        sys.exit(f"[autopsy] FAIL: tag {DECLARATION_TAG} does not exist")
    commit = rev.stdout.decode().strip()
    if _git("merge-base", "--is-ancestor", commit, "HEAD").returncode != 0:
        sys.exit(f"[autopsy] FAIL: the declaration commit {commit} is not an ancestor of HEAD")
    deviations = (
        DEVIATIONS_PATH.read_text(encoding="utf-8") if DEVIATIONS_PATH.is_file() else ""
    )
    declared: dict[str, bytes | None] = {}
    current: dict[str, bytes | None] = {}
    for relative in DECLARED_FILES:
        shown = _git("show", f"{commit}:{relative}")
        declared[relative] = shown.stdout if shown.returncode == 0 else None
        path = REPO_ROOT / relative
        current[relative] = path.read_bytes() if path.is_file() else None
    problems, notes = binding_problems(declared, current, waived_paths(deviations))
    for relative in notes:
        print(f"[autopsy] {relative} differs from the declaration; waived in DEVIATIONS.md")
    if problems:
        sys.exit("[autopsy] FAIL: " + "; ".join(problems) + f" (declaration {commit})")
    return commit


def load_grid() -> dict[str, Any]:
    return json.loads(GRID_PATH.read_text(encoding="utf-8"))


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


@dataclass(frozen=True)
class RunCounts:
    """Per-(context, condition) zone counts and None counts of one shipped run."""

    zone_counts: dict[tuple[str, str], tuple[int, ...]]
    none_counts: dict[tuple[str, str], int]


def load_run(relative: str, zones: tuple[str, ...]) -> RunCounts:
    zone_counts: dict[tuple[str, str], list[int]] = {}
    none_counts: dict[tuple[str, str], int] = {}
    with (REPO_ROOT / relative).open(encoding="utf-8") as handle:
        for line in handle:
            row = json.loads(line)
            key = (row["frozen_ctx_id"], row["condition"])
            counts = zone_counts.setdefault(key, [0] * len(zones))
            none_counts.setdefault(key, 0)
            zone = row["pre_bias_destination_zone"]
            if zone is None:
                none_counts[key] += 1
            else:
                counts[zones.index(zone)] += 1
    return RunCounts(
        zone_counts={k: tuple(v) for k, v in zone_counts.items()},
        none_counts=none_counts,
    )


@dataclass(frozen=True)
class Base:
    """A declared base: the true channel-off distribution of every context."""

    id: str
    index: int
    off: dict[str, tuple[Fraction, ...]]  # context -> distribution over zones
    none_counts: dict[tuple[str, str], int]
    pooled: tuple[Fraction, ...]  # weighted by the parsed channel-off counts

    def parsed(self, ctx: str, cond: str, m_draws: int) -> int:
        return m_draws - self.none_counts[(ctx, cond)]


def _fractions(values: list[str]) -> tuple[Fraction, ...]:
    return tuple(Fraction(v) for v in values)


def build_bases(grid: dict[str, Any]) -> list[Base]:
    zones = tuple(grid["zones"])
    ctxs = tuple(grid["context_ids"])
    m_draws = int(grid["m_draws"])
    runs = {name: load_run(path, zones) for name, path in RUN_FILES.items()}
    bases: list[Base] = []
    for spec in grid["bases"]:
        source = "control" if spec["id"] == "K" else "completed"
        run = runs[source]
        none_counts = {
            (ctx, cond): run.none_counts[(ctx, cond)] for ctx in ctxs for cond in CONDITIONS
        }
        off: dict[str, tuple[Fraction, ...]] = {}
        for ctx in ctxs:
            if "dist" in spec:
                dist = _fractions(spec["dist"])
            else:
                counts = run.zone_counts[(ctx, "off")]
                total = sum(counts)
                dist = tuple(Fraction(c, total) for c in counts)
                if "fill" in spec:
                    moved = list(dist)
                    src = zones.index(spec["fill"]["from"])
                    for zone, amount in spec["fill"]["to"].items():
                        moved[src] -= Fraction(amount)
                        moved[zones.index(zone)] += Fraction(amount)
                    dist = tuple(moved)
            if sum(dist) != 1 or min(dist) < 0:
                raise ValueError(f"base {spec['id']} {ctx}: not a distribution")
            off[ctx] = dist
        weights = {ctx: m_draws - none_counts[(ctx, "off")] for ctx in ctxs}
        total_weight = sum(weights.values())
        pooled = tuple(
            sum(Fraction(weights[ctx]) * off[ctx][i] for ctx in ctxs) / total_weight
            for i in range(len(zones))
        )
        bases.append(
            Base(
                id=spec["id"],
                index=int(spec["index"]),
                off=off,
                none_counts=none_counts,
                pooled=pooled,
            )
        )
    return bases


@dataclass(frozen=True)
class Roles:
    hi: int
    lo: int
    second: int
    smallest_nonzero: int
    empty: tuple[int, ...]


def roles_of(pooled: tuple[Fraction, ...]) -> Roles:
    """The roles of the grid, with hi and lo taken from the sealed perturbation itself."""
    base = np.asarray([float(p) for p in pooled], dtype=np.float64)
    alt, shift = _perturb_to_delta_tv(base, 0.001)
    if shift <= 0.0:
        raise ValueError("the sealed perturbation moved no mass")
    diff = alt - base
    hi = int(np.flatnonzero(diff < 0)[0])
    lo = int(np.flatnonzero(diff > 0)[0])
    others = [i for i in range(len(pooled)) if i != hi]
    second = min(others, key=lambda i: (-pooled[i], i))
    positive = [i for i in others if pooled[i] > 0]
    smallest_nonzero = min(positive, key=lambda i: (pooled[i], i))
    empty = tuple(i for i in others if pooled[i] == 0)
    if not empty:
        empty = tuple(sorted(sorted(others, key=lambda i: (pooled[i], i))[:2]))
    return Roles(hi=hi, lo=lo, second=second, smallest_nonzero=smallest_nonzero, empty=empty)


Move = tuple[int, int, Fraction]  # (from, to, amount)


def moves_for(direction: str, roles: Roles, ctx_position: int, delta: Fraction) -> list[Move]:
    if direction == "D1":
        return [(roles.hi, roles.lo, delta)]
    if direction == "D2":
        return [(roles.hi, roles.smallest_nonzero, delta)]
    if direction == "D3":
        return [(roles.hi, roles.second, delta)]
    if direction == "D4":
        return [(roles.second, roles.hi, delta)]
    if direction == "D5":
        share = delta / len(roles.empty)
        return [(roles.hi, target, share) for target in roles.empty]
    if direction == "D6":
        inner = "D3" if ctx_position < 4 else "D4"
        return moves_for(inner, roles, ctx_position, delta)
    raise ValueError(f"unknown direction {direction!r}")


def apply_moves(dist: tuple[Fraction, ...], moves: list[Move]) -> tuple[Fraction, ...] | None:
    """The channel-on distribution, or None when a source cell holds less than it must give."""
    out = list(dist)
    taken: dict[int, Fraction] = {}
    for src, dst, amount in moves:
        taken[src] = taken.get(src, Fraction(0)) + amount
        out[src] -= amount
        out[dst] += amount
    for src, amount in taken.items():
        if dist[src] < amount:
            return None
    return tuple(out)


def total_variation(a: tuple[Fraction, ...], b: tuple[Fraction, ...]) -> Fraction:
    return sum((abs(x - y) for x, y in zip(a, b, strict=True)), Fraction(0)) / 2


def cdf_of(dist: tuple[Fraction, ...]) -> np.ndarray:
    """Cumulative distribution, each entry the float of an exact partial sum (last = 1.0)."""
    running = Fraction(0)
    values = []
    for p in dist:
        running += p
        values.append(float(running))
    return np.asarray(values, dtype=np.float64)


def draw(cdf: np.ndarray, uniforms: np.ndarray) -> np.ndarray:
    """Inverse-CDF draws: the zone whose cumulative interval contains each uniform."""
    idx = np.searchsorted(cdf, uniforms, side="right")
    return np.minimum(idx, len(cdf) - 1)
