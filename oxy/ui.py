"""
OXY UI — Interactive terminal controls, keyboard-driven selection, and clean international typography.

Inspired by Grok Build's production TUI:
  - select_menu: flicker-free arrow-key selector with in-place ANSI rewriting
  - PersianFormatter: clean Persian/Arabic text preserving native ligatures
  - render_stepper: breadcrumb progress gauge
  - render_cockpit_header: clean centered logo with subtle animation
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

    Modern terminals have built-in HarfBuzz/Qt/CoreText shaping.
    'native' mode leaves standard Unicode intact — the right default.
    """

    @staticmethod
    def is_persian(text: str) -> bool:
        return any(
            '؀' <= c <= 'ۿ' or
            'ݐ' <= c <= 'ݿ' or
            'ﭐ' <= c <= '﷿' or
            'ﹰ' <= c <= '﻿'
            for c in text
        )

    @classmethod
    def format(cls, text: str, mode: str = "native") -> str:
        if mode == "native" or not cls.is_persian(text):
            return text

        if mode == "bidi" and HAS_BIDI:
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
    """Read a single keypress directly from raw OS file descriptor."""
    try:
        b = os.read(fd, 32)
    except Exception:
        return ""

    if not b:
        return ""

    if b == b"\x03":
        raise KeyboardInterrupt()

    # Up arrow
    if b in (b"\x1b[A", b"\x1bOA", b"k", b"K") or (b.startswith(b"\x1b[") and b.endswith(b"A")):
        return "up"

    # Down arrow
    if b in (b"\x1b[B", b"\x1bOB", b"j", b"J") or (b.startswith(b"\x1b[") and b.endswith(b"B")):
        return "down"

    # Enter
    if b in (b"\r", b"\n"):
        return "enter"

    # Direct 1-9 selection
    if len(b) == 1 and b in b"123456789":
        return b.decode("ascii")

    # Chunked escape sequences
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
    """Flicker-free arrow-key selector with in-place ANSI rewriting.

    Returns selected index (0-based).
    """
    if not sys.stdin.isatty():
        return default

    theme = theme or {}
    theme_name = theme.get("name", "Cyber").lower()

    # ANSI colors by theme
    if theme_name == "cyber":
        accent = "\033[1;36m"
        cursor_color = "\033[1;32m"
        dim = "\033[2m"
        white = "\033[1;37m"
        ok_color = "\033[1;32m"
    elif theme_name == "aurora":
        accent = "\033[1;35m"
        cursor_color = "\033[1;36m"
        dim = "\033[2m"
        white = "\033[1;37m"
        ok_color = "\033[1;35m"
    else:
        accent = "\033[1;34m"
        cursor_color = "\033[1m"
        dim = "\033[2m"
        white = "\033[1;37m"
        ok_color = "\033[1;32m"

    reset = "\033[0m"

    current = max(0, min(default, len(options) - 1))
    cols = shutil.get_terminal_size((80, 24)).columns

    def build_lines(idx: int) -> list[str]:
        lines = []
        step_prefix = f"{dim}{step_info}{reset} " if step_info else ""
        header = f"  {accent}?{reset} {step_prefix}{white}{title}{reset}"
        lines.append(header)

        max_label_cell = max(cell_len(l) for l, _ in options)
        col_w = max(16, min(28, max_label_cell + 2))

        for i, (label, desc) in enumerate(options):
            pad = " " * max(1, col_w - cell_len(label))
            d = desc[:cols - col_w - 16] if desc else ""
            if i == idx:
                lines.append(f"  {cursor_color}❯{reset} {white}{label}{pad}{reset}{dim}{d}{reset}")
            else:
                lines.append(f"    {dim}{label}{pad}{d}{reset}")

        hint = help_hint or "↑/↓ navigate · Enter select · 1-9 jump"
        lines.append(f"  {dim}{hint}{reset}")
        return lines

    import tty
    import termios

    fd = sys.stdin.fileno()
    old_term = termios.tcgetattr(fd)

    sys.stdout.write("\033[?25l")
    sys.stdout.flush()

    lines = build_lines(current)
    line_count = len(lines)

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
                continue

            new_lines = build_lines(current)
            sys.stdout.write(f"\033[{line_count}A\r")
            for line in new_lines:
                sys.stdout.write(f"\033[2K{line}\r\n")
            sys.stdout.flush()

    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old_term)
        try:
            termios.tcflush(fd, termios.TCIFLUSH)
        except Exception:
            pass

        sys.stdout.write(f"\033[{line_count}A\r\033[0J")
        chosen_label, _ = options[current]
        sys.stdout.write(f"  {ok_color}✔{reset} {white}{title}{reset} {dim}›{reset} {accent}{chosen_label}{reset}\r\n\r\n")
        sys.stdout.write("\033[?25h")
        sys.stdout.flush()

    return current


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  Stepper (Progress Gauge)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def render_stepper(current_step: int, total_steps: int, title: str, theme: dict[str, Any] | None = None):
    """Clean breadcrumb progress indicator."""
    theme = theme or {}
    accent = theme.get("accent", "cyan")
    dim = theme.get("dim", "dim")

    bar_parts = []
    for step in range(1, total_steps + 1):
        if step < current_step:
            bar_parts.append(f"[{accent}]●[/]")
            if step < total_steps:
                bar_parts.append(f"[{accent}]━━[/]")
        elif step == current_step:
            bar_parts.append(f"[bold white on {accent}] {step} [/]")
            if step < total_steps:
                bar_parts.append(f"[{dim}]━━[/]")
        else:
            bar_parts.append(f"[{dim}]○[/]")
            if step < total_steps:
                bar_parts.append(f"[{dim}]━━[/]")

    gauge = "".join(bar_parts)
    console.print(f"  {gauge}  [{dim}]{current_step}/{total_steps}[/] [bold white]{title}[/]")
    console.print()


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  Cockpit Header — Clean Centered OXY Logo
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
    """Render centered OXY banner with lower-right AGENT badge."""
    theme = theme or {}
    cols = shutil.get_terminal_size((80, 24)).columns
    reset = "\033[0m"

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
    version = "v1.0.0"

    if cols >= 45:
        margin = max(0, (cols - art_w) // 2)
        rule_w = max(40, min(cols - 4, 120))
        rule_margin = max(0, (cols - rule_w) // 2)

        # Top rule
        sys.stdout.write("\n" + " " * rule_margin + rule_color + ("━" * rule_w) + reset + "\n")
        sys.stdout.flush()

        # OXY art
        for idx, (line_text, _) in enumerate(OXY_BLOCK_ART):
            color = art_colors[idx]
            sys.stdout.write(" " * margin + color + line_text + reset + "\n")
            sys.stdout.flush()
            if animated and is_tty:
                time.sleep(0.012)

        # AGENT badge — right-aligned under the art
        badge = "A G E N T"
        badge_text = f"{badge}  \033[2m{version}\033[0m"
        badge_visible_len = len(badge) + 2 + len(version)
        badge_pad = margin + art_w - badge_visible_len
        sys.stdout.write(" " * max(0, badge_pad) + agent_color + badge_text + reset + "\n")

        # Bottom rule
        sys.stdout.write(" " * rule_margin + rule_color + ("━" * rule_w) + reset + "\n\n")
        sys.stdout.flush()
    else:
        # Compact fallback
        sys.stdout.write("\n" + rule_color + ("━" * cols) + reset + "\n")
        sys.stdout.write(f"  {agent_color}OXY AGENT{reset}  \033[2m{version}\033[0m\n")
        sys.stdout.write(rule_color + ("━" * cols) + reset + "\n\n")
        sys.stdout.flush()

    console.print()
