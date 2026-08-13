from __future__ import annotations

from dataclasses import replace

import pytest

from app.config import ConfigurationError, Settings
from app.llm_client import NvidiaGateway


def test_nvidia_model_and_legacy_deepseek_key_remain_supported(axiom_settings) -> None:
    legacy = replace(
        axiom_settings,
        nvidia_enabled=True,
        nvidia_api_key="",
        deepseek_api_key="legacy-deepseek-key",
        nvidia_model="meta/llama-3.1-70b-instruct",
    )
    gateway = NvidiaGateway(legacy)

    assert legacy.effective_nvidia_api_key == "legacy-deepseek-key"
    assert gateway.remote_enabled is True
    assert gateway.status() == {
        "gateway": "nvidia",
        "remote_enabled": True,
        "model": "meta/llama-3.1-70b-instruct",
        "fallback": "deterministic",
        "routes": [
            {
                "name": "nvidia",
                "provider": "nvidia",
                "model": "meta/llama-3.1-70b-instruct",
                "configured": True,
                "circuit_state": "closed",
            },
            {
                "name": "deterministic",
                "provider": "deterministic",
                "model": None,
                "configured": True,
                "circuit_state": "closed",
            },
        ],
    }


def test_insecure_nvidia_endpoint_fails_closed_without_echoing_its_value(monkeypatch) -> None:
    monkeypatch.setenv("AXIOM_NVIDIA_BASE_URL", "http://localhost:9000/v1")

    with pytest.raises(ConfigurationError) as captured:
        Settings.from_env()

    assert "AXIOM_NVIDIA_BASE_URL" in str(captured.value)
    assert "localhost" not in str(captured.value)


def test_langsmith_configuration_is_opt_in_and_does_not_expose_the_key(monkeypatch) -> None:
    monkeypatch.setenv("LANGSMITH_TRACING", "true")
    monkeypatch.setenv("LANGSMITH_API_KEY", "test-langsmith-key")
    monkeypatch.setenv("LANGSMITH_PROJECT", "axiom-test")
    monkeypatch.setenv("LANGSMITH_HIDE_INPUTS", "true")
    monkeypatch.setenv("LANGSMITH_HIDE_OUTPUTS", "true")

    configured = Settings.from_env()

    assert configured.langsmith_configured is True
    assert configured.langsmith_enabled is True
    assert configured.langsmith_project == "axiom-test"
    assert configured.langsmith_hide_inputs is True
    assert configured.langsmith_hide_outputs is True
    assert "test-langsmith-key" not in repr(configured)


def test_explicit_openai_route_requires_a_complete_configuration(monkeypatch) -> None:
    monkeypatch.setenv("AXIOM_LLM_PROVIDER", "openai")
    monkeypatch.setenv("AXIOM_LLM_FALLBACK", "none")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_MODEL", raising=False)

    with pytest.raises(ConfigurationError) as captured:
        Settings.from_env()

    assert str(captured.value) == "Model route openai is missing its key, model, or endpoint"


def test_explicit_route_order_uses_each_legacy_nvidia_credential(axiom_settings) -> None:
    configured = replace(
        axiom_settings,
        llm_routes=("nvidia-kimi", "nvidia-minimax", "nvidia-deepseek", "deterministic"),
        kimi_api_key="kimi-secret",
        minimax_api_key="minimax-secret",
        deepseek_api_key="deepseek-secret",
    )

    assert [route.name for route in configured.model_routes] == [
        "nvidia-kimi",
        "nvidia-minimax",
        "nvidia-deepseek",
        "deterministic",
    ]
    assert all(route.configured for route in configured.model_routes)
    serialized = repr(configured) + repr(configured.model_routes)
    assert "kimi-secret" not in serialized
    assert "minimax-secret" not in serialized
    assert "deepseek-secret" not in serialized


def test_custom_openai_endpoint_requires_separate_opt_in(monkeypatch) -> None:
    monkeypatch.setenv("AXIOM_OPENAI_BASE_URL", "https://models.example.test/v1")
    monkeypatch.setenv("AXIOM_OPENAI_ALLOW_CUSTOM_BASE_URL", "false")

    with pytest.raises(ConfigurationError) as captured:
        Settings.from_env()

    assert "AXIOM_OPENAI_ALLOW_CUSTOM_BASE_URL" in str(captured.value)
    assert "models.example.test" not in str(captured.value)


def test_invalid_boolean_is_rejected_instead_of_silently_disabling_a_provider(monkeypatch) -> None:
    monkeypatch.setenv("AXIOM_NVIDIA_ENABLED", "tru")

    with pytest.raises(ConfigurationError, match="AXIOM_NVIDIA_ENABLED"):
        Settings.from_env()
