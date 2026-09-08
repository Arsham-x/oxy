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
import time
from typing import Any

from rich.console import Console
from rich.panel import Panel
from rich.text import Text
from rich.cells import cell_len
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

def _read_raw_key(fd: int) -> str:
    """Read a single keypress directly from raw OS file descriptor without buffering."""
    try:
        b = os.read(fd, 32)
    except Exception:
        return ""

    if not b:
        return ""

    # Ctrl+C
    if b == b"\x03":
        raise KeyboardInterrupt()

    # Up arrow (ANSI, SS3, or vim navigation)
    if b in (b"\x1b[A", b"\x1bOA", b"k", b"K") or (b.startswith(b"\x1b[") and b.endswith(b"A")):
        return "up"

    # Down arrow (ANSI, SS3, or vim navigation)
    if b in (b"\x1b[B", b"\x1bOB", b"j", b"J") or (b.startswith(b"\x1b[") and b.endswith(b"B")):
        return "down"

    # Enter
    if b in (b"\r", b"\n"):
        return "enter"

    # Direct 1-9 selection
    if len(b) == 1 and b in b"123456789":
        return b.decode("ascii")

    # If it starts with an escape sequence that arrived in chunks
    if b.startswith(b"\x1b"):
        import select
        r, _, _ = select.select([fd], [], [], 0.04)
        if r:
            try:
                extra = os.read(fd, 32)
                full = b + extra
                if full.endswith(b"A"):
                    return "up"
                if full.endswith(b"B"):
                    return "down"
            except Exception:
                pass
        return "esc"

    return ""


def select_menu(
    title: str,
    options: list[tuple[str, str]],
    default: int = 0,
    theme: dict[str, Any] | None = None,
    help_hint: str | None = None,
    step_info: str | None = None,
) -> int:
    """Rock-solid, flicker-free arrow-key selector with full-width in-place ANSI rewriting.

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
        accent = "\033[1;36m"          # Bold Cyan
        cursor_color = "\033[1;32m"    # Bold Green
        dim = "\033[2m"
        white = "\033[1;37m"
        ok_color = "\033[1;32m"
        border_color = "\033[2;36m"
    elif theme_name == "aurora":
        accent = "\033[1;35m"          # Bold Magenta/Purple
        cursor_color = "\033[1;36m"    # Bold Teal
        dim = "\033[2m"
        white = "\033[1;37m"
        ok_color = "\033[1;35m"
        border_color = "\033[2;35m"
    else:  # Minimal
        accent = "\033[1;34m"          # Bold Blue
        cursor_color = "\033[1m"
        dim = "\033[2m"
        white = "\033[1;37m"
        ok_color = "\033[1;32m"
        border_color = "\033[2m"

    reset = "\033[0m"

    current = max(0, min(default, len(options) - 1))
    cols = shutil.get_terminal_size((80, 24)).columns
    rule_w = max(30, min(cols - 4, 120))

    def build_lines(idx: int) -> list[str]:
        lines = []
        step_prefix = f"{dim}[{step_info}]{reset} " if step_info else ""
        header = f"  {accent}?{reset} {step_prefix}{white}{title}{reset} {dim}(↑/↓ navigate · Enter confirm){reset}"

        lines.append(f"  {border_color}{'━' * rule_w}{reset}")
        lines.append(header)
        lines.append(f"  {border_color}{'─' * rule_w}{reset}")

        max_label_cell = max(cell_len(l) for l, _ in options)
        col_w = max(18, min(32, max_label_cell + 3))
        desc_w = max(10, rule_w - col_w - 12)

        for i, (label, desc) in enumerate(options):
            pad = " " * max(1, col_w - cell_len(label))
            d = desc[:desc_w]
            if i == idx:
                lines.append(f"  {cursor_color}❯{reset}  {white}{label}{pad}{reset}{accent}───  {d}{reset}")
            else:
                lines.append(f"     {dim}{label}{pad}───  {d}{reset}")

        lines.append(f"  {border_color}{'─' * rule_w}{reset}")
        hint = help_hint or "↑/↓ navigate · Enter select · 1-9 direct jump"
        lines.append(f"  {dim}↳ {hint}{reset}")
        lines.append(f"  {border_color}{'━' * rule_w}{reset}")
        return lines

    import tty
    import termios

    fd = sys.stdin.fileno()
    old_term = termios.tcgetattr(fd)

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
        tty.setraw(fd)
        termios.tcflush(fd, termios.TCIFLUSH)
        while True:
            try:
                key = _read_raw_key(fd)
            except KeyboardInterrupt:
                break

            if key == "up":
                current = (current - 1) % len(options)
            elif key == "down":
                current = (current + 1) % len(options)
            elif key == "enter":
                break
            elif key.isdigit() and 1 <= int(key) <= len(options):
                current = int(key) - 1
                break
            else:
                # Do NOT break on escape or other unhandled keys! Ignore safely.
                continue

            # In-place redraw: move cursor up line_count lines and rewrite each line
            new_lines = build_lines(current)
            sys.stdout.write(f"\033[{line_count}A\r")
            for line in new_lines:
                sys.stdout.write(f"\033[2K{line}\r\n")
            sys.stdout.flush()

    finally:
        # Restore terminal attributes before printing anything
        termios.tcsetattr(fd, termios.TCSADRAIN, old_term)
        try:
            termios.tcflush(fd, termios.TCIFLUSH)
        except Exception:
            pass

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
    """Render a clean breadcrumb progress indicator spanning terminal width."""
    theme = theme or {}
    accent = theme.get("accent", "cyan")
    dim = theme.get("dim", "dim")
    cols = shutil.get_terminal_size((80, 24)).columns

    bar_parts = []
    for step in range(1, total_steps + 1):
        if step < current_step:
            bar_parts.append(f"[{accent}]●[/]")
            if step < total_steps:
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
#  Cockpit Header — Centered Big OXY + Lower-Right AGENT
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

OXY_BLOCK_ART = [
    ("  ██████╗   ██╗   ██╗ ██╗   ██╗", "\033[1;36m"),
    (" ██╔═══██╗  ╚██╗ ██╔╝ ╚██╗ ██╔╝", "\033[1;36m"),
    (" ██║   ██║   ╚████╔╝   ╚████╔╝ ", "\033[1;96m"),
    (" ██║   ██║    ╚██╔╝     ╚██╔╝  ", "\033[1;32m"),
    (" ██║   ██║     ██║       ██║   ", "\033[1;32m"),
    (" ╚██████╔╝     ██║       ██║   ", "\033[1;92m"),
    ("  ╚═════╝      ╚═╝       ╚═╝   ", "\033[1;92m"),
]


def render_cockpit_header(theme: dict[str, Any] | None = None, animated: bool = True):
    """Render full-width, centered OXY banner with lower-right AGENT badge and animated reveal."""
    theme = theme or {}
    cols = shutil.get_terminal_size((80, 24)).columns
    rule_w = max(40, min(cols, 120))
    reset = "\033[0m"

    # Color palette based on theme
    theme_name = theme.get("name", "Cyber").lower()
    if theme_name == "aurora":
        rule_color = "\033[2;35m"
        art_colors = [
            "\033[1;35m", "\033[1;35m", "\033[1;95m",
            "\033[1;36m", "\033[1;36m", "\033[1;96m", "\033[1;96m"
        ]
        agent_color = "\033[1;96m"
    elif theme_name == "minimal":
        rule_color = "\033[2m"
        art_colors = ["\033[1;37m"] * 7
        agent_color = "\033[1;37m"
    else:  # Cyber
        rule_color = "\033[2;36m"
        art_colors = [
            "\033[1;36m", "\033[1;36m", "\033[1;96m",
            "\033[1;32m", "\033[1;32m", "\033[1;92m", "\033[1;92m"
        ]
        agent_color = "\033[1;92m"

    is_tty = sys.stdout.isatty()
    art_w = max(len(line) for line, _ in OXY_BLOCK_ART)

    # If terminal is wide enough, display centered block font
    if cols >= 45:
        margin = max(0, (cols - art_w) // 2)
        rule_margin = max(0, (cols - rule_w) // 2)

        # Top horizon line
        sys.stdout.write(" " * rule_margin + rule_color + ("━" * rule_w) + reset + "\n")
        sys.stdout.flush()

        # OXY Art Lines (with smooth animated reveal if interactive)
        for idx, (line_text, _) in enumerate(OXY_BLOCK_ART):
            color = art_colors[idx]
            sys.stdout.write(" " * margin + color + line_text + reset + "\n")
            sys.stdout.flush()
            if animated and is_tty:
                time.sleep(0.015)

        # Lower-right AGENT badge positioned under OXY
        agent_badge = "✦  A  G  E  N  T  ✦  \033[2mv1.0.0\033[0m"
        # Visible length without escape codes is 27 chars
        agent_pad = margin + art_w - 27
        sys.stdout.write(" " * max(0, agent_pad) + agent_color + agent_badge + reset + "\n")

        # Bottom horizon line
        sys.stdout.write(" " * rule_margin + rule_color + ("━" * rule_w) + reset + "\n\n")
        sys.stdout.flush()
    else:
        # Compact mode for narrow terminals
        sys.stdout.write(rule_color + ("━" * cols) + reset + "\n")
        sys.stdout.write(f"  {agent_color}✦ OXY AGENT ✦{reset}  \033[2mv1.0.0 · Production Grade\033[0m\n")
        sys.stdout.write(rule_color + ("━" * cols) + reset + "\n\n")
        sys.stdout.flush()
    console.print()
