"""Fail-closed, allowlisted web research for explicitly requested web queries."""

from __future__ import annotations

import hashlib
import ipaddress
import re
import socket
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple
from urllib.parse import urljoin, urlsplit, urlunsplit

import httpx

from app.agents.state import GraphTraceEvent
from app.config import Settings, settings


SERPER_SEARCH_URL = "https://google.serper.dev/search"
MAX_REDIRECTS = 2
USER_AGENT = "AxiomTechKnowledgeBot/3.0 (+allowlisted-research)"


@dataclass(frozen=True)
class SearchCandidate:
    title: str
    url: str
    snippet: str = ""


@dataclass(frozen=True)
class EvaluatedPage:
    title: str
    url: str
    text: str
    score: float


@dataclass(frozen=True)
class WebResearchResult:
    answer: str
    citations: List[Dict[str, Any]]
    trace: List[GraphTraceEvent]
    grounded: bool


class UnsafeWebUrl(ValueError):
    """Raised before a potentially unsafe URL can be requested."""


class WebResearchAgent:
    """Execute plan → search → fetch → evaluate → refine/synthesize safely.

    Search and network fetching are opt-in.  All candidate and redirect URLs are
    validated before requests: HTTPS only, no IP literals or userinfo, and an exact
    configured host/subdomain allowlist match.  This makes web research a bounded
    capability rather than a general outbound-proxy primitive.
    """

    def __init__(
        self,
        configuration: Settings = settings,
        client_factory: Optional[Callable[[], httpx.Client]] = None,
        resolver: Optional[Callable[[str], Sequence[str]]] = None,
    ) -> None:
        self.configuration = configuration
        self._client_factory = client_factory or self._default_client
        self._resolver = resolver or self._resolve_host

    def _default_client(self) -> httpx.Client:
        return httpx.Client(
            timeout=httpx.Timeout(self.configuration.web_timeout_seconds),
            follow_redirects=False,
            headers={"User-Agent": USER_AGENT},
        )

    def research(self, question: str, limit: int = 4) -> WebResearchResult:
        trace: List[GraphTraceEvent] = [
            self._trace("plan", "planned", "Prepared an allowlisted web-research plan")
        ]
        unavailable = self._unavailable_result(trace, question)
        if unavailable is not None:
            return unavailable

        candidates: List[SearchCandidate] = []
        search_error: Optional[str] = None
        try:
            with self._client_factory() as client:
                candidates = self._search(client, question, limit)
                trace.append(
                    self._trace(
                        "search", "completed", "Accepted {0} allowlisted search candidate(s)".format(len(candidates))
                    )
                )
                pages, failures = self._fetch_candidates(client, candidates)
        except Exception as exc:
            # Do not include provider bodies, request URLs, or credentials in API
            # output. The exception class gives an operator enough signal.
            search_error = type(exc).__name__
            pages = []
            failures = 0
            trace.append(self._trace("search", "unavailable", "Search request was unavailable ({0})".format(search_error)))

        if search_error is None:
            trace.append(
                self._trace(
                    "fetch",
                    "completed",
                    "Fetched {0} page(s); rejected or failed {1}".format(len(pages), failures),
                )
            )
        evaluated = self._evaluate(question, pages)
        trace.append(
            self._trace(
                "evaluate",
                "completed",
                "Accepted {0} page(s) with direct textual evidence".format(len(evaluated)),
            )
        )
        if not evaluated:
            trace.append(
                self._trace(
                    "refine_synthesize",
                    "unsupported",
                    "No fetched allowlisted source established an answer",
                )
            )
            return WebResearchResult(
                answer=(
                    "Não consegui verificar uma resposta nas fontes web permitidas. "
                    "Tente uma pergunta mais específica ou amplie a allowlist deliberadamente."
                    if self._is_portuguese(question)
                    else "I could not verify an answer from the configured allowlisted web sources. "
                    "Try a more specific question or expand the allowlist deliberately."
                ),
                citations=[],
                trace=trace,
                grounded=False,
            )

        answer, citations = self._synthesize(question, evaluated)
        if not citations:
            trace.append(
                self._trace(
                    "refine_synthesize",
                    "unsupported",
                    "Verified pages did not yield a citable excerpt",
                )
            )
            return WebResearchResult(answer=answer, citations=[], trace=trace, grounded=False)
        trace.append(
            self._trace(
                "refine_synthesize",
                "grounded",
                "Synthesized from {0} verified allowlisted source(s)".format(len(citations)),
            )
        )
        return WebResearchResult(answer=answer, citations=citations, trace=trace, grounded=True)

    def is_allowed_url(self, value: str) -> bool:
        """Return whether a URL may be fetched under the configured SSRF policy."""

        try:
            parsed = urlsplit(value)
            if parsed.scheme.lower() != "https" or not parsed.hostname:
                return False
            if parsed.username or parsed.password:
                return False
            try:
                port = parsed.port
            except ValueError:
                return False
            if port not in (None, 443):
                return False
            host = self._normalise_host(parsed.hostname)
            if not host:
                return False
            try:
                ipaddress.ip_address(host)
                return False
            except ValueError:
                pass
            return any(host == allowed or host.endswith("." + allowed) for allowed in self.configuration.web_allowlist)
        except (TypeError, ValueError):
            return False

    def _unavailable_result(
        self, trace: List[GraphTraceEvent], question: str
    ) -> Optional[WebResearchResult]:
        portuguese = self._is_portuguese(question)
        if not self.configuration.web_enabled:
            reason = (
                "A pesquisa web está desativada. Defina AXIOM_WEB_ENABLED=true para habilitá-la."
                if portuguese
                else "Web research is disabled. Set AXIOM_WEB_ENABLED=true to enable it."
            )
            event = "disabled"
        elif not self.configuration.serper_api_key:
            reason = (
                "A pesquisa web está indisponível porque a credencial do Serper não foi configurada."
                if portuguese
                else "Web research is unavailable because a Serper search credential is not configured."
            )
            event = "unconfigured"
        elif not self.configuration.web_allowlist:
            reason = (
                "A pesquisa web está indisponível porque nenhum host permitido foi configurado."
                if portuguese
                else "Web research is unavailable because no allowed web hosts are configured."
            )
            event = "unconfigured"
        else:
            return None
        trace.extend(
            [
                self._trace("search", event, "No external search request was made"),
                self._trace("fetch", "not_run", "No external page was fetched"),
                self._trace("evaluate", "not_run", "No external evidence was evaluated"),
                self._trace("refine_synthesize", "unsupported", "No web evidence is available"),
            ]
        )
        return WebResearchResult(answer=reason, citations=[], trace=trace, grounded=False)

    def _search(self, client: httpx.Client, question: str, limit: int) -> List[SearchCandidate]:
        accepted_limit = max(1, min(int(limit), 10))
        response = client.post(
            SERPER_SEARCH_URL,
            headers={"X-API-KEY": self.configuration.serper_api_key, "Content-Type": "application/json"},
            json={"q": question, "num": accepted_limit},
        )
        content = self._response_bytes(response)
        response.raise_for_status()
        payload = response.json() if content else {}
        if not isinstance(payload, dict):
            return []
        candidates = []
        seen_urls = set()
        for item in payload.get("organic", []):
            if not isinstance(item, dict):
                continue
            url = str(item.get("link", "")).strip()
            if not self.is_allowed_url(url):
                continue
            canonical = self._canonical_url(url)
            if canonical in seen_urls:
                continue
            seen_urls.add(canonical)
            candidates.append(
                SearchCandidate(
                    title=str(item.get("title", "")).strip() or self._host_for_url(url),
                    url=canonical,
                    snippet=str(item.get("snippet", "")).strip(),
                )
            )
            if len(candidates) >= accepted_limit:
                break
        return candidates

    def _fetch_candidates(
        self, client: httpx.Client, candidates: Sequence[SearchCandidate]
    ) -> Tuple[List[EvaluatedPage], int]:
        pages: List[EvaluatedPage] = []
        failures = 0
        for candidate in candidates:
            try:
                final_url, content_type, content = self._fetch(client, candidate.url)
                if content_type not in {"text/html", "application/xhtml+xml", "text/plain"}:
                    failures += 1
                    continue
                title, text = self._html_to_text(content, fallback_title=candidate.title)
                if not text:
                    failures += 1
                    continue
                pages.append(EvaluatedPage(title=title, url=final_url, text=text, score=0.0))
            except (httpx.HTTPError, UnsafeWebUrl, ValueError, UnicodeError):
                failures += 1
        return pages, failures

    def _fetch(self, client: httpx.Client, url: str) -> Tuple[str, str, bytes]:
        current = self._canonical_url(url)
        for _ in range(MAX_REDIRECTS + 1):
            if not self.is_allowed_url(current):
                raise UnsafeWebUrl("URL is outside the web allowlist")
            self._assert_public_resolution(current)
            with client.stream(
                "GET", current, headers={"User-Agent": USER_AGENT}, follow_redirects=False
            ) as response:
                if response.status_code in {301, 302, 303, 307, 308}:
                    location = response.headers.get("location")
                    if not location:
                        raise ValueError("Redirect response had no location")
                    next_url = self._canonical_url(urljoin(current, location))
                    # Validate before following the redirect; never hand the HTTP
                    # client an off-allowlist redirect destination.
                    if not self.is_allowed_url(next_url):
                        raise UnsafeWebUrl("Redirect URL is outside the web allowlist")
                    current = next_url
                    continue
                response.raise_for_status()
                content = self._stream_response_bytes(response)
                content_type = (
                    response.headers.get("content-type", "")
                    .split(";", 1)[0]
                    .strip()
                    .lower()
                )
                return current, content_type, content
        raise ValueError("Too many redirects")

    def _response_bytes(self, response: httpx.Response) -> bytes:
        header = response.headers.get("content-length")
        if header:
            try:
                declared_size = int(header)
            except ValueError:
                # An invalid content-length is not trusted; actual bytes below
                # still enforce the cap.
                declared_size = 0
            if declared_size > self.configuration.web_max_response_bytes:
                raise ValueError("Response exceeded configured size cap")
        content = response.content
        if len(content) > self.configuration.web_max_response_bytes:
            raise ValueError("Response exceeded configured size cap")
        return content

    def _stream_response_bytes(self, response: httpx.Response) -> bytes:
        header = response.headers.get("content-length")
        if header:
            try:
                declared_size = int(header)
            except ValueError:
                # Invalid size metadata is not trusted; the running cap below
                # remains authoritative.
                declared_size = 0
            if declared_size > self.configuration.web_max_response_bytes:
                raise ValueError("Response exceeded configured size cap")
        content = bytearray()
        for block in response.iter_bytes():
            content.extend(block)
            if len(content) > self.configuration.web_max_response_bytes:
                raise ValueError("Response exceeded configured size cap")
        return bytes(content)

    def _assert_public_resolution(self, value: str) -> None:
        host = self._host_for_url(value)
        try:
            addresses = list(self._resolver(host))
        except (OSError, ValueError, UnicodeError) as exc:
            raise UnsafeWebUrl("Allowed host could not be resolved safely") from exc
        if not addresses:
            raise UnsafeWebUrl("Allowed host had no resolved address")
        for address in addresses:
            try:
                parsed = ipaddress.ip_address(address)
            except ValueError as exc:
                raise UnsafeWebUrl("Resolver returned an invalid address") from exc
            if not parsed.is_global:
                raise UnsafeWebUrl("Allowed host resolved to a non-public address")

    @staticmethod
    def _resolve_host(host: str) -> Sequence[str]:
        values = socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)
        return tuple(dict.fromkeys(str(item[4][0]) for item in values))

    def _evaluate(self, question: str, pages: Sequence[EvaluatedPage]) -> List[EvaluatedPage]:
        terms = self._meaningful_terms(question)
        accepted: List[EvaluatedPage] = []
        for page in pages:
            content = page.text.lower()
            matching = sum(1 for term in terms if term in content)
            score = matching / max(1, len(terms))
            if score >= 0.15:
                accepted.append(EvaluatedPage(page.title, page.url, page.text, score))
        return sorted(accepted, key=lambda page: (-page.score, page.url))[:3]

    def _synthesize(
        self, question: str, pages: Sequence[EvaluatedPage]
    ) -> Tuple[str, List[Dict[str, Any]]]:
        terms = set(self._meaningful_terms(question))
        excerpts = []
        citations = []
        for index, page in enumerate(pages):
            excerpt = self._best_sentence(page.text, terms)
            if not excerpt:
                continue
            source = page.title or self._host_for_url(page.url)
            excerpts.append("- {0}: {1}".format(source, excerpt))
            identifier = hashlib.sha256(page.url.encode("utf-8")).hexdigest()
            citations.append(
                {
                    "id": identifier,
                    "source": source,
                    "domain": "web",
                    "file_type": "html",
                    "chunk_id": identifier,
                    "chunk_index": index,
                    "score": round(page.score, 4),
                    "url": page.url,
                }
            )
        if not excerpts:
            return (
                "I could not extract a grounded answer from the fetched allowlisted pages.",
                [],
            )
        introduction = (
            "Com base nas fontes web permitidas e verificadas:"
            if self._is_portuguese(question)
            else "Based on reviewed allowlisted web sources:"
        )
        return introduction + "\n\n" + "\n".join(excerpts), citations

    @staticmethod
    def _html_to_text(content: bytes, fallback_title: str) -> Tuple[str, str]:
        try:
            from bs4 import BeautifulSoup

            soup = BeautifulSoup(content, "html.parser")
            for tag in soup(["script", "style", "noscript", "svg", "iframe"]):
                tag.decompose()
            title = soup.title.get_text(" ", strip=True) if soup.title else fallback_title
            text = soup.get_text(" ", strip=True)
        except Exception:
            decoded = content.decode("utf-8", errors="ignore")
            title = fallback_title
            text = re.sub(r"<[^>]+>", " ", decoded)
        return title[:240], re.sub(r"\s+", " ", text).strip()[:20_000]

    @staticmethod
    def _meaningful_terms(question: str) -> List[str]:
        stop_words = {
            "a", "an", "and", "as", "at", "como", "da", "de", "do", "e", "for", "how", "is", "o", "of",
            "on", "or", "os", "para", "qual", "que", "the", "to", "um", "uma", "what", "with",
        }
        return [
            word
            for word in re.findall(r"[\wÀ-ÿ][\wÀ-ÿ._/-]*", question.lower(), flags=re.UNICODE)
            if len(word) > 2 and word not in stop_words
        ]

    @staticmethod
    def _is_portuguese(question: str) -> bool:
        value = question.lower()
        return bool(re.search(r"[áàâãéêíóôõúç]", value)) or bool(
            set(re.findall(r"[a-z]+", value)) & {"como", "qual", "quais", "devo", "segundo", "pesquise"}
        )

    @staticmethod
    def _best_sentence(text: str, terms: set) -> str:
        candidates = [part.strip() for part in re.split(r"(?<=[.!?])\s+|\n+", text) if part.strip()]
        if not candidates:
            return ""
        def rank(candidate: str) -> Tuple[int, int, str]:
            words = set(re.findall(r"[\wÀ-ÿ][\wÀ-ÿ._/-]*", candidate.lower(), flags=re.UNICODE))
            return (len(words & terms), -abs(len(candidate) - 280), candidate.lower())
        return max(candidates, key=rank)[:600]

    @staticmethod
    def _normalise_host(host: str) -> str:
        try:
            return host.encode("idna").decode("ascii").lower().rstrip(".")
        except UnicodeError:
            return ""

    @staticmethod
    def _canonical_url(value: str) -> str:
        parsed = urlsplit(value)
        return urlunsplit((parsed.scheme.lower(), parsed.netloc, parsed.path or "/", parsed.query, ""))

    @staticmethod
    def _host_for_url(value: str) -> str:
        return urlsplit(value).hostname or "web source"

    @staticmethod
    def _trace(event: str, outcome: str, details: str) -> GraphTraceEvent:
        return {"node": "web_research", "event": event + "." + outcome, "details": details}
