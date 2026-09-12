"""Single-coroutine heapq scheduler that drives the world tick loop (T13).

The runtime owns three periodic handlers:

* **physics** — 30 Hz: advance each agent's :class:`Kinematics`, emit
  :class:`ZoneTransitionEvent` when a zone boundary is crossed.
* **cognition** — 0.1 Hz (every 10 s): fan out to
  :meth:`CognitionCycle.step` for every registered agent via
  :func:`asyncio.gather` (``return_exceptions=True``) so one agent's LLM
  failure does not cancel the sibling tasks.
* **heartbeat** — 1 Hz: push a :class:`WorldTickMsg` into the envelope
  queue for observability.

All three live on a single :class:`asyncio.Task` via a min-heap of absolute
``due_at`` timestamps, which removes cross-task data races (no lock is taken
on ``_agents`` / ``_envelopes``) and lets a :class:`ManualClock` reproduce
any desired interleaving in tests.

The v2 design uses a single coroutine, Voronoi zones, an unbounded queue,
and anti-drift timing.
"""

from __future__ import annotations

import asyncio
import contextlib
import heapq
import logging
import math
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field, replace
from itertools import combinations
from typing import TYPE_CHECKING, ClassVar, Final, Literal

from erre_sandbox.cognition.relational import apply_affinity
from erre_sandbox.cognition.world_model import project_world_model_snapshot
from erre_sandbox.contracts.cognition_layers import IndividualProfile, PersonalityDrift
from erre_sandbox.schemas import (
    AffordanceEvent,
    AgentState,
    AgentView,
    ControlEnvelope,
    DialogScheduler,
    DialogTurnGenerator,
    DialogTurnMsg,
    EpochPhase,
    ErrorMsg,
    MoveMsg,
    Observation,
    PersonaSpec,
    PropLayout,
    ProximityEvent,
    RelationshipBond,
    RunLifecycleState,
    TemporalEvent,
    TimeOfDay,
    WorldLayoutMsg,
    WorldTickMsg,
    Zone,
    ZoneLayout,
    ZoneTransitionEvent,
)
from erre_sandbox.world.physics import Kinematics, apply_move_command, step_kinematics
from erre_sandbox.world.zones import (
    ZONE_CENTERS,
    ZONE_PROPS,
    default_spawn,
    locate_zone,
)

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable, Coroutine, Sequence

    from erre_sandbox.cognition import (
        CognitionCycle,
        CycleResult,
        WorldModelRuntimeState,
    )
    from erre_sandbox.contracts.cognition_layers import (
        DevelopmentState,
        NarrativeArc,
        PromotedEvidenceUnit,
        WorldModelHintDisposition,
        WorldModelSnapshot,
    )

    # M11-C2 / M10-A 段B: flag-on individual-state trace sink. Args are
    # ``(profile, belief_classes, world_model_evidence, tick)``; the orchestrator's
    # closure binds ``run_id`` and builds the trace row, so ``world`` never imports
    # ``evidence`` and never learns ``run_id`` (DA-M11C2-4). Both ``belief_classes``
    # and ``world_model_evidence`` ride in on ``CycleResult`` so ``world`` never
    # imports ``memory`` either (DA-M11C2-2 / DA-SB-1).
    IndividualTraceSink = Callable[
        [
            IndividualProfile,
            "list[str] | None",
            "list[PromotedEvidenceUnit] | None",
            int,
        ],
        None,
    ]

    # Saturation probe (ADR section 5): flag-on per-channel trace sink. Args are
    # ``(individual_id, world_model_saturation, tick)``; the orchestrator's closure
    # binds ``run_id`` / ``seed`` / ``individual_layer_enabled`` and explodes the
    # snapshot into rows, so ``world`` never imports ``evidence`` and never learns
    # the run identity. The post-reconcile pre-nudge ``WorldModelSnapshot`` rides in
    # on ``CycleResult.world_model_saturation`` so ``world`` never imports cognition.
    SaturationTraceSink = Callable[
        [
            str,
            "WorldModelSnapshot",
            int,
        ],
        None,
    ]

    # Engagement instrument (ADR §5): flag-on per-(agent, tick) hint-disposition sink.
    # Args are ``(individual_id, world_model_hint_engagement, tick)``; the
    # orchestrator's closure binds ``run_id`` / ``seed`` / ``individual_layer_enabled``
    # and builds the trace row, so ``world`` never imports ``evidence`` / learns the run
    # identity. The carrier rides in on ``CycleResult.world_model_hint_engagement`` (a
    # ``contracts`` read-model), so the sink adds no ``cognition`` dependency beyond the
    # ``CycleResult`` ``world`` already consumes — it never touches the classifier.
    HintEngagementTraceSink = Callable[
        [
            str,
            "WorldModelHintDisposition",
            int,
        ],
        None,
    ]

    # U5 replay infra: flag-on per-(agent, tick) reconcile-input floor sink. Args are
    # ``(individual_id, world_model_saturation, tick)`` — the **same** carrier the
    # saturation sink reads; the orchestrator's closure binds ``run_id`` / ``seed`` /
    # ``individual_layer_enabled`` and serialises ``snapshot.base_floor`` (the full
    # reconcile-input floor) into a row, so ``world`` never imports ``evidence`` and
    # never learns the run identity. Persisting the full floor (the saturation trace
    # is lossy) is what lets a deterministic replay re-feed it into the unchanged
    # ``reconcile_world_model`` kernel (U5 design DA-U5-1).
    FloorInputTraceSink = Callable[
        [
            str,
            "WorldModelSnapshot",
            int,
        ],
        None,
    ]

    # Bond-affinity trace (instrumentation ADR section 3.3, carrier A): flag-on
    # per-(agent, tick) sink. Args are ``(individual_id, relationships, tick)`` — the
    # agent's ``list[RelationshipBond]`` carried out on ``CycleResult.agent_state`` (no
    # new carrier field; ``world`` already consumes ``res.agent_state``). The
    # orchestrator's closure binds ``run_id`` / ``seed`` / ``individual_layer_enabled``
    # and builds the rows, so ``world`` never imports ``evidence`` / learns the run
    # identity. ``RelationshipBond`` is a ``schemas`` type ``world`` already imports, so
    # the sink adds no new dependency.
    BondAffinityTraceSink = Callable[
        [
            str,
            list[RelationshipBond],
            int,
        ],
        None,
    ]

    # ECL v0 (Issue 003): flag-on per-(agent, physics-tick) embodiment trace sink.
    # Args are ``(agent_id, physics_tick_index, x, y, z, yaw, pitch, zone)`` — pure
    # ``schemas`` primitives; the integration orchestrator's closure binds ``run_id`` /
    # ``agent_tick`` / ``order_slot`` and builds the trace row, so ``world`` never
    # imports ``integration`` / ``evidence`` and never learns the run identity. Mirrors
    # the existing injected-sink house-style (``IndividualTraceSink`` et al.); ``None``
    # (flag-off / live flow) makes ``_emit_ecl_trace`` a no-op so the live hot path
    # stays byte-invariant. ``physics_tick_index`` (30 Hz) is kept distinct from the
    # agent cognition ``tick`` (design §論点3, Codex MEDIUM-2); ``order_slot`` is
    # derived downstream from ``sorted(agent_id)`` — the sink fires in that order
    # (Codex MEDIUM-3).
    EclTraceSink = Callable[
        [str, int, float, float, float, float, float, Zone],
        None,
    ]

logger = logging.getLogger(__name__)


def _make_runtime_error(*, code: str, detail: str) -> ErrorMsg:
    # Intentional duplicate of integration.gateway._make_error: keeping the
    # world layer independent of the integration layer (architecture-rules:
    # integration consumes world, not the reverse) so importing the gateway
    # helper into tick.py would invert the dependency.
    return ErrorMsg(tick=0, code=code, detail=detail)


# =============================================================================
# Simulated time-of-day (M6-A-2b)
# =============================================================================

# Ordered ascending by phase. The period covering ``phase ∈ [phase, next_phase)``
# is the one returned by :func:`_time_of_day`. The six buckets map a
# continuous wall-time into the same vocabulary ``TimeOfDay`` uses so the
# FSM and LLM prompt can reason about "morning" without comparing floats.
# Boundaries skew toward daylight because research-session relevance peaks
# around noon / afternoon — night is the short tail.
_PERIOD_BOUNDARIES: tuple[tuple[float, TimeOfDay], ...] = (
    (0.00, TimeOfDay.DAWN),
    (0.10, TimeOfDay.MORNING),
    (0.40, TimeOfDay.NOON),
    (0.55, TimeOfDay.AFTERNOON),
    (0.80, TimeOfDay.DUSK),
    (0.90, TimeOfDay.NIGHT),
)


_PROXIMITY_THRESHOLD_M: Final[float] = 5.0
"""Distance at which an agent pair is considered "proximate" (M6-A-2b).

One :class:`ProximityEvent` is emitted per threshold crossing (``enter``
when the distance falls below, ``leave`` when it rises back above) so
co-walking agents do not spam the observation stream.  The value is
deliberately larger than a conversational radius so the FSM can react
**before** the dialog scheduler kicks in — five metres is the MASTER-PLAN
reading of "same room but not yet engaged".
"""

_SEP_PUSH_M: Final[float] = 0.4
"""Per-tick separation nudge in metres (M7ζ-3).

Sized so two ticks of pushing (0.8 m) is well inside the 1.5 m default
``separation_radius_m`` *and* well below :data:`_PROXIMITY_THRESHOLD_M`
(5 m), so dialog-scheduler proximity events are not displaced by
collapse correction.
"""


_AFFORDANCE_RADIUS_M: Final[float] = 2.0
"""Distance at which an agent is considered to notice a static world prop (M7 B1).

Mirrors the crossing-only semantics of :data:`_PROXIMITY_THRESHOLD_M`: a
single :class:`AffordanceEvent` is emitted when the agent's XZ distance to
a prop first falls below this radius. Until the agent has moved back out
of range and re-entered, no further event fires. The value is tighter than
proximity (5 m) because props are spot-like salience markers — a tea bowl
is noticed when the agent is *at* it, not merely in the same zone."""


_NEGATIVE_DELTA_TRIGGER: Final[float] = -0.05
"""M7δ threshold below which a negative affinity delta raises emotional_conflict.

Calibrated so the antagonism table's -0.10 magnitude (kant↔nietzsche)
fires the bump while transient negative noise from decay alone (decay
contribution at low ``prev`` is well above -0.05) does not. Value as of
the C5 retune."""

_EMOTIONAL_CONFLICT_GAIN: Final[float] = 0.5
"""Coefficient applied to ``abs(delta)`` when raising emotional_conflict.

A -0.10 antagonism delta therefore raises emotional_conflict by 0.05
per turn, clamped at the upper bound of 1.0. The decay back to baseline
(``-0.02`` per tick) happens in
:func:`erre_sandbox.cognition.state.advance_physical`. Value as of the
C5 retune."""


def _time_of_day(elapsed: float, day_duration: float) -> TimeOfDay:
    """Map an elapsed-time scalar to the containing :class:`TimeOfDay` bucket.

    ``day_duration`` is the wall-clock length (seconds) of one simulated day
    — the runtime passes its configured value so tests can compress a day
    into milliseconds. The function is pure and cheap; called once per
    physics tick.
    """
    if day_duration <= 0.0:
        return TimeOfDay.DAWN  # degenerate — avoid divide-by-zero
    phase = (elapsed % day_duration) / day_duration
    current = _PERIOD_BOUNDARIES[0][1]
    for boundary, period in _PERIOD_BOUNDARIES:
        if phase >= boundary:
            current = period
    return current


# =============================================================================
# Clock abstraction
# =============================================================================


class Clock(ABC):
    """Minimal clock used by :class:`WorldRuntime` for absolute scheduling."""

    @abstractmethod
    def monotonic(self) -> float:
        """Return the current monotonic time in seconds."""

    @abstractmethod
    async def sleep_until(self, due_at: float) -> None:
        """Sleep until :meth:`monotonic` would return at least ``due_at``."""


class RealClock(Clock):
    """Production clock backed by :func:`time.monotonic` / :func:`asyncio.sleep`."""

    def monotonic(self) -> float:
        return time.monotonic()

    async def sleep_until(self, due_at: float) -> None:
        delta = due_at - time.monotonic()
        if delta > 0.0:
            await asyncio.sleep(delta)


class ManualClock(Clock):
    """Deterministic clock for tests.

    ``advance(dt)`` moves the clock forward by ``dt`` seconds and resolves any
    :meth:`sleep_until` waiters whose ``due_at`` has been reached. Waiters
    with identical ``due_at`` are woken in insertion order.
    """

    def __init__(self, start: float = 0.0) -> None:
        self._now: float = start
        self._waiters: list[tuple[float, int, asyncio.Future[None]]] = []
        self._seq: int = 0

    def monotonic(self) -> float:
        return self._now

    async def sleep_until(self, due_at: float) -> None:
        if due_at <= self._now:
            await asyncio.sleep(0)
            return
        loop = asyncio.get_running_loop()
        fut: asyncio.Future[None] = loop.create_future()
        self._seq += 1
        heapq.heappush(self._waiters, (due_at, self._seq, fut))
        await fut

    def advance(self, dt: float) -> None:
        """Advance time and wake any sleepers whose ``due_at <= new now``.

        The method is synchronous on purpose: callers usually issue it as
        ``manual_clock.advance(...)`` and then ``await asyncio.sleep(0)`` to
        let the event loop run the woken coroutines.
        """
        if dt < 0.0:
            msg = "ManualClock cannot run backward"
            raise ValueError(msg)
        self._now += dt
        while self._waiters and self._waiters[0][0] <= self._now:
            _, _, fut = heapq.heappop(self._waiters)
            if not fut.done():
                fut.set_result(None)


# =============================================================================
# Scheduled events
# =============================================================================


@dataclass(order=True)
class ScheduledEvent:
    """A single entry on the runtime's min-heap.

    ``order=True`` plus the ``seq`` tie-breaker gives stable FIFO ordering
    when two events share the same ``due_at``, which matters because the three
    handlers (physics, cognition, heartbeat) are all seeded at ``t = 0``.
    """

    due_at: float
    seq: int
    period: float = field(compare=False)
    handler: Callable[[], Awaitable[None]] = field(compare=False)
    name: str = field(compare=False, default="")


# =============================================================================
# Agent runtime bookkeeping
# =============================================================================


@dataclass(slots=True)
class AgentRuntime:
    """Per-agent mutable state owned by :class:`WorldRuntime`.

    Kept deliberately separate from :class:`AgentState` so that transient
    bookkeeping (pending observations, kinematics) never leaks into the
    persisted snapshot.
    """

    agent_id: str
    state: AgentState
    persona: PersonaSpec
    kinematics: Kinematics
    pending: list[Observation] = field(default_factory=list)
    # M7ζ-3 phase-wheel cognition cadence. The global cognition heap event
    # still fires every ``_cognition_period`` seconds, but each agent only
    # actually steps when ``next_cognition_due <= clock.monotonic()`` — so
    # personas with longer ``cognition_period_s`` skip ticks and personas
    # with shorter periods step every global tick.
    next_cognition_due: float = 0.0
    # M7ζ-3 post-MoveMsg dwell. Set when a MoveMsg fires so the next
    # ``persona.behavior_profile.dwell_time_s`` seconds suppress cognition
    # entirely (Rikyū seiza). Phase wheel resumes once the global clock
    # passes this deadline.
    dwell_until: float = 0.0
    # M10-C individual-layer world-model state, carried across ticks. ``None``
    # until the first flag-on step seeds it (and always ``None`` flag-off). Lives
    # here — per-agent transient bookkeeping, never on the shared CognitionCycle —
    # so multi-agent runs cannot cross-contaminate (DA-M10C-6). Written back from
    # ``CycleResult.world_model_runtime`` in :meth:`WorldRuntime._consume_result`,
    # mirroring how ``state`` is updated.
    world_model_runtime: WorldModelRuntimeState | None = None
    # M11-A diagnostic narrative arc, carried across ticks. ``None`` until the
    # first flag-on step distils one (and always ``None`` flag-off). Written back
    # from ``CycleResult.narrative_arc`` in :meth:`WorldRuntime._consume_result`;
    # a ``None`` result leaves the last good arc in place (carry-forward).
    # Note: like ``world_model_runtime``, a runtime flag-on→off toggle
    # is unsupported — a stale arc would linger; the layer flag is read
    # once at construction in production.
    narrative_arc: NarrativeArc | None = None
    # M11-B evidence-driven development stage, carried across ticks. ``None`` until
    # the first flag-on fresh-evidence step advances it (always ``None`` flag-off).
    # Written back from ``CycleResult.development_state`` in
    # :meth:`WorldRuntime._consume_result`; a ``None`` result leaves the prior
    # state in place (carry-forward), mirroring ``narrative_arc`` /
    # ``world_model_runtime``. This field stays the single source of truth for the
    # stage; ``IndividualProfile`` is a *derived* read-model produced by
    # :meth:`snapshot_profile` (M11-C1; the live home is *not* moved off
    # ``AgentRuntime``).
    development_state: DevelopmentState | None = None

    def snapshot_profile(self) -> IndividualProfile:
        """Project the live carried state into an immutable read-model (M11-C1).

        Derived, never a second source of truth: the live home stays on this
        ``AgentRuntime`` (mutable fields, hot loop). All three carried fields are
        **deep-copied** so the returned profile can never alias — and therefore
        never mutate — the live state (owner single source). ``None``
        is projected faithfully as ``None``: a flag-off
        or pre-synthesis/pre-advance state is *not* materialised into a default,
        which would fabricate an unobserved state (e.g. a phantom S1_seed).

        ``personality_drift_offset`` has no live home on ``AgentRuntime`` yet, so
        it is the zero-offset default — an honest "no drift accumulated" read,
        not a fabrication. Drift mechanics arrive in a later milestone; when a
        live ``personality_drift`` field lands here, this line must switch to
        ``self.personality_drift.model_copy(deep=True)`` (same alias guard).

        Intended to be called **flag-on only** (the M11-C2 trace sink); C1 wires
        no unconditional caller, so flag-off byte-invariance is preserved.
        """
        return IndividualProfile(
            individual_id=self.agent_id,
            base_persona_id=self.state.persona_id,
            world_model=(
                project_world_model_snapshot(self.world_model_runtime)
                if self.world_model_runtime is not None
                else None
            ),
            development_state=(
                self.development_state.model_copy(deep=True)
                if self.development_state is not None
                else None
            ),
            narrative_arc=(
                self.narrative_arc.model_copy(deep=True)
                if self.narrative_arc is not None
                else None
            ),
            personality_drift_offset=PersonalityDrift(),
        )


@dataclass(slots=True)
class _PendingTurn:
    """One in-flight turn request staged by :meth:`WorldRuntime._drive_dialog_turns`.

    Staging the coroutine with its metadata lets the gather loop correlate
    each result with the dialog/speaker it belongs to for post-processing.
    """

    dialog_id: str
    speaker_id: str
    addressee_id: str
    turn_index: int
    coro: Coroutine[object, object, DialogTurnMsg | None]


# =============================================================================
# WorldRuntime
# =============================================================================


class WorldRuntime:
    """Drives physics + cognition + heartbeat for N agents on one asyncio task.

    Construction injects the :class:`CognitionCycle` (so the test double
    used in :mod:`tests.test_world` can be trivially swapped) and a
    :class:`Clock` (defaults to :class:`RealClock`; tests pass
    :class:`ManualClock` to drive time deterministically).
    """

    DEFAULT_PHYSICS_HZ: ClassVar[float] = 30.0
    DEFAULT_COGNITION_PERIOD_S: ClassVar[float] = 10.0
    DEFAULT_HEARTBEAT_PERIOD_S: ClassVar[float] = 1.0
    DEFAULT_DAY_DURATION_S: ClassVar[float] = 480.0
    """Wall-clock seconds per simulated day (M6-A-2b).

    Eight minutes is short enough that a live demo can traverse the full
    dawn → night cycle in one session while still giving the agent time
    to exhibit each :class:`TimeOfDay` phase. Tests pass a much smaller
    value via ``day_duration_s`` so crossing events can be forced quickly
    without advancing the :class:`ManualClock` for thousands of seconds.
    """

    def __init__(
        self,
        *,
        cycle: CognitionCycle,
        clock: Clock | None = None,
        physics_hz: float | None = None,
        cognition_period_s: float | None = None,
        heartbeat_period_s: float | None = None,
        day_duration_s: float | None = None,
        individual_trace_sink: IndividualTraceSink | None = None,
        saturation_trace_sink: SaturationTraceSink | None = None,
        hint_engagement_trace_sink: HintEngagementTraceSink | None = None,
        floor_input_trace_sink: FloorInputTraceSink | None = None,
        bond_affinity_trace_sink: BondAffinityTraceSink | None = None,
        ecl_trace_sink: EclTraceSink | None = None,
    ) -> None:
        self._cycle = cycle
        # M11-C2: flag-on individual-state trace sink. ``None`` (flag-off / live
        # flow) means ``_consume_result`` never calls ``snapshot_profile`` and no
        # trace is emitted — the flag-off byte-invariant carries through C1's
        # snapshot into C2's substrate (DA-M11C2-1/5). Wired only by the eval
        # orchestrator's individual-layer-enabled branch (DA-M11C2-7).
        self._individual_trace_sink: IndividualTraceSink | None = individual_trace_sink
        # Saturation probe (ADR section 5): flag-on per-channel trace sink, wired
        # only by the eval orchestrator's individual-layer-enabled branch. ``None``
        # (flag-off / live flow) makes ``_emit_saturation_trace`` a no-op so the
        # flag-off DuckDB stays byte-identical (the new table is never bootstrapped).
        self._saturation_trace_sink: SaturationTraceSink | None = saturation_trace_sink
        # Engagement instrument (ADR §5): flag-on hint-disposition trace sink, wired
        # only by the eval orchestrator's individual-layer-enabled branch. ``None``
        # (flag-off / live flow) makes ``_emit_hint_engagement_trace`` a no-op so the
        # flag-off DuckDB stays byte-identical (the new table is never bootstrapped).
        self._hint_engagement_trace_sink: HintEngagementTraceSink | None = (
            hint_engagement_trace_sink
        )
        # U5 replay infra: flag-on reconcile-input floor trace sink, wired only by the
        # eval orchestrator's individual-layer-enabled branch. ``None`` (flag-off / live
        # flow) makes ``_emit_floor_input_trace`` a no-op so the flag-off DuckDB stays
        # byte-identical (the new table is never bootstrapped).
        self._floor_input_trace_sink: FloorInputTraceSink | None = (
            floor_input_trace_sink
        )
        # Bond-affinity trace (instrumentation ADR section 3.3): flag-on per-(agent,
        # tick) bond sink, wired only by the eval orchestrator's individual-layer
        # branch. ``None`` (flag-off / live flow) makes ``_emit_bond_affinity_trace`` a
        # no-op so the flag-off DuckDB stays byte-identical (the table is never
        # bootstrapped).
        self._bond_affinity_trace_sink: BondAffinityTraceSink | None = (
            bond_affinity_trace_sink
        )
        # ECL v0 (Issue 003): flag-on embodiment trace sink, wired only by the
        # integration construction driver's ECL branch. ``None`` (flag-off / live flow)
        # makes ``_emit_ecl_trace`` a no-op so the physics hot path is byte-invariant.
        self._ecl_trace_sink: EclTraceSink | None = ecl_trace_sink
        # 30 Hz physics-tick counter, deliberately separate from the agent cognition
        # ``tick`` (design §論点3 / Codex MEDIUM-2). Advanced every ``_on_physics_tick``
        # regardless of the sink so a mid-run wiring sees a monotonic index; read only
        # by ``_emit_ecl_trace``, so its advance is invisible to every envelope.
        self._physics_tick_index: int = 0
        self._clock: Clock = clock if clock is not None else RealClock()
        self._physics_dt = 1.0 / (physics_hz or self.DEFAULT_PHYSICS_HZ)
        self._cognition_period = (
            cognition_period_s
            if cognition_period_s is not None
            else self.DEFAULT_COGNITION_PERIOD_S
        )
        self._heartbeat_period = (
            heartbeat_period_s
            if heartbeat_period_s is not None
            else self.DEFAULT_HEARTBEAT_PERIOD_S
        )
        self._day_duration_s = (
            day_duration_s
            if day_duration_s is not None
            else self.DEFAULT_DAY_DURATION_S
        )
        # M6-A-2b: simulated time-of-day tracking. ``_time_start`` is
        # lazily initialised on the first physics tick so ``_current_period``
        # matches the clock the runtime was actually started with (not the
        # clock the constructor saw, which is usually still at t=0).
        self._time_start: float | None = None
        self._current_period: TimeOfDay = TimeOfDay.DAWN
        # M6-A-2b: ProximityEvent needs a prev-tick distance per agent pair
        # to detect threshold crossings. Key is ``frozenset({id_a, id_b})``
        # so each unordered pair gets exactly one entry regardless of which
        # side registered first. Stale entries (one side de-registered)
        # remain until the pair is observed again and overwrites itself;
        # WorldRuntime does not currently expose agent removal, so
        # purge-on-deregister is left to the caller that adds that hook.
        self._pair_distances: dict[frozenset[str], float] = {}
        # M7 B1: per-(agent_id, prop_id) last-seen XZ distance so
        # AffordanceEvent emits once per *entry* into a prop's salient radius,
        # not every tick the agent remains inside it. Populated lazily by
        # ``_fire_affordance_events``; entries are never purged (the table is
        # O(agents × props) and both bounds are small at MVP scale).
        self._agent_prop_distances: dict[tuple[str, str], float] = {}
        self._agents: dict[str, AgentRuntime] = {}
        self._events: list[ScheduledEvent] = []
        # SH-5 (2026-05-13): bounded 2-queue split. Heartbeat is coalesced
        # to the latest tick (maxsize=1, latest-wins) because consumers only
        # care about the most recent world tick. Dialog / move / error
        # envelopes go to a bounded main queue (maxsize=1024) with drop-oldest
        # + ErrorMsg("runtime_backlog_overflow") warning so a stalled
        # WebSocket consumer cannot grow runtime memory without bound. The
        # same drop-oldest shape is used at the gateway layer (Registry.fan_out)
        # — see decisions.md SH-5 for the 3-alternative evaluation.
        self._heartbeat_envelopes: asyncio.Queue[ControlEnvelope] = asyncio.Queue(
            maxsize=1,
        )
        self._envelopes: asyncio.Queue[ControlEnvelope] = asyncio.Queue(maxsize=1024)
        self._envelope_overflow_count: int = 0
        self._dialog_scheduler: DialogScheduler | None = None
        # M5 orchestrator-integration: optional LLM-backed generator consulted
        # at the end of each cognition tick via ``_drive_dialog_turns``. When
        # ``None`` (e.g. unit tests that construct a bare runtime), open
        # dialogs are still admitted / timed out by the scheduler but no
        # utterances are generated — they close via the existing timeout path.
        self._dialog_generator: DialogTurnGenerator | None = None
        self._running: bool = False
        self._seq: int = 0
        # M8 L6-D3: run-level epoch state for the two-phase methodology.
        # Defaults to AUTONOMOUS so existing callers (run()) get today's
        # behaviour unchanged. Mutated only via transition_to_q_and_a() /
        # transition_to_evaluation() — direct assignment is not supported
        # (the field is addressed through a read-only property).
        self._run_lifecycle: RunLifecycleState = RunLifecycleState()

    # ----- Run lifecycle (M8) -----

    @property
    def run_lifecycle(self) -> RunLifecycleState:
        """Snapshot of the current run-level epoch state.

        Returns the live ``RunLifecycleState`` instance. Pydantic models are
        mutable by default, but callers **must not** mutate it — all state
        changes go through :meth:`transition_to_q_and_a` /
        :meth:`transition_to_evaluation` so the FSM invariants hold.
        """
        return self._run_lifecycle

    def transition_to_q_and_a(self) -> RunLifecycleState:
        """Advance the run from ``autonomous`` to ``q_and_a``.

        Raises :class:`ValueError` if the current phase is not
        :attr:`EpochPhase.AUTONOMOUS`. Replaces the lifecycle instance so
        observers that snapshotted the old value see a stable record.
        """
        current = self._run_lifecycle.epoch_phase
        if current is not EpochPhase.AUTONOMOUS:
            msg = (
                f"cannot transition to q_and_a from {current.value!r}; "
                "only autonomous → q_and_a is allowed"
            )
            raise ValueError(msg)
        self._run_lifecycle = RunLifecycleState(epoch_phase=EpochPhase.Q_AND_A)
        return self._run_lifecycle

    def transition_to_evaluation(self) -> RunLifecycleState:
        """Advance the run from ``q_and_a`` to ``evaluation``.

        Raises :class:`ValueError` if the current phase is not
        :attr:`EpochPhase.Q_AND_A`. Direct ``autonomous → evaluation`` is
        disallowed to protect the autonomous-emergence claim (any Q&A
        interaction with the researcher must be recorded before the run
        enters offline scoring).
        """
        current = self._run_lifecycle.epoch_phase
        if current is not EpochPhase.Q_AND_A:
            msg = (
                f"cannot transition to evaluation from {current.value!r}; "
                "only q_and_a → evaluation is allowed"
            )
            raise ValueError(msg)
        self._run_lifecycle = RunLifecycleState(epoch_phase=EpochPhase.EVALUATION)
        return self._run_lifecycle

    # ----- Registration -----

    def register_agent(self, state: AgentState, persona: PersonaSpec) -> None:
        """Add an agent whose cognition cycle this runtime should drive.

        Must be called before :meth:`run` or from within a handler on the
        same event-loop task; the runtime uses a plain :class:`dict` for
        ``_agents`` and takes no lock, so concurrent mutation from a
        different task would race with the scheduler.

        Re-registering an existing ``agent_id`` raises ``ValueError`` rather than
        silently overwriting the live runtime (M11-C1, DA-M11C1-3): same-base
        multi-individual launches must collide loudly so a launcher bug (e.g. a
        missing ordinal) surfaces at registration instead of corrupting state.
        """
        if state.agent_id in self._agents:
            msg = f"agent_id {state.agent_id!r} already registered"
            raise ValueError(msg)
        self._agents[state.agent_id] = AgentRuntime(
            agent_id=state.agent_id,
            state=state,
            persona=persona,
            kinematics=Kinematics(position=state.position),
        )

    def inject_observation(self, agent_id: str, obs: Observation) -> None:
        """Queue an externally sourced observation for ``agent_id``.

        The observation is consumed on the next cognition tick. Useful for
        tests and for T14 when external stimuli (e.g. user messages) need to
        reach an agent without going through the physics loop.
        """
        self._agents[agent_id].pending.append(obs)

    @property
    def agent_ids(self) -> list[str]:
        """Snapshot of currently registered agent ids (order = registration)."""
        return list(self._agents)

    def agent_persona_id(self, agent_id: str) -> str | None:
        """Resolve ``agent_id`` to its ``persona_id``; ``None`` when unknown.

        Used by the M8 L6-D1 dialog-turn sink closure in bootstrap to stamp
        each persisted turn with both participants' persona ids.
        Read-only — does not mutate the registry.
        """
        agent = self._agents.get(agent_id)
        return agent.state.persona_id if agent is not None else None

    def get_bond_affinity(
        self,
        agent_id: str,
        other_agent_id: str,
    ) -> float:
        """Return ``agent_id``'s current affinity toward ``other_agent_id``.

        ``0.0`` when ``agent_id`` is unknown or has no bond yet — matches
        :class:`RelationshipBond.affinity`'s default so the M7δ semi-formula's
        ``prev`` argument can be threaded through the bootstrap relational
        sink without a special "first interaction" branch. Read-only.
        """
        rt = self._agents.get(agent_id)
        if rt is None:
            return 0.0
        for bond in rt.state.relationships:
            if bond.other_agent_id == other_agent_id:
                return bond.affinity
        return 0.0

    def get_agent_zone(self, agent_id: str) -> Zone | None:
        """Return the zone of ``agent_id``'s current :class:`Position`.

        ``None`` when ``agent_id`` is unknown. Used by the M7δ bootstrap
        relational sink to stamp ``RelationshipBond.last_interaction_zone``
        with the zone the speaker spoke from. Read-only.
        """
        rt = self._agents.get(agent_id)
        if rt is None:
            return None
        return rt.state.position.zone

    def apply_affinity_delta(
        self,
        *,
        agent_id: str,
        other_agent_id: str,
        delta: float,
        tick: int,
        zone: Zone | None = None,
    ) -> None:
        """Apply an affinity ``delta`` to ``agent_id``'s bond with ``other_agent_id``.

        Mutates :attr:`AgentRuntime.state` in place via ``model_copy`` so the
        next ``AgentUpdateMsg`` snapshot picks up the new
        :class:`RelationshipBond`. When ``agent_id`` has no existing bond
        with ``other_agent_id`` a fresh bond is appended; otherwise the
        existing bond's :attr:`RelationshipBond.affinity` is updated (clamped
        through :func:`erre_sandbox.cognition.relational.apply_affinity`),
        :attr:`RelationshipBond.ichigo_ichie_count` is incremented, and
        :attr:`RelationshipBond.last_interaction_tick` is set to ``tick``.

        M7δ extensions:

        * ``zone`` — when supplied, written to
          :attr:`RelationshipBond.last_interaction_zone` so the Godot
          ``ReasoningPanel`` can render ``"<persona> affinity ±0.NN
          (N turns, last in <zone> @ tick T)"``. Default ``None`` keeps
          the field unset for callers that have not yet been migrated.
        * ``Physical.emotional_conflict`` write — negative ``delta`` past
          the M7δ trigger threshold (``< -0.05``) raises this field by
          ``abs(delta) * 0.5`` (clamped to ``[0, 1]``). Decay back to
          baseline lives in :func:`erre_sandbox.cognition.state.advance_physical`
          (per-tick ``-0.02``). Closes the dangling-read at
          ``cognition/state.py::sleep_penalty`` (R3 M4).

        Silent no-op when ``agent_id`` is not registered: the relational
        hook fires from the bootstrap turn-sink chain, which races a
        possible (M7γ-out-of-scope) deregistration. Future M9+ removal
        wiring should keep this fail-soft so a transient missing agent
        cannot crash the live runtime.
        """
        # SAFETY: single-writer assumption. The relational sink in
        # bootstrap is the sole producer of affinity-delta calls and runs
        # synchronously inside ``InMemoryDialogScheduler.record_turn``.
        # If M9 introduces parallel cognition cycles or external mutators
        # this method must guard ``rt.state.model_copy`` with an
        # ``asyncio.Lock`` to prevent lost updates (R3 H2).
        rt = self._agents.get(agent_id)
        if rt is None:
            return
        existing = list(rt.state.relationships)
        new_bonds: list[RelationshipBond] = []
        found = False
        for bond in existing:
            if bond.other_agent_id == other_agent_id:
                new_bonds.append(
                    bond.model_copy(
                        update={
                            "affinity": apply_affinity(bond.affinity, delta),
                            "ichigo_ichie_count": bond.ichigo_ichie_count + 1,
                            "last_interaction_tick": tick,
                            "last_interaction_zone": zone,
                        },
                    ),
                )
                found = True
            else:
                new_bonds.append(bond)
        if not found:
            new_bonds.append(
                RelationshipBond(
                    other_agent_id=other_agent_id,
                    affinity=apply_affinity(0.0, delta),
                    familiarity=0.0,
                    ichigo_ichie_count=1,
                    last_interaction_tick=tick,
                    last_interaction_zone=zone,
                ),
            )
        # M7δ: negative delta past the trigger threshold raises the
        # speaker / addressee's emotional_conflict so future cognition
        # cycles read the residue (sleep_penalty already consumes it).
        new_physical = rt.state.physical
        if delta < _NEGATIVE_DELTA_TRIGGER:
            bumped = min(
                1.0,
                rt.state.physical.emotional_conflict
                + abs(delta) * _EMOTIONAL_CONFLICT_GAIN,
            )
            new_physical = rt.state.physical.model_copy(
                update={"emotional_conflict": bumped},
            )
        rt.state = rt.state.model_copy(
            update={"relationships": new_bonds, "physical": new_physical},
        )

    def apply_belief_promotion(
        self,
        *,
        agent_id: str,
        other_agent_id: str,
        belief_kind: Literal["trust", "clash", "wary", "curious", "ambivalent"],
    ) -> None:
        """Stamp ``RelationshipBond.latest_belief_kind`` on a promoted dyad (M7ζ).

        Called from the bootstrap relational sink the moment
        :func:`erre_sandbox.cognition.belief.maybe_promote_belief` returns a
        non-None record, so the next ``AgentUpdateMsg`` snapshot carries the
        typed classification on the bond. Co-locating the write here (rather
        than at agent_state-export time via a semantic_memory lookup) avoids
        an extra DB read on every panel refresh; the bond IS the source of
        truth for what the Godot ``ReasoningPanel`` renders.

        Silent no-op when ``agent_id`` is not registered or the bond is
        absent: the relational sink is fire-and-forget, identical to
        :meth:`apply_affinity_delta`'s contract.

        SAFETY: same single-writer assumption as :meth:`apply_affinity_delta`
        — the bootstrap sink is the sole producer and runs synchronously.
        """
        rt = self._agents.get(agent_id)
        if rt is None:
            return
        existing = list(rt.state.relationships)
        new_bonds: list[RelationshipBond] = []
        found = False
        for bond in existing:
            if bond.other_agent_id == other_agent_id:
                new_bonds.append(
                    bond.model_copy(update={"latest_belief_kind": belief_kind}),
                )
                found = True
            else:
                new_bonds.append(bond)
        if not found:
            # Defensive: a promotion without a prior bond should never
            # happen (maybe_promote_belief reads bond fields), but if it
            # does the sink stays fail-soft rather than fabricating a bond.
            return
        rt.state = rt.state.model_copy(update={"relationships": new_bonds})

    def layout_snapshot(self, *, tick: int = 0) -> WorldLayoutMsg:
        """Construct a :class:`WorldLayoutMsg` from the static zone tables (M7γ).

        Pure read of :data:`erre_sandbox.world.zones.ZONE_CENTERS` and
        :data:`~erre_sandbox.world.zones.ZONE_PROPS` — no runtime state is
        consulted because in γ the world layout is immutable per run. The
        gateway emits this message exactly once per WS connection
        (see Slice γ Commit 3), immediately before completing the
        handshake-side ``registry.add(...)`` call.

        ``tick`` defaults to ``0`` to match the on-connect convention used
        by the ``world_layout.json`` fixture and asserted by
        ``tests/test_envelope_fixtures.py::test_shared_invariants_across_fixtures``.
        """
        zones = [
            ZoneLayout(zone=zone, x=x, y=y, z=z)
            for zone, (x, y, z) in ZONE_CENTERS.items()
        ]
        props: list[PropLayout] = [
            PropLayout(
                prop_id=spec.prop_id,
                prop_kind=spec.prop_kind,
                zone=zone,
                x=spec.x,
                y=spec.y,
                z=spec.z,
                salience=spec.salience,
            )
            for zone, prop_specs in ZONE_PROPS.items()
            for spec in prop_specs
        ]
        return WorldLayoutMsg(tick=tick, zones=zones, props=props)

    # ----- Envelope consumers (T14 hooks) -----

    async def recv_envelope(self) -> ControlEnvelope:
        """Await and return the next envelope.

        Blocking variant intended for T14's WebSocket producer. Main queue
        (``_envelopes``) is prioritised over heartbeat
        (``_heartbeat_envelopes``) when both are ready, so dialog and error
        envelopes never starve under a heartbeat-heavy load. When the race
        produces a *both-done* result, the heartbeat result is coalesce-
        requeued onto its own queue (latest-wins, maxsize=1) so the
        liveness signal is not silently dropped. The losing getter is
        cancelled and awaited (Python 3.11+ ``asyncio.Queue.get()`` is
        cancellation-safe — a cancelled getter does not pop from the queue).
        """
        main_task = asyncio.create_task(self._envelopes.get())
        hb_task = asyncio.create_task(self._heartbeat_envelopes.get())
        try:
            done, pending = await asyncio.wait(
                (main_task, hb_task),
                return_when=asyncio.FIRST_COMPLETED,
            )
            if main_task in done:
                # If heartbeat also finished, requeue its result so the
                # liveness tick is not silently dropped; coalescing
                # semantics (maxsize=1) make this safe even if a fresher
                # heartbeat is enqueued before the next recv.
                if hb_task in done and not hb_task.cancelled():
                    self._reinject_heartbeat(hb_task.result())
                else:
                    for task in pending:
                        task.cancel()
                await asyncio.gather(*pending, return_exceptions=True)
                return main_task.result()
            # heartbeat is the only completion. Cancel pending main getter
            # (Queue.get is cancellation-safe) and await it so no Task is
            # destroyed while pending.
            for task in pending:
                task.cancel()
            await asyncio.gather(*pending, return_exceptions=True)
            return hb_task.result()
        except BaseException:
            for task in (main_task, hb_task):
                if not task.done():
                    task.cancel()
            with contextlib.suppress(BaseException):
                await asyncio.gather(main_task, hb_task, return_exceptions=True)
            raise

    def _reinject_heartbeat(self, env: ControlEnvelope) -> None:
        # Place a recovered heartbeat back on its coalescing queue. If a
        # newer tick already occupies the slot, drop ours (latest-wins).
        with contextlib.suppress(asyncio.QueueFull):
            self._heartbeat_envelopes.put_nowait(env)

    def drain_envelopes(self) -> list[ControlEnvelope]:
        """Non-blocking drain of all currently queued envelopes.

        Drains the (coalesced, latest-only) heartbeat queue first, then the
        bounded main queue. Existing callers asserted that the periodic
        heartbeat appeared at the head of the drain when both clocks had
        advanced — that contract is preserved by emitting heartbeat first.
        Strict FIFO across both streams is not promised: the heartbeat
        queue collapses to the latest tick (SH-5).
        """
        out: list[ControlEnvelope] = []
        while not self._heartbeat_envelopes.empty():
            out.append(self._heartbeat_envelopes.get_nowait())
        while not self._envelopes.empty():
            out.append(self._envelopes.get_nowait())
        return out

    def _enqueue_with_drop_oldest(self, env: ControlEnvelope) -> None:
        # Mirror of ``Registry.fan_out`` (integration/gateway.py): on a full
        # queue, drop the oldest entries to make room for a warning + the
        # new envelope. The ``runtime_backlog_overflow`` code distinguishes
        # this runtime-side overflow from the gateway-side ``backlog_overflow``.
        if self._envelopes.maxsize > 0 and self._envelopes.full():
            while self._envelopes.qsize() > max(self._envelopes.maxsize - 2, 0):
                try:
                    self._envelopes.get_nowait()
                    self._envelope_overflow_count += 1
                except asyncio.QueueEmpty:  # pragma: no cover — defensive
                    break
            warning = _make_runtime_error(
                code="runtime_backlog_overflow",
                detail=(
                    f"runtime _envelopes full (maxsize="
                    f"{self._envelopes.maxsize}); "
                    f"drops={self._envelope_overflow_count}"
                ),
            )
            # Observability: emit an out-of-band
            # ``logger.warning`` alongside the in-band ErrorMsg so SRE
            # tooling that drains the journal (and only the journal — the
            # ErrorMsg consumer may be the very subscriber that is too slow
            # to dequeue the warning envelope) still sees the overflow.
            logger.warning(
                "runtime backlog overflow: drops=%d maxsize=%d",
                self._envelope_overflow_count,
                self._envelopes.maxsize,
            )
            try:
                self._envelopes.put_nowait(warning)
            except asyncio.QueueFull:  # pragma: no cover — maxsize < 2
                logger.debug("runtime dropped runtime_backlog_overflow warning")
        try:
            self._envelopes.put_nowait(env)
        except asyncio.QueueFull:  # pragma: no cover — we just made room
            logger.warning("runtime dropped envelope after drop-oldest")

    def inject_envelope(self, envelope: ControlEnvelope) -> None:
        """Append ``envelope`` to the fan-out queue from non-runtime code.

        Exposed for the dialog scheduler's envelope sink so it can interleave
        ``dialog_*`` messages with the cognition-generated stream without a
        second delivery path. Raw queue access stays private.
        """
        self._enqueue_with_drop_oldest(envelope)

    def attach_dialog_scheduler(self, scheduler: DialogScheduler) -> None:
        """Install the scheduler consulted at the end of each cognition tick.

        Separated from ``__init__`` because the scheduler's envelope sink
        normally wants to call :meth:`inject_envelope` on this same runtime,
        which is awkward to arrange before the runtime exists.
        """
        self._dialog_scheduler = scheduler

    def attach_dialog_generator(self, generator: DialogTurnGenerator) -> None:
        """Install the LLM-backed :class:`DialogTurnGenerator` (M5).

        When attached, :meth:`_on_cognition_tick` walks every open dialog
        after the scheduler's proximity-auto-fire / timeout-close pass and
        either (a) closes the dialog with ``reason="exhausted"`` if the
        speaker's ``dialog_turn_budget`` is saturated, or (b) asks the
        generator for the next utterance and records/emits the resulting
        :class:`DialogTurnMsg`. ``None`` from the generator leaves the
        dialog untouched for the existing timeout path to reap.

        Last-writer-wins: re-attaching replaces the previously attached
        generator, mirroring :meth:`attach_dialog_scheduler`.
        """
        self._dialog_generator = generator

    # ----- Lifecycle -----

    async def run(self) -> None:
        """Run the scheduler until :meth:`stop` is called.

        Uses a single min-heap of absolute ``due_at`` timestamps; on each
        iteration it pops the earliest event, awaits
        :meth:`Clock.sleep_until`, invokes the handler (with per-handler
        exception isolation so one bug cannot kill the loop), and reschedules
        the event at ``due_at + period`` (anti-drift: absolute time, not
        cumulative deltas).
        """
        now = self._clock.monotonic()
        self._schedule(
            now + self._physics_dt,
            self._physics_dt,
            self._on_physics_tick,
            name="physics",
        )
        self._schedule(
            now + self._cognition_period,
            self._cognition_period,
            self._on_cognition_tick,
            name="cognition",
        )
        self._schedule(
            now + self._heartbeat_period,
            self._heartbeat_period,
            self._on_heartbeat_tick,
            name="heartbeat",
        )

        self._running = True
        try:
            while self._running and self._events:
                ev = heapq.heappop(self._events)
                await self._clock.sleep_until(ev.due_at)
                if not self._running:
                    break
                try:
                    await ev.handler()
                except Exception:
                    logger.exception("world tick handler %s failed", ev.name)
                # Anti-drift: next due is previous due + period, not now + period.
                self._seq += 1
                next_due = ev.due_at + ev.period
                heapq.heappush(
                    self._events,
                    replace(ev, due_at=next_due, seq=self._seq),
                )
        finally:
            self._running = False

    def stop(self) -> None:
        """Signal :meth:`run` to return at the next scheduling point."""
        self._running = False

    # ----- Handlers -----

    def _sorted_runtimes(self) -> list[AgentRuntime]:
        """Return registered runtimes in deterministic ``sorted(agent_id)`` order.

        Discovery guard (§M4.3 / DA-M2IMPL-4): every Plane1 iteration over
        ``self._agents`` that can influence the record-mode event/decision log
        checksum must consume this helper (or an equivalent inline
        ``sorted(self._agents)`` walk) instead of a bare ``.values()``
        iteration, so the checksum never depends on ``dict`` insertion order.
        Live wall-clock cognition (``_on_cognition_tick``/``asyncio.gather``)
        is out of scope — it is inherently non-deterministic and untouched
        here (§M4.3 point 4, record-mode sequencing lands in society.py).
        """
        return [self._agents[agent_id] for agent_id in sorted(self._agents)]

    async def _on_physics_tick(self) -> None:
        dt = self._physics_dt
        for rt in self._sorted_runtimes():
            # Capture the zone BEFORE model_copy overwrites it; otherwise the
            # emitted ZoneTransitionEvent's from_zone would equal to_zone.
            prev_zone = rt.state.position.zone
            new_pos, zone_changed = step_kinematics(rt.kinematics, dt)
            if new_pos != rt.state.position:
                rt.state = rt.state.model_copy(update={"position": new_pos})
            if zone_changed is not None:
                rt.pending.append(
                    ZoneTransitionEvent(
                        tick=rt.state.tick,
                        agent_id=rt.agent_id,
                        from_zone=prev_zone,
                        to_zone=zone_changed,
                    ),
                )
        # ECL v0 (Issue 003): emit this physics tick's embodiment trace immediately
        # AFTER step_kinematics (design §論点3), in deterministic ``sorted(agent_id)``
        # order, then advance the 30 Hz physics-tick index. No-op when unset (live /
        # flag-off) so the hot path stays byte-invariant. Fires before the multi-agent
        # separation nudge below — v0 is single-agent so separation never fires; a
        # superseding ADR that lets separation move a live ECL agent would move this
        # call after ``_apply_separation_force`` to record the settled coordinate.
        self._emit_ecl_trace()
        self._physics_tick_index += 1
        # M7ζ-3: pair separation nudge — runs after step_kinematics so it
        # corrects any pair whose Python orchestrator routed them to
        # near-identical waypoints before the proximity-event detector
        # samples distances. Order matters: separation must precede
        # ``_fire_proximity_events`` so the latter sees the post-nudge
        # geometry and reports stable enter/leave crossings instead of
        # oscillating around the threshold every tick.
        if len(self._agents) >= 2:  # noqa: PLR2004 — "pair" is inherently 2
            self._apply_separation_force()
        # M6-A-2b: time-of-day cascade — emit a TemporalEvent for every
        # registered agent when the simulated clock crosses a period
        # boundary. No-agent ticks are hot-pathed so ``_time_start`` stays
        # None until at least one agent is registered; when agents appear
        # later their first tick sees elapsed near zero.
        if self._agents:
            self._fire_temporal_events()
        # M6-A-2b: agent-pair proximity crossings. Requires at least two
        # agents and the kinematic positions just advanced above, so this
        # runs AFTER the move loop in the same tick. Single-agent worlds
        # hot-path: no pairs, nothing to do.
        if len(self._agents) >= 2:  # noqa: PLR2004 — "pair" is inherently 2
            self._fire_proximity_events()
        # M7 B1: agent-prop affordance entries. Also needs the kinematic
        # positions just advanced above. Runs with any non-empty agent set —
        # a lone agent still notices props. Props are loaded from the static
        # ZONE_PROPS table so the loop cost is bounded by the MVP fixture
        # (two chashitsu tea bowls in the initial scope).
        if self._agents:
            self._fire_affordance_events()

    def _emit_ecl_trace(self) -> None:
        """Emit this physics tick's embodiment trace via the flag-on sink (Issue 003).

        No-op when ``_ecl_trace_sink`` is ``None`` (flag-off / live runs), so the live
        physics hot path stays byte-invariant. When wired, fires once per registered
        agent in deterministic ``sorted(agent_id)`` order (so the downstream
        ``order_slot`` is a stable function of the id set, not the ``dict`` insertion /
        ``asyncio.gather`` order — design §論点3, Codex MEDIUM-3), passing pure
        ``schemas`` primitives plus the current ``physics_tick_index``. The sink never
        learns ``run_id`` / ``agent_tick`` / ``order_slot`` — the integration closure
        binds those (house-style, mirroring ``_emit_individual_trace``), so ``world``
        gains no ``integration`` / ``evidence`` import.
        """
        sink = self._ecl_trace_sink
        if sink is None:
            return
        idx = self._physics_tick_index
        for agent_id in sorted(self._agents):
            pos = self._agents[agent_id].state.position
            sink(agent_id, idx, pos.x, pos.y, pos.z, pos.yaw, pos.pitch, pos.zone)

    def _apply_separation_force(self) -> None:
        """Nudge agent pairs apart on the XZ plane when distance < radius.

        For each unordered pair, the threshold is the *larger* of the two
        personas' ``separation_radius_m`` so a tight-bubble persona (e.g.
        Rikyū's 1.2 m) does not block a wider-bubble peer (Kant 1.5 m)
        from claiming personal space. When inside the radius both agents
        receive a fixed :data:`_SEP_PUSH_M` push along the unit vector
        between them; identical positions (``d == 0``) deterministically
        fall back to ``(1, 0)`` so the test outcome is reproducible.

        :class:`Kinematics` is kept in sync with :class:`Position` so the
        next physics tick's ``step_kinematics`` integrates from the
        post-nudge coordinate; the persisted ``AgentState`` carries the
        same coordinate so the Godot ``agent_update`` envelope reflects
        it without any wire-side change.

        Complexity is ``O(n*(n-1)/2)`` over registered agents — fine for
        the 3-agent MVP scale; revisit if MASTER-PLAN scales agent count.
        """
        for rt_a, rt_b in combinations(self._sorted_runtimes(), 2):
            radius = max(
                rt_a.persona.behavior_profile.separation_radius_m,
                rt_b.persona.behavior_profile.separation_radius_m,
            )
            if radius == 0.0:
                continue
            dx = rt_a.state.position.x - rt_b.state.position.x
            dz = rt_a.state.position.z - rt_b.state.position.z
            d = math.hypot(dx, dz)
            if d >= radius:
                continue
            if d == 0.0:
                ux, uz = 1.0, 0.0
            else:
                ux, uz = dx / d, dz / d
            for rt, sign in ((rt_a, +1.0), (rt_b, -1.0)):
                new_pos = rt.state.position.model_copy(
                    update={
                        "x": rt.state.position.x + sign * ux * _SEP_PUSH_M,
                        "z": rt.state.position.z + sign * uz * _SEP_PUSH_M,
                    },
                )
                rt.state = rt.state.model_copy(update={"position": new_pos})
                rt.kinematics.position = new_pos

    def _fire_proximity_events(self) -> None:
        """Detect agent-pair distance crossings of :data:`_PROXIMITY_THRESHOLD_M`.

        Distance is computed on the XZ plane to match
        :mod:`erre_sandbox.world.physics` (the Y axis carries avatar height,
        not a meaningful spatial separation). For each unordered pair:

        * First-time observation → cache distance, no event.
        * Crossed from ``>= threshold`` to ``< threshold`` → emit
          ``crossing="enter"`` to both agents.
        * Crossed from ``< threshold`` to ``>= threshold`` → emit
          ``crossing="leave"`` to both agents.
        * Stayed on the same side → cache update only, no event.

        Both sides of a crossing see the same ``distance_prev`` /
        ``distance_now`` values; only ``other_agent_id`` differs. This
        matches the observation stream's perspective-per-agent semantics
        (each agent gets its own view of what just happened to it).
        """
        for rt_a, rt_b in combinations(self._sorted_runtimes(), 2):
            # combinations() over a list pre-sorted by agent_id yields every
            # pair with rt_a.agent_id < rt_b.agent_id — this is the sorted-pair
            # canonical form (§M4.3 Codex HIGH-3): pair orientation never
            # leaks the registration/dict-insertion order into which agent's
            # perspective is appended to ``pending`` first.
            dx = rt_a.state.position.x - rt_b.state.position.x
            dz = rt_a.state.position.z - rt_b.state.position.z
            distance = math.hypot(dx, dz)
            key = frozenset({rt_a.agent_id, rt_b.agent_id})
            prev = self._pair_distances.get(key)
            self._pair_distances[key] = distance
            if prev is None:
                # First observation: no prior tick to compare against.
                continue
            crossed_enter = (
                prev >= _PROXIMITY_THRESHOLD_M and distance < _PROXIMITY_THRESHOLD_M
            )
            crossed_leave = (
                prev < _PROXIMITY_THRESHOLD_M and distance >= _PROXIMITY_THRESHOLD_M
            )
            if not (crossed_enter or crossed_leave):
                continue
            crossing: Literal["enter", "leave"] = "enter" if crossed_enter else "leave"
            tick_a = rt_a.state.tick
            tick_b = rt_b.state.tick
            rt_a.pending.append(
                ProximityEvent(
                    tick=tick_a,
                    agent_id=rt_a.agent_id,
                    other_agent_id=rt_b.agent_id,
                    distance_prev=prev,
                    distance_now=distance,
                    crossing=crossing,
                ),
            )
            rt_b.pending.append(
                ProximityEvent(
                    tick=tick_b,
                    agent_id=rt_b.agent_id,
                    other_agent_id=rt_a.agent_id,
                    distance_prev=prev,
                    distance_now=distance,
                    crossing=crossing,
                ),
            )

    def _fire_affordance_events(self) -> None:
        """Emit :class:`AffordanceEvent` when an agent enters a prop's radius.

        Mirrors the crossing-only semantics of :meth:`_fire_proximity_events`:
        the event fires once when the XZ distance first falls below
        :data:`_AFFORDANCE_RADIUS_M`, then stays silent until the agent has
        moved back out of range and re-entered. This matches ProximityEvent's
        "edge, not level" design so chashitsu visitors do not flood the
        observation stream while sitting next to a tea bowl.

        Iterates every ``(agent, prop)`` pair in the static :data:`ZONE_PROPS`
        table. Bound at MVP scope: three agents × two chashitsu bowls = six
        distance checks per tick.
        """
        for zone, props in ZONE_PROPS.items():
            if not props:
                continue
            for rt in self._sorted_runtimes():
                ax = rt.state.position.x
                az = rt.state.position.z
                for prop in props:
                    dx = ax - prop.x
                    dz = az - prop.z
                    distance = math.hypot(dx, dz)
                    key = (rt.agent_id, prop.prop_id)
                    prev = self._agent_prop_distances.get(key)
                    self._agent_prop_distances[key] = distance
                    if prev is None:
                        # First observation: no prior tick to compare against.
                        # Do not fire on the very first frame the prop is seen,
                        # otherwise every spawn-inside-chashitsu triggers a
                        # spurious entry even when the agent never moved.
                        continue
                    crossed_enter = (
                        prev >= _AFFORDANCE_RADIUS_M and distance < _AFFORDANCE_RADIUS_M
                    )
                    if not crossed_enter:
                        continue
                    rt.pending.append(
                        AffordanceEvent(
                            tick=rt.state.tick,
                            agent_id=rt.agent_id,
                            prop_id=prop.prop_id,
                            prop_kind=prop.prop_kind,
                            zone=zone,
                            distance=distance,
                            salience=prop.salience,
                        ),
                    )

    def _fire_temporal_events(self) -> None:
        """Detect and emit TimeOfDay boundary crossings for all agents."""
        now = self._clock.monotonic()
        if self._time_start is None:
            self._time_start = now
            # Silently sync the initial period to the boot time — no event
            # on first ever tick because there is no prior period to cite.
            self._current_period = _time_of_day(0.0, self._day_duration_s)
            return
        elapsed = now - self._time_start
        new_period = _time_of_day(elapsed, self._day_duration_s)
        if new_period == self._current_period:
            return
        previous = self._current_period
        self._current_period = new_period
        for rt in self._sorted_runtimes():
            rt.pending.append(
                TemporalEvent(
                    tick=rt.state.tick,
                    agent_id=rt.agent_id,
                    period_prev=previous,
                    period_now=new_period,
                ),
            )

    async def _on_cognition_tick(self) -> None:
        if not self._agents:
            return
        # M7ζ-3 phase wheel: the global cognition heap event still fires at
        # ``_cognition_period`` cadence, but only agents whose
        # ``next_cognition_due`` has elapsed (and which are not in
        # post-MoveMsg dwell) actually step this tick. The 1e-6 tolerance
        # absorbs floating-point drift between the global heap due time and
        # the per-agent due time computed from ``cognition_period_s``.
        now = self._clock.monotonic()
        # Evaluate agents list once so that dict mutation during gather
        # (register_agent from inside a handler, if anyone ever does that)
        # cannot desynchronise the result / runtime pairing below.
        runtimes = list(self._agents.values())
        due: list[AgentRuntime] = []
        for rt in runtimes:
            if now < rt.dwell_until:
                continue  # in seiza dwell, skip this cognition tick
            if rt.next_cognition_due <= now + 1e-6:
                due.append(rt)
        if due:
            results = await asyncio.gather(
                *(self._step_one(rt) for rt in due),
                return_exceptions=True,
            )
            for rt, res in zip(due, results, strict=True):
                self._consume_result(rt, res)
                # ``cognition_period_s`` is the *minimum* gap between this
                # agent's cognition steps. ``dwell_until`` (set inside
                # ``_consume_result`` when a MoveMsg fires) layers an
                # *upper* override on top: when ``dwell_time_s >
                # cognition_period_s`` (e.g. Rikyū's 90 s dwell vs 18 s
                # period) dwell wins, when ``dwell_time_s <
                # cognition_period_s`` (e.g. Nietzsche's 5 s dwell vs 7 s
                # period) period still bounds the next step. This is the
                # intended semantics — dwell never speeds an agent up.
                rt.next_cognition_due = (
                    now + rt.persona.behavior_profile.cognition_period_s
                )
        # Dialog scheduler runs every global tick regardless of which agents
        # were due, so persona-driven cognition cadence does not starve
        # proximity-driven dialog initiations.
        self._run_dialog_tick()
        if self._dialog_generator is not None and self._dialog_scheduler is not None:
            await self._drive_dialog_turns(self._current_world_tick())

    def _run_dialog_tick(self) -> None:
        """Evaluate the dialog scheduler after all per-agent cognition ran.

        The scheduler consumes a narrow projection (:class:`AgentView`) of
        each runtime so it cannot reach into kinematics or the pending
        observation buffer. Dialog envelopes are delivered through the
        scheduler's injected sink, which :func:`bootstrap` wires back to
        :meth:`inject_envelope`.
        """
        if self._dialog_scheduler is None:
            return
        views = self._agent_views()
        # The scheduler type is a Protocol frozen in schemas.py §7.5 —
        # ``tick`` is the concrete extension exposed by the default
        # :class:`InMemoryDialogScheduler`. Callers supplying a custom
        # scheduler should either subclass that class or accept that the
        # proximity auto-fire logic is skipped.
        tick_fn = getattr(self._dialog_scheduler, "tick", None)
        if tick_fn is None:
            return
        try:
            tick_fn(self._current_world_tick(), views)
        except Exception:
            # A misbehaving scheduler must not crash the cognition loop.
            logger.exception("dialog scheduler tick raised")

    def _current_world_tick(self) -> int:
        """Return the highest per-agent tick, or 0 when no agents are registered.

        Shared by ``_run_dialog_tick``, ``_drive_dialog_turns``, and
        ``_on_heartbeat_tick`` so the three consumers of "current world
        tick" always see the same value. Cheap enough to recompute each
        call (M4 target N ≤ 10 agents); if agent counts grow we could
        cache and invalidate inside ``_consume_result``.
        """
        return max((rt.state.tick for rt in self._agents.values()), default=0)

    def _agent_views(self) -> Sequence[AgentView]:
        return [
            AgentView(
                agent_id=rt.agent_id,
                zone=rt.state.position.zone,
                tick=rt.state.tick,
            )
            for rt in self._agents.values()
        ]

    async def _drive_dialog_turns(self, world_tick: int) -> None:
        """Walk every open dialog and either generate a turn or close at budget.

        Called only when both :attr:`_dialog_scheduler` and
        :attr:`_dialog_generator` are set. For each open dialog the method
        consults :meth:`InMemoryDialogScheduler.iter_open_dialogs` and:

        1. Picks the next speaker by strict alternation:
           ``turn_index % 2 == 0`` => initiator, else target. Derived from
           ``len(transcript)`` rather than a tracked counter so the scheduler
           remains the single source of truth.
        2. Closes the dialog with ``reason="exhausted"`` when
           ``len(transcript) >= speaker.cognitive.dialog_turn_budget``.
        3. Otherwise dispatches the generator concurrently via
           :func:`asyncio.gather` with ``return_exceptions=True`` so one
           misbehaving pair cannot cancel the siblings. ``None`` return is a
           soft close — the existing timeout path will reap it later. An
           exception logs at ``WARNING`` and leaves the dialog untouched.
        4. On a fresh ``DialogTurnMsg`` it calls
           :meth:`InMemoryDialogScheduler.record_turn` (updates transcript and
           ``last_activity_tick``) and :meth:`inject_envelope` (fan-out to
           the WebSocket consumers). Scheduler ``record_turn`` does not emit
           on its own, so the explicit inject here is load-bearing.

        If a referenced speaker agent is not registered with this runtime
        the dialog is skipped and a warning logged — it means the runtime
        and scheduler have drifted, which is a bug in higher-layer wiring.
        """
        scheduler = self._dialog_scheduler
        generator = self._dialog_generator
        if scheduler is None or generator is None:
            return
        open_dialogs: list[tuple[str, str, str, Zone]] = list(
            scheduler.iter_open_dialogs(),
        )
        if not open_dialogs:
            return

        pending = self._stage_dialog_turns(
            scheduler=scheduler,
            generator=generator,
            open_dialogs=open_dialogs,
            world_tick=world_tick,
        )
        if not pending:
            return
        results = await asyncio.gather(
            *(p.coro for p in pending),
            return_exceptions=True,
        )
        for p, res in zip(pending, results, strict=True):
            if isinstance(res, BaseException):
                logger.warning(
                    "dialog turn generation failed for dialog %s speaker %s: %s",
                    p.dialog_id,
                    p.speaker_id,
                    res,
                )
                continue
            if res is None:
                # Soft close — leave for timeout reaper.
                continue
            if not isinstance(res, DialogTurnMsg):
                logger.warning(
                    "dialog turn generator returned unexpected type %s "
                    "for dialog %s — dropping",
                    type(res).__name__,
                    p.dialog_id,
                )
                continue
            try:
                scheduler.record_turn(res)
            except KeyError:
                # Dialog closed mid-gather (timeout / exhausted / external).
                logger.debug(
                    "dialog %s closed before turn %d could be recorded",
                    p.dialog_id,
                    p.turn_index,
                )
                continue
            self.inject_envelope(res)

    def _stage_dialog_turns(
        self,
        *,
        scheduler: DialogScheduler,
        generator: DialogTurnGenerator,
        open_dialogs: Sequence[tuple[str, str, str, Zone]],
        world_tick: int,
    ) -> list[_PendingTurn]:
        """Decide per-dialog what to do this tick: close, skip, or enqueue.

        Synchronous because every decision (budget / unknown agent / close)
        is local state. Returned pending turns are staged coroutines that
        :meth:`_drive_dialog_turns` then runs under ``asyncio.gather``.
        """
        pending: list[_PendingTurn] = []
        for did, init_id, target_id, _zone in open_dialogs:
            transcript = scheduler.transcript_of(did)
            turn_index = len(transcript)
            speaker_id = init_id if turn_index % 2 == 0 else target_id
            addressee_id = target_id if speaker_id == init_id else init_id
            speaker_rt = self._agents.get(speaker_id)
            addressee_rt = self._agents.get(addressee_id)
            if speaker_rt is None or addressee_rt is None:
                logger.warning(
                    "dialog %s references unregistered agent(s) "
                    "speaker=%s addressee=%s — skipping",
                    did,
                    speaker_id,
                    addressee_id,
                )
                continue
            budget = speaker_rt.state.cognitive.dialog_turn_budget
            if turn_index >= budget:
                try:
                    scheduler.close_dialog(did, reason="exhausted", tick=world_tick)
                except KeyError:
                    # Racy concurrent close (timeout already ran) — ignore.
                    logger.debug("dialog %s already closed before exhaust", did)
                continue
            pending.append(
                _PendingTurn(
                    dialog_id=did,
                    speaker_id=speaker_id,
                    addressee_id=addressee_id,
                    turn_index=turn_index,
                    coro=generator.generate_turn(
                        dialog_id=did,
                        speaker_state=speaker_rt.state,
                        speaker_persona=speaker_rt.persona,
                        addressee_state=addressee_rt.state,
                        transcript=transcript,
                        world_tick=world_tick,
                    ),
                ),
            )
        return pending

    async def _on_heartbeat_tick(self) -> None:
        env = WorldTickMsg(
            tick=self._current_world_tick(),
            active_agents=len(self._agents),
        )
        try:
            self._heartbeat_envelopes.put_nowait(env)
        except asyncio.QueueFull:
            # Coalesce to the latest tick: drop the stale heartbeat and
            # enqueue the new one. Consumers only care about the most
            # recent world tick, so latest-wins is the correct semantics.
            with contextlib.suppress(asyncio.QueueEmpty):
                self._heartbeat_envelopes.get_nowait()
            self._heartbeat_envelopes.put_nowait(env)

    # ----- Cognition helpers -----

    async def _step_one(
        self, rt: AgentRuntime, *, self_other_context: str | None = None
    ) -> CycleResult:
        # Exceptions raised by the cycle are NOT caught here; the caller is
        # ``asyncio.gather(..., return_exceptions=True)`` which turns them
        # into result-list entries so one agent's failure cannot cancel its
        # siblings. Adding a try/except here would duplicate that contract
        # and confuse future maintainers.
        #
        # ``self_other_context`` (M2 Layer2 mirror-sim, keyword-only, default
        # ``None``): the live phase-wheel (``_on_cognition_tick``) never passes
        # it, so its call stays byte-identical; only the record-mode society
        # driver threads a pre-rendered SimToM segment through
        # :meth:`step_cognition_once`. Transient prompt-context only — it does
        # not touch ``rt.pending`` / memory (design-final.md §L6).
        obs: list[Observation] = rt.pending
        rt.pending = []
        return await self._cycle.step(
            rt.state,
            rt.persona,
            obs,
            tick_seconds=self._cognition_period,
            world_model_runtime=rt.world_model_runtime,
            development_state=rt.development_state,
            self_other_context=self_other_context,
        )

    async def step_cognition_once(
        self, agent_id: str, *, self_other_context: str | None = None
    ) -> CycleResult:
        """Deterministically step exactly one agent's cognition (record-mode seam).

        Public-ish seam (design-final.md §M4.1, DA-M2IMPL-3, Codex MEDIUM-6):
        a record-mode sequential driver (``integration.embodied.society``)
        needs a supported way to step one named agent's cognition without
        going through the live phase-wheel's due-time / dwell gating and
        ``asyncio.gather`` fan-out (:meth:`_on_cognition_tick`). This method
        calls the same ``_step_one``/``_consume_result`` pair the phase-wheel
        calls per due agent — unconditionally, with no dwell/due-time check —
        so a record-mode caller that wants every agent to step every window
        (mirroring ``run_ecl_loop``'s single-agent private direct-drive
        precedent, ``loop.py`` L624-625) gets a public, non-underscore-prefixed
        contract instead of reaching into ``_step_one``/``_consume_result``
        directly. ``_on_cognition_tick`` (the live wall-clock phase-wheel) is
        completely unchanged — this method is purely additive and does not
        alter live behaviour or byte determinism of any existing flow.

        Raises ``KeyError`` if ``agent_id`` is not registered (surfaced, not
        swallowed — a caller bug should fail loudly, matching
        :meth:`inject_observation`'s existing contract). Unlike the
        phase-wheel's ``asyncio.gather(..., return_exceptions=True)``, a
        raised cognition-cycle exception here propagates directly to the
        caller (matching ``run_ecl_loop``'s un-caught precedent), since
        record-mode drivers want failures to surface rather than be logged
        and swallowed.

        ``self_other_context`` (M2 Layer2 mirror-sim, keyword-only, default
        ``None``, additive): a record-mode society driver may thread a
        pre-rendered SimToM segment (other agents' prior-window observed
        behaviour) into this one agent's cognition. ``None`` — every existing
        caller — keeps the step byte-identical. The segment is injected into the
        user prompt only and never written to episodic memory (design-final.md
        §L6 disjointness). NOT a structural-floor verdict; verdict は holding.
        """
        rt = self._agents[agent_id]
        result = await self._step_one(rt, self_other_context=self_other_context)
        self._consume_result(rt, result)
        return result

    def _consume_result(
        self,
        rt: AgentRuntime,
        res: CycleResult | BaseException,
    ) -> None:
        if isinstance(res, BaseException):
            logger.exception(
                "agent %s step raised",
                rt.agent_id,
                exc_info=res,
            )
            return
        rt.state = res.agent_state
        rt.kinematics.position = res.agent_state.position
        # M10-C: persist the carried world-model state (flag-on only; ``None``
        # flag-off leaves the field untouched at its ``None`` default). On a
        # flag-on outage this is the pre-LLM reconciled state, so a transient
        # failure does not wipe accumulated modulations (DA-M10C-6/7).
        if res.world_model_runtime is not None:
            rt.world_model_runtime = res.world_model_runtime
        # M11-A: persist the diagnostic narrative arc (flag-on only). ``None``
        # leaves the field untouched so the last successfully-synthesised arc
        # carries forward across silent / outage ticks (DA-M11A-7), mirroring the
        # world_model_runtime write-back above.
        if res.narrative_arc is not None:
            rt.narrative_arc = res.narrative_arc
        # M11-B: persist the evidence-driven development stage (flag-on only).
        # ``None`` (flag-off / silent / outage tick) leaves the prior stage
        # untouched so it carries forward, mirroring the write-backs above.
        if res.development_state is not None:
            rt.development_state = res.development_state
        # M11-C2: emit this tick's individual-state trace (flag-on only). Extracted
        # to keep _consume_result's branch count bounded (C901); the helper no-ops
        # when the sink is unset (flag-off / live runs).
        self._emit_individual_trace(rt, res)
        # Saturation probe (ADR section 5): emit this tick's per-channel saturation
        # trace (flag-on only). Same no-op-when-unset contract as the individual
        # trace; uses the post-reconcile pre-nudge snapshot carried on the result.
        self._emit_saturation_trace(rt, res)
        # Engagement instrument (ADR §5): emit this tick's hint-disposition trace
        # (flag-on only). Same no-op-when-unset contract; uses the disposition carrier
        # carried on the result (contracts read-model, no cognition/evidence import).
        self._emit_hint_engagement_trace(rt, res)
        # U5 replay infra: emit this tick's reconcile-input floor trace (flag-on only).
        # Same no-op-when-unset contract; uses the **same** post-reconcile pre-nudge
        # snapshot as the saturation trace, but persists the full ``base_floor`` so a
        # deterministic replay can re-feed it into the unchanged reconcile kernel.
        self._emit_floor_input_trace(rt, res)
        # Bond-affinity trace (instrumentation ADR section 3.3, carrier A): emit this
        # tick's per-dyad bond affinity / interaction-count trace (flag-on only). Same
        # no-op-when-unset contract; reads ``res.agent_state.relationships`` (the bonds
        # ``world`` already persisted above), so no new carrier and no evidence import.
        self._emit_bond_affinity_trace(rt, res)
        # M6-A-2b: observations detected post-LLM (stress crossings) are
        # surfaced one tick late — append them to ``pending`` so the next
        # cognition tick sees the signal. Empty for agents whose stress
        # stayed on one side of the mid-band, which is the common case.
        if res.follow_up_observations:
            rt.pending.extend(res.follow_up_observations)
        for env in res.envelopes:
            if isinstance(env, MoveMsg):
                # Resolve a "zone-only" MoveMsg (coords unchanged from current
                # position, only zone field differs) to the target zone's spawn
                # point. CognitionCycle._build_envelopes emits this shape when
                # the LLM returns a destination_zone, relying on the world
                # layer to map semantic zone -> physical coordinates. Without
                # this resolution, step_kinematics would see dest == position,
                # mark "arrived immediately", and never cross a zone boundary
                # -> pending observations stay empty -> episodic_memory never
                # populates (GAP-1 blocker for MASTER-PLAN §4.4 #3).
                tgt = env.target
                if locate_zone(tgt.x, tgt.y, tgt.z) is not tgt.zone:
                    resolved = default_spawn(tgt.zone).model_copy(
                        update={"yaw": tgt.yaw, "pitch": tgt.pitch},
                    )
                    env = env.model_copy(update={"target": resolved})  # noqa: PLW2901 — intentional re-bind to propagate the zone-resolved target to both apply_move_command and the downstream queue
                apply_move_command(rt.kinematics, env)
                # M7ζ-3: arm seiza-style dwell so the persona's cognition is
                # suppressed for ``dwell_time_s`` before the phase wheel
                # resumes. dwell_time_s == 0.0 (the default) makes this a
                # no-op, so personas without a dwell tuning are unaffected.
                dwell = rt.persona.behavior_profile.dwell_time_s
                if dwell > 0.0:
                    rt.dwell_until = self._clock.monotonic() + dwell
            self._enqueue_with_drop_oldest(env)

    def _emit_individual_trace(self, rt: AgentRuntime, res: CycleResult) -> None:
        """Emit this tick's individual-state trace via the flag-on sink (M11-C2).

        No-op when ``_individual_trace_sink`` is ``None`` (flag-off / live runs),
        so snapshot_profile() is never built and the substrate stays empty — the
        flag-off byte-invariant carries C1's snapshot into C2's substrate
        (DA-M11C2-1). Built from the single-source AgentRuntime snapshot *after*
        ``_consume_result``'s write-backs, so development_stage / coherence /
        arc_segment_count reflect the carried state; ``belief_classes`` and
        ``world_model_evidence`` (M10-A 段B H2 substrate) ride in on the result so
        ``world`` never reads ``memory`` (DA-M11C2-2 / DA-SB-1). The orchestrator's
        sink closure owns the DuckDB-write error semantics (CaptureFatalError),
        mirroring the dialog-turn DuckDB sink — not swallowed.
        """
        if self._individual_trace_sink is None:
            return
        self._individual_trace_sink(
            rt.snapshot_profile(),
            res.belief_classes,
            res.world_model_evidence,
            rt.state.tick,
        )

    def _emit_saturation_trace(self, rt: AgentRuntime, res: CycleResult) -> None:
        """Emit this tick's saturation trace via the flag-on sink (ADR section 5).

        No-op when ``_saturation_trace_sink`` is ``None`` (flag-off / live runs), so
        the new trace table is never written and the flag-off DuckDB stays
        byte-identical. ``res.world_model_saturation`` is the post-reconcile
        pre-nudge ``WorldModelSnapshot`` (ADR section 2.1) carried off the result so
        ``world`` never imports cognition; ``None`` on a flag-off tick (defensive —
        the sink is already ``None`` there) so this no-ops then too. ``rt.state.tick``
        is the same post-step tick label the individual trace records, keeping the
        two traces joinable (DA-IMPL-4). The orchestrator's sink closure owns the
        DuckDB-write error semantics (CaptureFatalError), mirroring the dialog-turn
        sink — not swallowed.
        """
        if self._saturation_trace_sink is None:
            return
        snapshot = res.world_model_saturation
        if snapshot is None:
            return
        self._saturation_trace_sink(rt.agent_id, snapshot, rt.state.tick)

    def _emit_hint_engagement_trace(self, rt: AgentRuntime, res: CycleResult) -> None:
        """Emit this tick's hint-engagement trace via the flag-on sink (ADR §5).

        No-op when ``_hint_engagement_trace_sink`` is ``None`` (flag-off / live runs),
        so the new trace table is never written and the flag-off DuckDB stays
        byte-identical. ``res.world_model_hint_engagement`` is the
        :class:`WorldModelHintDisposition` carried off the result (a ``contracts``
        read-model), so the sink adds no ``evidence`` import and no ``cognition``
        dependency beyond the ``CycleResult`` ``world`` already consumes (it never
        touches the classifier); ``None`` on a flag-off tick (defensive — the sink is
        already ``None`` there) so this no-ops then too. ``rt.state.tick`` is the same
        post-step tick label the saturation / individual traces record, keeping them
        joinable. The orchestrator's sink closure owns the DuckDB-write error semantics
        (CaptureFatalError), mirroring the saturation sink — not swallowed.
        """
        if self._hint_engagement_trace_sink is None:
            return
        disposition = res.world_model_hint_engagement
        if disposition is None:
            return
        self._hint_engagement_trace_sink(rt.agent_id, disposition, rt.state.tick)

    def _emit_floor_input_trace(self, rt: AgentRuntime, res: CycleResult) -> None:
        """Emit this tick's reconcile-input floor trace via the flag-on sink (U5).

        No-op when ``_floor_input_trace_sink`` is ``None`` (flag-off / live runs), so
        the new trace table is never written and the flag-off DuckDB stays
        byte-identical.
        Reads the **same** ``res.world_model_saturation`` carrier the saturation sink
        uses (the post-reconcile pre-nudge ``WorldModelSnapshot``), so ``world`` imports
        neither ``evidence`` nor ``cognition``; the orchestrator's closure persists the
        full ``snapshot.base_floor`` (the lossy saturation trace cannot drive a faithful
        replay). ``None`` on a flag-off tick (defensive — the sink is already ``None``
        there) so this no-ops then too. ``rt.state.tick`` is the same post-step tick
        label the saturation / hint / individual traces record, keeping them joinable.
        The orchestrator's sink closure owns the DuckDB-write error semantics
        (CaptureFatalError), mirroring the saturation sink — not swallowed.
        """
        if self._floor_input_trace_sink is None:
            return
        snapshot = res.world_model_saturation
        if snapshot is None:
            return
        self._floor_input_trace_sink(rt.agent_id, snapshot, rt.state.tick)

    def _emit_bond_affinity_trace(self, rt: AgentRuntime, res: CycleResult) -> None:
        """Emit this tick's bond-affinity trace via the flag-on sink (ADR section 3.3).

        No-op when ``_bond_affinity_trace_sink`` is ``None`` (flag-off / live runs), so
        the new trace table is never written and the flag-off DuckDB stays
        byte-identical. Reads ``res.agent_state.relationships`` — the agent's
        ``list[RelationshipBond]`` ``world`` has just persisted to ``rt.state``; these
        are ``schemas`` types ``world`` already uses, so passing them straight through
        adds no ``evidence`` / ``cognition`` import (the orchestrator's closure builds
        the rows, ADR section 3.2-7). ``rt.state.tick`` is the same post-step tick label
        the saturation / floor / hint / individual traces record, keeping them joinable
        on ``(individual, tick)`` for the cap-exposure join. The orchestrator's sink
        closure owns the DuckDB-write error semantics (CaptureFatalError), mirroring the
        saturation sink — not swallowed.
        """
        if self._bond_affinity_trace_sink is None:
            return
        self._bond_affinity_trace_sink(
            rt.agent_id, res.agent_state.relationships, rt.state.tick
        )

    # ----- Scheduling helper -----

    def _schedule(
        self,
        due_at: float,
        period: float,
        handler: Callable[[], Awaitable[None]],
        *,
        name: str,
    ) -> None:
        self._seq += 1
        heapq.heappush(
            self._events,
            ScheduledEvent(
                due_at=due_at,
                seq=self._seq,
                period=period,
                handler=handler,
                name=name,
            ),
        )
