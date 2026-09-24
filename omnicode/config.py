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

import re

# Known providers list: tool only preconfigures standard API URL and env_key; no preconfigured models!
KNOWN_PROVIDERS: Dict[str, Dict[str, Any]] = {
    "openai": {
        "name": "OpenAI",
        "base_url": "https://api.openai.com/v1",
        "env_key": "OPENAI_API_KEY",
        "requires_key": True,
    },
    "openrouter": {
        "name": "OpenRouter",
        "base_url": "https://openrouter.ai/api/v1",
        "env_key": "OPENROUTER_API_KEY",
        "requires_key": True,
    },
    "deepseek": {
        "name": "DeepSeek",
        "base_url": "https://api.deepseek.com",
        "env_key": "DEEPSEEK_API_KEY",
        "requires_key": True,
    },
    "groq": {
        "name": "Groq",
        "base_url": "https://api.groq.com/openai/v1",
        "env_key": "GROQ_API_KEY",
        "requires_key": True,
    },
    "ollama": {
        "name": "Ollama (Local)",
        "base_url": "http://localhost:11434/v1",
        "env_key": "OLLAMA_API_KEY",
        "requires_key": False,
    },
    "lmstudio": {
        "name": "LM Studio (Local)",
        "base_url": "http://localhost:1234/v1",
        "env_key": "LMSTUDIO_API_KEY",
        "requires_key": False,
    },
    "vllm": {
        "name": "vLLM (Local)",
        "base_url": "http://localhost:8000/v1",
        "env_key": "VLLM_API_KEY",
        "requires_key": False,
    },
}
PROVIDER_PRESETS = KNOWN_PROVIDERS


def detect_context_limit(model_id: str, raw_metadata: Optional[Dict[str, Any]] = None) -> int:
    """Automatically determine and configure context window limit for a model."""
    if not model_id:
        return 128000

    # 1. Inspect raw metadata from server if available
    if raw_metadata:
        for field in [
            "context_length",
            "max_context_length",
            "context_window",
            "max_model_len",
            "max_position_embeddings",
            "max_tokens",
        ]:
            val = raw_metadata.get(field)
            if isinstance(val, int) and val >= 2048:
                return val

    m_lower = model_id.lower()

    # 2. Match explicit numeric context indicators (e.g. 128k, 64k, 32k, 1m, 200k)
    match = re.search(r"(\d+)(k|m)(?:[_\-\b]|$)", m_lower)
    if match:
        num = int(match.group(1))
        unit = match.group(2)
        if unit == "k":
            return num * 1000 if num >= 100 else num * 1024
        elif unit == "m":
            return num * 1000000

    # 3. Model family heuristics
    if "gemini" in m_lower:
        return 1000000
    if any(k in m_lower for k in ["claude-3-7", "claude-3.7", "claude-3-5", "claude-3.5", "claude-3"]):
        return 200000
    if any(k in m_lower for k in ["o1", "o3-mini", "o3", "o1-mini", "o1-preview"]):
        return 200000
    if any(k in m_lower for k in ["gpt-4o", "gpt-4.5", "gpt-4-turbo"]):
        return 128000
    if "deepseek" in m_lower:
        return 128000
    if any(k in m_lower for k in ["llama-3.3", "llama-3.2", "llama-3.1", "llama3.3", "llama3.2", "llama3.1"]):
        return 128000
    if any(k in m_lower for k in ["qwen2.5", "qwen-2.5", "qwq"]):
        return 128000
    if any(k in m_lower for k in ["mistral-large", "codestral"]):
        return 128000
    if "gpt-3.5-turbo" in m_lower:
        return 16385
    if any(k in m_lower for k in ["llama-3", "llama3"]):
        return 8192

    return 32768  # Sensible default for general models


class OmniConfig(BaseModel):
    """Configuration schema for OmniCode CLI without hardcoded models."""

    provider: str = Field(default="", description="Active provider name")
    base_url: str = Field(default="", description="OpenAI compatible base URL")
    api_key: str = Field(default="", description="API key for the LLM endpoint")
    model: str = Field(default="", description="Target model name")
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
    override_profile: Optional[str] = None,
) -> OmniConfig:
    """Load configuration merging defaults, global file, project file, env vars, profiles, and overrides."""
    config_dict: Dict[str, Any] = {}

    # 1. Global config file
    global_path = get_global_config_path()
    global_data: Dict[str, Any] = {}
    if global_path.is_file():
        try:
            with open(global_path, "r", encoding="utf-8") as f:
                global_data = json.load(f)
                config_dict.update(global_data)
        except Exception:
            pass

    # 2. Named profile if specified
    active_profile_name = override_profile or os.environ.get("OMNICODE_PROFILE") or global_data.get("active_profile")
    if active_profile_name and "profiles" in global_data and active_profile_name in global_data["profiles"]:
        config_dict.update(global_data["profiles"][active_profile_name])

    # 3. Project config file (.omnicode/config.json)
    root = workspace_root or Path.cwd()
    project_conf = root / ".omnicode" / "config.json"
    if project_conf.is_file():
        try:
            with open(project_conf, "r", encoding="utf-8") as f:
                config_dict.update(json.load(f))
        except Exception:
            pass

    # 4. Project rules (.omnicoderules or .clirules or AGENTS.md)
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

    # 5. Environment variables
    env_provider = os.environ.get("OMNICODE_PROVIDER")
    if env_provider:
        config_dict["provider"] = env_provider.lower()

    # Detect provider preset if specified or from environment
    current_provider = override_provider or config_dict.get("provider", "")
    preset = KNOWN_PROVIDERS.get(current_provider, {})

    # Base URL from env or preset
    env_base_url = (
        os.environ.get("OMNICODE_BASE_URL")
        or os.environ.get("OPENAI_BASE_URL")
        or (preset.get("base_url") if preset else None)
    )
    if env_base_url and not config_dict.get("base_url"):
        config_dict["base_url"] = env_base_url

    # API key from env or preset
    env_key_name = preset.get("env_key", "OPENAI_API_KEY") if preset else "OPENAI_API_KEY"
    env_api_key = (
        os.environ.get("OMNICODE_API_KEY")
        or (os.environ.get(env_key_name) if env_key_name else None)
        or os.environ.get("OPENAI_API_KEY")
    )
    if env_api_key and not config_dict.get("api_key"):
        config_dict["api_key"] = env_api_key

    # Model from env
    env_model = os.environ.get("OMNICODE_MODEL") or os.environ.get("OPENAI_MODEL")
    if env_model:
        config_dict["model"] = env_model

    # Permission mode from env
    env_perm = os.environ.get("OMNICODE_PERMISSION_MODE")
    if env_perm:
        config_dict["permission_mode"] = env_perm

    # 6. Explicit CLI overrides
    if override_provider:
        config_dict["provider"] = override_provider
        if override_provider in KNOWN_PROVIDERS:
            p = KNOWN_PROVIDERS[override_provider]
            if not override_base_url and not config_dict.get("base_url"):
                config_dict["base_url"] = p["base_url"]

    if override_base_url:
        config_dict["base_url"] = override_base_url
    if override_api_key:
        config_dict["api_key"] = override_api_key
    if override_model:
        config_dict["model"] = override_model
    if override_permission_mode:
        config_dict["permission_mode"] = override_permission_mode

    cfg = OmniConfig(**config_dict)

    # Automatically configure context window limit for the model
    if cfg.model and ("context_window" not in config_dict or config_dict.get("context_window") == 128000):
        cfg.context_window = detect_context_limit(cfg.model)

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


def save_current_config(config: OmniConfig, is_project: bool = False, workspace_root: Optional[Path] = None) -> Path:
    """Save the active OmniConfig instance to global or project config."""
    save_data = {
        "provider": config.provider,
        "base_url": config.base_url,
        "api_key": config.api_key,
        "model": config.model,
        "permission_mode": config.permission_mode,
        "temperature": config.temperature,
        "context_window": config.context_window,
        "max_agent_steps": config.max_agent_steps,
    }
    if is_project:
        root = workspace_root or Path.cwd()
        save_project_config(root, save_data)
        return root / ".omnicode" / "config.json"
    else:
        save_global_config(save_data)
        return get_global_config_path()


def save_profile(name: str, profile_data: Dict[str, Any]) -> None:
    """Save named profile to ~/.omnicode/config.json under 'profiles'."""
    config_path = get_global_config_path()
    existing: Dict[str, Any] = {}
    if config_path.is_file():
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                existing = json.load(f)
        except Exception:
            pass

    if "profiles" not in existing:
        existing["profiles"] = {}

    existing["profiles"][name] = profile_data
    with open(config_path, "w", encoding="utf-8") as f:
        json.dump(existing, f, indent=2)


def list_profiles() -> Dict[str, Dict[str, Any]]:
    """List all saved profiles in ~/.omnicode/config.json."""
    config_path = get_global_config_path()
    if config_path.is_file():
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                return data.get("profiles", {})
        except Exception:
            pass
    return {}


def set_active_profile(name: str) -> bool:
    """Set the active default profile name in global config."""
    profiles = list_profiles()
    if name not in profiles:
        return False
    save_global_config({"active_profile": name})
    return True
