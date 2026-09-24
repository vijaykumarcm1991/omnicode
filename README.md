# ⚡ OmniCode

> **An OpenAI API-Compatible Autonomous AI Coding Agent & CLI Tool**  
> *Engineered with the speed, toolset, and ergonomics of Claude Code, OpenAI Codex, and Antigravity.*

[![Python](https://img.shields.io/badge/Python-3.9%2B-blue.svg)](https://python.org)
[![License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Tests](https://img.shields.io/badge/Tests-19%20Passed-brightgreen.svg)]()

---

## 🌟 Highlights

- 🔌 **Universal OpenAI-API Compatibility**: Seamlessly connects to OpenAI (`gpt-4o`, `o1`, `o3-mini`), OpenRouter (`claude-3.7-sonnet`, `deepseek-r1`), DeepSeek (`deepseek-chat`, `deepseek-reasoner`), Groq, and local LLMs (Ollama, LM Studio, vLLM).
- 💾 **Endpoint & Credential Persistence**: Save custom endpoints and secret keys once with `--save`, named profiles (`omnicode profile`), or the interactive `omnicode setup` wizard.
- 🎛️ **Custom & Self-Hosted Models**: Full support for any custom model checkpoint, fine-tuned weights, internal corporate servers, or self-hosted engines via standard OpenAI endpoints.
- 🔍 **Live `/v1/models` Auto-Discovery**: Automatically query and discover all models available on your server in real time with interactive tables and `<Tab>` autocompletion.
- 🧠 **Autonomous Multi-Turn Agent Loop**: Powered by a robust ReAct execution engine with real-time streaming, chain-of-thought (`<think>` / reasoning) visualization, and automatic loop detection.
- 🛠️ **Built-in Toolset**:
  - **File Operations**: `view_file` (with line slices & pagination), `write_file`, `edit_file` (targeted replacement with fuzzy match), `apply_patch` (unified diffs), `list_dir`, `file_search`, `grep_search` (regex).
  - **Terminal Commands**: `run_command` (cross-platform bash/PowerShell with streaming stdout/stderr, timeouts, exit codes).
  - **Git Integration**: `git_status`, `git_diff`, `git_commit`, `git_log`.
  - **Web Intelligence**: `fetch_web_page` (HTML to clean Markdown), `web_search` (DuckDuckGo integration).
  - **Interactivity & Memory**: `ask_user` (clarifying questions), `manage_todo` (task checklist), `project_memory` (persistent notes).
  - **Extensibility**: MCP (Model Context Protocol) client for stdio tool servers.
- 🛡️ **Granular Permission Modes**:
  - `auto-read` (default): Auto-approves safe read tools, prompts for file edits and shell commands.
  - `ask`: Explicit confirmation for every tool action.
  - `yolo` (`-y` / `--yes`): Auto-approves all actions for headless scripting.
- 🔄 **Context Budgeting & Auto-Compaction**: Automatic conversation summarization and token tracking to prevent exceeding LLM context windows.
- 💻 **Rich Terminal REPL**: Fast prompt-toolkit interface with `@file` path auto-completions, slash commands (`/help`, `/models`, `/save`, `/compact`, `/cost`, `/diff`, `/model`, etc.), and live syntax highlighting.

---

## 🚀 Installation

```bash
# Clone the repository
git clone https://github.com/vijaykumarcm1991/omnicode.git
cd omnicode

# Install in editable mode
pip install -e .
```

---

## 💾 Saving & Configuring Endpoints (Never Re-type Flags!)

OmniCode provides four flexible ways to save endpoint URLs, API keys, and models so you only have to configure them once:

### Method 1: Use `--save` Flag on Launch (Instant)
Just append `--save` (or `-s`) to your command. OmniCode will run your session and simultaneously persist the settings globally:

```bash
omnicode -b "https://ai.internal.corp/v1" -k "secret-token" -m "internal-coder-70b" --save
```
> Next time, simply type `omnicode` and it will automatically use `https://ai.internal.corp/v1` with your token and model!

*Tip:* Use `--save-project` to save endpoint settings inside `.omnicode/config.json` for a specific repository only.

---

### Method 2: Interactive Setup Wizard (`omnicode setup` / `omnicode login`)
Run the interactive setup wizard to configure endpoints with automated connectivity testing and model selection:

```bash
omnicode setup
```
1. Prompts for your Base URL.
2. Prompts for your API Key.
3. Automatically connects to `/v1/models` to discover all available models.
4. Lets you select your default model from a menu.
5. Saves everything to `~/.omnicode/config.json`.

---

### Method 3: Named Profiles (`omnicode profile`)
Easily switch between multiple work, home, and cloud endpoints:

```bash
# Save a corporate endpoint profile
omnicode profile save work -b "https://ai.internal.corp/v1" -k "secret-token" -m "internal-coder-70b"

# Save a local Ollama profile
omnicode profile save local -b "http://localhost:11434/v1" -m "qwen2.5-coder:32b"

# List all saved profiles
omnicode profile list

# Switch default active profile
omnicode profile use work

# Or launch with a specific profile on demand
omnicode -P local
```

---

### Method 4: Save from Inside REPL (`/save`)
If you change your model, provider, or endpoint during an active chat session, simply type `/save` in the REPL:

```text
omnicode[gpt-4o] ❯ /save
✓ Current configuration saved to global config (~/.omnicode/config.json).
```

---

## ⚙️ Configuration & Providers

### 1. Provider Presets

| Provider | Preset Name | Default Model | Example Model |
| :--- | :--- | :--- | :--- |
| **OpenAI** | `openai` | `gpt-4o` | `o3-mini`, `o1`, `gpt-4.5-preview` |
| **OpenRouter** | `openrouter` | `anthropic/claude-3.7-sonnet` | `deepseek/deepseek-r1`, `openai/gpt-4o` |
| **DeepSeek** | `deepseek` | `deepseek-chat` | `deepseek-reasoner` |
| **Groq** | `groq` | `llama-3.3-70b-versatile` | `deepseek-r1-distill-llama-70b` |
| **Ollama (Local)** | `ollama` | `qwen2.5-coder:latest` | `deepseek-r1:latest`, `llama3.1` |
| **LM Studio (Local)** | `lmstudio` | `local-model` | Any loaded GGUF model |
| **vLLM (Local)** | `vllm` | `default` | Any hosted model |

---

## 🔍 Live Dynamic Model Discovery (`/v1/models`)

OmniCode can automatically query the `GET /v1/models` endpoint of whatever server you connect to.

### Terminal Discovery:
```bash
# Discover models from current active endpoint
omnicode models --fetch

# Query a specific remote or local server
omnicode models --fetch --base-url "http://localhost:11434/v1"
omnicode models --fetch --base-url "https://openrouter.ai/api/v1" --api-key "sk-or-..."
```

### In-REPL Discovery:
- Type `/models` in the chat shell to discover and list all available models.
- Type `/model <Tab>` to autoselect any model discovered from the endpoint.

---

## 📖 Usage Guide

### 1. Interactive REPL Mode

Launch the interactive coding assistant:

```bash
omnicode
```

Or target a specific provider or profile:

```bash
omnicode --profile work
omnicode --provider openrouter --model anthropic/claude-3.7-sonnet
omnicode --provider deepseek --model deepseek-reasoner
```

### 2. Single-Prompt / Scripting Mode

```bash
# Fix a bug or refactor code
omnicode "Analyze src/auth.py and fix the token expiration bug"

# Auto-approve actions (YOLO mode)
omnicode -y "Write unit tests for utils/string_helpers.py and run pytest"

# Pipe error log or diff into OmniCode
cat test_failure.log | omnicode "Explain why this test failed and patch the file"
```

### 3. REPL Slash Commands

Within the interactive REPL, use slash commands for fast actions:

- `/help` — Display help and command table
- `/save [project]` — Save current endpoint and model settings to config
- `/models` — Discover and list all models from `/v1/models`
- `/model [name]` — Switch or view the active LLM model (supports `<Tab>` autocompletion)
- `/provider [name]` — Switch provider preset (`openai`, `openrouter`, `deepseek`, etc.)
- `/mode [ask|auto-read|yolo]` — Change tool permission mode
- `/clear` — Clear terminal and reset conversation context
- `/compact` — Compact conversation history to free context tokens
- `/cost` — View session token consumption and estimated cost
- `/diff` — View git diff for current workspace
- `/status` — View git branch and uncommitted files
- `/commit <message>` — Stage and commit project changes
- `/rules` — Show active `.omnicoderules`
- `/tools` — List all registered tools
- `/exit` or `/quit` — Exit the REPL

---

## 📁 Custom Rules (`.omnicoderules`)

Initialize custom project conventions using:

```bash
omnicode init
```

This creates `.omnicoderules` in your project root. OmniCode automatically injects these rules into its system prompt on every turn.

---

## 🧪 Testing

Run the test suite with `pytest`:

```bash
pytest -v
```

---

## 📄 License

MIT License. Crafted for high-performance AI-assisted software engineering.
