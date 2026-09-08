"""
OXY Hooks — Deterministic lifecycle hooks system for agent extension.

Inspired by Git hooks and Claude Code lifecycle callbacks:
  - Events: session_start, pre_turn, pre_tool_call, post_tool_call, post_turn, session_end
  - Supports Python callable listeners and file-based scripts in .oxy/hooks/<event>
  - Exception boundary: Hook failures never crash the agent session.
"""

from __future__ import annotations

import json
import os
import subprocess
from enum import Enum
from pathlib import Path
from typing import Any, Callable


class HookEvent(str, Enum):
    SESSION_START = "session_start"
    PRE_TURN = "pre_turn"
    PRE_TOOL_CALL = "pre_tool_call"
    POST_TOOL_CALL = "post_tool_call"
    POST_TURN = "post_turn"
    SESSION_END = "session_end"


class HookResult:
    __slots__ = ("allow", "modified_data", "error", "output")

    def __init__(
        self,
        allow: bool = True,
        modified_data: dict[str, Any] | None = None,
        error: str | None = None,
        output: str = "",
    ):
        self.allow = allow
        self.modified_data = modified_data
        self.error = error
        self.output = output


class HookRegistry:
    """Manages lifecycle callbacks and workspace script hooks."""

    def __init__(self, workspace_dir: Path | str | None = None):
        self.workspace_dir = Path(workspace_dir or Path.cwd()).resolve()
        self.hooks_dir = self.workspace_dir / ".oxy" / "hooks"
        self._listeners: dict[HookEvent, list[Callable[..., Any]]] = {
            event: [] for event in HookEvent
        }

    def register(self, event: HookEvent | str, callback: Callable[..., Any]):
        """Register an in-memory Python callable for an event."""
        ev = HookEvent(event) if isinstance(event, str) else event
        self._listeners[ev].append(callback)

    def dispatch(self, event: HookEvent | str, **payload: Any) -> HookResult:
        """Dispatch event to in-memory listeners and executable disk hooks."""
        ev = HookEvent(event) if isinstance(event, str) else event
        modified = payload.copy()

        # 1. Run in-memory Python listeners
        for cb in self._listeners.get(ev, []):
            try:
                res = cb(**modified)
                if isinstance(res, dict):
                    modified.update(res)
                elif res is False:
                    return HookResult(allow=False, modified_data=modified, error=f"Blocked by hook {cb.__name__}")
            except Exception:
                # Never crash the agent on hook failure
                pass

        # 2. Run file-based shell hook if exists: .oxy/hooks/<event> or .oxy/hooks/<event>.sh
        script_candidates = [
            self.hooks_dir / ev.value,
            self.hooks_dir / f"{ev.value}.sh",
        ]
        for script in script_candidates:
            if script.exists() and os.access(script, os.X_OK):
                try:
                    proc = subprocess.run(
                        [str(script)],
                        input=json.dumps(modified),
                        text=True,
                        capture_output=True,
                        timeout=10,
                        cwd=self.workspace_dir,
                        env={**os.environ, "OXY_HOOK_EVENT": ev.value},
                    )
                    if proc.returncode != 0:
                        err_msg = proc.stderr.strip() or f"Hook script exited with code {proc.returncode}"
                        return HookResult(allow=False, error=err_msg, output=proc.stdout)
                except Exception:
                    pass

        return HookResult(allow=True, modified_data=modified)


# Global hook registry instance
hooks = HookRegistry()
