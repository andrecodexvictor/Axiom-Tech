"""Grounded synthesis through explicit OpenAI-compatible model routes."""

from __future__ import annotations

import logging
import re
import threading
import time
from dataclasses import dataclass
from typing import Any, Callable, List, Optional, Sequence

from app.config import ModelRouteConfig, Settings, settings
from app.vectorstore.port import RetrievedChunk


logger = logging.getLogger(__name__)


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
        self._clock = clock
        self._circuits = {
            route.name: _CircuitState() for route in configuration.model_routes if route.remote
        }
        self._circuit_lock = threading.Lock()

    @property
    def remote_enabled(self) -> bool:
        return self.configuration.remote_models_configured

    def synthesize(self, question: str, evidence: Sequence[RetrievedChunk]) -> SynthesisResult:
        transient_failure = False
        for route in self.configuration.model_routes:
            if not route.remote:
                return SynthesisResult(
                    answer=self._deterministic_synthesis(question, evidence),
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
                answer = self._remote_synthesize(route, question, evidence)
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
    ) -> str:
        context = "\n\n".join(
            "[{0}] {1}".format(item.metadata.get("source", "internal document"), item.content)
            for item in evidence
        )
        client = self._client_factory(
            route,
            self.configuration.llm_timeout_seconds,
            self.configuration.llm_max_retries,
        )
        response = client.chat.completions.create(
            model=route.model,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "Answer only from the supplied internal evidence. "
                        "If evidence does not establish a fact, say that it is not established. "
                        "Use the same language as the user's question. "
                        "Be concise and do not invent citations."
                    ),
                },
                {
                    "role": "user",
                    "content": "Question: {0}\n\nEvidence:\n{1}".format(question, context),
                },
            ],
            temperature=0,
            max_tokens=700,
        )
        try:
            content = response.choices[0].message.content
        except (AttributeError, IndexError, TypeError) as exc:
            raise ModelProviderResponseError(
                "The model provider returned an invalid response"
            ) from exc
        if not isinstance(content, str) or not content.strip():
            raise ModelProviderResponseError("The model provider returned an empty response")
        return content.strip()

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
    def _deterministic_synthesis(question: str, evidence: Sequence[RetrievedChunk]) -> str:
        portuguese = ModelGateway._is_portuguese(question)
        if not evidence:
            return (
                "Não encontrei evidência interna para responder a esta pergunta."
                if portuguese
                else "I could not find internal evidence that answers this question."
            )
        query_terms = set(re.findall(r"[\wÀ-ÿ][\wÀ-ÿ._/-]*", question.lower(), flags=re.UNICODE))
        excerpts: List[str] = []
        seen = set()
        for item in evidence:
            excerpt = ModelGateway._best_sentence(item.content, query_terms)
            normalized = re.sub(r"\s+", " ", excerpt).strip()
            if not normalized or normalized.lower() in seen:
                continue
            seen.add(normalized.lower())
            source = str(item.metadata.get("source", "internal document"))
            location = ModelGateway._location(item)
            excerpts.append("{0}{1}: {2}".format(source, location, normalized))
            if len(excerpts) == 3:
                break
        if not excerpts:
            return (
                "Encontrei documentos relacionados, mas nenhum trecho adequado "
                "para uma resposta fundamentada."
                if portuguese
                else "I found related internal documents, but no extract suitable "
                "for a grounded answer."
            )
        introduction = (
            "Com base na documentação interna indexada:"
            if portuguese
            else "Based on the indexed internal documentation:"
        )
        return introduction + "\n\n" + "\n".join("- " + excerpt for excerpt in excerpts)

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
        candidates = re.split(r"(?<=[.!?])\s+|\n+", content)
        nonempty = [candidate.strip() for candidate in candidates if candidate.strip()]
        if not nonempty:
            return content.strip()[:500]

        def rank(candidate: str) -> tuple:
            words = set(
                re.findall(r"[\wÀ-ÿ][\wÀ-ÿ._/-]*", candidate.lower(), flags=re.UNICODE)
            )
            return (len(words & query_terms), -abs(len(candidate) - 260), candidate.lower())

        return max(nonempty, key=rank)[:500]

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
