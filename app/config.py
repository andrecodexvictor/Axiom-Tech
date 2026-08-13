"""Validated runtime configuration for the Axiom Tech modular monolith.

Cloud integrations are opt-in.  The default route is deterministic and performs
no network access.  Secret-bearing fields are excluded from dataclass
representations, and configuration errors identify variable names rather than
values.
"""

from __future__ import annotations

import math
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, Tuple
from urllib.parse import urlsplit

from dotenv import load_dotenv


BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

_TRUE_VALUES = {"1", "true", "yes", "on"}
_FALSE_VALUES = {"0", "false", "no", "off"}
_MODEL_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,199}$")
_MODEL_ROUTE_ALIASES = {
    "local": "deterministic",
    "kimi": "nvidia-kimi",
    "minimax": "nvidia-minimax",
    "deepseek": "nvidia-deepseek",
}
_MODEL_ROUTE_NAMES = {
    "deterministic",
    "nvidia",
    "nvidia-kimi",
    "nvidia-minimax",
    "nvidia-deepseek",
    "openai",
}


class ConfigurationError(ValueError):
    """A sanitized startup error caused by invalid runtime configuration."""


def _as_bool(value: Optional[str], default: bool = False, variable: str = "value") -> bool:
    if value is None:
        return default
    normalized = value.strip().lower()
    if normalized in _TRUE_VALUES:
        return True
    if normalized in _FALSE_VALUES:
        return False
    raise ConfigurationError(f"{variable} must be a boolean")


def _bounded_int(
    value: Optional[str],
    default: int,
    minimum: int,
    maximum: int,
    variable: str,
    *,
    clamp: bool = False,
) -> int:
    try:
        parsed = default if value is None else int(value.strip())
    except (AttributeError, TypeError, ValueError) as exc:
        raise ConfigurationError(f"{variable} must be an integer") from exc
    if clamp:
        return min(maximum, max(minimum, parsed))
    if not minimum <= parsed <= maximum:
        raise ConfigurationError(f"{variable} must be between {minimum} and {maximum}")
    return parsed


def _bounded_float(
    value: Optional[str],
    default: float,
    minimum: float,
    maximum: float,
    variable: str,
    *,
    clamp: bool = False,
) -> float:
    try:
        parsed = default if value is None else float(value.strip())
    except (AttributeError, TypeError, ValueError) as exc:
        raise ConfigurationError(f"{variable} must be a number") from exc
    if not math.isfinite(parsed):
        raise ConfigurationError(f"{variable} must be finite")
    if clamp:
        return min(maximum, max(minimum, parsed))
    if not minimum <= parsed <= maximum:
        raise ConfigurationError(f"{variable} must be between {minimum} and {maximum}")
    return parsed


def _secret(value: Optional[str], variable: str) -> str:
    secret = (value or "").strip()
    if any(character in secret for character in ("\r", "\n", "\x00")):
        raise ConfigurationError(f"{variable} contains an invalid control character")
    return secret


def _model(value: Optional[str], default: str, variable: str, *, required: bool = True) -> str:
    model = (value or default).strip()
    if not model and not required:
        return ""
    if not _MODEL_NAME.fullmatch(model):
        raise ConfigurationError(f"{variable} must be a valid model identifier")
    return model


def _origins(value: Optional[str]) -> Tuple[str, ...]:
    default = "http://localhost:5173,http://127.0.0.1:5173,http://localhost:3000"
    return tuple(origin.strip() for origin in (value or default).split(",") if origin.strip())


def _hosts(value: Optional[str]) -> Tuple[str, ...]:
    """Parse a comma-separated hostname allowlist without accepting URL syntax."""

    hosts = []
    for value_item in (value or "").split(","):
        host = value_item.strip().lower().rstrip(".")
        if not host or "://" in host or "/" in host or "@" in host or ":" in host:
            continue
        labels = host.split(".")
        if len(labels) >= 2 and all(label and label.replace("-", "").isalnum() for label in labels):
            hosts.append(host)
    return tuple(dict.fromkeys(hosts))


def _safe_https_url(value: Optional[str], default: str, variable: str = "endpoint") -> str:
    """Return an HTTPS endpoint or fail without echoing the supplied value."""

    candidate = (value or default).strip().rstrip("/")
    try:
        parsed = urlsplit(candidate)
        port = parsed.port
    except ValueError as exc:
        raise ConfigurationError(f"{variable} must be a valid HTTPS URL") from exc
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
        or port is not None and not 1 <= port <= 65535
    ):
        raise ConfigurationError(
            f"{variable} must be an HTTPS URL without credentials, query, or fragment"
        )
    return candidate


def _model_routes(value: str, variable: str = "AXIOM_LLM_ROUTES") -> Tuple[str, ...]:
    items = []
    for item in value.split(","):
        normalized = _MODEL_ROUTE_ALIASES.get(item.strip().lower(), item.strip().lower())
        if not normalized or normalized not in _MODEL_ROUTE_NAMES:
            raise ConfigurationError(f"{variable} contains an unsupported route")
        if normalized in items:
            raise ConfigurationError(f"{variable} must not contain duplicate routes")
        items.append(normalized)
    if not items:
        raise ConfigurationError(f"{variable} must contain at least one route")
    if "deterministic" in items and items[-1] != "deterministic":
        raise ConfigurationError(f"{variable} must place deterministic last")
    return tuple(items)


@dataclass(frozen=True)
class ModelRouteConfig:
    """One resolved route.  Its credential is never included in ``repr``."""

    name: str
    provider: str
    model: Optional[str]
    base_url: Optional[str]
    api_key: str = field(default="", repr=False)

    @property
    def remote(self) -> bool:
        return self.provider != "deterministic"

    @property
    def configured(self) -> bool:
        return not self.remote or bool(self.api_key and self.model and self.base_url)


@dataclass(frozen=True)
class Settings:
    """Runtime settings read from the environment once at application startup."""

    documents_dir: Path
    chroma_path: Path
    chroma_collection: str
    vector_backend: str
    chunk_size: int
    chunk_overlap: int
    cors_origins: Tuple[str, ...]
    nvidia_enabled: bool
    kimi_api_key: str = field(repr=False)
    minimax_api_key: str = field(repr=False)
    deepseek_api_key: str = field(repr=False)
    pinecone_api_key: str = field(repr=False)
    pinecone_index_name: str
    pinecone_environment: str

    # NVIDIA remains the backwards-compatible remote provider.  The model-specific
    # credentials below become active only through an explicit nvidia-* route.
    nvidia_api_key: str = field(default="", repr=False)
    nvidia_model: str = "meta/llama-3.1-70b-instruct"
    nvidia_base_url: str = "https://integrate.api.nvidia.com/v1"
    nvidia_kimi_model: str = "moonshotai/kimi-k2.6"
    nvidia_minimax_model: str = "minimaxai/minimax-m3"
    nvidia_deepseek_model: str = "deepseek-ai/deepseek-v4-pro"

    # The official OpenAI endpoint is the default.  A custom endpoint requires a
    # separate opt-in so an accidental base URL cannot receive an OpenAI key.
    openai_api_key: str = field(default="", repr=False)
    openai_model: str = ""
    openai_base_url: str = "https://api.openai.com/v1"
    openai_allow_custom_base_url: bool = False

    # Empty routes mean legacy derivation: NVIDIA+deterministic when
    # AXIOM_NVIDIA_ENABLED is true, otherwise deterministic only.
    llm_routes: Tuple[str, ...] = ()
    llm_timeout_seconds: float = 30.0
    llm_max_retries: int = 1
    llm_circuit_failure_threshold: int = 3
    llm_circuit_recovery_seconds: float = 30.0

    web_enabled: bool = False
    serper_api_key: str = field(default="", repr=False)
    web_allowlist: Tuple[str, ...] = ()
    web_timeout_seconds: float = 8.0
    web_max_response_bytes: int = 1_000_000
    langsmith_tracing: bool = False
    langsmith_api_key: str = field(default="", repr=False)
    langsmith_endpoint: str = "https://api.smith.langchain.com"
    langsmith_project: str = "axiom-tech-v3"
    langsmith_workspace_id: str = field(default="", repr=False)
    langsmith_hide_inputs: bool = True
    langsmith_hide_outputs: bool = True

    # Deterministic embeddings keep a clean checkout useful offline.  Operators
    # may explicitly choose disabled or a fully configured remote provider.
    embedding_provider: str = "deterministic"
    embedding_model: str = "text-embedding-3-small"
    embedding_dimensions: int = 384
    embedding_base_url: str = "https://api.openai.com/v1"
    embedding_api_key: str = field(default="", repr=False)
    embedding_timeout_seconds: float = 10.0
    embedding_batch_size: int = 64
    retrieval_candidate_multiplier: int = 4
    retrieval_min_score: float = 0.12
    retrieval_lexical_weight: float = 0.25
    retrieval_mmr_lambda: float = 0.75

    def __post_init__(self) -> None:
        route_names = tuple(
            _MODEL_ROUTE_ALIASES.get(str(item).strip().lower(), str(item).strip().lower())
            for item in self.llm_routes
        )
        if route_names:
            route_names = _model_routes(",".join(route_names), "llm_routes")
        object.__setattr__(self, "llm_routes", route_names)

        provider = self.embedding_provider.strip().lower()
        if provider == "openai-compatible":
            provider = "openai"
        if provider not in {"disabled", "deterministic", "openai"}:
            raise ConfigurationError("AXIOM_EMBEDDING_PROVIDER is unsupported")
        object.__setattr__(self, "embedding_provider", provider)

    @classmethod
    def from_env(cls) -> "Settings":
        documents_dir = Path(
            os.getenv("AXIOM_DOCUMENTS_DIR", str(BASE_DIR / "documentos"))
        ).expanduser()
        chroma_path = Path(
            os.getenv("AXIOM_CHROMA_PATH", str(BASE_DIR / ".axiom_chroma"))
        ).expanduser()

        legacy_nvidia_enabled = _as_bool(
            os.getenv("AXIOM_NVIDIA_ENABLED"), False, "AXIOM_NVIDIA_ENABLED"
        )
        routes_value = (os.getenv("AXIOM_LLM_ROUTES") or "").strip() or None
        provider_value = (os.getenv("AXIOM_LLM_PROVIDER") or "").strip() or None
        fallback_value = (os.getenv("AXIOM_LLM_FALLBACK") or "").strip() or None
        explicit_routes = routes_value is not None or provider_value is not None

        if routes_value is not None and provider_value is not None:
            raise ConfigurationError("Set AXIOM_LLM_ROUTES or AXIOM_LLM_PROVIDER, not both")
        if routes_value is not None:
            if fallback_value is not None:
                raise ConfigurationError("AXIOM_LLM_ROUTES already defines fallback order")
            routes = _model_routes(routes_value)
        elif provider_value is not None:
            provider = provider_value.strip().lower()
            if provider not in {"deterministic", "nvidia", "openai"}:
                raise ConfigurationError("AXIOM_LLM_PROVIDER is unsupported")
            fallback = fallback_value or (
                "none" if provider == "deterministic" else "deterministic"
            )
            fallback = fallback.strip().lower()
            if fallback not in {"none", "deterministic"}:
                raise ConfigurationError("AXIOM_LLM_FALLBACK must be none or deterministic")
            if provider == "deterministic" and fallback != "none":
                raise ConfigurationError("A deterministic provider cannot have a fallback")
            routes = (provider,) + (("deterministic",) if fallback == "deterministic" else ())
        else:
            if fallback_value is not None:
                raise ConfigurationError("AXIOM_LLM_FALLBACK requires AXIOM_LLM_PROVIDER")
            routes = ()

        openai_base_url = _safe_https_url(
            os.getenv("AXIOM_OPENAI_BASE_URL"),
            "https://api.openai.com/v1",
            "AXIOM_OPENAI_BASE_URL",
        )
        allow_custom_openai = _as_bool(
            os.getenv("AXIOM_OPENAI_ALLOW_CUSTOM_BASE_URL"),
            False,
            "AXIOM_OPENAI_ALLOW_CUSTOM_BASE_URL",
        )
        if urlsplit(openai_base_url).hostname != "api.openai.com" and not allow_custom_openai:
            raise ConfigurationError(
                "AXIOM_OPENAI_ALLOW_CUSTOM_BASE_URL=true is required for a custom OpenAI endpoint"
            )

        embedding_provider = os.getenv("AXIOM_EMBEDDING_PROVIDER", "deterministic").strip().lower()
        if embedding_provider == "openai-compatible":
            embedding_provider = "openai"

        configured = cls(
            documents_dir=documents_dir,
            chroma_path=chroma_path,
            chroma_collection=os.getenv("AXIOM_CHROMA_COLLECTION", "axiom_knowledge").strip()
            or "axiom_knowledge",
            vector_backend=os.getenv("AXIOM_VECTOR_BACKEND", "chroma").strip().lower(),
            chunk_size=_bounded_int(
                os.getenv("AXIOM_CHUNK_SIZE"), 900, 100, 100_000, "AXIOM_CHUNK_SIZE", clamp=True
            ),
            chunk_overlap=_bounded_int(
                os.getenv("AXIOM_CHUNK_OVERLAP"), 150, 0, 20_000, "AXIOM_CHUNK_OVERLAP", clamp=True
            ),
            cors_origins=_origins(os.getenv("AXIOM_CORS_ORIGINS")),
            nvidia_enabled=legacy_nvidia_enabled,
            kimi_api_key=_secret(os.getenv("KIMI_API_KEY"), "KIMI_API_KEY"),
            minimax_api_key=_secret(os.getenv("MINIMAX_API_KEY"), "MINIMAX_API_KEY"),
            deepseek_api_key=_secret(os.getenv("DEEPSEEK_API_KEY"), "DEEPSEEK_API_KEY"),
            pinecone_api_key=_secret(os.getenv("PINECONE_API_KEY"), "PINECONE_API_KEY"),
            pinecone_index_name=os.getenv("PINECONE_INDEX_NAME", "axiom-tech-knowledge").strip(),
            pinecone_environment=os.getenv("PINECONE_ENVIRONMENT", "us-east-1").strip(),
            nvidia_api_key=_secret(os.getenv("NVIDIA_API_KEY"), "NVIDIA_API_KEY"),
            nvidia_model=_model(
                os.getenv("NVIDIA_MODEL"),
                "meta/llama-3.1-70b-instruct",
                "NVIDIA_MODEL",
            ),
            nvidia_base_url=_safe_https_url(
                os.getenv("AXIOM_NVIDIA_BASE_URL"),
                "https://integrate.api.nvidia.com/v1",
                "AXIOM_NVIDIA_BASE_URL",
            ),
            nvidia_kimi_model=_model(
                os.getenv("NVIDIA_KIMI_MODEL"), "moonshotai/kimi-k2.6", "NVIDIA_KIMI_MODEL"
            ),
            nvidia_minimax_model=_model(
                os.getenv("NVIDIA_MINIMAX_MODEL"), "minimaxai/minimax-m3", "NVIDIA_MINIMAX_MODEL"
            ),
            nvidia_deepseek_model=_model(
                os.getenv("NVIDIA_DEEPSEEK_MODEL"),
                "deepseek-ai/deepseek-v4-pro",
                "NVIDIA_DEEPSEEK_MODEL",
            ),
            openai_api_key=_secret(os.getenv("OPENAI_API_KEY"), "OPENAI_API_KEY"),
            openai_model=_model(os.getenv("OPENAI_MODEL"), "", "OPENAI_MODEL", required=False),
            openai_base_url=openai_base_url,
            openai_allow_custom_base_url=allow_custom_openai,
            llm_routes=routes,
            llm_timeout_seconds=_bounded_float(
                os.getenv("AXIOM_LLM_TIMEOUT_SECONDS"),
                30.0,
                1.0,
                120.0,
                "AXIOM_LLM_TIMEOUT_SECONDS",
            ),
            llm_max_retries=_bounded_int(
                os.getenv("AXIOM_LLM_MAX_RETRIES"), 1, 0, 5, "AXIOM_LLM_MAX_RETRIES"
            ),
            llm_circuit_failure_threshold=_bounded_int(
                os.getenv("AXIOM_LLM_CIRCUIT_FAILURE_THRESHOLD"),
                3,
                1,
                10,
                "AXIOM_LLM_CIRCUIT_FAILURE_THRESHOLD",
            ),
            llm_circuit_recovery_seconds=_bounded_float(
                os.getenv("AXIOM_LLM_CIRCUIT_RECOVERY_SECONDS"),
                30.0,
                1.0,
                600.0,
                "AXIOM_LLM_CIRCUIT_RECOVERY_SECONDS",
            ),
            web_enabled=_as_bool(os.getenv("AXIOM_WEB_ENABLED"), False, "AXIOM_WEB_ENABLED"),
            serper_api_key=_secret(os.getenv("SERPER_API_KEY"), "SERPER_API_KEY"),
            web_allowlist=_hosts(os.getenv("AXIOM_WEB_ALLOWLIST")),
            web_timeout_seconds=_bounded_float(
                os.getenv("AXIOM_WEB_TIMEOUT_SECONDS"),
                8.0,
                1.0,
                30.0,
                "AXIOM_WEB_TIMEOUT_SECONDS",
                clamp=True,
            ),
            web_max_response_bytes=_bounded_int(
                os.getenv("AXIOM_WEB_MAX_RESPONSE_BYTES"),
                1_000_000,
                8_192,
                5_000_000,
                "AXIOM_WEB_MAX_RESPONSE_BYTES",
                clamp=True,
            ),
            langsmith_tracing=_as_bool(
                os.getenv("LANGSMITH_TRACING") or os.getenv("LANGCHAIN_TRACING_V2"),
                False,
                "LANGSMITH_TRACING",
            ),
            langsmith_api_key=_secret(
                os.getenv("LANGSMITH_API_KEY") or os.getenv("LANGCHAIN_API_KEY"),
                "LANGSMITH_API_KEY",
            ),
            langsmith_endpoint=_safe_https_url(
                os.getenv("LANGSMITH_ENDPOINT") or os.getenv("LANGCHAIN_ENDPOINT"),
                "https://api.smith.langchain.com",
                "LANGSMITH_ENDPOINT",
            ),
            langsmith_project=(
                os.getenv("LANGSMITH_PROJECT")
                or os.getenv("LANGCHAIN_PROJECT")
                or "axiom-tech-v3"
            ).strip()
            or "axiom-tech-v3",
            langsmith_workspace_id=_secret(
                os.getenv("LANGSMITH_WORKSPACE_ID"), "LANGSMITH_WORKSPACE_ID"
            ),
            langsmith_hide_inputs=_as_bool(
                os.getenv("LANGSMITH_HIDE_INPUTS"), True, "LANGSMITH_HIDE_INPUTS"
            ),
            langsmith_hide_outputs=_as_bool(
                os.getenv("LANGSMITH_HIDE_OUTPUTS"), True, "LANGSMITH_HIDE_OUTPUTS"
            ),
            embedding_provider=embedding_provider,
            embedding_model=_model(
                os.getenv("AXIOM_EMBEDDING_MODEL"),
                "text-embedding-3-small",
                "AXIOM_EMBEDDING_MODEL",
            ),
            embedding_dimensions=_bounded_int(
                os.getenv("AXIOM_EMBEDDING_DIMENSIONS"),
                384,
                64,
                4096,
                "AXIOM_EMBEDDING_DIMENSIONS",
                clamp=True,
            ),
            embedding_base_url=_safe_https_url(
                os.getenv("AXIOM_EMBEDDING_BASE_URL"),
                "https://api.openai.com/v1",
                "AXIOM_EMBEDDING_BASE_URL",
            ),
            embedding_api_key=_secret(
                os.getenv("AXIOM_EMBEDDING_API_KEY"), "AXIOM_EMBEDDING_API_KEY"
            ),
            embedding_timeout_seconds=_bounded_float(
                os.getenv("AXIOM_EMBEDDING_TIMEOUT_SECONDS"),
                10.0,
                1.0,
                60.0,
                "AXIOM_EMBEDDING_TIMEOUT_SECONDS",
                clamp=True,
            ),
            embedding_batch_size=_bounded_int(
                os.getenv("AXIOM_EMBEDDING_BATCH_SIZE"),
                64,
                1,
                256,
                "AXIOM_EMBEDDING_BATCH_SIZE",
                clamp=True,
            ),
            retrieval_candidate_multiplier=_bounded_int(
                os.getenv("AXIOM_RETRIEVAL_CANDIDATE_MULTIPLIER"),
                4,
                1,
                10,
                "AXIOM_RETRIEVAL_CANDIDATE_MULTIPLIER",
                clamp=True,
            ),
            retrieval_min_score=_bounded_float(
                os.getenv("AXIOM_RETRIEVAL_MIN_SCORE"),
                0.12,
                0.0,
                1.0,
                "AXIOM_RETRIEVAL_MIN_SCORE",
                clamp=True,
            ),
            retrieval_lexical_weight=_bounded_float(
                os.getenv("AXIOM_RETRIEVAL_LEXICAL_WEIGHT"),
                0.25,
                0.0,
                0.5,
                "AXIOM_RETRIEVAL_LEXICAL_WEIGHT",
                clamp=True,
            ),
            retrieval_mmr_lambda=_bounded_float(
                os.getenv("AXIOM_RETRIEVAL_MMR_LAMBDA"),
                0.75,
                0.5,
                1.0,
                "AXIOM_RETRIEVAL_MMR_LAMBDA",
                clamp=True,
            ),
        )

        if configured.chunk_overlap >= configured.chunk_size:
            raise ConfigurationError("AXIOM_CHUNK_OVERLAP must be smaller than AXIOM_CHUNK_SIZE")
        if configured.embedding_provider == "openai" and not configured.embedding_api_key:
            raise ConfigurationError(
                "AXIOM_EMBEDDING_API_KEY is required when AXIOM_EMBEDDING_PROVIDER=openai"
            )
        if explicit_routes:
            configured.validate_selected_model_routes()
        return configured

    @property
    def effective_model_route_names(self) -> Tuple[str, ...]:
        if self.llm_routes:
            return self.llm_routes
        if self.nvidia_enabled:
            return ("nvidia", "deterministic")
        return ("deterministic",)

    @property
    def model_routes(self) -> Tuple[ModelRouteConfig, ...]:
        registry = {
            "deterministic": ModelRouteConfig("deterministic", "deterministic", None, None),
            "nvidia": ModelRouteConfig(
                "nvidia",
                "nvidia",
                self.nvidia_model,
                self.nvidia_base_url,
                self.effective_nvidia_api_key,
            ),
            "nvidia-kimi": ModelRouteConfig(
                "nvidia-kimi",
                "nvidia",
                self.nvidia_kimi_model,
                self.nvidia_base_url,
                self.kimi_api_key,
            ),
            "nvidia-minimax": ModelRouteConfig(
                "nvidia-minimax",
                "nvidia",
                self.nvidia_minimax_model,
                self.nvidia_base_url,
                self.minimax_api_key,
            ),
            "nvidia-deepseek": ModelRouteConfig(
                "nvidia-deepseek",
                "nvidia",
                self.nvidia_deepseek_model,
                self.nvidia_base_url,
                self.deepseek_api_key,
            ),
            "openai": ModelRouteConfig(
                "openai",
                "openai",
                self.openai_model or None,
                self.openai_base_url,
                self.openai_api_key,
            ),
        }
        return tuple(registry[name] for name in self.effective_model_route_names)

    def validate_selected_model_routes(self) -> None:
        for route in self.model_routes:
            if route.remote and not route.configured:
                raise ConfigurationError(
                    f"Model route {route.name} is missing its key, model, or endpoint"
                )

    @property
    def remote_models_configured(self) -> bool:
        """Whether at least one selected remote route can make a network call."""

        return any(route.remote and route.configured for route in self.model_routes)

    @property
    def effective_nvidia_api_key(self) -> str:
        """Prefer NVIDIA_API_KEY while retaining DEEPSEEK_API_KEY compatibility."""

        return self.nvidia_api_key or self.deepseek_api_key

    @property
    def web_search_configured(self) -> bool:
        return self.web_enabled and bool(self.serper_api_key) and bool(self.web_allowlist)

    @property
    def langsmith_configured(self) -> bool:
        return bool(self.langsmith_api_key and self.langsmith_project)

    @property
    def langsmith_enabled(self) -> bool:
        return self.langsmith_tracing and self.langsmith_configured


# Compatibility for existing CLI/import users.  New code receives Settings through
# dependency injection so tests can use temporary directories.
settings = Settings.from_env()
