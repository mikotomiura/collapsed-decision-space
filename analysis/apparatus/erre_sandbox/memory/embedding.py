"""Ollama ``/api/embed`` adapter with enforced QUERY/DOC prefix dispatch.

The two prefixes defined here are the exact QUERY/DOC asymmetry that
``test_embedding_prefix.py`` guards.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar, Final, Literal, Self

import httpx

if TYPE_CHECKING:
    from collections.abc import Sequence

QUERY_PREFIX: Final[str] = "search_query: "
"""Prefix used when embedding a search query (nomic-embed-text-v1.5 convention)."""

DOC_PREFIX: Final[str] = "search_document: "
"""Prefix used when embedding a document (nomic-embed-text-v1.5 convention)."""


class EmbeddingUnavailableError(RuntimeError):
    """Raised when Ollama ``/api/embed`` is unreachable or malformed."""


class EmbeddingClient:
    """Asynchronous client for Ollama's embedding endpoint.

    The high-level API (:meth:`embed_query` / :meth:`embed_document`) is the
    default entrypoint and automatically prepends the correct prefix. The
    low-level :meth:`embed` is retained for tests and special cases where
    the caller needs explicit control.

    Example::

        async with EmbeddingClient() as client:
            vec = await client.embed_query("peripatos における思索")
            assert len(vec) == client.dim
    """

    DEFAULT_MODEL: ClassVar[str] = "nomic-embed-text"
    DEFAULT_DIM: ClassVar[int] = 768
    DEFAULT_ENDPOINT: ClassVar[str] = "http://127.0.0.1:11434"
    DEFAULT_TIMEOUT_SECONDS: ClassVar[float] = 30.0

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
        self.dim = self.DEFAULT_DIM
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
        if self._owns_client:
            await self._client.aclose()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def embed(self, text: str) -> list[float]:
        """Embed raw ``text`` with **no** prefix injection (low-level).

        Prefer :meth:`embed_query` or :meth:`embed_document` in production
        code paths; this method exists for tests and advanced callers.
        """
        return (await self._post([text]))[0]

    async def embed_query(self, text: str) -> list[float]:
        """Embed a search query. Prepends :data:`QUERY_PREFIX`."""
        return (await self._post([QUERY_PREFIX + text]))[0]

    async def embed_document(self, text: str) -> list[float]:
        """Embed a document (for storage). Prepends :data:`DOC_PREFIX`."""
        return (await self._post([DOC_PREFIX + text]))[0]

    async def embed_many(
        self,
        texts: Sequence[str],
        *,
        kind: Literal["query", "document"],
    ) -> list[list[float]]:
        """Embed multiple texts at once. ``kind`` selects the prefix."""
        prefix = QUERY_PREFIX if kind == "query" else DOC_PREFIX
        return await self._post([prefix + t for t in texts])

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    async def _post(self, inputs: list[str]) -> list[list[float]]:
        try:
            response = await self._client.post(
                "/api/embed",
                json={"model": self.model, "input": inputs},
            )
        except httpx.HTTPError as exc:
            raise EmbeddingUnavailableError(
                f"Ollama /api/embed unreachable at {self.endpoint}: {exc!r}",
            ) from exc

        if response.status_code != httpx.codes.OK:
            raise EmbeddingUnavailableError(
                f"Ollama /api/embed returned HTTP {response.status_code}: "
                f"{response.text[:200]}",
            )

        try:
            payload = response.json()
        except ValueError as exc:
            raise EmbeddingUnavailableError(
                f"Ollama /api/embed returned non-JSON payload: {exc!r}",
            ) from exc

        vectors = payload.get("embeddings")
        if not isinstance(vectors, list) or not vectors:
            raise EmbeddingUnavailableError(
                f"Ollama /api/embed payload missing 'embeddings': {payload!r}",
            )
        # Coerce numeric elements to float for type consistency.
        return [[float(x) for x in v] for v in vectors]


__all__ = [
    "DOC_PREFIX",
    "QUERY_PREFIX",
    "EmbeddingClient",
    "EmbeddingUnavailableError",
]
