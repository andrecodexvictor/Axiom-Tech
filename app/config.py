"""Configuration for the Axiom Tech modular monolith.

Settings deliberately contain no logging or string representation of secrets.  The
application must be useful with an empty ``.env``: cloud integrations are opt-in
and local Chroma plus deterministic embeddings remain the default.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, Tuple
from urllib.parse import urlsplit

from dotenv import load_dotenv


BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")


def _as_bool(value: Optional[str], default: bool = False) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


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
        # A registrable-looking host keeps an accidental value such as `com` from
        # becoming an effectively unbounded allowlist.
        if len(labels) >= 2 and all(label and label.replace("-", "").isalnum() for label in labels):
            hosts.append(host)
    return tuple(dict.fromkeys(hosts))


def _safe_https_url(value: Optional[str], default: str) -> str:
    """Accept only a credential-safe HTTPS endpoint without URL credentials.

    A custom HTTPS endpoint receives the configured NVIDIA credential. Operators
    must therefore set it only to an endpoint they trust; malformed or insecure
    values fall back to the NVIDIA hosted endpoint rather than being used.
    """

    candidate = (value or default).strip().rstrip("/")
    parsed = urlsplit(candidate)
    if (
        parsed.scheme == "https"
        and parsed.hostname
        and not parsed.username
        and not parsed.password
        and not parsed.query
        and not parsed.fragment
    ):
        return candidate
    return default


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
    kimi_api_key: str
    minimax_api_key: str
    deepseek_api_key: str
    pinecone_api_key: str
    pinecone_index_name: str
    pinecone_environment: str
    # New NVIDIA variables supersede the model-specific legacy key. Defaults keep
    # direct Settings construction backwards-compatible in existing integrations.
    nvidia_api_key: str = ""
    nvidia_model: str = "meta/llama-3.1-70b-instruct"
    nvidia_base_url: str = "https://integrate.api.nvidia.com/v1"
    web_enabled: bool = False
    serper_api_key: str = ""
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

    @classmethod
    def from_env(cls) -> "Settings":
        documents_dir = Path(os.getenv("AXIOM_DOCUMENTS_DIR", str(BASE_DIR / "documentos"))).expanduser()
        chroma_path = Path(os.getenv("AXIOM_CHROMA_PATH", str(BASE_DIR / ".axiom_chroma"))).expanduser()
        return cls(
            documents_dir=documents_dir,
            chroma_path=chroma_path,
            chroma_collection=os.getenv("AXIOM_CHROMA_COLLECTION", "axiom_knowledge"),
            vector_backend=os.getenv("AXIOM_VECTOR_BACKEND", "chroma").strip().lower(),
            chunk_size=max(100, int(os.getenv("AXIOM_CHUNK_SIZE", "900"))),
            chunk_overlap=max(0, int(os.getenv("AXIOM_CHUNK_OVERLAP", "150"))),
            cors_origins=_origins(os.getenv("AXIOM_CORS_ORIGINS")),
            nvidia_enabled=_as_bool(os.getenv("AXIOM_NVIDIA_ENABLED"), default=False),
            kimi_api_key=os.getenv("KIMI_API_KEY", ""),
            minimax_api_key=os.getenv("MINIMAX_API_KEY", ""),
            deepseek_api_key=os.getenv("DEEPSEEK_API_KEY", ""),
            pinecone_api_key=os.getenv("PINECONE_API_KEY", ""),
            pinecone_index_name=os.getenv("PINECONE_INDEX_NAME", "axiom-tech-knowledge"),
            pinecone_environment=os.getenv("PINECONE_ENVIRONMENT", "us-east-1"),
            nvidia_api_key=os.getenv("NVIDIA_API_KEY") or os.getenv("DEEPSEEK_API_KEY", ""),
            nvidia_model=os.getenv("NVIDIA_MODEL", "meta/llama-3.1-70b-instruct").strip()
            or "meta/llama-3.1-70b-instruct",
            nvidia_base_url=_safe_https_url(
                os.getenv("AXIOM_NVIDIA_BASE_URL"), "https://integrate.api.nvidia.com/v1"
            ),
            web_enabled=_as_bool(os.getenv("AXIOM_WEB_ENABLED"), default=False),
            serper_api_key=os.getenv("SERPER_API_KEY", ""),
            web_allowlist=_hosts(os.getenv("AXIOM_WEB_ALLOWLIST")),
            web_timeout_seconds=min(30.0, max(1.0, float(os.getenv("AXIOM_WEB_TIMEOUT_SECONDS", "8")))),
            web_max_response_bytes=min(
                5_000_000, max(8_192, int(os.getenv("AXIOM_WEB_MAX_RESPONSE_BYTES", "1000000")))
            ),
            langsmith_tracing=_as_bool(
                os.getenv("LANGSMITH_TRACING") or os.getenv("LANGCHAIN_TRACING_V2"), default=False
            ),
            langsmith_api_key=os.getenv("LANGSMITH_API_KEY") or os.getenv("LANGCHAIN_API_KEY", ""),
            langsmith_endpoint=_safe_https_url(
                os.getenv("LANGSMITH_ENDPOINT") or os.getenv("LANGCHAIN_ENDPOINT"),
                "https://api.smith.langchain.com",
            ),
            langsmith_project=(
                os.getenv("LANGSMITH_PROJECT")
                or os.getenv("LANGCHAIN_PROJECT")
                or "axiom-tech-v3"
            ).strip()
            or "axiom-tech-v3",
            langsmith_workspace_id=os.getenv("LANGSMITH_WORKSPACE_ID", "").strip(),
            langsmith_hide_inputs=_as_bool(os.getenv("LANGSMITH_HIDE_INPUTS"), default=True),
            langsmith_hide_outputs=_as_bool(os.getenv("LANGSMITH_HIDE_OUTPUTS"), default=True),
        )

    @property
    def remote_models_configured(self) -> bool:
        """Whether the explicit remote-model opt-in can make a network call."""

        return self.nvidia_enabled and bool(self.nvidia_api_key or self.deepseek_api_key)

    @property
    def effective_nvidia_api_key(self) -> str:
        """Prefer NVIDIA_API_KEY while retaining DEEPSEEK_API_KEY compatibility."""

        return self.nvidia_api_key or self.deepseek_api_key

    @property
    def web_search_configured(self) -> bool:
        return self.web_enabled and bool(self.serper_api_key) and bool(self.web_allowlist)

    @property
    def langsmith_configured(self) -> bool:
        """Whether LangSmith has the non-public values required for tracing."""

        return bool(self.langsmith_api_key and self.langsmith_project)

    @property
    def langsmith_enabled(self) -> bool:
        """Whether tracing is explicitly enabled and can authenticate."""

        return self.langsmith_tracing and self.langsmith_configured


# Compatibility for existing CLI/import users.  New code receives Settings through
# dependency injection so tests can use temporary directories.
settings = Settings.from_env()
