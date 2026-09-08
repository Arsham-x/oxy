"""
OXY Session — Persist-Before-Execute transaction ledger and session durability manager.

Architectural Guarantees:
  1. Persist-Before-Execute: Model tool call requests are flushed to disk in an append-only
     JSONL transaction ledger BEFORE any tool side effect executes. If a tool crashes,
     is killed, or power drops, no conversation state is corrupted or lost.
  2. Transaction Recovery: Unmatched tool invocations (calls without corresponding results)
     are detected on startup, allowing clean recovery or continuation.
  3. Context Compaction: Provides clean message replay and sliding window serialization.
"""

from __future__ import annotations

import json
import os
import time
import uuid
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  Ledger Entry
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def _truncate_messages_to_prefix(
    messages: list[dict[str, Any]],
    target_id: str,
    payload: dict[str, Any],
) -> list[dict[str, Any]]:
    """Map a rewind marker to the visible message prefix.

    The ledger is append-only; nothing is deleted. The marker records where
    the operator asked to return to, identified either by entry id or by
    message count. Returns the truncated copy.
    """
    if not target_id and "message_count" in payload:
        try:
            count = int(payload.get("message_count", 0))
            return list(messages[: max(0, count)])
        except (TypeError, ValueError):
            return list(messages)
    # Entry-id markers are advisory: keep full history unless a count is given.
    # The engine drops pending tool calls separately via discard helpers.
    return list(messages)


@dataclass
class LedgerEntry:
    entry_id: str
    entry_type: str  # "system", "user", "assistant", "tool_result", "checkpoint", "rewind"
    timestamp: float
    payload: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.entry_id,
            "type": self.entry_type,
            "ts": self.timestamp,
            "payload": self.payload,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> LedgerEntry:
        return cls(
            entry_id=data.get("id", str(uuid.uuid4())[:8]),
            entry_type=data.get("type", "unknown"),
            timestamp=data.get("ts", time.time()),
            payload=data.get("payload", {}),
        )


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  Session Manager & Transaction Ledger
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class Session:
    """Represents an active or resumed OXY session backed by an append-only JSONL ledger."""

    def __init__(
        self,
        session_id: str | None = None,
        workspace_dir: str | Path | None = None,
        title: str = "New Session",
    ):
        self.workspace_dir = Path(workspace_dir or Path.cwd()).resolve()
        self.session_id = session_id or self._generate_session_id()
        self.title = title
        self.created_at = time.time()
        self.updated_at = self.created_at

        # Session storage directory
        self.storage_dir = self.workspace_dir / ".oxy" / "sessions"
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        self.ledger_file = self.storage_dir / f"{self.session_id}.jsonl"

        # In-memory turn list for LLM context
        self.messages: list[dict[str, Any]] = []
        self.pending_tool_calls: dict[str, dict[str, Any]] = {}

        if self.ledger_file.exists():
            self._replay_ledger()
        else:
            self._init_ledger()

    @staticmethod
    def _generate_session_id() -> str:
        """Generate human-friendly session ID (e.g. 2026-09-08-a1b2c3d4)."""
        date_str = datetime.now().strftime("%Y%m%d")
        rand_suffix = uuid.uuid4().hex[:8]
        return f"{date_str}-{rand_suffix}"

    def _append_entry(self, entry_type: str, payload: dict[str, Any]) -> LedgerEntry:
        """Atomically append a transaction entry to the JSONL ledger file."""
        entry = LedgerEntry(
            entry_id=uuid.uuid4().hex[:12],
            entry_type=entry_type,
            timestamp=time.time(),
            payload=payload,
        )
        line = json.dumps(entry.to_dict(), ensure_ascii=False) + "\n"
        with open(self.ledger_file, "a", encoding="utf-8") as f:
            f.write(line)
            f.flush()
            os.fsync(f.fileno())

        self.updated_at = entry.timestamp
        return entry

    def _init_ledger(self):
        """Write session initialization metadata header."""
        meta_payload = {
            "session_id": self.session_id,
            "title": self.title,
            "workspace": str(self.workspace_dir),
            "created_at": self.created_at,
        }
        self._append_entry("session_init", meta_payload)

    def _replay_ledger(self):
        """Replay transaction ledger from disk into memory."""
        self.messages = []
        self.pending_tool_calls = {}

        with open(self.ledger_file, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    data = json.loads(line)
                    entry = LedgerEntry.from_dict(data)
                except Exception:
                    continue

                t = entry.entry_type
                p = entry.payload

                if t == "session_init":
                    self.title = p.get("title", self.title)
                    self.created_at = p.get("created_at", self.created_at)

                elif t == "user_message":
                    msg = {"role": "user", "content": p.get("content", "")}
                    self.messages.append(msg)

                elif t == "assistant_turn":
                    # Assistant message containing thoughts, text, and/or tool_calls
                    msg = {"role": "assistant"}
                    if "content" in p and p["content"] is not None:
                        msg["content"] = p["content"]
                    if "tool_calls" in p and p["tool_calls"]:
                        msg["tool_calls"] = p["tool_calls"]
                        for tc in p["tool_calls"]:
                            tc_id = tc.get("id")
                            if tc_id:
                                self.pending_tool_calls[tc_id] = tc
                    self.messages.append(msg)

                elif t == "tool_result":
                    tc_id = p.get("tool_call_id")
                    if tc_id in self.pending_tool_calls:
                        del self.pending_tool_calls[tc_id]

                    msg = {
                        "role": "tool",
                        "tool_call_id": tc_id,
                        "name": p.get("name", ""),
                        "content": p.get("content", ""),
                    }
                    self.messages.append(msg)

                elif t == "compaction_checkpoint":
                    prior = p.get("summary", "") or p.get("summary_preview", "")
                    if prior:
                        self.messages.append({"role": "system", "content": prior})

                elif t == "rewind":
                    # Non-destructive rewind marker: hide turns after the target prefix.
                    target_id = p.get("rewind_to_entry_id", "")
                    self.messages = _truncate_messages_to_prefix(self.messages, target_id, p)

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    #  Transaction Durability Operations
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    def commit_user_message(self, content: str):
        """Record user input in transaction ledger."""
        self._append_entry("user_message", {"content": content})
        self.messages.append({"role": "user", "content": content})

    def commit_assistant_pre_execution(
        self,
        content: str | None,
        tool_calls: list[dict[str, Any]] | None = None,
        thought: str | None = None,
    ):
        """PERSIST-BEFORE-EXECUTE:

        Flushes the assistant message and all tool calls to disk BEFORE any tool executes.
        Guarantees that if a tool execution aborts or crashes the process,
        the model's requested actions are preserved on disk.
        """
        payload: dict[str, Any] = {}
        if content is not None:
            payload["content"] = content
        if tool_calls:
            payload["tool_calls"] = tool_calls
        if thought:
            payload["thought"] = thought

        self._append_entry("assistant_turn", payload)

        msg: dict[str, Any] = {"role": "assistant"}
        if content is not None:
            msg["content"] = content
        if tool_calls:
            msg["tool_calls"] = tool_calls
            for tc in tool_calls:
                tc_id = tc.get("id")
                if tc_id:
                    self.pending_tool_calls[tc_id] = tc

        self.messages.append(msg)

    def commit_tool_result(self, tool_call_id: str, tool_name: str, result_content: str):
        """Record tool execution result in ledger."""
        if tool_call_id in self.pending_tool_calls:
            del self.pending_tool_calls[tool_call_id]

        payload = {
            "tool_call_id": tool_call_id,
            "name": tool_name,
            "content": result_content,
        }
        self._append_entry("tool_result", payload)

        self.messages.append({
            "role": "tool",
            "tool_call_id": tool_call_id,
            "name": tool_name,
            "content": result_content,
        })

    def commit_compaction(self, before_count: int, after_count: int, summary: str):
        """Record context compaction checkpoint in the transaction ledger."""
        payload = {
            "before_count": before_count,
            "after_count": after_count,
            "summary_preview": summary[:200],
        }
        self._append_entry("compaction_checkpoint", payload)

    def has_unresolved_tool_calls(self) -> bool:
        """Check if any tool calls were dispatched without receiving results."""
        return len(self.pending_tool_calls) > 0

    def get_unresolved_tool_calls(self) -> list[dict[str, Any]]:
        """Return list of pending tool calls from crashed/interrupted turns."""
        return list(self.pending_tool_calls.values())

    def discard_unresolved_tool_calls(self) -> int:
        """Clear pending tool calls (e.g., after user declines recovery).
        Returns the number of discarded calls."""
        count = len(self.pending_tool_calls)
        self.pending_tool_calls.clear()
        return count

    def rewind_to_message_count(self, message_count: int) -> dict[str, Any]:
        """Append a non-destructive rewind marker and truncate in-memory history.

        The JSONL ledger is append-only: prior turns remain on disk for audit,
        but replay honors the latest rewind marker so resumed sessions show the
        rewound prefix. Returns a summary dict for command feedback.
        """
        before = len(self.messages)
        message_count = max(0, min(int(message_count), before))
        removed = before - message_count
        self._append_entry("rewind", {
            "message_count": message_count,
            "removed": removed,
            "before_count": before,
        })
        self.messages = list(self.messages[:message_count])
        # Drop pending dispatches that belonged to pruned turns.
        self.pending_tool_calls.clear()
        return {"before": before, "after": message_count, "removed": removed}

    def undo_last_turn(self) -> dict[str, Any]:
        """Remove the most recent user→assistant→tool exchange.

        Walks backwards past trailing tool/assistant messages to the last user
        message, then rewinds to just before it. Returns the rewind summary.
        If no user message exists, returns removed=0.
        """
        idx = len(self.messages) - 1
        while idx >= 0 and self.messages[idx].get("role") in ("tool", "assistant", "system"):
            idx -= 1
        if idx < 0 or self.messages[idx].get("role") != "user":
            return {"before": len(self.messages), "after": len(self.messages), "removed": 0}
        return self.rewind_to_message_count(idx)

    def get_context_messages(self, max_turns: int = 20) -> list[dict[str, Any]]:
        """Get sliding window of conversation messages for inference."""
        if not self.messages:
            return []

        # Ensure we don't slice in the middle of a tool call / tool result pair
        target_messages = self.messages[-max_turns:]

        # If the first message in the slice is a tool result, expand backwards to include the assistant call
        while target_messages and target_messages[0].get("role") == "tool":
            idx = self.messages.index(target_messages[0])
            if idx > 0:
                target_messages = self.messages[idx - 1 :]
            else:
                break

        return target_messages

    def export_markdown(self) -> str:
        """Export session dialogue as formatted Markdown."""
        lines = [
            f"# OXY Session: {self.title}",
            f"**Session ID:** `{self.session_id}`  ",
            f"**Created:** {datetime.fromtimestamp(self.created_at).strftime('%Y-%m-%d %H:%M:%S')}  ",
            f"**Workspace:** `{self.workspace_dir}`  ",
            "\n---\n",
        ]

        for m in self.messages:
            role = m.get("role", "unknown")
            content = m.get("content", "")
            if role == "user":
                lines.append(f"### 👤 User\n\n{content}\n")
            elif role == "assistant":
                lines.append(f"### ✦ OXY\n\n{content or ''}\n")
                if "tool_calls" in m:
                    lines.append("**Tool Calls:**")
                    for tc in m["tool_calls"]:
                        fn = tc.get("function", {})
                        lines.append(f"- `{fn.get('name')}`: `{fn.get('arguments')}`")
                    lines.append("")
            elif role == "tool":
                lines.append(f"**Tool Result ({m.get('name')}):**\n```\n{content}\n```\n")

        return "\n".join(lines)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  Session Registry
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class SessionRegistry:
    """Discovers, lists, and resumes past OXY sessions in workspace."""

    @staticmethod
    def get_storage_dir(workspace_dir: Path | str | None = None) -> Path:
        base = Path(workspace_dir or Path.cwd()).resolve()
        return base / ".oxy" / "sessions"

    @classmethod
    def list_sessions(cls, workspace_dir: Path | str | None = None) -> list[dict[str, Any]]:
        """List all saved sessions sorted by most recent activity."""
        sdir = cls.get_storage_dir(workspace_dir)
        if not sdir.exists():
            return []

        results = []
        for file in sdir.glob("*.jsonl"):
            session_id = file.stem
            mod_time = file.stat().st_mtime
            title = "Untitled Session"
            turn_count = 0

            # Read first line for title
            try:
                with open(file, "r", encoding="utf-8") as f:
                    for line in f:
                        turn_count += 1
                        if turn_count == 1:
                            data = json.loads(line)
                            p = data.get("payload", {})
                            title = p.get("title", title)
            except Exception:
                pass

            results.append({
                "id": session_id,
                "title": title,
                "path": str(file),
                "modified": mod_time,
                "turns": turn_count,
            })

        results.sort(key=lambda x: x["modified"], reverse=True)
        return results

    @classmethod
    def get_latest_session(cls, workspace_dir: Path | str | None = None) -> Session | None:
        """Load the most recently modified session in the current workspace."""
        sessions = cls.list_sessions(workspace_dir)
        if not sessions:
            return None
        latest_id = sessions[0]["id"]
        return Session(session_id=latest_id, workspace_dir=workspace_dir)
