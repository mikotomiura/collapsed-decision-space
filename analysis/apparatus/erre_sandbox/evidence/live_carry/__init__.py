"""III-a live §5.3 — cross-arm live-carry trajectory-contrast verdict scorer.

A **new-module shadow** (mirrors ``evidence.saturation`` /
``evidence.hint_engagement``): it reads the frozen III-a traces
(``swm_floor_input_trace`` / ``swm_modulation_saturation_trace`` /
``individual_state_trace``) from a 12-run paired-arm capture matrix and computes
the **verdict-readiness** of the live
§5.3 GO/NO-GO contrast (M0 fidelity / M1 distal separation / M2 boundedness /
null hierarchy → the four-state verdict), without ever touching the frozen
reconcile kernel, the frozen saturation constants, or the frozen
``world_model_overlap_jaccard_active`` distance body.

The single source of truth for every threshold/column it consumes is the **GPU
前 threshold freeze ADR** (``.steering/20260616-iiia-live-pregpu-freeze/``,
ACCEPTED 2026-06-16, binding=user). What this package produces is the *compute
path* a later GPU live exec re-scores — **not a verdict** (no GPU data exists
yet); see :mod:`.constants` for the forking-paths guard.
"""

from __future__ import annotations
