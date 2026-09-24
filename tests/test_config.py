"""
Unit tests for configuration management, profiles, and persistence in OmniCode.
"""

import pytest
from pathlib import Path
from omnicode.config import (
    OmniConfig,
    load_config,
    save_profile,
    list_profiles,
    set_active_profile,
    save_current_config,
    detect_context_limit,
    KNOWN_PROVIDERS,
)


def test_profile_saving_and_loading(tmp_path, monkeypatch):
    # Mock home directory to tmp_path
    monkeypatch.setattr(Path, "home", lambda: tmp_path)

    # Save custom corporate profile
    save_profile(
        "work-corp",
        {
            "base_url": "https://ai.internal.corp/v1",
            "api_key": "secret-token-123",
            "model": "internal-coder-70b",
        },
    )

    profiles = list_profiles()
    assert "work-corp" in profiles
    assert profiles["work-corp"]["base_url"] == "https://ai.internal.corp/v1"
    assert profiles["work-corp"]["model"] == "internal-coder-70b"

    # Test loading with override_profile
    cfg = load_config(workspace_root=tmp_path, override_profile="work-corp")
    assert cfg.base_url == "https://ai.internal.corp/v1"
    assert cfg.model == "internal-coder-70b"
    assert cfg.api_key == "secret-token-123"

    # Test setting as active profile
    assert set_active_profile("work-corp") is True
    cfg_active = load_config(workspace_root=tmp_path)
    assert cfg_active.base_url == "https://ai.internal.corp/v1"
    assert cfg_active.model == "internal-coder-70b"


def test_save_current_config(tmp_path, monkeypatch):
    monkeypatch.setattr(Path, "home", lambda: tmp_path)

    cfg = OmniConfig(
        base_url="http://localhost:11434/v1",
        api_key="ollama-key",
        model="qwen2.5-coder:32b",
    )

    # Save to global
    saved_global = save_current_config(cfg, is_project=False)
    assert saved_global.exists()

    reloaded_cfg = load_config(workspace_root=tmp_path)
    assert reloaded_cfg.base_url == "http://localhost:11434/v1"
    assert reloaded_cfg.model == "qwen2.5-coder:32b"


def test_known_providers_have_no_hardcoded_models():
    """Verify that known providers do not hardcode model lists, only base URLs."""
    for key, provider in KNOWN_PROVIDERS.items():
        assert "base_url" in provider
        assert provider["base_url"].startswith("http")
        assert "name" in provider
        # Models must not be hardcoded in provider config
        assert "models" not in provider
        assert "default_model" not in provider


def test_detect_context_limit():
    """Test automatic detection of context limits from metadata and model names."""
    # From raw metadata
    assert detect_context_limit("custom-model", {"context_length": 65536}) == 65536
    assert detect_context_limit("custom-model", {"max_model_len": 32768}) == 32768

    # From model name patterns
    assert detect_context_limit("custom-coder-32k") == 32768
    assert detect_context_limit("meta-llama-128k") == 128000
    assert detect_context_limit("my-llm-1m") == 1000000

    # From well-known model families
    assert detect_context_limit("gemini-1.5-pro") == 1000000
    assert detect_context_limit("claude-3-7-sonnet") == 200000
    assert detect_context_limit("deepseek-chat") == 128000
    assert detect_context_limit("llama-3.3-70b-instruct") == 128000
    assert detect_context_limit("qwen2.5-coder-32b") == 128000
    assert detect_context_limit("gpt-4o-mini") == 128000

    # Default fallback
    assert detect_context_limit("completely-unknown-model-xyz") == 32768

