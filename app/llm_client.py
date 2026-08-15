"""Grounded synthesis through explicit OpenAI-compatible model routes."""

from __future__ import annotations

import logging
import re
import textwrap
import threading
import time
from dataclasses import dataclass
from typing import Any, Callable, List, Optional, Sequence

from app.config import ModelRouteConfig, Settings, settings
from app.response_modes import (
    DEFAULT_RESPONSE_MODE,
    normalize_response_mode,
    response_guidance,
)
from app.vectorstore.port import RetrievedChunk
from app.vectorstore.retrieval import tokenize


logger = logging.getLogger(__name__)

MAX_EVIDENCE_CHARS = 800
MAX_CONTEXT_CHARS = 9_000
# The console needs a concise grounded answer, not a long generation.  A
# smaller cap materially reduces tail latency on the 70B gateway route while
# leaving enough room for a short explanation and bullet list.
MAX_SYNTHESIS_TOKENS = 256


class ModelGatewayError(RuntimeError):
    """Base error safe for translation to a generic API response."""


class ModelRouteConfigurationError(ModelGatewayError):
    """A selected route is incomplete and must never be attempted."""


class ModelProviderRejected(ModelGatewayError):
    """A non-transient provider failure for which fallback is unsafe."""


class ModelProviderUnavailable(ModelGatewayError):
    """All selected remote routes failed transiently or have open circuits."""


class ModelProviderResponseError(ModelGatewayError):
    """The provider returned a successful but unusable response."""


class ModelProviderEmptyResponse(ModelProviderResponseError):
    """The provider used its completion budget without producing an answer."""


@dataclass(frozen=True)
class SynthesisResult:
    answer: str
    mode: str


@dataclass
class _CircuitState:
    transient_failures: int = 0
    opened_at: Optional[float] = None
    probe_in_flight: bool = False


ClientFactory = Callable[[ModelRouteConfig, float, int], Any]


class ModelGateway:
    """Route grounded synthesis across deterministic and remote providers.

    Route order comes only from :class:`Settings`; credentials never choose a
    provider implicitly.  Remote fallback advances only after transient network,
    rate-limit, timeout, or 5xx failures.  Authentication, permission, request,
    and response-shape failures stop the route chain and surface a sanitized 503
    at the HTTP boundary.
    """

    def __init__(
        self,
        configuration: Settings = settings,
        *,
        client_factory: Optional[ClientFactory] = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.configuration = configuration
        self._client_factory = client_factory or self._create_client
        self._reuse_clients = client_factory is None
        self._clients: dict[str, Any] = {}
        self._clock = clock
        self._circuits = {
            route.name: _CircuitState() for route in configuration.model_routes if route.remote
        }
        self._circuit_lock = threading.Lock()

    @property
    def remote_enabled(self) -> bool:
        return self.configuration.remote_models_configured

    def synthesize(
        self,
        question: str,
        evidence: Sequence[RetrievedChunk],
        *,
        response_mode: str = DEFAULT_RESPONSE_MODE,
    ) -> SynthesisResult:
        requested_mode = normalize_response_mode(response_mode)
        transient_failure = False
        for route in self.configuration.model_routes:
            if not route.remote:
                return SynthesisResult(
                    answer=self._deterministic_synthesis(
                        question, evidence, response_mode=requested_mode
                    ),
                    mode="deterministic",
                )
            if not route.configured:
                logger.error("Model route %s is not configured", route.name)
                raise ModelRouteConfigurationError("The selected model route is not configured")
            if not self._circuit_allows(route.name):
                transient_failure = True
                logger.warning("Model route %s circuit is open", route.name)
                continue
            try:
                answer = self._remote_synthesize(
                    route, question, evidence, response_mode=requested_mode
                )
            except ModelProviderEmptyResponse as exc:
                # A reasoning model can legally return HTTP 200 with no final
                # content when its reasoning budget is exhausted.  Treat that
                # shape as a transient route failure so grounded local
                # synthesis remains available instead of returning a 503.
                transient_failure = True
                self._record_transient_failure(route.name)
                logger.warning(
                    "Model route %s returned no final content (%s)",
                    route.name,
                    type(exc).__name__,
                )
                continue
            except Exception as exc:
                if self._is_transient(exc):
                    transient_failure = True
                    self._record_transient_failure(route.name)
                    logger.warning(
                        "Model route %s temporarily unavailable (%s)",
                        route.name,
                        type(exc).__name__,
                    )
                    continue
                self._record_non_transient_response(route.name)
                logger.error(
                    "Model route %s rejected request (%s)", route.name, type(exc).__name__
                )
                if isinstance(exc, ModelGatewayError):
                    raise
                raise ModelProviderRejected(
                    "The selected model provider rejected the request"
                ) from exc
            self._record_success(route.name)
            return SynthesisResult(answer=answer, mode=route.name)

        if transient_failure:
            raise ModelProviderUnavailable("No configured model route is temporarily available")
        raise ModelRouteConfigurationError("No usable model route is configured")

    def status(self) -> dict:
        routes = self.configuration.model_routes
        primary = routes[0]
        primary_remote = next((route for route in routes if route.remote), None)
        return {
            # Existing fields remain present for current API/frontend consumers.
            "gateway": primary.provider,
            "remote_enabled": self.remote_enabled,
            "model": primary_remote.model if primary_remote else None,
            "fallback": (
                "deterministic" if any(not route.remote for route in routes[1:]) else "none"
            ),
            "routes": [
                {
                    "name": route.name,
                    "provider": route.provider,
                    "model": route.model,
                    "configured": route.configured,
                    "circuit_state": self._circuit_status(route.name) if route.remote else "closed",
                }
                for route in routes
            ],
        }

    def _create_client(self, route: ModelRouteConfig, timeout: float, max_retries: int) -> Any:
        from openai import OpenAI

        client = OpenAI(
            base_url=route.base_url,
            api_key=route.api_key,
            timeout=timeout,
            max_retries=max_retries,
        )
        if self.configuration.langsmith_enabled:
            try:
                from langsmith.wrappers import wrap_openai

                client = wrap_openai(client)
            except Exception as exc:
                # Observability is optional and must not alter provider routing.
                logger.warning("Model tracing wrapper unavailable (%s)", type(exc).__name__)
        return client

    def _remote_synthesize(
        self,
        route: ModelRouteConfig,
        question: str,
        evidence: Sequence[RetrievedChunk],
        *,
        response_mode: str = DEFAULT_RESPONSE_MODE,
    ) -> str:
        context_parts: List[str] = []
        context_size = 0
        prompt_evidence = evidence
        if "muse-glimmer-30b" in str(route.model or "").lower():
            # Reasoning-heavy routes perform better with the two strongest
            # chunks than with a long mixed context; citations remain complete
            # in the API because this only limits synthesis input.
            query_terms = {term for term in tokenize(question) if len(term) > 2}
            selected = []
            for item in evidence:
                compact = self._compact_evidence(question, str(item.content))
                overlap = len(query_terms & set(tokenize(compact)))
                if selected and overlap == 0:
                    continue
                selected.append(item)
                if len(selected) == 2:
                    break
            prompt_evidence = selected or evidence[:1]
        for item in prompt_evidence:
            source = str(item.metadata.get("source", "internal document"))
            content = self._compact_evidence(question, str(item.content))
            part = "[{0}] {1}".format(source, content)
            if context_parts and context_size + len(part) > MAX_CONTEXT_CHARS:
                break
            context_parts.append(part)
            context_size += len(part)
        context = "\n\n".join(context_parts)
        client = self._get_client(route)
        request: dict[str, Any] = {
            "model": route.model,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "Use only the supplied internal evidence. "
                        "Answer in the user's language. "
                        "If it is insufficient, say so. Do not invent citations or unsupported details."
                        " "
                        + response_guidance(normalize_response_mode(response_mode))
                    ),
                },
                {
                    "role": "user",
                    "content": "Question: {0}\n\nEvidence:\n{1}".format(question, context),
                },
            ],
            "temperature": 0,
            "max_tokens": self._max_tokens(route, len(context_parts)),
        }
        extra_body = self._extra_body(route)
        if extra_body:
            request["extra_body"] = extra_body
        response = client.chat.completions.create(**request)
        try:
            message = response.choices[0].message
            content = message.content
        except (AttributeError, IndexError, TypeError) as exc:
            raise ModelProviderResponseError(
                "The model provider returned an invalid response"
            ) from exc
        if not isinstance(content, str) or not content.strip():
            raise ModelProviderEmptyResponse("The model provider returned an empty response")
        return content.strip()

    @staticmethod
    def _max_tokens(route: ModelRouteConfig, evidence_count: int = 1) -> int:
        # Muse Glimmer emits a separate reasoning stream before final content;
        # 256 tokens is often consumed before it reaches the answer.  Keep the
        # normal cap small and give this known route enough room to finish.
        if "muse-glimmer-30b" in str(route.model or "").lower():
            return 384 if evidence_count <= 1 else 512
        return MAX_SYNTHESIS_TOKENS

    @staticmethod
    def _extra_body(route: ModelRouteConfig) -> dict[str, Any]:
        """Return safe provider extensions for known reasoning model shapes.

        Muse Glimmer exposes its internal reasoning budget through a provider
        chat-template option.  Without a low reasoning setting, short RAG
        requests can spend the entire completion budget in ``reasoning_content``
        and return no user-facing ``content``.  The reasoning field is never
        used as the answer or exposed in the API.
        """

        model = str(route.model or "").lower()
        if "muse-glimmer-30b" in model:
            return {"chat_template_kwargs": {"reasoning_strength": "low"}}
        return {}

    @staticmethod
    def _compact_evidence(question: str, content: str) -> str:
        """Send the most query-relevant source lines to a remote synthesizer.

        Retrieval already selected the chunk.  This second, deterministic
        compression keeps large CSV/Markdown chunks from consuming the model's
        reasoning budget while preserving verbatim evidence and its source
        citation.  It is not a summary and never adds text.
        """

        raw = content.strip()
        normalized = re.sub(r"\s+", " ", raw)
        if len(raw) <= MAX_EVIDENCE_CHARS:
            return normalized
        query_terms = {term for term in tokenize(question) if len(term) > 2}
        segments = ModelGateway._evidence_segments(content)
        if not segments:
            return normalized[:MAX_EVIDENCE_CHARS]
        ranked, require_overlap = ModelGateway._rank_evidence_segments(
            segments,
            query_terms,
        )
        chosen = ModelGateway._fit_evidence_segments(
            ranked,
            query_terms,
            require_overlap=require_overlap,
        )
        if not chosen:
            return normalized[:MAX_EVIDENCE_CHARS]
        return " ".join(segment for _, segment in sorted(chosen))

    @staticmethod
    def _evidence_segments(content: str) -> List[str]:
        return [
            re.sub(r"\s+", " ", segment).strip()
            for segment in re.split(r"\n+|(?<=[.!?])\s+", content)
            if segment.strip()
        ]

    @staticmethod
    def _rank_evidence_segments(
        segments: Sequence[str],
        query_terms: set[str],
    ) -> tuple[List[tuple[int, str]], bool]:
        overlap_by_index = {
            index: len(query_terms & set(tokenize(segment)))
            for index, segment in enumerate(segments)
        }
        best_index = max(
            overlap_by_index,
            key=lambda index: (overlap_by_index[index], -index),
        )
        # A Markdown heading often introduces the exact list or policy section
        # needed by the question. Preserve the section containing the best
        # segment instead of returning its matching line without context.
        section = ModelGateway._markdown_section_bounds(segments, best_index)
        if overlap_by_index[best_index] > 0 and section is not None:
            section_start, section_end = section
            return (
                [(index, segments[index]) for index in range(section_start, section_end)],
                False,
            )
        ranked = sorted(
            enumerate(segments),
            key=lambda pair: (-overlap_by_index[pair[0]], pair[0]),
        )
        return ranked, True

    @staticmethod
    def _markdown_section_bounds(
        segments: Sequence[str],
        best_index: int,
    ) -> Optional[tuple[int, int]]:
        section_start = next(
            (
                index
                for index in range(best_index, -1, -1)
                if re.match(r"^#{1,6}\s", segments[index])
            ),
            None,
        )
        if section_start is None:
            return None
        section_end = next(
            (
                index
                for index in range(best_index + 1, len(segments))
                if re.match(r"^#{1,6}\s", segments[index])
            ),
            len(segments),
        )
        return section_start, section_end

    @staticmethod
    def _fit_evidence_segments(
        ranked: Sequence[tuple[int, str]],
        query_terms: set[str],
        *,
        require_overlap: bool,
    ) -> List[tuple[int, str]]:
        chosen: List[tuple[int, str]] = []
        size = 0
        for index, segment in ranked:
            overlap = len(query_terms & set(tokenize(segment)))
            if chosen and overlap == 0 and require_overlap:
                continue
            addition = len(segment) + (1 if chosen else 0)
            if size + addition > MAX_EVIDENCE_CHARS:
                continue
            chosen.append((index, segment))
            size += addition
            if size >= MAX_EVIDENCE_CHARS:
                break
        return chosen

    def _get_client(self, route: ModelRouteConfig) -> Any:
        if self._reuse_clients and route.name in self._clients:
            return self._clients[route.name]
        client = self._client_factory(
            route,
            self.configuration.llm_timeout_seconds,
            self.configuration.llm_max_retries,
        )
        if self._reuse_clients:
            self._clients[route.name] = client
        return client

    @staticmethod
    def _is_transient(exc: Exception) -> bool:
        if isinstance(exc, (TimeoutError, ConnectionError)):
            return True
        status_code = getattr(exc, "status_code", None)
        if isinstance(status_code, int) and (
            status_code in {408, 409, 429} or 500 <= status_code <= 599
        ):
            return True
        try:
            from openai import (
                APIConnectionError,
                APITimeoutError,
                InternalServerError,
                RateLimitError,
            )
        except ImportError:
            return False
        return isinstance(
            exc, (APIConnectionError, APITimeoutError, InternalServerError, RateLimitError)
        )

    def _circuit_allows(self, route_name: str) -> bool:
        with self._circuit_lock:
            circuit = self._circuits[route_name]
            if circuit.opened_at is None:
                return True
            elapsed = self._clock() - circuit.opened_at
            if elapsed < self.configuration.llm_circuit_recovery_seconds:
                return False
            if circuit.probe_in_flight:
                return False
            # Keep the circuit marked open while exactly one half-open probe runs.
            # Other threads continue to the next explicit route.
            circuit.probe_in_flight = True
            return True

    def _record_transient_failure(self, route_name: str) -> None:
        with self._circuit_lock:
            circuit = self._circuits[route_name]
            circuit.transient_failures += 1
            circuit.probe_in_flight = False
            if circuit.transient_failures >= self.configuration.llm_circuit_failure_threshold:
                circuit.opened_at = self._clock()

    def _record_success(self, route_name: str) -> None:
        with self._circuit_lock:
            self._circuits[route_name] = _CircuitState()

    def _record_non_transient_response(self, route_name: str) -> None:
        # A provider response proves connectivity, so old transient failures must
        # not later open the circuit.  The current non-transient error still fails.
        self._record_success(route_name)

    def _circuit_status(self, route_name: str) -> str:
        with self._circuit_lock:
            circuit = self._circuits[route_name]
            if circuit.opened_at is None:
                return "closed"
            return "open"

    @staticmethod
    def _deterministic_synthesis(
        question: str,
        evidence: Sequence[RetrievedChunk],
        *,
        response_mode: str = DEFAULT_RESPONSE_MODE,
    ) -> str:
        portuguese = ModelGateway._is_portuguese(question)
        if not evidence:
            return (
                "Não encontrei evidência interna para responder a esta pergunta."
                if portuguese
                else "I could not find internal evidence that answers this question."
            )
        mode = normalize_response_mode(response_mode)
        limits = {
            "concise": (2, 320),
            "detailed": (5, 480),
            "checklist": (4, 300),
            "evidence": (4, 480),
        }
        limit, max_chars = limits[mode]
        excerpts = ModelGateway._grounded_excerpts(
            question, evidence, limit=limit, max_chars=max_chars
        )
        if not excerpts:
            return (
                "Encontrei documentos relacionados, mas nenhum trecho adequado "
                "para uma resposta fundamentada."
                if portuguese
                else "I found related internal documents, but no extract suitable "
                "for a grounded answer."
            )

        introductions = {
            "concise": (
                "Com base na documentação interna indexada:"
                if portuguese
                else "Based on the indexed internal documentation:"
            ),
            "detailed": (
                "A documentação interna sustenta os seguintes pontos:"
                if portuguese
                else "The internal documentation supports these points:"
            ),
            "checklist": (
                "Checklist fundamentado na documentação interna:"
                if portuguese
                else "Checklist grounded in the internal documentation:"
            ),
            "evidence": (
                "Trechos de evidência da documentação interna:"
                if portuguese
                else "Evidence excerpts from the internal documentation:"
            ),
        }
        return introductions[mode] + "\n\n" + "\n".join("- " + item for item in excerpts)

    @staticmethod
    def _grounded_excerpts(
        question: str,
        evidence: Sequence[RetrievedChunk],
        *,
        limit: int,
        max_chars: int,
    ) -> List[str]:
        query_terms = set(tokenize(question))
        excerpts: List[str] = []
        seen = set()
        for item in evidence:
            compact_content = ModelGateway._compact_evidence(question, item.content)
            excerpt = ModelGateway._best_sentence(compact_content, query_terms)
            normalized = ModelGateway._plain_excerpt(excerpt, max_chars=max_chars)
            if not normalized or normalized.lower() in seen:
                continue
            seen.add(normalized.lower())
            source = str(item.metadata.get("source", "internal document"))
            location = ModelGateway._location(item)
            excerpts.append("{0}{1}: {2}".format(source, location, normalized))
            if len(excerpts) >= max(1, int(limit)):
                break
        return excerpts

    @staticmethod
    def _plain_excerpt(value: str, *, max_chars: int) -> str:
        text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", value)
        text = re.sub(r"[*_`]+", "", text)
        # Some image-based or font-mapped PDFs yield only Unicode replacement
        # characters. They are not usable evidence and must not reach the UI.
        text = text.replace("\ufffd", " ")
        text = re.sub(r"\s+", " ", text).strip()
        return textwrap.shorten(text, width=max(80, int(max_chars)), placeholder="…")

    @staticmethod
    def _is_portuguese(question: str) -> bool:
        value = question.lower()
        if re.search(r"[áàâãéêíóôõúç]", value):
            return True
        words = set(re.findall(r"[a-z]+", value))
        return bool(
            words & {"como", "qual", "quais", "devo", "segundo", "política", "incidente"}
        )

    @staticmethod
    def _best_sentence(content: str, query_terms: set) -> str:
        # Prefer a compact paragraph/section over an isolated heading or a
        # single bullet.  This is especially important for policies whose
        # answer is a list (for example, LGPD data-subject rights): the
        # deterministic fallback should show the list that the citation came
        # from, not only the section title.
        candidates = re.split(r"\n{2,}", content)
        nonempty = [candidate.strip() for candidate in candidates if candidate.strip()]
        if not nonempty:
            return content.strip()[:500]

        def rank(candidate: str) -> tuple:
            words = set(tokenize(candidate))
            return (len(words & query_terms), min(len(candidate), 500), candidate.lower())

        selected = max(nonempty, key=rank)
        return re.sub(r"(?m)^#{1,6}\s*", "", selected)[:500]

    @staticmethod
    def _location(item: RetrievedChunk) -> str:
        metadata = item.metadata
        if metadata.get("page") is not None:
            return " (page {0})".format(metadata["page"])
        if metadata.get("slide") is not None:
            return " (slide {0})".format(metadata["slide"])
        if metadata.get("sheet"):
            return " (sheet {0})".format(metadata["sheet"])
        return ""


# Existing imports keep working while composition can use the provider-neutral name.
NvidiaGateway = ModelGateway
