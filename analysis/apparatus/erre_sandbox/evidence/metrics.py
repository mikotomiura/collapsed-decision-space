"""Pure metric-computation helpers for the M8 baseline.

Three metrics are computed on data already persisted by the live run:

* ``self_repetition_rate`` — per-persona trigram overlap between a speaker's
  consecutive utterances. LOW means a persona stays fresh turn-over-turn
* ``cross_persona_echo_rate`` — trigram overlap between utterances emitted
  by *different* personas within the same dialog. LOW means personas are
  linguistically distinct
* ``bias_fired_rate`` — observed bias firings normalised by the number of
  opportunities the knob *could* have fired (``duration × num_agents ×
  bias_p``). A value near 1.0 means ``_bias_target_zone`` fired at the rate
  its probability knob requested; values far above or below flag a
  divergence between cognition's preference resampling and the knob

Design decisions D1-D5 explain why
``affinity_trajectory`` is intentionally absent (defer to
``m8-affinity-dynamics`` after ``RelationshipBond.affinity`` gains mutation
logic) and why the pipeline is a post-hoc CLI rather than a live-run hook.

The pure-function style keeps every metric testable against a fixture
``list[dict]`` without spinning up a MemoryStore. ``aggregate(path)`` is
the thin I/O wrapper on top that the CLI calls.
"""

from __future__ import annotations

from collections import defaultdict
from typing import TYPE_CHECKING

from erre_sandbox.cognition.cycle import CognitionCycle

if TYPE_CHECKING:
    from pathlib import Path


TRIGRAM_WINDOW: int = 5
"""Default window size for the ``self_repetition_rate`` sliding pair count.

Five turns is enough to catch "said the same thing three turns ago"
repetitions without over-weighting the persona's opening statement across
the entire run. The window is exposed as a module-level constant rather
than a function argument so fixture tests pin the same window the CLI
uses — a spike-level constant we can promote to a CLI flag if future
calibration demands it.
"""

CROSS_PERSONA_WINDOW: int = 10
"""Default window size for the ``cross_persona_echo_rate`` pair count.

Ten turns corresponds to the nominal 5-exchange dialog length (two
personas alternating) × the two speakers. Wider than ``TRIGRAM_WINDOW``
because cross-persona echo is a slower-moving signal — personas tend
to drift toward each other over an entire dialog, not across 2-3 turns.
"""


def _trigrams(text: str) -> set[tuple[str, str, str]]:
    """Return the set of whitespace-token trigrams in ``text``.

    Japanese and English utterances both tokenise on whitespace for the
    baseline — we are comparing *persona linguistic fingerprint*, not
    semantic content, so any stable tokeniser gives a useful signal as
    long as the same tokeniser is used across both runs being compared.
    Empty and very short utterances (<3 tokens) yield an empty set.
    """
    tokens = text.split()
    if len(tokens) < 3:  # noqa: PLR2004 — trigram arity, no magic
        return set()
    return {(tokens[i], tokens[i + 1], tokens[i + 2]) for i in range(len(tokens) - 2)}


def _jaccard(a: set[tuple[str, str, str]], b: set[tuple[str, str, str]]) -> float:
    """Jaccard similarity of two trigram sets; 0.0 when both are empty."""
    union = a | b
    if not union:
        return 0.0
    return len(a & b) / len(union)


def compute_self_repetition_rate(turns: list[dict[str, object]]) -> float | None:
    """Mean trigram Jaccard between consecutive turns of the *same* persona.

    For each ``speaker_persona_id``, examine the trailing
    :data:`TRIGRAM_WINDOW` turns and average the Jaccard similarity of
    every adjacent pair. Returns the cross-persona mean, or ``None`` when
    no persona produced enough turns to form at least one pair (run was
    too short to measure).

    The windowing is per-persona so a quiet persona does not drag the
    metric toward 0.0 by contributing nothing — they simply do not vote.
    """
    by_persona: dict[str, list[str]] = defaultdict(list)
    for turn in turns:
        persona = turn.get("speaker_persona_id")
        utterance = turn.get("utterance")
        if not isinstance(persona, str) or not isinstance(utterance, str):
            continue
        by_persona[persona].append(utterance)

    per_persona_means: list[float] = []
    for utterances in by_persona.values():
        window = utterances[-TRIGRAM_WINDOW:]
        if len(window) < 2:  # noqa: PLR2004 — need at least one pair
            continue
        trigrams = [_trigrams(u) for u in window]
        pair_scores = [
            _jaccard(trigrams[i], trigrams[i + 1]) for i in range(len(trigrams) - 1)
        ]
        if pair_scores:
            per_persona_means.append(sum(pair_scores) / len(pair_scores))

    if not per_persona_means:
        return None
    return sum(per_persona_means) / len(per_persona_means)


def compute_cross_persona_echo_rate(turns: list[dict[str, object]]) -> float | None:
    """Mean trigram Jaccard between *different* personas' utterances.

    Within each ``dialog_id`` (so cross-dialog drift does not contaminate
    the signal), look at the trailing :data:`CROSS_PERSONA_WINDOW` turns
    and average Jaccard similarity of every pair whose speakers belong to
    different personas. Returns the dialog-wise mean, or ``None`` when no
    dialog contained turns from at least two distinct personas.
    """
    by_dialog: dict[str, list[dict[str, object]]] = defaultdict(list)
    for turn in turns:
        dialog_id = turn.get("dialog_id")
        persona = turn.get("speaker_persona_id")
        utterance = turn.get("utterance")
        if (
            not isinstance(dialog_id, str)
            or not isinstance(persona, str)
            or not isinstance(utterance, str)
        ):
            continue
        by_dialog[dialog_id].append(
            {"persona": persona, "utterance": utterance},
        )

    per_dialog_means: list[float] = []
    for rows in by_dialog.values():
        window = rows[-CROSS_PERSONA_WINDOW:]
        scores: list[float] = []
        for i in range(len(window)):
            for j in range(i + 1, len(window)):
                if window[i]["persona"] == window[j]["persona"]:
                    continue
                u_i = window[i]["utterance"]
                u_j = window[j]["utterance"]
                if not isinstance(u_i, str) or not isinstance(u_j, str):
                    continue
                scores.append(_jaccard(_trigrams(u_i), _trigrams(u_j)))
        if scores:
            per_dialog_means.append(sum(scores) / len(scores))

    if not per_dialog_means:
        return None
    return sum(per_dialog_means) / len(per_dialog_means)


def compute_bias_fired_rate(
    events: list[dict[str, object]],
    *,
    run_duration_s: float,
    num_agents: int,
) -> float | None:
    """Observed bias firings divided by the knob's expected firings.

    The denominator assumes one cognition tick per agent per
    :data:`~erre_sandbox.cognition.cycle.CognitionCycle.DEFAULT_TICK_SECONDS`
    (10 s at MVP). For each event the ``bias_p`` that was in effect at
    firing time is used, so runs that tuned ``ERRE_ZONE_BIAS_P`` mid-way
    still produce a well-defined ratio. Returns ``None`` when the
    denominator is non-positive (run_duration_s ≤ 0 or num_agents ≤ 0 or
    events had ``bias_p ≤ 0``) — these states are operator error, not
    metric signal.

    Interpretation:

    * ≈ 1.0 — ``_bias_target_zone`` fired at the expected rate
    * < 1.0 — the LLM frequently picked preferred zones unprompted (good
      news: persona prompting already biased the destination)
    * > 1.0 — logging defect or multi-tick firings per cycle; investigate

    Caveat: ``bias_p`` is read from the fired events themselves, so runs
    where ``ERRE_ZONE_BIAS_P`` changed mid-run will skew toward whichever
    setting was active during the majority of firings (selection bias).
    For MVP with a constant knob this is exact; promoting this metric to
    compare runs with variable ``bias_p`` requires also persisting the
    no-fire ticks.
    """
    if run_duration_s <= 0 or num_agents <= 0 or not events:
        return None

    expected_ticks = (run_duration_s / CognitionCycle.DEFAULT_TICK_SECONDS) * num_agents
    if expected_ticks <= 0:
        return None

    bias_p_values: list[float] = []
    for e in events:
        bias_p = e.get("bias_p")
        if isinstance(bias_p, (int, float)):
            bias_p_values.append(float(bias_p))
    if not bias_p_values or any(p <= 0 for p in bias_p_values):
        return None

    expected_firings = (
        sum(p * expected_ticks / num_agents for p in bias_p_values)
        / len(
            bias_p_values,
        )
        * num_agents
    )
    if expected_firings <= 0:
        return None
    return len(events) / expected_firings


def aggregate(run_db_path: Path) -> dict[str, object]:
    """Open ``run_db_path``, compute every baseline metric, return JSON shape.

    Reads every ``dialog_turns`` row and every ``bias_events`` row, then
    calls the three pure helpers. ``run_duration_s`` and ``num_agents`` are
    derived from the persisted rows so the CLI does not need the live run
    config file — if those rows are empty, the bias rate returns ``None``.

    The returned dict is the JSON shape the ``baseline-metrics`` CLI emits
    and is the exact shape M9 comparison runs must also produce. Keys use
    ``snake_case`` to stay legible in diff tools.
    """
    # Lazy import — keep memory/ off the cognition graph at module load.
    from erre_sandbox.memory.store import MemoryStore  # noqa: PLC0415

    store = MemoryStore(db_path=run_db_path)
    store.create_schema()
    try:
        turns = list(store.iter_dialog_turns())
        events = list(store.iter_bias_events())
    finally:
        # ``MemoryStore.close`` is async — reach through to the raw sqlite
        # connection so repeat invocations (batch comparison) do not leak
        # file descriptors. Guarded for the case where ``_ensure_conn`` has
        # not been called; ``_conn`` is ``None`` then.
        conn = store._conn  # noqa: SLF001 — sync close needed here
        if conn is not None:
            conn.close()

    agent_ids: set[str] = set()
    for turn in turns:
        speaker = turn.get("speaker_agent_id")
        addressee = turn.get("addressee_agent_id")
        if isinstance(speaker, str):
            agent_ids.add(speaker)
        if isinstance(addressee, str):
            agent_ids.add(addressee)
    num_agents = len(agent_ids)
    ticks: list[int] = []
    for t in turns:
        tick_val = t.get("tick")
        if isinstance(tick_val, (int, float)):
            ticks.append(int(tick_val))
    run_duration_s = 0.0
    if ticks:
        run_duration_s = (max(ticks) - min(ticks)) * CognitionCycle.DEFAULT_TICK_SECONDS

    return {
        "schema": "baseline_metrics_v1",
        "turn_count": len(turns),
        "bias_event_count": len(events),
        "num_agents": num_agents,
        "run_duration_s": run_duration_s,
        "self_repetition_rate": compute_self_repetition_rate(turns),
        "cross_persona_echo_rate": compute_cross_persona_echo_rate(turns),
        "bias_fired_rate": compute_bias_fired_rate(
            events,
            run_duration_s=run_duration_s,
            num_agents=num_agents,
        ),
        # affinity metric is deferred to the ``m8-affinity-dynamics`` spike
        # (L6 D1 residual). Retained as a null field so M9 comparison runs
        # reading the same JSON shape can fall back gracefully.
        "affinity_trajectory": None,
    }
