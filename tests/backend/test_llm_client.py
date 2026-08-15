from __future__ import annotations

from dataclasses import replace
from types import SimpleNamespace

import pytest

from app.agents.grounding import deduplicate_evidence, grade_evidence
from app.llm_client import ModelGateway, ModelProviderRejected, ModelProviderUnavailable
from app.vectorstore.port import RetrievedChunk


class ProviderStatusError(Exception):
    def __init__(self, status_code: int) -> None:
        super().__init__("provider body must never be logged or returned")
        self.status_code = status_code


class FakeCompletion:
    def __init__(self, outcome) -> None:
        self.outcome = outcome

    def create(self, **kwargs):
        if isinstance(self.outcome, Exception):
            raise self.outcome
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=self.outcome))]
        )


class FakeClient:
    def __init__(self, outcome) -> None:
        self.chat = SimpleNamespace(completions=FakeCompletion(outcome))


@pytest.fixture
def evidence() -> list[RetrievedChunk]:
    return [
        RetrievedChunk(
            id="chunk-1",
            content="The internal recovery objective is four hours.",
            metadata={"source": "runbook.md", "page": 2},
            score=0.9,
        )
    ]


def test_route_priority_timeout_and_retry_are_passed_to_clients(axiom_settings, evidence) -> None:
    configured = replace(
        axiom_settings,
        llm_routes=("nvidia", "openai", "deterministic"),
        nvidia_api_key="nvidia-secret",
        openai_api_key="openai-secret",
        openai_model="gpt-test",
        llm_timeout_seconds=12.5,
        llm_max_retries=2,
    )
    calls = []

    def factory(route, timeout, max_retries):
        calls.append((route.name, timeout, max_retries))
        outcome = ProviderStatusError(503) if route.name == "nvidia" else "Grounded answer"
        return FakeClient(outcome)

    result = ModelGateway(configured, client_factory=factory).synthesize(
        "What is the RTO?", evidence
    )

    assert result.answer == "Grounded answer"
    assert result.mode == "openai"
    assert calls == [("nvidia", 12.5, 2), ("openai", 12.5, 2)]


def test_muse_glimmer_disables_excessive_reasoning_for_grounded_synthesis(
    axiom_settings, evidence
) -> None:
    configured = replace(
        axiom_settings,
        llm_routes=("nvidia", "deterministic"),
        nvidia_api_key="nvidia-secret",
        nvidia_model="meta/muse-glimmer-30b",
    )
    calls = []

    def factory(route, timeout, max_retries):
        class Completion:
            def create(self, **kwargs):
                calls.append(kwargs)
                return SimpleNamespace(
                    choices=[SimpleNamespace(message=SimpleNamespace(content="Grounded answer"))]
                )

        return SimpleNamespace(chat=SimpleNamespace(completions=Completion()))

    result = ModelGateway(configured, client_factory=factory).synthesize(
        "What is the RTO?", evidence
    )

    assert result.mode == "nvidia"
    assert calls[0]["extra_body"] == {
        "chat_template_kwargs": {"reasoning_strength": "low"}
    }


def test_empty_remote_response_uses_grounded_deterministic_fallback(
    axiom_settings, evidence
) -> None:
    configured = replace(
        axiom_settings,
        llm_routes=("nvidia", "deterministic"),
        nvidia_api_key="nvidia-secret",
        nvidia_model="meta/muse-glimmer-30b",
    )
    gateway = ModelGateway(
        configured,
        client_factory=lambda route, timeout, retries: FakeClient(None),
    )

    result = gateway.synthesize("What is the RTO?", evidence)

    assert result.mode == "deterministic"
    assert "runbook.md" in result.answer


def test_non_transient_provider_failure_does_not_fall_back(axiom_settings, evidence) -> None:
    configured = replace(
        axiom_settings,
        llm_routes=("nvidia", "openai", "deterministic"),
        nvidia_api_key="nvidia-secret",
        openai_api_key="openai-secret",
        openai_model="gpt-test",
    )
    calls = []

    def factory(route, timeout, max_retries):
        calls.append(route.name)
        return FakeClient(ProviderStatusError(401))

    with pytest.raises(ModelProviderRejected) as captured:
        ModelGateway(configured, client_factory=factory).synthesize("What is the RTO?", evidence)

    assert calls == ["nvidia"]
    assert "provider body" not in str(captured.value)


def test_transient_failure_uses_explicit_deterministic_fallback(axiom_settings, evidence) -> None:
    configured = replace(
        axiom_settings,
        llm_routes=("nvidia", "deterministic"),
        nvidia_api_key="nvidia-secret",
    )

    gateway = ModelGateway(
        configured,
        client_factory=lambda route, timeout, max_retries: FakeClient(TimeoutError("secret-body")),
    )
    result = gateway.synthesize("What is the RTO?", evidence)

    assert result.mode == "deterministic"
    assert "runbook.md" in result.answer


def test_transient_failure_without_fallback_is_unavailable(axiom_settings, evidence) -> None:
    configured = replace(
        axiom_settings,
        llm_routes=("nvidia",),
        nvidia_api_key="nvidia-secret",
    )
    gateway = ModelGateway(
        configured,
        client_factory=lambda route, timeout, max_retries: FakeClient(ProviderStatusError(429)),
    )

    with pytest.raises(ModelProviderUnavailable):
        gateway.synthesize("What is the RTO?", evidence)


def test_circuit_opens_only_after_transient_failures_and_recovers(axiom_settings, evidence) -> None:
    configured = replace(
        axiom_settings,
        llm_routes=("nvidia", "deterministic"),
        nvidia_api_key="nvidia-secret",
        llm_circuit_failure_threshold=2,
        llm_circuit_recovery_seconds=10,
    )
    now = [100.0]
    calls = []

    def factory(route, timeout, max_retries):
        calls.append(route.name)
        return FakeClient(TimeoutError("not public"))

    gateway = ModelGateway(configured, client_factory=factory, clock=lambda: now[0])
    assert gateway.synthesize("What is the RTO?", evidence).mode == "deterministic"
    assert gateway.synthesize("What is the RTO?", evidence).mode == "deterministic"
    assert gateway.status()["routes"][0]["circuit_state"] == "open"

    assert gateway.synthesize("What is the RTO?", evidence).mode == "deterministic"
    assert calls == ["nvidia", "nvidia"]

    now[0] += 11
    assert gateway.synthesize("What is the RTO?", evidence).mode == "deterministic"
    assert calls == ["nvidia", "nvidia", "nvidia"]


def test_circuit_allows_only_one_half_open_probe(axiom_settings) -> None:
    configured = replace(
        axiom_settings,
        llm_routes=("nvidia", "deterministic"),
        nvidia_api_key="nvidia-secret",
        llm_circuit_failure_threshold=1,
        llm_circuit_recovery_seconds=10,
    )
    now = [100.0]
    gateway = ModelGateway(configured, clock=lambda: now[0])
    gateway._record_transient_failure("nvidia")
    now[0] += 11

    assert gateway._circuit_allows("nvidia") is True
    assert gateway._circuit_allows("nvidia") is False


def test_status_is_sanitized_per_route(axiom_settings) -> None:
    configured = replace(
        axiom_settings,
        llm_routes=("openai", "deterministic"),
        openai_api_key="openai-secret",
        openai_model="gpt-test",
        openai_base_url="https://models.example.test/v1",
        openai_allow_custom_base_url=True,
    )

    status = ModelGateway(configured, client_factory=lambda route, timeout, retries: None).status()
    serialized = repr(status)

    assert status["gateway"] == "openai"
    assert status["fallback"] == "deterministic"
    assert status["routes"][0] == {
        "name": "openai",
        "provider": "openai",
        "model": "gpt-test",
        "configured": True,
        "circuit_state": "closed",
    }
    assert "openai-secret" not in serialized
    assert "models.example.test" not in serialized


def test_compact_evidence_keeps_the_relevant_markdown_section_bounded() -> None:
    content = "\n".join(
        [
            "# Introduction",
            "General material. " * 80,
            "# Recovery objectives",
            "The RTO is four hours.",
            "The RPO is one hour.",
            "# Contacts",
            "Contact the service desk. " * 80,
        ]
    )

    compact = ModelGateway._compact_evidence("What is the RTO?", content)

    assert len(compact) <= 800
    assert "# Recovery objectives" in compact
    assert "The RTO is four hours." in compact
    assert "# Contacts" not in compact


def test_plain_excerpt_discards_unreadable_pdf_replacement_characters() -> None:
    assert ModelGateway._plain_excerpt("\ufffd" * 500, max_chars=300) == ""


def test_grounding_rejects_corrupt_extracted_evidence() -> None:
    corrupt = RetrievedChunk(
        id="broken-pdf",
        content="\ufffd" * 500,
        metadata={"source": "broken.pdf", "domain": "engenharia"},
        score=0.99,
    )

    assert deduplicate_evidence([corrupt], limit=4) == []
    assert grade_evidence("Como agir no incidente?", [corrupt]).passed is False
