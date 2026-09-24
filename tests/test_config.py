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
