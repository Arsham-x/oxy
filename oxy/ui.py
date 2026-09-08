"""
OXY UI — Interactive terminal controls, keyboard-driven selection, and clean international typography.

Provides:
  - select_menu: rock-solid, flicker-free arrow-key selector (↑/↓/Enter/1-9) with ANSI in-place rewriting
  - PersianFormatter: clean Persian/Arabic text formatter preserving standard Unicode ligatures
  - render_stepper: sleek breadcrumb progress gauge inspired by Claude Code and Hermes
  - render_cockpit_header: high-tech ASCII banners (Cyber, Aurora, Minimal)
"""

from __future__ import annotations

import os
import re
import sys
import shutil
from typing import Any

from rich.console import Console
from rich.panel import Panel
from rich.text import Text
from rich import box

try:
    import arabic_reshaper
    from bidi.algorithm import get_display as bidi_get_display
    HAS_BIDI = True
except ImportError:
    HAS_BIDI = False

console = Console()


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  Persian & RTL Typography Engine
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class PersianFormatter:
    """Handles Persian text cleanly for modern terminals.

    Modern Linux terminals (KDE Konsole, GNOME Terminal, Ptyxis, Alacritty)
    and macOS/Windows terminals have built-in HarfBuzz/Qt/CoreText font
    shaping engines. They connect standard Arabic/Persian Unicode codepoints
    (U+0600..U+06FF) into cursive ligatures natively.

    Converting characters to Presentation Form B (arabic_reshaper) forces
    terminals to treat them as isolated monospace glyphs, causing spaced-out
    letters. Therefore, 'native' mode leaves standard Unicode intact.
    """

    @staticmethod
    def is_persian(text: str) -> bool:
        """Check if string contains Persian/Arabic characters."""
        return any(
            '؀' <= c <= 'ۿ' or
            'ݐ' <= c <= 'ݿ' or
            'ﭐ' <= c <= '﷿' or
            'ﹰ' <= c <= '﻿'
            for c in text
        )

    @classmethod
    def format(cls, text: str, mode: str = "native") -> str:
        """Format Persian text.

        Modes:
          - 'native': preserves standard Unicode codepoints (recommended for modern terminals)
          - 'bidi': reshapes and reverses visual order for LTR-only terminal emulators
          - 'force_reshape': connects letters into Presentation Form B
        """
        if mode == "native" or not cls.is_persian(text):
            return text

        if mode == "bidi" and HAS_BIDI:
            # Protect Rich markup tags
            tag_regex = re.compile(r'(\[/?[a-zA-Z0-9_# \-.:]+\])')
            tokens = tag_regex.split(text)
            processed = []
            for token in tokens:
                if tag_regex.match(token) or not token:
                    processed.append(token)
                else:
                    reshaped = arabic_reshaper.reshape(token)
                    processed.append(bidi_get_display(reshaped))
            return "".join(processed)

        if mode == "force_reshape" and HAS_BIDI:
            tag_regex = re.compile(r'(\[/?[a-zA-Z0-9_# \-.:]+\])')
            tokens = tag_regex.split(text)
            processed = []
            for token in tokens:
                if tag_regex.match(token) or not token:
                    processed.append(token)
                else:
                    processed.append(arabic_reshaper.reshape(token))
            return "".join(processed)

        return text


def p(text: str, mode: str = "native") -> str:
    """Shorthand for PersianFormatter.format."""
    return PersianFormatter.format(text, mode=mode)


def reshape_markdown(md_text: str) -> str:
    """Format markdown text preserving code blocks and syntax."""
    return md_text


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  Interactive Arrow-Key Selector (In-Place ANSI Engine)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def _read_key() -> str:
    """Read a single keypress in raw mode on POSIX systems."""
    import tty
    import termios

    fd = sys.stdin.fileno()
    old = termios.tcgetattr(fd)
    try:
        tty.setraw(fd)
        ch = sys.stdin.read(1)
        if ch == '\x1b':
            # Handle escape sequences with short non-blocking lookahead
            import select
            r, _, _ = select.select([sys.stdin], [], [], 0.05)
            if r:
                ch2 = sys.stdin.read(1)
                if ch2 == '[':
                    ch3 = sys.stdin.read(1)
                    if ch3 == 'A': return 'up'
                    if ch3 == 'B': return 'down'
                    if ch3 == 'C': return 'right'
                    if ch3 == 'D': return 'left'
            return 'esc'
        elif ch in ('\r', '\n'):
            return 'enter'
        elif ch == ' ':
            return 'enter'
        elif ch in ('k', 'K'):
            return 'up'
        elif ch in ('j', 'J'):
            return 'down'
        elif ch == '\x03':  # Ctrl+C
            raise KeyboardInterrupt()
        elif ch in ('q', 'Q'):
            return 'q'
        return ch
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old)


def select_menu(
    title: str,
    options: list[tuple[str, str]],
    default: int = 0,
    theme: dict[str, Any] | None = None,
    help_hint: str | None = None,
    step_info: str | None = None,
) -> int:
    """Rock-solid, flicker-free arrow-key selector with in-place ANSI rewriting.

    Zero screen duplication, zero background thread races.
    Operates identically to Claude Code and Hermes Agent selection prompts.

    Arguments:
      title: Header text for the prompt
      options: List of (Label, Description) tuples
      default: Initially selected index
      theme: OXY theme dictionary
      help_hint: Optional footer tip
      step_info: Optional step prefix (e.g. "Step 1/5")

    Returns:
      Selected index (0-based)
    """
    # Non-interactive fallback
    if not sys.stdin.isatty():
        return default

    theme = theme or {}
    theme_name = theme.get("name", "Cyber").lower()

    # ANSI Color Codes
    if theme_name == "cyber":
        accent = "\033[1;36m"    # Bold Cyan
        cursor_color = "\033[1;32m" # Bold Green
        dim = "\033[2m"
        white = "\033[1;37m"
        ok_color = "\033[1;32m"
    elif theme_name == "aurora":
        accent = "\033[1;35m"    # Bold Magenta/Purple
        cursor_color = "\033[1;36m" # Bold Teal
        dim = "\033[2m"
        white = "\033[1;37m"
        ok_color = "\033[1;35m"
    else:  # Minimal
        accent = "\033[1;34m"    # Bold Blue
        cursor_color = "\033[1m"
        dim = "\033[2m"
        white = "\033[1;37m"
        ok_color = "\033[1;32m"

    reset = "\033[0m"

    current = max(0, min(default, len(options) - 1))
    cols = shutil.get_terminal_size((80, 24)).columns

    def build_lines(idx: int) -> list[str]:
        lines = []
        # Header line
        step_prefix = f"{dim}[{step_info}]{reset} " if step_info else ""
        header = f"  {accent}?{reset} {step_prefix}{white}{title}{reset} {dim}(↑/↓ navigate, Enter confirm){reset}"
        lines.append(header)

        # Options
        for i, (label, desc) in enumerate(options):
            pad = max(2, 22 - len(label))
            if i == idx:
                line = f"  {cursor_color}❯{reset} {white}{label}{reset}{' ' * pad} {accent}{desc}{reset}"
            else:
                line = f"    {dim}{label}{' ' * pad} {desc}{reset}"
            lines.append(line)

        # Footer hint
        hint = help_hint or "↑/↓ navigate · Enter select · 1-9 direct jump"
        lines.append(f"  {dim}↳ {hint}{reset}")
        return lines

    # Hide cursor
    sys.stdout.write("\033[?25l")
    sys.stdout.flush()

    lines = build_lines(current)
    line_count = len(lines)

    # Initial render
    for line in lines:
        sys.stdout.write(f"\033[2K{line}\r\n")
    sys.stdout.flush()

    try:
        while True:
            try:
                key = _read_key()
            except KeyboardInterrupt:
                sys.stdout.write(f"\033[{line_count}A\r\033[0J")
                sys.stdout.write("\033[?25h\r\n")
                sys.stdout.flush()
                raise SystemExit(0)

            if key == "up":
                current = (current - 1) % len(options)
            elif key == "down":
                current = (current + 1) % len(options)
            elif key == "enter":
                break
            elif key.isdigit() and 1 <= int(key) <= len(options):
                current = int(key) - 1
                break
            elif key in ("esc", "q"):
                break

            # In-place redraw: move cursor up line_count lines and rewrite each line
            new_lines = build_lines(current)
            sys.stdout.write(f"\033[{line_count}A\r")
            for line in new_lines:
                sys.stdout.write(f"\033[2K{line}\r\n")
            sys.stdout.flush()

    finally:
        # Clear menu lines completely and print clean confirmation badge
        sys.stdout.write(f"\033[{line_count}A\r\033[0J")
        chosen_label, _ = options[current]
        sys.stdout.write(f"  {ok_color}✔{reset} {white}{title}{reset} {dim}›{reset} {accent}{chosen_label}{reset}\r\n\r\n")
        # Restore cursor
        sys.stdout.write("\033[?25h")
        sys.stdout.flush()

    return current


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  Glowing Visual Stepper (Hermes & Claude Code Inspired)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def render_stepper(current_step: int, total_steps: int, title: str, theme: dict[str, Any] | None = None):
    """Render a clean breadcrumb progress indicator across setup steps."""
    theme = theme or {}
    accent = theme.get("accent", "cyan")
    dim = theme.get("dim", "dim")

    bar_parts = []
    for step in range(1, total_steps + 1):
        if step < current_step:
            bar_parts.append(f"[{accent}]●[/]")
            bar_parts.append(f"[{accent}]━━━[/]")
        elif step == current_step:
            bar_parts.append(f"[bold white on {accent}] {step} [/]")
            if step < total_steps:
                bar_parts.append(f"[{dim}]━━━[/]")
        else:
            bar_parts.append(f"[{dim}]○[/]")
            if step < total_steps:
                bar_parts.append(f"[{dim}]━━━[/]")

    gauge = "".join(bar_parts)
    console.print(f"  {gauge}  [{accent}]Step {current_step}/{total_steps}:[/] [bold white]{title}[/]")
    console.print()


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  Cockpit Header
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

BANNER_CYBER = """
[bold cyan]  ██████╗ ██╗  ██╗██╗   ██╗[/]   [bold #00ff88]✦ O X Y  A G E N T ✦[/]
 [bold cyan]██╔═══██╗╚██╗██╔╝╚██╗ ██╔╝[/]   [dim bright_white]Autonomous Coding Assistant[/]
 [bold cyan]██║   ██║ ╚███╔╝  ╚████╔╝ [/]   [dim cyan]v1.0.0 · Production Grade[/]
 [bold cyan]██║   ██║ ██╔██╗   ╚██╔╝  [/]   [dim bright_black]OpenAI Compatible · Multi-Provider Engine[/]
 [bold cyan]╚██████╔╝██╔╝ ██╗   ██║   [/]
  [bold cyan]╚═════╝ ╚═╝  ╚═╝   ╚═╝   [/]
"""

BANNER_AURORA = """
[bold #c792ea]   ✦  O  X  Y   A  G  E  N  T  ✦   [/]
[italic #7fdbca]  Northern Lights Autonomous Workspace · v1.0.0  [/]
"""

BANNER_MINIMAL = """
[bold white on blue]  OXY  [/]  [bold]AI Agent[/]  [dim]v1.0.0 · Setup[/]
"""


def render_cockpit_header(theme: dict[str, Any] | None = None):
    """Render top cockpit banner based on theme."""
    theme = theme or {}
    theme_name = theme.get("name", "Minimal").lower()

    if theme_name == "cyber":
        console.print(BANNER_CYBER.strip())
    elif theme_name == "aurora":
        console.print(BANNER_AURORA.strip())
    else:
        console.print(BANNER_MINIMAL.strip())
    console.print()
