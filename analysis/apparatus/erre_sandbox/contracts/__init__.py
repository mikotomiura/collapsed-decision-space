"""Boundary-safe contract definitions importable from any layer.

The ``contracts`` package holds light-weight Pydantic models and frozen
configuration constants that are shared across architectural layers
(``ui``, ``integration``, ``world``, ``cognition``, ``memory``,
``inference``). Modules placed here MUST depend only on
:mod:`erre_sandbox.schemas` and the standard library / pydantic — never
on heavier layers — so that any caller (notably ``ui``) can import them
without dragging in a transitive ``inference`` / ``fastapi`` graph.

The package was introduced 2026-04-28 as the resolution of codex review
F5: ``ui/dashboard/state.py`` previously imported ``M2_THRESHOLDS`` and
``Thresholds`` from :mod:`erre_sandbox.integration`, which violated the
``architecture-rules`` SKILL invariant ``ui → schemas only``. Hosting
those acceptance thresholds in :mod:`.thresholds` and re-exporting them
through this ``__init__`` lets ``ui`` depend on a contract-only path
while :mod:`erre_sandbox.integration.metrics` keeps a thin shim for
back-compat with existing tests.
"""

from __future__ import annotations

from erre_sandbox.contracts.thresholds import M2_THRESHOLDS, Thresholds

__all__ = ["M2_THRESHOLDS", "Thresholds"]
