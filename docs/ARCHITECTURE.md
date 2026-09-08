# OXY Architecture & System Internals

> *"Never write complex, bloated code when a simpler, robust architecture achieves the exact same result."*

OXY is an autonomous AI coding agent designed from first principles. It discards the fragile multi-threaded rendering loops, bloated abstractions, and vendor lock-in prevalent in contemporary agent frameworks in favor of a **hardened, single-threaded master loop with deterministic guarantees**.

---

## High-Level Topology

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              Terminal Cockpit                               │
│        (Native HarfBuzz Unicode Shaper · In-Place ANSI Selection Engine)    │
└──────────────────────────────────────▲──────────────────────────────────────┘
                                       │ Interactive I/O
┌──────────────────────────────────────▼──────────────────────────────────────┐
│                                OXY REPL Loop                                │
│       (Prompt Toolkit · Persistent History · Tab Completion · Commands)     │
└──────────────────────────────────────▲──────────────────────────────────────┘
                                       │ User Envelopes
┌──────────────────────────────────────▼──────────────────────────────────────┐
│                           Agentic Dispatch Engine                           │
│  ┌────────────────────────────────────────────────────────────────────────┐ │
│  │ KV Prefix-Frozen System Prompt (Base + Skills Index + Persistent Mem)   │ │
│  └───────────────────────────────────┬────────────────────────────────────┘ │
│                                      ▼                                      │
│  ┌────────────────────────────────────────────────────────────────────────┐ │
│  │ OpenAI-Compatible Multi-Provider Client (Exponential Backoff + RR Keys)│ │
│  └───────────────────────────────────┬────────────────────────────────────┘ │
│                                      ▼ Stream / Response                    │
│  ┌────────────────────────────────────────────────────────────────────────┐ │
│  │ Persist-Before-Execute Transaction Ledger (.oxy/sessions/<id>.jsonl)   │ │
│  └───────────────────────────────────┬────────────────────────────────────┘ │
│                                      ▼ Parsed Tool Calls                    │
│  ┌────────────────────────────────────────────────────────────────────────┐ │
│  │ Segmented Parallel Execution Planner                                   │ │
│  │   ├── Read-Only Phase   ──► ThreadPoolExecutor (Concurrent Non-Overlap)│ │
│  │   └── Mutation Barrier  ──► Strict Sequential Isolation Gate           │ │
│  └───────────────────────────────────┬────────────────────────────────────┘ │
│                                      ▼ Action Intent                        │
│  ┌────────────────────────────────────────────────────────────────────────┐ │
│  │ Non-Bypassable Hardline Security Floor (Catastrophic + Steering Guard) │ │
│  └───────────────────────────────────┬────────────────────────────────────┘ │
│                                      ▼ Verified Dispatch                    │
│  ┌────────────────────────────────────────────────────────────────────────┐ │
│  │ Core Tool Registry (read, write, edit, bash, search, memory, skills)   │ │
│  └────────────────────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## The 19 Core Subsystems

### 1. In-Place ANSI Terminal Menu Engine (`oxy/ui.py`)
Traditional CLI agents rely on asynchronous background threads (e.g., `rich.live.Live` with timer polling) to redraw menus. In raw terminal mode (`tty.setraw`), timer ticks race with keystrokes, causing terminal duplication, cursor drift, and frame ghosting.

OXY eliminates asynchronous rendering loops:
- **Synchronous Event Loop**: Keypresses block synchronously via raw file-descriptor reads (`os.read(fd, 32)`), supporting multi-byte ANSI escape sequences (CSI `\x1b[A`, SS3 `\x1bOA`) and Vim-style navigation (`j`/`k`) in a single call.
- **Absolute Delta Cursor Positioning**: Uses ANSI escapes `\033[{N}A\r` to move the cursor up precisely `N` lines and `\033[2K` to clear individual lines.
- **Terminal Width Clamping**: Output lines are clamped to `columns - 2` to prevent terminal line soft-wrapping desynchronization.
- **Clean Confirmation Wipe**: Upon selection, the entire menu block is cleared (`\033[{N}A\r\033[0J`) and replaced with a single static confirmation badge (`✔ Chosen Item`), maintaining a clean terminal scrollback buffer.

### 2. Native Unicode Typography Engine (`oxy/ui.py`)
Modern Linux and Unix terminal emulators (KDE Konsole, Ptyxis, GNOME Terminal, Alacritty) use hardware-accelerated font shaping engines (HarfBuzz, Qt, CoreText) that natively connect Arabic and Persian Unicode codepoints (`U+0600..U+06FF`) into cursive ligatures.

Third-party libraries (e.g., `arabic_reshaper`) convert standard characters into Arabic Presentation Form B (`U+FE80..U+FEFC`). When fed to modern monospace terminal shapers, Presentation Form B overrides ligature shaping, treating characters as isolated glyphs separated by whitespace gaps.
- OXY preserves raw standard Unicode codepoints in `"native"` mode, guaranteeing pixel-perfect cursive typography.
- For legacy terminal emulators without native Bidirectional support, an explicit `"bidi"` fallback mode is available.

### 3. Persist-Before-Execute Transaction Ledger & Crash Recovery (`oxy/session.py`)
Tool execution in AI agents produces irreversible side effects (file overwrites, command execution, network mutations). If an agent crashes or loses power mid-execution, memory-only state is permanently lost.

OXY enforces an append-only JSONL transaction ledger (`.oxy/sessions/<session_id>.jsonl`):
```
[Model Call] ──► [Commit Assistant Turn + Tool Calls to Disk] ──► [fsync()] ──► [Execute Tools]
```
1. Before any tool starts executing, the assistant turn containing tool call descriptors is committed to disk and flushed with `os.fsync()`.
2. Unresolved tool calls are tracked in an active ledger state (`pending_tool_calls`).
3. **Orphan Recovery**: Upon restart or invocation with `--resume`, OXY detects any orphaned tool calls via `has_unresolved_tool_calls()`, allowing users to discard orphaned state via `discard_unresolved_tool_calls()` or replay conversation history without state corruption.
4. **Compaction Checkpoints**: Context compaction events commit structured `compaction_checkpoint` entries to disk with `before_count`, `after_count`, and summary previews for complete auditability.

### 4. Segmented Parallel Execution Planner (`oxy/tools.py`)
LLMs frequently return batches of multiple tool calls in a single turn. Naive execution either runs them sequentially (high latency) or executes all operations concurrently (causing race conditions and data corruption).

OXY partitions tool batches into distinct execution segments:
- **Concurrent Read Phase**: Consecutive read-only tools (`read_file`, `file_search`, `content_search`, `list_dir`, `git_status`, `recall_memory`, `load_skill`, `job_status`) are grouped and executed concurrently across a `ThreadPoolExecutor(max_workers=8)`.
- **Sequential Mutation Barrier**: Mutating operations (`write_file`, `edit_file`, `bash`, `bash_background`, `job_cancel`, `save_memory`) flush pending read operations and execute in strict, isolated sequence.

```
Model returns: [read(A), read(B), edit(C), read(C)]
Execution:
  Phase 1: [read(A), read(B)]  ──► Concurrent Execution (⚡ 5x faster)
  Phase 2: [edit(C)]           ──► Sequential Barrier (Protected)
  Phase 3: [read(C)]           ──► Sequential Execution (Fresh state)
```

### 5. System Prompt Immutability & Dynamic Refresh Seam for KV Caching (`oxy/engine.py`)
Modern LLM APIs (DeepSeek, Anthropic, OpenAI) offer prompt caching that reduces latency and costs by 50–90% when prompt prefixes remain byte-identical across requests.

Dynamic insertions into the system prompt (e.g., real-time git branch status, active files, current timestamp) invalidate the KV cache on every turn.
- **Prefix Byte-Freezing**: OXY byte-freezes the system prompt at engine initialization (core persona, architectural directives, skill catalog index, static memory index). Dynamic turn-specific metadata is injected out-of-band in tool results or user envelopes, maintaining 90%+ prefix cache hit rates.
- **Dynamic Refresh Seam**: In-session prompt mutations (pinning/unpinning files via `/add` and `/drop`, updating guidelines via `/system`, or clearing memories via `/memory clear`) invoke `engine.refresh_system_prompt()`, atomically rebuilding the byte-frozen prefix in-memory so subsequent turns immediately reflect the new state without requiring session restarts.

### 6. Non-Bypassable Hardline Security Floor & Deny-by-Default (`oxy/security.py`)
Autonomous modes (`--yolo` or `permission_mode="auto"`) should never grant an LLM permission to destroy the host machine.

OXY implements a three-tier defense:
1. **The Hardline Floor**: Categorically blocks catastrophic operations (`rm -rf /`, `mkfs`, raw device writes `dd of=/dev/sd*`, fork bombs, system halts, and extraction of credentials like `~/.ssh`, `~/.aws`, `/etc/shadow`). No command-line flag or agent instruction can bypass this floor.
2. **Steering File Gate**: Modifications to agent instruction files (`system_prompt.md`, `CLAUDE.md`, `AGENTS.md`, `.cursorrules`, `oxy_config.json`, `.env`) unconditionally trigger human confirmation prompts, preventing prompt injection attacks from hijacking agent behavior.
3. **Deny-by-Default Policy**: Any tool name not explicitly registered in `KNOWN_TOOLS` and verified in `SecurityGate.evaluate_tool_call` is blocked immediately with an explicit denial error.
4. **Ambient System Prompt Quarantine**: OXY deliberately never implicitly loads an adjacent `system_prompt.md` from the current working directory to eliminate workspace-based prompt injection attacks.

### 7. Outgoing Schema Normalizer & Incoming Argument Coercer (`oxy/schemas.py`)
Different providers enforce conflicting constraints on JSON Schema definitions:
- **Outgoing Sanitizer**: Flattens `anyOf`/`oneOf` nullable unions to `{"type": "string", "nullable": true}`, strips invalid sibling keywords next to `$ref`, and validates property names against `^[a-zA-Z0-9_.-]+$`.
- **Incoming Coercer**: Heals common LLM argument hallucinations before tool dispatch:
  - Stringified numbers: `"42"` ──► `42`
  - Stringified booleans: `"true"` ──► `True`
  - Encoded arrays: `"[\"item\"]"` ──► `["item"]`
  - Python dict syntax: `"{'key': 'value'}"` ──► `{"key": "value"}`

### 8. Progressive Disclosure Skills System (`oxy/skills.py`)
Injecting thousands of tokens of procedural guidelines (test execution, code review standards, refactoring rules, git workflows) into the system prompt wastes context window and degrades inference quality.

OXY follows the **AgentSkills standard**:
- Skills are defined in modular directories (`.oxy/skills/<name>/SKILL.md` or `~/.oxy/skills/<name>/SKILL.md`).
- Only a compact, single-line summary (~15 tokens per skill) is exposed in the initial prompt.
- When invoked by slash commands (`/review`, `/test`) or the `load_skill` tool, full procedural instructions are loaded on-demand.
- Built-in multilingual triggers support natural invocation in English and Persian.

### 9. Token-Budgeted Context Compaction & Failure Preservation (`oxy/engine.py`, `oxy/session.py`)
As conversations and tool execution traces accumulate, models risk context window overflow or degraded reasoning performance.

OXY implements a two-tier compaction engine with error-preserving safety invariants:
- **Dynamic Context Sizing**: `_context_window()` automatically resolves window boundaries by model family (128,000 for DeepSeek and GPT-4o, 200,000 for Claude models, 32,768 default, or explicit user override via `context_window`).
- **Conservative Token Budgeting**: `_estimate_tokens()` calculates total prompt weight across text, tool arguments, and system prompt using a conservative ~4 chars/token heuristic.
- **Two-Tier Compaction**:
  1. *Micro-Compaction (`_micro_compact()`)*: Prunes historical tool output payloads exceeding 200 characters down to 120-character previews, retaining recent turns while freeing token headroom.
  2. *Auto-Compaction (`_auto_compact()`)*: Triggers automatically when estimated tokens exceed 75% of the effective context window or conversation history reaches 24 messages (`COMPACTION_THRESHOLD`). Older dialogue turns (beyond the 8 most recent) are summarized and consolidated.
- **Strict Failure Preservation**: When pruning or summarizing tool results, OXY inspects output strings for error conditions. If an execution failed, the `FAILED — see error` marker is strictly preserved so the model never assumes a failed file modification or shell command succeeded.
- **Provider Role Compatibility**: Many inference providers reject or crash on duplicate mid-conversation `system` role messages. OXY formats consolidated historical summaries inside a single `user`-role envelope (`[Context compacted — summary of earlier turns:]`).
- **Manual Compaction**: The `/compact` command (`compact_now(keep_recent=8)`) allows users to trigger manual compaction at any time, returning the number of pruned turns.
- **Ledger Auditing**: Compaction events record a `compaction_checkpoint` to the transaction ledger (`session.commit_compaction(before_count, after_count, summary)`).

### 10. Real-Time Streaming Pipeline with Live Markdown & Interruption (`oxy/engine.py`)
Slow, monolithic responses degrade developer experience. OXY streams inference tokens in real time with Live Markdown rendering and signal-safe cancellation.

- **SSE Streaming (`_stream_completion`)**: Iterates Server-Sent Events with empty-chunk guards (`if not chunk.choices:` handling final usage envelopes from OpenAI and DeepSeek).
- **Stream Assembly Data Structures**: Reconstructs standard completion objects (`AssembledResponse`, `AssembledChoice`, `AssembledMessage`, `AssembledToolCall`, `AssembledFunction`, `AssembledUsage`) from streaming chunks, allowing downstream agentic loops to process streamed responses identically to non-streamed responses.
- **Dual-Phase Live UI**:
  1. *Spinner Phase*: Displays a spinner with real-time thinking progress (`thinking (X chars)`) while awaiting TTFT (Time-To-First-Token) or tool call schemas.
  2. *Live Panel Phase*: Once content tokens arrive, mounts a Rich `Live` panel (`make_ai_response_panel`) that re-renders syntax-highlighted Markdown at 15Hz.
- **Reasoning Stream**: Captures and accumulates `delta.reasoning_content` from reasoning models (DeepSeek R1, OpenAI o1/o3), rendering diamond thought blocks (`◆ Thought for Xs`) before response generation.
- **Signal-Safe Interruption (`cancel()`)**: Catches `KeyboardInterrupt` (`Ctrl+C`), gracefully terminates active HTTP streams, pops unfulfilled user turns from conversation history, and resets terminal signal handlers cleanly without process termination or state corruption.
- **Non-Streaming Fallback**: If streaming fails or an API proxy lacks SSE streaming support, OXY automatically falls back to non-streaming execution (`_call_with_retry`).

### 11. Bounded Sub-Agent Execution Loop with Scoped Tools & Shared Telemetry (`oxy/engine.py`, `oxy/commands.py`)
Complex engineering tasks benefit from specialized sub-agents running focused workflows without polluting the main conversation's context window.

- **Specialized Personas**:
  - `architect`: High-level system architecture, subsystem boundaries, zero-bloat patterns.
  - `debugger`: Root-cause analysis, stack trace inspection, minimal reproducible fixes.
  - `reviewer`: Security flaws, race conditions, type safety, performance regressions.
  - `general`: Versatile exploration and autonomous task execution.
- **Strict Tool Scoping (`DEFAULT_ALLOWED_TOOLS`)**:
  - Allowed by default: `read_file`, `file_search`, `content_search`, `list_dir`, `git_status`, `recall_memory`, `load_skill` (read-only tools).
  - Categorically blocked: `write_file`, `edit_file`, `bash`, `save_memory`. Sub-agents cannot mutate workspace files, execute arbitrary shell commands, or overwrite long-term memory without explicit operator opt-in.
- **Autonomous Multi-Iteration Loop**: Executes a bounded agentic loop up to `sub_agent_max_iterations` (default 6, configurable via `/agent iterations <N>` or config) and `sub_agent_max_tokens` (default 2048).
- **Context Isolation & Shared Telemetry**:
  - *Context Isolation*: Runs in an isolated `messages` list; leaves `engine.history` and `.oxy/sessions/<id>.jsonl` untouched.
  - *Shared Telemetry*: Sub-agent token consumption is aggregated directly into the parent `engine.tokens` tracker, maintaining 100% accurate session-wide token accounting.
- **Interactive Controls**:
  - `/agent [role] <task>`: Dispatch a sub-agent with a specific persona.
  - `/agent on|off`: Toggle sub-agent availability.
  - `/agent model <name>`: Configure an independent model for sub-agents (e.g. a faster, lightweight model).
  - `/agent iterations <N>`: Adjust the sub-agent iteration budget.

### 12. Declarative Command Registry & Tab Autocompletion (`oxy/commands.py`, `oxy/input.py`)
Cockpit command dispatch is unified into a declarative registry that serves as the single source of truth across execution, documentation, and prompt completion.

- **Single Source of Truth**: The `Command` dataclass defines `name`, `handler`, `description`, `usage`, `aliases`, `group`, and `needs_arg`.
- **Centralized Dispatch & Argument Checking**: Replaces sprawling 20-arm `match` or `if/elif` blocks with table-driven lookup, auto-grouping in `/help`, and automatic missing-argument validation (`needs_arg`).
- **Natural Aliases**:
  - `/help` ──► `/h`, `/?`
  - `/quit` ──► `/exit`, `/q`
  - `/permissions` ──► `/permission`
  - `/skills` ──► `/skill`
- **Dynamic Categorized Help**: Commands automatically group into `Core`, `Tools & Permissions`, `Codebase & Files`, `Memory`, `Agent & Model`, and `Session & Durability`.
- **Direct Autocompletion Export**: Exports `SLASH_COMMANDS` directly to `prompt_toolkit`'s `WordCompleter`, guaranteeing command prompt autocompletion is always in sync with registered commands.

### 13. Model Context Protocol (MCP) Stdio JSON-RPC Client (`oxy/mcp.py`)
OXY natively connects to external tool ecosystems via the open Model Context Protocol (MCP) specification over stdio:
- **JSON-RPC 2.0 Handshake**: Spawns external MCP server subprocesses, performs `initialize` capabilities exchange (`protocolVersion: 2024-11-05`), and emits `notifications/initialized`.
- **Dynamic Discovery & Namespacing**: Queries `tools/list` on launch and registers tools into `ToolRegistry` and `TOOL_SCHEMAS` under the `mcp_{server}_{tool}` namespace.
- **Security Containment**: Every dynamic MCP tool call is registered into `KNOWN_TOOLS` and checked through `SecurityGate.evaluate_tool_call()`.
- **Clean Teardown**: `MCPManager.shutdown()` safely terminates all spawned MCP servers on exit or session end.

### 14. Deterministic Lifecycle Hooks System (`oxy/hooks.py`)
Inspired by Git hooks and Claude Code lifecycle callbacks, OXY allows developers to extend the agent without touching its core loop:
- **Events**:
  - `session_start`: Dispatched when the REPL initializes.
  - `pre_turn`: Dispatched before sending a message to the LLM; can modify input or abort the turn.
  - `pre_tool_call`: Dispatched before executing any tool; can block or modify arguments.
  - `post_tool_call`: Dispatched after tool execution with execution status and output.
  - `post_turn`: Dispatched after the final assistant response.
  - `session_end`: Dispatched on clean REPL exit.
- **Dual Support**: Supports in-memory Python callable listeners (`hooks.register(event, callback)`) and file-based workspace executable scripts (`.oxy/hooks/<event>` or `.oxy/hooks/<event>.sh`).
- **Exception Boundary**: Hook errors are isolated and never crash the active REPL session.

### 15. Non-Destructive Append-Only Ledger Rewind & Undo (`oxy/session.py`)
Unlike naive CLI tools that physically delete files or slice records, OXY maintains a 100% durable audit trail:
- **Append-Only Markers**: Rewind operations write an explicit `{"type": "rewind", "payload": {"message_count": N}}` entry to `.oxy/sessions/<id>.jsonl`.
- **Deterministic Replay**: During ledger replay on session resume, `_truncate_messages_to_prefix` truncates the visible message list to the requested prefix, guaranteeing clean state reproduction while preserving full historical audits on disk.
- **Commands**: `/rewind <N>` rewinds to the first `N` messages; `/undo` removes the last user turn and all generated responses/tool calls.

### 16. Asynchronous Background Job Execution Engine (`oxy/jobs.py`, `oxy/tools.py`)
Long-running operations (test suites, build steps, local servers) can freeze an interactive REPL. OXY provides non-blocking asynchronous execution:
- **Subprocess Isolation**: `JobManager` launches background processes with dedicated stdout/stderr capture pipes, unique hex IDs, and thread-safe status tracking.
- **Daemon Watcher Threads**: Lightweight threads monitor process exit status and capture tail output without blocking user conversation.
- **Agent Tools**: Exposes `bash_background` (submits job), `job_status` (polls status and output), and `job_cancel` (terminates job).
- **Interactive Control**: Slash command `/jobs [job_id]` inspects active or completed jobs.

### 17. Thread-Safe API Key Rotation with Reactive 429 Cooldown (`oxy/keys.py`)
High-volume agent workflows frequently hit provider rate limits (HTTP 429). OXY provides enterprise-grade key rotation:
- **Strategy Enum**: Type-safe strategies: `SEQUENTIAL` (round-robin), `RANDOM`, and `LEAST_USED`.
- **Lock Protection**: `threading.Lock` guarantees race-free key rotation across parallel worker threads.
- **Reactive Cooldown**: When an HTTP 429 rate limit is received, `mark_cooldown(key, cooldown_seconds)` benches the exhausted key and skips it in subsequent rotations until its backoff window expires.

### 18. Multi-Tier Workspace Memory Overlay & Multi-Signal Recall (`oxy/memory.py`)
Persistent memory supports both global developer rules and workspace-specific team standards:
- **Two-Tier Storage**: Global memories live in `~/.oxy/memory/`; workspace-scoped rules live in `.oxy/memory/`.
- **Overlay Precedence**: Project-local memories take precedence over global memories during recall.
- **Multi-Signal Relevance Scoring**: Queries match against slug identifiers, titles, and body content with keyword-frequency and proximity weighting.
- **Index Injection**: Project memory overlays are automatically indexed and injected into the byte-frozen system prompt (`get_memory_index_text()`).

### 19. Structured JSONL Observability & Secret Redaction (`oxy/observability.py`)
Every agent decision, tool execution, and token count is logged for post-mortem analysis:
- **Structured JSONL**: Logs to `.oxy/logs/<session_id>.jsonl` with timestamps, event types, and payloads.
- **Secret Redaction**: Regex-based redaction intercepts API keys (`sk-...`, `sk-ant-...`, `xoxb-...`), bearer tokens, and credentials before writing to disk, ensuring logs are safe for sharing and debugging.

---

## Grok Build-Inspired Interface Layer

OXY's terminal interface draws from production-grade patterns observed in Grok Build (xAI's terminal coding agent). These are adapted from Rust TUI concepts into Python/Rich/prompt_toolkit equivalents.

### Status Line (`oxy/input.py`)
A persistent bottom toolbar renders live session telemetry in a single compact row:

```
 deepseek-chat  │  5 turns  │  1,234 tok  │  2:15  │  ask  │  3 files  │  /help
```

Fields: model name, turn count, formatted token total, elapsed session timer (`M:SS`), permission mode (`ask`/`auto`), active file count, memory count, round-robin indicator, and `/help` hint. Updated on every prompt cycle via `prompt_toolkit`'s `bottom_toolbar` callback.

### Turn Timing Telemetry (`oxy/engine.py`)
Each agentic turn is bracketed by `time.perf_counter()` measurements:
- **Turn duration**: Wall-clock time from user message dispatch to final response render, displayed as a `[turn: Xs]` badge below each response.
- **Thinking elapsed**: For reasoning models (DeepSeek R1, OpenAI o1/o3), the duration of the `<think>` block is captured separately and passed to the thinking renderer.

### Thinking Display (`oxy/render.py`)
Reasoning model output renders with a status diamond and elapsed time:

```
  ◆ Thought for 3.8s (2,450 chars)
  ┌
  │ The user wants to refactor the auth module...
  └
```

The `◆` diamond icon and elapsed-time header are inspired by Grok Build's thinking status indicators.

### Tool Execution Display (`oxy/render.py`)
Tool calls render with clean status badges:
- `●` dot for in-progress tools
- `✔` checkmark for successful completion with timing
- `⚡` indicator for parallel read operations
- `✖` for failures with error details

### Welcome Panel (`oxy/render.py`)
The welcome screen shows a dual-panel layout:
- **Engine panel**: Model name, provider endpoint, permission mode
- **Context panel**: Workspace path, active files, memory entries, git branch
- **Hint bar**: Quick-reference for key commands (`/help`, `/tools`, `/skills`, `Alt+Enter`)

### Three Themes (`oxy/render.py`)
Each theme dict includes: `accent`, `dim`, `border`, `prompt`, `success`, `warning`, `tool_icon`, and `think_icon` colors. Themes are switchable at runtime via `/theme` or `--theme`.
