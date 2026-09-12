"""LLM output parsing — JSON plan extraction with validation.

The LLM is prompted (see :mod:`cognition.prompting`) to return a single JSON
object matching :class:`LLMPlan`. This module is the single place where that
contract is enforced: malformed output collapses to ``None`` so the caller
(``cognition.cycle.CognitionCycle.step``) can fall back to the
"continue current action" path declared by ``docs/functional-design.md``
§2 error-condition row.

The parser tolerates common LLM idiosyncrasies (code fences, surrounding
prose, trailing whitespace) but does NOT try to salvage broken JSON — once
we mix forgiving heuristics and Pydantic validation we lose the ability to
tell "model misbehaved" from "adapter misbehaved".
"""

from __future__ import annotations

import json
import re
from typing import Final

from pydantic import BaseModel, ConfigDict, Field, ValidationError

# ``Zone`` / ``WorldModelUpdateHint`` stay runtime imports: they type
# :attr:`LLMPlan.destination_zone` / :attr:`LLMPlan.world_model_update_hint` and
# Pydantic resolves field types at model-build time, not under TYPE_CHECKING.
# The TC001 suppressions below are intentional for that reason.
from erre_sandbox.contracts.cognition_layers import WorldModelUpdateHint  # noqa: TC001
from erre_sandbox.schemas import Zone  # noqa: TC001

# Match ```json ... ``` or ``` ... ``` code fences (both common in LLM replies).
_FENCE_RE: Final[re.Pattern[str]] = re.compile(
    r"```(?:json)?\s*(.*?)\s*```",
    re.DOTALL | re.IGNORECASE,
)

MAX_RAW_PLAN_BYTES: Final[int] = 64 * 1024
"""Upper bound on raw LLM text before we refuse to parse (security M1).

Ollama with an unbounded ``num_predict`` has been observed producing
multi-MB loops. We stay well under Python's ``json.loads`` practical memory
footprint and Ollama's realistic output. If an honest response ever grows
past this, the plan schema has outgrown its design and needs a redesign,
not a larger buffer.
"""


class LLMPlan(BaseModel):
    """One tick of agent action parsed out of the LLM's JSON response.

    All fields are bounded so a mis-configured prompt / persona can never
    produce an out-of-range ``_Signed`` that would later fail Pydantic
    validation deep inside :mod:`cognition.state`.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    thought: str = Field(..., description="Internal monologue (may be persisted).")
    utterance: str | None = Field(
        default=None,
        description="Speech bubble content; ``None`` = stay silent.",
    )
    destination_zone: Zone | None = Field(
        default=None,
        description="Zone to walk to; ``None`` = stay put.",
    )
    animation: str | None = Field(
        default=None,
        description="Animation tag such as 'walk' / 'idle' / 'sit_seiza'.",
    )
    valence_delta: float = Field(default=0.0, ge=-1.0, le=1.0)
    arousal_delta: float = Field(default=0.0, ge=-1.0, le=1.0)
    motivation_delta: float = Field(default=0.0, ge=-1.0, le=1.0)
    importance_hint: float = Field(default=0.5, ge=0.0, le=1.0)
    # M6-A-3: optional reasoning rationale. Absence must not fail validation —
    # stable Ollama output is never 100% for added fields, and the plan's
    # action contract is independent of the reasoning trace.
    salient: str | None = Field(
        default=None,
        description="What the agent noticed as most salient this tick (xAI).",
    )
    decision: str | None = Field(
        default=None,
        description="One-sentence rationale behind the chosen action (xAI).",
    )
    next_intent: str | None = Field(
        default=None,
        description="Forward-looking intent surfaced for upcoming ticks (xAI).",
    )
    # M10-C: optional bounded world-model nudge. Absent on every flag-off turn
    # (the schema hint that elicits it is only shown when the individual layer is
    # enabled) and tolerated as ``None`` so existing parse behaviour is unchanged.
    # The LLM is a *candidate*: this hint is verified (cited ids must match the
    # displayed entry's belief citations) and applied as a bounded value nudge by
    # ``cognition.world_model.apply_world_model_update_hint`` — never trusted as-is.
    world_model_update_hint: WorldModelUpdateHint | None = Field(
        default=None,
        description="Bounded request to nudge a held world-model entry; null to skip.",
    )


def _find_matching_brace(text: str, start: int) -> int | None:
    r"""Return index of the ``}`` matching the ``{`` at *start*, or ``None``.

    Walks the string character by character, honouring double-quoted strings
    and ``\"`` escapes so embedded JSON strings don't throw off the depth.
    """
    depth = 0
    in_string = False
    escape = False
    for i in range(start, len(text)):
        ch = text[i]
        if in_string:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_string = False
            continue
        if ch == '"':
            in_string = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return i
    return None


def _extract_json_object(text: str) -> str | None:
    """Return the first balanced ``{...}`` block in *text*, or ``None``."""
    fence_match = _FENCE_RE.search(text)
    haystack = fence_match.group(1) if fence_match else text

    start = haystack.find("{")
    if start == -1:
        return None
    end = _find_matching_brace(haystack, start)
    if end is None:
        return None
    return haystack[start : end + 1]


def parse_llm_plan(text: str) -> LLMPlan | None:
    """Extract and validate an :class:`LLMPlan` from raw LLM text.

    Returns ``None`` on any failure — including missing JSON, malformed JSON,
    Pydantic validation error, or input exceeding :data:`MAX_RAW_PLAN_BYTES`
    (see security M1) — so the caller can deterministically route all of
    these to a single fallback branch.
    """
    if len(text) > MAX_RAW_PLAN_BYTES:
        return None
    raw = _extract_json_object(text)
    if raw is None:
        return None
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return None
    if not isinstance(payload, dict):
        return None
    try:
        return LLMPlan.model_validate(payload)
    except ValidationError:
        return None


__all__ = ["LLMPlan", "parse_llm_plan"]
