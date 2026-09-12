"""Ollama ``/api/chat`` adapter with Contract-First :class:`ChatResponse`.

This module is the G-GEAR side entrypoint for local LLM inference during M2.
It intentionally mirrors the shape of
:class:`erre_sandbox.memory.embedding.EmbeddingClient` (ClassVar defaults,
DI-friendly ``client`` parameter, async context-manager semantics, single
``*Unavailable`` error) so that the two Ollama-backed adapters on G-GEAR are
symmetric and share the same mental model.

Scope boundary:

* T11 (this module) is responsible for the wire protocol, response
  normalisation, and error unification. It does NOT own retry loops, fallback
  policy, or logging context — those belong to T14 ``inference/server.py``.
* Sampling composition lives in :mod:`erre_sandbox.inference.sampling`; this
  adapter only consumes the already-composed :class:`ResolvedSampling`.
* Structured parsing of the assistant text (extracting actions, speech, etc.)
  is the T12 cognition cycle's responsibility.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, ClassVar, Final, Literal, Self

import httpx
from pydantic import BaseModel, ConfigDict, Field, ValidationError

if TYPE_CHECKING:
    from collections.abc import Sequence

    from erre_sandbox.inference.sampling import ResolvedSampling

# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------

DEFAULT_CHAT_MODEL: Final[str] = "qwen3:8b"
"""Model tag pulled on G-GEAR during T09.

Decisions D1 of ``20260418-model-pull-g-gear`` records the fallback from
``qwen3:8b-q5_K_M`` (not available in the Ollama registry) to ``qwen3:8b``.
Override per call via :meth:`OllamaChatClient.chat` ``model=...``.
"""


# ---------------------------------------------------------------------------
# Wire types — frozen Pydantic models so callers cannot accidentally mutate
# a request or response mid-flight.
# ---------------------------------------------------------------------------


class ChatMessage(BaseModel):
    """Single message in an Ollama ``/api/chat`` ``messages`` array.

    Constraining ``role`` to the three values Ollama accepts keeps callers
    honest — e.g. ``tool`` / ``function`` messages would need a schema change
    and deliberate consideration (M4+).
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    role: Literal["system", "user", "assistant"]
    content: str


class ChatResponse(BaseModel):
    """Normalised ``/api/chat`` response, backend-agnostic.

    This is the single shape every inference adapter (Ollama today, SGLang
    at M7+, vLLM at M9+) must return so the callers stay backend-agnostic.
    Provider-specific extras (``load_duration``, ``eval_duration``, etc.)
    are intentionally dropped; if performance instrumentation is needed in
    the future, add a dedicated ``diagnostics`` field under a ``schema_version``
    bump rather than leaking raw Ollama keys through this boundary.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    content: str = Field(..., description="Assistant message content.")
    model: str = Field(..., description="Model tag, e.g. 'qwen3:8b'.")
    eval_count: int = Field(
        ...,
        ge=0,
        description="Output tokens generated (Ollama `eval_count`).",
    )
    prompt_eval_count: int = Field(
        default=0,
        ge=0,
        description="Prompt tokens consumed (Ollama `prompt_eval_count`).",
    )
    total_duration_ms: float = Field(
        ...,
        ge=0.0,
        description=(
            "Wall-clock of the whole chat call in milliseconds. ``0.0`` both "
            "when the call was truly instantaneous and when Ollama omitted "
            "``total_duration`` (e.g. partial error payloads) — treat as "
            "best-effort instrumentation only."
        ),
    )
    finish_reason: Literal["stop", "length"] = Field(
        default="stop",
        description="'length' when the `num_predict` budget was exhausted.",
    )


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class OllamaUnavailableError(RuntimeError):
    """Raised when ``/api/chat`` is unreachable, errors, or malforms.

    Intentionally single-typed (mirroring ``EmbeddingUnavailableError`` from
    T10) so callers in T12 / T14 write one ``except`` branch per adapter.
    Inspect ``args[0]`` / ``str(exc)`` for the specific reason substring
    (``'timeout'``, ``'unreachable'``, ``'HTTP 500'``, ``'non-JSON'``,
    ``"missing 'message.content'"``, ``'failed to parse'``).
    """


# ---------------------------------------------------------------------------
# Client
# ---------------------------------------------------------------------------


class OllamaChatClient:
    """Asynchronous client for Ollama's ``/api/chat`` endpoint.

    Typical use::

        async with OllamaChatClient() as llm:
            resp = await llm.chat(
                [
                    ChatMessage(role="system", content=persona_prompt),
                    ChatMessage(role="user", content=observation),
                ],
                sampling=compose_sampling(
                    persona.default_sampling,
                    agent.erre.sampling_overrides,
                ),
                options={"num_predict": 256},
            )
            print(resp.content)

    The client takes an optional :class:`httpx.AsyncClient` so tests can inject
    an :class:`httpx.MockTransport` and production code can share a long-lived
    connection pool. When the ``client`` argument is ``None`` the adapter
    constructs and owns its own client (closed on ``async with`` exit).
    """

    DEFAULT_MODEL: ClassVar[str] = DEFAULT_CHAT_MODEL
    DEFAULT_ENDPOINT: ClassVar[str] = "http://127.0.0.1:11434"
    DEFAULT_TIMEOUT_SECONDS: ClassVar[float] = 60.0
    CHAT_PATH: ClassVar[str] = "/api/chat"

    def __init__(
        self,
        *,
        model: str | None = None,
        endpoint: str | None = None,
        timeout: float | None = None,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self.model = model or self.DEFAULT_MODEL
        self.endpoint = (endpoint or self.DEFAULT_ENDPOINT).rstrip("/")
        self._timeout = timeout if timeout is not None else self.DEFAULT_TIMEOUT_SECONDS
        self._client: httpx.AsyncClient = client or httpx.AsyncClient(
            base_url=self.endpoint,
            timeout=self._timeout,
        )
        self._owns_client = client is None

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(self, *_exc_info: object) -> None:
        await self.close()

    async def close(self) -> None:
        if self._owns_client and not self._client.is_closed:
            await self._client.aclose()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def chat(
        self,
        messages: Sequence[ChatMessage],
        *,
        sampling: ResolvedSampling,
        model: str | None = None,
        options: dict[str, Any] | None = None,
        think: bool | None = None,
    ) -> ChatResponse:
        """Send a chat completion and return a normalised :class:`ChatResponse`.

        Args:
            messages: Role-tagged messages; Ollama accepts system/user/assistant.
            sampling: Pre-composed sampling (see
                :func:`erre_sandbox.inference.sampling.compose_sampling`).
                Requiring this type in the signature makes it impossible to
                forget ERRE delta composition or the clamp.
            model: One-shot override of :attr:`DEFAULT_MODEL` for this call.
            options: Extra Ollama ``options`` keys (``num_ctx``, ``num_predict``,
                ``stop``, …) passed through as-is. The sampling values
                (``temperature`` / ``top_p`` / ``repeat_penalty``) are applied
                **after** these, so a caller cannot accidentally override the
                clamped sampling.
            think: Top-level Ollama payload flag controlling thinking-model
                reasoning on models like qwen3. ``None`` (default) omits the
                key entirely, preserving the M2 wire shape for existing
                callers (``cognition.cycle`` / ``Reflector``). ``False``
                suppresses hidden reasoning — required for dialog_turn
                generation on qwen3:8b where the default spends the response
                budget on <think> tokens and returns empty content
                (validated in the M5 LLM spike).
                Must be set at the body top level, not inside ``options``.

        Raises:
            OllamaUnavailableError: When the request cannot be delivered, the
                server responds non-2xx, or the payload cannot be parsed as a
                :class:`ChatResponse`.
        """
        body = self._build_body(messages, sampling, model, options, think)
        payload = await self._post(body)
        return self._parse(payload)

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _build_body(
        self,
        messages: Sequence[ChatMessage],
        sampling: ResolvedSampling,
        model: str | None,
        options: dict[str, Any] | None,
        think: bool | None,  # noqa: FBT001 — private helper; public ``chat`` makes it kw-only
    ) -> dict[str, Any]:
        merged_options: dict[str, Any] = dict(options or {})
        # Sampling is authoritative — intentionally overwrite any caller-supplied
        # duplicates so T12 cannot silently regress the clamp (design.md §2.2).
        merged_options["temperature"] = sampling.temperature
        merged_options["top_p"] = sampling.top_p
        merged_options["repeat_penalty"] = sampling.repeat_penalty
        body: dict[str, Any] = {
            "model": model or self.model,
            "messages": [m.model_dump() for m in messages],
            "stream": False,
            "options": merged_options,
        }
        # Guarded: only emit ``think`` when the caller explicitly opted in.
        # ``None`` default preserves the pre-M5 wire shape for cognition /
        # reflection paths, which would otherwise silently suppress qwen3
        # thinking on every tick.
        if think is not None:
            body["think"] = think
        return body

    async def health_check(self) -> None:
        """Verify Ollama is reachable. Raise ``OllamaUnavailableError`` if not.

        Probes ``GET /api/tags`` which is a cheap listing endpoint that does
        not load a model. Used by the orchestrator at startup (fail-fast so
        the operator notices immediately instead of hitting the first
        cognition tick 10s later).
        """
        try:
            response = await self._client.get("/api/tags")
        except httpx.TimeoutException as exc:
            raise OllamaUnavailableError(
                f"Ollama /api/tags timeout after {self._timeout}s: {exc!r}",
            ) from exc
        except httpx.HTTPError as exc:
            raise OllamaUnavailableError(
                f"Ollama /api/tags unreachable at {self.endpoint}: {exc!r}",
            ) from exc
        if response.status_code != httpx.codes.OK:
            raise OllamaUnavailableError(
                f"Ollama /api/tags returned HTTP {response.status_code}",
            )

    async def _post(self, body: dict[str, Any]) -> dict[str, Any]:
        try:
            response = await self._client.post(self.CHAT_PATH, json=body)
        except httpx.TimeoutException as exc:
            raise OllamaUnavailableError(
                f"Ollama {self.CHAT_PATH} timeout after {self._timeout}s: {exc!r}",
            ) from exc
        except httpx.HTTPError as exc:
            raise OllamaUnavailableError(
                f"Ollama {self.CHAT_PATH} unreachable at {self.endpoint}: {exc!r}",
            ) from exc

        if response.status_code != httpx.codes.OK:
            raise OllamaUnavailableError(
                f"Ollama {self.CHAT_PATH} returned HTTP {response.status_code}: "
                f"{response.text[:200]}",
            )

        try:
            payload = response.json()
        except ValueError as exc:
            raise OllamaUnavailableError(
                f"Ollama {self.CHAT_PATH} returned non-JSON payload: {exc!r}",
            ) from exc

        if not isinstance(payload, dict):
            raise OllamaUnavailableError(
                f"Ollama {self.CHAT_PATH} returned non-object JSON: {payload!r}",
            )
        return payload

    @staticmethod
    def _parse(payload: dict[str, Any]) -> ChatResponse:
        message = payload.get("message")
        if not isinstance(message, dict) or "content" not in message:
            # Log only the top-level key set — never the raw payload, which may
            # contain echoed persona prompts or conversation history (see
            # code-reviewer MEDIUM-4 / security MEDIUM-2).
            raise OllamaUnavailableError(
                "Ollama /api/chat payload missing 'message.content' "
                f"(top-level keys: {sorted(payload.keys())})",
            )
        total_ns = payload.get("total_duration", 0)
        done_reason = payload.get("done_reason", "stop")
        finish_reason: Literal["stop", "length"] = (
            "length" if done_reason == "length" else "stop"
        )
        try:
            return ChatResponse(
                content=str(message["content"]),
                model=str(payload.get("model", "unknown")),
                eval_count=int(payload.get("eval_count", 0)),
                prompt_eval_count=int(payload.get("prompt_eval_count", 0)),
                total_duration_ms=float(total_ns) / 1_000_000.0,
                finish_reason=finish_reason,
            )
        except (ValidationError, TypeError, ValueError) as exc:
            raise OllamaUnavailableError(
                f"Ollama /api/chat payload failed to parse as ChatResponse "
                f"(top-level keys: {sorted(payload.keys())}): {type(exc).__name__}",
            ) from exc


__all__ = [
    "DEFAULT_CHAT_MODEL",
    "ChatMessage",
    "ChatResponse",
    "OllamaChatClient",
    "OllamaUnavailableError",
]
