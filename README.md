<div align="center">

```
  ██████╗   ██╗   ██╗ ██╗   ██╗
 ██╔═══██╗  ╚██╗ ██╔╝ ╚██╗ ██╔╝
 ██║   ██║   ╚████╔╝   ╚████╔╝
 ██║   ██║    ╚██╔╝     ╚██╔╝
 ██║   ██║     ██║       ██║
 ╚██████╔╝     ██║       ██║
  ╚═════╝      ╚═╝       ╚═╝
                    A G E N T  v1.0.0
```

### Autonomous CLI Coding Agent. Any Provider. Zero Bloat.

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-3776AB?style=flat-square&logo=python&logoColor=white)](https://python.org)
[![License: MIT](https://img.shields.io/badge/license-MIT-00ff88?style=flat-square)](LICENSE)
[![Tests: 32/32](https://img.shields.io/badge/tests-32%2F32-brightgreen?style=flat-square)](tests/test_e2e_suite.py)
[![Security: Hardline Floor](https://img.shields.io/badge/security-hardline%20floor-yellow?style=flat-square)](docs/SECURITY.md)

*"Never write complex, bloated code when a simpler, robust architecture achieves the exact same result."*

[Quickstart](#quickstart) · [Architecture](docs/ARCHITECTURE.md) · [Security](docs/SECURITY.md) · [Skills](docs/SKILLS.md) · [CLI Reference](docs/CLI_REFERENCE.md)

</div>

---

## Why OXY?

Most AI coding agents either lock you into a single vendor or ship as sprawling codebases that are impossible to understand or extend.

OXY is different:
- **Any provider** — DeepSeek, OpenAI, Groq, OpenRouter, Together AI, Ollama, LM Studio. One config, any endpoint.
- **Zero screen duplication** — In-place ANSI rewriting. No flickering, no ghost frames.
- **Crash-proof sessions** — Persist-before-execute ledger writes to disk before every tool runs. Resume anytime with `--resume`.
- **Parallel reads, sequential writes** — Read-only tools run concurrently. Mutations go through strict barriers.
- **Hardline security** — `rm -rf /`, fork bombs, credential dumps are blocked at engine level. No flag bypasses it.
- **Clean codebase** — ~5k LOC of modular Python. Readable, hackable, no spaghetti.

---

## Quickstart

```bash
git clone https://github.com/Arsham-x/oxy.git
cd oxy
pip install -e .
```

### Setup wizard (6 steps, keyboard-driven)

```bash
python3 oxy.py --setup
```

Arrow keys navigate, Enter confirms. Auto-detects environment keys, configures providers, selects themes.

### Launch

```bash
# Interactive REPL
python3 oxy.py

# Headless (CI/CD, scripts)
python3 oxy.py -p "Review git diff and write tests for modified functions"

# Resume last session
python3 oxy.py --resume
```

---

## Terminal Interface

OXY's interface is inspired by production-grade terminal agents like Grok Build — clean, responsive, no visual clutter.

### Status Line

A live status bar at the bottom shows session state at a glance:

```
 deepseek-chat  │  5 turns  │  1,234 tok  │  2:15  │  ask  │  3 files  │  /help
```

Model name, turn count, token usage, elapsed time, permission mode, active files — all updating in real time.

### Thinking Display

When using reasoning models (DeepSeek R1, OpenAI o1/o3), thinking blocks render with elapsed time:

```
  ◆ Thought for 3.8s (2,450 chars)
  ┌
  │ The user wants to refactor the auth module...
  │ I should first read the current implementation...
  └
```

### Tool Execution

Tools display clean status badges with timing:

```
  ● read_file  path='src/auth.py'
  ✔ read_file · read 142 lines  85ms

  ● edit_file  path='src/auth.py'
  ✔ edit_file · 1 replaced  12ms
```

Parallel read operations show a ⚡ indicator:

```
  ● ⚡ read_file  path='models.py'
  ● ⚡ file_search  pattern='*.test.py'
  ✔ read_file · read 89 lines  42ms
  ✔ file_search · 7 files found  42ms
```

### Turn Metadata

Each response includes timing:

```
  [turn: 2.5s]
  1,204 + 856 = 2,060  ·  session: 12,340
```

### Three Themes

| Theme | Style |
| :--- | :--- |
| `cyber` | Electric cyan, neon green, matrix aesthetic |
| `aurora` | Northern lights — violet and emerald gradients |
| `minimal` | Clean monochrome for focused work |

Switch anytime with `/theme cyber` or pass `--theme aurora` at launch.

---

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    Terminal Cockpit (ui.py)                  │
│     In-Place ANSI · Native Unicode · Arrow-Key Selection    │
└───────────────────────────┬─────────────────────────────────┘
                            │
┌───────────────────────────▼─────────────────────────────────┐
│                   REPL Loop (app.py)                         │
│       Prompt Toolkit · History · Tab Completion · Commands   │
└───────────────────────────┬─────────────────────────────────┘
                            │
┌───────────────────────────▼─────────────────────────────────┐
│               Agentic Engine (engine.py)                     │
│                                                              │
│  ┌─────────────────────────────────────────────────────────┐│
│  │ KV Prefix-Frozen System Prompt                          ││
│  │ (byte-frozen; rebuilt on /system /add /drop /memory)   ││
│  └────────────────────────┬────────────────────────────────┘│
│                           ▼                                  │
│  ┌─────────────────────────────────────────────────────────┐│
│  │ OpenAI-Compatible Client                                ││
│  │ (exponential backoff + round-robin key rotation)        ││
│  └────────────────────────┬────────────────────────────────┘│
│                           ▼                                  │
│  ┌─────────────────────────────────────────────────────────┐│
│  │ Persist-Before-Execute Ledger                           ││
│  │ (.oxy/sessions/<id>.jsonl → fsync before execution)     ││
│  └────────────────────────┬────────────────────────────────┘│
│                           ▼                                  │
│  ┌─────────────────────────────────────────────────────────┐│
│  │ Segmented Parallel Planner                              ││
│  │ reads → concurrent  │  writes → sequential barrier      ││
│  └────────────────────────┬────────────────────────────────┘│
│                           ▼                                  │
│  ┌─────────────────────────────────────────────────────────┐│
│  │ Hardline Security Floor                                 ││
│  │ (catastrophic block + steering file protection)         ││
│  └────────────────────────┬────────────────────────────────┘│
│                           ▼                                  │
│  ┌─────────────────────────────────────────────────────────┐│
│  │ Tool Registry (14 tools + dynamic MCP client)           ││
│  └─────────────────────────────────────────────────────────┘│
└─────────────────────────────────────────────────────────────┘
```

See [Architecture Deep-Dive](docs/ARCHITECTURE.md) for full subsystem documentation.

---

## Built-in Tools

| Tool | Safety | What it does |
| :--- | :---: | :--- |
| `read_file` | read-only | Read file contents with line numbers and range slicing |
| `write_file` | mutating | Create or overwrite files |
| `edit_file` | mutating | Exact search-and-replace with visual diffs |
| `bash` | mutating | Run shell commands with timeout and output truncation |
| `bash_background` | mutating | Submit non-blocking background jobs with dedicated output pipes |
| `job_status` | read-only | Poll background job status and inspect output tails |
| `job_cancel` | mutating | Terminate active background jobs safely |
| `file_search` | read-only | Glob search, skips `node_modules` / `.git` / build dirs |
| `content_search` | read-only | Grep text/regex across the workspace |
| `list_dir` | read-only | List directory contents with dirs-first sorting and size badges |
| `git_status` | read-only | Branch, staged files, working tree changes |
| `save_memory` | mutating | Store persistent user preferences and project rules |
| `recall_memory` | read-only | Query long-term knowledge base (global + workspace overlay) |
| `load_skill` | read-only | Load procedural instructions on demand |

---

## Slash Commands

| Command | Description |
| :--- | :--- |
| `/help` (`/h`, `/?`) | Command reference |
| `/clear` | Clear conversation history from working memory |
| `/compact` | Consolidate older turns into a summary to free context |
| `/quit` (`/exit`, `/q`) | Exit |
| `/tools` | List tools and safety status |
| `/permissions [ask\|auto]` (`/permission`) | View or toggle permission mode |
| `/jobs [job_id]` | List or inspect asynchronous background jobs |
| `/mcp` | List connected MCP servers and discovered tools |
| `/skills [name]` (`/skill`) | List or inspect skills |
| `/add <file>` | Pin file into context (rebuilds frozen prompt) |
| `/drop <file>` | Remove file from context (rebuilds frozen prompt) |
| `/files` | List active files and project tree |
| `/git` | Git branch and status |
| `/memory [view <slug>\|clear]` | List, view, or clear persistent memories |
| `/agent [role] <task>` | Run tool-using sub-agent (`architect`/`debugger`/`reviewer`/`general`) |
| `/agent on\|off\|model\|iterations` | Toggle sub-agent, set model, or set iteration budget |
| `/model [name]` | View or switch model |
| `/system [text\|edit\|reload]` | View, set, edit, or reload system prompt |
| `/keys` | Manage round-robin API keys and cooldown strategies |
| `/sessions` | List saved sessions |
| `/resume <id>` | Resume past session |
| `/rewind <n>` | Rewind conversation to first `n` messages (append-only ledger) |
| `/undo` | Undo last turn and all generated responses/tools |
| `/history` | Show conversation turns |
| `/save [file]` | Export to markdown |
| `/copy` | Copy last response to clipboard |
| `/tokens` | Token usage stats |
| `/theme [name]` | Switch theme |
| `/config` | View config |

Keyboard: `Enter` send · `Alt+Enter` newline · `Ctrl+C` cancel · `Tab` autocomplete · `↑↓` history

---

## Tests

```bash
python3 -m pytest tests/test_e2e_suite.py -v
```

```
32 passed in ~4s
```

Covers: Persian typography, security floor + default-deny, schema coercion, transaction ledger (durability + orphan recovery), parallel planner, skills system, KV cache + prompt refresh seam, command registry (dispatch + aliases), raw key parser, cockpit header, status line, thinking blocks, turn metadata, permission modes, atomic config, `list_dir`, token-budgeted compaction, sub-agent scoping, streaming assembly, KeyManager cooldown & thread lock, append-only rewind & undo, project memory overlay, background jobs engine, deterministic lifecycle hooks, and structured observability with secret redaction.

---

## Documentation

- **[Architecture](docs/ARCHITECTURE.md)** — System topology, streaming, compaction budgets, command registry, sub-agents, MCP, hooks, background jobs, all 19 subsystems
- **[Security](docs/SECURITY.md)** — Hardline floor spec, deny-by-default, steering file protection, MCP sandboxing, telemetry redaction
- **[Skills](docs/SKILLS.md)** — Progressive disclosure protocol, writing custom skills
- **[CLI Reference](docs/CLI_REFERENCE.md)** — Flags, slash commands (incl. `/compact`, `/agent` controls), keyboard bindings
- **[Reconnaissance](docs/PHASE0_RECONNAISSANCE.md)** — Phase 0 audit: strengths, weaknesses, gaps, risks, P0–P3 roadmap

---

## License

MIT · Built by **[Arsham](https://github.com/Arsham-x)**
