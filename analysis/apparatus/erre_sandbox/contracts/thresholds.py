"""Frozen acceptance thresholds for M2 integration (T19 / T20).

Every number consumed by the T19 execution-phase tests and the T20 acceptance
sign-off lives here as a single :class:`Thresholds` instance — this module is
the *what* (the acceptance values themselves), not the *why*.

Conservative defaults per decisions.md D6. Post-measurement adjustments go
into the same decisions.md entry, not by editing values silently.

This module was relocated from :mod:`erre_sandbox.integration.metrics`
2026-04-28 (codex review F5) so that ``ui`` can depend on a contract-only
path without transitively pulling in the heavy ``integration`` package
init (gateway / dialog). The legacy module is kept as a shim re-export
to preserve ``from erre_sandbox.integration import M2_THRESHOLDS`` for
existing tests.
"""

from __future__ import annotations

from typing import Final

from pydantic import BaseModel, ConfigDict, Field


class Thresholds(BaseModel):
    """Frozen acceptance thresholds for M2 integration tests.

    Fields are grouped into ``latency_*`` (network + scheduling),
    ``tick_*`` (scheduler health), ``memory_*`` (store layer), and
    ``state_*`` (AgentState field-range invariants).

    Instances are ``frozen`` so consumers cannot mutate in place — swap-out
    requires constructing a fresh :class:`Thresholds`, which is visible in
    ``git diff`` and thus reviewable.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    # ----- latency -------------------------------------------------------
    latency_p50_ms_max: float = Field(
        ...,
        gt=0.0,
        description="p50 of (envelope produced → client received) in ms.",
    )
    latency_p95_ms_max: float = Field(
        ...,
        gt=0.0,
        description="p95 of (envelope produced → client received) in ms.",
    )

    # ----- tick scheduler -------------------------------------------------
    tick_jitter_sigma_max: float = Field(
        ...,
        gt=0.0,
        le=1.0,
        description="Standard deviation of real-clock tick period divided "
        "by the nominal period (dimensionless ratio).",
    )

    # ----- memory store --------------------------------------------------
    memory_write_success_rate_min: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Fraction of memory writes that must succeed over the "
        "scenario window.",
    )

    # ----- AgentState invariants (mirror schemas.py _Unit constraints) ----
    arousal_min: float = Field(..., description="AgentState.arousal lower bound.")
    arousal_max: float = Field(..., description="AgentState.arousal upper bound.")
    valence_min: float = Field(..., description="AgentState.valence lower bound.")
    valence_max: float = Field(..., description="AgentState.valence upper bound.")
    attention_min: float = Field(..., description="AgentState.attention lower bound.")
    attention_max: float = Field(..., description="AgentState.attention upper bound.")


M2_THRESHOLDS: Final[Thresholds] = Thresholds(
    latency_p50_ms_max=100.0,
    latency_p95_ms_max=250.0,
    tick_jitter_sigma_max=0.20,
    memory_write_success_rate_min=0.98,
    arousal_min=0.0,
    arousal_max=1.0,
    valence_min=-1.0,
    valence_max=1.0,
    attention_min=0.0,
    attention_max=1.0,
)
"""The single M2 Thresholds instance.

Changing any number here MUST:

1. Be accompanied by a new decisions.md D6 entry explaining why.
2. Pass the contract snapshot test
   (:mod:`tests.test_integration.test_contract_snapshot`)
   — intentionally strict so adjustments are visible in CI.
"""

__all__ = ["M2_THRESHOLDS", "Thresholds"]
