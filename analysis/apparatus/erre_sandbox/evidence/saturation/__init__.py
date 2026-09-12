"""SWM modulation saturation probe (new-module shadow).

A self-contained probe that measures whether the real cognition loop drives
``SubjectiveWorldModel`` modulation to the ``reconcile_world_model`` cap
boundary (``floor +/- MAX_TOTAL_MODULATION``). It owns its own lightweight
longitudinal trace + a pure loader, kept strictly separate from the
``evidence.individuation`` package so the frozen M11-C3b individuation gates and
the existing ``individual_state_trace`` measure are never touched (saturation ADR
section 5 / section B-5: new-module shadow, existing frozen measure not reused).

This subpackage implements only the **src + CPU-testable** half of the probe:
the trace schema/row-builder, the capture-substrate contract, and the scoring
loader. The real Ollama run, GPU execution, and the 3-way verdict are a separate
downstream task (saturation ADR section 9 — not authorised here).
"""

from __future__ import annotations
