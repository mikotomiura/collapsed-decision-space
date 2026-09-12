"""Session lifecycle constants and phase enum for the T14 gateway (WS).

This module augments :mod:`erre_sandbox.schemas` §7 ``ControlEnvelope`` with the
**operational parameters** that the wire-type definitions intentionally do not
encode:

* heartbeat cadence — how often the server must push :class:`WorldTickMsg`
* handshake / idle-disconnect timeouts — session lifecycle bounds
* ``SessionPhase`` — explicit enum of session states, consumed by the T14
  gateway implementation and the T19 skeleton scenario tests

The wire types themselves (``HandshakeMsg``, ``AgentUpdateMsg``, ...) are **not**
redefined here. They live in :mod:`erre_sandbox.schemas` and are imported by
consumers directly — this module only owns timing and state-machine rules.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Final

# =============================================================================
# Session lifecycle constants
# =============================================================================

HEARTBEAT_INTERVAL_S: Final[float] = 1.0
"""Expected cadence of :class:`~erre_sandbox.schemas.WorldTickMsg` heartbeat.

Matches ``WorldRuntime._heartbeat_period`` default in :mod:`erre_sandbox.world.tick`.
Consumers (Godot client, monitor dashboards) may tolerate up to
``HEARTBEAT_INTERVAL_S * 3`` without raising a liveness alarm.
"""

HANDSHAKE_TIMEOUT_S: Final[float] = 5.0
"""Maximum time a peer has to send :class:`~erre_sandbox.schemas.HandshakeMsg`.

Measured from TCP accept / WS upgrade completion. Exceeding it causes the
gateway to close the socket with :class:`~erre_sandbox.schemas.ErrorMsg`
``code="handshake_timeout"``.
"""

IDLE_DISCONNECT_S: Final[float] = 60.0
"""Inactivity ceiling after which the gateway voluntarily closes a session.

Applies only once the session is :attr:`SessionPhase.ACTIVE`. During
``AWAITING_HANDSHAKE`` the stricter :data:`HANDSHAKE_TIMEOUT_S` governs.
"""

MAX_ENVELOPE_BACKLOG: Final[int] = 256
"""Maximum number of pending envelopes before the gateway drops the oldest.

The runtime queue (``WorldRuntime._envelopes``) is now bounded as well
(SH-5: ``maxsize=1024`` for the main queue plus a ``maxsize=1`` coalescing
heartbeat queue). The two layers stack: this gateway bound applies
per-client so a slow Godot viewer cannot exhaust server memory, while the
runtime bound protects against an upstream that never drains.
"""

DEFAULT_ALLOWED_ORIGINS: Final[tuple[str, ...]] = ()
"""Default origin allow-list — empty tuple disables Origin check (SH-2).

LAN-internal deployment runs without a reverse proxy so Godot's native WS
client sends no Origin header. Operators that expose the gateway through a
browser-driven dashboard (M10+) pass a non-empty tuple via ``BootConfig``
to enable per-Origin filtering. An empty tuple combined with
``host=0.0.0.0`` and ``require_token=False`` triggers a startup
``RuntimeError`` in :func:`erre_sandbox.bootstrap.bootstrap` so a careless
``--host=0.0.0.0`` flag cannot silently expose the server.
"""

MAX_ACTIVE_SESSIONS: Final[int] = 8
"""Session-count cap enforced by :class:`Registry` (SH-2).

Sized for the M10 working assumption: Mac+G-GEAR Godot viewers + curl probe
+ Slack bridge + 3 per-persona UI panels = 7, plus headroom = 8. The cap
is reached only when an attacker (or buggy client) opens connections in a
tight loop; legitimate UI clients reconnect, not stack. On overflow the
gateway closes the new socket with WebSocket close code ``1013``
(Try Again Later) so well-behaved clients back off instead of looping.
"""

SCHEMA_VERSION_HEADER: Final[str] = "X-Erre-Schema-Version"
"""HTTP header the gateway sets on the WS upgrade response.

Peers that don't send :class:`~erre_sandbox.schemas.HandshakeMsg` (e.g. debug
curl probes) can still discover the server's
:data:`~erre_sandbox.schemas.SCHEMA_VERSION` this way.
"""

SUBSCRIBE_QUERY_PARAM: Final[str] = "subscribe"
"""URL query-parameter name controlling per-session agent filtering.

Added by ``m4-gateway-multi-agent-stream``. Clients connecting to
``/ws/observe`` without this parameter receive every envelope (broadcast,
preserving M2 behaviour). A comma-separated list of ``persona_id`` values
restricts the session to envelopes whose routing set intersects the list.
The literal ``*`` is equivalent to omission.
"""

SUBSCRIBE_DELIMITER: Final[str] = ","
"""Delimiter used inside the ``?subscribe=`` query parameter."""

MAX_SUBSCRIBE_ITEMS: Final[int] = 32
"""Upper bound on the number of agent ids permitted in one ``?subscribe=``.

Defends against a pathological client sending a giant subscription list to
force linear-scan fan-out cost to blow up. 32 is >> any realistic persona
count (M4 uses 3; M10-11 projections are <20).
"""

MAX_SUBSCRIBE_ID_LENGTH: Final[int] = 64
"""Per-item length ceiling inside ``?subscribe=``.

``persona_id`` values are kebab-case slugs (see PersonaSpec) and never
exceed a few dozen characters; 64 leaves generous headroom while still
rejecting abusive inputs.
"""

MAX_SUBSCRIBE_RAW_LENGTH: Final[int] = (
    MAX_SUBSCRIBE_ITEMS * (MAX_SUBSCRIBE_ID_LENGTH + 1) + 1
)
"""Upper bound on the whole ``?subscribe=`` string before we attempt parse.

Cheap O(1) pre-check that rejects multi-megabyte payloads before ``split``
has a chance to allocate a long list of short strings behind a permissive
reverse proxy. Derived from :data:`MAX_SUBSCRIBE_ITEMS` and
:data:`MAX_SUBSCRIBE_ID_LENGTH` so bumping either one keeps this cap
consistent.
"""


# =============================================================================
# Session phase enum
# =============================================================================


class SessionCapExceededError(Exception):
    """Raised by :meth:`Registry.reserve_slot` when ``MAX_ACTIVE_SESSIONS`` is reached.

    The gateway converts this into a WebSocket close with code ``1013``
    (Try Again Later) so well-behaved clients back off rather than retry
    immediately in a tight loop. Carries the configured cap so callers can
    log the limit without re-importing the constant.
    """

    def __init__(self, *, current: int, cap: int) -> None:
        self.current = current
        self.cap = cap
        super().__init__(
            f"active session cap exceeded: {current} ≥ {cap}",
        )


class SessionPhase(StrEnum):
    """Explicit state-machine phases of a single WS session on the gateway.

    The T14 gateway implementation drives transitions strictly in this order:
    ``AWAITING_HANDSHAKE → ACTIVE → CLOSING``. No backwards transitions.

    Reconnection produces a fresh session (new ``SessionPhase`` instance).
    """

    AWAITING_HANDSHAKE = "awaiting_handshake"
    ACTIVE = "active"
    CLOSING = "closing"


__all__ = [
    "DEFAULT_ALLOWED_ORIGINS",
    "HANDSHAKE_TIMEOUT_S",
    "HEARTBEAT_INTERVAL_S",
    "IDLE_DISCONNECT_S",
    "MAX_ACTIVE_SESSIONS",
    "MAX_ENVELOPE_BACKLOG",
    "MAX_SUBSCRIBE_ID_LENGTH",
    "MAX_SUBSCRIBE_ITEMS",
    "MAX_SUBSCRIBE_RAW_LENGTH",
    "SCHEMA_VERSION_HEADER",
    "SUBSCRIBE_DELIMITER",
    "SUBSCRIBE_QUERY_PARAM",
    "SessionCapExceededError",
    "SessionPhase",
]
