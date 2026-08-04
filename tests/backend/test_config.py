from __future__ import annotations

from dataclasses import replace

from app.config import Settings
from app.llm_client import NvidiaGateway


def test_nvidia_model_is_configurable_and_legacy_deepseek_key_remains_supported(axiom_settings) -> None:
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
    }


def test_insecure_nvidia_endpoint_falls_back_to_the_hosted_https_endpoint(monkeypatch) -> None:
    monkeypatch.setenv("AXIOM_NVIDIA_BASE_URL", "http://localhost:9000/v1")

    configured = Settings.from_env()

    assert configured.nvidia_base_url == "https://integrate.api.nvidia.com/v1"


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
