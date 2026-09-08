"""
OXY Input — prompt_toolkit setup with Grok Build-style status line and contextual hints.

Status line pattern (Grok Build inspired):
  model │ N turns │ N,NNN tokens │ M:SS │ mode │ /help

The prompt uses a clean ❯ chevron matching Grok Build's input style.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Callable

from prompt_toolkit import PromptSession
from prompt_toolkit.history import FileHistory
from prompt_toolkit.auto_suggest import AutoSuggestFromHistory
from prompt_toolkit.completion import WordCompleter
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.keys import Keys
from prompt_toolkit.formatted_text import HTML
from prompt_toolkit.styles import Style as PTStyle

from .config import HISTORY_FILE


# ── Slash commands for tab-completion ─────────────────────────────

SLASH_COMMANDS = [
    "/help",
    "/clear",
    "/system",
    "/model",
    "/history",
    "/save",
    "/config",
    "/tokens",
    "/copy",
    "/theme",
    "/keys",
    "/agent",
    "/tools",
    "/permissions",
    "/skills",
    "/sessions",
    "/resume",
    "/test",
    "/review",
    "/refactor",
    "/add",
    "/drop",
    "/files",
    "/git",
    "/memory",
    "/compact",
    "/quit",
    "/exit",
]


# ── Build prompt session ──────────────────────────────────────────

def make_prompt_session(theme: dict[str, Any]) -> PromptSession:
    """Build a prompt_toolkit session with key bindings, history, and auto-complete."""
    bindings = KeyBindings()

    @bindings.add(Keys.Enter)
    def _submit(event):
        event.current_buffer.validate_and_handle()

    @bindings.add(Keys.Escape, Keys.Enter)
    def _newline(event):
        event.current_buffer.insert_text("\n")

    completer = WordCompleter(SLASH_COMMANDS, sentence=True)

    style = PTStyle.from_dict({
        "prompt":         theme.get("prompt_style", "dim"),
        "bottom-toolbar": f"bg:{theme.get('toolbar_bg', '#1a1a1a')} {theme.get('toolbar_fg', '#888888')}",
    })

    return PromptSession(
        history=FileHistory(str(HISTORY_FILE)),
        auto_suggest=AutoSuggestFromHistory(),
        completer=completer,
        key_bindings=bindings,
        style=style,
        multiline=False,
        enable_open_in_editor=True,
    )


# ── Prompt Formatter ──────────────────────────────────────────────

def format_prompt(theme: dict[str, Any]) -> HTML:
    """Return the styled prompt prefix — clean ❯ chevron."""
    char = theme.get("prompt_char", "❯")
    return HTML(f"<b>{char}</b> ")


# ── Status Line (Grok Build inspired) ────────────────────────────

def make_toolbar(
    model: str,
    msg_count: int,
    max_history: int,
    token_total: int,
    start_time: datetime,
    theme_name: str,
    rr_active: bool,
    active_files_count: int = 0,
    memory_count: int = 0,
    permission_mode: str = "ask",
) -> Callable:
    """Return a callable that generates the Grok Build-style status line.

    Layout: model │ turns │ tokens │ timer │ mode │ files │ /help
    """
    def _toolbar():
        elapsed = datetime.now() - start_time
        mins = int(elapsed.total_seconds()) // 60
        secs = int(elapsed.total_seconds()) % 60

        parts = [
            f" <b>{model}</b>",
            f"{msg_count} turns",
            f"{token_total:,} tok",
            f"{mins}:{secs:02d}",
        ]

        # Mode indicator
        if permission_mode == "auto":
            parts.append("<style bg='#1a3a1a' fg='#44cc44'>auto</style>")
        else:
            parts.append("ask")

        if active_files_count > 0:
            parts.append(f"{active_files_count} files")

        if memory_count > 0:
            parts.append(f"{memory_count} mem")

        if rr_active:
            parts.append("⟳ rr")

        parts.append("<i>/help</i>")
        return HTML("  │  ".join(parts))

    return _toolbar
