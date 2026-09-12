"""SGLang LoRA-aware chat adapter (OpenAI-compatible) — m9-c-spike Phase H.

This module mirrors :mod:`erre_sandbox.inference.ollama_adapter` (DI-friendly
``client`` parameter, ``_owns_client`` flag, async context-manager semantics,
single ``*Unavailable`` error type) so the two backend adapters on G-GEAR
share the same mental model.

Scope boundary (m9-c-spike design-final.md / decisions.md CS-1 / CS-2 / CS-9):

* ``SGLangChatClient`` consumes a pre-composed :class:`ResolvedSampling` and
  emits the request via the OpenAI-compatible ``/v1/chat/completions``
  endpoint that SGLang serves. Sampling composition stays in
  :mod:`erre_sandbox.inference.sampling` — this adapter only consumes the
  clamped output.
* LoRA lifecycle is driven by ``POST /load_lora_adapter`` /
  ``POST /unload_lora_adapter``. SGLang 0.5.10.post1 does NOT document a
  ``GET /list_lora_adapters`` endpoint (CS-2), so the client maintains an
  internal ``_loaded`` registry that is reconciled with the server through
  the load/unload responses. Callers query the registry via
  :attr:`SGLangChatClient.loaded_adapters` (immutable view); there is no
  server-round-trip alternative by design.
* :class:`LoRAAdapterRef` carries ERRE-internal naming (``adapter_name`` /
  ``weight_path`` / ``pinned``) but serialises to the SGLang wire fields
  (``lora_name`` / ``lora_path`` / ``pinned``) at the boundary (LOW-3).
* Mock LoRA detection: when a ref carries ``is_mock=True`` the adapter logs
  a warning at load time but does not block the load (CS-9). Production
  loaders should reject mock adapters at policy level, not here.
* DB3 fallback fire policy (CS-8): API failure / format reject / FSM
  regression are immediate triggers. Latency / N=3 throughput collapse
  observed via mock-LoRA are diagnostic only and require real-Kant
  confirmation before vLLM migration is fired.

The sglang Python package is intentionally NOT imported — this adapter
talks to SGLang over plain HTTP, so unit tests can run without the heavy
CUDA-bound install (``[inference]`` extras are only needed when actually
booting the SGLang server on G-GEAR).
"""

from __future__ import annotations

import logging
from pathlib import (
    Path,  # noqa: TC003 — Pydantic v2 needs runtime resolution for LoRAAdapterRef.weight_path
)
from types import MappingProxyType
from typing import TYPE_CHECKING, Any, ClassVar, Final, Literal, Self

import httpx
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from erre_sandbox.inference.ollama_adapter import ChatMessage, ChatResponse

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

    from erre_sandbox.inference.sampling import ResolvedSampling

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------

DEFAULT_SGLANG_MODEL: Final[str] = "qwen/Qwen3-8B"
"""Base model served by SGLang on G-GEAR for the m9-c-spike (CS-1 / CS-5).

The HuggingFace model id (lowercase ``qwen/Qwen3-8B``) is what the SGLang
launch command (``--model qwen/Qwen3-8B``) and the Phase K-α handoff prompt
expect. Override per call via :meth:`SGLangChatClient.chat` ``model=...``.
"""

DEFAULT_SGLANG_VERSION: Final[str] = "0.5.10.post1"
"""SGLang version pin (CS-1, decisions.md).

Recorded as a constant for traceability — the actual install pin lives in
``pyproject.toml`` ``[inference]`` extras. Bumping this constant signals an
ADR re-open (CS-1 re-open conditions).
"""

NO_LORA_SENTINEL: Final[str] = "no_lora"
"""Sentinel value for :meth:`SGLangChatClient.chat` ``adapter=`` to dispatch
to the base model (per-language routing).

Per-language routing requires every chat call to declare its adapter
intent explicitly — there is no implicit ``None → base`` fallback anymore.
Callers that intentionally route to the base model (e.g. ja stimuli with
no Japanese LoRA) pass this sentinel; everything else must be a name that
appears in :attr:`SGLangChatClient.loaded_adapters` or the call fails fast
with :class:`ValueError` before any network round-trip.
"""


# ---------------------------------------------------------------------------
# LoRA adapter reference
# ---------------------------------------------------------------------------


class LoRAAdapterRef(BaseModel):
    """Reference to a single LoRA adapter for SGLang load/unload (CS-2 / CS-9).

    Internal ERRE naming (``adapter_name`` / ``weight_path``) lives at the
    Python boundary; the wire form (``lora_name`` / ``lora_path``) is
    constructed in :meth:`SGLangChatClient.load_adapter` so the rest of the
    codebase can stay in ERRE-style naming. ``frozen=True`` keeps a ref
    immutable once handed to the registry.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    adapter_name: str = Field(
        ...,
        min_length=1,
        description="ERRE-side adapter name (serialises to SGLang ``lora_name``).",
    )
    weight_path: Path = Field(
        ...,
        description=(
            "PEFT directory containing ``adapter_config.json`` and "
            "``adapter_model.safetensors``. Serialises to SGLang ``lora_path``."
        ),
    )
    base_model: str = Field(
        default=DEFAULT_SGLANG_MODEL,
        description=(
            "HuggingFace base model id the adapter targets (CS-5: rank=8 continuity)."
        ),
    )
    rank: int = Field(
        default=8,
        ge=1,
        description=(
            "LoRA rank — must match ``--max-lora-rank`` on the server (CS-1 / CS-5)."
        ),
    )
    pinned: bool = Field(
        default=False,
        description=(
            "When True the SGLang server keeps the adapter resident across batches."
        ),
    )
    is_mock: bool = Field(
        default=False,
        description=(
            "Client-only flag (NOT serialised on the wire). When True the "
            "loader emits a warning so spike runs cannot silently masquerade "
            "as production loads (CS-9 sentinel)."
        ),
    )


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class SGLangUnavailableError(RuntimeError):
    """Raised when SGLang is unreachable, errors, or malforms a payload.

    Symmetric to :class:`erre_sandbox.inference.ollama_adapter.OllamaUnavailableError`
    so callers can write a single ``except`` branch per backend. Inspect
    ``str(exc)`` for the specific reason substring (``'timeout'``,
    ``'unreachable'``, ``'HTTP 500'``, ``'non-JSON'``,
    ``"missing 'choices'"``, ``'failed to parse'``).
    """


# ---------------------------------------------------------------------------
# Client
# ---------------------------------------------------------------------------


class SGLangChatClient:
    """Asynchronous client for SGLang's LoRA-aware chat endpoints.

    Typical use::

        ref = LoRAAdapterRef(
            adapter_name="kant_r8",
            weight_path=Path("/var/lora/kant_r8"),
            rank=8,
        )
        async with SGLangChatClient(base_url="http://g-gear:30000") as llm:
            await llm.load_adapter(ref)
            resp = await llm.chat(
                [
                    ChatMessage(role="system", content=persona_prompt),
                    ChatMessage(role="user", content=observation),
                ],
                sampling=compose_sampling(
                    persona.default_sampling, agent.erre.sampling_overrides
                ),
                adapter="kant_r8",
            )

    The client takes an optional :class:`httpx.AsyncClient` so tests can
    inject an :class:`httpx.MockTransport` and production code can share a
    long-lived connection pool. When the ``client`` argument is ``None`` the
    adapter constructs and owns its own client (closed on ``async with`` exit).

    Adapter state reconciliation (CS-2):

    * :meth:`load_adapter` — POSTs ``/load_lora_adapter``; on 2xx the ref is
      stored in ``_loaded`` keyed by ``adapter_name``. The same ref re-loaded
      is idempotent (same key in, same key out — the registry tolerates the
      second 2xx by overwriting).
    * :meth:`unload_adapter` — POSTs ``/unload_lora_adapter``; on 2xx the
      key is removed (``pop(name, None)`` so an unknown name never raises).
    * :attr:`loaded_adapters` — read-only mapping view of the internal
      registry. There is no server-round-trip query (HIGH-1: SGLang
      0.5.10.post1 docs has no documented ``/list_lora_adapters``).
    """

    DEFAULT_MODEL: ClassVar[str] = DEFAULT_SGLANG_MODEL
    DEFAULT_ENDPOINT: ClassVar[str] = "http://127.0.0.1:30000"
    DEFAULT_TIMEOUT_SECONDS: ClassVar[float] = 60.0
    CHAT_PATH: ClassVar[str] = "/v1/chat/completions"
    LOAD_LORA_PATH: ClassVar[str] = "/load_lora_adapter"
    UNLOAD_LORA_PATH: ClassVar[str] = "/unload_lora_adapter"
    HEALTH_PATH: ClassVar[str] = "/health"

    def __init__(
        self,
        *,
        model: str | None = None,
        endpoint: str | None = None,
        timeout: float | None = None,
        sglang_version: str = DEFAULT_SGLANG_VERSION,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self.model = model or self.DEFAULT_MODEL
        self.endpoint = (endpoint or self.DEFAULT_ENDPOINT).rstrip("/")
        self._timeout = timeout if timeout is not None else self.DEFAULT_TIMEOUT_SECONDS
        self.sglang_version = sglang_version
        self._client: httpx.AsyncClient = client or httpx.AsyncClient(
            base_url=self.endpoint,
            timeout=self._timeout,
        )
        self._owns_client = client is None
        self._loaded: dict[str, LoRAAdapterRef] = {}

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(self, *_exc_info: object) -> None:
        await self.close()

    async def close(self) -> None:
        if self._owns_client and not self._client.is_closed:
            await self._client.aclose()

    # ------------------------------------------------------------------
    # Adapter lifecycle (CS-2 / CS-9)
    # ------------------------------------------------------------------

    @property
    def loaded_adapters(self) -> Mapping[str, LoRAAdapterRef]:
        """Immutable view of the client-side adapter registry (CS-2).

        Returns:
            A :class:`types.MappingProxyType` over ``_loaded``. Mutation by the
            caller is impossible (the proxy raises ``TypeError`` on assignment).
        """
        return MappingProxyType(self._loaded)

    async def load_adapter(self, ref: LoRAAdapterRef) -> None:
        """POST ``/load_lora_adapter`` and update the client-side registry.

        Idempotent — re-loading the same ``adapter_name`` with the same ref
        overwrites the registry entry (the server-side 2xx is what actually
        determines success; the registry is a local mirror).

        Args:
            ref: The adapter to load. ``ref.adapter_name`` becomes the
                registry key; ``ref.weight_path`` is sent as ``lora_path``.

        Raises:
            SGLangUnavailableError: When the request cannot be delivered or
                the server responds non-2xx. The registry is NOT mutated on
                failure (the caller's ``_loaded`` view stays consistent
                with the server's actual state).
        """
        body = {
            "lora_name": ref.adapter_name,
            "lora_path": str(ref.weight_path),
            "pinned": ref.pinned,
        }
        await self._post(self.LOAD_LORA_PATH, body)
        if ref.is_mock:
            logger.warning(
                "loaded mock LoRA adapter %r from %s — production loaders "
                "should reject mock=true sentinels at policy level (CS-9)",
                ref.adapter_name,
                ref.weight_path,
            )
        self._loaded[ref.adapter_name] = ref

    async def unload_adapter(self, name: str) -> None:
        """POST ``/unload_lora_adapter`` and remove the registry entry.

        Idempotent — unloading an unknown name does not raise; the registry
        ``pop(name, None)`` swallows the missing key. The server-side
        contract for unknown adapters is left to SGLang (typically 2xx
        with a no-op semantic, but if it returns 4xx the
        :class:`SGLangUnavailableError` propagates).

        Args:
            name: The ``adapter_name`` to unload.

        Raises:
            SGLangUnavailableError: When the request cannot be delivered or
                the server responds non-2xx.
        """
        body = {"lora_name": name}
        await self._post(self.UNLOAD_LORA_PATH, body)
        self._loaded.pop(name, None)

    # ------------------------------------------------------------------
    # Chat -- OpenAI-compatible request
    # ------------------------------------------------------------------

    async def chat(
        self,
        messages: Sequence[ChatMessage],
        *,
        sampling: ResolvedSampling,
        adapter: str,
        model: str | None = None,
        options: dict[str, Any] | None = None,
    ) -> ChatResponse:
        """Send a chat completion via SGLang and return a normalised response.

        Args:
            messages: Role-tagged messages (system / user / assistant); shared
                wire type with the Ollama adapter.
            sampling: Pre-composed sampling (see
                :func:`erre_sandbox.inference.sampling.compose_sampling`).
                Sampling values are authoritative — caller-supplied
                ``temperature`` / ``top_p`` / ``repetition_penalty`` keys in
                ``options`` are overwritten.
            adapter: Required. ``adapter_name`` of a previously loaded LoRA
                (must appear in :attr:`loaded_adapters`) **or**
                :data:`NO_LORA_SENTINEL` to dispatch to the base model.
                Passing any other unknown name fails fast with
                :class:`ValueError` before any network round-trip
                (per-language routing requires explicit
                adapter intent on every call; CS-2: adapter routing is the
                client's responsibility, not the server's).
            model: One-shot override of :attr:`DEFAULT_MODEL`.
            options: Extra OpenAI-compatible request keys (``max_tokens``,
                ``stop``, …). ``temperature`` / ``top_p`` /
                ``repetition_penalty`` here are silently overridden by
                ``sampling`` (mirrors the Ollama adapter's clamp invariant).

        Raises:
            ValueError: ``adapter`` is neither :data:`NO_LORA_SENTINEL` nor
                in :attr:`loaded_adapters`.
            SGLangUnavailableError: When the request cannot be delivered,
                the server responds non-2xx, or the payload cannot be
                parsed as a :class:`ChatResponse`.
        """
        if adapter != NO_LORA_SENTINEL and adapter not in self._loaded:
            raise ValueError(
                f"adapter {adapter!r} is not loaded; call load_adapter() first "
                f"or pass NO_LORA_SENTINEL={NO_LORA_SENTINEL!r} to route to the "
                f"base model (loaded: {sorted(self._loaded)})",
            )
        body = self._build_body(messages, sampling, model, options, adapter)
        payload = await self._post(self.CHAT_PATH, body)
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
        adapter: str,
    ) -> dict[str, Any]:
        merged: dict[str, Any] = dict(options or {})
        # Sampling is authoritative — overwrite any caller-supplied duplicates
        # so spike callers cannot regress the clamp invariant (mirrors the
        # Ollama adapter, see ollama_adapter.py _build_body).
        merged["temperature"] = sampling.temperature
        merged["top_p"] = sampling.top_p
        merged["repetition_penalty"] = sampling.repeat_penalty
        body: dict[str, Any] = {
            "model": model or self.model,
            "messages": [m.model_dump() for m in messages],
            "stream": False,
        }
        # OpenAI-compatible body merges sampling/options at the top level
        # (unlike Ollama's nested ``options`` field).
        body.update(merged)
        if adapter != NO_LORA_SENTINEL:
            # SGLang OpenAI-compatible extension: lora_path field (which the
            # server resolves to a registered lora_name) selects the adapter
            # for this request. Spec'd to match the registry key set in
            # load_adapter(). NO_LORA_SENTINEL routes to base model (no
            # lora_path field) — per-language routing.
            body["lora_path"] = adapter
        return body

    async def health_check(self) -> None:
        """Verify SGLang is reachable. Raise :class:`SGLangUnavailableError` if not.

        Probes ``GET /health`` (cheap, no model load). Used by the orchestrator
        at startup so the operator sees a fail-fast at boot rather than at
        the first chat tick.
        """
        try:
            response = await self._client.get(self.HEALTH_PATH)
        except httpx.TimeoutException as exc:
            raise SGLangUnavailableError(
                f"SGLang {self.HEALTH_PATH} timeout after {self._timeout}s: {exc!r}",
            ) from exc
        except httpx.HTTPError as exc:
            raise SGLangUnavailableError(
                f"SGLang {self.HEALTH_PATH} unreachable at {self.endpoint}: {exc!r}",
            ) from exc
        if response.status_code != httpx.codes.OK:
            raise SGLangUnavailableError(
                f"SGLang {self.HEALTH_PATH} returned HTTP {response.status_code}",
            )

    async def _post(self, path: str, body: dict[str, Any]) -> dict[str, Any]:
        try:
            response = await self._client.post(path, json=body)
        except httpx.TimeoutException as exc:
            raise SGLangUnavailableError(
                f"SGLang {path} timeout after {self._timeout}s: {exc!r}",
            ) from exc
        except httpx.HTTPError as exc:
            raise SGLangUnavailableError(
                f"SGLang {path} unreachable at {self.endpoint}: {exc!r}",
            ) from exc

        if response.status_code != httpx.codes.OK:
            # Body may carry server-side debug info (model paths, env, stack
            # traces). Keep it out of the public exception message; surface
            # only the status code. Operators inspecting failures can raise
            # the logger to DEBUG to recover the body locally.
            logger.debug(
                "SGLang %s error body (truncated): %s",
                path,
                response.text[:200],
            )
            raise SGLangUnavailableError(
                f"SGLang {path} returned HTTP {response.status_code}",
            )

        try:
            payload = response.json()
        except ValueError as exc:
            raise SGLangUnavailableError(
                f"SGLang {path} returned non-JSON payload: {exc!r}",
            ) from exc

        if not isinstance(payload, dict):
            raise SGLangUnavailableError(
                f"SGLang {path} returned non-object JSON: {payload!r}",
            )
        return payload

    @staticmethod
    def _parse(payload: dict[str, Any]) -> ChatResponse:
        choices = payload.get("choices")
        if not isinstance(choices, list) or not choices:
            raise SGLangUnavailableError(
                "SGLang /v1/chat/completions payload missing 'choices' "
                f"(top-level keys: {sorted(payload.keys())})",
            )
        first = choices[0]
        if not isinstance(first, dict):
            raise SGLangUnavailableError(
                "SGLang /v1/chat/completions 'choices[0]' is not an object "
                f"(top-level keys: {sorted(payload.keys())})",
            )
        message = first.get("message")
        if not isinstance(message, dict) or "content" not in message:
            raise SGLangUnavailableError(
                "SGLang /v1/chat/completions payload missing "
                "'choices[0].message.content' "
                f"(top-level keys: {sorted(payload.keys())})",
            )
        finish_raw = first.get("finish_reason", "stop")
        finish_reason: Literal["stop", "length"] = (
            "length" if finish_raw == "length" else "stop"
        )
        usage = payload.get("usage", {})
        if not isinstance(usage, dict):
            usage = {}
        try:
            return ChatResponse(
                content=str(message["content"]),
                model=str(payload.get("model", "unknown")),
                eval_count=int(usage.get("completion_tokens", 0)),
                prompt_eval_count=int(usage.get("prompt_tokens", 0)),
                # SGLang OpenAI-compatible response does not document a
                # wall-clock duration field; emit 0.0 so the ChatResponse
                # contract holds (best-effort instrumentation, see ChatResponse
                # docstring).
                total_duration_ms=0.0,
                finish_reason=finish_reason,
            )
        except (ValidationError, TypeError, ValueError) as exc:
            raise SGLangUnavailableError(
                "SGLang /v1/chat/completions payload failed to parse as ChatResponse "
                f"(top-level keys: {sorted(payload.keys())}): {type(exc).__name__}",
            ) from exc


__all__ = [
    "DEFAULT_SGLANG_MODEL",
    "DEFAULT_SGLANG_VERSION",
    "NO_LORA_SENTINEL",
    "LoRAAdapterRef",
    "SGLangChatClient",
    "SGLangUnavailableError",
]
