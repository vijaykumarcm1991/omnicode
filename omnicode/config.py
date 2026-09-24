"""
Configuration management for OmniCode.
Supports OpenAI-compatible providers (OpenAI, OpenRouter, DeepSeek, Groq, Ollama, vLLM, LM Studio).
Loads from environment variables, global config (~/.omnicode/config.json), and project-level config.
"""

import os
import json
from pathlib import Path
from typing import Dict, Any, Optional
from pydantic import BaseModel, Field

# Provider presets
PROVIDER_PRESETS = {
    "openai": {
        "base_url": "https://api.openai.com/v1",
        "default_model": "gpt-4o",
        "env_key": "OPENAI_API_KEY",
        "models": ["gpt-4o", "gpt-4o-mini", "o1", "o3-mini", "gpt-4-turbo"],
        "context_windows": {
            "gpt-4o": 128000,
            "gpt-4o-mini": 128000,
            "o1": 200000,
            "o3-mini": 200000,
        },
    },
    "openrouter": {
        "base_url": "https://openrouter.ai/api/v1",
        "default_model": "anthropic/claude-3.7-sonnet",
        "env_key": "OPENROUTER_API_KEY",
        "models": [
            "anthropic/claude-3.7-sonnet",
            "anthropic/claude-3.5-sonnet",
            "deepseek/deepseek-r1",
            "deepseek/deepseek-chat",
            "openai/gpt-4o",
            "meta-llama/llama-3.3-70b-instruct",
        ],
        "context_windows": {
            "anthropic/claude-3.7-sonnet": 200000,
            "anthropic/claude-3.5-sonnet": 200000,
            "deepseek/deepseek-r1": 128000,
            "deepseek/deepseek-chat": 128000,
            "openai/gpt-4o": 128000,
        },
    },
    "deepseek": {
        "base_url": "https://api.deepseek.com",
        "default_model": "deepseek-chat",
        "env_key": "DEEPSEEK_API_KEY",
        "models": ["deepseek-chat", "deepseek-reasoner"],
        "context_windows": {
            "deepseek-chat": 128000,
            "deepseek-reasoner": 128000,
        },
    },
    "groq": {
        "base_url": "https://api.groq.com/openai/v1",
        "default_model": "llama-3.3-70b-versatile",
        "env_key": "GROQ_API_KEY",
        "models": [
            "llama-3.3-70b-versatile",
            "deepseek-r1-distill-llama-70b",
            "mixtral-8x7b-32768",
        ],
        "context_windows": {
            "llama-3.3-70b-versatile": 128000,
            "deepseek-r1-distill-llama-70b": 128000,
        },
    },
    "ollama": {
        "base_url": "http://localhost:11434/v1",
        "default_model": "qwen2.5-coder:latest",
        "env_key": "OLLAMA_API_KEY",
        "models": ["qwen2.5-coder", "llama3.1", "deepseek-r1", "mistral"],
        "context_windows": {
            "default": 32768,
        },
    },
    "lmstudio": {
        "base_url": "http://localhost:1234/v1",
        "default_model": "local-model",
        "env_key": "LMSTUDIO_API_KEY",
        "models": ["local-model"],
        "context_windows": {
            "default": 32768,
        },
    },
    "vllm": {
        "base_url": "http://localhost:8000/v1",
        "default_model": "default",
        "env_key": "VLLM_API_KEY",
        "models": ["default"],
        "context_windows": {
            "default": 32768,
        },
    },
}


class OmniConfig(BaseModel):
    """Configuration schema for OmniCode CLI."""

    provider: str = Field(default="openai", description="Active provider preset name")
    base_url: str = Field(
        default="https://api.openai.com/v1", description="OpenAI compatible base URL"
    )
    api_key: str = Field(
        default="", description="API key for the OpenAI-compatible service"
    )
    model: str = Field(default="gpt-4o", description="Target model name")
    temperature: float = Field(
        default=0.1, description="Sampling temperature (lower is more deterministic)"
    )
    max_tokens: Optional[int] = Field(
        default=None, description="Max tokens for response completion"
    )
    max_agent_steps: int = Field(
        default=40, description="Max autonomous tool execution iterations per prompt"
    )
    permission_mode: str = Field(
        default="auto-read",
        description="Permission mode: 'ask' (confirm all), 'auto-read' (auto-approve reads, confirm writes/exec), 'yolo' (auto-approve all)",
    )
    context_window: int = Field(
        default=128000, description="Max context window size in tokens"
    )
    auto_compact_threshold: float = Field(
        default=0.80,
        description="Threshold percentage of context window before running auto-compaction",
    )
    system_prompt_extra: str = Field(
        default="", description="Extra project or user instructions"
    )
    custom_headers: Dict[str, str] = Field(
        default_factory=dict, description="Custom HTTP headers to send with requests"
    )
    enable_mcp: bool = Field(
        default=True, description="Enable Model Context Protocol support"
    )
    mcp_servers: Dict[str, Any] = Field(
        default_factory=dict, description="MCP server configurations"
    )
    stream_output: bool = Field(
        default=True, description="Stream assistant responses in real time"
    )
    show_reasoning: bool = Field(
        default=True, description="Display model chain-of-thought/reasoning blocks"
    )


def get_global_config_dir() -> Path:
    """Return ~/.omnicode path and ensure it exists."""
    config_dir = Path.home() / ".omnicode"
    config_dir.mkdir(parents=True, exist_ok=True)
    (config_dir / "sessions").mkdir(exist_ok=True)
    return config_dir


def get_global_config_path() -> Path:
    return get_global_config_dir() / "config.json"


def get_project_config_dir(workspace_root: Optional[Path] = None) -> Path:
    """Return .omnicode directory inside project root."""
    root = workspace_root or Path.cwd()
    pdir = root / ".omnicode"
    return pdir


def load_config(
    workspace_root: Optional[Path] = None,
    override_model: Optional[str] = None,
    override_base_url: Optional[str] = None,
    override_api_key: Optional[str] = None,
    override_provider: Optional[str] = None,
    override_permission_mode: Optional[str] = None,
) -> OmniConfig:
    """Load configuration merging defaults, global file, project file, env vars, and overrides."""
    config_dict: Dict[str, Any] = {}

    # 1. Global config file
    global_path = get_global_config_path()
    if global_path.is_file():
        try:
            with open(global_path, "r", encoding="utf-8") as f:
                config_dict.update(json.load(f))
        except Exception:
            pass

    # 2. Project config file (.omnicode/config.json)
    root = workspace_root or Path.cwd()
    project_conf = root / ".omnicode" / "config.json"
    if project_conf.is_file():
        try:
            with open(project_conf, "r", encoding="utf-8") as f:
                config_dict.update(json.load(f))
        except Exception:
            pass

    # 3. Project rules (.omnicoderules or .clirules or AGENTS.md)
    rules_text = ""
    for rfile in [".omnicoderules", ".clirules", "AGENTS.md", "CLAUDE.md"]:
        rpath = root / rfile
        if rpath.is_file():
            try:
                with open(rpath, "r", encoding="utf-8", errors="ignore") as f:
                    rules_text += f"\n--- Rules from {rfile} ---\n" + f.read() + "\n"
            except Exception:
                pass
    if rules_text:
        existing_extra = config_dict.get("system_prompt_extra", "")
        config_dict["system_prompt_extra"] = (existing_extra + "\n" + rules_text).strip()

    # 4. Environment variables
    env_provider = os.environ.get("OMNICODE_PROVIDER")
    if env_provider:
        config_dict["provider"] = env_provider.lower()

    # Detect provider preset if specified or from environment
    current_provider = override_provider or config_dict.get("provider", "openai")
    preset = PROVIDER_PRESETS.get(current_provider, {})

    # Base URL from env or preset
    env_base_url = (
        os.environ.get("OMNICODE_BASE_URL")
        or os.environ.get("OPENAI_BASE_URL")
        or (preset.get("base_url") if preset else None)
    )
    if env_base_url and "base_url" not in config_dict:
        config_dict["base_url"] = env_base_url

    # API key from env or preset
    env_key_name = preset.get("env_key", "OPENAI_API_KEY") if preset else "OPENAI_API_KEY"
    env_api_key = (
        os.environ.get("OMNICODE_API_KEY")
        or os.environ.get(env_key_name)
        or os.environ.get("OPENAI_API_KEY")
    )
    if env_api_key and not config_dict.get("api_key"):
        config_dict["api_key"] = env_api_key

    # Model from env
    env_model = os.environ.get("OMNICODE_MODEL") or os.environ.get("OPENAI_MODEL")
    if env_model:
        config_dict["model"] = env_model
    elif "model" not in config_dict and preset:
        config_dict["model"] = preset.get("default_model", "gpt-4o")

    # Permission mode from env
    env_perm = os.environ.get("OMNICODE_PERMISSION_MODE")
    if env_perm:
        config_dict["permission_mode"] = env_perm

    # 5. Explicit CLI overrides
    if override_provider:
        config_dict["provider"] = override_provider
        if override_provider in PROVIDER_PRESETS:
            p = PROVIDER_PRESETS[override_provider]
            if not override_base_url and "base_url" not in config_dict:
                config_dict["base_url"] = p["base_url"]
            if not override_model and "model" not in config_dict:
                config_dict["model"] = p["default_model"]

    if override_base_url:
        config_dict["base_url"] = override_base_url
    if override_api_key:
        config_dict["api_key"] = override_api_key
    if override_model:
        config_dict["model"] = override_model
    if override_permission_mode:
        config_dict["permission_mode"] = override_permission_mode

    # Auto-adjust context window if known
    cfg = OmniConfig(**config_dict)
    if current_provider in PROVIDER_PRESETS:
        cw_map = PROVIDER_PRESETS[current_provider].get("context_windows", {})
        if cfg.model in cw_map:
            cfg.context_window = cw_map[cfg.model]
        elif "default" in cw_map:
            cfg.context_window = cw_map["default"]

    return cfg


def save_global_config(config_data: Dict[str, Any]) -> None:
    """Save configuration dictionary to ~/.omnicode/config.json."""
    config_path = get_global_config_path()
    existing: Dict[str, Any] = {}
    if config_path.is_file():
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                existing = json.load(f)
        except Exception:
            pass
    existing.update(config_data)
    with open(config_path, "w", encoding="utf-8") as f:
        json.dump(existing, f, indent=2)


def save_project_config(workspace_root: Path, config_data: Dict[str, Any]) -> None:
    """Save configuration dictionary to .omnicode/config.json in project root."""
    pdir = get_project_config_dir(workspace_root)
    pdir.mkdir(parents=True, exist_ok=True)
    config_path = pdir / "config.json"
    existing: Dict[str, Any] = {}
    if config_path.is_file():
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                existing = json.load(f)
        except Exception:
            pass
    existing.update(config_data)
    with open(config_path, "w", encoding="utf-8") as f:
        json.dump(existing, f, indent=2)
