"""M13 C-proper — bank-annotation scorer (§CB4.4 verdict over opaque raw rows).

This is the **measurement** layer that C-design #2 (``AUTHORIZE_C_PROPER``,
``.steering/20260708-m13-c-design-bank/design-final.md`` §CB4) authorised and that
the B apparatus deliberately withheld: ``bank.py`` / ``bank_fixtures.py`` /
``ecl_bank_capture.py`` emit only the **opaque raw-row annotation**
(``{frozen_ctx_id, condition, mc_index, pre_bias_destination_zone,
resolved_from}``) and compute no ``H(zone|ctx)`` / divergence / verdict (the
spend guard forbids it there). This module — a **new file, outside the spend
guard's scan set** (``bank.py`` / ``bank_fixtures.py`` / ``ecl_bank_capture.py``
/ ``test_ecl_bank_golden.py``) — reads that annotation and computes the
pre-registered §CB4.4 verdict.

The scorer is **result-independent** and frozen before the powered sealed run
(``.steering/20260710-m13-c-proper/design-final.md`` §S8 seal). It implements the
FROZEN schema faithfully (tune-to-pass封鎖); every threshold is imported from
``bank_power`` rather than redefined. The observed shift test is the reimagine-v2
**stratified within-context permutation** design (user 裁定 2026-07-10,
``decisions.md`` 判断 1): pooling (§CB4.3 caveat) is confined to the a-priori
power gate and kept out of the primary significance test, so heterogeneous /
opposite-direction shifts do not cancel and the null is exact under per-context
base-rate differences.

Scope guard: reads annotation dicts + a manifest dict only. Imports no
``evidence`` / ``spdm`` / ``runningness`` machinery and never mutates the B
apparatus. Verdict floats are 6-decimal quantised on emit so a Windows bake and a
WSL replay serialise byte-identically (categorical zones are float-insensitive;
``feedback_golden_crossplatform_float_drift``).
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import TYPE_CHECKING, Any, Final

import numpy as np

from erre_sandbox.integration.embodied.bank_power import (
    ALPHA_SIGNIFICANCE,
    DELTA_TV_MIN,
    H_MIN_BITS,
    K_MIN,
    M_MIN,
    N_REPLICATES_DEFAULT,
    POWER_MIN,
    POWER_SEED_DEFAULT,
    RHO_MIN,
    categorical_multinomial_power,
)
from erre_sandbox.schemas import Zone

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

__all__ = [
    "NONE_RATE_MAX",
    "SCORER_SCHEMA_VERSION",
    "ZONES",
    "CProperVerdict",
    "score_bank_annotation",
    "verdict_to_dict",
]

SCORER_SCHEMA_VERSION: Final[str] = "ecl-cproper-scorer-1"

#: The five spatial zones in a fixed order (§CB4.1 5-way categorical). Sorting by
#: value keeps the index map deterministic and platform-independent.
ZONES: Final[tuple[Zone, ...]] = tuple(sorted(Zone, key=lambda z: z.value))

#: §S2.3 pre-register: a (context, condition) cell whose unparseable-destination
#: (``None``) rate exceeds this is a degenerate estimator → ``INCONCLUSIVE``.
NONE_RATE_MAX: Final[float] = 0.5

#: Quantisation applied to every emitted float (WSL byte-一致) and to TV values
#: before the permutation ``>=`` comparison (so a near-tie cannot flip the reject
#: bit across platforms' 1-ULP ``libm`` drift).
_FLOAT_DECIMALS: Final[int] = 6
_TV_COMPARE_DECIMALS: Final[int] = 9

_CONDITIONS: Final[tuple[str, str]] = ("on", "off")
_ZONE_INDEX: Final[dict[str, int]] = {z.value: i for i, z in enumerate(ZONES)}


# --------------------------------------------------------------------------- #
# Verdict record
# --------------------------------------------------------------------------- #


@dataclass(frozen=True, slots=True)
class CProperVerdict:
    """The §CB4.4 verdict plus every gate readout (§S6).

    ``verdict`` ∈ {``INCONCLUSIVE``, ``NO_CHANNEL_CONFORMANCE``,
    ``INCONCLUSIVE_UNDERPOWERED``, ``CHANNEL_CONFORMANCE_DETECTED``}. The
    ``tv_pool`` / ``tv_per_context`` / ``per_context_h`` fields are **secondary
    descriptors** (over-read guard §CB6: recorded, never part of the gate).
    """

    verdict: str
    reason: tuple[str, ...]
    n_contexts: int
    effective_k: int
    rho_hat: float
    none_rate_max_observed: float
    per_context_h: dict[str, float]
    i_pass_mask: dict[str, bool]
    tv_bar: float | None
    tv_per_context: dict[str, float]
    tv_pool: float | None
    permutation_reject: bool | None
    permutation_p_value: float | None
    power: float | None
    thresholds: dict[str, float]


# Verdict string constants (single source, never inline-typed).
_INCONCLUSIVE: Final[str] = "INCONCLUSIVE"
_NO_CONFORMANCE: Final[str] = "NO_CHANNEL_CONFORMANCE"
_UNDERPOWERED: Final[str] = "INCONCLUSIVE_UNDERPOWERED"
_DETECTED: Final[str] = "CHANNEL_CONFORMANCE_DETECTED"


# --------------------------------------------------------------------------- #
# Annotation → per-(context, condition) zone tallies
# --------------------------------------------------------------------------- #


@dataclass(frozen=True, slots=True)
class _CellTally:
    """One (context, condition) cell: valid 5-way zone counts + book-keeping."""

    zone_labels: tuple[int, ...]  # per valid draw, index into ZONES
    total_draws: int
    none_draws: int
    mc_indices: tuple[int, ...]  # every draw's mc_index (valid + None), for gating

    @property
    def valid_draws(self) -> int:
        return len(self.zone_labels)

    @property
    def none_rate(self) -> float:
        return self.none_draws / self.total_draws if self.total_draws else 0.0

    def counts(self) -> np.ndarray:
        vec = np.zeros(len(ZONES), dtype=np.int64)
        for idx in self.zone_labels:
            vec[idx] += 1
        return vec


def _tally(
    annotation_rows: Sequence[Mapping[str, Any]],
) -> dict[str, dict[str, _CellTally]]:
    """Group rows into ``{frozen_ctx_id: {condition: _CellTally}}`` (sorted keys).

    ``None`` (unparseable) destinations are counted but excluded from the zone
    label list (§S2.3). Rows arrive with ``pre_bias_destination_zone`` as a Zone
    value string or ``None``.
    """
    grouped: dict[str, dict[str, list[int]]] = {}
    mc_idx: dict[tuple[str, str], list[int]] = {}
    totals: dict[tuple[str, str], int] = {}
    nones: dict[tuple[str, str], int] = {}
    for row in annotation_rows:
        # Required keys — a KeyError here is caught by the schema gate (MEDIUM-1).
        ctx = str(row["frozen_ctx_id"])
        cond = str(row["condition"])
        mc = int(row["mc_index"])
        if cond not in _CONDITIONS:
            msg = f"unknown condition {cond!r} (expected 'on'/'off')"
            raise ValueError(msg)
        key = (ctx, cond)
        totals[key] = totals.get(key, 0) + 1
        mc_idx.setdefault(key, []).append(mc)
        zone_value = row["pre_bias_destination_zone"]
        cond_map = grouped.setdefault(ctx, {})
        labels = cond_map.setdefault(cond, [])
        if zone_value is None:
            nones[key] = nones.get(key, 0) + 1
            continue
        zone_str = zone_value.value if isinstance(zone_value, Zone) else str(zone_value)
        if zone_str not in _ZONE_INDEX:
            msg = f"unknown zone {zone_str!r} in annotation"
            raise ValueError(msg)
        labels.append(_ZONE_INDEX[zone_str])

    tallies: dict[str, dict[str, _CellTally]] = {}
    for ctx in sorted(grouped):
        tallies[ctx] = {}
        for cond in _CONDITIONS:
            labels = grouped[ctx].get(cond, [])
            key = (ctx, cond)
            tallies[ctx][cond] = _CellTally(
                zone_labels=tuple(labels),
                total_draws=totals.get(key, 0),
                none_draws=nones.get(key, 0),
                mc_indices=tuple(mc_idx.get(key, [])),
            )
    return tallies


# --------------------------------------------------------------------------- #
# Statistics (§S3 entropy / §S5 TV + permutation)
# --------------------------------------------------------------------------- #


def _empirical_dist(counts: np.ndarray) -> np.ndarray:
    total = counts.sum()
    if total == 0:
        return np.zeros(len(ZONES), dtype=np.float64)
    return counts.astype(np.float64) / float(total)


def _entropy_bits(dist: np.ndarray) -> float:
    """Shannon entropy in bits; ``0 log2 0 := 0``."""
    nonzero = dist[dist > 0.0]
    if nonzero.size == 0:
        return 0.0
    return float(-np.sum(nonzero * np.log2(nonzero)))


def _tv_distance(dist_a: np.ndarray, dist_b: np.ndarray) -> float:
    """Total-variation distance ``½ Σ_z |a(z) − b(z)|`` (§CB4.1 effect metric)."""
    return float(0.5 * np.sum(np.abs(dist_a - dist_b)))


def _tv_from_labels(labels_on: np.ndarray, labels_off: np.ndarray) -> float:
    on = np.bincount(labels_on, minlength=len(ZONES)).astype(np.float64)
    off = np.bincount(labels_off, minlength=len(ZONES)).astype(np.float64)
    return _tv_distance(_empirical_dist(on), _empirical_dist(off))


def _permutation_test(
    ipass_labels: list[tuple[np.ndarray, np.ndarray]],
    observed_tv_bar: float,
    *,
    n_replicates: int,
    seed: int,
) -> tuple[bool, float]:
    """Stratified within-context label-permutation test on ``TV̄`` (§S5.4).

    ``ipass_labels`` is one ``(on_labels, off_labels)`` array pair per (i)-PASS
    context (valid draws only). Under H0 the on/off labels are exchangeable
    **within each context**, so each replicate pools a context's valid draws,
    shuffles, and re-splits keeping ``(n_on, n_off)`` fixed — an exact
    per-stratum permutation null. Returns ``(reject, p_value)`` with the
    Phipson–Smyth exact-permutation ``p = (ge + 1) / (n_replicates + 1)`` and
    ``reject = p <= α``. TV values are rounded to 9 decimals before the ``>=`` so a
    1-ULP tie cannot flip the bit across platforms.
    """
    rng = np.random.default_rng(seed)
    pooled = [np.concatenate([on, off]) for on, off in ipass_labels]
    n_on = [on.shape[0] for on, _ in ipass_labels]
    obs = round(observed_tv_bar, _TV_COMPARE_DECIMALS)
    ge = 0
    for _ in range(n_replicates):
        tv_sum = 0.0
        for pool, k_on in zip(pooled, n_on, strict=True):
            perm = rng.permutation(pool)
            tv_sum += _tv_from_labels(perm[:k_on], perm[k_on:])
        tv_bar_star = round(tv_sum / len(pooled), _TV_COMPARE_DECIMALS)
        if tv_bar_star >= obs:
            ge += 1
    # Phipson–Smyth (2010) exact-permutation p: the +1 counts the observed
    # statistic as one null draw, so p is never 0 (an anti-conservative ge/n
    # would over-reject at the boundary — Codex HIGH-3).
    p_value = (ge + 1) / (n_replicates + 1)
    return (p_value <= ALPHA_SIGNIFICANCE, p_value)


# --------------------------------------------------------------------------- #
# Verdict assembly (§S6, ordered conjunctive gate — evaluate_phase0 型)
# --------------------------------------------------------------------------- #


def _thresholds(
    *, m_draws: int | None = None, k_contexts: int | None = None
) -> dict[str, float]:
    thresholds = {
        "delta_tv_min": DELTA_TV_MIN,
        "power_min": POWER_MIN,
        "h_min_bits": H_MIN_BITS,
        "rho_min": RHO_MIN,
        "alpha": ALPHA_SIGNIFICANCE,
        "none_rate_max": NONE_RATE_MAX,
        "m_min": float(M_MIN),
        "k_min": float(K_MIN),
        "seed": float(POWER_SEED_DEFAULT),
    }
    if m_draws is not None:
        thresholds["m_draws"] = float(m_draws)
    if k_contexts is not None:
        thresholds["k_contexts"] = float(k_contexts)
    return thresholds


def _inconclusive(
    reason: str,
    tallies: dict[str, dict[str, _CellTally]],
    *,
    m_draws: int | None = None,
    k_contexts: int | None = None,
) -> CProperVerdict:
    none_max = max(
        (cell.none_rate for cond in tallies.values() for cell in cond.values()),
        default=0.0,
    )
    return CProperVerdict(
        verdict=_INCONCLUSIVE,
        reason=(reason,),
        n_contexts=len(tallies),
        effective_k=0,
        rho_hat=0.0,
        none_rate_max_observed=none_max,
        per_context_h={},
        i_pass_mask={},
        tv_bar=None,
        tv_per_context={},
        tv_pool=None,
        permutation_reject=None,
        permutation_p_value=None,
        power=None,
        thresholds=_thresholds(m_draws=m_draws, k_contexts=k_contexts),
    )


def _validity_gate(
    tallies: dict[str, dict[str, _CellTally]],
    *,
    env_pins: Mapping[str, Any],
    m_expected: Any,
    k_expected: Any,
    context_ids: Any,
    require_powered_scale: bool,
) -> CProperVerdict | None:
    """§S2 validity gate — returns an ``INCONCLUSIVE`` verdict or ``None`` (pass).

    Enforces (Codex HIGH-2 / MEDIUM-2): think regime, powered scale (``m_draws``
    and ``k_contexts`` present **and** ≥ ``M_MIN`` / ``K_MIN``; a sub-powered
    bundle can never yield a spend verdict), exact per-cell ``mc_index`` set
    ``{0..M-1}`` (catches duplicate/missing indices even at the right count),
    manifest ``context_ids`` ↔ annotation contexts, and None-rate ≤ NONE_RATE_MAX.
    """
    if env_pins.get("think") is not False:
        return _inconclusive(
            f"think-regime-mismatch: env_pins.think={env_pins.get('think')!r} != False",
            tallies,
        )
    if not tallies:
        return _inconclusive("no annotation rows", tallies)
    if m_expected is None or k_expected is None:
        return _inconclusive(
            f"schema-invalid: manifest.run missing m_draws/k_contexts "
            f"(m={m_expected!r}, k={k_expected!r})",
            tallies,
        )
    m_draws = int(m_expected)
    k_contexts = int(k_expected)
    if require_powered_scale and (m_draws < M_MIN or k_contexts < K_MIN):
        return _inconclusive(
            f"below-powered-scale: m_draws={m_draws} (min {M_MIN}) / "
            f"k_contexts={k_contexts} (min {K_MIN})",
            tallies,
            m_draws=m_draws,
            k_contexts=k_contexts,
        )
    return _shape_and_cell_gate(
        tallies, m_draws=m_draws, k_contexts=k_contexts, context_ids=context_ids
    )


def _shape_and_cell_gate(
    tallies: dict[str, dict[str, _CellTally]],
    *,
    m_draws: int,
    k_contexts: int,
    context_ids: Any,
) -> CProperVerdict | None:
    """Context-set + per-(ctx, condition) completeness gate.

    Requires the exact context count, manifest ``context_ids`` ↔ annotation
    contexts, exact draw count, exact ``{0..M-1}`` ``mc_index`` set (catches
    duplicate/missing indices even at the right count), and None-rate ≤
    NONE_RATE_MAX.
    """
    if len(tallies) != k_contexts:
        return _inconclusive(
            f"incomplete-contexts: {len(tallies)} != k_contexts={k_contexts}",
            tallies,
            m_draws=m_draws,
            k_contexts=k_contexts,
        )
    if context_ids is not None and sorted(map(str, context_ids)) != sorted(tallies):
        return _inconclusive(
            "context-id-mismatch: manifest context_ids != annotation contexts",
            tallies,
            m_draws=m_draws,
            k_contexts=k_contexts,
        )
    expected_index_set = set(range(m_draws))
    for ctx, cond_map in tallies.items():
        for cond in _CONDITIONS:
            cell = cond_map[cond]
            reason: str | None = None
            if cell.total_draws != m_draws:
                reason = (
                    f"incomplete-draws: ctx={ctx} cond={cond} "
                    f"{cell.total_draws} != m_draws={m_draws}"
                )
            elif set(cell.mc_indices) != expected_index_set:
                reason = (
                    f"mc-index-set-invalid: ctx={ctx} cond={cond} "
                    f"expected {{0..{m_draws - 1}}} (duplicate or missing index)"
                )
            elif cell.none_rate > NONE_RATE_MAX:
                reason = (
                    f"excessive-none: ctx={ctx} cond={cond} "
                    f"none_rate={cell.none_rate:.4f} > {NONE_RATE_MAX}"
                )
            if reason is not None:
                return _inconclusive(
                    reason, tallies, m_draws=m_draws, k_contexts=k_contexts
                )
    return None


def _schema_invalid(reason: str) -> CProperVerdict:
    """Malformed annotation (missing keys / bad types) → ``INCONCLUSIVE`` (MEDIUM-1).

    A crash mid-scoring would violate §S2/§S6 (validity fail = non-spend
    ``INCONCLUSIVE``), so row-parsing errors surface as this verdict instead.
    """
    return CProperVerdict(
        verdict=_INCONCLUSIVE,
        reason=(f"schema-invalid: {reason}",),
        n_contexts=0,
        effective_k=0,
        rho_hat=0.0,
        none_rate_max_observed=0.0,
        per_context_h={},
        i_pass_mask={},
        tv_bar=None,
        tv_per_context={},
        tv_pool=None,
        permutation_reject=None,
        permutation_p_value=None,
        power=None,
        thresholds=_thresholds(),
    )


def score_bank_annotation(
    *,
    annotation_rows: Sequence[Mapping[str, Any]],
    manifest: Mapping[str, Any],
    n_replicates: int = N_REPLICATES_DEFAULT,
    seed: int = POWER_SEED_DEFAULT,
    require_powered_scale: bool = True,
) -> CProperVerdict:
    """Compute the §CB4.4 verdict from a bank annotation + its manifest (§S).

    Ordered conjunctive gate (returns the first non-PASS branch reached, mirroring
    ``es4_actuator.verdict_report.evaluate_phase0``): validity (§S2) → (i) H
    filter (§S3) → power (§S4) → observed shift (§S5).

    ``n_replicates`` / ``seed`` exist only to let the unit tests run the Monte-Carlo
    faster and assert determinism; the sealed path (``ecl_bank_cproper_capture.verify``)
    calls with the pinned ``N_REPLICATES_DEFAULT`` / ``POWER_SEED_DEFAULT`` (Codex
    MEDIUM-3). ``require_powered_scale`` (default True) is the sealed precondition
    that a spend verdict may only come from an ``M ≥ M_MIN ∧ K ≥ K_MIN`` bundle
    (Codex HIGH-2); tests exercising the statistical branches at small scale pass
    ``False`` — it relaxes a precondition, never a result (a sub-powered bundle can
    still only ever produce ``INCONCLUSIVE`` / the same branch, never a spurious
    ``DETECTED``).
    """
    run_cfg = manifest.get("run", {})
    env_pins = manifest.get("env_pins", {})
    m_expected = run_cfg.get("m_draws")
    k_expected = run_cfg.get("k_contexts")

    try:
        tallies = _tally(annotation_rows)
    except (ValueError, KeyError, TypeError) as exc:  # malformed rows (MEDIUM-1)
        return _schema_invalid(str(exc))

    # -- §S2 validity gate -------------------------------------------------- #
    invalid = _validity_gate(
        tallies,
        env_pins=env_pins,
        m_expected=m_expected,
        k_expected=k_expected,
        context_ids=run_cfg.get("context_ids"),
        require_powered_scale=require_powered_scale,
    )
    if invalid is not None:
        return invalid

    # validity passed → m/k are present and powered (echoed in every verdict below).
    m_draws = int(m_expected)
    k_contexts = int(k_expected)
    none_max = max(
        cell.none_rate for cond in tallies.values() for cell in cond.values()
    )

    # -- §S3 (i) evaluation criterion --------------------------------------- #
    per_context_h: dict[str, float] = {}
    i_pass_mask: dict[str, bool] = {}
    for ctx, cond_map in tallies.items():
        pooled_counts = cond_map["on"].counts() + cond_map["off"].counts()
        h_c = _entropy_bits(_empirical_dist(pooled_counts))
        per_context_h[ctx] = h_c
        i_pass_mask[ctx] = h_c >= H_MIN_BITS
    ipass_ctx = [c for c, ok in i_pass_mask.items() if ok]
    effective_k = len(ipass_ctx)
    rho_hat = effective_k / len(tallies)

    base = CProperVerdict(
        verdict=_NO_CONFORMANCE,
        reason=(),
        n_contexts=len(tallies),
        effective_k=effective_k,
        rho_hat=rho_hat,
        none_rate_max_observed=none_max,
        per_context_h=per_context_h,
        i_pass_mask=i_pass_mask,
        tv_bar=None,
        tv_per_context={},
        tv_pool=None,
        permutation_reject=None,
        permutation_p_value=None,
        power=None,
        thresholds=_thresholds(m_draws=m_draws, k_contexts=k_contexts),
    )

    if rho_hat < RHO_MIN:
        return _replace(
            base,
            verdict=_NO_CONFORMANCE,
            reason=(
                f"(i) collapse: rho_hat={rho_hat:.4f} < rho_min={RHO_MIN} "
                f"(effective_k={effective_k}/{len(tallies)})",
            ),
        )

    # -- §S4 power gate (pooling caveat confined here) ---------------------- #
    pooled_off = np.zeros(len(ZONES), dtype=np.float64)
    for ctx in ipass_ctx:
        pooled_off += tallies[ctx]["off"].counts().astype(np.float64)
    base_dist = _empirical_dist(pooled_off)
    if float(base_dist.sum()) <= 0.0:
        return _replace(
            base, verdict=_INCONCLUSIVE, reason=("degenerate off base_dist",)
        )
    power_result = categorical_multinomial_power(
        base_dist=[float(x) for x in base_dist],
        delta_tv=DELTA_TV_MIN,
        m_draws=m_draws,
        k_contexts=effective_k,
        pooling=True,
        n_replicates=n_replicates,
        seed=seed,
    )
    power = power_result.power
    if power < POWER_MIN:
        return _replace(
            base,
            verdict=_UNDERPOWERED,
            reason=(
                f"effective K'={effective_k} power={power:.4f} < {POWER_MIN} "
                "(pooling caveat §CB4.3)",
            ),
            power=power,
        )

    # -- §S5 observed shift test (stratified permutation, reimagine v2) ----- #
    tv_per_context: dict[str, float] = {}
    ipass_labels: list[tuple[np.ndarray, np.ndarray]] = []
    for ctx in ipass_ctx:
        on_labels = np.array(tallies[ctx]["on"].zone_labels, dtype=np.int64)
        off_labels = np.array(tallies[ctx]["off"].zone_labels, dtype=np.int64)
        tv_c = _tv_from_labels(on_labels, off_labels)
        tv_per_context[ctx] = tv_c
        ipass_labels.append((on_labels, off_labels))
    tv_bar = float(np.mean([tv_per_context[c] for c in ipass_ctx]))

    pooled_on = np.zeros(len(ZONES), dtype=np.float64)
    pooled_off_all = np.zeros(len(ZONES), dtype=np.float64)
    for ctx in ipass_ctx:
        pooled_on += tallies[ctx]["on"].counts().astype(np.float64)
        pooled_off_all += tallies[ctx]["off"].counts().astype(np.float64)
    tv_pool = _tv_distance(_empirical_dist(pooled_on), _empirical_dist(pooled_off_all))

    reject, p_value = _permutation_test(
        ipass_labels, tv_bar, n_replicates=n_replicates, seed=seed
    )

    tv_meets_floor = round(tv_bar, _TV_COMPARE_DECIMALS) >= DELTA_TV_MIN
    shift_detected = reject and tv_meets_floor
    verdict = _DETECTED if shift_detected else _NO_CONFORMANCE
    reason = (
        (
            f"shift detected: tv_bar={tv_bar:.4f} >= {DELTA_TV_MIN}, "
            f"permutation p={p_value:.4f} <= {ALPHA_SIGNIFICANCE}, power={power:.4f}"
        )
        if shift_detected
        else (
            f"no shift (effect-absent measurement, §CB4.4 relocated (b)): "
            f"tv_bar={tv_bar:.4f} floor_met={tv_meets_floor}, "
            f"reject={reject}, p={p_value:.4f}"
        )
    )
    return _replace(
        base,
        verdict=verdict,
        reason=(reason,),
        tv_bar=tv_bar,
        tv_per_context=tv_per_context,
        tv_pool=tv_pool,
        permutation_reject=reject,
        permutation_p_value=p_value,
        power=power,
    )


def _replace(base: CProperVerdict, **changes: Any) -> CProperVerdict:
    return replace(base, **changes)


# --------------------------------------------------------------------------- #
# Serialisation (6-decimal quantise for WSL byte-一致)
# --------------------------------------------------------------------------- #


def _q(value: float | None) -> float | None:
    return None if value is None else round(float(value), _FLOAT_DECIMALS)


def verdict_to_dict(verdict: CProperVerdict) -> dict[str, Any]:
    """Canonical dict for ``verdict.json`` — every float 6-decimal quantised."""
    return {
        "scorer_schema_version": SCORER_SCHEMA_VERSION,
        "verdict": verdict.verdict,
        "reason": list(verdict.reason),
        "n_contexts": verdict.n_contexts,
        "effective_k": verdict.effective_k,
        "rho_hat": _q(verdict.rho_hat),
        "none_rate_max_observed": _q(verdict.none_rate_max_observed),
        "per_context_h": {k: _q(v) for k, v in sorted(verdict.per_context_h.items())},
        "i_pass_mask": dict(sorted(verdict.i_pass_mask.items())),
        "tv_bar": _q(verdict.tv_bar),
        "tv_per_context": {k: _q(v) for k, v in sorted(verdict.tv_per_context.items())},
        "tv_pool": _q(verdict.tv_pool),
        "permutation_reject": verdict.permutation_reject,
        "permutation_p_value": _q(verdict.permutation_p_value),
        "power": _q(verdict.power),
        "thresholds": {k: _q(v) for k, v in sorted(verdict.thresholds.items())},
    }
