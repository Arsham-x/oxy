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
| Command | Arguments | Description |
| :--- | :--- | :--- |
| `/help` | None | Display the quick-reference command table. |
| `/clear` | None | Clear current conversation history from active memory. |
| `/quit` | None | Exit OXY cleanly, displaying session execution statistics. |

### Tools & Permissions
| Command | Arguments | Description |
| :--- | :--- | :--- |
| `/tools` | None | List all 10 registered agent tools, parameters, and safety classifications. |
| `/permissions` | `[ask\|auto]` | View current permission mode or toggle between interactive and autonomous execution. |

### Procedural Skills
| Command | Arguments | Description |
| :--- | :--- | :--- |
| `/skills` | None | Display table of all installed project and global skills. |
| `/skill` | `<name>` | Inspect procedural workflow and instructions for a specific skill. |
| `/<skill>` | `[task]` | Directly invoke an installed skill (e.g., `/test`, `/review`, `/refactor`, `/git-commit`). |

### Session Management & Durability
| Command | Arguments | Description |
| :--- | :--- | :--- |
| `/sessions` | None | List saved session transaction ledgers, turn counts, and modification dates. |
| `/resume` | `<id>` | Hot-swap active conversation state by replaying a session ledger from disk. |
| `/history` | None | Print complete message history of the current session. |
| `/save` | `[path]` | Export dialogue and tool execution traces to a formatted Markdown file. |

### Codebase Context (Aider-Style)
| Command | Arguments | Description |
| :--- | :--- | :--- |
| `/add` | `<path>` | Pin a file directly into active chat context. |
| `/drop` | `<path>` | Remove a file from active chat context. |
| `/files` | None | List pinned files and show the project directory structure. |
| `/git` | None | View git branch, short status, and modified working tree files. |

### Persistent Memory (Claude Code-Style)
| Command | Arguments | Description |
| :--- | :--- | :--- |
| `/memory` | None | List all stored long-term memory entries and tags. |
| `/memory view` | `<slug>` | View full contents of a specific memory entry. |
| `/memory clear` | None | Purge all stored memories. |

### Model & Agent Steering
| Command | Arguments | Description |
| :--- | :--- | :--- |
| `/model` | `[name]` | View active model or switch models on the fly. |
| `/system` | `[text\|edit]` | View, set inline, or open system prompt in `$EDITOR`. |
| `/agent` | `[role] <task>` | Dispatch an isolated sub-agent (`architect`, `debugger`, `reviewer`). |
| `/keys` | `[on\|off\|add]` | Manage round-robin API key pool and rotation strategies. |

### UI & Telemetry
| Command | Arguments | Description |
| :--- | :--- | :--- |
| `/tokens` | None | Display prompt, completion, and total token usage counters. |
| `/copy` | None | Copy the last assistant response directly to system clipboard. |
| `/theme` | `[name]` | Switch visual theme (`cyber`, `aurora`, `minimal`). |
| `/config` | None | Display active configuration parameters. |

---

## 3. Keyboard Bindings

| Key Combination | Action |
| :--- | :--- |
| `Enter` | Submit current input to agent. |
| `Alt + Enter` (or `Esc` + `Enter`) | Insert a multi-line newline without submitting. |
| `Ctrl + C` | Cancel current generation or abort running tool execution without terminating OXY. |
| `Tab` | Autocomplete slash commands. |
| `↑` / `↓` | Navigate command history across sessions (stored in `~/.oxy_history`). |
| `1` – `9` | Direct numerical jump in setup selection menus. |
