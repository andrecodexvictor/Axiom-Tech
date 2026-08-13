"""Deterministic, auditable routing for the grounded knowledge workflow."""

from __future__ import annotations

import re
from typing import Optional


SUPPORTED_DOMAINS = {"rh", "juridico", "engenharia", "api_spec", "web"}


_DOMAIN_RULES = (
    (
        "web",
        (
            "search the web",
            "web research",
            "internet research",
            "online research",
            "external research",
            "pesquise na web",
            "pesquisa na web",
        ),
    ),
    (
        "juridico",
        (
            "lgpd",
            "privacidade",
            "privacy",
            "termo",
            "terms",
            "legal",
            "compliance",
            "dados pessoais",
        ),
    ),
    (
        "rh",
        (
            "home office",
            "benefício",
            "beneficio",
            "onboarding",
            "reembolso",
            "expense",
            "férias",
            "ferias",
            "recursos humanos",
            "rh",
        ),
    ),
    (
        "api_spec",
        ("endpoint", "api", "repo", "github", "openapi", "swagger", "repository"),
    ),
)


def classify_domain(question: str) -> str:
    value = question.casefold()
    for domain, keywords in _DOMAIN_RULES:
        if any(_matches_keyword(value, keyword) for keyword in keywords):
            return domain
    return "engenharia"


def _matches_keyword(value: str, keyword: str) -> bool:
    if " " in keyword:
        return keyword in value
    return re.search(r"(?<!\w){0}(?!\w)".format(re.escape(keyword)), value) is not None


def specialist_for(domain: str) -> str:
    try:
        return {
            "rh": "hr_policy",
            "juridico": "legal_compliance",
            "api_spec": "repository_api",
            "engenharia": "engineering_operations",
            "web": "web_research",
        }[domain]
    except KeyError as exc:
        raise ValueError("Unsupported knowledge domain") from exc


def validate_requested_domain(domain: Optional[str]) -> Optional[str]:
    if domain is None:
        return None
    normalized = str(domain).strip().lower()
    if normalized not in SUPPORTED_DOMAINS:
        raise ValueError("Unsupported knowledge domain")
    return normalized
