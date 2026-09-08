"""
OXY Compat — Cross-platform terminal primitives and OS compatibility layer.

Provides unified primitives across Linux, macOS, and Windows:
  - Raw keyboard input and arrow-key detection (POSIX termios / Windows msvcrt)
  - Input buffer flushing without platform-specific crashes
  - Safe terminal fallback for non-interactive / CI / Windows consoles
  - Rich markup escaping utility
"""

from __future__ import annotations

import os
import sys
from typing import Any

from rich.markup import escape as safe_markup


def supports_raw() -> bool:
    """Return True if the current runtime supports in-place raw terminal control."""
    if not sys.stdin.isatty():
        return False
    if os.name == "nt":
        try:
            import msvcrt  # noqa: F401
            return True
        except ImportError:
            return False
    else:
        try:
            import termios  # noqa: F401
            import tty  # noqa: F401
            return True
        except ImportError:
            return False


def flush_input():
    """Flush pending characters from stdin buffer across platforms safely."""
    if not sys.stdin.isatty():
        return

    if os.name == "nt":
        try:
            import msvcrt
            while msvcrt.kbhit():
                msvcrt.getch()
        except Exception:
            pass
    else:
        try:
            import termios
            termios.tcflush(sys.stdin.fileno(), termios.TCIFLUSH)
        except Exception:
            pass


def read_key(fd: int | None = None) -> str:
    """Read a single keypress or navigation command across platforms.

    If fd is specified, reads from that file descriptor (POSIX), enabling pipe testing.
    """
    if fd is None and not sys.stdin.isatty():
        return ""

    if os.name == "nt" and fd is None:
        try:
            import msvcrt
            ch = msvcrt.getch()
            if ch in (b"\x00", b"\xe0"):  # Special prefix (arrows / function keys)
                ext = msvcrt.getch()
                if ext == b"H":
                    return "up"
                elif ext == b"P":
                    return "down"
                return ""
            if ch == b"\x03":
                raise KeyboardInterrupt()
            if ch in (b"\r", b"\n"):
                return "enter"
            if ch in (b"k", b"K"):
                return "up"
            if ch in (b"j", b"J"):
                return "down"
            if ch.isdigit():
                return ch.decode("ascii", errors="ignore")
        except KeyboardInterrupt:
            raise
        except Exception:
            return ""
        return ""

    # POSIX termios / fd path
    target_fd = fd if fd is not None else sys.stdin.fileno()
    try:
        b = os.read(target_fd, 32)
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
        try:
            import select
            r, _, _ = select.select([target_fd], [], [], 0.04)
            if r:
                extra = os.read(target_fd, 32)
                full = b + extra
                if full.endswith(b"A"):
                    return "up"
                if full.endswith(b"B"):
                    return "down"
        except Exception:
            pass
        return "esc"

    return ""


def fallback_select(
    title: str,
    options: list[tuple[str, str]],
    default: int = 0,
) -> int:
    """Clean fallback prompt for environments without raw ANSI menu support."""
    print(f"\n{title}")
    for idx, (label, desc) in enumerate(options, 1):
        suffix = f" — {desc}" if desc else ""
        print(f"  {idx}) {label}{suffix}")

    prompt_default = default + 1 if 0 <= default < len(options) else 1
    try:
        raw = input(f"Select [1-{len(options)}] (default {prompt_default}): ").strip()
    except (KeyboardInterrupt, EOFError):
        print()
        return default

    if not raw:
        return default
    try:
        chosen = int(raw) - 1
        if 0 <= chosen < len(options):
            return chosen
    except ValueError:
        pass
    return default
