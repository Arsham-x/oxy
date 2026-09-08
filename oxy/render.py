"""
OXY Render — Themes, response rendering, tool display, and terminal UI components.

Inspired by Grok Build's production-quality terminal interface:
  - Status diamonds (◆) for thinking with elapsed time
  - Turn metadata badges [turn: Xs, ↕Nk]
  - Clean tool execution display with timing telemetry
  - Compact mode for denser layouts
  - Three themes: minimal, cyber, aurora
"""

from __future__ import annotations

import time
import os
from typing import Any
from pathlib import Path

from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.text import Text
from rich.table import Table
from rich.live import Live
from rich.spinner import Spinner
from rich.rule import Rule
from rich.syntax import Syntax
from rich.columns import Columns
from rich import box

console = Console()


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  Theme definitions
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

THEMES: dict[str, dict[str, Any]] = {
    "minimal": {
        "name":           "Minimal",
        "user_style":     "bold",
        "ai_title":       "[dim]oxy[/]",
        "ai_border":      "dim",
        "ai_box":         box.SIMPLE,
        "system_style":   "dim italic",
        "error_style":    "red",
        "dim":            "dim",
        "accent":         "blue",
        "success":        "green",
        "warning":        "yellow",
        "spinner":        "dots",
        "spinner_style":  "dim",
        "prompt_char":    "❯",
        "prompt_style":   "dim",
        "toolbar_bg":     "#1a1a1a",
        "toolbar_fg":     "#888888",
        "welcome_border": "dim",
        "welcome_box":    box.SIMPLE,
        "rule_style":     "dim",
        "sub_agent":      "dim italic",
        "tool_icon":      "●",
        "think_icon":     "◆",
    },
    "cyber": {
        "name":           "Cyber",
        "user_style":     "bold cyan",
        "ai_title":       "[bold green]⟫ OXY[/]",
        "ai_border":      "green",
        "ai_box":         box.DOUBLE,
        "system_style":   "bold yellow",
        "error_style":    "bold red",
        "dim":            "bright_black",
        "accent":         "cyan",
        "success":        "green",
        "warning":        "yellow",
        "spinner":        "dots12",
        "spinner_style":  "cyan",
        "prompt_char":    "❯",
        "prompt_style":   "bold cyan",
        "toolbar_bg":     "#0a0a2e",
        "toolbar_fg":     "#00ff88",
        "welcome_border": "cyan",
        "welcome_box":    box.DOUBLE,
        "rule_style":     "cyan",
        "sub_agent":      "bold magenta",
        "tool_icon":      "●",
        "think_icon":     "◆",
    },
    "aurora": {
        "name":           "Aurora",
        "user_style":     "bold #e0b0ff",
        "ai_title":       "[bold #7fdbca]✦ oxy[/]",
        "ai_border":      "#7fdbca",
        "ai_box":         box.ROUNDED,
        "system_style":   "#f0c674",
        "error_style":    "#ff6b6b",
        "dim":            "#666680",
        "accent":         "#c792ea",
        "success":        "#7fdbca",
        "warning":        "#f0c674",
        "spinner":        "moon",
        "spinner_style":  "#7fdbca",
        "prompt_char":    "❯",
        "prompt_style":   "#c792ea",
        "toolbar_bg":     "#1e1e3f",
        "toolbar_fg":     "#7fdbca",
        "welcome_border": "#c792ea",
        "welcome_box":    box.ROUNDED,
        "rule_style":     "#7fdbca",
        "sub_agent":      "italic #c792ea",
        "tool_icon":      "●",
        "think_icon":     "◆",
    },
}


def get_theme(name: str) -> dict[str, Any]:
    return THEMES.get(name, THEMES["minimal"])


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  Spinner
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def make_spinner(theme: dict[str, Any], text: str = "thinking") -> Spinner:
    return Spinner(theme["spinner"], text=f" {text}", style=theme["spinner_style"])


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  Welcome screen
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def print_welcome(config: dict[str, Any], theme: dict[str, Any], engine: Any = None):
    """Print a clean, professional welcome dashboard."""
    console.print()

    accent = theme.get("accent", "cyan")
    dim = theme.get("dim", "dim")

    # Header — centered OXY banner
    from .ui import render_cockpit_header
    render_cockpit_header(theme, animated=False)

    # Resolve provider display
    base = config.get("base_url", "")
    if "api.openai.com" in base:
        prov = "OpenAI"
    elif "deepseek" in base:
        prov = "DeepSeek"
    elif "groq" in base:
        prov = "Groq"
    elif "openrouter" in base:
        prov = "OpenRouter"
    elif "together" in base:
        prov = "Together AI"
    elif "localhost" in base or "127.0.0.1" in base:
        prov = "Local"
    else:
        prov = base.replace("https://", "").replace("http://", "").split("/")[0] or "Custom"

    key_display = _mask_key(config.get("api_key", ""))

    # ── Panel 1: Engine ──
    t1 = Table.grid(padding=(0, 2))
    t1.add_column(style=dim, justify="right")
    t1.add_column(style="bold white")

    t1.add_row("provider", prov)
    t1.add_row("model", config.get("model", "default"))
    t1.add_row("key", key_display)
    t1.add_row("history", f"{config.get('max_history', 20)} turns")

    tool_count = len(engine.tools.get_schemas()) if engine and hasattr(engine, "tools") else 9
    perm_mode = getattr(engine, "permission_mode", "ask") if engine else "ask"
    gate_style = "yellow" if perm_mode == "ask" else "green"

    t1.add_row("tools", f"[bold green]{tool_count} active[/]")
    t1.add_row("security", f"[{gate_style}]{perm_mode}[/]")

    p1 = Panel(
        t1,
        title=f"[bold {accent}]Engine[/]",
        border_style=theme.get("ai_border", "cyan"),
        box=theme.get("welcome_box", box.ROUNDED),
        padding=(0, 1),
    )

    # ── Panel 2: Workspace ──
    t2 = Table.grid(padding=(0, 2))
    t2.add_column(style=dim, justify="right")
    t2.add_column(style="bold white")

    if engine and hasattr(engine, "repo"):
        ws_name = engine.repo.root.name
        if engine.repo.is_git:
            t2.add_row("repo", f"[cyan]{ws_name}[/] [{dim}]({engine.repo.branch})[/]")
        else:
            t2.add_row("workspace", ws_name)
        active_count = len(engine.repo.active_files)
        t2.add_row("files", f"{active_count}" if active_count else f"[{dim}]none[/]")
    else:
        t2.add_row("workspace", Path.cwd().name)

    from .memory import list_memories
    mem_count = len(list_memories())
    t2.add_row("memory", f"{mem_count} items" if mem_count else f"[{dim}]0[/]")

    prompt_chars = len(getattr(engine, "system_prompt", "")) if engine else 0
    t2.add_row("persona", f"{prompt_chars:,} chars" if prompt_chars else f"[{dim}]inline[/]")
    t2.add_row("theme", theme.get("name", "Minimal"))

    if config.get("round_robin") and config.get("round_robin_keys"):
        t2.add_row("round-robin", f"[bold cyan]{len(config['round_robin_keys'])} keys[/]")

    p2 = Panel(
        t2,
        title=f"[bold {accent}]Context[/]",
        border_style=theme.get("welcome_border", "cyan"),
        box=theme.get("welcome_box", box.ROUNDED),
        padding=(0, 1),
    )

    console.print(Columns([p1, p2], equal=True))

    # ── Hint bar ──
    console.print(
        f"  [{dim}]Enter[/] send   "
        f"[{dim}]Alt+Enter[/] newline   "
        f"[{dim}]Ctrl+C[/] cancel   "
        f"[{dim}]/help[/] commands   "
        f"[{dim}]/tools[/] {tool_count} tools"
    )
    console.print()


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  AI response rendering
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def render_ai_response(text: str, theme: dict[str, Any], turn_time: float | None = None):
    """Render an AI response with markdown inside a themed panel."""
    from .ui import reshape_markdown
    formatted_text = reshape_markdown(text)
    md = Markdown(formatted_text)

    # Build title with optional turn timing
    title = theme["ai_title"]

    console.print(Panel(
        md,
        title=title,
        title_align="left",
        border_style=theme["ai_border"],
        box=theme["ai_box"],
        padding=(0, 1),
    ))

    # Turn metadata badge (Grok Build style)
    if turn_time is not None:
        dim = theme["dim"]
        console.print(f"  [{dim}][turn: {turn_time:.1f}s][/]")


def render_sub_agent_response(text: str, label: str, theme: dict[str, Any]):
    """Render a sub-agent response."""
    from .ui import reshape_markdown
    formatted_text = reshape_markdown(text)
    md = Markdown(formatted_text)
    title = f"[{theme['sub_agent']}]⤷ {label}[/]"
    console.print(Panel(
        md,
        title=title,
        title_align="left",
        border_style=theme["dim"],
        box=box.SIMPLE,
        padding=(0, 1),
    ))


def render_diff(diff_text: str, title: str = "Diff", theme: dict[str, Any] | None = None):
    """Render a syntax-highlighted unified diff."""
    if not diff_text.strip():
        return
    syntax = Syntax(diff_text, "diff", theme="monokai", line_numbers=True)
    border = theme["accent"] if theme else "cyan"
    console.print(Panel(
        syntax,
        title=f"[bold {border}]Δ {title}[/]",
        title_align="left",
        border_style=border,
        box=box.ROUNDED,
        padding=(0, 1),
    ))
    console.print()


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  Tool execution display (Grok Build inspired)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def render_tool_start(name: str, args_summary: str, theme: dict[str, Any], is_parallel: bool = False):
    """Render tool start indicator with clean badge."""
    accent = theme.get("accent", "cyan")
    dim = theme.get("dim", "dim")
    icon = theme.get("tool_icon", "●")

    parallel_tag = f" [{dim}]⚡[/]" if is_parallel else ""
    args_display = f" [{dim}]{args_summary}[/]" if args_summary else ""

    console.print(f"  [{accent}]{icon}[/]{parallel_tag} [{theme.get('user_style', 'bold')}]{name}[/]{args_display}")


def render_tool_result(name: str, success: bool, summary: str, theme: dict[str, Any], elapsed_ms: float | None = None):
    """Render tool completion with status and timing."""
    icon = "[green]✔[/]" if success else "[red]✖[/]"
    style = "green" if success else "red"
    dim = theme.get("dim", "dim")
    ms_tag = f" [{dim}]{elapsed_ms:.0f}ms[/]" if elapsed_ms is not None else ""
    console.print(f"  {icon} [{style}]{name}[/] [{dim}]· {summary}[/]{ms_tag}")


def ask_permission(tool_name: str, summary: str, theme: dict[str, Any]) -> str:
    """Ask interactive user permission for tool execution."""
    console.print()
    border = theme.get("warning", "yellow")
    prompt_text = (
        f"[bold {border}]Allow this action?[/]\n"
        f"  [{theme.get('accent', 'cyan')}]{tool_name}[/] · {summary}\n\n"
        f"  [green]y[/]es  [red]n[/]o  [yellow]a[/]lways"
    )
    console.print(Panel(
        prompt_text,
        title="[bold yellow]🛡 Permission[/]",
        border_style="yellow",
        box=box.ROUNDED,
        padding=(0, 1),
    ))
    try:
        choice = console.input("  ❯ ").strip().lower()
    except (KeyboardInterrupt, EOFError):
        console.print()
        return "no"

    if choice in ("y", "yes", "بله", "آره"):
        return "yes"
    if choice in ("a", "always", "همیشه"):
        return "always"
    return "no"


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  Thinking / reasoning display (Grok Build ◆ style)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def render_thought(thought_text: str, theme: dict[str, Any], elapsed_secs: float | None = None):
    """Render model reasoning with Grok Build diamond indicator and elapsed time."""
    if not thought_text.strip():
        return
    dim = theme.get("dim", "dim")
    accent = theme.get("accent", "cyan")
    icon = theme.get("think_icon", "◆")

    length = len(thought_text)
    preview = thought_text if length <= 300 else thought_text[:300] + "..."

    # Header with elapsed time (Grok Build: ◆Thought for 3.8s)
    if elapsed_secs is not None:
        header = f"[{accent}]{icon}[/] [{dim}]Thought for {elapsed_secs:.1f}s ({length:,} chars)[/]"
    else:
        header = f"[{accent}]{icon}[/] [{dim}]Thought ({length:,} chars)[/]"

    console.print(f"\n  {header}")
    console.print(Panel(
        f"[{dim} italic]{preview}[/]",
        border_style=dim,
        box=box.SIMPLE,
        padding=(0, 1),
    ))


def render_compaction_notice(before_turns: int, after_turns: int, theme: dict[str, Any]):
    """Render context compaction notification."""
    dim = theme.get("dim", "dim")
    accent = theme.get("accent", "cyan")
    console.print(f"\n  [{accent}]⟳[/] [{dim}]Context compacted: {before_turns} → {after_turns} messages[/]\n")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  Token display
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def render_token_info(prompt_tok: int, compl_tok: int, total_session: int, theme: dict[str, Any]):
    """Render inline token usage."""
    d = theme["dim"]
    console.print(f"  [{d}]{prompt_tok:,} + {compl_tok:,} = {prompt_tok + compl_tok:,}  ·  session: {total_session:,}[/]")


def render_token_table(tracker, theme: dict[str, Any]):
    """Render full token usage table."""
    t = Table(box=box.SIMPLE_HEAVY, show_edge=False, pad_edge=False)
    t.add_column("metric", style=theme["accent"])
    t.add_column("count", style="white", justify="right")
    t.add_row("prompt tokens",     f"{tracker.total_prompt:,}")
    t.add_row("completion tokens", f"{tracker.total_complete:,}")
    t.add_row("total tokens",      f"[bold]{tracker.total:,}[/]")
    t.add_row("turns",             f"{tracker.turns}")
    console.print(t)
    console.print()


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  Error display
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def render_error(message: str, theme: dict[str, Any]):
    console.print(f"  [{theme['error_style']}]✖ {message}[/]")
    console.print()


def render_error_panel(message: str, theme: dict[str, Any]):
    console.print(Panel(
        message,
        title=f"[{theme['error_style']}]error[/]",
        title_align="left",
        border_style=theme["error_style"],
        box=box.ROUNDED,
        padding=(0, 1),
    ))
    console.print()


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  Goodbye screen
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def print_goodbye(msg_count: int, token_total: int, elapsed_secs: float, theme: dict[str, Any]):
    """Print goodbye with session stats."""
    mins = int(elapsed_secs) // 60
    secs = int(elapsed_secs) % 60
    d = theme["dim"]

    console.print()
    console.print(Rule(style=theme["rule_style"]))
    console.print(f"  [{d}]{msg_count} turns  ·  {token_total:,} tokens  ·  {mins}:{secs:02d}[/]")
    console.print(f"  [{d}]goodbye[/]")
    console.print()


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  System / info messages
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def render_info(message: str, theme: dict[str, Any]):
    console.print(f"  [{theme['system_style']}]{message}[/]")
    console.print()


def render_system_prompt(prompt: str, theme: dict[str, Any]):
    length = len(prompt)
    display = prompt if length <= 500 else prompt[:500] + f"\n\n[{theme['dim']}]… {length:,} chars total[/]"
    console.print(Panel(
        display,
        title=f"[{theme['system_style']}]system prompt[/]  [{theme['dim']}]{length:,} chars[/]",
        title_align="left",
        border_style=theme["system_style"],
        box=box.ROUNDED,
    ))
    console.print()


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  Helpers
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def _mask_key(key: str) -> str:
    if not key:
        return "[red]NOT SET[/]"
    if len(key) > 12:
        return key[:4] + "..." + key[-4:]
    return "****"
