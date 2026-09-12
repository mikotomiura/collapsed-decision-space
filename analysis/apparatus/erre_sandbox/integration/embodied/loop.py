"""ECL v0 integration determinism harness — Issue 004 (design-final.md §論点3).

A **pure record/replay harness** that drives the Embodied Cognition Loop v0 live
seam (Issue 003) *without modifying it*: ``cognition/cycle.py`` and
``world/tick.py`` are imported and driven, never touched. The harness owns only
the integration-layer glue the seam deliberately does not:

* a **record/replay LLM adapter** (:class:`RecordReplayChatClient`) — Plane 2 of
  the two-plane determinism model. In *record* mode it wraps an inner chat client,
  captures every action-LLM call (system/user prompt + final sampling + raw
  response), and returns it verbatim. In *replay* mode it injects the recorded
  responses in order and **never calls any LLM** — the closed set of LLM
  non-determinism for v0 (reflection is disabled by the seam, so the action call
  is the sole Plane 2 entry).
* an **EclRecordMode driver** — constructs the frozen determinism handles
  (:class:`~erre_sandbox.cognition.embodiment.EclRecordMode`) that pin Plane 1
  (fixed retrieval clock / tick-derived memory id·ts / named RNG substream) and
  injects them into an otherwise-live :class:`~erre_sandbox.cognition.CognitionCycle`
  and :class:`~erre_sandbox.world.WorldRuntime`, then steps the two-axis loop
  (cognition ``agent_tick`` + 30 Hz ``physics_tick_index``) for one agent.
* an **``ecl_trace_sink`` closure** — binds ``run_id`` / ``agent_tick`` /
  ``order_slot`` onto the pure ``schemas`` primitives the world seam emits
  (house-style, so ``world`` never imports ``integration``) and assembles each
  physics-tick :class:`EclTraceRow`, joining in the cognition tick's move-decision
  provenance (:class:`~erre_sandbox.cognition.embodiment.EclDestination`) on the
  ``agent_tick`` axis.
* a replay checksum (:func:`ecl_trace_checksum`, SHA-256, design-copied from
  ``evidence.d0_substrate.stub.trace_checksum`` — copied, *not* imported).

Scope guard (design-final.md §論点3/§論点4, binding). This harness is a
*construction* apparatus, **NOT a measurement line — verdict は holding**. It
imports no ``evidence`` / ``spdm`` / ``runningness`` machinery and computes/emits
no floor / landscape / verdict statistic. ``ecl_trace_checksum`` proves
reproducibility (a re-run reproduces the trace byte-for-byte); it is not a metric.
Measurement-line re-entry stays behind the scoping §4.2 costed superseding-ADR
gate.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from random import Random
from typing import TYPE_CHECKING, Any, Final, Literal, cast

from erre_sandbox.cognition import (
    BiasFiredEvent,
    CognitionCycle,
    LLMPlan,
    parse_llm_plan,
)
from erre_sandbox.cognition.embodiment import (
    K_ECL,
    EclDestination,
    EclRecordMode,
)
from erre_sandbox.inference import OllamaUnavailableError
from erre_sandbox.memory import EmbeddingClient, MemoryStore, Retriever
from erre_sandbox.schemas import (
    SCHEMA_VERSION,
    PerceptionEvent,
    Zone,
)
from erre_sandbox.world import ManualClock, WorldRuntime

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence
    from datetime import datetime

    from erre_sandbox.cognition import CycleResult
    from erre_sandbox.cognition.reflection import Reflector
    from erre_sandbox.inference.ollama_adapter import ChatMessage, ChatResponse
    from erre_sandbox.inference.sampling import ResolvedSampling
    from erre_sandbox.schemas import AgentState, Observation, PersonaSpec

GOLDEN_COGNITION_TICKS: Final[int] = 8
"""Cognition ticks (``agent_tick`` axis) driven per golden run (grill G-5).

One agent × 8 ticks: enough for continuous transit (tick > 1) and a
history-dependent centroid (memories accumulate so the forage centroid diverges
from ``default_spawn``), and minimal as a committed fixture. The committed golden
fixture itself is baked in Issue 005; here N=8 only proves in-memory
reproducibility (two runs → identical :func:`ecl_trace_checksum`)."""

DEFAULT_PHYSICS_TICKS_PER_COGNITION: Final[int] = 20
"""Physics ticks (30 Hz) driven per cognition window.

At 1.3 m/s and dt = 1/30 s the agent advances ~0.9 m per window — well short of a
zone traversal, so the agent is *always* in transit across the whole run (the
continuous-transit demonstration) rather than snapping to a destination and
stalling. Any fixed value yields a deterministic trace; this one keeps the row
count small while the motion stays visible."""


# --------------------------------------------------------------------------- #
# Plane 2 — record/replay LLM adapter (the sole LLM non-determinism in v0)
# --------------------------------------------------------------------------- #


@dataclass(frozen=True, slots=True)
class RecordedLlmCall:
    """One captured action-LLM call — the Plane 2 replay unit (design §論点3).

    ``system_prompt`` / ``user_prompt`` are the exact messages the cognition cycle
    handed the client; ``sampling`` is the final resolved sampling; ``response``
    is the raw :class:`~erre_sandbox.inference.ollama_adapter.ChatResponse` whose
    ``content`` is re-injected verbatim on replay (the cycle re-parses it and
    re-applies its deterministic RNG, so the post-processed plan is reconstructed
    rather than stored as the replay key).

    ``outcome`` tags the call as an **outcome-tagged union** so the harness
    reproduces LLM *failures* deterministically, not just successes (Codex HIGH-2,
    B-2):

    * ``ok`` — the inner LLM returned content (``response`` present). Replay
      re-injects ``response.content``; the cycle re-parses it (a well-formed plan
      → move, an unparseable one → the same fallback the record run took).
    * ``unparseable`` — a valid downstream state (the cycle's ``parse_llm_plan``
      returned ``None``); recorded like ``ok`` (content present) because replay
      reproduces the fallback by re-parsing the same content, not by a flag.
    * ``raised`` — the inner LLM raised ``OllamaUnavailableError``. ``response`` is
      ``None`` (response-less); replay **re-raises** the same exception so the
      cognition fallback fires exactly as it did on record.
    """

    system_prompt: str
    user_prompt: str
    sampling: ResolvedSampling
    response: ChatResponse | None = None
    outcome: Literal["ok", "unparseable", "raised"] = "ok"
    """The recorded call's outcome tag.

    ``unparseable`` is a forward-extension value: the current record path
    (:meth:`RecordReplayChatClient.chat`) only ever sets ``ok`` (content
    returned) or ``raised`` (``OllamaUnavailableError``). An unparseable plan is
    *not* tagged here — it is recorded as ``ok`` (content present) and the
    unparseable determination is made downstream in ``_build_decision`` via
    ``llm_status``, which re-parses the same content on replay (CR-L2)."""

    @property
    def raw_response(self) -> str:
        """The raw assistant text — the exact string re-injected on replay.

        ``""`` for a ``raised`` call (response-less); the driver processes
        ``raised`` before ever parsing this, so the empty string is never fed to
        ``parse_llm_plan``.
        """
        return self.response.content if self.response is not None else ""


class EclReplayError(RuntimeError):
    """Replay stream is exhausted or a record-mode client has no inner backend."""


class RecordReplayChatClient:
    """Duck-typed chat client that records live calls or replays recorded ones.

    Structurally matches the keyword surface of
    :class:`~erre_sandbox.inference.ollama_adapter.OllamaChatClient.chat` that
    :class:`~erre_sandbox.cognition.CognitionCycle` calls, so it can stand in for
    the real client without the cycle importing this class.

    * **Record** — ``inner`` set, ``recorded=None``: each ``chat`` delegates to the
      inner client once, captures the call, and returns the real response.
    * **Replay** — ``recorded`` set, ``inner=None``: each ``chat`` returns the next
      recorded response in order and **never touches an LLM** (``inner_invocations``
      stays 0 — the AC4 witness).
    """

    def __init__(
        self,
        *,
        inner: Any | None = None,
        recorded: Sequence[RecordedLlmCall] | None = None,
    ) -> None:
        self._inner = inner
        self._replay: list[RecordedLlmCall] | None = (
            list(recorded) if recorded is not None else None
        )
        self._used: list[RecordedLlmCall] = []
        self._replay_index = 0
        self._inner_invocations = 0

    @property
    def is_replay(self) -> bool:
        """``True`` in replay mode (recorded responses injected, no LLM called)."""
        return self._replay is not None

    @property
    def used(self) -> tuple[RecordedLlmCall, ...]:
        """The calls actually served, in order — one per cognition tick.

        Uniform across modes: the captured calls in record mode, the injected
        calls in replay mode, so the driver correlates ``used[t]`` with cognition
        tick ``t`` either way.
        """
        return tuple(self._used)

    @property
    def inner_invocations(self) -> int:
        """How many times a real (inner) LLM was called — 0 in replay mode (AC4)."""
        return self._inner_invocations

    async def chat(
        self,
        messages: Sequence[ChatMessage],
        *,
        sampling: ResolvedSampling,
        model: str | None = None,
        options: dict[str, Any] | None = None,
        think: bool | None = None,
    ) -> ChatResponse:
        system_prompt = next((m.content for m in messages if m.role == "system"), "")
        user_prompt = next((m.content for m in messages if m.role == "user"), "")
        if self._replay is not None:
            if self._replay_index >= len(self._replay):
                msg = (
                    f"ECL replay exhausted after {self._replay_index} calls; "
                    "the recorded Plane 2 is shorter than the replay run's demand"
                )
                raise EclReplayError(msg)
            call = self._replay[self._replay_index]
            # Advance the stream (index + ``_used``) BEFORE any re-raise so a
            # ``raised`` call still leaves the replay stream tick-aligned for the
            # next tick (Codex M-2): the driver correlates a tick with the calls
            # served in [before, after), so the raised call must be recorded as
            # served even though it re-raises.
            self._replay_index += 1
            self._used.append(call)
            if call.outcome == "raised":
                raise OllamaUnavailableError(
                    "ECL replay: re-raising the recorded OllamaUnavailableError "
                    "so the cognition fallback fires as it did on record"
                )
            # ``ok`` / ``unparseable``: re-inject the recorded content; the cycle
            # re-parses it and reconstructs the same decision (move or fallback).
            if call.response is None:  # pragma: no cover — schema invariant
                msg = (
                    "ECL replay: non-raised recorded call has no response — "
                    "the recorded Plane 2 is malformed"
                )
                raise EclReplayError(msg)
            return call.response
        if self._inner is None:
            msg = "record-mode RecordReplayChatClient needs an inner chat client"
            raise EclReplayError(msg)
        self._inner_invocations += 1
        try:
            response = await self._inner.chat(
                messages,
                sampling=sampling,
                model=model,
                options=options,
                think=think,
            )
        except OllamaUnavailableError:
            # Record the failure as a ``raised`` (response-less) call and keep
            # ``_used`` tick-aligned, THEN re-raise so the cognition cycle takes
            # its fallback branch (design §3.2 / Codex HIGH-1). Replaying this
            # call re-raises the same exception and reproduces the fallback.
            self._used.append(
                RecordedLlmCall(
                    system_prompt=system_prompt,
                    user_prompt=user_prompt,
                    sampling=sampling,
                    response=None,
                    outcome="raised",
                )
            )
            raise
        call = RecordedLlmCall(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            sampling=sampling,
            response=response,
            outcome="ok",
        )
        self._used.append(call)
        return response


# --------------------------------------------------------------------------- #
# Plane 2 — per-cognition-tick decision record (full LLM provenance)
# --------------------------------------------------------------------------- #


@dataclass(frozen=True, slots=True)
class EclDecisionRecord:
    """One cognition tick's Plane 2 record — full action-LLM provenance (§論点3).

    Carries the closed record set: the post-processed full :class:`LLMPlan`
    (re-parsed from the raw response), the schema version, the fallback status,
    the ``_bias_target_zone`` resample event (``None`` when it did not fire), the
    move-decision provenance (:class:`EclDestination`), the emitted envelope
    provenance, and the underlying :class:`RecordedLlmCall` (prompt / sampling /
    raw response). Replaying ``[d.call for d in decisions]`` reconstructs the run
    with no fresh LLM — the AC4 completeness witness.
    """

    agent_tick: int
    call: RecordedLlmCall
    plan: LLMPlan | None
    plan_schema_version: str
    llm_fell_back: bool
    llm_status: str
    bias_fired: BiasFiredEvent | None
    move_decision: EclDestination | None
    envelope_provenance: tuple[str, ...]


# --------------------------------------------------------------------------- #
# Trace row + replay checksum (frozen design-copy of stub.TraceRow / trace_checksum)
# --------------------------------------------------------------------------- #


@dataclass(frozen=True, slots=True)
class EclTraceRow:
    """One physics tick of one agent's embodiment trace, with move provenance.

    Kinematic fields (``x``/``y``/``z``/``yaw``/``pitch``/``zone``) come from the
    world seam's ``ecl_trace_sink`` primitives; the axis fields the closure binds
    (``run_id`` / ``agent_tick`` / ``order_slot``, distinct from the 30 Hz
    ``physics_tick_index``) satisfy AC3's forward-compatible log slots. The
    ``move_*`` fields join in the driving cognition tick's
    :class:`EclDestination` candidate-selection trail (``None`` on a window whose
    plan did not move), so the trace records the frozen transform's *inputs* —
    never an absolute-target replay — and the continuity gate's causal ablation
    actually bites (design §論点4). Design-copied from
    ``evidence.d0_substrate.stub.TraceRow`` (copied, not imported).
    """

    run_id: str
    agent_id: str
    physics_tick_index: int
    agent_tick: int
    order_slot: int
    x: float
    y: float
    z: float
    yaw: float
    pitch: float
    zone: Zone
    resolved_from: str | None
    move_centroid: tuple[float, float] | None
    move_provenance: tuple[str, ...] | None
    move_jitter: tuple[float, float] | None
    move_pre_clamp: tuple[float, float] | None
    move_post_clamp: tuple[float, float] | None
    move_clamp_fired: bool | None


# The 6-decimal float quantisation ``handoff.CANONICAL_FLOAT_DECIMALS`` advertises.
# Inlined (not imported) because ``handoff`` imports ``loop`` — sharing a helper
# would create an import cycle; ``test_ecl_trace_checksum_canonical_rules`` pins
# that this value matches ``handoff.CANONICAL_JSON_RULES`` so it cannot drift.
_TRACE_FLOAT_DECIMALS: Final[int] = 6


def _q(value: float) -> float:
    """Quantise one float to :data:`_TRACE_FLOAT_DECIMALS` decimals (platform-safe)."""
    return round(value, _TRACE_FLOAT_DECIMALS)


def _pair_or_none(value: tuple[float, float] | None) -> list[float] | None:
    return [_q(value[0]), _q(value[1])] if value is not None else None


def ecl_trace_checksum(rows: Sequence[EclTraceRow]) -> str:
    """SHA-256 over the canonical-serialised trace — the replay checksum (§論点3).

    Design-copied from ``evidence.d0_substrate.stub.trace_checksum`` (copied, not
    imported): a stable JSON projection so a byte-identical re-run yields a
    byte-identical digest. This proves *reproducibility*; it is not a metric,
    floor, or verdict (measurement-line non-re-entry, design §論点4).

    The ``json.dumps`` canonicalisation matches ``handoff.CANONICAL_JSON_RULES``
    exactly (``sort_keys=True`` + compact ``separators`` + ``ensure_ascii=False`` +
    ``allow_nan=False`` + 6-decimal float quantisation) so a consumer recomputing
    the digest under the advertised rules gets the same bytes (Codex MEDIUM-1).
    Every float in the projection is rounded to 6 decimals (``_q``) — the same
    quantisation ``handoff.canonical_dumps`` applies via ``_quantize_floats`` —
    which absorbs the sub-ULP cross-platform ``libm`` drift (frozen ``disc_jitter``
    ``cos``/``sin``, max abs 8.88e-16) that would otherwise diverge the golden
    checksum between Windows (UCRT) and Linux (glibc/CI). ``handoff.canonical_dumps``
    is not imported: ``handoff`` imports ``loop``, so the rules are inlined here to
    avoid the cycle, and ``test_ecl_trace_checksum_canonical_rules`` pins that the
    two inlined copies produce identical digests so they cannot drift (CR-M2). A
    non-finite float raises (``allow_nan=False``) — a Stop condition, not a
    silently-hashed value (design §論点3).
    """
    canonical = [
        {
            "run_id": r.run_id,
            "agent_id": r.agent_id,
            "physics_tick_index": r.physics_tick_index,
            "agent_tick": r.agent_tick,
            "order_slot": r.order_slot,
            "x": _q(r.x),
            "y": _q(r.y),
            "z": _q(r.z),
            "yaw": _q(r.yaw),
            "pitch": _q(r.pitch),
            "zone": r.zone.value,
            "resolved_from": r.resolved_from,
            "move_centroid": _pair_or_none(r.move_centroid),
            "move_provenance": (
                list(r.move_provenance) if r.move_provenance is not None else None
            ),
            "move_jitter": _pair_or_none(r.move_jitter),
            "move_pre_clamp": _pair_or_none(r.move_pre_clamp),
            "move_post_clamp": _pair_or_none(r.move_post_clamp),
            "move_clamp_fired": r.move_clamp_fired,
        }
        for r in rows
    ]
    blob = json.dumps(
        canonical,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()


# --------------------------------------------------------------------------- #
# Run result
# --------------------------------------------------------------------------- #


@dataclass(frozen=True, slots=True)
class EclRunResult:
    """Outcome of one :func:`run_ecl_loop` drive."""

    run_id: str
    rows: tuple[EclTraceRow, ...]
    decisions: tuple[EclDecisionRecord, ...]
    checksum: str

    def replay_calls(self) -> tuple[RecordedLlmCall, ...]:
        """The recorded Plane 2 to seed a replay run (AC4: ``decisions`` alone)."""
        return tuple(d.call for d in self.decisions)


def replay_client_from(result: EclRunResult) -> RecordReplayChatClient:
    """Build a replay adapter from a prior run's recorded decisions (AC4).

    The replay run driven with this client re-injects the recorded responses and
    never calls an LLM (``inner_invocations == 0``), reconstructing the state — and
    hence the :func:`ecl_trace_checksum` — from the Plane 2 record alone.
    """
    return RecordReplayChatClient(recorded=result.replay_calls())


# --------------------------------------------------------------------------- #
# Driver
# --------------------------------------------------------------------------- #


@dataclass(slots=True)
class _SinkContext:
    """Mutable per-window context the trace-sink closure reads (driver writes)."""

    agent_tick: int = 0
    move: EclDestination | None = None


def _default_observation_factory(
    agent_id: str,
) -> Callable[[int], Sequence[Observation]]:
    """One deterministic perception per tick so located memories accumulate.

    Each cognition tick's observation is written (ECL record mode) as an episodic
    memory *at the agent's current position*; as the agent transits, those
    formation locations spread, so the strength-weighted centroid the resolver
    reads becomes history-dependent (grill G-5).
    """

    def factory(agent_tick: int) -> Sequence[Observation]:
        return [
            PerceptionEvent(
                tick=agent_tick,
                agent_id=agent_id,
                modality="sight",
                source_zone=Zone.STUDY,
                content=f"ecl v0 forage step {agent_tick}",
                intensity=0.4,
            )
        ]

    return factory


async def run_ecl_loop(
    *,
    run_id: str,
    store: MemoryStore,
    embedding: EmbeddingClient,
    llm: RecordReplayChatClient,
    agent_state: AgentState,
    persona: PersonaSpec,
    retrieval_now: datetime,
    base_ts: datetime,
    seed: int = 0,
    n_cognition_ticks: int = GOLDEN_COGNITION_TICKS,
    physics_ticks_per_cognition: int = DEFAULT_PHYSICS_TICKS_PER_COGNITION,
    k_ecl: int = K_ECL,
    reflector: Reflector | None = None,
    observation_factory: Callable[[int], Sequence[Observation]] | None = None,
) -> EclRunResult:
    """Drive the I3 live seam deterministically for one embodied agent.

    Constructs the frozen determinism handles (:class:`EclRecordMode` with a fixed
    ``retrieval_now`` / ``base_ts``, a seeded ``Random`` for the cycle, a
    ``now_factory``-pinned :class:`Retriever`) and a live
    :class:`~erre_sandbox.cognition.CognitionCycle` +
    :class:`~erre_sandbox.world.WorldRuntime` **without modifying either**, then
    steps ``n_cognition_ticks`` cognition ticks — each followed by
    ``physics_ticks_per_cognition`` 30 Hz physics ticks — while an
    ``ecl_trace_sink`` closure assembles the :class:`EclTraceRow` stream. Returns
    the rows, the per-tick :class:`EclDecisionRecord` Plane 2 provenance, and the
    :func:`ecl_trace_checksum`.

    ``llm`` is the record/replay adapter; ``store`` / ``embedding`` are injected so
    the harness never depends on a live Ollama. The single-agent restriction is a
    v0 scope choice (grill G-5); the log slots carry ``order_slot`` for
    forward-compatible multi-agent runs.
    """
    agent_id = agent_state.agent_id
    ecl_mode = EclRecordMode(
        run_id=run_id,
        retrieval_now=retrieval_now,
        base_ts=base_ts,
        k_ecl=k_ecl,
        reflection_disabled=True,
    )
    retriever = Retriever(store, embedding, now_factory=retrieval_now)
    # Plane 2 bias capture: the cycle pushes one BiasFiredEvent per resample. The
    # slot is cleared before each cognition step so a decision records only its own
    # tick's event (``None`` when the resample did not fire).
    bias_slot: list[BiasFiredEvent] = []
    cycle = CognitionCycle(
        retriever=retriever,
        store=store,
        embedding=embedding,
        # RecordReplayChatClient structurally matches the ``chat`` surface the cycle
        # calls; the concrete annotation is ``OllamaChatClient`` so we duck-type.
        llm=cast("Any", llm),
        rng=Random(seed),  # noqa: S311 — determinism seed, not cryptographic
        ecl_mode=ecl_mode,
        bias_sink=bias_slot.append,
        reflector=reflector,
    )
    clock = ManualClock(start=0.0)
    ctx = _SinkContext()
    order_slot = sorted([agent_id]).index(agent_id)

    rows: list[EclTraceRow] = []

    def sink(
        sink_agent_id: str,
        physics_tick_index: int,
        x: float,
        y: float,
        z: float,
        yaw: float,
        pitch: float,
        zone: Zone,
    ) -> None:
        md = ctx.move
        rows.append(
            EclTraceRow(
                run_id=run_id,
                agent_id=sink_agent_id,
                physics_tick_index=physics_tick_index,
                agent_tick=ctx.agent_tick,
                order_slot=order_slot,
                x=x,
                y=y,
                z=z,
                yaw=yaw,
                pitch=pitch,
                zone=zone,
                resolved_from=md.resolved_from if md is not None else None,
                move_centroid=md.centroid if md is not None else None,
                move_provenance=md.provenance if md is not None else None,
                move_jitter=md.jitter if md is not None else None,
                move_pre_clamp=md.pre_clamp if md is not None else None,
                move_post_clamp=md.post_clamp if md is not None else None,
                move_clamp_fired=md.clamp_fired if md is not None else None,
            )
        )

    world = WorldRuntime(
        cycle=cycle,
        clock=clock,
        physics_hz=30.0,
        ecl_trace_sink=sink,
    )
    world.register_agent(agent_state, persona)
    # ``_agents`` / ``_step_one`` / ``_consume_result`` are the world seam's cognition
    # driver (Issue 003 owns them). The harness drives them directly rather than the
    # phase-wheel ``_on_cognition_tick`` so every cognition tick fires unconditionally
    # and the CycleResult (move provenance / envelopes) is captured — no cycle/world
    # edit, purely reading the public CycleResult the step returns.
    rt = world._agents[agent_id]  # noqa: SLF001 — driving the I3 seam (sanctioned)

    obs_factory = observation_factory or _default_observation_factory(agent_id)
    decisions: list[EclDecisionRecord] = []

    for agent_tick in range(n_cognition_ticks):
        ctx.agent_tick = agent_tick
        bias_slot.clear()
        for obs in obs_factory(agent_tick):
            world.inject_observation(agent_id, obs)
        # Correlate this cognition tick with the LLM call(s) it served by the
        # before/after ``used`` count, never a positional ``used[agent_tick]``
        # (Codex M-2): a ``raised`` call is appended before it re-raises, so the
        # stream stays tick-aligned but is no longer 1:1 with a positional index.
        # Reflection is disabled in record mode, so each cognition tick issues
        # exactly one action-LLM call (ok / unparseable / raised).
        used_before = len(llm.used)
        result = await world._step_one(rt)  # noqa: SLF001 — I3 seam driver
        world._consume_result(rt, result)  # noqa: SLF001 — wires MoveMsg → kinematics
        ctx.move = result.ecl_destination
        served = llm.used[used_before:]
        if len(served) != 1:
            msg = (
                f"ECL cognition tick {agent_tick} served {len(served)} action-LLM "
                "calls; expected exactly 1 (reflection disabled in record mode)"
            )
            raise EclReplayError(msg)
        decisions.append(
            _build_decision(
                agent_tick=agent_tick,
                call=served[0],
                result=result,
                bias_fired=bias_slot[0] if bias_slot else None,
            )
        )
        for _ in range(physics_ticks_per_cognition):
            await world._on_physics_tick()  # noqa: SLF001 — I3 seam driver

    frozen_rows = tuple(rows)
    return EclRunResult(
        run_id=run_id,
        rows=frozen_rows,
        decisions=tuple(decisions),
        checksum=ecl_trace_checksum(frozen_rows),
    )


def _build_decision(
    *,
    agent_tick: int,
    call: RecordedLlmCall,
    result: CycleResult,
    bias_fired: BiasFiredEvent | None,
) -> EclDecisionRecord:
    """Assemble one tick's Plane 2 record from the served call + CycleResult."""
    if call.outcome == "raised":
        # A raised (OllamaUnavailableError) call is response-less: skip parsing
        # entirely (``raw_response`` is ``""``) and record it as the ``raised``
        # fallback branch (Codex HIGH-2). ``result.llm_fell_back`` is already True.
        plan = None
        llm_status = "raised"
    else:
        plan = parse_llm_plan(call.raw_response)
        llm_status = "ok" if not result.llm_fell_back else "fell_back"
        if plan is None:
            llm_status = "unparseable"
    envelope_provenance = tuple(env.model_dump_json() for env in result.envelopes)
    return EclDecisionRecord(
        agent_tick=agent_tick,
        call=call,
        plan=plan,
        plan_schema_version=SCHEMA_VERSION,
        llm_fell_back=result.llm_fell_back,
        llm_status=llm_status,
        bias_fired=bias_fired,
        move_decision=result.ecl_destination,
        envelope_provenance=envelope_provenance,
    )


__all__ = [
    "DEFAULT_PHYSICS_TICKS_PER_COGNITION",
    "GOLDEN_COGNITION_TICKS",
    "EclDecisionRecord",
    "EclReplayError",
    "EclRunResult",
    "EclTraceRow",
    "RecordReplayChatClient",
    "RecordedLlmCall",
    "ecl_trace_checksum",
    "replay_client_from",
    "run_ecl_loop",
]
