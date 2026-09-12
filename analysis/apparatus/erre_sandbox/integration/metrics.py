"""Shim re-export for the M2 thresholds.

The authoritative source has moved to :mod:`erre_sandbox.contracts.thresholds`
(codex review F5, 2026-04-28). This module is kept so that existing imports
``from erre_sandbox.integration import M2_THRESHOLDS, Thresholds`` and
``from erre_sandbox.integration.metrics import ...`` continue to resolve
without churning every callsite. New imports — especially from ``ui`` —
should target :mod:`erre_sandbox.contracts` directly.
"""

from __future__ import annotations

from erre_sandbox.contracts.thresholds import M2_THRESHOLDS, Thresholds

__all__ = ["M2_THRESHOLDS", "Thresholds"]
