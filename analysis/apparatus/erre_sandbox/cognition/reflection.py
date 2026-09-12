"""Reflection collaborator (M4 foundation).

A :class:`Reflector` is held per :class:`~erre_sandbox.cognition.CognitionCycle`
and consulted at the tail of every tick. When its :class:`ReflectionPolicy`
decides the conditions are met, it distils the agent's recent episodic
memories into a single :class:`~erre_sandbox.schemas.SemanticMemoryRecord`
(via a separate LLM call), embeds the summary, persists the row through
:meth:`MemoryStore.upsert_semantic`, and returns the corresponding
:class:`~erre_sandbox.schemas.ReflectionEvent`.

Design rationale:

* Action selection and reflection are *different responsibilities* with
  different failure semantics — reflection being unavailable must not
  break the action path — so the two are intentionally separated rather
  than inlined into ``CognitionCycle.step``.
* The trigger policy is a pure :class:`ReflectionPolicy` dataclass so tests
  can inject ``tick_interval=1`` etc. without subclassing.
* The ``tick_interval`` is evaluated via a per-agent **counter** (not
  ``tick % N``) so M4 multi-agent orchestration (#6) can add/remove agents
  without synthetic firings caused by arbitrary global-tick alignment.
"""

from __future__ import annotations

import logging
import sqlite3
import uuid
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Final

from erre_sandbox.inference import (
    ChatMessage,
    OllamaUnavailableError,
    compose_sampling,
)
from erre_sandbox.memory import EmbeddingUnavailableError
from erre_sandbox.schemas import (
    MemoryKind,
    ReflectionEvent,
    SemanticMemoryRecord,
    Zone,
)

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable, Sequence

    from erre_sandbox.inference import OllamaChatClient
    from erre_sandbox.memory import EmbeddingClient, MemoryStore
    from erre_sandbox.schemas import (
        AgentState,
        DialogTurnMsg,
        MemoryEntry,
        Observation,
        PersonaSpec,
    )

logger = logging.getLogger(__name__)


DEFAULT_REFLECTIVE_ZONES: frozenset[Zone] = frozenset({Zone.PERIPATOS, Zone.CHASHITSU})

_MAX_SUMMARY_CHARS: Final[int] = 500
"""Hard cap on the LLM-produced summary before persistence.

The prompt asks for ≤200 chars but the LLM is not obliged to honour that.
Truncating here bounds both the SQLite row size and the embedding input —
relevant because prompt-injected or malfunctioning models can otherwise
return multi-KB responses. See security review (MEDIUM-1).
"""
"""Zones whose entry is interpreted as an implicit invitation to reflect.

Mirrors :data:`erre_sandbox.cognition.cycle._REFLECTION_ZONES` and is kept
here so a test can override the policy without touching the cycle module.
"""

_REFLECTION_LANG_HINT: Final[dict[str, str]] = {
    "kant": (
        "日本語で記述せよ（学術的・厳密・分析的な語彙を用い、"
        "原語のドイツ語・ラテン語の鍵概念は括弧で併記してよい）。"
    ),
    "rikyu": "日本語で記述せよ（古典的・侘び寂びの語彙を用いる）。",
    "nietzsche": (
        "日本語で記述せよ（詩的・アフォリスティック・警句的な語彙を用い、"
        "原語のドイツ語の鍵概念は括弧で併記してよい）。"
    ),
}
"""Per-persona language hint appended to the reflection system prompt.

Mirrors ``_DIALOG_LANG_HINT`` in ``integration/dialog_turn.py`` so
LATEST REFLECTION matches speech/dialog output language. Verb is 「記述せよ」
rather than dialog's 「応答せよ」 because reflection is a written monologue.
Unknown persona ids skip injection (degrade, don't raise)."""


@dataclass(frozen=True)
class ReflectionPolicy:
    """Pure rules for deciding when reflection should fire.

    Frozen so it can be shared across agents without defensive copies.
    Methods are side-effect free — all mutable per-agent state lives in
    :class:`Reflector`.
    """

    tick_interval: int = 10
    importance_threshold: float = 1.5
    trigger_zones: frozenset[Zone] = field(
        default_factory=lambda: DEFAULT_REFLECTIVE_ZONES
    )
    episodic_window: int = 10

    def should_fire(
        self,
        *,
        ticks_since_last: int,
        importance_sum: float,
        zone_entered: bool,
        low_coherence: bool = False,
    ) -> bool:
        """Return ``True`` when any trigger condition is satisfied.

        The conditions are OR-combined — a single tick that hits more than
        one still fires exactly once (the caller is expected to treat firing
        as a binary event and reset its counter).

        ``low_coherence`` (M11-A) is the only diagnostic-driven trigger: when
        the agent's latest utterance is *clearly incoherent* with its held
        world model the caller asks for an extra reflection-deepening pass.
        It defaults to ``False`` so every pre-M11-A caller keeps the original
        three-condition behaviour byte-for-byte; the score that produces it is
        measured by the cycle, never by this policy (diagnostic ⊥ control).
        """
        if ticks_since_last >= self.tick_interval:
            return True
        if importance_sum > self.importance_threshold:
            return True
        return zone_entered or low_coherence


def build_reflection_messages(
    persona: PersonaSpec,
    agent: AgentState,
    episodic: Sequence[MemoryEntry],
    recent_dialog_turns: Sequence[DialogTurnMsg] = (),
    *,
    persona_resolver: Callable[[str], str | None] | None = None,
) -> list[ChatMessage]:
    """Build the two-message prompt the reflection LLM call consumes.

    The system message pins persona identity; the user message lists the
    episodic window and asks for a concise UTF-8 summary with no JSON
    wrapping. The summary is stored verbatim as
    :attr:`SemanticMemoryRecord.summary`, so the output format here is
    load-bearing: we explicitly ask for plain text and cap the length,
    because we do not run a parser afterwards.

    M7γ: when ``recent_dialog_turns`` is non-empty, a "Recent peer
    utterances" section is appended to the system prompt. Each line carries
    one peer turn so the agent's reflection can react to *what other
    agents just said* (M7γ D1).
    Empty default keeps M6 callers (and unit tests for those callers)
    binary-compatible.

    M7δ (R3 M3): the optional ``persona_resolver`` maps a peer
    ``speaker_id`` (e.g. ``a_nietzsche_001``) to the persona's
    ``display_name`` (e.g. ``"Friedrich Nietzsche"``) so the LLM sees
    historically-grounded names rather than internal id strings. The
    resolver may return ``None`` for unresolved ids; the line then falls
    back to the raw ``speaker_id``. Default ``None`` preserves the M7γ
    rendering for callers that have not yet been migrated.
    """
    zone = agent.position.zone.value
    mode = agent.erre.name.value
    system = (
        f"You are {persona.display_name} ({persona.era}), pausing to reflect. "
        f"You are currently in the {zone} in {mode} mode. "
        "Distil the following recent experiences into a single short paragraph "
        "(<= 200 characters, UTF-8) written in your own voice, as if annotating "
        "a memory you want to keep. Return ONLY the paragraph — no headers, "
        "no JSON, no bullet points."
    )
    lang_hint = _REFLECTION_LANG_HINT.get(persona.persona_id, "")
    if lang_hint:
        system = f"{system} {lang_hint}"
    if recent_dialog_turns:
        peer_lines: list[str] = []
        for turn in recent_dialog_turns:
            speaker_label = turn.speaker_id
            if persona_resolver is not None:
                resolved = persona_resolver(turn.speaker_id)
                if resolved:
                    speaker_label = resolved
            peer_lines.append(f"- {speaker_label}: {_truncate(turn.utterance)}")
        peer_block = "\n".join(peer_lines)
        system = (
            f"{system}\n\nRecent peer utterances (newest last, max 3):\n{peer_block}"
        )
    if not episodic:
        body = "(no recent episodic memories)"
    else:
        lines = [f"- {_truncate(entry.content)}" for entry in episodic]
        body = "\n".join(lines)
    user = f"Recent episodic memories (newest first):\n{body}"
    return [
        ChatMessage(role="system", content=system),
        ChatMessage(role="user", content=user),
    ]


class Reflector:
    """Stateful distillation collaborator owned by one :class:`CognitionCycle`.

    Holds per-agent counters so ``tick_interval`` is measured against the
    number of ``maybe_reflect`` invocations between fires, not wall-clock
    or global tick. :meth:`maybe_reflect` never raises; all failure modes
    (LLM unavailable, embedding unavailable, empty episodic window) resolve
    to ``return None`` with a WARNING log.
    """

    def __init__(
        self,
        *,
        store: MemoryStore,
        embedding: EmbeddingClient,
        llm: OllamaChatClient,
        policy: ReflectionPolicy | None = None,
        persona_resolver: Callable[[str], str | None] | None = None,
    ) -> None:
        self._store = store
        self._embedding = embedding
        self._llm = llm
        self._policy = policy or ReflectionPolicy()
        self._ticks_since_last: dict[str, int] = {}
        # M7δ R3 M3: optional ``speaker_id → display_name`` resolver
        # threaded into ``build_reflection_messages`` so peer-utterance
        # lines render historical names instead of internal agent ids.
        # Default ``None`` keeps M7γ rendering for callers (e.g. unit
        # tests) that have not supplied one.
        self._persona_resolver = persona_resolver

    @property
    def policy(self) -> ReflectionPolicy:
        return self._policy

    def record_tick(self, agent_id: str) -> int:
        """Increment and return the counter for ``agent_id``.

        Exposed primarily for tests that want to assert counter isolation
        without driving a full cycle.
        """
        new_value = self._ticks_since_last.get(agent_id, 0) + 1
        self._ticks_since_last[agent_id] = new_value
        return new_value

    def reset_counter(self, agent_id: str) -> None:
        self._ticks_since_last[agent_id] = 0

    async def maybe_reflect(
        self,
        *,
        agent_state: AgentState,
        persona: PersonaSpec,
        observations: Sequence[Observation],
        importance_sum: float,
        recent_dialog_turns: Sequence[DialogTurnMsg] = (),
        low_coherence: bool = False,
    ) -> ReflectionEvent | None:
        """Evaluate the policy and, if triggered, run the full reflection path.

        Returns the produced :class:`ReflectionEvent` on success, or
        ``None`` when either the policy declined or a downstream (LLM /
        embedding / store) operation failed.

        ``recent_dialog_turns`` (M7γ D1): up to three recent turns from
        *other* personas, surfaced in the reflection system prompt so the
        agent's distillation can react to peer utterances. Empty default
        keeps existing M6 callers binary-compatible.

        ``low_coherence`` (M11-A): the cycle's diagnostic signal that this
        tick's utterance is clearly incoherent with the held world model;
        forwarded to :meth:`ReflectionPolicy.should_fire` as an extra OR
        trigger. Defaults to ``False`` so existing callers are unchanged.
        """
        ticks_since = self.record_tick(agent_state.agent_id)
        zone_entered = _detect_zone_entry(observations, self._policy.trigger_zones)
        if not self._policy.should_fire(
            ticks_since_last=ticks_since,
            importance_sum=importance_sum,
            zone_entered=zone_entered,
            low_coherence=low_coherence,
        ):
            return None
        # Attempt the reflection. On any recoverable failure we keep the
        # counter high so the next tick retries promptly (the policy still
        # considers "ticks_since >= interval" as firing). The counter is
        # reset only when we successfully persist a summary.
        event = await self._execute(
            agent_state=agent_state,
            persona=persona,
            recent_dialog_turns=recent_dialog_turns,
        )
        if event is not None:
            self.reset_counter(agent_state.agent_id)
        return event

    async def _execute(
        self,
        *,
        agent_state: AgentState,
        persona: PersonaSpec,
        recent_dialog_turns: Sequence[DialogTurnMsg] = (),
    ) -> ReflectionEvent | None:
        episodic = await self._store.list_by_agent(
            agent_id=agent_state.agent_id,
            kind=MemoryKind.EPISODIC,
            limit=self._policy.episodic_window,
        )
        if not episodic:
            logger.info(
                "Reflection skipped for agent %s: no episodic memories",
                agent_state.agent_id,
            )
            return None

        messages = build_reflection_messages(
            persona,
            agent_state,
            episodic,
            recent_dialog_turns=recent_dialog_turns,
            persona_resolver=self._persona_resolver,
        )
        sampling = compose_sampling(
            persona.default_sampling,
            agent_state.erre.sampling_overrides,
        )
        try:
            resp = await self._llm.chat(messages, sampling=sampling)
        except OllamaUnavailableError as exc:
            logger.warning(
                "Reflection LLM unavailable for agent %s: %s — skipping this tick",
                agent_state.agent_id,
                exc,
            )
            return None

        summary_text = resp.content.strip()[:_MAX_SUMMARY_CHARS]
        if not summary_text:
            logger.warning(
                "Reflection LLM returned empty summary for agent %s — skipping",
                agent_state.agent_id,
            )
            return None

        try:
            embedding = await self._embedding.embed_document(summary_text)
        except EmbeddingUnavailableError as exc:
            logger.warning(
                "Reflection embedding unavailable for agent %s: %s — "
                "storing row without vector",
                agent_state.agent_id,
                exc,
            )
            embedding = []

        reflection_id = str(uuid.uuid4())
        event = ReflectionEvent(
            agent_id=agent_state.agent_id,
            tick=agent_state.tick,
            summary_text=summary_text,
            src_episodic_ids=[m.id for m in episodic],
        )
        record = SemanticMemoryRecord(
            id=str(uuid.uuid4()),
            agent_id=agent_state.agent_id,
            embedding=embedding,
            summary=summary_text,
            origin_reflection_id=reflection_id,
        )
        try:
            await self._store.upsert_semantic(record)
        except (ValueError, sqlite3.OperationalError, OSError) as exc:
            # ``maybe_reflect`` advertises "never raises"; honour it for the
            # realistic persistence failures:
            # - ValueError: embedding-dim mismatch (config bug)
            # - sqlite3.OperationalError: DB lock / disk issue
            # - OSError: filesystem / permission issue
            logger.warning(
                "Reflection upsert failed for agent %s: %s — event discarded",
                agent_state.agent_id,
                exc,
            )
            return None
        return event


# ---------------------------------------------------------------------------
# Module-private helpers
# ---------------------------------------------------------------------------


def _detect_zone_entry(
    observations: Iterable[Observation],
    trigger_zones: frozenset[Zone],
) -> bool:
    for obs in observations:
        if obs.event_type == "zone_transition" and obs.to_zone in trigger_zones:
            return True
    return False


def _truncate(text: str, limit: int = 160) -> str:
    collapsed = " ".join(text.split())
    if len(collapsed) <= limit:
        return collapsed
    return collapsed[: limit - 1] + "…"


__all__ = [
    "DEFAULT_REFLECTIVE_ZONES",
    "ReflectionPolicy",
    "Reflector",
    "build_reflection_messages",
]
