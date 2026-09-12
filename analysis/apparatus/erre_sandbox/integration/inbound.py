"""Inbound (client -> server) stimulus wiring — Issue 001 (construction).

FROZEN ADR ``.steering/20260724-m13-live-loop-closure/design-final.md``
(Plan + Codex independent review, Adopt-with-changes). This module is part of
the M13 live-loop-closure milestone's **inbound face**: it turns a bounded
:class:`~erre_sandbox.schemas.WorldPerturbationMsg` Godot sends over
:data:`~erre_sandbox.schemas.InboundEnvelope` into a
:class:`~erre_sandbox.schemas.PerceptionEvent` the cognition loop already
knows how to read via ``world.tick.step_cognition_once`` /
``inject_observation``.

**Honest framing (binding, design-final.md §2)**: this is *wiring*, not
aha / emergence / effect. :func:`world_perturbation_to_perception` is a pure
mapping — it computes no floor / landscape / verdict / divergence /
magnitude / detectability / aha-proxy statistic, and it does not itself
inject anything into a running loop (that is a later issue's
``InboundSink``). construction-only, measurement non-reentrant.

**Issue 002 adds** :class:`InboundSink` — the ``asyncio.Queue`` wrapper +
correlation-id assignment the gateway's opt-in ``inbound_sink`` parameter
(``integration/gateway.py``) pushes parsed :class:`WorldPerturbationMsg`
frames into. It remains pure plumbing: no LLM / embedding / DB dependency,
no floor / verdict / divergence computation — just FIFO enqueue/drain with a
bounded, deterministic overflow policy (LOW-1,
``design-final.md`` §3 DA-1 step 1 / decisions.md LOW-1).

**correlation_id is dropped here, not carried onto ``PerceptionEvent``**
(grill G2, design-final.md DA-2): the W-live closure witness traces a
perturbation across seams via the driven loop's own per-tick trace
structure, not by widening the existing (organ-consumed) observation
schema. ``WorldPerturbationMsg.correlation_id`` is available to the caller
directly off ``msg`` for that bookkeeping; it is simply not one of the
fields this mapping copies onto the returned :class:`PerceptionEvent`.

Mirrors ``integration.embodied.traversal_live.traversal_observation_factory``
(traversal_live.py:243-285): a world stimulus -> :class:`PerceptionEvent`
mapping with a fixed ``event_type="perception"`` shape, no side effects.

Layer dependency (``architecture-rules`` skill): ``integration/`` may import
``erre_sandbox.schemas`` (and, in general, ``inference`` / ``memory`` /
``cognition`` / ``world``); this module only needs ``schemas``.
"""

from __future__ import annotations

import asyncio

from erre_sandbox.schemas import PerceptionEvent, WorldPerturbationMsg


def world_perturbation_to_perception(
    msg: WorldPerturbationMsg,
    *,
    tick: int,
) -> PerceptionEvent:
    """Map an inbound world stimulus onto the observation the loop consumes.

    Pure function — no I/O, no mutation of ``msg``, no touching any runtime
    or memory state. ``tick`` is supplied by the caller (the driven loop's
    current cognition tick) rather than read off ``msg`` because
    :class:`WorldPerturbationMsg` is a wire message that may have been
    queued for one or more ticks before being drained (design-final.md
    DA-1 step 1: "inbound 摂動キューを drain"); the :class:`PerceptionEvent`
    must carry the tick it is actually being injected into.

    Field mapping (design-final.md DA-2 "意味論"):

    * ``msg.target_agent_id`` -> ``agent_id`` (the observing agent).
    * ``msg.modality`` / ``msg.source_zone`` / ``msg.content`` /
      ``msg.intensity`` copy through unchanged.
    * ``source_agent_id=None`` always — a :class:`WorldPerturbationMsg` is
      by construction an *environmental* stimulus (Godot/world side), never
      attributed to another agent (mirrors
      ``PerceptionEvent.source_agent_id``'s "environmental" convention and
      ``traversal_observation_factory``'s fixed environmental
      ``source_zone``).
    * ``msg.correlation_id`` is intentionally **not** copied onto the
      returned :class:`PerceptionEvent` — see module docstring / grill G2.
    """
    return PerceptionEvent(
        tick=tick,
        agent_id=msg.target_agent_id,
        modality=msg.modality,
        source_agent_id=None,
        source_zone=msg.source_zone,
        content=msg.content,
        intensity=msg.intensity,
    )


class InboundSink:
    """Bounded, in-memory FIFO queue of parsed :class:`WorldPerturbationMsg`.

    The gateway's opt-in ``inbound_sink`` parameter (Issue 002,
    ``integration/gateway.py``'s ``_recv_loop`` / ``make_app`` / ``ws_observe``)
    pushes every successfully-parsed inbound frame here; the closure
    composition root (a later issue) drains it once per driven tick. Pure
    plumbing — no LLM / embedding / DB dependency, no I/O beyond the
    ``asyncio.Queue`` itself.

    **Overflow policy (LOW-1, design-final.md DA-1 step 1 / decisions.md
    LOW-1)**: bounded queue, FIFO, drop-oldest on overflow — the same shape
    as :meth:`erre_sandbox.world.tick.WorldRuntime._enqueue_with_drop_oldest`
    (world/tick.py) and :meth:`erre_sandbox.integration.gateway.Registry.fan_out`,
    minus the warning-envelope side channel (this sink has no outbound
    protocol to warn over — the drop is only observable via :attr:`dropped`).

    **Determinism (binding)**: correlation-id assignment uses a monotonically
    increasing in-process counter (``self._seq``), never ``datetime.now()``
    or ``random`` — so the sequence of ids issued for a given call order is
    reproducible.
    """

    def __init__(self, *, maxsize: int = 256) -> None:
        self._queue: asyncio.Queue[WorldPerturbationMsg] = asyncio.Queue(
            maxsize=maxsize,
        )
        self._seq: int = 0
        self._dropped: int = 0

    @property
    def dropped(self) -> int:
        """Count of messages evicted by the drop-oldest overflow policy."""
        return self._dropped

    def push(self, msg: WorldPerturbationMsg) -> WorldPerturbationMsg:
        """Enqueue ``msg``, assigning a correlation-id when the client left it blank.

        A client-supplied ``correlation_id`` (non-empty string) is preserved
        unchanged. An empty ``correlation_id`` (the schema default) is
        replaced with ``f"wp-{self._seq}"`` via ``model_copy`` — ``msg``
        itself is never mutated. ``self._seq`` advances on every call
        (whether or not this particular message needed a synthesized id) so
        it doubles as a monotonic push-count.

        On a full queue the oldest entry is evicted (get_nowait) before the
        new one is enqueued (put_nowait) — same drop-oldest shape as
        ``world/tick.py::_enqueue_with_drop_oldest``. Returns the (possibly
        id-assigned) message that was actually enqueued.
        """
        if msg.correlation_id == "":
            msg = msg.model_copy(update={"correlation_id": f"wp-{self._seq}"})
        self._seq += 1
        if self._queue.maxsize > 0 and self._queue.full():
            try:
                self._queue.get_nowait()
                self._dropped += 1
            except asyncio.QueueEmpty:  # pragma: no cover — defensive
                pass
        self._queue.put_nowait(msg)
        return msg

    def drain(self, max_n: int) -> list[WorldPerturbationMsg]:
        """Pop up to ``max_n`` messages in FIFO (push) order.

        Non-blocking: stops early if the queue empties before ``max_n`` is
        reached. Intended to be called once per driven cognition tick
        (design-final.md DA-1 step 1: "tick 毎 max_drain").
        """
        out: list[WorldPerturbationMsg] = []
        while len(out) < max_n:
            try:
                out.append(self._queue.get_nowait())
            except asyncio.QueueEmpty:
                break
        return out
