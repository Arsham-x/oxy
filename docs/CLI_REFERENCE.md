# OXY CLI Reference & Commands Manual

Complete reference for command-line flags, interactive cockpit commands, and keyboard bindings.

---

## 1. Command-Line Arguments (`oxy.py`)

```bash
python3 oxy.py [OPTIONS]
```

| Flag | Argument | Description |
| :--- | :--- | :--- |
| `--setup` | None | Launch the 6-step interactive onboarding wizard with in-place ANSI navigation. |
| `-p`, `--prompt` | `<text>` | **Headless Execution Mode**: Executes a single prompt headlessly and exits (ideal for CI/CD or shell scripts). |
| `--resume` | `[id]` | Resume a past session by ID (or the most recent session if `id` is omitted). |
| `--yolo` | None | Auto-approve all tool actions (**Hardline Security Floor remains fully active**). |
| `--permission-mode` | `ask` \| `auto` | Set tool authorization behavior (`ask` prompts on mutating actions, `auto` executes automatically). |
| `-m`, `--model` | `<name>` | Override the model identifier for the active session (e.g., `-m deepseek-reasoner`). |
| `--theme` | `cyber` \| `aurora` \| `minimal` | Override terminal theme. |
| `-c`, `--config` | `<path>` | Path to a custom JSON configuration file. |
| `-h`, `--help` | None | Show argument summary and exit. |

### Headless Mode Examples
```bash
# Analyze git diff from shell script
python3 oxy.py -p "Review unstaged changes and check for security flaws"

# Run automated tests and report output
python3 oxy.py -p "Run pytest and summarize failures"

# Headless refactoring with auto-approval
python3 oxy.py --yolo -p "Refactor auth.py to eliminate duplicated token checks"
```

---

## 2. Interactive Slash Commands

All slash commands support **Tab Autocompletion**.

### Core & Navigation
| Command | Aliases | Arguments | Description |
| :--- | :--- | :--- | :--- |
| `/help` | `/h`, `/?` | None | Display the grouped command reference. |
| `/clear` | — | None | Clear current conversation history from active memory. |
| `/compact` | — | None | Consolidate older turns into a user-role summary to free context (auto-compaction also runs at 75% window usage). |
| `/quit` | `/exit`, `/q` | None | Exit OXY cleanly, displaying session execution statistics. |

### Tools & Permissions
| Command | Aliases | Arguments | Description |
| :--- | :--- | :--- | :--- |
| `/tools` | — | None | List all 11 registered agent tools, parameters, and safety classifications. |
| `/permissions` | `/permission` | `[ask\|auto]` | View current permission mode or toggle between interactive and autonomous execution. |

### Procedural Skills
| Command | Aliases | Arguments | Description |
| :--- | :--- | :--- | :--- |
| `/skills` | `/skill` | `[name]` | List all installed skills, or inspect one skill's workflow. |
| `/<skill>` | — | `[task]` | Directly invoke an installed skill (e.g., `/test`, `/review`, `/refactor`, `/git-commit`). |

### Session Management & Durability
| Command | Aliases | Arguments | Description |
| :--- | :--- | :--- | :--- |
| `/sessions` | — | None | List saved session transaction ledgers, turn counts, and modification dates. |
| `/resume` | — | `<id>` | Hot-swap active conversation state by replaying a session ledger from disk. |
| `/history` | — | None | Print complete message history of the current session. |
| `/save` | — | `[path]` | Export dialogue and tool execution traces to a formatted Markdown file. |

### Codebase Context (Aider-Style)
| Command | Aliases | Arguments | Description |
| :--- | :--- | :--- | :--- |
| `/add` | — | `<path>` | Pin a file into chat context (rebuilds the frozen system prompt). |
| `/drop` | — | `<path>` | Remove a file from chat context (rebuilds the frozen system prompt). |
| `/files` | — | None | List pinned files and show the project directory structure. |
| `/git` | — | None | View git branch, short status, and modified working tree files. |

### Persistent Memory (Claude Code-Style)
| Command | Aliases | Arguments | Description |
| :--- | :--- | :--- | :--- |
| `/memory` | — | None | List all stored long-term memory entries and tags. |
| `/memory view` | — | `<slug>` | View full contents of a specific memory entry. |
| `/memory clear` | — | None | Purge all stored memories (rebuilds the frozen system prompt). |

### Model & Agent Steering
| Command | Aliases | Arguments | Description |
| :--- | :--- | :--- | :--- |
| `/model` | — | `[name]` | View active model or switch models on the fly. |
| `/system` | — | `[text\|edit\|reload]` | View, set inline, edit in `$EDITOR`, or reload from file (rebuilds the frozen system prompt). |
| `/agent` | — | `[role] <task>` | Dispatch an isolated tool-using sub-agent (`architect`, `debugger`, `reviewer`, `general`). Scoped to read-only tools, max 6 iterations by default; shares parent token tracker and theme. |
| `/agent on\|off` | — | `on\|off` | Enable or disable sub-agents for this session. |
| `/agent model` | — | `[name]` | View or set the sub-agent model (empty = main model). |
| `/agent iterations` | — | `[N]` | View or set the sub-agent tool-loop budget (default 6). |
| `/keys` | — | `[on\|off\|add]` | Manage round-robin API key pool and rotation strategies. |

### UI & Telemetry
| Command | Aliases | Arguments | Description |
| :--- | :--- | :--- | :--- |
| `/tokens` | — | None | Display prompt, completion, and total token usage counters. |
| `/copy` | — | None | Copy the last assistant response directly to system clipboard. |
| `/theme` | — | `[name]` | Switch visual theme (`cyber`, `aurora`, `minimal`). |
| `/config` | — | None | Display active configuration parameters (API keys masked). |

---

## 3. Status Line

The bottom toolbar displays live session telemetry, inspired by Grok Build's status bar:

```
 deepseek-chat  │  5 turns  │  1,234 tok  │  2:15  │  ask  │  3 files  │  /help
```

| Segment | Description |
| :--- | :--- |
| Model name | Active model identifier (e.g., `deepseek-chat`, `gpt-4o`) |
| Turn count | Number of conversation turns in the current session |
| Token total | Cumulative token usage, comma-formatted |
| Timer | Elapsed session time in `M:SS` format |
| Permission mode | `ask` (interactive confirmation) or `auto` (autonomous) |
| Active files | Number of files pinned into context via `/add` |
| Memory count | Number of persistent memory entries |
| Round-robin | `rr` indicator when round-robin key rotation is active |
| Hint | `/help` shortcut reminder |

---

## 4. Keyboard Bindings

| Key Combination | Action |
| :--- | :--- |
| `Enter` | Submit current input to agent. |
| `Alt + Enter` (or `Esc` + `Enter`) | Insert a multi-line newline without submitting. |
| `Ctrl + C` | Cancel current generation or abort running tool execution without terminating OXY. |
| `Tab` | Autocomplete slash commands. |
| `↑` / `↓` | Navigate command history across sessions (stored in `~/.oxy_history`). |
| `1` – `9` | Direct numerical jump in setup selection menus. |
| `j` / `k` | Vim-style navigation in selection menus. |

---

## 5. Turn Metadata

Each AI response displays timing and token telemetry:

```
  [turn: 2.5s]
  1,204 + 856 = 2,060  ·  session: 12,340
```

- **Turn time**: Wall-clock duration of the agentic turn
- **Token breakdown**: Prompt tokens + completion tokens = turn total
- **Session total**: Cumulative tokens across all turns

### Thinking Display (Reasoning Models)

When using reasoning models (DeepSeek R1, OpenAI o1/o3), thinking blocks render with elapsed time:

```
  ◆ Thought for 3.8s (2,450 chars)
  ┌
  │ The user wants to refactor the auth module...
  └
```
