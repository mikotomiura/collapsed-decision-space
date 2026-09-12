"""ECL v0 embodied integration harness (M13, Issue 004).

Public surface for the determinism record/replay harness that drives the Issue
003 live seam (``cognition/cycle.py`` + ``world/tick.py``, both unmodified):

* :func:`run_ecl_loop` — construct the frozen determinism handles and step the
  two-axis (cognition + 30 Hz physics) loop for one embodied agent.
* :class:`RecordReplayChatClient` / :class:`RecordedLlmCall` — Plane 2
  record/replay LLM adapter and its captured-call unit.
* :class:`EclTraceRow` / :func:`ecl_trace_checksum` — per-physics-tick trace row
  and its SHA-256 replay checksum (reproducibility witness, *not* a metric).
* :class:`EclDecisionRecord` — per-cognition-tick full LLM provenance.
* :class:`EclRunResult` / :func:`replay_client_from` — run outcome and the helper
  that seeds a replay run from a prior run's recorded decisions.

Layer discipline (architecture-rules): ``integration`` may import every lower
layer, so this harness imports ``cognition`` / ``world`` / ``memory`` / ``schemas``
freely. It imports **no** ``evidence`` / ``spdm`` / ``runningness`` machinery and
emits no floor / landscape / verdict statistic (measurement-line non-re-entry,
design-final.md §論点4).
"""

from erre_sandbox.integration.embodied.loop import (
    DEFAULT_PHYSICS_TICKS_PER_COGNITION,
    GOLDEN_COGNITION_TICKS,
    EclDecisionRecord,
    EclReplayError,
    EclRunResult,
    EclTraceRow,
    RecordedLlmCall,
    RecordReplayChatClient,
    ecl_trace_checksum,
    replay_client_from,
    run_ecl_loop,
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
