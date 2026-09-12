"""Cognition-time shadow classifier + carrier builder for the hint instrument.

The engagement instrument (ADR §2) records *what the authority did* to each
world-model update hint. The **headline** adopted/rejected split is read straight off
``apply_world_model_update_hint``'s real return (``nudged is not None``) in
``cognition.cycle`` — never re-derived. This module owns only the two cognition-time
pieces the authority does not hand back:

* :func:`classify_rejection_reason` — a pure **shadow** that re-walks the authority's
  four reject predicates *in the same order* to name which gate fired. It reuses the
  authority's own ``_nudge_value`` for the no-effect predicate, so that gate cannot
  drift; the gate-1/2/3 equivalence is pinned by a conformance property test.
* :func:`build_emitted_disposition` / :func:`build_not_emitted_disposition` — assemble
  the :class:`WorldModelHintDisposition` carrier ``cycle`` rides out on ``CycleResult``.
  The adopted step is the **measured** ``new - old`` (補強 §1), not a hardcoded
  ``+/-VALUE_STEP`` (``_nudge_value``'s ``weaken`` clamps at 0, so a near-zero entry
  adopts with a sub-step delta).

Layering: this lives in ``cognition`` (not ``evidence``) because the runtime calls it
and ``cognition`` may not import ``evidence`` (DA-EII-9 / repository-structure §4). It
imports only ``contracts`` + the sibling ``world_model`` authority.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Literal

from erre_sandbox.cognition.world_model import _nudge_value
from erre_sandbox.contracts.cognition_layers import WorldModelHintDisposition

if TYPE_CHECKING:
    from collections.abc import Mapping

    from erre_sandbox.contracts.cognition_layers import (
        HintDisposition,
        SubjectiveWorldModel,
        WorldModelUpdateHint,
    )

# Carrier ``llm_status`` vocabulary (mirrors the contract field's Literal).
LlmStatus = Literal["ok", "unavailable", "unparseable"]

# Literal fallback statuses for the two pre-step-7.5 returns (Codex HIGH-1).
LLM_STATUS_UNAVAILABLE: LlmStatus = "unavailable"
LLM_STATUS_UNPARSEABLE: LlmStatus = "unparseable"


def classify_rejection_reason(
    hint: WorldModelUpdateHint,
    exposed_citations: Mapping[tuple[str, str], frozenset[str]],
    swm: SubjectiveWorldModel,
) -> HintDisposition:
    """Name the disposition by re-walking the authority's predicates (ADR §2).

    Returns ``adopted`` when all four predicates pass, else the one ``rejected_*`` gate
    that fired — evaluated in the **same order** as
    :func:`~erre_sandbox.cognition.world_model.apply_world_model_update_hint`:

    1. ``rejected_not_displayed`` — ``(axis, key)`` was not shown this turn;
    2. ``rejected_citation`` — the cited ids are empty or not a subset of that entry's
       displayed ids;
    3. ``rejected_no_change`` — the requested direction is ``no_change``;
    4. ``rejected_no_effect`` — the nudge does not move the value (zero-valued or
       absolute-bound entry). This is **not** the cumulative cap saturation — the cap
       is enforced by ``reconcile_world_model``, not the authority (Codex MED-1/6).

    Domain precondition (Codex MED-1): *exposed_citations* is built from the same
    ``reconciled.modulated`` as *swm* (the cycle's wiring invariant), so a displayed
    ``(axis, key)`` is always present in *swm* — the authority's defensive
    ``idx is None`` path is unreachable and is not given its own reject reason. A
    caller that violates this precondition is out of contract.
    """
    key = (hint.axis, hint.key)
    visible = exposed_citations.get(key)
    if visible is None:
        return "rejected_not_displayed"
    cited = set(hint.cited_memory_ids)
    if not cited or not cited.issubset(visible):
        return "rejected_citation"
    if hint.direction == "no_change":
        return "rejected_no_change"
    entry = next((e for e in swm.entries if (e.axis, e.key) == key), None)
    # Unreachable under the domain precondition (gate 1 passed -> entry present);
    # treated as no-effect rather than a phantom reason so the universe stays the
    # four authority gates.
    if entry is None:
        return "rejected_no_effect"
    new_value = _nudge_value(entry.value, hint.direction)
    if new_value is None or new_value == entry.value:
        return "rejected_no_effect"
    return "adopted"


def measure_adopted_signed_step(
    swm: SubjectiveWorldModel,
    nudged: SubjectiveWorldModel,
    *,
    axis: str,
    key: str,
) -> float:
    """Measured ``new_value - old_value`` of the nudged entry (補強 §1).

    *swm* is the pre-nudge ``reconciled.modulated``; *nudged* is the authority's
    returned SWM. Both contain the ``(axis, key)`` entry on an adopted path (the
    authority only returns non-``None`` after locating and moving it), so the lookup is
    total here. Signed: a ``weaken`` on a positive entry yields a negative step, a
    ``strengthen`` a positive one. Returns the real delta — which may be smaller than
    ``VALUE_STEP`` when ``weaken`` clamped at 0 (e.g. ``0.03 -> 0.0`` gives ``-0.03``).
    """
    old_value = next(e.value for e in swm.entries if (e.axis, e.key) == (axis, key))
    new_value = next(e.value for e in nudged.entries if (e.axis, e.key) == (axis, key))
    return new_value - old_value


def build_emitted_disposition(
    *,
    hint: WorldModelUpdateHint,
    exposed_citations: Mapping[tuple[str, str], frozenset[str]],
    swm: SubjectiveWorldModel,
    nudged: SubjectiveWorldModel | None,
    exposed_entry_count: int,
) -> WorldModelHintDisposition:
    """Build the carrier for a tick that emitted a hint (``llm_status='ok'``).

    The headline ``adopted`` vs rejected is taken from the authority's real return
    (*nudged*): ``adopted`` iff ``nudged is not None`` — the shadow classifier is only
    consulted to subdivide a rejection. ``adopted_signed_step`` is the measured delta on
    adoption, ``0.0`` otherwise.
    """
    if nudged is not None:
        disposition: HintDisposition = "adopted"
        signed_step = measure_adopted_signed_step(
            swm, nudged, axis=hint.axis, key=hint.key
        )
    else:
        disposition = classify_rejection_reason(hint, exposed_citations, swm)
        signed_step = 0.0
    return WorldModelHintDisposition(
        llm_status="ok",
        emitted=True,
        disposition=disposition,
        target_axis=hint.axis,
        target_key=hint.key,
        direction=hint.direction,
        adopted_signed_step=signed_step,
        exposed_entry_count=exposed_entry_count,
    )


def build_not_emitted_disposition(
    *,
    llm_status: LlmStatus,
    exposed_entry_count: int,
) -> WorldModelHintDisposition:
    """Build the ``not_emitted`` carrier (no hint this tick — ADR §3 / 補強 §4).

    Used on the normal path when ``plan.world_model_update_hint is None``
    (``llm_status='ok'``) **and** on the two fallback ticks that return before step 7.5
    (``llm_status`` = ``unavailable`` / ``unparseable``, Codex HIGH-1). All three target
    columns are ``None`` and the step is ``0.0``; ``exposed_entry_count`` is the flag-on
    ``exposed_citations`` size, available on both paths.
    """
    return WorldModelHintDisposition(
        llm_status=llm_status,
        emitted=False,
        disposition="not_emitted",
        target_axis=None,
        target_key=None,
        direction=None,
        adopted_signed_step=0.0,
        exposed_entry_count=exposed_entry_count,
    )


__all__ = [
    "LLM_STATUS_UNAVAILABLE",
    "LLM_STATUS_UNPARSEABLE",
    "LlmStatus",
    "build_emitted_disposition",
    "build_not_emitted_disposition",
    "classify_rejection_reason",
    "measure_adopted_signed_step",
]
