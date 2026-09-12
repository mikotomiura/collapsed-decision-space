"""Pure metric-computation helpers for the M8 scaling bottleneck profiling.

Three metrics are computed on data already persisted by the live run, then
compared against analytic thresholds (expressed as a percentage of each
metric's information-theoretic upper bound) to decide whether the system
has hit the observability ceiling that L6 ADR D2 (`observability-triggered`)
treats as the closure condition for adding a fourth persona:

* ``pair_information_gain`` — mutual information (bits/turn) the observer
  gains from the next dialog pair, relative to a ``history_k``-turn
  history. LOW means the observer can predict the next pair = relational
  saturation.
* ``late_turn_fraction`` — fraction of dialog turns whose ``turn_index``
  is past the dialog turn budget midpoint (default budget 6). HIGH means
  dialogs lean on their late turns = observer attention drained early.
* ``zone_kl_from_uniform`` — KL divergence (bits) between observed agent
  zone occupancy and the uniform 1/n_zones prior. HIGH means agents stay
  zone-biased (healthy); LOW means the zone bias has lost meaning =
  scaling trigger.

Design decisions D1-D5 explain
why M2 stays at the v1 simple-ratio formulation, why M1/M3 use information
theory, and why thresholds are expressed as a percentage of the analytic
upper bound rather than ``mean + 1.5σ``.

The pure-function style keeps every metric testable against fixture
``list[dict]`` data without spinning up a MemoryStore. ``aggregate(...)``
is the thin I/O wrapper on top that the CLI calls.
"""

from __future__ import annotations

import json
import math
from collections import Counter, defaultdict
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from erre_sandbox.cognition.cycle import CognitionCycle

if TYPE_CHECKING:
    from pathlib import Path


# ---------------------------------------------------------------------------
# Module constants
# ---------------------------------------------------------------------------

DEFAULT_HISTORY_K: int = 3
"""Default conditioning history length for ``compute_pair_information_gain``.

Three turns covers a "speaker, addressee, response" arc which is roughly
the unit a human observer follows when reading a dialog. Larger ``k``
needs more turns to estimate ``H(pair | history_k)`` reliably; the
spike's typical 60-360 s runs only produce 12-17 dialog turns total, so
k=3 is the maximum that keeps every conditional bin populated by ≥1
sample on average.
"""

DEFAULT_DIALOG_TURN_BUDGET: int = 6
"""Default dialog turn budget for ``compute_late_turn_fraction``.

Mirrors the ``dialog_turn_budget`` cap observed in M7-δ run logs — each
dialog runs at most six turns before the scheduler enforces a close.
"""

DEFAULT_NUM_ZONES: int = 5
"""Default zone count for ``compute_zone_kl_from_uniform``.

Five zones (study / peripatos / chashitsu / agora / garden) match the
M5+ world layout. Any deployment that adds or removes zones must pass an
explicit ``n_zones`` to keep the analytic upper bound (``log2(n_zones)``)
correct.
"""

PAIR_INFO_GAIN_THRESHOLD_PCT: float = 0.30
"""Default lower-bound ratio for ``pair_information_gain`` against
``log2(C(N, 2))``. See decisions.md D4."""

LATE_TURN_FRACTION_THRESHOLD: float = 0.60
"""Default upper-bound for ``late_turn_fraction``. Empirical 60% midpoint.
See decisions.md D4."""

ZONE_KL_THRESHOLD_PCT: float = 0.30
"""Default lower-bound ratio for ``zone_kl_from_uniform`` against
``log2(n_zones)``. See decisions.md D4."""


# ---------------------------------------------------------------------------
# Entropy helper (Laplace smoothing + Miller-Madow correction)
# ---------------------------------------------------------------------------


def _compute_entropy_safe(counts: list[int]) -> float:
    """Shannon entropy in bits with bias correction for small samples.

    Uses additive (Laplace) smoothing of +0.5 per slot to avoid undefined
    ``log2(0)`` and reduces the small-sample plug-in entropy bias via the
    Miller-Madow correction ``(K_nonzero - 1) / (2 * N_total)``. Both
    techniques are standard for entropy estimation from finite-count
    histograms; the combination keeps the estimate well-defined for
    ``len(counts) >= 1`` and reduces but does not eliminate the bias
    toward zero that plug-in MLE shows on small ``N``.

    Returns ``0.0`` when every count is zero or ``counts`` is empty.
    """
    n_total = sum(counts)
    if n_total <= 0:
        return 0.0

    n_slots = len(counts)
    smoothed_total = float(n_total) + 0.5 * n_slots

    entropy = 0.0
    for count in counts:
        smoothed = float(count) + 0.5
        probability = smoothed / smoothed_total
        # Smoothed values are strictly positive so log2(p) is finite.
        entropy -= probability * math.log2(probability)

    k_nonzero = sum(1 for c in counts if c > 0)
    if k_nonzero > 1:
        entropy += (k_nonzero - 1) / (2.0 * float(n_total))
    return entropy


# ---------------------------------------------------------------------------
# Metric 1 — pair information gain
# ---------------------------------------------------------------------------


def compute_pair_information_gain(
    turns: list[dict[str, object]],
    num_agents: int,
    *,
    history_k: int = DEFAULT_HISTORY_K,
) -> float | None:
    """Mutual information (bits/turn) between the next pair and prior history.

    Treats each dialog turn as emitting an unordered pair
    ``frozenset({speaker_persona_id, addressee_persona_id})``. Computes
    the marginal entropy ``H(pair)`` minus the conditional entropy
    ``H(pair | history_k)``, which is the average information the
    observer gains when they see the next pair after watching the
    previous ``history_k`` pairs.

    Returns ``None`` when:

    * ``num_agents < 2`` (no pair can be formed)
    * Fewer than ``history_k + 1`` usable turns (cannot form a
      conditional pair)
    * No turn has both ``speaker_persona_id`` and
      ``addressee_persona_id`` populated as strings (sqlite query miss)

    Analytic upper bound: ``log2(C(num_agents, 2))``. With N=3 the bound
    is ``log2(3) ≈ 1.585`` bits.
    """
    if num_agents < 2:  # noqa: PLR2004 — pair arity, not magic
        return None

    pair_seq: list[frozenset[str]] = []
    for turn in turns:
        speaker = turn.get("speaker_persona_id")
        addressee = turn.get("addressee_persona_id")
        if not isinstance(speaker, str) or not isinstance(addressee, str):
            continue
        if speaker == addressee:
            continue
        pair_seq.append(frozenset({speaker, addressee}))

    if len(pair_seq) < history_k + 1:
        return None

    pair_counts = Counter(pair_seq)
    h_marginal = _compute_entropy_safe(list(pair_counts.values()))

    history_to_next: dict[tuple[frozenset[str], ...], list[frozenset[str]]] = (
        defaultdict(list)
    )
    for i in range(history_k, len(pair_seq)):
        key = tuple(pair_seq[i - history_k : i])
        history_to_next[key].append(pair_seq[i])

    n_observations = sum(len(v) for v in history_to_next.values())
    if n_observations == 0:
        return None

    h_conditional = 0.0
    for outcomes in history_to_next.values():
        weight = len(outcomes) / n_observations
        next_counts = Counter(outcomes)
        h_conditional += weight * _compute_entropy_safe(list(next_counts.values()))

    return max(0.0, h_marginal - h_conditional)


# ---------------------------------------------------------------------------
# Metric 2 — late turn fraction
# ---------------------------------------------------------------------------


def compute_late_turn_fraction(
    turns: list[dict[str, object]],
    *,
    budget: int = DEFAULT_DIALOG_TURN_BUDGET,
) -> float | None:
    """Fraction of dialog turns whose ``turn_index`` lies past ``budget // 2``.

    Treats ``turn_index > budget // 2`` as "late". With the default
    ``budget = 6``, late turns are those with ``turn_index >= 4`` (i.e.
    > 3). Returns ``None`` when no usable turn is present.
    """
    midpoint = budget // 2
    total = 0
    late = 0
    for turn in turns:
        index = turn.get("turn_index")
        if not isinstance(index, int):
            continue
        total += 1
        if index > midpoint:
            late += 1
    if total == 0:
        return None
    return late / total


# ---------------------------------------------------------------------------
# Metric 3 — zone KL from uniform
# ---------------------------------------------------------------------------


def compute_zone_kl_from_uniform(
    snapshots: list[dict[str, object]],
    *,
    n_zones: int = DEFAULT_NUM_ZONES,
) -> float | None:
    """KL divergence (bits) between agent zone occupancy and the uniform prior.

    Reconstructs zone dwell time from a snapshot stream of
    ``{agent_id, tick, zone}``. For each agent, every consecutive pair
    of snapshots adds ``(tick_{i+1} - tick_i) *
    CognitionCycle.DEFAULT_TICK_SECONDS`` to the bucket of the *earlier*
    snapshot's zone. Run-boundary partial dwells are naturally excluded
    (each agent's first and last snapshot does not form a complete pair
    in isolation).

    Returns ``None`` when no agent contributed at least one consecutive
    pair (every agent has fewer than two snapshots in ``snapshots``) or
    when ``n_zones < 2`` (uniform-over-single-bucket is degenerate).

    Analytic upper bound: ``log2(n_zones)``. With 5 zones the bound is
    ``log2(5) ≈ 2.322`` bits.
    """
    if n_zones < 2:  # noqa: PLR2004 — uniform arity, not magic
        return None

    by_agent: dict[str, list[tuple[int, str]]] = defaultdict(list)
    for snap in snapshots:
        agent = snap.get("agent_id")
        tick = snap.get("tick")
        zone = snap.get("zone")
        if (
            not isinstance(agent, str)
            or not isinstance(tick, int)
            or not isinstance(zone, str)
        ):
            continue
        by_agent[agent].append((tick, zone))

    zone_seconds: dict[str, float] = defaultdict(float)
    tick_seconds = float(CognitionCycle.DEFAULT_TICK_SECONDS)
    for series in by_agent.values():
        series.sort(key=lambda entry: entry[0])
        for i in range(len(series) - 1):
            tick_curr, zone_curr = series[i]
            tick_next = series[i + 1][0]
            delta = tick_next - tick_curr
            if delta <= 0:
                continue
            zone_seconds[zone_curr] += delta * tick_seconds

    total = sum(zone_seconds.values())
    if total <= 0:
        return None

    uniform_p = 1.0 / float(n_zones)
    kl = 0.0
    for seconds in zone_seconds.values():
        probability = seconds / total
        if probability <= 0:
            continue
        kl += probability * math.log2(probability / uniform_p)
    return kl


# ---------------------------------------------------------------------------
# Threshold dispatch
# ---------------------------------------------------------------------------


def _pair_max_bits(num_agents: int) -> float:
    """Analytic upper bound for ``pair_information_gain`` in bits.

    With ``C(N, 2)`` distinct unordered pairs the marginal entropy
    ``H(pair)`` cannot exceed ``log2(C(N, 2))``. Returns ``0.0`` when
    fewer than two distinct pairs exist (``N < 3``) — there is then no
    information for the observer to gain from pair selection, and the
    metric should not gate scaling decisions.
    """
    n_pairs = num_agents * (num_agents - 1) // 2
    if n_pairs < 2:  # noqa: PLR2004 — pair entropy floor, not magic
        return 0.0
    return math.log2(n_pairs)


def _zone_max_bits(n_zones: int) -> float:
    """Analytic upper bound for ``zone_kl_from_uniform`` in bits.

    Returns ``0.0`` when ``n_zones < 2``; the uniform prior degenerates
    and the KL divergence is undefined or always 0.
    """
    if n_zones < 2:  # noqa: PLR2004 — zone arity floor, not magic
        return 0.0
    return math.log2(n_zones)


def default_thresholds(
    num_agents: int,
    *,
    n_zones: int = DEFAULT_NUM_ZONES,
) -> dict[str, float]:
    """Build the default analytic thresholds keyed by metric name.

    Returns a dict with three entries — one per metric — whose suffix
    (``_min_bits`` / ``_max`` / ``_min_bits``) selects the comparison
    direction that :func:`evaluate_thresholds` applies.

    When the analytic upper bound for a bits-based metric is 0 (e.g.
    ``num_agents < 3`` for M1, ``n_zones < 2`` for M3), the threshold
    is set to 0. Combined with the strict ``<`` comparison in
    :func:`evaluate_thresholds`, no observed value can trigger an alert
    in that degenerate case — the metric is silently neutralised
    instead of producing false positives.
    """
    return {
        "pair_information_gain_min_bits": PAIR_INFO_GAIN_THRESHOLD_PCT
        * _pair_max_bits(num_agents),
        "late_turn_fraction_max": LATE_TURN_FRACTION_THRESHOLD,
        "zone_kl_from_uniform_min_bits": ZONE_KL_THRESHOLD_PCT
        * _zone_max_bits(n_zones),
    }


_DIRECTION_SUFFIXES: tuple[tuple[str, str], ...] = (
    ("_min_bits", "min"),
    ("_max_bits", "max"),
    ("_min", "min"),
    ("_max", "max"),
)


def _parse_threshold_key(key: str) -> tuple[str, str] | None:
    """Return ``(metric_name, direction)`` for a threshold key, or ``None``.

    Direction is ``"min"`` (trigger when value < threshold) or ``"max"``
    (trigger when value > threshold). Recognised suffixes are
    ``_min_bits`` / ``_max_bits`` / ``_min`` / ``_max``.
    """
    for suffix, direction in _DIRECTION_SUFFIXES:
        if key.endswith(suffix):
            return key[: -len(suffix)], direction
    return None


def _resolve_metric_value(
    metric_name: str,
    metrics: dict[str, float | None],
) -> float | None:
    """Look up ``metric_name`` in ``metrics``, trying ``_bits`` suffix first."""
    for candidate in (f"{metric_name}_bits", metric_name):
        raw = metrics.get(candidate)
        if isinstance(raw, (int, float)):
            return float(raw)
    return None


def evaluate_thresholds(
    metrics: dict[str, float | None],
    thresholds: dict[str, float],
    *,
    run_id: str,
    log_path: Path | None = None,
) -> list[str]:
    r"""Compare ``metrics`` against ``thresholds`` and return violated names.

    The ``thresholds`` dict keys must end with one of ``_min_bits`` /
    ``_max_bits`` / ``_min`` / ``_max``: the suffix selects the
    comparison direction (``_min*`` triggers when value < threshold,
    ``_max*`` triggers when value > threshold). The metric value is
    looked up under both ``"<name>_bits"`` and ``"<name>"`` to match how
    ``aggregate()`` exposes the M1/M3 results (with ``_bits`` suffix) and
    M2 (without).

    ``None`` values in ``metrics`` are silently skipped (graceful
    degradation when M3 is unavailable because no journal was supplied).

    When ``log_path`` is set, every triggered metric appends one TSV
    line ``timestamp \t metric \t value \t threshold \t run_id`` to the
    file (creating the parent directory if missing).
    """
    triggered: list[str] = []
    triggered_records: list[tuple[str, float, float]] = []

    for key, threshold in thresholds.items():
        parsed = _parse_threshold_key(key)
        if parsed is None:
            continue
        metric_name, direction = parsed
        value = _resolve_metric_value(metric_name, metrics)
        if value is None:
            continue
        violated = (direction == "min" and value < threshold) or (
            direction == "max" and value > threshold
        )
        if violated:
            triggered.append(metric_name)
            triggered_records.append((metric_name, value, threshold))

    if log_path is not None and triggered_records:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now(tz=UTC).isoformat()
        with log_path.open("a", encoding="utf-8") as f:
            for metric_name, value, threshold in triggered_records:
                f.write(
                    f"{timestamp}\t{metric_name}\t{value:.6f}\t{threshold:.6f}\t{run_id}\n",
                )

    return triggered


# ---------------------------------------------------------------------------
# Journal scan helper
# ---------------------------------------------------------------------------


def _decode_journal_line(line: str) -> dict[str, object] | None:  # noqa: PLR0911 — JSON shape dispatch
    """Decode one journal line, unwrapping the probe-wrapped shape if present.

    Two envelope shapes are supported for M7-δ probe compatibility:

    * **top-level envelope**: ``{"kind": "agent_update", "tick": ...,
      "agent_state": {...}}``
    * **probe-wrapped**: ``{"_probe": ..., "raw": "<json string>"}`` —
      legacy handshake-style lines

    Returns the decoded inner dict, or ``None`` for malformed JSON,
    missing or non-string ``raw`` payloads, or non-dict shapes.
    """
    try:
        entry = json.loads(line)
    except json.JSONDecodeError:
        return None
    if not isinstance(entry, dict):
        return None
    if "raw" not in entry:
        return entry
    wrapped = entry["raw"]
    if isinstance(wrapped, dict):
        return wrapped
    if not isinstance(wrapped, str):
        return None
    try:
        inner = json.loads(wrapped)
    except json.JSONDecodeError:
        return None
    return inner if isinstance(inner, dict) else None


def _extract_zone_snapshot(payload: dict[str, object]) -> dict[str, object] | None:
    """Return ``{agent_id, tick, zone}`` from an ``agent_update`` envelope.

    Returns ``None`` when ``payload`` is not an ``agent_update`` event,
    when ``agent_state``/``position`` are missing, or when any of the
    three required fields has the wrong type.
    """
    if payload.get("kind") != "agent_update":
        return None
    state = payload.get("agent_state")
    if not isinstance(state, dict):
        return None
    agent_id = state.get("agent_id")
    tick = state.get("tick")
    position = state.get("position")
    zone = position.get("zone") if isinstance(position, dict) else None
    if isinstance(agent_id, str) and isinstance(tick, int) and isinstance(zone, str):
        return {"agent_id": agent_id, "tick": tick, "zone": zone}
    return None


def _scan_zone_snapshots_from_journal(journal_path: Path) -> list[dict[str, object]]:
    """Extract ``{agent_id, tick, zone}`` triples from a probe NDJSON journal.

    Walks the journal one line at a time. Lines that do not match an
    ``agent_update`` envelope shape are silently skipped — the journal
    is allowed to interleave message kinds. See ``_decode_journal_line``
    and ``_extract_zone_snapshot`` for the per-line shape contract.
    """
    triples: list[dict[str, object]] = []
    with journal_path.open(encoding="utf-8") as f:
        for raw_line in f:
            line = raw_line.rstrip()
            if not line:
                continue
            payload = _decode_journal_line(line)
            if payload is None:
                continue
            snapshot = _extract_zone_snapshot(payload)
            if snapshot is not None:
                triples.append(snapshot)
    return triples


# ---------------------------------------------------------------------------
# I/O wrapper
# ---------------------------------------------------------------------------


def aggregate(
    run_db_path: Path,
    journal_path: Path | None = None,
    *,
    run_id: str | None = None,
    alert_log_path: Path | None = None,
    n_zones: int = DEFAULT_NUM_ZONES,
) -> dict[str, object]:
    """Aggregate all 3 scaling metrics from a run's persisted artifacts.

    Reads dialog turns from the sqlite database at ``run_db_path``
    (populated by the M8 L6-D1 sink) for M1/M2 and zone snapshots from
    the journal NDJSON at ``journal_path`` (probe envelope stream) for
    M3. When ``journal_path`` is ``None`` the zone metric is omitted
    (returns ``None`` in the JSON shape) — graceful degradation is
    intentional so older runs without a journal can still produce M1/M2
    numbers.

    The returned dict matches schema ``scaling_metrics_v1`` and is the
    JSON shape the ``scaling-metrics`` CLI emits.

    .. note::

       D5 (epoch_phase boundary, M7ε): only ``EpochPhase.AUTONOMOUS``
       turns drive the relational-saturation metrics. Q&A epoch turns
       (researcher-injected, ``EpochPhase.Q_AND_A``) are filtered out
       at iteration time so the trigger reflects autonomous behaviour
       quality, not user-induced bias. Pre-M7ε rows have NULL
       ``epoch_phase`` and are treated as AUTONOMOUS for backward compat
       (see ``MemoryStore.iter_dialog_turns`` docstring).
    """
    # Local import: store is async-heavy and we don't want to pay its
    # startup cost when callers only want the pure helpers above.
    from erre_sandbox.memory.store import MemoryStore  # noqa: PLC0415
    from erre_sandbox.schemas import EpochPhase  # noqa: PLC0415

    store = MemoryStore(db_path=run_db_path)
    store.create_schema()
    try:
        turns = list(
            store.iter_dialog_turns(epoch_phase=EpochPhase.AUTONOMOUS),
        )
    finally:
        conn = store._conn  # noqa: SLF001 — sync close mirrors evidence.metrics.aggregate
        if conn is not None:
            conn.close()

    persona_ids: set[str] = set()
    for turn in turns:
        speaker = turn.get("speaker_persona_id")
        addressee = turn.get("addressee_persona_id")
        if isinstance(speaker, str):
            persona_ids.add(speaker)
        if isinstance(addressee, str):
            persona_ids.add(addressee)
    num_agents = len(persona_ids)

    ticks: list[int] = []
    for turn in turns:
        tick_value = turn.get("tick")
        if isinstance(tick_value, int):
            ticks.append(tick_value)
    run_duration_s = 0.0
    if ticks:
        run_duration_s = (max(ticks) - min(ticks)) * float(
            CognitionCycle.DEFAULT_TICK_SECONDS,
        )

    snapshots: list[dict[str, object]] | None = None
    if journal_path is not None:
        snapshots = _scan_zone_snapshots_from_journal(journal_path)

    pair_info = compute_pair_information_gain(turns, num_agents)
    late_frac = compute_late_turn_fraction(turns)
    zone_kl: float | None
    if snapshots is None:
        zone_kl = None
    else:
        zone_kl = compute_zone_kl_from_uniform(snapshots, n_zones=n_zones)

    pair_max_bits = _pair_max_bits(num_agents)
    zone_max_bits = _zone_max_bits(n_zones)

    metrics_payload: dict[str, float | None] = {
        "pair_information_gain_bits": pair_info,
        "late_turn_fraction": late_frac,
        "zone_kl_from_uniform_bits": zone_kl,
    }
    thresholds = default_thresholds(num_agents, n_zones=n_zones)
    effective_run_id = run_id or run_db_path.stem
    alerts = evaluate_thresholds(
        metrics_payload,
        thresholds,
        run_id=effective_run_id,
        log_path=alert_log_path,
    )

    return {
        "schema": "scaling_metrics_v1",
        "run_id": effective_run_id,
        "run_duration_s": run_duration_s,
        "num_agents": num_agents,
        "num_dialog_turns": len(turns),
        "pair_information_gain_bits": pair_info,
        "pair_information_gain_max_bits": pair_max_bits,
        "late_turn_fraction": late_frac,
        "zone_kl_from_uniform_bits": zone_kl,
        "zone_kl_max_bits": zone_max_bits,
        "thresholds": thresholds,
        "alerts": alerts,
    }
