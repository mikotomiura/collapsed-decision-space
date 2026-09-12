"""Default concrete :class:`ERREModeTransitionPolicy` for M5.

The FSM folds an :class:`~erre_sandbox.schemas.Observation` sequence (assumed
chronological) into a single successor mode using **latest-signal-wins**
semantics — the caller emits observations in world-tick order, the FSM
respects that ordering without a hard-coded priority table. Each
observation kind has its own pure handler; :class:`DefaultERREModePolicy`
is a thin ``@dataclass(frozen=True)`` wrapper that drives the accumulation
loop and performs the final ``None``-vs-new-mode idempotency wrap.

Inputs are purely read-only (:class:`Observation` payloads + the canonical
``ZONE_TO_DEFAULT_ERRE_MODE`` map, overridable via the dataclass field).
No persistent state, no I/O, no logging — downstream orchestrator tasks
own those concerns (``m5-orchestrator-integration``).

Design rationale: the FSM uses an event-driven design; a v1 priority-ordered
alternative was considered and rejected.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Final

from erre_sandbox.schemas import (
    ERREModeName,
    ERREModeShiftEvent,
    InternalEvent,
    ShuhariStage,
    Zone,
    ZoneTransitionEvent,
)

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

    from erre_sandbox.schemas import Observation

# =============================================================================
# Canonical maps
# =============================================================================

ZONE_TO_DEFAULT_ERRE_MODE: Final[Mapping[Zone, ERREModeName]] = {
    Zone.STUDY: ERREModeName.DEEP_WORK,
    Zone.PERIPATOS: ERREModeName.PERIPATETIC,
    Zone.CHASHITSU: ERREModeName.CHASHITSU,
    Zone.AGORA: ERREModeName.SHALLOW,
    Zone.GARDEN: ERREModeName.PERIPATETIC,
}
"""Canonical zone → default ERRE mode map.

1:1 with the persona-erre skill's §ルール 5 table, copied from the retired
``bootstrap.py::_ZONE_TO_DEFAULT_ERRE_MODE`` so boot-time behaviour is
byte-identical before and after this milestone.

``garden`` resolves to ``peripatetic`` rather than ``ri_create`` — the two
share the "walk and muse" semantics in the current world model, and the
bootstrap-era fallback has been in production since M4 without issue.
"""

SHUHARI_TO_MODE: Final[Mapping[ShuhariStage, ERREModeName]] = {
    ShuhariStage.SHU: ERREModeName.SHU_KATA,
    ShuhariStage.HA: ERREModeName.HA_DEVIATE,
    ShuhariStage.RI: ERREModeName.RI_CREATE,
}
"""Shuhari-stage → ERRE mode promotion map.

Used when an :class:`InternalEvent` announces a shuhari stage transition
(content ``"shuhari_promote:<stage>"``). The synthesis of these events
lives in a downstream sub-task (likely ``m5-world-zone-triggers``); the FSM
only reads the event.
"""

_SHUHARI_PROMOTE_PREFIX: Final = "shuhari_promote:"
_FATIGUE_PREFIX: Final = "fatigue:"
_REASON_EXTERNAL: Final = "external"
"""Literal value of :attr:`ERREModeShiftEvent.reason` that signals the caller
has already updated ``AgentState.erre`` out-of-band. Extracted as a constant
so downstream emitters (``m5-world-zone-triggers``) can import the exact
string and avoid magic-literal drift.
"""


# =============================================================================
# Per-observation handlers (pure functions, unit-tested in isolation)
# =============================================================================


def _on_zone_transition(
    ev: ZoneTransitionEvent,
    *,
    zone_defaults: Mapping[Zone, ERREModeName],
) -> ERREModeName | None:
    """Return the default ERRE mode for the zone the agent entered."""
    return zone_defaults.get(ev.to_zone)


def _on_internal(ev: InternalEvent) -> ERREModeName | None:
    """Parse an :class:`InternalEvent`'s ``content`` for FSM-relevant prefixes.

    Two recognised prefixes:

    * ``"shuhari_promote:<stage>"`` — promote the agent to the ERRE mode
      corresponding to the given shuhari stage. Unknown stage strings are
      silently ignored (returns ``None``) so callers are free to synthesise
      richer ``content`` shapes without breaking the FSM.
    * ``"fatigue:<anything>"`` — request a rest transition to CHASHITSU.

    Any other ``content`` shape returns ``None`` (= no FSM decision from
    this observation).
    """
    if ev.content.startswith(_SHUHARI_PROMOTE_PREFIX):
        stage_str = ev.content.removeprefix(_SHUHARI_PROMOTE_PREFIX)
        try:
            stage = ShuhariStage(stage_str)
        except ValueError:
            return None
        return SHUHARI_TO_MODE[stage]
    if ev.content.startswith(_FATIGUE_PREFIX):
        return ERREModeName.CHASHITSU
    return None


def _on_mode_shift(ev: ERREModeShiftEvent) -> ERREModeName | None:
    """Translate an :class:`ERREModeShiftEvent` into an FSM decision.

    ``reason="external"`` is treated as a no-op: the caller already updated
    ``AgentState.erre`` out-of-band, so re-proposing a transition would
    overwrite their decision. For the other four ``reason`` values
    (``scheduled`` / ``zone`` / ``fatigue`` / ``reflection``) the event
    author has authority, so ``ev.current`` is accepted as the new mode.
    """
    if ev.reason == _REASON_EXTERNAL:
        return None
    return ev.current


# =============================================================================
# Concrete policy
# =============================================================================


@dataclass(frozen=True)
class DefaultERREModePolicy:
    """Event-driven ERRE mode FSM.

    Accumulates an ``ERREModeName`` over the observation stream in the
    order observations appear (**latest signal wins**) and returns
    ``None`` when the final value equals the caller's ``current`` mode.

    Callers must supply ``observations`` in chronological order (oldest
    first). The world tick loop already does this; tests should follow the
    same convention.

    The ``match/case`` dispatch in :meth:`next_mode` relies on
    ``isinstance`` checks under the hood. The :class:`Observation` union
    (schemas.py §5) must remain **flat** — no inheritance among its
    members — or a subclass instance could be captured by an earlier
    branch. If a future Observation variant needs shared behaviour,
    extract a mixin (not a superclass) or thread the shared field
    through a new union member.
    """

    zone_defaults: Mapping[Zone, ERREModeName] = field(
        default_factory=lambda: dict(ZONE_TO_DEFAULT_ERRE_MODE),
    )

    def next_mode(
        self,
        *,
        current: ERREModeName,
        zone: Zone,
        observations: Sequence[Observation],
        tick: int,
    ) -> ERREModeName | None:
        """Decide the agent's next ERRE mode (or ``None`` to keep ``current``).

        ``zone`` and ``tick`` are part of the Protocol signature and are
        currently unused — kept for future rules (e.g. dwell-time thresholds,
        tick-modulo schedules). Implementations that ignore them should not
        rename the parameters so downstream sub-tasks can swap policies
        without call-site changes.
        """
        del zone, tick  # reserved for future rules; see docstring
        accumulated: ERREModeName = current
        for ev in observations:
            match ev:
                case ZoneTransitionEvent():
                    candidate = _on_zone_transition(
                        ev,
                        zone_defaults=self.zone_defaults,
                    )
                case InternalEvent():
                    candidate = _on_internal(ev)
                case ERREModeShiftEvent():
                    candidate = _on_mode_shift(ev)
                case _:
                    candidate = None
            if candidate is not None:
                accumulated = candidate
        return None if accumulated == current else accumulated


__all__ = [
    "SHUHARI_TO_MODE",
    "ZONE_TO_DEFAULT_ERRE_MODE",
    "DefaultERREModePolicy",
]
