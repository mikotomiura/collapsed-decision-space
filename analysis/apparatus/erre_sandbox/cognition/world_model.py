"""Read-only subjective-world-model synthesis (M10-B).

Periodically distils an agent's **observable evidence** — its belief-promoted
:class:`~erre_sandbox.schemas.SemanticMemoryRecord` rows plus the matching
:class:`~erre_sandbox.schemas.RelationshipBond` state — into a bounded
:class:`~erre_sandbox.contracts.cognition_layers.SubjectiveWorldModel`. The
result is injected into the *user* prompt (never the system prompt) as a
bounded top-K so SGLang RadixAttention's shared system prefix is preserved.

Design constraints:

* **Observable evidence only.** An entry exists only because a dyad was
  *promoted* to a belief record by
  :func:`erre_sandbox.cognition.belief.maybe_promote_belief`. The LLM never
  declares a world-model entry — Python distils one from the promoted record +
  bond. This module is **pure** (no I/O); the caller (the cognition cycle) owns
  reading the records via :meth:`MemoryStore.list_semantic_beliefs`.
* **cited ⊆ input.** Every :attr:`WorldModelEntry.cited_memory_ids` is a subset
  of the input record ids — a record-centric honesty invariant verified by
  ``tests/test_cognition/test_world_model.py``.
* **dyadic ⊥ class-wise.** The ``self`` axis only emits when ``>= 2``
  distinct dyads contribute, so it is a *generalised* self-model rather than a
  relabel of a single dyadic belief.
* **Deterministic.** Entries sort by ``(-salience, axis, key)``, cited ids are
  ``tuple(sorted(...))`` and bonds are visited in ``other_agent_id`` order, so
  a fixed input yields byte-stable downstream prompts.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Final, TypeAlias

from pydantic import BaseModel, ConfigDict

from erre_sandbox.cognition.belief_ids import belief_record_id
from erre_sandbox.contracts.cognition_layers import (
    PromotedEvidenceUnit,
    SubjectiveWorldModel,
    WorldModelEntry,
    WorldModelSnapshot,
)

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

    from erre_sandbox.contracts.cognition_layers import WorldModelUpdateHint
    from erre_sandbox.schemas import RelationshipBond, SemanticMemoryRecord


_SELF_MIN_DISTINCT_DYADS: Final[int] = 2
"""``self`` axis emits only with at least this many distinct dyads.

A single dyad would make ``self.relational_disposition`` a relabel of a dyadic
belief, violating the class-wise ⊥ dyadic orthogonality. Two or more
distinct dyads make the aggregate a genuine *generalised* self-model.
"""

_RELATIONAL_DISPOSITION_KEY: Final[str] = "relational_disposition"
"""``self`` axis key for the agent's generalised pro-/anti-social stance."""


@dataclass(frozen=True)
class _Evidence:
    """One promoted dyad: the belief record (id / confidence) + its bond."""

    record: SemanticMemoryRecord
    bond: RelationshipBond


def _recency_weight(current_tick: int, last_updated_tick: int, half_life: int) -> float:
    """Exponential recency decay in ``(0, 1]`` (1.0 when freshly updated).

    Folds interaction recency into entry salience (DA-M10B-7) without adding a
    separate ``temporal`` axis: a stale belief ranks below a fresh one of equal
    magnitude/confidence.
    """
    age = max(0, current_tick - last_updated_tick)
    return 0.5 ** (age / float(half_life))


def _salience(entry: WorldModelEntry, current_tick: int) -> float:
    """Ranking score = ``|value| * confidence * recency`` (not a stored field)."""
    recency = _recency_weight(
        current_tick,
        entry.last_updated_tick,
        entry.decay_half_life_ticks,
    )
    return abs(entry.value) * entry.confidence * recency


def _last_tick(evidence: Sequence[_Evidence], *, current_tick: int) -> int:
    """Max non-``None`` ``last_interaction_tick``; ``current_tick`` if all None."""
    ticks = [
        e.bond.last_interaction_tick
        for e in evidence
        if e.bond.last_interaction_tick is not None
    ]
    return max(ticks) if ticks else current_tick


def _sorted_cited(evidence: Sequence[_Evidence]) -> tuple[str, ...]:
    """Deterministic, deduplicated, sorted cited record ids."""
    return tuple(sorted({e.record.id for e in evidence}))


def _derive_env(
    evidence: Sequence[_Evidence],
    *,
    current_tick: int,
) -> list[WorldModelEntry]:
    """One ``env`` entry per interaction zone (bonds with a known last zone).

    ``value`` = mean affinity in the zone (how positively the individual
    relates to others *there*), ``confidence`` = mean familiarity. Bonds whose
    ``last_interaction_zone`` is ``None`` are skipped for ``env`` (no zone to
    key on) but still feed ``self``.
    """
    by_zone: dict[str, list[_Evidence]] = {}
    for e in evidence:
        zone = e.bond.last_interaction_zone
        if zone is None:
            continue
        by_zone.setdefault(zone.value, []).append(e)

    entries: list[WorldModelEntry] = []
    # ``sorted`` keeps the pre-final-sort order deterministic too (the final
    # salience sort would mask insertion order, but an explicit sort is cheaper
    # to reason about than relying on dict-insertion order — code-review MED-2).
    for zone_key, group in sorted(by_zone.items()):
        affinity = sum(e.bond.affinity for e in group) / len(group)
        familiarity = sum(e.bond.familiarity for e in group) / len(group)
        entries.append(
            WorldModelEntry(
                axis="env",
                key=zone_key,
                value=affinity,
                confidence=familiarity,
                cited_memory_ids=_sorted_cited(group),
                last_updated_tick=_last_tick(group, current_tick=current_tick),
            ),
        )
    return entries


def _derive_self(
    evidence: Sequence[_Evidence],
    *,
    current_tick: int,
) -> list[WorldModelEntry]:
    """A single generalised ``self`` disposition entry (>= 2 distinct dyads).

    ``value`` = mean affinity across dyads (net pro-/anti-social stance).
    ``confidence`` = mean belief confidence * **agreement** (the fraction by
    which the dyad affinity signs agree), so a self-model built from conflicting
    dyads (trust some, clash others) is low-confidence rather than a misleading
    near-zero average presented confidently.
    """
    distinct = {e.bond.other_agent_id for e in evidence}
    if len(distinct) < _SELF_MIN_DISTINCT_DYADS:
        return []

    affinities = [e.bond.affinity for e in evidence]
    value = sum(affinities) / len(affinities)
    mean_conf = sum(e.record.confidence for e in evidence) / len(evidence)
    # Agreement in [0, 1]: 1.0 when every dyad shares one sign, ~0 when balanced.
    signs = [(1 if a > 0 else -1 if a < 0 else 0) for a in affinities]
    agreement = abs(sum(signs)) / len(signs)
    confidence = max(0.0, min(1.0, mean_conf * agreement))
    return [
        WorldModelEntry(
            axis="self",
            key=_RELATIONAL_DISPOSITION_KEY,
            value=value,
            confidence=confidence,
            cited_memory_ids=_sorted_cited(evidence),
            last_updated_tick=_last_tick(evidence, current_tick=current_tick),
        ),
    ]


# Module-local deriver table (DA-M10B-11): a small fixed tuple, not a plugin
# registry. concept / norm / temporal have no deterministic observable evidence
# in M10-B and are intentionally absent (no fabricated axes); a future milestone
# adds a deriver here when a structured evidence type for them exists.
_DERIVERS: Final = (_derive_env, _derive_self)


def collect_promoted_evidence(
    belief_records: Sequence[SemanticMemoryRecord],
    bonds: Sequence[RelationshipBond],
    *,
    agent_id: str,
) -> list[_Evidence]:
    """Match each bond to its promoted belief record (single source of truth).

    The *set* of promoted dyads ``synthesize_world_model`` derives entries from
    and :func:`collect_promoted_evidence_units` persists are identical because
    both route through this one helper — so the persisted H2 substrate can never
    drift from the algorithm that produced the entries (stage-A ADR §6).

    A dyad is evidence iff its bond's ``other_agent_id`` resolves (via the
    deterministic :func:`belief_record_id`) to a belief-promoted record owned by
    *agent_id*: foreign-agent records, non-belief records (``belief_kind is None``)
    and orphan bonds (no matching record) are all rejected. Visited in
    ``other_agent_id`` order so a fixed input is byte-stable downstream.
    """
    valid_by_id: dict[str, SemanticMemoryRecord] = {
        r.id: r
        for r in belief_records
        if r.agent_id == agent_id and r.belief_kind is not None
    }
    evidence: list[_Evidence] = []
    for bond in sorted(bonds, key=lambda b: b.other_agent_id):
        record = valid_by_id.get(belief_record_id(agent_id, bond.other_agent_id))
        if record is not None:
            evidence.append(_Evidence(record=record, bond=bond))
    return evidence


def collect_promoted_evidence_units(
    belief_records: Sequence[SemanticMemoryRecord],
    bonds: Sequence[RelationshipBond],
    *,
    agent_id: str,
) -> list[PromotedEvidenceUnit]:
    """Project the matched promoted evidence into serialisable units (M10-A 段B).

    The H2 conformance substrate carrier: the cognition cycle calls this in its
    flag-on block and rides the result out on ``CycleResult.world_model_evidence``
    so the ``world`` layer never imports ``memory`` (mirrors ``belief_classes``,
    DA-M11C2-2 / DA-SB-1). Units are returned in ``other_agent_id`` order
    (:func:`collect_promoted_evidence` sorts bonds by it) so a fixed input yields
    a byte-stable persisted payload.

    Floats are **not** rounded here — the contract type stays exact for any other
    consumer; the trace serialiser owns the ``round(6)`` quantisation (DA-SB-4).
    """
    return [
        PromotedEvidenceUnit(
            other_agent_id=e.bond.other_agent_id,
            belief_kind=e.record.belief_kind,
            confidence=e.record.confidence,
            affinity=e.bond.affinity,
            familiarity=e.bond.familiarity,
            last_interaction_zone=e.bond.last_interaction_zone,
            last_interaction_tick=e.bond.last_interaction_tick,
        )
        for e in collect_promoted_evidence(belief_records, bonds, agent_id=agent_id)
    ]


def synthesize_world_model(
    belief_records: Sequence[SemanticMemoryRecord],
    bonds: Sequence[RelationshipBond],
    *,
    agent_id: str,
    current_tick: int,
    max_entries: int = 50,
) -> SubjectiveWorldModel:
    """Distil observable evidence into a bounded :class:`SubjectiveWorldModel`.

    Pure and deterministic. The cognition cycle reads *belief_records* via
    :meth:`MemoryStore.list_semantic_beliefs` and passes the agent's bonds.

    Evidence is the set of *promoted dyads*: a belief record whose deterministic
    id matches a bond. Foreign-agent records (``agent_id`` mismatch), non-belief
    records (``belief_kind is None``) and orphan records (no matching bond) are
    rejected, so no entry can cite a record outside the valid promoted set.

    Args:
        belief_records: The agent's belief-promoted semantic records.
        bonds: The agent's current relationship bonds.
        agent_id: The synthesising agent; records for any other agent are
            ignored (defensive — the store query already scopes by agent).
        current_tick: Used for recency-weighted salience ranking.
        max_entries: Hard upper bound on retained entries (schema allows 50).

    Returns:
        A :class:`SubjectiveWorldModel` whose entries are sorted by descending
        salience (ties broken by ``axis`` then ``key``) and capped at
        *max_entries*.
    """
    evidence = collect_promoted_evidence(belief_records, bonds, agent_id=agent_id)

    entries: list[WorldModelEntry] = []
    for deriver in _DERIVERS:
        entries.extend(deriver(evidence, current_tick=current_tick))

    entries.sort(key=lambda e: (-_salience(e, current_tick), e.axis, e.key))
    return SubjectiveWorldModel(entries=entries[:max_entries])


# ---------------------------------------------------------------------------
# M10-C — bounded LLM value modulation on top of the evidence floor
# ---------------------------------------------------------------------------
#
# Core invariant (decisions.md DA-M10C-2/4): the per-tick ``synthesize_world_model``
# output is the **evidence floor** and is authoritative for confidence /
# last_updated_tick / cited ids. The LLM, via a verified
# :class:`WorldModelUpdateHint`, may only nudge an existing entry's ``value`` by a
# bounded step in the direction of its current sign — it can never flip a sign,
# create an entry, or touch confidence / recency. Evidence change drops the
# modulation, so a belief the world stopped supporting cannot be kept alive by an
# LLM that liked it (continuity-bias guard).

VALUE_STEP: Final[float] = 0.05
"""Per-tick magnitude nudge a verified hint applies to an entry's ``value``.

The ``value`` step is calibrated by property tests (repeated nudge
converges to the cap, evidence change resets), *not* by the adoption-rate band.
"""

MAX_TOTAL_MODULATION: Final[float] = 0.15
"""Hard cap on how far the carried modulation may drift an entry from its floor.

Enforced in :func:`reconcile_world_model` when carrying a modulation across a
fresh floor. A same-direction nudge in the current tick may transiently sit one
:data:`VALUE_STEP` beyond this (~0.20, the top of the recommended band)
*before* it is injected — but the next reconcile re-clamps to ``+/-0.15`` so no
prompt ever shows a value past the cap.
"""


STM_HORIZON: Final[int] = 16
"""III-a STM carry horizon in ticks (fork III-a LTM/STM layer).

When :func:`reconcile_world_model` runs in its ``stm_carry=True`` arm it carries a
bounded LLM *offset* across a **floor-fingerprint change** (a ``T-fp`` cross-fp
transition: evidence churned but the floor sign is unchanged), instead of dropping
it as the frozen arm does. The carry is a **short-term** memory: it expires this
many ticks past the first cross-fp carry of a carrying run, after which the entry
re-grounds to its evidence floor.

Frozen against the versioned-measurement ADR's external TTL ceiling
``H_safety = 20`` (``evidence.saturation.versioned_constants.H_SAFETY``): the STM
horizon **must be <= H_safety** so the intervention cannot self-conform to the
measurement (ADR §3.0', Codex HIGH-3). 16 leaves a 4-tick margin below the V2
guard's ``episode_end - t0 > 20`` FAIL boundary. cognition does **not** import the
evidence layer (architecture dependency direction); the ``STM_HORIZON <= H_SAFETY``
relation is asserted in the test layer, which may import both.
"""


def _sign(x: float) -> int:
    """Three-valued sign (+1 / -1 / 0), matching the versioned scorer's ``_sign``.

    Used to detect a ``T-flip`` (floor sign reversal) on a cross-fp transition so
    the STM carry drops rather than letting a stale offset survive a belief that
    flipped direction (versioned ADR §4 V4).
    """
    if x > 0.0:
        return 1
    if x < 0.0:
        return -1
    return 0


_FLOOR_FINGERPRINT_PRECISION: Final[int] = 6
"""Decimal places the floor fingerprint rounds value/confidence to.

``synthesize_world_model`` derives value/confidence as floating-point means
(``sum()/len()``); comparing those with exact ``==`` would treat sub-ULP
representational jitter as an evidence change and silently reset the LLM
modulation every tick. Rounding to 6 dp absorbs that jitter while staying far
below any real affinity/familiarity change (>= 0.01), so a genuine evidence shift
still drops the stale modulation (code-review HIGH-1)."""


def _clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


def _floor_fingerprint(
    entry: WorldModelEntry,
) -> tuple[str, str, float, float, tuple[str, ...], int]:
    """Identity of an entry's *evidence* content (DA-M10C-2).

    A modulation is carried across ticks only while the floor entry it was based
    on is fingerprint-identical; any change here (value/confidence/cited/recency
    moved) means the evidence shifted, so the stale LLM modulation is dropped.
    value/confidence are rounded (:data:`_FLOOR_FINGERPRINT_PRECISION`) so
    floating-point mean jitter is not mistaken for an evidence change (HIGH-1).
    """
    return (
        entry.axis,
        entry.key,
        round(entry.value, _FLOOR_FINGERPRINT_PRECISION),
        round(entry.confidence, _FLOOR_FINGERPRINT_PRECISION),
        entry.cited_memory_ids,
        entry.last_updated_tick,
    )


def _nudge_value(value: float, direction: str) -> float | None:
    """Return the bounded one-step nudge of ``value``, or ``None`` if inapplicable.

    Sign is preserved (``weaken`` stops at 0, never crosses it; ``strengthen``
    grows magnitude toward 1). A zero-valued entry has no sign to push, so both
    directions are inapplicable.
    """
    if value == 0.0:
        return None
    sign = 1.0 if value > 0 else -1.0
    magnitude = abs(value)
    if direction == "strengthen":
        magnitude = min(1.0, magnitude + VALUE_STEP)
    elif direction == "weaken":
        magnitude = max(0.0, magnitude - VALUE_STEP)
    else:  # "no_change" is handled by the caller; defensive.
        return None
    return sign * magnitude


def apply_world_model_update_hint(
    swm: SubjectiveWorldModel,
    hint: WorldModelUpdateHint,
    exposed_entry_citations: Mapping[tuple[str, str], frozenset[str]],
) -> SubjectiveWorldModel | None:
    """Apply a verified hint as a bounded value nudge, or reject it (``None``).

    Pure. The LLM is a *candidate*; Python is the *authority* (ME-9 guard). A hint
    is adopted only when **all** of these hold (else ``None`` — non-adoption):

    * its ``(axis, key)`` names an entry that was actually displayed this turn
      (present in *exposed_entry_citations*);
    * every ``cited_memory_id`` is among the belief ids displayed *on that very
      entry* (entry-local grounding, DA-M10C-3 — not a global memory set);
    * ``direction`` is ``strengthen`` / ``weaken`` (``no_change`` is a no-op);
    * the nudge actually moves ``value`` (a zero-valued or already-saturated entry
      yields no change).

    Only ``value`` changes; ``confidence`` / ``last_updated_tick`` /
    ``cited_memory_ids`` stay floor-derived (DA-M10C-4) so the LLM cannot launder
    recency or certainty. The cumulative ``+/-MAX_TOTAL_MODULATION`` cap is
    enforced by :func:`reconcile_world_model`, not here.

    Args:
        swm: The reconciled SWM that was injected this turn.
        hint: The bounded update the LLM requested.
        exposed_entry_citations: ``(axis, key) -> displayed belief ids`` for the
            entries actually shown this turn (built by
            :func:`erre_sandbox.cognition.prompting.visible_entry_citations`).

    Returns:
        A new :class:`SubjectiveWorldModel` with the one nudged entry, or ``None``
        when the hint is not adopted.
    """
    key = (hint.axis, hint.key)
    visible = exposed_entry_citations.get(key)
    if visible is None:
        return None
    cited = set(hint.cited_memory_ids)
    if not cited or not cited.issubset(visible):
        return None
    if hint.direction == "no_change":
        return None

    idx = next(
        (i for i, e in enumerate(swm.entries) if (e.axis, e.key) == key),
        None,
    )
    if idx is None:  # displayed but absent from the SWM — defensive, shouldn't happen.
        return None
    entry = swm.entries[idx]
    new_value = _nudge_value(entry.value, hint.direction)
    if new_value is None or new_value == entry.value:
        return None
    new_entries = list(swm.entries)
    new_entries[idx] = entry.model_copy(update={"value": new_value})
    return SubjectiveWorldModel(entries=new_entries)


CarriedSinceClock: TypeAlias = tuple[tuple[tuple[str, str], int], ...]
"""III-a STM age clock: ``(((axis, key), first_cross_fp_carry_tick), ...)``.

Key-unique and sorted by :func:`_reconcile_stm_carry` so a fixed input is
byte-stable; an immutable tuple (not a dict) so the frozen
:class:`WorldModelRuntimeState` stays hashable-safe and cannot be mutated in place.
"""


class WorldModelRuntimeState(BaseModel):
    """Per-agent runtime state separating the evidence floor from LLM modulation.

    Held by ``world.tick.AgentRuntime`` (never the shared ``CognitionCycle``, to
    avoid multi-agent crosstalk — DA-M10C-6) and carried out of the cycle on
    :class:`~erre_sandbox.cognition.cycle.CycleResult`. Storing both the
    ``base_floor`` the modulations were computed against *and* the ``modulated``
    result lets :func:`reconcile_world_model` tell an evidence change apart from
    an LLM nudge (DA-M10C-2) instead of guessing from a single-SWM diff.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    base_floor: SubjectiveWorldModel
    modulated: SubjectiveWorldModel
    carried_since: CarriedSinceClock = ()
    """III-a STM age clock (see :data:`CarriedSinceClock`).

    Empty ``()`` on the frozen arm and on M10-C (no III-a carry) — so the
    ``base_floor`` / ``modulated`` projections the prompt, trace and snapshot read
    stay byte-identical to the pre-III-a behaviour (Codex MED-1: the guarantee is
    scoped to those projections, not the whole-state ``model_dump``). Populated only
    by the ``stm_carry=True`` arm of :func:`reconcile_world_model`, which writes it
    key-unique and in deterministic (sorted) order. This is a **conservative safety
    clock** that starts no later than the versioned scorer's retention ``t0`` — it
    does not claim to reconstruct the scorer's exact episode boundary (Codex
    HIGH-2)."""


def project_world_model_snapshot(
    state: WorldModelRuntimeState,
) -> WorldModelSnapshot:
    """Project a live :class:`WorldModelRuntimeState` into an immutable read-model.

    Pure and deterministic. ``base_floor`` / ``modulated`` are **deep-copied**
    — although :class:`WorldModelSnapshot` is ``frozen``, its inner
    :class:`SubjectiveWorldModel.entries` is a mutable ``list`` of non-frozen
    :class:`WorldModelEntry`, so sharing the instances would let a snapshot
    consumer mutate the single-source ``AgentRuntime`` state. The deep copy
    severs that alias (owner single source, ``contracts`` read-model is derived).
    """
    return WorldModelSnapshot(
        base_floor=state.base_floor.model_copy(deep=True),
        modulated=state.modulated.model_copy(deep=True),
    )


def reconcile_world_model(
    state: WorldModelRuntimeState | None,
    new_floor: SubjectiveWorldModel,
    *,
    current_tick: int | None = None,
    stm_carry: bool = False,
) -> WorldModelRuntimeState:
    """Carry bounded LLM value-modulations forward onto a fresh evidence floor.

    Pure and deterministic. On the first tick (``state is None``) the modulated view
    equals the floor.

    Two arms (the arm gate, versioned ADR §5.1):

    * ``stm_carry=False`` (default, **frozen arm**): a modulation is carried only
      while the floor entry it was based on is *fingerprint-identical*; any evidence
      change (or a new entry) drops it. ``current_tick`` is ignored. Every existing
      caller takes this path, so its ``base_floor`` / ``modulated`` projections are
      byte-identical to the pre-III-a behaviour.
    * ``stm_carry=True`` (**III-a STM arm**): in addition to the fingerprint-identical
      carry, a bounded LLM *offset* survives a floor-fingerprint change as long as
      the floor sign is unchanged (a ``T-fp`` cross-fp transition) and the carry is
      within :data:`STM_HORIZON` ticks of its first cross-fp carry; a floor sign
      reversal (``T-flip``), a new entry, or expiry drops it (see
      :func:`_reconcile_stm_carry`). Requires ``current_tick``.

    The floor's salience order is preserved in both arms (the LLM nudges *values*,
    never the ranking).
    """
    if state is None:
        return WorldModelRuntimeState(base_floor=new_floor, modulated=new_floor)
    if not stm_carry:
        return _reconcile_frozen(state, new_floor)
    if current_tick is None:
        raise ValueError("current_tick is required when stm_carry is True")
    return _reconcile_stm_carry(state, new_floor, current_tick=current_tick)


def _reconcile_frozen(
    state: WorldModelRuntimeState,
    new_floor: SubjectiveWorldModel,
) -> WorldModelRuntimeState:
    """Frozen reconcile arm — carry only across a fingerprint-identical floor.

    The pre-III-a body, unchanged, so ``stm_carry=False`` stays byte-identical in
    its ``base_floor`` / ``modulated`` projections (the existing reconcile tests are
    the mechanical proof).
    """
    prev_by_key = {(e.axis, e.key): e for e in state.base_floor.entries}
    mod_by_key = {(e.axis, e.key): e for e in state.modulated.entries}

    reconciled: list[WorldModelEntry] = []
    for e_new in new_floor.entries:
        key = (e_new.axis, e_new.key)
        prev = prev_by_key.get(key)
        mod = mod_by_key.get(key)
        if (
            prev is not None
            and mod is not None
            and _floor_fingerprint(prev) == _floor_fingerprint(e_new)
        ):
            lo = max(-1.0, e_new.value - MAX_TOTAL_MODULATION)
            hi = min(1.0, e_new.value + MAX_TOTAL_MODULATION)
            capped = _clamp(mod.value, lo, hi)
            reconciled.append(
                e_new
                if capped == e_new.value
                else e_new.model_copy(update={"value": capped}),
            )
        else:
            reconciled.append(e_new)

    return WorldModelRuntimeState(
        base_floor=new_floor,
        modulated=SubjectiveWorldModel(entries=reconciled),
    )


def _stm_carry_entry(
    prev: WorldModelEntry | None,
    mod: WorldModelEntry | None,
    e_new: WorldModelEntry,
    since: int | None,
    *,
    current_tick: int,
) -> tuple[WorldModelEntry, int | None]:
    """Resolve one entry's III-a STM carry: ``(reconciled_entry, carried_since)``.

    ``carried_since`` is ``None`` whenever the modulation drops (the clock clears).
    Decision order:

    * new entry / vanished modulation / zero offset -> floor stands (no synthesis from
      nothing, Codex HIGH-1);
    * cross-fp ``T-flip`` (floor sign reversed) -> drop (versioned V4);
    * STM expiry (``current_tick - carried_since > STM_HORIZON``) -> drop (the bounded
      conservative safety clock, Codex HIGH-2/3);
    * else carry the **offset** ``delta`` onto the fresh floor, clamped to the cap and
      unit range (a floor move keeps the offset sign — HIGH-1).
    """
    if prev is None or mod is None:
        return e_new, None  # new entry / vanished modulation -> drop
    delta = mod.value - prev.value
    if delta == 0.0:
        return e_new, None  # no modulation -> floor stands
    # An exact ``== 0.0`` is intentional: a genuine offset is a multiple of
    # VALUE_STEP (0.05), far above float noise, and the final ``capped == e_new.value``
    # guard below re-grounds any sub-ULP residue anyway.

    # T-flip is only checked under ``fp_changed`` because ``_floor_fingerprint``
    # includes the (rounded) floor value, so a value sign-flip always changes the
    # fingerprint — a fp-stable sign reversal cannot occur while that holds.
    fp_changed = _floor_fingerprint(prev) != _floor_fingerprint(e_new)
    if fp_changed and _sign(prev.value) != _sign(e_new.value):
        return e_new, None  # T-flip -> drop (versioned V4)

    if fp_changed and since is None:
        since = current_tick  # first cross-fp carry of this carrying run
    if since is not None:
        if current_tick < since:
            raise ValueError(
                f"current_tick {current_tick} precedes carried_since {since}: "
                "STM clock cannot run backward"
            )
        if current_tick - since > STM_HORIZON:
            return e_new, None  # STM expiry -> drop

    lo = max(-1.0, e_new.value - MAX_TOTAL_MODULATION)
    hi = min(1.0, e_new.value + MAX_TOTAL_MODULATION)
    capped = _clamp(e_new.value + delta, lo, hi)
    if capped == e_new.value:
        return e_new, None  # offset clamped to zero -> re-ground
    return e_new.model_copy(update={"value": capped}), since


def _reconcile_stm_carry(
    state: WorldModelRuntimeState,
    new_floor: SubjectiveWorldModel,
    *,
    current_tick: int,
) -> WorldModelRuntimeState:
    """III-a STM reconcile arm — carry a bounded *offset* across a ``T-fp`` change.

    In addition to the frozen fingerprint-identical carry, a bounded LLM offset
    survives a floor-fingerprint change while the floor sign is unchanged (a ``T-fp``
    cross-fp transition) and the carry is within :data:`STM_HORIZON` ticks of its first
    cross-fp carry. The per-entry decision (offset carry / T-flip drop / STM expiry) is
    in :func:`_stm_carry_entry`; this driver only walks the floor entries and threads
    the per-key ``carried_since`` clock.

    The clock starts no later than the versioned scorer's retention ``t0`` (the scorer
    episode is a subset of the carrying run), so ``episode_end - t0 <= STM_HORIZON``,
    which is ``< H_safety`` — the carry structurally cannot trip the V2 staleness guard
    (Codex HIGH-2). ``STM_HORIZON`` is the module constant (no per-call override).
    """
    if current_tick < 0:
        raise ValueError(f"current_tick must be non-negative, got {current_tick}")
    prev_by_key = {(e.axis, e.key): e for e in state.base_floor.entries}
    mod_by_key = {(e.axis, e.key): e for e in state.modulated.entries}
    since_by_key: dict[tuple[str, str], int] = dict(state.carried_since)

    reconciled: list[WorldModelEntry] = []
    next_since: dict[tuple[str, str], int] = {}
    for e_new in new_floor.entries:
        key = (e_new.axis, e_new.key)
        entry, since = _stm_carry_entry(
            prev_by_key.get(key),
            mod_by_key.get(key),
            e_new,
            since_by_key.get(key),
            current_tick=current_tick,
        )
        reconciled.append(entry)
        if since is not None:
            next_since[key] = since

    return WorldModelRuntimeState(
        base_floor=new_floor,
        modulated=SubjectiveWorldModel(entries=reconciled),
        carried_since=tuple(sorted(next_since.items())),
    )


__all__ = [
    "MAX_TOTAL_MODULATION",
    "STM_HORIZON",
    "VALUE_STEP",
    "WorldModelRuntimeState",
    "apply_world_model_update_hint",
    "collect_promoted_evidence_units",
    "reconcile_world_model",
    "synthesize_world_model",
]
