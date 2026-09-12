"""LLM inference adapters (Ollama + SGLang LoRA) — depends on ``schemas`` only.

Public surface:

* :class:`OllamaChatClient` — Ollama ``/api/chat`` client
* :class:`SGLangChatClient` — SGLang LoRA-aware OpenAI-compatible client
  (m9-c-spike Phase H, decisions.md CS-1 / CS-2)
* :class:`LoRAAdapterRef` — frozen ref for SGLang LoRA load/unload (CS-2 / CS-9)
* :class:`ChatMessage` — role-tagged request message (shared)
* :class:`ChatResponse` — normalised, backend-agnostic response (shared)
* :class:`OllamaUnavailableError` / :class:`SGLangUnavailableError` — single
  unified errors per backend
* :func:`compose_sampling` — ``SamplingBase + SamplingDelta`` → clamped
  :class:`ResolvedSampling` (the only supported way to reach the adapter)
* :data:`DEFAULT_CHAT_MODEL` — Ollama model tag pulled during T09
* :data:`DEFAULT_SGLANG_MODEL` / :data:`DEFAULT_SGLANG_VERSION` — m9-c-spike
  base model and version pin (CS-1)

The sampling composition is deliberately re-exported from the top level so
callers (T12 cognition cycle, T14 gateway) never touch the inner module
paths.

Layer dependency (see ``architecture-rules`` skill):

* allowed: ``erre_sandbox.schemas``, ``httpx``, ``pydantic``
* forbidden: ``memory``, ``cognition``, ``world``, ``ui``
"""

from erre_sandbox.inference.ollama_adapter import (
    DEFAULT_CHAT_MODEL,
    ChatMessage,
    ChatResponse,
    OllamaChatClient,
    OllamaUnavailableError,
)
from erre_sandbox.inference.sampling import ResolvedSampling, compose_sampling
from erre_sandbox.inference.sglang_adapter import (
    DEFAULT_SGLANG_MODEL,
    DEFAULT_SGLANG_VERSION,
    NO_LORA_SENTINEL,
    LoRAAdapterRef,
    SGLangChatClient,
    SGLangUnavailableError,
)

__all__ = [
    "DEFAULT_CHAT_MODEL",
    "DEFAULT_SGLANG_MODEL",
    "DEFAULT_SGLANG_VERSION",
    "NO_LORA_SENTINEL",
    "ChatMessage",
    "ChatResponse",
    "LoRAAdapterRef",
    "OllamaChatClient",
    "OllamaUnavailableError",
    "ResolvedSampling",
    "SGLangChatClient",
    "SGLangUnavailableError",
    "compose_sampling",
]
