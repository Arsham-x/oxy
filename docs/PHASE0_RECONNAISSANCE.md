# OXY Phase 0 — Deep Repository Reconnaissance & Architectural Audit

> Generated from parallel analysis of all 23 source files (5,732 LOC) by 24-agent workflow.
> Date: 2026-09-08

---

## 1. SYSTEM MAP

```
USER INPUT
    │
    ▼
oxy.py ─────────────────────────── Thin entry point (3 lines → app.main)
    │
    ▼
app.py::main() ─────────────────── God function (155 lines)
    ├── argparse (10 flags)
    ├── load_config() + validate_config()    ← config.py
    ├── resolve_system_prompt()               ← config.py (⚠ P0: loads hostile system_prompt.md)
    ├── get_theme()                           ← render.py
    ├── KeyManager()                          ← keys.py (optional)
    ├── ChatEngine()                          ← engine.py (god object, 608 lines)
    │       ├── ToolRegistry()                ← tools.py
    │       ├── SkillManager()                ← skills.py
    │       ├── RepoContext()                 ← repo.py
    │       ├── Session()                     ← session.py
    │       ├── TokenTracker()                ← engine.py
    │       └── _frozen_system_prompt         ← built once, never rebuilt
    ├── SessionRegistry.resume()              ← session.py (optional)
    ├── setup_wizard()                        ← setup.py (if --setup)
    ├── print_welcome()                       ← render.py
    ├── make_prompt_session()                 ← input.py
    │
    ▼
REPL LOOP (while True)
    ├── session.prompt() ──► user text
    ├── if /command → handle_command()        ← commands.py (20-arm match/case)
    └── else → engine.send(text)
              │
              ▼
         ChatEngine.send() ── for i in range(15):
              ├── _auto_compact() + _micro_compact()
              ├── _build_messages() → [system, ...history]
              ├── _call_with_retry() → blocking completion (NO streaming)
              │       └── 429 → time.sleep countdown + key rotation
              ├── if tool_calls:
              │       ├── session.commit_assistant_pre_execution()  ← PERSIST FIRST
              │       ├── plan_execution_batches()                  ← tools.py
              │       │       ├── consecutive reads → ThreadPoolExecutor
              │       │       └── mutations → sequential barrier
              │       ├── SecurityGate.evaluate_tool_call()         ← security.py
              │       │       ├── BLOCKED → reject
              │       │       ├── REQUIRES_CONFIRMATION → ask_permission()
              │       │       └── ALLOWED → execute (⚠ default for unknown tools)
              │       ├── execute tool → ToolResult
              │       ├── session.commit_tool_result()
              │       └── continue loop
              └── else (text response):
                      ├── session.commit_assistant_text()
                      ├── render_ai_response()                     ← render.py
                      └── return
```

### Module Dependency Graph
```
oxy.py → app
app → config, engine, keys, memory, render, input, commands, setup
engine → config, tools, skills, session, render, repo, schemas, security, keys
commands → config, render, memory, session, skills, engine (via param)
render → ui (lazy), memory (lazy)
ui → (standalone, stdlib + rich)
tools → security, schemas, memory, skills
setup → config, render, ui
repo → tools (IGNORED_DIRS only)
input → (standalone, prompt_toolkit)
security → (standalone, stdlib only)
schemas → (standalone, stdlib only)
skills → (standalone, stdlib only)
memory → (standalone, stdlib only)
keys → (standalone, stdlib only)
session → (standalone, stdlib only)
config → (standalone, stdlib only)
```

---

## 2. CURRENT ARCHITECTURE

### Agent Loop
- **Type**: Synchronous `for` loop in `ChatEngine.send()`, NOT a state machine
- **Max iterations**: 15 (`MAX_TOOL_ITERATIONS`)
- **Pre-step**: `_auto_compact` + `_micro_compact` + `_rotate_client`
- **Cancellation**: Boolean `_cancelled` set by SIGINT handler
- **No streaming**: Despite config flag, every turn blocks on full completion
- **No planning**: No planner/executor split, no task tracking
- **No pause/resume/rewind**: Loop is fire-and-forget

### TUI Architecture
Three disjoint rendering mechanisms with no shared `Renderer` seam:

| Layer | Module | Mechanism |
|:------|:-------|:----------|
| Rich panels/tables/markdown | `render.py` | Global `Console` singleton, 19 stateless functions |
| prompt_toolkit chrome | `input.py` | `PromptSession` + toolbar closure + key bindings |
| Raw ANSI menus | `ui.py` | `tty.setraw` + `os.read(fd,32)` + cursor arithmetic |

### Tool Architecture
- **Registry**: 10 builtin tools in `ToolRegistry`, `register()` exists but has no schema path
- **Schemas**: 225-line hand-maintained `TOOL_SCHEMAS` dict (drift risk)
- **Dispatch**: `execute()` → coerce args → `SecurityGate` → function call → `ToolResult`
- **Planner**: `plan_execution_batches()` — correct read/write segmentation
- **Output bounding**: 250-line + 25KB truncation with disk spill

### Context System
- **Frozen prompt**: Built once in `__init__`, never rebuilt (stale after `/system`, `/add`, `/drop`, `save_memory`)
- **Compaction**: Count-based (threshold=24), not token-based
- **Micro-compact**: Rewrites failed tool outputs as "completed successfully" (data loss)
- **Macro-compact**: Injects `role: system` mid-history (breaks tool_call pairing)

### Extension Ecosystem
- **Skills**: 4 builtins + filesystem discovery (`.oxy/skills/`, `~/.oxy/skills/`) ✓
- **MCP**: ✗ Missing entirely
- **Hooks**: ✗ Missing entirely
- **Plugin manifest**: ✗ Missing
- **Command registry**: ✗ Hardcoded match/case

---

## 3. CURRENT STRENGTHS

| # | Strength | Module |
|:--|:---------|:-------|
| 1 | **Persist-Before-Execute ledger** — `flush` + `fsync` before tool side effects | `session.py` |
| 2 | **Three-verdict security policy** — `ALLOWED`/`REQUIRES_CONFIRMATION`/`BLOCKED`, stateless, stdlib-only | `security.py` |
| 3 | **Read-before-write with mtime staleness** — prevents blind overwrites | `tools.py` |
| 4 | **Segmented parallel execution planner** — concurrent reads, sequential mutation barriers | `tools.py` |
| 5 | **Output bounding** — 250-line truncation + 25KB spill to disk | `tools.py` |
| 6 | **Byte-frozen system prompt** — correct KV prefix-cache optimization intent | `engine.py` |
| 7 | **Progressive-disclosure skills** — compact index + on-demand load | `skills.py` |
| 8 | **Provider-agnostic client** — OpenAI-compatible, any endpoint | `setup.py` |
| 9 | **Clean leaf modules** — `security`, `keys`, `schemas`, `skills`, `memory`, `session` import only stdlib | various |

---

## 4. CURRENT WEAKNESSES

| # | Weakness | Severity |
|:--|:---------|:---------|
| 1 | **Hostile `system_prompt.md` auto-loaded** — shipped "Onyx v67" persona with non-refusal directives silently activates when run from repo dir | **P0 Critical** |
| 2 | **SecurityGate open-by-default** — unknown tools return `ALLOWED`, bypasses silently | **P0** |
| 3 | **No streaming** — blocks on full completion, worst latency UX of any modern agent | **P1** |
| 4 | **ChatEngine god object** — 608 lines fusing client, retry, permission UI, compaction, orchestration, session, prompt assembly | **P1** |
| 5 | **Frozen prompt never rebuilt** — `/system`, `/add`, `/drop`, `save_memory` invisible until restart | **P1** |
| 6 | **Dual history stores diverge** — `engine.history` + `Session.messages` + ledger JSONL, no single source of truth | **P1** |
| 7 | **Compaction loses data** — micro-compact rewrites failures as success, macro-compact breaks tool_call pairing | **P1** |
| 8 | **Config is untyped dict** — typos persist silently, validation mutates, non-atomic saves, cwd-dependent | **P2** |
| 9 | **Search is pure-Python `os.walk`** — no timeouts, nondeterministic order, no ripgrep | **P2** |
| 10 | **SubAgent is single-shot no-tool** — cannot use tools despite docstring | **P2** |
| 11 | **No MCP, no hooks, no checkpoints/undo** | **P2** |
| 12 | **Narrow-terminal NameError** — `version` undefined in compact branch of `ui.py` | **P2** |
| 13 | **Toolbar closure freezes counts** — stale display until factory recalled | **P2** |

---

## 5. ARCHITECTURAL SMELLS

1. **God function** `main()` in `app.py` — 155 lines, zero decomposition
2. **God object** `ChatEngine` in `engine.py` — 608 lines, 7+ responsibilities
3. **God dispatcher** `handle_command` in `commands.py` — 20+ case arms, violates Open-Closed
4. **Global mutable state** — `READ_FILE_STATE` dict in `tools.py` shared process-wide
5. **Three global Console singletons** — `render.py`, `ui.py`, `setup.py` each create their own
6. **Import-time path binding** — `MEMORY_DIR`, `HISTORY_FILE`, `CONFIG_FILE` bound to `Path.home()` at import
7. **Stringly-typed everywhere** — theme dict (22 implicit keys), config dict (17 keys), `entry_type`, `permission_mode`, `strategy`
8. **Circular import** — `render.py` → `ui.py` hidden with lazy function-body imports
9. **Dead code** — `OXY_BLOCK_ART` color field never read, `reshape_markdown` no-op stub, unused imports across 7 modules
10. **Path traversal** — `cmd_save` uses `Path(arg).write_text`, `cmd_system` passes unsanitized `$EDITOR` to `os.system`
11. **Unbounded growth** — `~/.oxy/tool-results/` with no rotation, ledger `O(n)` full replay on resume
12. **Regex security fragile** — bypassable via `$VAR` expansion, `eval`, base64, pipes; `cp`/`scp`/`tar` exfil not covered

---

## 6. GAP ANALYSIS vs Modern Coding Agents

| Capability | OXY | Claude Code | Grok Build | Codex |
|:-----------|:---:|:----------:|:----------:|:-----:|
| Streaming + cancellable generation | ✗ | ✓ | ✓ | ✓ |
| Plan mode / task tracking | ✗ | ✓ | ✓ | ≈ |
| Checkpoints / rewind / undo | ✗ | ✓ | ≈ | ✓ |
| Parallel subagents with tools | ⚠ | ✓ | ✓ | ✓ |
| MCP tools / resources / prompts | ✗ | ✓ | ✗ | ✗ |
| Hooks / command registry / events | ✗ | ✓ | ≈ | ✗ |
| Workspace sandbox / approval scopes | ⚠ | ✓ | ✓ | ✓ |
| File edit with diff | ≈ | ✓ | ✓ | ✓ |
| Search / codebase map | ⚠ | ✓ | ✓ | ✓ |
| Shell + git | ≈ | ✓ | ✓ | ✓ |
| Context management | ⚠ | ✓ | ✓ | ≈ |
| Session persistence | ≈ | ✓ | ✓ | ≈ |
| Multi-key failover | ≈ | N/A | N/A | N/A |
| Prompt input UX | ≈ | ✓ | ✓ | ≈ |
| Themes + rendering | ✓ | ≈ | ✓ | ✗ |
| Memory | ⚠ | ✓ | ✗ | ✗ |
| Setup + onboarding | ✓ | ≈ | ≈ | ✗ |
| Evals / tests / observability | ✗ | ✓ | ✓ | ✓ |
| IDE / web / background execution | ✗ | ✓ | ✗ | ✓ |
| Native i18n (Persian/Arabic) | ✓ | ✗ | ✗ | ✗ |

**Legend**: ✓ Strong · ≈ Acceptable · ⚠ Weak · ✗ Missing

---

## 7. QUICK WINS (< 50 lines each)

| # | Fix | Lines | Impact |
|:--|:----|:-----:|:-------|
| 1 | Fix `config["api_key"]` → `config.get("api_key")` in `app.py:64` | 1 | Prevents startup `KeyError` |
| 2 | Deny-by-default in `SecurityGate.evaluate_tool_call` for unknown tools | 3 | Closes security bypass |
| 3 | Fix `version` NameError in `ui.py:378` — hoist above branch | 2 | Fixes narrow terminal crash |
| 4 | Wrap `engine.send` in `app.py` with `try/except` rendering error panel | 10 | Stops tool errors killing REPL |
| 5 | Recreate toolbar each turn or accept state callbacks | 30 | Fixes stale status display |
| 6 | Precompile steering-file regexes at module level | 15 | Performance improvement |
| 7 | Add `engine.refresh_system_prompt()` called from `/system`, `/add`, `/drop` | 20 | Fixes frozen prompt staleness |
| 8 | Atomic config write via `tmp` + `os.replace` + `fsync` | 20 | Prevents config corruption |
| 9 | Fix micro-compact to preserve failure label and error text | 10 | Stops data loss |
| 10 | Escape HTML in `make_toolbar` model interpolation | 10 | Prevents XSS in toolbar |
| 11 | Change `.gitignore` `chat_20260908_073521.md` to `chat_*.md` | 1 | Proper wildcard |
| 12 | Add timeout to `RepoContext` git subprocess calls | 15 | Prevents hangs |

---

## 8. DEEP REFACTOR CANDIDATES

| # | Candidate | Rationale |
|:--|:----------|:----------|
| 1 | **Split ChatEngine** into `LlmClient` (SDK+retry+streaming), `Conversation` (history+compaction+messages), `Policy` (permission+SecurityGate+audit), `Executor` (batch planning+dispatch+ledger) | God object cannot be unit tested, every change risks regression |
| 2 | **Typed Config** dataclass with validated load, atomic save, XDG compliance, explicit resolution | Every module depends on this seam — must fix first |
| 3 | **Unified SessionStore** — single source of truth replacing dual `engine.history` + `Session.messages` | History divergence causes resume bugs and stale state |
| 4 | **Renderer interface** with `RichConsole`/`NoOp`/`Test` adapters, injected into engine+commands | Fixes testability, eliminates global consoles, resolves render↔ui cycle |
| 5 | **Token-budgeted compaction** replacing heuristic count-based pruning | Current compaction loses data, breaks tool_call pairing, has no cost awareness |
| 6 | **Ripgrep-backed search** with timeout, binary skip, deterministic ordering, `list_dir` tool | Pure-Python walk is too slow and unreliable for real codebases |
| 7 | **Real workspace sandbox** — path canonicalization, symlink checks, workspace_root boundary | Regex floor is necessary but insufficient defense |
| 8 | **Extension registry** — unified Command/Tool/Skill interface driving dispatch+help+completions | Current 20-arm match/case prevents extension without editing core |

---

## 9. PRIORITIZED ROADMAP

### P0 — Foundational / Blocking

| ID | Task | Why Blocking |
|:---|:-----|:-------------|
| P0-1 | **Remove/quarantine hostile `system_prompt.md`** — change `resolve_system_prompt` to never auto-load adjacent file without explicit `system_prompt_file` config | Any run from repo dir loads non-refusal persona |
| P0-2 | **Close open-by-default security dispatch** — deny unknown tools, require explicit policy per tool, add audit log | New tools bypass security silently |
| P0-3 | **Unify conversation state** — make `Session` the single source of truth, surface `has_unresolved_tool_calls` on startup | Dual stores diverge, crash recovery is write-only |
| P0-4 | **Harden config** — typed Config, atomic write, explicit resolution, fix `api_key` KeyError | Foundation every module builds on |
| P0-5 | **Crash-proof REPL** — wrap `engine.send` with exception boundary, fix SIGINT restore with `try/finally` | Unhandled exceptions kill session |

### P1 — High Impact

| ID | Task |
|:---|:-----|
| P1-1 | **Add streaming with cancellation** — stream deltas into Rich Live panel, wire SIGINT to cancel |
| P1-2 | **Token-budgeted compaction** — replace heuristic with model-graded summarization, preserve errors |
| P1-3 | **Fix frozen-prompt staleness** — add `rebuild_frozen_prompt()` called on mutation commands |
| P1-4 | **Ripgrep-backed search** — adapter with timeout + binary skip + `list_dir` tool |
| P1-5 | **Command registry** — `Command` dataclass driving dispatch + help + completions |
| P1-6 | **Testable rendering** — `Renderer` interface, `Theme` TypedDict, fix toolbar + narrow-terminal crash |
| P1-7 | **Give subagents tools and budgets** — tool subset + max iterations + isolated ledger |

### P2 — Important

| ID | Task |
|:---|:-----|
| P2-1 | **MCP client** — stdio + SSE transports, tool discovery into `ToolRegistry` |
| P2-2 | **Lifecycle hooks** — `pre_tool`, `post_tool`, `session_start`, `session_stop` |
| P2-3 | **Checkpoints and undo** — ledger-backed `/rewind` + edit undo stack |
| P2-4 | **Background execution** — detached bash/subagents with job table |
| P2-5 | **Fix KeyManager** — thread lock, strategy enum, reactive 429 cooldown |
| P2-6 | **Project-scoped memory** — `.oxy/memory` overlay + ranked recall |
| P2-7 | **Cross-platform hardening** — Windows fallback for termios, HTML escaping |
| P2-8 | **Observability** — structured logging, cost estimates, export with secret redaction |

### P3 — Polish / Future

| ID | Task |
|:---|:-----|
| P3-1 | Theme registry with validation and user theme files |
| P3-2 | Complete i18n (translate all chrome for fa + zh) |
| P3-3 | Packaging hygiene (upper-bound deps, lockfile, dev extras) |
| P3-4 | Docs overhaul (architecture seams, adding tools/skills/providers) |
| P3-5 | Idle polish (dedup boilerplate, prune dead code, unify consoles) |

---

## 10. TARGET ARCHITECTURE (Summary)

```
┌─────────────────────────────────────────────────────────────────┐
│                        CLI / TUI Layer                          │
│   Renderer(interface) ← RichConsole │ NoOp │ Test adapters      │
│   CommandRegistry ← Command dataclass + handler + schema        │
│   InputManager ← prompt_toolkit + live toolbar callbacks        │
└──────────────────────────────┬──────────────────────────────────┘
                               │
┌──────────────────────────────▼──────────────────────────────────┐
│                      Agent Runtime                               │
│   Conversation ← history + compaction + message building         │
│   Executor ← batch planning + dispatch + ledger commits          │
│   Policy ← permission + SecurityGate + workspace sandbox         │
│   LlmClient ← SDK adapter + retry + streaming + key rotation     │
│   TokenBudget ← provider usage + tiktoken fallback               │
└──────────────────────────────┬──────────────────────────────────┘
                               │
┌──────────────────────────────▼──────────────────────────────────┐
│                     Extension Layer                               │
│   ToolRegistry ← builtins + MCP + custom, schema-validated       │
│   SkillManager ← builtins + user + project, progressive          │
│   HookDispatcher ← pre/post tool + session lifecycle             │
│   SubAgentPool ← scoped tools + budgets + isolated ledger        │
└──────────────────────────────┬──────────────────────────────────┘
                               │
┌──────────────────────────────▼──────────────────────────────────┐
│                    Foundation Layer                               │
│   Config ← typed dataclass + atomic persistence                  │
│   SessionStore ← single JSONL source of truth                    │
│   SecurityGate ← deny-by-default + regex floor + sandbox         │
│   Memory ← global + project-scoped + ranked recall               │
└─────────────────────────────────────────────────────────────────┘
```

---

## NEXT: Phase 1 — P0 Fixes

The first implementation phase will address all 5 P0 items:
1. Quarantine hostile system prompt
2. Close open-by-default security
3. Unify conversation state
4. Harden config seam
5. Crash-proof REPL

These are blocking — no architectural improvement is safe to build on a foundation with these defects.
