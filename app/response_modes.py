"""Public response-shape vocabulary for grounded internal answers."""

from __future__ import annotations

from typing import Literal


ResponseMode = Literal["concise", "detailed", "checklist", "evidence"]
DEFAULT_RESPONSE_MODE: ResponseMode = "concise"
RESPONSE_MODES = frozenset({"concise", "detailed", "checklist", "evidence"})


def normalize_response_mode(value: str) -> ResponseMode:
    normalized = str(value or DEFAULT_RESPONSE_MODE).strip().lower()
    if normalized not in RESPONSE_MODES:
        raise ValueError("Unsupported response mode")
    return normalized  # type: ignore[return-value]


def response_guidance(mode: ResponseMode, *, portuguese: bool = False) -> str:
    if portuguese:
        return {
            "concise": "Responda diretamente em no máximo dois parágrafos curtos.",
            "detailed": "Explique a resposta com contexto, regras e passos práticos sustentados pelas fontes.",
            "checklist": "Organize as ações e os requisitos sustentados pelas fontes como um checklist claro.",
            "evidence": "Priorize evidências curtas, traduzidas quando necessário, e identifique cada fonte fornecida.",
        }[mode]
    return {
        "concise": "Answer directly in at most two short paragraphs.",
        "detailed": "Explain the answer with context, rules, and practical steps when supported.",
        "checklist": "Format supported actions and requirements as a clear checklist.",
        "evidence": "Prioritize short verbatim evidence excerpts and identify each supplied source.",
    }[mode]
