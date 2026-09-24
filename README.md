# ⚡ OmniCode

> **An OpenAI API-Compatible Autonomous AI Coding Agent & CLI Tool**  
> *Engineered with the speed, toolset, and ergonomics of Claude Code, OpenAI Codex, and Antigravity.*

[![Python](https://img.shields.io/badge/Python-3.9%2B-blue.svg)](https://python.org)
[![License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Tests](https://img.shields.io/badge/Tests-23%20Passed-brightgreen.svg)]()

---

## 🌟 Highlights

- 🔌 **Universal OpenAI-API Compatibility**: Works with any OpenAI-compatible provider (OpenAI, OpenRouter, DeepSeek, Groq, Ollama, LM Studio, vLLM, or private custom clusters).
- 🔐 **Streamlined `/auth` Setup**: Choose from known providers with preconfigured URLs (only prompts for API key) or custom providers (URL + key), with instant live model discovery.
- 🚫 **Zero Hardcoded Models**: No stale or hardcoded model lists. OmniCode dynamically queries `/v1/models` in real time.
- 📜 **Built-in Model Pagination & Search**: Easily browse and filter through massive model catalogs (e.g. OpenRouter, custom clusters) with pagination (`n`/`p`), search (`s <query>`), and interactive scrolling.
- 📏 **Automatic Context Limit Detection**: Automatically determines and configures the exact context window limit (e.g. 128k, 200k, 1M tokens) from server metadata and model families.
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

### Method 2: Interactive Auth & Setup Wizard (`omnicode auth` or `/auth`)
Run the interactive authentication wizard at any time via the CLI or directly inside the REPL with `/auth`:

```bash
omnicode auth
```
*(Aliases: `omnicode login`, `omnicode setup`, or `/auth` in REPL)*

1. **Provider Selection**: Displays a list of known providers plus an option for custom self-hosted endpoints:
   - For **Known Providers** (OpenAI, OpenRouter, DeepSeek, Groq, Ollama, LM Studio, vLLM), the API URL is **already preconfigured**—you only need to provide your API key (optional for local engines).
   - For **Custom Providers**, you are prompted for both the OpenAI-compatible Base URL and API key.
2. **Live Model Discovery**: OmniCode queries `GET /v1/models` in real time to fetch all available models.
3. **Auto Context Detection**: Calculates and displays the context window limit (e.g. 128k, 200k, 1M) for each model.
4. **Interactive Selection**: Select your desired model and choose whether to save globally, for the local project, or as a named profile.

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
omnicode[custom-coder] ❯ /save
✓ Current configuration saved to global config (~/.omnicode/config.json).
```

---

## ⚙️ Configuration & Providers

OmniCode does not rely on static, outdated model lists. When you select a known provider, only the official API URL is preconfigured:

| Provider | Provider Key | Preconfigured Base URL | Requires Key? |
| :--- | :--- | :--- | :--- |
| **OpenAI** | `openai` | `https://api.openai.com/v1` | Yes |
| **OpenRouter** | `openrouter` | `https://openrouter.ai/api/v1` | Yes |
| **DeepSeek** | `deepseek` | `https://api.deepseek.com` | Yes |
| **Groq** | `groq` | `https://api.groq.com/openai/v1` | Yes |
| **Ollama (Local)** | `ollama` | `http://localhost:11434/v1` | Optional |
| **LM Studio (Local)** | `lmstudio` | `http://localhost:1234/v1` | Optional |
| **vLLM (Local)** | `vllm` | `http://localhost:8000/v1` | Optional |
| **Custom Provider** | `custom` | *User Specified* (e.g. `https://ai.internal.corp/v1`) | User Specified |

All models and their context limits are **dynamically resolved** upon connection!

---

## 🔍 Live Dynamic Model Discovery (`/v1/models`)

OmniCode automatically queries the standard `GET /v1/models` endpoint of your connected provider and provides built-in pagination, search, and context limit detection.

### 1. Terminal Discovery & Pagination:
```bash
# Discover models from current active endpoint with pagination
omnicode models --fetch

# Jump directly to page 2 (15 models per page)
omnicode models --fetch -p 2

# Search/filter models by keyword (e.g. 'claude', 'qwen', 'deepseek', '70b')
omnicode models --fetch -s "claude"

# Launch interactive scrolling & selection browser
omnicode models --fetch -i

# Display all models at once without pagination
omnicode models --fetch --all

# Query a specific remote or local server
omnicode models --fetch --base-url "http://localhost:11434/v1"
omnicode models --fetch --base-url "https://openrouter.ai/api/v1" --api-key "sk-or-..."
```

### 2. Interactive Auth Wizard Pagination:
When running `omnicode auth` (or `/auth` in REPL):
- `n` / `next`: Move to next page
- `p` / `prev`: Move to previous page
- `s <keyword>` / `f <keyword>`: Live filter models
- `c` / `clear`: Clear filter
- `1..N`: Select model by number
- `<name>`: Select or type model ID directly

### 3. In-REPL Discovery:
- `/models` — Discover models and view page 1 with total model count
- `/models <page>` — View specific page (e.g. `/models 2`)
- `/models <search>` — Search models (e.g. `/models deepseek` or `/models coder`)
- `/models -i` — Open interactive model browser
- `/model <name>` — Switch active model (with `<Tab>` autocompletion & automatic context limit detection)

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
- `/auth` — Configure provider, API key, and auto-discover models
- `/save [project]` — Save current endpoint and model settings to config
- `/models [page|query|-i]` — Discover, paginate, and search models from `/v1/models`
- `/model [name]` — Switch or view active model with auto-detected context limit
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

## 🗑️ How to Completely Uninstall OmniCode

If you wish to completely remove OmniCode and all associated data, cache, and configurations from your machine, follow these steps:

### Option A: Automated Clean Up (Recommended)

1. Run the built-in uninstall assistant to purge all configuration files, profiles, and history:
   ```bash
   omnicode uninstall
   ```
2. Remove the Python package executable:
   ```bash
   pip uninstall omnicode -y
   ```

---

### Option B: Manual Uninstallation

#### Step 1: Uninstall the Python Package
```bash
pip uninstall omnicode -y
```
*(If installed with `pipx`, run: `pipx uninstall omnicode`)*

#### Step 2: Remove Global Configurations & Stored Profiles
- **Windows (PowerShell)**:
  ```powershell
  Remove-Item -Recurse -Force "$HOME\.omnicode"
  ```
- **Windows (Command Prompt)**:
  ```cmd
  rmdir /s /q "%USERPROFILE%\.omnicode"
  ```
- **Linux / macOS (Bash / Zsh)**:
  ```bash
  rm -rf ~/.omnicode
  ```

#### Step 3: Remove Project-Level Configs (Optional)
If you initialized OmniCode in specific project folders:
```bash
# Windows (PowerShell)
Remove-Item -Recurse -Force .omnicode, .omnicoderules -ErrorAction SilentlyContinue

# Linux / macOS
rm -rf .omnicode .omnicoderules
```

#### Step 4: Remove Cloned Source Repository (Optional)
If you cloned the source repository:
```bash
# Windows
rmdir /s /q omnicode

# Linux / macOS
rm -rf omnicode
```

---

## 🧪 Testing

Run the test suite with `pytest`:

```bash
pytest -v
```

---

## 📄 License

MIT License. Crafted for high-performance AI-assisted software engineering.

