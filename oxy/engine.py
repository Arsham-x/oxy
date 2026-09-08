"""
OXY Engine — Chat engine, tool-use agentic loop, streaming, and sub-agents.

Core Architecture:
  - Agentic Loop: LLM -> tool_calls -> Permission Gate -> Execution -> Tool Results -> Iterate
  - Single-threaded master loop inspired by Claude Code
  - Context auto-compaction when conversation memory grows
  - Rate limit handling (HTTP 429) with exponential backoff countdown & key rotation
  - Sub-agent personas (architect, debugger, reviewer, general)
  - Tool execution with syntax-highlighted diffs and live progress indicators
"""

from __future__ import annotations

import json
import os
import time
from typing import Any

from openai import OpenAI, APIError, APIConnectionError, RateLimitError
from rich.live import Live

from .render import (
    console, make_spinner, make_ai_response_panel, render_ai_response,
    render_sub_agent_response, render_token_info, render_error_panel,
    render_diff, render_tool_start, render_tool_result, ask_permission,
    render_thought, render_compaction_notice, get_theme,
)
from .keys import KeyManager
from .tools import ToolRegistry, ToolResult
from .memory import get_memory_index_text
from .repo import RepoContext
from .session import Session
from .skills import SkillManager


MAX_RETRIES = 3
RETRY_BASE_DELAY = 2
MAX_TOOL_ITERATIONS = 15
COMPACTION_THRESHOLD = 24  # messages before folding context


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  Token Tracker
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class TokenTracker:
    __slots__ = ("total_prompt", "total_complete", "turns")

    def __init__(self):
        self.total_prompt = 0
        self.total_complete = 0
        self.turns = 0

    def add(self, prompt_tokens: int, completion_tokens: int):
        self.total_prompt += prompt_tokens
        self.total_complete += completion_tokens
        self.turns += 1

    @property
    def total(self) -> int:
        return self.total_prompt + self.total_complete


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  Stream Assembly Data Structures
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class AssembledFunction:
    __slots__ = ("name", "arguments")

    def __init__(self, name: str = "", arguments: str = ""):
        self.name = name
        self.arguments = arguments


class AssembledToolCall:
    __slots__ = ("id", "type", "function")

    def __init__(self, id: str = "", function: AssembledFunction | None = None, type: str = "function"):
        self.id = id
        self.function = function or AssembledFunction()
        self.type = type


class AssembledMessage:
    __slots__ = ("content", "tool_calls", "reasoning_content")

    def __init__(
        self,
        content: str | None = None,
        tool_calls: list[AssembledToolCall] | None = None,
        reasoning_content: str | None = None,
    ):
        self.content = content
        self.tool_calls = tool_calls
        self.reasoning_content = reasoning_content


class AssembledChoice:
    __slots__ = ("message",)

    def __init__(self, message: AssembledMessage):
        self.message = message


class AssembledUsage:
    __slots__ = ("prompt_tokens", "completion_tokens")

    def __init__(self, prompt_tokens: int = 0, completion_tokens: int = 0):
        self.prompt_tokens = prompt_tokens
        self.completion_tokens = completion_tokens


class AssembledResponse:
    __slots__ = ("choices", "usage", "was_streamed", "thought_rendered")

    def __init__(
        self,
        choices: list[AssembledChoice],
        usage: AssembledUsage | None = None,
        was_streamed: bool = False,
        thought_rendered: bool = False,
    ):
        self.choices = choices
        self.usage = usage
        self.was_streamed = was_streamed
        self.thought_rendered = thought_rendered


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  Chat Engine (Agentic Master Loop)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class ChatEngine:
    """The central agentic engine orchestrating model calls, tool use, and memory."""

    def __init__(self, config: dict[str, Any], key_manager: KeyManager | None = None):
        self.config = config
        self.key_manager = key_manager
        self.system_prompt = ""
        self.max_history = config.get("max_history", 20)
        self.history: list[dict[str, Any]] = []
        self.tokens = TokenTracker()
        self._cancelled = False
        self._theme = get_theme(config.get("theme", "minimal"))

        # Tools, Skills & Codebase context
        self.tools = ToolRegistry()
        self.skills = SkillManager()
        self.repo = RepoContext(os.getcwd())

        # Persist-Before-Execute Session Ledger
        session_id = config.get("session_id")
        self.session = Session(session_id=session_id, title=config.get("session_title", "OXY Interactive Session"))

        # Permission state: 'ask' (interactive prompt on mutating tools) or 'auto'
        self.permission_mode = config.get("permission_mode", "ask")
        self.always_allow: set[str] = set()

        # Build OpenAI client
        api_key = self._resolve_key()
        self.client = OpenAI(base_url=config["base_url"], api_key=api_key)

        # Pre-compute byte-frozen system prompt for KV prefix-cache preservation
        self._frozen_system_prompt = self._assemble_frozen_system_prompt()

    def _resolve_key(self) -> str:
        if self.key_manager and self.key_manager.is_active:
            return self.key_manager.next_key()
        return self.config.get("api_key", "")

    def _rotate_client(self):
        if self.key_manager and self.key_manager.is_active:
            new_key = self.key_manager.next_key()
            self.client = OpenAI(base_url=self.config["base_url"], api_key=new_key)

    def cancel(self):
        self._cancelled = True

    def set_model(self, model: str):
        self.config["model"] = model

    def set_system(self, prompt: str):
        self.system_prompt = prompt
        self.refresh_system_prompt()

    def refresh_system_prompt(self):
        """Re-assemble the frozen system prompt after mutations (e.g. /add, /drop, /system, memory)."""
        self._frozen_system_prompt = self._assemble_frozen_system_prompt()

    def clear_history(self):
        self.history.clear()

    # ── Context Assembler & KV Cache Preservation ───────────────────

    def _assemble_frozen_system_prompt(self) -> str:
        """Compose byte-frozen system prompt for KV prefix-cache preservation.

        Freezes the immutable prefix (persona + core directives + tool rules + skills + memory)
        to ensure 90%+ prefix cache hit rate on Anthropic, DeepSeek, and OpenAI across turns.
        """
        sections = []

        # 1. Base persona / instructions
        base = self.system_prompt or self.config.get("system_prompt", "You are OXY, an elite AI coding agent.")
        sections.append(base.strip())

        # 2. Core Architectural Directive
        sections.append(
            "## Core Philosophy\n"
            "\"تا وقتی میشه با یک کد ساده تر به همون نتیجه رسید, نباید کد پیچیده ای نوشت\"\n"
            "Never over-engineer or write complex spaghetti abstractions when a simpler, direct, clean implementation achieves the exact same result."
        )

        # 3. Agent tool instructions
        sections.append(
            "## Tool Usage Instructions\n"
            "You have access to powerful tools to explore, read, edit, and execute code:\n"
            "- ALWAYS use `read_file` to inspect files before editing them.\n"
            "- Use `edit_file` for targeted changes (exact string replacement). Match whitespace exactly.\n"
            "- Use `write_file` only when creating new files or doing full rewrites.\n"
            "- Use `bash` to run tests, build tools, or inspect system state.\n"
            "- Use `file_search` and `content_search` to discover symbols and files.\n"
            "- Save persistent guidelines with `save_memory` when learning user preferences.\n"
            "- Load on-demand procedural skill instructions via `load_skill` when needed.\n"
            "- Be concise, direct, and verify your changes with tests."
        )

        # 4. Progressive Disclosure Skills Catalog (~15 tokens/skill)
        skills_index = self.skills.generate_compact_prompt_index()
        if skills_index:
            sections.append(skills_index)

        # 5. Persistent Auto-Memory Index
        memory_index = get_memory_index_text()
        if memory_index:
            sections.append(f"## Persistent Auto-Memory\n{memory_index}")

        # 6. Static Project Structure
        repo_ctx = self.repo.get_system_prompt_context()
        if repo_ctx:
            sections.append(repo_ctx)

        return "\n\n---\n\n".join(sections)

    def _build_messages(self) -> list[dict[str, Any]]:
        """Construct the complete message payload sent to the model API."""
        msgs: list[dict[str, Any]] = [
            {"role": "system", "content": self._frozen_system_prompt}
        ]
        msgs.extend(self.history)
        return msgs

    # ── Context Token Budget & Auto-Compaction ──────────────────────

    # Conservative char-to-token estimate (≈4 chars per token) used only
    # for compaction budgeting — never shown as usage telemetry.
    _CHARS_PER_TOKEN = 4
    # Fraction of the model's window at which auto-compaction triggers.
    _COMPACT_TRIGGER_FRACTION = 0.75

    def _estimate_tokens(self, msgs: list[dict[str, Any]]) -> int:
        """Return a conservative token estimate for a message list."""
        total_chars = 0
        for m in msgs:
            content = m.get("content", "")
            if isinstance(content, str):
                total_chars += len(content)
            tool_calls = m.get("tool_calls") or []
            for tc in tool_calls:
                fn = tc.get("function", {})
                total_chars += len(str(fn.get("name", "")))
                total_chars += len(str(fn.get("arguments", "")))
        total_chars += len(self._frozen_system_prompt)
        return max(1, total_chars // self._CHARS_PER_TOKEN)

    def _context_window(self) -> int:
        """Effective context window: explicit config or provider default."""
        explicit = self.config.get("context_window")
        if isinstance(explicit, int) and explicit > 0:
            return explicit
        # Conservative defaults per provider family; unknown models get 32k.
        model = str(self.config.get("model", "")).lower()
        if any(k in model for k in ("128k", "gpt-4o", "gpt-4-turbo", "deepseek")):
            return 128_000
        if any(k in model for k in ("200k", "claude", "sonnet", "opus")):
            return 200_000
        if any(k in model for k in ("32k", "mistral")):
            return 32_768
        return 32_768

    def _micro_compact(self):
        """Prune older tool outputs, preserving failure signals for the model."""
        tool_indices = [i for i, m in enumerate(self.history) if m.get("role") == "tool"]
        if len(tool_indices) <= 4:
            return

        # Indices to prune: all except the last 4
        to_prune = tool_indices[:-4]
        for idx in to_prune:
            msg = self.history[idx]
            content = str(msg.get("content", ""))
            name = msg.get("name", "tool")
            if len(content) > 200:
                lowered = content.lower()
                failed = lowered.startswith("error") or "error:" in lowered[:200] or "failed" in lowered[:200]
                tag = "FAILED — see error" if failed else "completed successfully"
                preview = content[:120].replace("\n", " ")
                msg["content"] = f"[Tool result pruned to conserve context: {name} {tag} — preview: {preview}…]"

    def _auto_compact(self):
        """Compact older turns into a user-role summary when over token budget.

        Uses a user-role block (not system) because many providers reject or
        misbehave with a second `role: system` message mid-conversation.
        """
        self._micro_compact()
        estimated = self._estimate_tokens(self.history)
        budget = int(self._context_window() * self._COMPACT_TRIGGER_FRACTION)
        # Message-count guard keeps behaviour sane when window is huge.
        if estimated < budget and len(self.history) < COMPACTION_THRESHOLD:
            return

        before_count = len(self.history)
        # Keep recent 8 messages, compact the older ones
        to_compact = self.history[:-8]
        recent = self.history[-8:]

        summary_lines = ["[Context compacted — summary of earlier turns:]"]
        for msg in to_compact:
            role = msg.get("role", "")
            content = msg.get("content", "")
            if role == "user":
                preview = content[:150].replace("\n", " ") if isinstance(content, str) else "(action)"
                summary_lines.append(f"- User asked: {preview}")
            elif role == "assistant" and content:
                preview = content[:150].replace("\n", " ") if isinstance(content, str) else "(tool calls)"
                summary_lines.append(f"- Assistant: {preview}")
            elif role == "assistant":
                calls = msg.get("tool_calls") or []
                names = ", ".join(tc.get("function", {}).get("name", "?") for tc in calls) or "?"
                summary_lines.append(f"- Assistant called tools: {names}")
            elif role == "tool":
                name = msg.get("name", "tool")
                text = str(content)
                lowered = text.lower()
                failed = lowered.startswith("error") or "error:" in lowered[:200] or "failed" in lowered[:200]
                preview = text[:120].replace("\n", " ") if isinstance(text, str) else ""
                status = f"FAILED — {preview}" if failed else "ok"
                summary_lines.append(f"- Tool '{name}' {status}.")
            elif role == "system":
                preview = str(content)[:120].replace("\n", " ") if isinstance(content, str) else ""
                summary_lines.append(f"- [prior summary] {preview}")

        summary_block = {
            "role": "user",
            "content": "\n".join(summary_lines),
        }

        self.history = [summary_block] + recent
        self.session.commit_compaction(before_count, len(self.history), "\n".join(summary_lines))
        render_compaction_notice(before_count, len(self.history), self._theme)

    def compact_now(self, keep_recent: int = 8) -> int:
        """Public manual compaction entry point (/compact). Returns messages removed."""
        before = len(self.history)
        if before <= keep_recent:
            return 0
        self._micro_compact()
        to_compact = self.history[:-keep_recent]
        recent = self.history[-keep_recent:]
        lines = ["[Manual compaction — summary of earlier turns:]"]
        for msg in to_compact:
            role = msg.get("role", "")
            content = str(msg.get("content", ""))
            lines.append(f"- {role or '?'}: {content[:150].replace(chr(10), ' ')}")
        summary_block = {"role": "user", "content": "\n".join(lines)}
        self.history = [summary_block] + recent
        removed = before - len(self.history)
        self.session.commit_compaction(before, len(self.history), "\n".join(lines))
        render_compaction_notice(before, len(self.history), self._theme)
        return removed

    # ── Agentic Dispatcher ──────────────────────────────────────────

    def send(self, user_input: str) -> str | None:
        """Process a user message through the agentic loop.

        Returns final assistant text, or None if cancelled/failed.
        """
        self.history.append({"role": "user", "content": user_input})
        self.session.commit_user_message(user_input)

        self._cancelled = False
        self._auto_compact()
        self._rotate_client()

        # Track turn timing (Grok Build style)
        turn_start = time.perf_counter()

        # The Agentic Tool Loop
        for iteration in range(MAX_TOOL_ITERATIONS):
            if self._cancelled:
                self._pop_failed_user_msg()
                return None

            messages = self._build_messages()
            schemas = self.tools.get_schemas()

            params: dict[str, Any] = {
                "model":       self.config["model"],
                "messages":    messages,
                "temperature": self.config["temperature"],
                "max_tokens":  self.config["max_tokens"],
                "tools":       schemas if schemas else None,
            }

            # Execute model call with rate-limit retry loop
            response = self._call_with_retry(params, turn_start=turn_start)
            if response is None:
                return None

            choice = response.choices[0]
            message = choice.message

            # Display thinking / reasoning if present (e.g. DeepSeek R1, OpenAI o1/o3)
            thought = getattr(message, "reasoning_content", None)
            if thought and not getattr(response, "thought_rendered", False):
                thought_elapsed = time.perf_counter() - turn_start
                render_thought(thought, self._theme, elapsed_secs=thought_elapsed)

            # Track tokens if provided by provider
            if response.usage:
                pt = response.usage.prompt_tokens or 0
                ct = response.usage.completion_tokens or 0
                self.tokens.add(pt, ct)

            # ── Check if the model wants to call tools ──
            if message.tool_calls:
                tc_dicts = [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {
                            "name": tc.function.name,
                            "arguments": tc.function.arguments,
                        },
                    }
                    for tc in message.tool_calls
                ]

                # PERSIST-BEFORE-EXECUTE: Commit assistant message + tool calls to transaction ledger
                self.session.commit_assistant_pre_execution(
                    content=message.content,
                    tool_calls=tc_dicts,
                    thought=thought,
                )
                self.history.append({
                    "role": "assistant",
                    "content": message.content or "",
                    "tool_calls": tc_dicts,
                })

                # SEGMENTED PARALLEL EXECUTION PLANNER
                batches = self.tools.plan_execution_batches(tc_dicts)

                for batch in batches:
                    if self._cancelled:
                        break

                    is_concurrent_read = (
                        len(batch) > 1
                        and all(self.tools.is_safe(tc["function"]["name"]) for tc in batch)
                    )

                    if is_concurrent_read:
                        # ⚡ Concurrent Read-Only Execution Phase
                        for tc in batch:
                            t_name = tc["function"]["name"]
                            raw_args = tc["function"]["arguments"]
                            try:
                                args = json.loads(raw_args) if raw_args else {}
                            except json.JSONDecodeError:
                                args = {}
                            args_str = ", ".join(f"{k}={repr(v)[:25]}" for k, v in args.items())
                            render_tool_start(t_name, args_str, self._theme, is_parallel=True)

                        start_t = time.perf_counter()
                        batch_results = self.tools.execute_batch(batch)
                        total_elapsed_ms = (time.perf_counter() - start_t) * 1000

                        for tc, tool_result in batch_results:
                            t_name = tc["function"]["name"]
                            tc_id = tc["id"]
                            summary = "completed"
                            if t_name == "read_file":
                                summary = f"read {tool_result.metadata.get('read', 0)} lines"
                            elif t_name == "file_search":
                                summary = f"{tool_result.metadata.get('count', 0)} files found"
                            elif t_name == "content_search":
                                summary = f"{tool_result.metadata.get('count', 0)} matches"

                            render_tool_result(t_name, tool_result.success, summary, self._theme, elapsed_ms=total_elapsed_ms)
                            self.session.commit_tool_result(tc_id, t_name, tool_result.output)
                            self.history.append({
                                "role": "tool",
                                "tool_call_id": tc_id,
                                "name": t_name,
                                "content": tool_result.output,
                            })

                    else:
                        # 🛡 Sequential Barrier Execution Phase (Mutating operations or isolated calls)
                        for tc in batch:
                            if self._cancelled:
                                break

                            tool_name = tc["function"]["name"]
                            raw_args = tc["function"]["arguments"]
                            try:
                                args = json.loads(raw_args) if raw_args else {}
                            except json.JSONDecodeError:
                                args = {}

                            args_summary = ", ".join(f"{k}={repr(v)[:30]}" for k, v in args.items())
                            if len(args_summary) > 60:
                                args_summary = args_summary[:57] + "..."

                            # Permission Gate Check
                            is_safe = self.tools.is_safe(tool_name)
                            can_run = is_safe or (tool_name in self.always_allow) or (self.permission_mode == "auto")

                            if not can_run:
                                perm = ask_permission(tool_name, args_summary or tool_name, self._theme)
                                if perm == "always":
                                    self.always_allow.add(tool_name)
                                    can_run = True
                                elif perm == "yes":
                                    can_run = True
                                else:
                                    can_run = False

                            if not can_run:
                                render_tool_result(tool_name, False, "denied by user", self._theme)
                                denial_msg = "Error: User denied permission to execute this tool."
                                self.session.commit_tool_result(tc["id"], tool_name, denial_msg)
                                self.history.append({
                                    "role": "tool",
                                    "tool_call_id": tc["id"],
                                    "name": tool_name,
                                    "content": denial_msg,
                                })
                                continue

                            # Execute tool with timing telemetry
                            render_tool_start(tool_name, args_summary, self._theme, is_parallel=False)
                            t0 = time.perf_counter()
                            tool_result: ToolResult = self.tools.execute(tool_name, args)
                            elapsed_ms = (time.perf_counter() - t0) * 1000

                            # Determine concise badge summary
                            if tool_name == "read_file":
                                summary = f"read {tool_result.metadata.get('read', 0)} lines"
                            elif tool_name == "edit_file":
                                summary = f"{tool_result.metadata.get('replacements', 1)} replaced"
                            elif tool_name == "write_file":
                                summary = f"{tool_result.metadata.get('action', 'wrote')} {tool_result.metadata.get('lines', 0)} lines"
                            elif tool_name == "bash":
                                summary = f"exit code {tool_result.metadata.get('returncode', 0)}"
                            else:
                                summary = "completed"

                            render_tool_result(tool_name, tool_result.success, summary, self._theme, elapsed_ms=elapsed_ms)

                            # Show syntax-highlighted diff if edit_file produced one
                            if tool_result.diff:
                                target = args.get("path", "file")
                                render_diff(tool_result.diff, f"Modified: {target}", self._theme)

                            # Commit tool result to ledger and history
                            self.session.commit_tool_result(tc["id"], tool_name, tool_result.output)
                            self.history.append({
                                "role": "tool",
                                "tool_call_id": tc["id"],
                                "name": tool_name,
                                "content": tool_result.output,
                            })

                            if tool_name == "save_memory" and tool_result.success:
                                self.refresh_system_prompt()

                # Loop back to let the LLM evaluate tool results and continue
                continue

            # ── No tool calls: Final response from model ──
            content = message.content or ""
            if content:
                self.session.commit_assistant_pre_execution(content=content)
                self.history.append({"role": "assistant", "content": content})
                turn_elapsed = time.perf_counter() - turn_start
                # Streaming path already rendered the full panel live; only
                # re-render static panel + metadata for non-streamed responses.
                if not getattr(response, "was_streamed", False):
                    render_ai_response(content, self._theme, turn_time=turn_elapsed)
                elif response.usage:
                    # Streamed path: usage available, print turn badge only.
                    pt = response.usage.prompt_tokens or 0
                    ct = response.usage.completion_tokens or 0
                    dim = self._theme["dim"]
                    console.print(f"  [{dim}][turn: {turn_elapsed:.1f}s][/]")
                if response.usage:
                    pt = response.usage.prompt_tokens or 0
                    ct = response.usage.completion_tokens or 0
                    render_token_info(pt, ct, self.tokens.total, self._theme)
                console.print()

            return content

        # Loop limit reached without final text
        warning = "Reached maximum tool iterations without completion."
        render_ai_response(warning, self._theme)
        return warning

    def _stream_completion(self, params: dict[str, Any], turn_start: float = 0.0) -> AssembledResponse | None:
        """Stream chat completion deltas with real-time markdown Live UI and cancellation."""
        stream_params = dict(params)
        stream_params["stream"] = True

        stream = self.client.chat.completions.create(**stream_params)

        accumulated_content = ""
        accumulated_thought = ""
        thought_rendered = False
        assembled_tcs: dict[int, AssembledToolCall] = {}
        prompt_tokens = 0
        completion_tokens = 0
        was_streamed = False

        spinner = make_spinner(self._theme, "thinking")

        try:
            with Live(spinner, console=console, refresh_per_second=12, transient=True):
                for chunk in stream:
                    if self._cancelled:
                        return None

                    if not chunk.choices:
                        if hasattr(chunk, "usage") and chunk.usage:
                            prompt_tokens = getattr(chunk.usage, "prompt_tokens", 0) or 0
                            completion_tokens = getattr(chunk.usage, "completion_tokens", 0) or 0
                        continue

                    choice = chunk.choices[0]
                    delta = choice.delta

                    # 1. Reasoning / Thinking deltas (DeepSeek R1, o1, etc.)
                    reasoning_delta = getattr(delta, "reasoning_content", None)
                    if reasoning_delta:
                        accumulated_thought += reasoning_delta
                        spinner.text = f" thinking ({len(accumulated_thought):,} chars)"

                    # 2. Tool calls deltas
                    tc_deltas = getattr(delta, "tool_calls", None)
                    if tc_deltas:
                        for tc in tc_deltas:
                            idx = getattr(tc, "index", 0)
                            if idx not in assembled_tcs:
                                assembled_tcs[idx] = AssembledToolCall(
                                    id=getattr(tc, "id", None) or "",
                                    function=AssembledFunction(),
                                )
                            entry = assembled_tcs[idx]
                            if getattr(tc, "id", None):
                                entry.id = tc.id
                            fn = getattr(tc, "function", None)
                            if fn:
                                if getattr(fn, "name", None):
                                    entry.function.name += fn.name
                                if getattr(fn, "arguments", None):
                                    entry.function.arguments += fn.arguments

                    # 3. Content deltas
                    content_delta = getattr(delta, "content", None)
                    if content_delta:
                        # First text token arrived: break out of spinner Live context
                        accumulated_content += content_delta
                        break
        except KeyboardInterrupt:
            self.cancel()
            self._pop_failed_user_msg()
            console.print(f"\n  [{self._theme['dim']}]cancelled by user[/]\n")
            return None

        if self._cancelled:
            self._pop_failed_user_msg()
            console.print(f"\n  [{self._theme['dim']}]cancelled by user[/]\n")
            return None

        # If reasoning finished and text content exists, render thought first
        if accumulated_thought and accumulated_content:
            elapsed = time.perf_counter() - turn_start if turn_start else None
            render_thought(accumulated_thought, self._theme, elapsed_secs=elapsed)
            thought_rendered = True

        # If we have content, stream the remaining chunks into Live markdown panel
        if accumulated_content:
            was_streamed = True
            try:
                with Live(
                    make_ai_response_panel(accumulated_content, self._theme),
                    console=console,
                    refresh_per_second=15,
                    transient=False,
                ) as live:
                    for chunk in stream:
                        if self._cancelled:
                            break
                        if not chunk.choices:
                            if hasattr(chunk, "usage") and chunk.usage:
                                prompt_tokens = getattr(chunk.usage, "prompt_tokens", 0) or 0
                                completion_tokens = getattr(chunk.usage, "completion_tokens", 0) or 0
                            continue

                        choice = chunk.choices[0]
                        delta = choice.delta
                        cd = getattr(delta, "content", None)
                        if cd:
                            accumulated_content += cd
                            live.update(make_ai_response_panel(accumulated_content, self._theme))
            except KeyboardInterrupt:
                self.cancel()
                self._pop_failed_user_msg()
                console.print(f"\n  [{self._theme['dim']}]cancelled by user[/]\n")
                return None
        else:
            # No content started yet, but stream might have more tool_call deltas
            try:
                for chunk in stream:
                    if self._cancelled:
                        break
                    if not chunk.choices:
                        if hasattr(chunk, "usage") and chunk.usage:
                            prompt_tokens = getattr(chunk.usage, "prompt_tokens", 0) or 0
                            completion_tokens = getattr(chunk.usage, "completion_tokens", 0) or 0
                        continue
                    delta = chunk.choices[0].delta
                    tc_deltas = getattr(delta, "tool_calls", None)
                    if tc_deltas:
                        for tc in tc_deltas:
                            idx = getattr(tc, "index", 0)
                            if idx not in assembled_tcs:
                                assembled_tcs[idx] = AssembledToolCall(
                                    id=getattr(tc, "id", None) or "",
                                    function=AssembledFunction(),
                                )
                            entry = assembled_tcs[idx]
                            if getattr(tc, "id", None):
                                entry.id = tc.id
                            fn = getattr(tc, "function", None)
                            if fn:
                                if getattr(fn, "name", None):
                                    entry.function.name += fn.name
                                if getattr(fn, "arguments", None):
                                    entry.function.arguments += fn.arguments
            except KeyboardInterrupt:
                self.cancel()
                self._pop_failed_user_msg()
                console.print(f"\n  [{self._theme['dim']}]cancelled by user[/]\n")
                return None

        if self._cancelled:
            self._pop_failed_user_msg()
            console.print(f"\n  [{self._theme['dim']}]cancelled by user[/]\n")
            return None

        # Build assembled message
        tc_list = [assembled_tcs[k] for k in sorted(assembled_tcs.keys())] if assembled_tcs else None
        msg = AssembledMessage(
            content=accumulated_content or None,
            tool_calls=tc_list,
            reasoning_content=accumulated_thought or None,
        )
        usage = AssembledUsage(prompt_tokens, completion_tokens) if (prompt_tokens or completion_tokens) else None
        resp = AssembledResponse(
            [AssembledChoice(msg)],
            usage=usage,
            was_streamed=was_streamed,
            thought_rendered=thought_rendered,
        )
        return resp

    def _call_with_retry(self, params: dict[str, Any], turn_start: float = 0.0) -> Any:
        """Call chat completion with automatic streaming deltas and rate limit retry loop."""
        spinner = make_spinner(self._theme, "thinking")
        should_stream = self.config.get("stream", True)

        for attempt in range(MAX_RETRIES + 1):
            if self._cancelled:
                return None

            # 1. Attempt real-time streaming if enabled
            if should_stream:
                try:
                    resp = self._stream_completion(params, turn_start=turn_start)
                    if resp is not None:
                        return resp
                    if self._cancelled:
                        return None
                except (RateLimitError, APIConnectionError):
                    # Let the outer handler process rate limits / connection drops
                    raise
                except Exception:
                    # Streaming failed (e.g. proxy or provider lacks SSE streaming support)
                    # Gracefully fall back to standard non-streaming request
                    pass

            # 2. Non-streaming fallback
            try:
                with Live(spinner, console=console, refresh_per_second=12, transient=True):
                    resp = self.client.chat.completions.create(**params)
                return resp

            except KeyboardInterrupt:
                self.cancel()
                self._pop_failed_user_msg()
                console.print(f"\n  [{self._theme['dim']}]cancelled by user[/]\n")
                return None

            except RateLimitError as e:
                if attempt < MAX_RETRIES:
                    wait = RETRY_BASE_DELAY * (2 ** attempt)
                    if hasattr(e, 'response') and e.response:
                        retry_after = e.response.headers.get("retry-after")
                        if retry_after:
                            try:
                                wait = int(retry_after)
                            except ValueError:
                                pass

                    d = self._theme["dim"]
                    for remaining in range(wait, 0, -1):
                        console.print(
                            f"\r  [{d}]rate limited · retrying in {remaining}s (attempt {attempt + 2}/{MAX_RETRIES + 1})[/]",
                            end="",
                        )
                        time.sleep(1)
                    console.print()
                    self._rotate_client()
                    continue
                else:
                    self._pop_failed_user_msg()
                    render_error_panel("Rate limited — all retries exhausted. Check your provider quotas.", self._theme)
                    return None

            except APIConnectionError as e:
                self._pop_failed_user_msg()
                render_error_panel(f"Connection failed — check base_url and network connection.\n{e}", self._theme)
                return None

            except APIError as e:
                self._pop_failed_user_msg()
                render_error_panel(f"API error ({e.status_code}): {e.message}", self._theme)
                return None

            except Exception as e:
                self._pop_failed_user_msg()
                render_error_panel(f"Unexpected error: {e}", self._theme)
                return None

        return None

    def _pop_failed_user_msg(self):
        if self.history and self.history[-1]["role"] == "user":
            self.history.pop()


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  Sub-Agent Ecosystem (Specialized Personas)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

SUB_AGENT_PERSONAS = {
    "architect": (
        "You are an elite Software Architect. Your mission is to analyze complex problems, "
        "design clean modular solutions, enforce SOLID principles, and produce step-by-step implementation roadmaps."
    ),
    "debugger": (
        "You are a master Debugging Specialist. Your goal is to systematically isolate root causes, "
        "analyze tracebacks, examine edge cases, and devise minimal, bulletproof fixes."
    ),
    "reviewer": (
        "You are a senior Code Reviewer. Audit the code for security vulnerabilities (OWASP top 10), "
        "performance bottlenecks, race conditions, and stylistic maintainability. Be strict and specific."
    ),
    "general": (
        "You are a focused Sub-Agent handling a dedicated task in an isolated context window."
    ),
}


class SubAgent:
    """Specialized agent running a task in its own isolated context window with tool access.

    Isolation guarantees:
      - Own in-memory message list; NEVER touches parent ``engine.history``
        or ``engine.session`` ledger (no persist-before-execute writes).
      - Scoped tool subset (read-only by default); mutating tools denied
        unless explicitly listed in ``sub_agent_tools`` config.
      - Bounded tool loop (``sub_agent_max_iterations``) + per-call
        ``sub_agent_max_tokens``.
      - Shares the parent TokenTracker and renders with the parent theme.
    """

    # Default scoped subset: read-only + recall + skill loading. Write/edit/
    # bash/save_memory are excluded — a sub-agent must not mutate the
    # workspace or long-term memory without explicit operator opt-in.
    DEFAULT_ALLOWED_TOOLS = frozenset({
        "read_file", "file_search", "content_search",
        "list_dir", "git_status", "recall_memory", "load_skill",
    })

    def __init__(self, engine: ChatEngine, persona: str = "general"):
        self.engine = engine
        self.config = engine.config
        self._theme = engine._theme
        self.persona_name = persona
        self.system_prompt = SUB_AGENT_PERSONAS.get(persona, SUB_AGENT_PERSONAS["general"])

        self.model = self.config.get("sub_agent_model") or self.config["model"]
        self.max_tokens = self.config.get("sub_agent_max_tokens", 2048)
        self.max_iterations = self.config.get("sub_agent_max_iterations", 6)

        configured = self.config.get("sub_agent_tools")
        if isinstance(configured, list) and configured:
            self.allowed_tools = frozenset(configured)
        else:
            self.allowed_tools = self.DEFAULT_ALLOWED_TOOLS

    def _filtered_schemas(self) -> list[dict[str, Any]] | None:
        """Return sanitized tool schemas restricted to the allowed subset."""
        schemas = self.engine.tools.get_schemas()
        filtered = [s for s in schemas if s.get("function", {}).get("name") in self.allowed_tools]
        return filtered or None

    def run(self, task: str, context: str = "") -> str | None:
        """Run a focused sub-agent task with optional context.

        Executes a bounded tool loop in an isolated message list and
        returns the final assistant text (or None on failure/cancel).
        """
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": self.system_prompt}
        ]

        if context:
            messages.append({"role": "user", "content": f"Context:\n{context}\n\nTask: {task}"})
        else:
            messages.append({"role": "user", "content": task})

        schemas = self._filtered_schemas()
        sub_prompt_tokens = 0
        sub_completion_tokens = 0
        last_content = ""

        spinner = make_spinner(self._theme, f"sub-agent ({self.persona_name}) working")

        try:
            for _iteration in range(max(1, self.max_iterations)):
                if self.engine._cancelled:
                    console.print(f"\n  [{self._theme['dim']}]sub-agent cancelled[/]\n")
                    return None

                with Live(spinner, console=console, refresh_per_second=12, transient=True):
                    resp = self.engine.client.chat.completions.create(
                        model=self.model,
                        messages=messages,
                        temperature=self.config["temperature"],
                        max_tokens=self.max_tokens,
                        tools=schemas,
                        stream=False,
                    )

                if not resp.choices:
                    render_error_panel("Sub-agent: empty response.", self._theme)
                    return last_content or None

                if resp.usage:
                    pt = resp.usage.prompt_tokens or 0
                    ct = resp.usage.completion_tokens or 0
                    sub_prompt_tokens += pt
                    sub_completion_tokens += ct
                    self.engine.tokens.add(pt, ct)

                message = resp.choices[0].message
                content = getattr(message, "content", None) or ""
                tool_calls = getattr(message, "tool_calls", None) or []
                if content:
                    last_content = content

                if not tool_calls:
                    label = f"sub-agent · {self.persona_name} · {self.model}"
                    if content:
                        render_sub_agent_response(content, label, self._theme)
                    render_token_info(
                        sub_prompt_tokens, sub_completion_tokens,
                        self.engine.tokens.total, self._theme,
                    )
                    console.print()
                    return content or last_content or None

                # ── Tool loop: execute scoped subset sequentially ──
                tc_dicts: list[dict[str, Any]] = []
                for tc in tool_calls:
                    fn = getattr(tc, "function", None)
                    tc_dicts.append({
                        "id": getattr(tc, "id", ""),
                        "type": "function",
                        "function": {
                            "name": getattr(fn, "name", "") or "",
                            "arguments": getattr(fn, "arguments", "") or "",
                        },
                    })

                messages.append({
                    "role": "assistant",
                    "content": content or "",
                    "tool_calls": tc_dicts,
                })

                for tc in tc_dicts:
                    tool_name = tc["function"]["name"]
                    raw_args = tc["function"]["arguments"]
                    try:
                        args = json.loads(raw_args) if raw_args else {}
                    except json.JSONDecodeError:
                        args = {}

                    if tool_name not in self.allowed_tools:
                        denial = (
                            f"Error: tool '{tool_name}' is not available to sub-agents. "
                            f"Allowed: {sorted(self.allowed_tools)}. "
                            "Complete the task with the available tools or answer directly."
                        )
                        render_tool_result(tool_name, False, "not in sub-agent scope", self._theme)
                        messages.append({
                            "role": "tool",
                            "tool_call_id": tc["id"],
                            "name": tool_name,
                            "content": denial,
                        })
                        continue

                    # Parent permission policy still applies to mutating tools
                    # when explicitly enabled via sub_agent_tools config.
                    is_safe = self.engine.tools.is_safe(tool_name)
                    can_run = (
                        is_safe
                        or (tool_name in self.engine.always_allow)
                        or (self.engine.permission_mode == "auto")
                    )
                    if not can_run:
                        args_summary = ", ".join(f"{k}={repr(v)[:30]}" for k, v in args.items())
                        perm = ask_permission(tool_name, args_summary or tool_name, self._theme)
                        if perm == "always":
                            self.engine.always_allow.add(tool_name)
                            can_run = True
                        elif perm == "yes":
                            can_run = True
                    if not can_run:
                        render_tool_result(tool_name, False, "denied by user", self._theme)
                        messages.append({
                            "role": "tool",
                            "tool_call_id": tc["id"],
                            "name": tool_name,
                            "content": "Error: User denied permission to execute this tool.",
                        })
                        continue

                    args_summary = ", ".join(f"{k}={repr(v)[:30]}" for k, v in args.items())
                    render_tool_start(tool_name, args_summary, self._theme, is_parallel=False)
                    t0 = time.perf_counter()
                    tool_result: ToolResult = self.engine.tools.execute(tool_name, args)
                    elapsed_ms = (time.perf_counter() - t0) * 1000
                    render_tool_result(tool_name, tool_result.success, "completed", self._theme, elapsed_ms=elapsed_ms)
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tc["id"],
                        "name": tool_name,
                        "content": tool_result.output,
                    })

            render_error_panel(
                f"Sub-agent reached max iterations ({self.max_iterations}) without a final answer.",
                self._theme,
            )
            return last_content or None

        except KeyboardInterrupt:
            self.engine.cancel()
            console.print(f"\n  [{self._theme['dim']}]sub-agent cancelled by user[/]\n")
            return None
        except Exception as e:
            render_error_panel(f"Sub-agent error: {e}", self._theme)
            return None
