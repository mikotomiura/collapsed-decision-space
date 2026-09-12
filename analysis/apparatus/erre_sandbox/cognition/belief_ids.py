"""Deterministic belief-record id — the single source of truth (M10-C LOW-1).

Both :mod:`erre_sandbox.cognition.belief` (which *mints* belief-promoted
:class:`~erre_sandbox.schemas.SemanticMemoryRecord` rows) and
:mod:`erre_sandbox.cognition.world_model` (which *matches* promoted records to
their bonds) need the same ``belief_{agent}__{other}`` encoding. They used to
carry private copies kept in lockstep by a parity test; M10-C promotes the
encoding to one public helper so the citation-verification path
(:func:`erre_sandbox.cognition.world_model.apply_world_model_update_hint`) has a
single, importable definition (decisions.md DA-M10C-10).
"""

from __future__ import annotations


def belief_record_id(agent_id: str, other_agent_id: str) -> str:
    """Return the deterministic belief-record id for an ``(agent, other)`` dyad.

    Encoding ``(agent, other)`` rather than the bond's hash means a refreshed
    promotion always lands on the same row regardless of how the bond's affinity
    drifted between calls, keeping the semantic table bounded by
    ``O(agent_pairs)`` rather than ``O(promotions)``.
    """
    return f"belief_{agent_id}__{other_agent_id}"


__all__ = ["belief_record_id"]
