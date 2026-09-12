"""Memory subsystem (sqlite-vec backed) — depends on ``schemas`` only.

Public API entry points:

* :class:`MemoryStore` — persistence for 4 memory kinds + shared vec0 table
* :class:`EmbeddingClient` / :data:`QUERY_PREFIX` / :data:`DOC_PREFIX` —
  Ollama ``/api/embed`` adapter with nomic-embed-text-v1.5 prefix discipline
* :class:`Retriever` / :func:`score` — 2-scope retrieval with decay-weighted
  ranking (see ``docs/architecture.md §Memory Layer``)
"""

from erre_sandbox.memory.embedding import (
    DOC_PREFIX,
    QUERY_PREFIX,
    EmbeddingClient,
    EmbeddingUnavailableError,
)
from erre_sandbox.memory.retrieval import (
    DEFAULT_DECAY_LAMBDA,
    DEFAULT_K_AGENT,
    DEFAULT_K_WORLD,
    DEFAULT_KINDS,
    DEFAULT_RECALL_BOOST,
    RankedMemory,
    Retriever,
    cosine_similarity,
    score,
)
from erre_sandbox.memory.store import DEFAULT_EMBED_DIM, MemoryStore

__all__ = [
    "DEFAULT_DECAY_LAMBDA",
    "DEFAULT_EMBED_DIM",
    "DEFAULT_KINDS",
    "DEFAULT_K_AGENT",
    "DEFAULT_K_WORLD",
    "DEFAULT_RECALL_BOOST",
    "DOC_PREFIX",
    "QUERY_PREFIX",
    "EmbeddingClient",
    "EmbeddingUnavailableError",
    "MemoryStore",
    "RankedMemory",
    "Retriever",
    "cosine_similarity",
    "score",
]
