"""Pure string-building for the cognition cycle's LLM messages.

Split into three stages (persona-erre skill §ルール 3):

* ``_COMMON_PREFIX`` — shared across every agent / tick. Placed first so
  SGLang's RadixAttention (M7+) can reuse its KV cache across personas.
* ``build_system_prompt`` — persona-specific + current-state tail.
* ``build_user_prompt`` — observations + retrieved memories + the JSON
  response contract consumed by :func:`cognition.parse.parse_llm_plan`.

All three are side-effect-free and deterministic for a fixed input.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Final

if TYPE_CHECKING:
    from collections.abc import Sequence

    from erre_sandbox.contracts.cognition_layers import WorldModelEntry
    from erre_sandbox.memory import RankedMemory
    from erre_sandbox.schemas import AgentState, Observation, PersonaSpec


_COMMON_PREFIX: Final[str] = (
    "You are an autonomous agent living in ERRE-Sandbox, a 3D world with "
    "five zones (study / peripatos / chashitsu / agora / garden). Each tick "
    "represents ten seconds of wall-clock time. Respond in character, "
    "following the cognitive habits of the persona described below. "
    "The ``utterance`` field MUST be written in Japanese (日本語) so the "
    "researcher observing the 3D scene can read it at a glance — "
    "original-language key terms (Kant のドイツ語/ラテン語, Nietzsche の"
    "ドイツ語など) may appear parenthetically inside the Japanese sentence. "
    "Keep utterances under 80 Japanese characters."
)

RESPONSE_SCHEMA_HINT: Final[str] = (
    "Respond with a SINGLE JSON object matching this schema (all deltas in "
    "[-1.0, 1.0], importance_hint in [0.0, 1.0]; use null for optional fields "
    "you intentionally skip). The last three keys (salient / decision / "
    "next_intent) are the reasoning trace shown to the researcher observing "
    "you — keep each under 80 characters of natural Japanese and be honest "
    "about why you act; leave them null only if genuinely not applicable:\n"
    "{\n"
    '  "thought": "internal monologue",\n'
    '  "utterance": "speech bubble text or null",\n'
    '  "destination_zone": "study|peripatos|chashitsu|agora|garden|null",\n'
    '  "animation": "walk|idle|sit_seiza|bow|null",\n'
    '  "valence_delta": 0.0,\n'
    '  "arousal_delta": 0.0,\n'
    '  "motivation_delta": 0.0,\n'
    '  "importance_hint": 0.5,\n'
    '  "salient": "what you found most salient this tick or null",\n'
    '  "decision": "the one-sentence reason for your action or null",\n'
    '  "next_intent": "what you plan to do next or null"\n'
    "}\n"
    "Return ONLY the JSON object. No prose outside the braces."
)

RESPONSE_SCHEMA_HINT_WITH_UPDATE: Final[str] = (
    "Respond with a SINGLE JSON object matching this schema (all deltas in "
    "[-1.0, 1.0], importance_hint in [0.0, 1.0]; use null for optional fields "
    "you intentionally skip). The last three keys (salient / decision / "
    "next_intent) are the reasoning trace shown to the researcher observing "
    "you — keep each under 80 characters of natural Japanese and be honest "
    "about why you act; leave them null only if genuinely not applicable:\n"
    "{\n"
    '  "thought": "internal monologue",\n'
    '  "utterance": "speech bubble text or null",\n'
    '  "destination_zone": "study|peripatos|chashitsu|agora|garden|null",\n'
    '  "animation": "walk|idle|sit_seiza|bow|null",\n'
    '  "valence_delta": 0.0,\n'
    '  "arousal_delta": 0.0,\n'
    '  "motivation_delta": 0.0,\n'
    '  "importance_hint": 0.5,\n'
    '  "salient": "what you found most salient this tick or null",\n'
    '  "decision": "the one-sentence reason for your action or null",\n'
    '  "next_intent": "what you plan to do next or null",\n'
    '  "world_model_update_hint": {\n'
    '    "axis": "exact shown axis= value",\n'
    '    "key": "exact shown key= value",\n'
    '    "direction": "strengthen|weaken|no_change",\n'
    '    "cited_memory_ids": ["ids from that entry\'s cite="]\n'
    "  }\n"
    "}\n"
    "world_model_update_hint: null unless a Held entry above no longer fits; if "
    "set, copy one shown entry axis= and key= exactly; never prefix or combine; "
    "each cited_memory_id MUST come from that entry's cite= list (else ignored).\n"
    "Return ONLY the JSON object. No prose outside the braces."
)


def _format_habit_line(habit_description: str, flag: str) -> str:
    return f"- {habit_description} [{flag}]"


def _format_persona_block(persona: PersonaSpec) -> str:
    habits = "\n".join(
        _format_habit_line(h.description, h.flag.value)
        for h in persona.cognitive_habits
    )
    zones = ", ".join(z.value for z in persona.preferred_zones)
    p = persona.personality
    # Big Five + ERRE-specific traits as two compact lines so three agents
    # sharing one scene read as three biologies instead of one. Numeric form
    # (not adjectives) keeps the prompt short and leaves the natural-language
    # interpretation to the LLM — giving each persona's own voice room to
    # colour identical 0.8 differently. See M7 First PR D4 in decisions.md.
    big_five = (
        f"openness={p.openness:.2f} conscientiousness={p.conscientiousness:.2f} "
        f"extraversion={p.extraversion:.2f} agreeableness={p.agreeableness:.2f} "
        f"neuroticism={p.neuroticism:.2f}"
    )
    aesthetic = f"wabi={p.wabi:.2f} ma_sense={p.ma_sense:.2f}"
    return (
        f"Persona: {persona.display_name} ({persona.era}).\n"
        f"Personality (Big Five, [0,1]): {big_five}.\n"
        f"Aesthetic sensibility: {aesthetic}.\n"
        f"Preferred zones: {zones}.\n"
        f"Cognitive habits (fact / legend / speculative):\n{habits}"
    )


def _format_state_tail(agent: AgentState) -> str:
    zone = agent.position.zone.value
    erre_mode = agent.erre.name.value
    cog = agent.cognitive
    phy = agent.physical
    return (
        f"Current tick: {agent.tick}.\n"
        f"Location: {zone}. ERRE mode: {erre_mode}.\n"
        f"Physical — sleep_quality={phy.sleep_quality:.2f}, "
        f"physical_energy={phy.physical_energy:.2f}, "
        f"fatigue={phy.fatigue:.2f}, cognitive_load={phy.cognitive_load:.2f}.\n"
        f"Cognitive — valence={cog.valence:.2f}, arousal={cog.arousal:.2f}, "
        f"motivation={cog.motivation:.2f}, stress={cog.stress:.2f}."
    )


def build_system_prompt(persona: PersonaSpec, agent: AgentState) -> str:
    """Assemble the system prompt in three stages (common / persona / tail).

    Ordering is load-bearing: the common prefix comes first so downstream
    KV caches can share it across personas (MVP Ollama does not exploit
    this, but SGLang at M7 will).
    """
    return "\n\n".join(
        [
            _COMMON_PREFIX,
            _format_persona_block(persona),
            _format_state_tail(agent),
        ],
    )


def _one_line(text: str, limit: int = 160) -> str:
    single = " ".join(text.split())
    if len(single) <= limit:
        return single
    return single[: limit - 1] + "…"


def format_memories(memories: Sequence[RankedMemory], max_items: int = 8) -> str:
    """Render *memories* as a bullet list sorted by strength (high first)."""
    if not memories:
        return "(no relevant memories)"
    ranked = sorted(memories, key=lambda m: m.strength, reverse=True)[:max_items]
    lines: list[str] = []
    for m in ranked:
        kind = m.entry.kind.value
        body = _one_line(m.entry.content)
        lines.append(f"- [{kind} strength={m.strength:.2f}] {body}")
    return "\n".join(lines)


_MAX_CITATIONS_PER_ENTRY: Final[int] = 2
"""Belief ids shown per Held entry when the M10-C update channel is on.

Capped because the ``self`` axis aggregates several dyads and
its full ``cited_memory_ids`` would otherwise blow the <= 80-token section
budget and destabilise the cache-benchmark byte count. The displayed subset is
*also* the authority set the LLM may cite from: a hint may only cite
ids it could actually see.
"""


def _displayed_citations(entry: WorldModelEntry, max_citations: int) -> list[str]:
    """Deterministic head of an entry's sorted cited ids (display == authority)."""
    return sorted(entry.cited_memory_ids)[:max_citations]


def visible_entry_citations(
    entries: Sequence[WorldModelEntry],
    max_items: int = 4,
    *,
    max_citations: int = _MAX_CITATIONS_PER_ENTRY,
) -> dict[tuple[str, str], frozenset[str]]:
    """Map ``(axis, key) -> displayed belief ids`` for the entries shown this turn.

    The **single source** shared by prompt rendering
    (:func:`format_world_model_entries` with ``include_citations=True``) and the
    cycle's hint verification (``world_model.apply_world_model_update_hint``), so
    the ids the LLM is shown are exactly the ids Python will accept as citations
    (DA-M10C-3). Only the displayed head (``entries[:max_items]``, each truncated
    to ``max_citations``) is exposed — the LLM cannot cite what it never saw.
    """
    return {
        (e.axis, e.key): frozenset(_displayed_citations(e, max_citations))
        for e in list(entries)[:max_items]
    }


def format_world_model_entries(
    entries: Sequence[WorldModelEntry],
    max_items: int = 4,
    *,
    include_citations: bool = False,
    max_citations: int = _MAX_CITATIONS_PER_ENTRY,
) -> str:
    """Render held world-model entries as a bounded bullet list (M10-B/M10-C).

    *entries* are expected **pre-sorted by salience** (the synthesis in
    :func:`erre_sandbox.cognition.world_model.synthesize_world_model` does
    this), so the top ``max_items`` are simply the head of the list. The line
    renders ``axis`` and ``key`` as **separate verbatim-copyable fields**
    (``- axis=<axis> key=<key> ...``) rather than a joined ``[axis/key]`` label,
    so a hint copying the shown ``key=`` field hits the bare ``(axis, key)`` the
    authority exposes (:func:`visible_entry_citations`) — the gate-1 not_displayed
    contract fix from ``.steering/20260606-hint-stateB-notdisplayed-adr/``. Values
    pin two-decimal fixed-point so the rendered text is byte-stable for the cache
    benchmark (DA-M10B-8).

    ``max_items`` defaults to 4 because each rendered line is ~18 proxy tokens,
    so 4 lines (~72) stay under the <= 80-token section budget (design-final
    §1.3) while 5 would overflow it. The bound is verified by
    ``tests/test_cognition/test_prompting_world_model.py`` (DA-M10B-11).

    ``include_citations`` (M10-C, default off so M10-B byte stability is
    untouched) appends ``cite=<id,...>`` — the same displayed-citation subset
    :func:`visible_entry_citations` returns — so a verified
    :class:`WorldModelUpdateHint` can cite a belief id it was actually shown.
    """
    lines: list[str] = []
    for e in list(entries)[:max_items]:
        line = (
            f"- axis={e.axis} key={e.key} value={e.value:+.2f} conf={e.confidence:.2f}"
        )
        if include_citations:
            line += f" cite={','.join(_displayed_citations(e, max_citations))}"
        lines.append(line)
    return "\n".join(lines)


def _observation_line(obs: Observation) -> str:  # noqa: PLR0911 — discriminator dispatch
    if obs.event_type == "perception":
        return _one_line(
            f"[perception] {obs.content} (intensity={obs.intensity:.2f})",
        )
    if obs.event_type == "speech":
        return _one_line(f"[speech by {obs.speaker_id}] {obs.utterance}")
    if obs.event_type == "zone_transition":
        frm = obs.from_zone.value
        to = obs.to_zone.value
        return f"[zone_transition] {frm} -> {to}"
    if obs.event_type == "erre_mode_shift":
        prev = obs.previous.value
        curr = obs.current.value
        return f"[erre_mode_shift] {prev} -> {curr} ({obs.reason})"
    if obs.event_type == "internal":
        return _one_line(
            f"[internal hint={obs.importance_hint:.2f}] {obs.content}",
        )
    if obs.event_type == "affordance":
        return _one_line(
            f"[affordance] {obs.prop_kind}#{obs.prop_id} in {obs.zone.value} "
            f"(distance={obs.distance:.1f}m, salience={obs.salience:.2f})",
        )
    if obs.event_type == "proximity":
        return (
            f"[proximity {obs.crossing}] other={obs.other_agent_id} "
            f"{obs.distance_prev:.1f}m -> {obs.distance_now:.1f}m"
        )
    if obs.event_type == "temporal":
        return f"[temporal] {obs.period_prev.value} -> {obs.period_now.value}"
    if obs.event_type == "biorhythm":
        return (
            f"[biorhythm {obs.signal}:{obs.threshold_crossed}] "
            f"{obs.level_prev:.2f} -> {obs.level_now:.2f}"
        )
    return "[unknown] (unformatted)"


_MAX_PROXIMITY_PER_TICK: Final[int] = 2
"""Upper bound on :class:`~erre_sandbox.schemas.ProximityEvent` items kept in
the user prompt per tick (M6-A-2b).

Rationale: with ``recent_limit=10`` a chaotic multi-agent scene can easily
fill every slot with proximity crossings (two agents pacing around each
other cross twice per round), pushing the more rare signals
(ZoneTransition / Biorhythm / ERREModeShift) out of the window entirely.
Keeping only the two most-recent proximity events preserves the
"somebody is near / just walked off" cue without starving the rest of the
stream."""


def _clamp_proximity(
    recent: Sequence[Observation],
    max_proximity: int = _MAX_PROXIMITY_PER_TICK,
) -> list[Observation]:
    """Drop all but the last ``max_proximity`` :class:`ProximityEvent`.

    Preserves the relative order of every non-proximity observation and of
    the surviving proximity entries. Implemented as a single left-to-right
    pass after counting total proximity entries so the surviving window is
    the *latest* ``max_proximity``, which is what the LLM should reason
    about (recent crossings matter more than ancient co-walks).
    """
    total_proximity = sum(1 for o in recent if o.event_type == "proximity")
    if total_proximity <= max_proximity:
        return list(recent)
    drop_before = total_proximity - max_proximity
    skipped = 0
    out: list[Observation] = []
    for o in recent:
        if o.event_type == "proximity" and skipped < drop_before:
            skipped += 1
            continue
        out.append(o)
    return out


def build_user_prompt(
    observations: Sequence[Observation],
    memories: Sequence[RankedMemory],
    recent_limit: int = 10,
    *,
    world_model_entries: Sequence[WorldModelEntry] = (),
    world_model_update_enabled: bool = False,
    self_other_context: str = "",
) -> str:
    """Build the user message: recent observations + memories + JSON contract.

    ``recent_limit`` (default 10 — widened from 5 in M6-A-2b) is the window
    of the tail-most observations fed to the LLM. After slicing, the window
    is rebalanced by :func:`_clamp_proximity` so a chatty proximity stream
    cannot crowd out rarer signals.

    ``world_model_entries`` (M10-B, keyword-only) is the individual layer's
    held subjective-world-model top-K. It is injected as a bounded section
    **immediately after** the memories, on the *user* side only, so the
    system prompt (and its shared RadixAttention prefix) is untouched. When
    empty (the flag-off default and every pre-M10-B caller) the section is
    omitted entirely, so the output is **byte-identical** to the prior
    contract — pinned by ``test_prompting_world_model.py`` and the
    cache-benchmark ``--check`` gate (DA-M10B-9). **Note**: byte-identity holds
    for this *empty* (base-path) case only; a Held-entry-present prompt changed
    intentionally with the ``axis= key=`` render contract fix
    (``20260607-hint-render-contract-alignment``), even at
    ``world_model_update_enabled=False``.

    ``world_model_update_enabled`` (M10-C, keyword-only, default off) opens the
    write-back channel: Held entries gain a ``cite=`` belief-id list and the
    response schema gains a ``world_model_update_hint`` field. It is **only**
    set on the individual-layer-enabled path, so the flag-off **base path**
    (empty entries; and ``RESPONSE_SCHEMA_HINT``) stays byte-identical — the off
    branch below is the literal pre-M10-C output (DA-M10C-3).

    ``self_other_context`` (M2 Layer2 mirror-sim, keyword-only) is a *pre-rendered*
    bounded SimToM text segment — the deterministic render of the other agents'
    prior-window observed behaviour that
    :func:`~erre_sandbox.integration.embodied.society.build_self_other_context`
    produces (self-contained header + body). It follows the exact same additive
    idiom as ``world_model_entries``: injected on the **user** side only, at a
    stable position **after** the held world-model block, so the shared system
    prefix is untouched and the world-model block's byte position is unchanged
    whether or not this segment is present. When empty (``""`` — the flag-off
    default and every non-Layer2 caller) the section is omitted entirely, so the
    output is **byte-identical** to the prior contract. This is a transient
    prompt-context injection: it is **never written to episodic memory** (that
    disjointness is the mirror-sim circularity guard, design-final.md §L6), so
    it rides in here as a plain string argument and nowhere near the memory sink.
    NOT a structural-floor verdict; verdict は holding.
    """
    recent = _clamp_proximity(list(observations)[-recent_limit:])
    obs_block = (
        "\n".join(_observation_line(o) for o in recent)
        if recent
        else "(nothing happened)"
    )
    mem_block = format_memories(memories)
    if world_model_entries:
        held_block = (
            "Held world-model entries:\n"
            + format_world_model_entries(
                world_model_entries,
                include_citations=world_model_update_enabled,
            )
            + "\n\n"
        )
    else:
        held_block = ""
    # M2 Layer2: the pre-rendered self-other segment carries its own header/body
    # (build_self_other_context), so it is placed as-is with a trailing blank
    # line at a stable position after the held block. Empty (``""``) → no
    # section → byte-identical to the pre-Layer2 contract (§L8 coexist golden).
    self_other_block = f"{self_other_context}\n\n" if self_other_context else ""
    schema_hint = (
        RESPONSE_SCHEMA_HINT_WITH_UPDATE
        if world_model_update_enabled
        else RESPONSE_SCHEMA_HINT
    )
    return (
        "Recent observations:\n"
        f"{obs_block}\n\n"
        "Relevant memories:\n"
        f"{mem_block}\n\n"
        f"{held_block}"
        f"{self_other_block}"
        "Decide what to do in the next ten seconds.\n\n"
        f"{schema_hint}"
    )


__all__ = [
    "RESPONSE_SCHEMA_HINT",
    "RESPONSE_SCHEMA_HINT_WITH_UPDATE",
    "build_system_prompt",
    "build_user_prompt",
    "format_memories",
    "format_world_model_entries",
    "visible_entry_citations",
]
