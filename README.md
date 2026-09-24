# ⚡ OmniCode

> **An OpenAI API-Compatible Autonomous AI Coding Agent & CLI Tool**  
> *Engineered with the speed, toolset, and ergonomics of Claude Code, OpenAI Codex, and Antigravity.*

[![Python](https://img.shields.io/badge/Python-3.9%2B-blue.svg)](https://python.org)
[![License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Tests](https://img.shields.io/badge/Tests-17%20Passed-brightgreen.svg)]()

---

## 🌟 Highlights

- 🔌 **Universal OpenAI-API Compatibility**: Seamlessly connects to OpenAI (`gpt-4o`, `o1`, `o3-mini`), OpenRouter (`claude-3.7-sonnet`, `deepseek-r1`), DeepSeek (`deepseek-chat`, `deepseek-reasoner`), Groq, and local LLMs (Ollama, LM Studio, vLLM).
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
- 💻 **Rich Terminal REPL**: Fast prompt-toolkit interface with `@file` path auto-completions, slash commands (`/help`, `/models`, `/compact`, `/cost`, `/diff`, `/model`, etc.), and live syntax highlighting.

---

## 🚀 Installation

```bash
# Clone the repository
git clone https://github.com/your-org/omnicode.git
cd omnicode

# Install in editable mode
pip install -e .
```

---

## ⚙️ Configuration & Providers

OmniCode supports easy provider switching via environment variables, CLI flags, or config files.

### 1. API Keys & Environment Variables

```bash
# OpenAI
export OPENAI_API_KEY="sk-..."

# OpenRouter (Access Claude 3.7 Sonnet, DeepSeek-R1, etc.)
export OPENROUTER_API_KEY="sk-or-..."

# DeepSeek
export DEEPSEEK_API_KEY="sk-..."

# Groq
export GROQ_API_KEY="gsk_..."
```

### 2. Provider Presets

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

## 🎛️ Custom Models & Auto-Discovery

OmniCode works seamlessly with any custom, fine-tuned, or private LLM server and can dynamically discover available models from the `/v1/models` API endpoint.

### 1. Running Custom & Local Models

Point OmniCode to your custom endpoint with `--base-url` (or `-b`) and `--model` (or `-m`):

```bash
# Self-hosted vLLM instance
omnicode --base-url "http://192.168.1.100:8000/v1" --model "my-fine-tuned-qwen-coder-32b"

# Local LM Studio
omnicode --base-url "http://localhost:1234/v1" --model "local-model"

# Private corporate server with API token
omnicode -b "https://ai.internal.corp/v1" -k "secret-token" -m "internal-coder-70b"
```

You can also persist custom endpoints permanently:

```bash
omnicode config set base_url "http://localhost:8000/v1"
omnicode config set model "my-custom-model"
```

### 2. Dynamic Model Discovery (`/v1/models`)

#### A. From the Terminal CLI
Query the remote server's `/v1/models` endpoint directly:

```bash
# Fetch live models from active configured server
omnicode models --fetch

# Discover models from a specific local or remote server
omnicode models --fetch --base-url "http://localhost:11434/v1"
omnicode models --fetch --base-url "https://openrouter.ai/api/v1" --api-key "sk-or-..."
```

**Output:**
```text
               Live Discovered Models (http://localhost:11434/v1/models)
┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━┓
┃ Model ID                           ┃ Owner    ┃
┡━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━┩
│ qwen2.5-coder:32b                  │ ollama   │
│ deepseek-r1:70b                    │ ollama   │
│ llama3.3:70b-instruct-q8_0         │ ollama   │
│ mistral-large:latest               │ ollama   │
└────────────────────────────────────┴──────────┘
Total: 4 models available on endpoint.
```

#### B. Inside the Interactive REPL
- Run `/models` (or `/model` without arguments) in the REPL to discover and display all models from the live endpoint.
- Type `/model <Tab>` to auto-complete and select any model discovered from the server.

```text
omnicode[gpt-4o] ❯ /models
Discovered 4 models from http://localhost:11434/v1/models

omnicode[gpt-4o] ❯ /model qwen2.5-coder:32b
✓ Switched model to: qwen2.5-coder:32b
```

---

## 📖 Usage Guide

### 1. Interactive REPL Mode

Launch the interactive coding assistant in your project directory:

```bash
omnicode
```

Or target a specific provider and model:

```bash
# Run with Claude 3.7 Sonnet via OpenRouter
omnicode --provider openrouter --model anthropic/claude-3.7-sonnet

# Run with DeepSeek-R1 reasoning model
omnicode --provider deepseek --model deepseek-reasoner

# Run with local Ollama
omnicode --provider ollama --model qwen2.5-coder:latest
```

### 2. Single-Prompt / Scripting Mode

Execute a specific task directly without entering the interactive shell:

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

### 4. Referencing Files with `@`

In the interactive REPL, type `@` followed by any filename to automatically autocomplete and embed file contents into your prompt:

```text
omnicode[gpt-4o] ❯ Refactor @src/auth.py to use async/await and add tests to @tests/test_auth.py
```

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
