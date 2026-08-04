"""Credential-optional NVIDIA model gateway with a grounded local fallback."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Iterable, List, Optional, Sequence

from app.config import Settings, settings
from app.vectorstore.port import RetrievedChunk


logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class SynthesisResult:
    answer: str
    mode: str


class NvidiaGateway:
    """Small adapter around NVIDIA-compatible APIs.

    Remote calls are disabled unless both ``AXIOM_NVIDIA_ENABLED=true`` and an
    applicable credential are present.  Failures are intentionally logged only by
    exception class; credentials and provider response bodies never reach logs or
    API responses.
    """

    def __init__(self, configuration: Settings = settings) -> None:
        self.configuration = configuration

    @property
    def remote_enabled(self) -> bool:
        return self.configuration.remote_models_configured

    def synthesize(self, question: str, evidence: Sequence[RetrievedChunk]) -> SynthesisResult:
        if self.remote_enabled and self.configuration.effective_nvidia_api_key:
            answer = self._remote_synthesize(question, evidence)
            if answer:
                return SynthesisResult(answer=answer, mode="nvidia")
        return SynthesisResult(answer=self._deterministic_synthesis(question, evidence), mode="deterministic")

    def status(self) -> dict:
        return {
            "gateway": "nvidia",
            "remote_enabled": self.remote_enabled,
            "model": self.configuration.nvidia_model,
        }

    def _remote_synthesize(self, question: str, evidence: Sequence[RetrievedChunk]) -> Optional[str]:
        context = "\n\n".join(
            "[{0}] {1}".format(item.metadata.get("source", "internal document"), item.content)
            for item in evidence
        )
        try:
            from openai import OpenAI

            client = OpenAI(
                base_url=self.configuration.nvidia_base_url,
                api_key=self.configuration.effective_nvidia_api_key,
            )
            response = client.chat.completions.create(
                model=self.configuration.nvidia_model,
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
                    {"role": "user", "content": "Question: {0}\n\nEvidence:\n{1}".format(question, context)},
                ],
                temperature=0,
                max_tokens=700,
            )
            content = response.choices[0].message.content
            return content.strip() if content and content.strip() else None
        except Exception as exc:  # Network/provider errors must not break grounded local operation.
            logger.warning("NVIDIA synthesis unavailable (%s); using deterministic fallback", type(exc).__name__)
            return None

    @staticmethod
    def _deterministic_synthesis(question: str, evidence: Sequence[RetrievedChunk]) -> str:
        portuguese = NvidiaGateway._is_portuguese(question)
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
            excerpt = NvidiaGateway._best_sentence(item.content, query_terms)
            normalized = re.sub(r"\s+", " ", excerpt).strip()
            if not normalized or normalized.lower() in seen:
                continue
            seen.add(normalized.lower())
            source = str(item.metadata.get("source", "internal document"))
            location = NvidiaGateway._location(item)
            excerpts.append("{0}{1}: {2}".format(source, location, normalized))
            if len(excerpts) == 3:
                break
        if not excerpts:
            return (
                "Encontrei documentos relacionados, mas nenhum trecho adequado para uma resposta fundamentada."
                if portuguese
                else "I found related internal documents, but no extract suitable for a grounded answer."
            )
        introduction = (
            "Com base na documentação interna indexada:"
            if portuguese
            else "Based on the indexed internal documentation:"
        )
        return introduction + "\n\n" + "\n".join(
            "- " + excerpt for excerpt in excerpts
        )

    @staticmethod
    def _is_portuguese(question: str) -> bool:
        value = question.lower()
        if re.search(r"[áàâãéêíóôõúç]", value):
            return True
        words = set(re.findall(r"[a-z]+", value))
        return bool(words & {"como", "qual", "quais", "devo", "segundo", "política", "incidente"})

    @staticmethod
    def _best_sentence(content: str, query_terms: set) -> str:
        candidates = re.split(r"(?<=[.!?])\s+|\n+", content)
        nonempty = [candidate.strip() for candidate in candidates if candidate.strip()]
        if not nonempty:
            return content.strip()[:500]
        def rank(candidate: str) -> tuple:
            words = set(re.findall(r"[\wÀ-ÿ][\wÀ-ÿ._/-]*", candidate.lower(), flags=re.UNICODE))
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


class UnifiedNVIDIAClient:
    """Compatibility facade for previous agent imports.

    It deliberately returns local deterministic results instead of sending a
    credential-free request with an empty bearer token.
    """

    def __init__(self, configuration: Settings = settings) -> None:
        self.gateway = NvidiaGateway(configuration)

    def invoke_kimi(self, prompt: str, system_prompt: str = "") -> str:
        # Preserve an inexpensive routing-compatible result for legacy agents.
        words = (prompt + " " + system_prompt).lower()
        if any(word in words for word in ("lgpd", "privacidade", "termo", "legal")):
            return "juridico"
        if any(word in words for word in ("benefício", "beneficio", "onboarding", "home office", "rh")):
            return "rh"
        if any(word in words for word in ("endpoint", "api", "repo", "github")):
            return "repo"
        return "engenharia"

    def invoke_minimax(self, prompt: str, system_prompt: str = "") -> str:
        return "A local grounded response is available through the V3 query workflow."

    def invoke_deepseek_rag(self, prompt: str, context_docs: str = "") -> str:
        return "A local grounded response is available through the V3 query workflow."


nvidia_client = UnifiedNVIDIAClient()
