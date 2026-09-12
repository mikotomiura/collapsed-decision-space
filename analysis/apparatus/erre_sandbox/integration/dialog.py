"""In-memory implementation of the M4 :class:`DialogScheduler` Protocol.

Responsibility: admission-control and lifecycle tracking for agent-to-agent
dialogs. The scheduler *also* owns the envelope emission path — when it
admits an initiate or closes a dialog, it calls the injected ``sink``
callable with the corresponding :class:`ControlEnvelope`, so callers do not
need to route the return value back into the gateway's queue themselves.

Design rationale:

* The Protocol is frozen at M4 foundation and says ``schedule_initiate``
  returns ``DialogInitiateMsg | None``; we keep that return contract but
  the authoritative delivery path is the sink. Callers that build on the
  Protocol API only get a signal of "was this admitted"; they MUST NOT
  put the returned envelope onto a queue themselves — doing so would
  duplicate the envelope delivered via the sink.
* ``tick()`` is an extension method (not part of the Protocol) that drives
  proximity-based auto-firing: two agents sharing a reflective zone after
  the pair's cooldown has elapsed get a probabilistic initiate.
* All randomness flows through an injected :class:`~random.Random` so the
  auto-fire path is deterministic under test.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from random import Random
from typing import TYPE_CHECKING, ClassVar, Final

from erre_sandbox.schemas import (
    AgentView,
    DialogCloseMsg,
    DialogInitiateMsg,
    DialogTurnMsg,
    Zone,
)

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable, Iterator, Sequence
    from typing import Literal

    from erre_sandbox.schemas import ControlEnvelope

logger = logging.getLogger(__name__)


@dataclass
class _OpenDialog:
    """In-flight dialog state carried by the scheduler's ``_open`` map."""

    dialog_id: str
    initiator: str
    target: str
    zone: Zone
    opened_tick: int
    last_activity_tick: int
    turns: list[DialogTurnMsg] = field(default_factory=list)


_REFLECTIVE_ZONES: Final[frozenset[Zone]] = frozenset(
    {Zone.PERIPATOS, Zone.CHASHITSU, Zone.AGORA, Zone.GARDEN},
)
"""Zones where proximity-based dialog admission is allowed.

``Zone.STUDY`` is intentionally excluded — the M2 persona-erre model treats
the study as a private deep-work space where interrupting speech is
culturally inappropriate.
"""


def _pair_key(a: str, b: str) -> frozenset[str]:
    """Order-agnostic dialog pair identity used as a dict key."""
    return frozenset({a, b})


class InMemoryDialogScheduler:
    """Default :class:`DialogScheduler` implementation for MVP multi-agent runs.

    State lives entirely in memory; there is no persistence because M4
    scoped dialog history to the transient layer (semantic summaries come
    from the Reflector on a different path). If a future milestone wants
    cross-run dialog transcripts, subclass and override ``record_turn`` /
    ``close_dialog`` to also write to sqlite.
    """

    COOLDOWN_TICKS: ClassVar[int] = 30
    """Ticks that must elapse after a close before the same pair may reopen
    in live multi-agent runs. Calibrated for the live-natural cadence where
    cognition_period_s is in the 7-18 s range and ``ManualClock`` advances
    ticks at roughly real-time speed.
    """

    COOLDOWN_TICKS_EVAL: ClassVar[int] = 5
    """Reduced cooldown applied when ``eval_natural_mode=True`` (eval cadence
    calibration, distinct from live natural cadence).

    m9-eval-system P3a-decide v2 (ME-8 amendment 2026-05-01): empirical
    G-GEAR re-capture measured ``cognition_period`` ≈ 120 s/tick on
    qwen3:8b Q4_K_M / RTX 5060 Ti / Ollama 0.22.0 — the live-mode 30-tick
    cooldown translates to ~60 min wall, making same-pair re-admission
    physically impossible inside a 10 min sanity wall. dialog_turn_budget=6
    enforces a 6-tick occupancy on each open dialog, so close-to-close gap
    in eval mode is ``5 + 6 = 11 ticks`` ≈ 22 min wall — that is the eval
    cadence calibration, not live natural cadence. Re-evaluate when the
    inference backend changes such that cognition_period falls below ~60 s
    or rises above ~240 s per tick (ME-8 amendment 2026-05-01 §re-open).
    """

    TIMEOUT_TICKS: ClassVar[int] = 6
    """Inactivity window after which an open dialog is auto-closed."""

    AUTO_FIRE_PROB_PER_TICK: ClassVar[float] = 0.25
    """Probability that a qualifying co-located pair is admitted on a tick.

    Keeps dialog from firing every single cognition tick when two agents
    happen to share a zone; the RNG is injected so tests can force the
    probability to 1.0 or 0.0 deterministically.
    """

    def __init__(
        self,
        *,
        envelope_sink: Callable[[ControlEnvelope], None],
        rng: Random | None = None,
        rng_for_pair: Callable[[str, str], Random] | None = None,
        turn_sink: Callable[[DialogTurnMsg], None] | None = None,
        golden_baseline_mode: bool = False,
        eval_natural_mode: bool = False,
    ) -> None:
        self._sink = envelope_sink
        self._rng = rng if rng is not None else Random()  # noqa: S311 — non-crypto
        # M2 §M4.2 (I4): when a record-mode driver injects a per-pair named
        # RNG substream factory, ``tick()``'s auto-fire draw below is keyed
        # by the co-located pair rather than drawn from one shared sequence
        # — the draw *site* and *comparison* are unchanged, only which
        # ``Random`` instance the draw comes from. ``None`` (the default,
        # every existing live/eval caller) keeps the pre-existing single
        # shared-``_rng`` behaviour byte-for-byte.
        self._rng_for_pair = rng_for_pair
        # M8 L6-D1: optional per-turn sink. When bootstrap wires it to a
        # ``MemoryStore.add_dialog_turn_sync`` closure (with agent_id →
        # persona_id resolution baked in), every recorded turn lands in
        # sqlite for later LoRA-training export. Left None for unit tests
        # and the existing lightweight fixtures that have no store.
        self._turn_sink = turn_sink
        # m9-eval-system P2b (design-final.md §Orchestrator): when True the
        # external golden baseline driver bypasses cooldown / timeout / zone
        # restriction so that 70-stimulus battery × 3 cycles can drive the
        # same agent pair without the natural-dialog admission rules. Public
        # attribute so the driver can flip it between stimulus phase
        # (200 turn, mode=True) and natural-dialog phase (300 turn,
        # mode=False) within the same scheduler instance / MemoryStore.
        self.golden_baseline_mode: bool = golden_baseline_mode
        # m9-eval-system P3a-decide (design-natural-gating-fix.md): when True
        # the eval natural-condition pilot bypasses zone-equality and
        # reflective-zone gates inside ``tick()`` and ``schedule_initiate()``
        # so 3 personas can sustain dialog after LLM-driven destination_zone
        # scatters them across study/peripatos/chashitsu. Cooldown / probability
        # / timeout / self-dialog reject / double-open reject all remain active
        # so admission cadence is still natural — only the spatial constraint
        # is dropped. Orthogonal to ``golden_baseline_mode``: stimulus phase
        # uses ``golden_baseline_mode=True`` (driver controls everything),
        # natural phase uses ``eval_natural_mode=True`` (proximity-free
        # logical co-location). Default False keeps M4-frozen Protocol
        # behaviour for live multi-agent runs.
        self.eval_natural_mode: bool = eval_natural_mode
        if eval_natural_mode and golden_baseline_mode:
            # the invariant claims for
            # ``eval_natural_mode`` (cooldown / timeout active) only hold
            # when ``golden_baseline_mode`` is False — combining the two is
            # a programming error because golden_baseline overrides cooldown
            # and timeout independently. Reject construction up-front rather
            # than letting the two flags interleave silently.
            msg = (
                "InMemoryDialogScheduler does not support enabling both "
                "golden_baseline_mode and eval_natural_mode on the same "
                "instance — they cover disjoint capture phases (stimulus "
                "vs natural). Construct two schedulers if both phases are "
                "needed in the same run."
            )
            raise ValueError(msg)
        self._open: dict[str, _OpenDialog] = {}
        self._pair_to_id: dict[frozenset[str], str] = {}
        # Bounded by C(N, 2) for N agents — M4 targets N≤3 so this cannot
        # grow beyond a few entries. If a future milestone scales to N>100
        # agents, cap this to an LRU dict or prune by stale age from
        # ``tick()``; for now the memory footprint is irrelevant.
        self._last_close_tick: dict[frozenset[str], int] = {}

    # ------------------------------------------------------------------
    # Protocol methods (frozen in schemas.py §7.5)
    # ------------------------------------------------------------------

    def schedule_initiate(
        self,
        initiator_id: str,
        target_id: str,
        zone: Zone,
        tick: int,
    ) -> DialogInitiateMsg | None:
        """Admit or reject a new dialog.

        Returns the :class:`DialogInitiateMsg` on admission for callers that
        rely on the Protocol signature, BUT the envelope is already on the
        way to consumers via the injected sink at the moment this method
        returns. Callers must not forward the return value onto the same
        envelope queue — see module docstring.
        """
        if initiator_id == target_id:
            return None
        if (
            zone not in _REFLECTIVE_ZONES
            and not self.golden_baseline_mode
            and not self.eval_natural_mode
        ):
            # m9-eval-system P2b: golden baseline stimulus battery includes
            # ``Zone.STUDY`` (Kant Wachsmuth/RoleEval, Nietzsche aphoristic
            # bursts) — bypass the natural-dialog cultural restriction.
            # m9-eval-system P3a-decide: eval natural condition lets agents
            # wander out of reflective zones (LLM-driven destination_zone)
            # and we still want them to dialog — bypass zone gate too.
            return None
        key = _pair_key(initiator_id, target_id)
        if key in self._pair_to_id:
            return None
        last_close = self._last_close_tick.get(key)
        if (
            last_close is not None
            and tick - last_close < self._effective_cooldown()
            and not self.golden_baseline_mode
        ):
            # m9-eval-system P2b: 70 stimulus × 3 cycles drives the same pair
            # repeatedly; cooldown would otherwise serialize them across
            # ≥ 30-tick gaps and inflate baseline tick range artificially.
            # m9-eval-system P3a-decide v2: ``_effective_cooldown()`` returns
            # ``COOLDOWN_TICKS_EVAL`` (5) when ``eval_natural_mode=True`` so
            # same-pair re-admission stays physically reachable inside the
            # 60-120 min wall budget under the empirical 120 s/tick rate.
            return None

        dialog_id = self._allocate_dialog_id(initiator_id, target_id)
        self._open[dialog_id] = _OpenDialog(
            dialog_id=dialog_id,
            initiator=initiator_id,
            target=target_id,
            zone=zone,
            opened_tick=tick,
            last_activity_tick=tick,
        )
        self._pair_to_id[key] = dialog_id
        envelope = DialogInitiateMsg(
            tick=tick,
            initiator_agent_id=initiator_id,
            target_agent_id=target_id,
            zone=zone,
        )
        self._emit(envelope)
        return envelope

    def record_turn(self, turn: DialogTurnMsg) -> None:
        """Attach ``turn`` to its dialog's transcript.

        Raises ``KeyError`` when the dialog is not open — this surfaces bugs
        (agents speaking into a closed dialog) rather than silently dropping.

        When a ``turn_sink`` was injected at construction (M8 L6-D1), the
        turn is forwarded to it after the in-memory bookkeeping so the sink
        observes turns in the same order as the transcript. Sink exceptions
        are caught and logged — a transient persistence failure must not
        tear down the live dialog loop.
        """
        dialog = self._open.get(turn.dialog_id)
        if dialog is None:
            raise KeyError(
                f"record_turn called for unknown dialog_id={turn.dialog_id!r}",
            )
        dialog.turns.append(turn)
        dialog.last_activity_tick = turn.tick
        if self._turn_sink is not None:
            try:
                self._turn_sink(turn)
            except Exception:
                logger.exception(
                    "turn_sink raised for dialog_id=%s turn_index=%d; "
                    "dropping row but keeping dialog alive",
                    turn.dialog_id,
                    turn.turn_index,
                )

    def close_dialog(
        self,
        dialog_id: str,
        reason: Literal["completed", "interrupted", "timeout", "exhausted"],
        *,
        tick: int | None = None,
    ) -> DialogCloseMsg:
        """Close ``dialog_id`` and emit the envelope via the sink.

        When ``tick`` is provided the close is recorded at that world tick
        (``DialogCloseMsg.tick`` and the cooldown anchor both honour it).
        When omitted, falls back to ``dialog.last_activity_tick`` so callers
        that only see the M4-frozen Protocol surface continue to behave as
        before. The keyword-only ``tick`` is the supported path for any
        caller that knows the current world tick (timeout sweep, exhausted
        budget, manual interrupt) — see codex review F1 (2026-04-28) for
        the stale-tick regression that motivated the parameter.

        Raises ``KeyError`` when the id is not currently open.
        """
        return self._close_dialog_at(dialog_id, reason, tick)

    def _close_dialog_at(
        self,
        dialog_id: str,
        reason: Literal["completed", "interrupted", "timeout", "exhausted"],
        tick: int | None,
    ) -> DialogCloseMsg:
        """Apply the close operation, honouring an optional override tick."""
        dialog = self._open.pop(dialog_id, None)
        if dialog is None:
            raise KeyError(f"close_dialog called for unknown dialog_id={dialog_id!r}")
        close_tick = tick if tick is not None else dialog.last_activity_tick
        key = _pair_key(dialog.initiator, dialog.target)
        self._pair_to_id.pop(key, None)
        self._last_close_tick[key] = close_tick
        envelope = DialogCloseMsg(
            tick=close_tick,
            dialog_id=dialog_id,
            reason=reason,
        )
        self._emit(envelope)
        return envelope

    # ------------------------------------------------------------------
    # Protocol-external extensions
    # ------------------------------------------------------------------

    def tick(self, world_tick: int, agents: Sequence[AgentView]) -> None:
        """Drive proximity-based admission + timeout close in one step.

        Called by ``WorldRuntime._on_cognition_tick`` after per-agent
        cognition has run. Order:

        1. close any dialogs whose last_activity_tick is older than TIMEOUT
        2. for each co-located pair in reflective zones, probabilistically
           admit (if not already open and past cooldown)

        m9-eval-system P3a-decide: when ``eval_natural_mode`` is True the
        spatial gates are dropped. ``_iter_all_distinct_pairs`` enumerates
        every distinct agent pair regardless of zone, and the reflective-zone
        skip below is bypassed. Cooldown / probability / timeout invariants
        remain active so admission cadence is still natural — only proximity
        is removed.
        """
        self._close_timed_out(world_tick)
        if self.eval_natural_mode:
            pair_iter = _iter_all_distinct_pairs(agents)
        else:
            pair_iter = _iter_colocated_pairs(agents)
        for a, b in pair_iter:
            if not self.eval_natural_mode and a.zone not in _REFLECTIVE_ZONES:
                continue
            key = _pair_key(a.agent_id, b.agent_id)
            if key in self._pair_to_id:
                continue
            last_close = self._last_close_tick.get(key)
            if (
                last_close is not None
                and world_tick - last_close < self._effective_cooldown()
            ):
                continue
            draw_rng = (
                self._rng_for_pair(a.agent_id, b.agent_id)
                if self._rng_for_pair is not None
                else self._rng
            )
            if draw_rng.random() > self.AUTO_FIRE_PROB_PER_TICK:
                continue
            self.schedule_initiate(a.agent_id, b.agent_id, a.zone, world_tick)

    def get_dialog_id(self, agent_a: str, agent_b: str) -> str | None:
        """Return the open dialog id for the (a, b) pair if any, else None."""
        return self._pair_to_id.get(_pair_key(agent_a, agent_b))

    @property
    def open_count(self) -> int:
        return len(self._open)

    def transcript_of(self, dialog_id: str) -> list[DialogTurnMsg]:
        dialog = self._open.get(dialog_id)
        return list(dialog.turns) if dialog is not None else []

    def iter_open_dialogs(self) -> Iterator[tuple[str, str, str, Zone]]:
        """Yield ``(dialog_id, initiator_id, target_id, zone)`` for each open dialog.

        Added for ``m5-orchestrator-integration``: the per-tick turn driver in
        :class:`~erre_sandbox.world.tick.WorldRuntime` needs to enumerate every
        open dialog to decide budget / speaker / turn generation. Read-only
        — callers must not mutate the scheduler's state via the yielded ids
        except through the existing ``record_turn`` / ``close_dialog`` surface.
        """
        for did, dialog in self._open.items():
            yield did, dialog.initiator, dialog.target, dialog.zone

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _effective_cooldown(self) -> int:
        """Return the cooldown threshold appropriate for the active mode.

        m9-eval-system P3a-decide v2 (ME-8 amendment 2026-05-01): live mode
        keeps ``COOLDOWN_TICKS=30`` calibrated for cognition_period in the
        7-18 s range, while ``eval_natural_mode=True`` switches to
        ``COOLDOWN_TICKS_EVAL=5`` calibrated for the empirical
        cognition_period ≈ 120 s/tick observed on qwen3:8b Q4_K_M.
        ``golden_baseline_mode`` bypasses cooldown entirely upstream — this
        helper is only consulted on the live / eval natural code paths.
        """
        return (
            self.COOLDOWN_TICKS_EVAL if self.eval_natural_mode else self.COOLDOWN_TICKS
        )

    def _close_timed_out(self, world_tick: int) -> None:
        if self.golden_baseline_mode:
            # m9-eval-system P2b: stimulus phase uses long expected_turn_count
            # (1-3) per stimulus; the driver explicitly closes each dialog so
            # the natural inactivity timeout is suppressed to avoid races
            # between driver close and tick() auto-close.
            return
        expired: list[str] = [
            did
            for did, d in self._open.items()
            if world_tick - d.last_activity_tick >= self.TIMEOUT_TICKS
        ]
        for did in expired:
            self.close_dialog(did, reason="timeout", tick=world_tick)

    def _allocate_dialog_id(self, initiator_id: str, target_id: str) -> str:
        """Allocate a dialog id for a newly-admitted ``(initiator_id, target_id)`` pair.

        M2 §M4.2 (I4): when a per-pair named RNG substream factory is
        injected, the id is drawn deterministically from that same pair's
        substream (the one ``tick()``'s auto-fire draw above also consumes)
        instead of :func:`_allocate_dialog_id`'s module-level ``uuid.uuid4()``
        — a record-mode driver that folds ``dialog_id`` into a reproducibility
        checksum (:func:`~erre_sandbox.integration.embodied.society.event_log_checksum`)
        cannot tolerate an unseeded id. ``None`` (the default, every existing
        live/eval caller) keeps the pre-existing ``uuid4``-based allocation
        byte-for-byte.
        """
        if self._rng_for_pair is not None:
            draw_rng = self._rng_for_pair(initiator_id, target_id)
            return f"d_{draw_rng.getrandbits(32):08x}"
        return _allocate_dialog_id()

    def _emit(self, envelope: ControlEnvelope) -> None:
        try:
            self._sink(envelope)
        except Exception:
            # We refuse to let a sink failure desync scheduler state — log and
            # continue. The sink is the gateway's responsibility; if it is
            # broken that is a gateway-layer bug, not ours.
            logger.exception(
                "Dialog scheduler sink raised for envelope kind=%s",
                envelope.kind,
            )


# ---------------------------------------------------------------------------
# Module-private helpers
# ---------------------------------------------------------------------------


def _allocate_dialog_id() -> str:
    return f"d_{uuid.uuid4().hex[:8]}"


def _iter_colocated_pairs(
    agents: Iterable[AgentView],
) -> Iterator[tuple[AgentView, AgentView]]:
    """Yield (a, b) pairs of distinct agents sharing the same zone.

    Each unordered pair is yielded exactly once with a stable ``a.agent_id``
    < ``b.agent_id`` ordering, so callers can use the first entry as the
    canonical initiator without extra sorting.
    """
    sorted_agents = sorted(agents, key=lambda v: v.agent_id)
    for i, a in enumerate(sorted_agents):
        for b in sorted_agents[i + 1 :]:
            if a.zone == b.zone:
                yield a, b


def _iter_all_distinct_pairs(
    agents: Iterable[AgentView],
) -> Iterator[tuple[AgentView, AgentView]]:
    """Yield every distinct unordered pair regardless of zone, exactly once.

    Each unordered pair surfaces with a stable ``a.agent_id`` < ``b.agent_id``
    ordering (mirroring :func:`_iter_colocated_pairs`), so callers can use
    the first entry as the canonical initiator without extra sorting.

    m9-eval-system P3a-decide: used by ``tick()`` when
    ``eval_natural_mode=True``. The zone field on the leading element is
    still meaningful (it becomes the dialog's recorded zone via the
    ``schedule_initiate`` envelope), but pair eligibility itself does not
    depend on zone equality.
    """
    sorted_agents = sorted(agents, key=lambda v: v.agent_id)
    for i, a in enumerate(sorted_agents):
        for b in sorted_agents[i + 1 :]:
            yield a, b


__all__ = [
    # Re-exported from :mod:`erre_sandbox.schemas` for import ergonomics in
    # callers that already reach into this module for the scheduler.
    "AgentView",
    "InMemoryDialogScheduler",
]
