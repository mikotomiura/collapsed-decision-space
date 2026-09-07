"""Frozen §5 constants for the M13-ES3 locomotion → sampling conformance verdict.

This module is the **single source of truth** for every value the ES-3
pre-registration freeze fixed **before** any result was seen (forking-paths
guard, mirroring :mod:`erre_sandbox.evidence.es2_replay.constants`). A value can
only change by a deliberate edit here, which itself requires a **superseding
ADR**. No value is read off a result and then tuned.

The table is the frozen ``design-final.md`` §5 numeric pre-registration
(``.steering/20260629-m13-es3-adr/``, user-ratified = the pre-registration
commitment, Codex 2nd HIGH-5). Several values are **inherited** rather than newly
invented: ``B`` / ``MIN_WALK_SEEDS`` / ``CI_ALPHA`` track the ES-2 freeze, and
``TEMP_MAX`` is inherited from ``inference/sampling.py`` (the clamp ceiling). The
freeze is pinned verbatim in ``tests/test_evidence/test_es3_constants.py``.

Claim boundary (``design-final.md`` §0 / §8): a GO means the locomotion→sampling
channel is wired (causal · separated · ablation-identity), i.e. **eligible to
proceed to ES-4 / divergence measurement**, *not* a test of "walking → creative
divergence" itself (that needs LLM power, deferred). NO_GO is a *progressive*
finding (the channel cannot convert headroom into effective modulation), not a
refutation. INCONCLUSIVE (invalid apparatus / no within-cell λ spread / headroom
saturation) is kept distinct from NO_GO.
"""

from __future__ import annotations

from typing import Final

from erre_sandbox.schemas import SamplingBase

# --- ensemble (blind walks × steps × persona, §2.1) ---------------------------

B: Final[int] = 64
"""Blind walks = the bootstrap unit count (ES-2 ``N_SEED=64`` inherited). The
per-walk-seed aggregate ``D_loco^(b)`` is the minimal independent unit (HIGH-4),
so ``B`` is the bootstrap sample size."""

T: Final[int] = 200
"""Steps per walk. EMA burn-in (~1/α≈3) plus enough within-cell n across the
5 zones × 3 personas = 15 cells (≈ B·T/5 per persona)."""

ALPHA: Final[float] = 0.3
"""λ EMA smoothing (effective window ~3-4 steps). Balances within-cell variation
(λ moves inside a zone visit) against history-carrying (the N_hist sensitivity)."""

# --- locomotion gains (§1.2 / §5) ---------------------------------------------

LOCO_GAIN_T: Final[float] = 0.3
"""Temperature gain: λ=1 → +0.3 temp = the ``peripatetic`` constant in scale but
**state-dependent** (not zone-constant). Inside ``SamplingDelta.temperature``'s
``[-1,1]`` for λ∈[0,1]. Pinned equal to ``locomotion_sampling.DEFAULT_LOCO_GAIN_T``."""

LOCO_GAIN_P: Final[float] = 0.1
"""top_p gain (secondary, M3): λ=1 → +0.1 top_p. Pinned equal to
``locomotion_sampling.DEFAULT_LOCO_GAIN_P``."""

# --- headroom / clamp (§2.3) --------------------------------------------------

TEMP_MAX: Final[float] = 2.0
"""Temperature clamp ceiling, inherited from ``inference/sampling.py``
``_TEMPERATURE_MAX``. ``H_s = TEMP_MAX − E_abl,s`` is the per-cell headroom."""

HEADROOM_MIN: Final[float] = 0.3
"""= ``LOCO_GAIN_T``. The minimum headroom a cell needs to express λ's full-width
modulation without clamping; cells with ``H_s ≤ HEADROOM_MIN`` are
headroom-invalid (§4 INCONCLUSIVE contribution, M2)."""

# --- validity gates (§3 / §4.1) -----------------------------------------------

LOCO_SPREAD_MIN: Final[float] = 0.0025
"""Minimum within-cell var(λ) (std≈0.05). Below it λ is ~constant in the cell
(zone-determined) = unmeasurable → INCONCLUSIVE (falsifiability #1)."""

MIN_CELLS: Final[int] = 8
"""Minimum headroom∧spread∧n-valid cells (of the 15) for a strong verdict
(over half; integrates with ES-1 n_valid=8)."""

MIN_CELL_N: Final[int] = 30
"""Within-cell n floor for a stable within-cell std estimate (empirical rule)."""

HEADROOM_VALID_FRAC: Final[float] = 0.5
"""Headroom-valid cell fraction floor; below it base+mode is saturated →
INCONCLUSIVE (M2)."""

MIN_WALK_SEEDS: Final[int] = 32
"""Minimum valid walk-seeds for the bootstrap (ES-2 ``MIN_VALID_SEEDS=32``
inherited; Codex 2nd HIGH-5 "minimum walk-seed validity")."""

# --- verdict thresholds (§4.2 / §4.3) -----------------------------------------

AMP_FLOOR: Final[float] = 0.02
"""GO threshold: locomotion must traverse ≥2% of the cell headroom in within-cell
std (``D_loco = std_within(E_full)/H_s``). Below it the effective modulation is
negligible (clamp / saturation) → NO_GO. A structural minimum-effect bar, fixed
**before** the run (not read off an observed ``D_loco``)."""

CI_ALPHA: Final[float] = 0.10
"""90% one-sided bootstrap CI (ES-2 inherited). GO needs ``CI_lower ≥ AMP_FLOOR``."""

N_RESAMPLES: Final[int] = 10000
"""Bootstrap resample count (standard)."""

ZERO_TOL: Final[float] = 1e-9
"""Numerical zero tolerance for the zone-function control (``D_loco ≤ ZERO_TOL``)
and the ablation bit-equality (std epsilon guard, Codex 2nd LOW-1)."""

# --- persona roster (§5 P row, blind: real YAML default_sampling) -------------

PERSONA_ROSTER: Final[tuple[tuple[str, SamplingBase], ...]] = (
    ("kant", SamplingBase(temperature=0.60, top_p=0.85, repeat_penalty=1.12)),
    ("nietzsche", SamplingBase(temperature=0.85, top_p=0.80, repeat_penalty=0.95)),
    ("rikyu", SamplingBase(temperature=0.45, top_p=0.78, repeat_penalty=1.25)),
)
"""The frozen persona roster: ``persona_id`` pinned, the ``SamplingBase`` values
mirrored from the real ``personas/*.yaml`` ``default_sampling`` (not chosen for
this test = blind, Codex L1). The spread of base temperatures (0.45 / 0.60 / 0.85)
makes ``H_s`` vary per cell so the headroom gate is exercised. Pinned to the YAML
files in ``tests/test_evidence/test_es3_scenario.py``."""

__all__ = [
    "ALPHA",
    "AMP_FLOOR",
    "CI_ALPHA",
    "HEADROOM_MIN",
    "HEADROOM_VALID_FRAC",
    "LOCO_GAIN_P",
    "LOCO_GAIN_T",
    "LOCO_SPREAD_MIN",
    "MIN_CELLS",
    "MIN_CELL_N",
    "MIN_WALK_SEEDS",
    "N_RESAMPLES",
    "PERSONA_ROSTER",
    "TEMP_MAX",
    "ZERO_TOL",
    "B",
    "T",
]
