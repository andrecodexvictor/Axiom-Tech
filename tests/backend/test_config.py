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
