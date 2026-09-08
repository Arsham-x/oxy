<div align="center">

```
  ██████╗ ██╗  ██╗██╗   ██╗   ✦ O X Y  A G E N T ✦
 ██╔═══██╗╚██╗██╔╝╚██╗ ██╔╝   Autonomous AI Coding Assistant
 ██║   ██║ ╚███╔╝  ╚████╔╝    Production-Grade · Zero-Bloat Engine
 ██║   ██║ ██╔██╗   ╚██╔╝     OpenAI Compatible · Multi-Provider
 ╚██████╔╝██╔╝ ██╗   ██║      
  ╚═════╝ ╚═╝  ╚═╝   ╚═╝      v1.0.0 · MIT Licensed
```

### The Autonomous CLI Coding Agent Engineered for Engineers.

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-3776AB?style=flat-square&logo=python&logoColor=white)](https://python.org)
[![License: MIT](https://img.shields.io/badge/license-MIT-00ff88?style=flat-square)](LICENSE)
[![Architecture: Zero-Bloat](https://img.shields.io/badge/architecture-zero--bloat-cyan?style=flat-square)](docs/ARCHITECTURE.md)
[![Tests: 10/10 Passing](https://img.shields.io/badge/tests-10%2F10%20passing-brightgreen?style=flat-square)](tests/test_e2e_suite.py)
[![Security: Hardline Floor](https://img.shields.io/badge/security-hardline%20floor-yellow?style=flat-square)](docs/SECURITY.md)

*“Never write complex, bloated code when a simpler, robust architecture achieves the exact same result.”*

[Quickstart](#quickstart-in-30-seconds) • [Architecture](docs/ARCHITECTURE.md) • [Security Model](docs/SECURITY.md) • [Skills System](docs/SKILLS.md) • [CLI Manual](docs/CLI_REFERENCE.md)

</div>

---

## Why OXY?

Contemporary AI coding agents suffer from two extremes: **fragile terminal abstractions** that duplicate menus on every keypress, or **spaghetti codebases spanning hundreds of files** that lock you into proprietary vendor endpoints.

**OXY** is engineered from first principles as an elite, single-threaded master loop:
- **Zero Screen Duplication**: In-place ANSI delta-rewriting replaces fragile asynchronous rendering loops.
- **Native Unicode Ligatures**: Preserves raw Unicode codepoints for hardware font shapers (HarfBuzz/Qt), guaranteeing cursive Persian and multilingual typography without disconnected letters.
- **Durability by Design**: A persist-before-execute JSONL transaction ledger commits model actions to disk before tool execution begins.
- **High-Performance Parallelism**: A segmented execution planner batches read-only operations across worker threads while enforcing strict sequential isolation on filesystem mutations.
- **Non-Bypassable Hardline Security**: Catastrophic commands (`rm -rf /`, `mkfs`, raw device writes, credential dumping) are categorically blocked at the engine level—no flag can ever bypass host protection.

---

## Architectural Comparison

| Dimension | OXY | Claude Code | Hermes Agent | OpenCode | Aider |
| :--- | :---: | :---: | :---: | :---: | :---: |
| **Provider Freedom** | **Any OpenAI-compatible** (DeepSeek, Groq, Ollama, OpenRouter) | Anthropic only | Multi-provider | Multi-provider | Multi-provider |
| **Terminal UX** | **Flicker-Free In-Place ANSI** | In-place Ink/Node | Rich Live (Flicker prone) | Textual / TUI | Standard Prompt |
| **Multilingual Typography** | **Native HarfBuzz Cursive** | Basic Latin | Broken RTL glyphs | Terminal default | Terminal default |
| **Tool Execution** | **Segmented Parallel Planner** | Sequential | Sequential | Concurrent | Sequential |
| **Transaction Durability** | **Persist-Before-Execute Ledger** | Session JSONL | SQLite / State JSON | In-Memory | Git commits only |
| **Host Security Floor** | **Non-Bypassable Hardline Floor** | Permission prompt | Permission prompt | Sandbox / Prompts | Git checkout prompt |
| **Codebase Footprint** | **Clean Modular Python (~3k LOC)** | Node.js binary | 700+ sprawling files | Go / Node | Python |
| **Prefix-Cache Preservation**| **Byte-Frozen System Prompt** | Yes (Anthropic) | Partial | No | Partial |

---

## Quickstart in 30 Seconds

### 1. Installation

```bash
git clone https://github.com/Arsham-x/oxy.git
cd oxy
pip install -e .
```

### 2. Interactive Cockpit Onboarding

Launch the 6-step keyboard-driven setup wizard:

```bash
python3 oxy.py --setup
```

The wizard auto-detects environment keys, configures provider endpoints, lets you select themes with arrow keys, and formats an instant summary card.

### 3. Launch OXY

```bash
# Interactive Coding REPL
python3 oxy.py

# Headless Pipeline Execution (for CI/CD or scripts)
python3 oxy.py -p "Inspect git diff and write unit tests for modified functions"

# Resume previous session
python3 oxy.py --resume
```

---

## The Wonder Tunnel: Interactive Terminal Cockpit

```
  ? [Step 2/6] AI Provider (↑/↓ navigate, Enter confirm)
  ❯ DeepSeek               DeepSeek V3 & R1 high-speed reasoning (Best value)
    OpenAI                 Official OpenAI API (GPT-4o, o3-mini, o1)
    Groq                   Ultra-fast LPU inference (~300+ tokens/sec)
    OpenRouter             Unified router for Claude, GPT, DeepSeek, Mistral
    Local (Ollama)         On-device private inference (localhost:11434)
    Local (LM Studio)      Local GUI model server (localhost:1234)
  ↳ ↑/↓ navigate · Enter select · 1-9 direct jump
```

- **In-Place Redraw**: Cursor positions move up precisely $N$ lines, rewriting only modified lines.
- **Three Aesthetic Themes**:
  - `Cyber`: Electric cyan borders, neon badges, matrix aesthetics.
  - `Aurora`: Northern lights palette, emerald & purple gradient highlights.
  - `Minimal`: Clean, distraction-free monochrome for high-density terminal setups.

---

## Deep-Dive Architectural Highlights

```
                          ┌───────────────────────────┐
                          │   LLM Generates Turn      │
                          └─────────────┬─────────────┘
                                        │
                                        ▼
                          ┌───────────────────────────┐
                          │ PERSIST-BEFORE-EXECUTE:   │
                          │ Flush Assistant Turn +    │
                          │ Tool Calls to Disk (fsync)│
                          └─────────────┬─────────────┘
                                        │
                                        ▼
                          ┌───────────────────────────┐
                          │ Segmented Parallel Planner│
                          └───────┬───────────┬───────┘
                                  │           │
             ┌────────────────────┘           └────────────────────┐
             ▼                                                     ▼
┌──────────────────────────┐                             ┌───────────────────┐
│ Concurrent Read Phase    │                             │ Mutation Barrier  │
│ [read_file, file_search] │                             │ [write, edit, cmd]│
│ ──► ThreadPoolExecutor   │                             │ ──► Security Gate │
└────────────┬─────────────┘                             └─────────┬─────────┘
             │                                                     │
             └──────────────────────┬──────────────────────────────┘
                                    ▼
                          ┌───────────────────────────┐
                          │ Commit Results to Ledger  │
                          │ Replay to LLM for Next Turn│
                          └───────────────────────────┘
```

### 1. Persist-Before-Execute Transaction Ledger
Model tool calls are written to `.oxy/sessions/<session_id>.jsonl` using `os.fsync()` **before** tools run. If power drops, a process hangs, or `Ctrl+C` is triggered mid-execution, your conversation and action history remain completely intact. Resume instantly with `oxy --resume`.

### 2. Segmented Parallel Execution Planner
Consecutive read operations run concurrently across worker threads, dropping symbol and file-search times by up to **80%**. Any file modification (`write_file`, `edit_file`) or shell command acts as an isolated sequential barrier, eliminating race conditions.

### 3. Non-Bypassable Hardline Security Floor
The host security engine intercepts actions before execution:
- Unconditionally blocks destructive commands (`rm -rf /`, `mkfs`, raw device writes, fork bombs, power halts).
- Blocks access to credentials (`~/.ssh`, `~/.aws`, `/etc/shadow`).
- Guarantees human confirmation on any attempted edits to agent steering files (`system_prompt.md`, `CLAUDE.md`, `.cursorrules`, `oxy_config.json`, `.env`), neutralizing prompt injection exploits.

### 4. Progressive Disclosure Skills System (AgentSkills Standard)
Procedural knowledge is organized in modular `.oxy/skills/<name>/SKILL.md` directories. Instead of polluting the context window with 10,000 tokens of static rules, OXY exposes a compact ~15-token index in the prompt and loads complete workflows on-demand. Includes multilingual Persian trigger keywords (`بررسی کد`, `تست`, `ساده سازی`).

### 5. KV Prefix-Cache Preservation
By byte-freezing the base system prompt and skill catalog at engine initialization, OXY ensures that providers supporting KV caching (DeepSeek, Anthropic, OpenAI) achieve **90%+ cache hits**, drastically lowering latency and API costs.

---

## Built-in Agent Tools

| Tool | Safety Class | Description |
| :--- | :---: | :--- |
| `read_file` | Read-only | Read file contents with line numbering and range slicing. |
| `write_file` | Mutating | Create new files or overwrite existing files safely. |
| `edit_file` | Mutating | Exact search-and-replace with syntax-highlighted visual diffs. |
| `bash` | Mutating | Run shell commands with configurable timeouts and output truncation. |
| `file_search` | Read-only | Fast glob search skipping dependencies and build directories. |
| `content_search`| Read-only | Grep text/regex search across project workspace. |
| `git_status` | Read-only | Inspect active branch, staged files, and modified working tree. |
| `save_memory` | Mutating | Store user preferences and persistent project guidelines. |
| `recall_memory` | Read-only | Query persistent long-term knowledge base. |
| `load_skill` | Read-only | Dynamically load specialized procedural instructions. |

---

## Interactive Slash Commands

| Command | Action |
| :--- | :--- |
| `/help` | Display interactive command reference. |
| `/tools` | List registered tools and security permission status. |
| `/skills [name]` | View installed skills catalog or inspect specific workflows. |
| `/sessions` | List saved session ledgers, turn counts, and modification dates. |
| `/resume <id>` | Resume past session directly from disk. |
| `/add <file>` | Pin file into active context window. |
| `/drop <file>` | Unpin file from active context window. |
| `/git` | Show git branch and changed files. |
| `/memory` | Inspect persistent memory entries. |
| `/model [name]` | Switch LLM model identifier on the fly. |
| `/system [edit]` | View, modify, or open system prompt in `$EDITOR`. |
| `/tokens` | Display session token usage statistics. |
| `/theme [name]` | Switch cockpit visual theme. |
| `/quit` | Exit OXY cleanly. |

---

## Verification & Test Suite

OXY includes an automated test suite verifying all 8 architectural subsystems:

```bash
PYTHONPATH=. python3 tests/test_e2e_suite.py
```

```
..................
Ran 10 tests in 0.523s

OK
```

---

## Modular Documentation

- 📐 **[Architecture Deep-Dive](docs/ARCHITECTURE.md)**: System topology, In-Place ANSI engine, HarfBuzz shaping, KV prefix-cache preservation.
- 🛡 **[Security Model](docs/SECURITY.md)**: Hardline floor specifications, regex filters, steering file integrity.
- 🧩 **[Skills & Workflows](docs/SKILLS.md)**: Progressive disclosure protocol, frontmatter schema, writing custom skills.
- 📖 **[CLI Manual & Reference](docs/CLI_REFERENCE.md)**: Complete flags, slash commands, headless scripts, and keybindings.

---

## License

Distributed under the **MIT License**. Engineered with passion by **[Arsham](https://github.com/Arsham-x)**.
