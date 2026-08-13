"""Configurable embedding providers with a versioned, sanitized contract.

Production embeddings are obtained from an explicitly configured
OpenAI-compatible endpoint.  The hashing implementation is intentionally
available only when the operator selects ``deterministic`` (normally in tests or
local development); provider failures never fall back to a different vector
space.
"""

from __future__ import annotations

import hashlib
import json
import math
from typing import Any, Dict, Iterable, List, Optional, Protocol, Sequence
from urllib.parse import urlsplit


EMBEDDING_CONTRACT_VERSION = "axiom-embedding-v1"


class EmbeddingConfigurationError(RuntimeError):
    """Raised when no safe embedding provider can be constructed."""


class EmbeddingResponseError(RuntimeError):
    """Raised when a provider returns vectors that violate its declared contract."""


class EmbeddingPort(Protocol):
    provider_name: str
    model_name: str
    dimensions: int
    fingerprint: str

    def embed(self, text: str) -> List[float]:
        ...

    def embed_many(self, texts: Iterable[str]) -> List[List[float]]:
        ...

    def status(self) -> Dict[str, Any]:
        ...


def embedding_fingerprint(
    *, provider: str, model: str, dimensions: int, implementation: str
) -> str:
    """Return a stable identifier for vectors that may safely share a collection."""

    payload = json.dumps(
        {
            "contract": EMBEDDING_CONTRACT_VERSION,
            "dimensions": int(dimensions),
            "implementation": implementation,
            "model": model,
            "provider": provider,
            "normalization": "l2-v1",
        },
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def normalize_vector(values: Sequence[Any], dimensions: int) -> List[float]:
    """Validate dimensionality/finite values and return an L2-normalized vector."""

    if len(values) != dimensions:
        raise EmbeddingResponseError(
            "Embedding provider returned a vector with an unexpected dimension"
        )
    try:
        vector = [float(value) for value in values]
    except (TypeError, ValueError) as exc:
        raise EmbeddingResponseError("Embedding provider returned a non-numeric vector") from exc
    if not all(math.isfinite(value) for value in vector):
        raise EmbeddingResponseError("Embedding provider returned a non-finite vector")
    magnitude = math.sqrt(sum(value * value for value in vector))
    if magnitude == 0:
        raise EmbeddingResponseError("Embedding provider returned a zero vector")
    return [value / magnitude for value in vector]


def cosine_similarity(left: Sequence[float], right: Sequence[float]) -> float:
    """Provider-neutral cosine for vectors normalized by this module's contract."""

    if len(left) != len(right):
        raise EmbeddingResponseError("Stored and query embedding dimensions do not match")
    similarity = sum(float(a) * float(b) for a, b in zip(left, right))
    if not math.isfinite(similarity):
        raise EmbeddingResponseError("Embedding similarity was non-finite")
    return similarity


class OpenAICompatibleEmbedding:
    """Real embeddings from an explicitly configured OpenAI-compatible API."""

    provider_name = "openai"

    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        dimensions: int,
        base_url: str,
        timeout_seconds: float = 10.0,
        batch_size: int = 64,
        input_type: str = "auto",
        client: Optional[Any] = None,
    ) -> None:
        parsed = urlsplit(base_url)
        if (
            parsed.scheme.lower() != "https"
            or not parsed.hostname
            or parsed.username
            or parsed.password
        ):
            raise EmbeddingConfigurationError(
                "The embedding endpoint must be credential-free HTTPS"
            )
        if not api_key:
            raise EmbeddingConfigurationError("The configured embedding provider needs a credential")
        if not model.strip():
            raise EmbeddingConfigurationError("The embedding model must not be empty")
        if int(dimensions) < 1:
            raise EmbeddingConfigurationError("Embedding dimensions must be positive")

        self.model_name = model.strip()
        self.dimensions = int(dimensions)
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = max(1.0, min(float(timeout_seconds), 60.0))
        self.batch_size = max(1, min(int(batch_size), 256))
        normalized_input_type = str(input_type).strip().lower()
        if normalized_input_type not in {"auto", "none"}:
            raise EmbeddingConfigurationError("Embedding input_type must be auto or none")
        self.input_type = normalized_input_type
        self._api_key = api_key
        self._client = client
        model_lower = self.model_name.lower()
        self._requires_query_passage = self.input_type == "auto" and any(
            marker in model_lower
            for marker in (
                "llama-nemotron-embed",
                "llama-3.2-nv-embedqa",
                "nemoretriever",
                "embedqa-e5",
                "embedqa-mistral",
            )
        )
        self.fingerprint = embedding_fingerprint(
            provider=self.provider_name,
            model=self.model_name,
            dimensions=self.dimensions,
            # The endpoint is hashed into the fingerprint because two compatible
            # providers can serve different vector spaces under the same model
            # label.  The endpoint itself is never returned by status APIs.
            implementation="openai-compatible:" + self.base_url,
        )

    def embed(self, text: str) -> List[float]:
        vectors = self._embed_many([text], input_type="query")
        return vectors[0]

    def embed_many(self, texts: Iterable[str]) -> List[List[float]]:
        return self._embed_many(texts, input_type="passage")

    def _embed_many(
        self, texts: Iterable[str], *, input_type: str
    ) -> List[List[float]]:
        values = [str(text).strip() for text in texts]
        if not values:
            return []
        if any(not value for value in values):
            raise ValueError("Embedding inputs must not be empty")

        client = self._get_client()
        vectors: List[List[float]] = []
        for start in range(0, len(values), self.batch_size):
            batch = values[start : start + self.batch_size]
            try:
                request: Dict[str, Any] = {
                    "model": self.model_name,
                    "input": batch,
                    "dimensions": self.dimensions,
                }
                if self._requires_query_passage:
                    # NVIDIA's Nemotron retriever API uses an OpenAI-compatible
                    # endpoint but requires this extra discriminator to keep
                    # passage/index vectors aligned with query vectors.
                    request["extra_body"] = {"input_type": input_type}
                response = client.embeddings.create(**request)
                records = sorted(response.data, key=lambda item: int(item.index))
            except EmbeddingResponseError:
                raise
            except Exception as exc:
                # Do not leak provider bodies, endpoint details, or credentials.
                raise EmbeddingResponseError(
                    "Embedding provider request was unavailable ({0})".format(type(exc).__name__)
                ) from exc
            if len(records) != len(batch):
                raise EmbeddingResponseError("Embedding provider returned an incomplete batch")
            try:
                indexes = [int(record.index) for record in records]
            except (AttributeError, TypeError, ValueError) as exc:
                raise EmbeddingResponseError("Embedding provider returned invalid indexes") from exc
            if indexes != list(range(len(batch))):
                raise EmbeddingResponseError("Embedding provider returned invalid indexes")
            vectors.extend(
                normalize_vector(record.embedding, self.dimensions) for record in records
            )
        return vectors

    def status(self) -> Dict[str, Any]:
        return {
            "provider": self.provider_name,
            "model": self.model_name,
            "dimensions": self.dimensions,
            "fingerprint": self.fingerprint,
            "mode": "remote",
            "configured": True,
        }

    def _get_client(self) -> Any:
        if self._client is None:
            try:
                from openai import OpenAI
            except ImportError as exc:
                raise EmbeddingConfigurationError(
                    "The openai package is required for remote embeddings"
                ) from exc
            self._client = OpenAI(
                api_key=self._api_key,
                base_url=self.base_url,
                timeout=self.timeout_seconds,
                # Rebuild is an explicit operator action.  Retrying a whole
                # batch here makes a broken key or endpoint look like a hung
                # index operation and can duplicate provider load.
                max_retries=0,
            )
        return self._client


def create_embedding(configuration: Any) -> EmbeddingPort:
    """Construct the selected vector space without implicit provider fallback."""

    provider = str(getattr(configuration, "embedding_provider", "disabled")).strip().lower()
    if provider == "openai-compatible":
        provider = "openai"
    dimensions = int(getattr(configuration, "embedding_dimensions", 1536))
    if provider == "deterministic":
        from app.vectorstore.deterministic import DeterministicEmbedding

        return DeterministicEmbedding(dimensions=dimensions)
    if provider == "openai":
        return OpenAICompatibleEmbedding(
            api_key=str(getattr(configuration, "embedding_api_key", "")),
            model=str(getattr(configuration, "embedding_model", "text-embedding-3-small")),
            dimensions=dimensions,
            base_url=str(
                getattr(configuration, "embedding_base_url", "https://api.openai.com/v1")
            ),
            timeout_seconds=float(getattr(configuration, "embedding_timeout_seconds", 10.0)),
            batch_size=int(getattr(configuration, "embedding_batch_size", 64)),
            input_type=str(getattr(configuration, "embedding_input_type", "auto")),
        )
    if provider == "disabled":
        raise EmbeddingConfigurationError(
            "Embeddings are disabled; select a production provider or explicit deterministic mode"
        )
    raise EmbeddingConfigurationError("Unsupported embedding provider")
