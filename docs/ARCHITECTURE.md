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

## The 8 Core Subsystems

### 1. In-Place ANSI Terminal Menu Engine (`oxy/ui.py`)
Traditional CLI agents rely on asynchronous background threads (e.g., `rich.live.Live` with timer polling) to redraw menus. In raw terminal mode (`tty.setraw`), timer ticks race with keystrokes, causing terminal duplication, cursor drift, and frame ghosting.

OXY eliminates asynchronous rendering loops:
- **Synchronous Event Loop**: Keypresses block synchronously via `sys.stdin.read(1)`.
- **Absolute Delta Cursor Positioning**: Uses ANSI escapes `\033[{N}A\r` to move the cursor up precisely `N` lines and `\033[2K` to clear individual lines.
- **Terminal Width Clamping**: Output lines are clamped to `columns - 2` to prevent terminal line soft-wrapping desynchronization.
- **Clean Confirmation Wipe**: Upon selection, the entire menu block is cleared (`\033[{N}A\r\033[0J`) and replaced with a single static confirmation badge (`✔ Chosen Item`), maintaining a clean terminal scrollback buffer.

### 2. Native Unicode Typography Engine (`oxy/ui.py`)
Modern Linux and Unix terminal emulators (KDE Konsole, Ptyxis, GNOME Terminal, Alacritty) use hardware-accelerated font shaping engines (HarfBuzz, Qt, CoreText) that natively connect Arabic and Persian Unicode codepoints (`U+0600..U+06FF`) into cursive ligatures.

Third-party libraries (e.g., `arabic_reshaper`) convert standard characters into Arabic Presentation Form B (`U+FE80..U+FEFC`). When fed to modern monospace terminal shapers, Presentation Form B overrides ligature shaping, treating characters as isolated glyphs separated by whitespace gaps.
- OXY preserves raw standard Unicode codepoints in `"native"` mode, guaranteeing pixel-perfect cursive typography.
- For legacy terminal emulators without native Bidirectional support, an explicit `"bidi"` fallback mode is available.

### 3. Persist-Before-Execute Transaction Ledger (`oxy/session.py`)
Tool execution in AI agents produces irreversible side effects (file overwrites, command execution, network mutations). If an agent crashes or loses power mid-execution, memory-only state is permanently lost.

OXY enforces an append-only JSONL transaction ledger (`.oxy/sessions/<session_id>.jsonl`):
```
[Model Call] ──► [Commit Assistant Turn + Tool Calls to Disk] ──► [fsync()] ──► [Execute Tools]
```
1. Before any tool starts executing, the assistant turn containing tool call descriptors is committed to disk and flushed with `os.fsync()`.
2. Unresolved tool calls are tracked in an active ledger state.
3. Upon restart or invocation with `--resume`, OXY detects any orphaned tool calls and replays conversation history without state corruption.

### 4. Segmented Parallel Execution Planner (`oxy/tools.py`)
LLMs frequently return batches of multiple tool calls in a single turn. Naive execution either runs them sequentially (high latency) or executes all operations concurrently (causing race conditions and data corruption).

OXY partitions tool batches into distinct execution segments:
- **Concurrent Read Phase**: Consecutive read-only tools (`read_file`, `file_search`, `content_search`, `git_status`, `recall_memory`, `load_skill`) are grouped and executed concurrently across a `ThreadPoolExecutor(max_workers=8)`.
- **Sequential Mutation Barrier**: Mutating operations (`write_file`, `edit_file`, `bash`, `save_memory`) flush pending read operations and execute in strict, isolated sequence.

```
Model returns: [read(A), read(B), edit(C), read(C)]
Execution:
  Phase 1: [read(A), read(B)]  ──► Concurrent Execution (⚡ 5x faster)
  Phase 2: [edit(C)]           ──► Sequential Barrier (Protected)
  Phase 3: [read(C)]           ──► Sequential Execution (Fresh state)
```

### 5. System Prompt Immutability for KV Prefix Caching (`oxy/engine.py`)
Modern LLM APIs (DeepSeek, Anthropic, OpenAI) offer prompt caching that reduces latency and costs by 50–90% when prompt prefixes remain byte-identical across requests.

Dynamic insertions into the system prompt (e.g., real-time git branch status, active files, current timestamp) invalidate the KV cache on every turn.
- OXY byte-freezes the system prompt at engine initialization (core persona, architectural directives, skill catalog index, static memory index).
- Dynamic turn-specific metadata is injected out-of-band in tool results or user envelopes, maintaining 90%+ prefix cache hit rates.

### 6. Non-Bypassable Hardline Security Floor (`oxy/security.py`)
Autonomous modes (`--yolo` or `permission_mode="auto"`) should never grant an LLM permission to destroy the host machine.

OXY implements a two-tier defense:
1. **The Hardline Floor**: Categorically blocks catastrophic operations (`rm -rf /`, `mkfs`, raw device writes `dd of=/dev/sd*`, fork bombs, system halts, and extraction of credentials like `~/.ssh`, `~/.aws`, `/etc/shadow`). No command-line flag or agent instruction can bypass this floor.
2. **Steering File Gate**: Modifications to agent instruction files (`system_prompt.md`, `CLAUDE.md`, `AGENTS.md`, `.cursorrules`, `oxy_config.json`, `.env`) unconditionally trigger human confirmation prompts, preventing prompt injection attacks from hijacking agent behavior.

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
