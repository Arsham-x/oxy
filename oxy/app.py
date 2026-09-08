"""
OXY App — Main REPL loop and lifecycle orchestration.

Wires together: config, engine, tools, memory, repo, render, input, commands.
"""

from __future__ import annotations

import signal
import argparse
from datetime import datetime
from typing import Any

from .config import (
    load_config, save_config, resolve_system_prompt,
    validate_config, CONFIG_FILE, DEFAULT_CONFIG,
)
from .engine import ChatEngine
from .keys import KeyManager
from .memory import list_memories
from .render import (
    console, get_theme, print_welcome, print_goodbye,
    render_info, render_error_panel,
)
from .input import make_prompt_session, format_prompt, make_toolbar
from .commands import handle_command
from .setup import setup_wizard


def main():
    parser = argparse.ArgumentParser(description="OXY — CLI Agent for OpenAI-compatible APIs")
    parser.add_argument("-c", "--config", help="path to config JSON file")
    parser.add_argument("--setup", action="store_true", help="run the interactive config wizard")
    parser.add_argument("--theme", choices=["minimal", "cyber", "aurora"], help="override theme")
    parser.add_argument("--permission-mode", choices=["ask", "auto"], help="tool permission mode ('ask' for prompt, 'auto' for auto-approve)")
    parser.add_argument("--yolo", action="store_true", help="auto-approve tool execution (non-bypassable security floor still active)")
    parser.add_argument("-m", "--model", help="override model identifier for this session")
    parser.add_argument("-p", "--prompt", help="run single prompt headlessly and exit")
    parser.add_argument("--resume", nargs="?", const="latest", help="resume session by ID (or latest if omitted)")
    args = parser.parse_args()

    # ── Config ─────────────────────────────────────────────────
    if args.setup:
        config = setup_wizard()
    else:
        config = load_config(args.config)

    if args.theme:
        config["theme"] = args.theme

    if args.permission_mode:
        config["permission_mode"] = args.permission_mode

    if args.yolo:
        config["permission_mode"] = "auto"

    if args.model:
        config["model"] = args.model

    # ── Validation ─────────────────────────────────────────────
    warnings = validate_config(config)

    # If no API key and no round-robin keys, show setup help and exit
    if not config.get("api_key") and not config.get("round_robin_keys"):
        from rich.panel import Panel
        from rich import box

        console.print(Panel(
            "No API key configured.\n\n"
            "  1. Run [cyan]python oxy.py --setup[/]\n"
            "  2. Set [cyan]OPENAI_API_KEY[/] env var\n"
            "  3. Edit [cyan]oxy_config.json[/] directly",
            title="[bold red]missing API key[/]",
            border_style="red",
            box=box.ROUNDED,
        ))
        from pathlib import Path
        if not Path(args.config or CONFIG_FILE).exists():
            save_config(config)
            console.print(f"[dim]default config created → {CONFIG_FILE}[/]")
        raise SystemExit(1)

    # ── Theme ──────────────────────────────────────────────────
    theme = get_theme(config.get("theme", "minimal"))

    # Show warnings
    for w in warnings:
        render_info(f"⚠ {w}", theme)

    # ── Key manager ────────────────────────────────────────────
    key_manager = None
    if config.get("round_robin") and config.get("round_robin_keys"):
        key_manager = KeyManager(
            keys=config["round_robin_keys"],
            strategy=config.get("round_robin_strategy", "sequential"),
        )

    # ── Engine ─────────────────────────────────────────────────
    engine = ChatEngine(config, key_manager)
    engine.system_prompt = resolve_system_prompt(config)

    # ── Session Resumption ─────────────────────────────────────
    if args.resume:
        from .session import SessionRegistry, Session
        if args.resume == "latest":
            resumed_sess = SessionRegistry.get_latest_session()
        else:
            resumed_sess = Session(session_id=args.resume)

        if resumed_sess:
            engine.session = resumed_sess
            # Preserve ALL replayed message types (including system compaction blocks)
            engine.history = [m for m in resumed_sess.messages if m.get("role") in ("user", "assistant", "tool", "system")]
            render_info(f"Resumed session '{resumed_sess.session_id}' ({len(engine.history)} turns)", theme)
        else:
            render_info("No existing session found to resume. Starting fresh session.", theme)

    # ── Crash Recovery: surface orphaned tool calls ────────────────
    if engine.session.has_unresolved_tool_calls():
        from .render import render_error, ask_yes_no
        orphaned = engine.session.get_unresolved_tool_calls()
        render_error(
            f"Previous session ended with {len(orphaned)} unresolved tool call(s) "
            "(crashed or interrupted mid-execution).",
            theme,
        )
        for tc in orphaned:
            fn = tc.get("function", {})
            console.print(f"  [dim]• {fn.get('name')}: {str(fn.get('arguments'))[:80]}[/]")
        ask_yes_no("Continue without those calls? (no keeps the warning for this session)", theme, default_yes=True)
        discarded = engine.session.discard_unresolved_tool_calls()
        render_info(f"Discarded {discarded} orphaned tool call(s). State is clean.", theme)

    # ── Headless Prompt Mode (-p / --prompt) ───────────────────
    if args.prompt:
        try:
            engine.send(args.prompt)
        except Exception as e:
            render_error_panel(f"Agent failed: {type(e).__name__}: {e}", theme)
        return

    # ── Welcome ────────────────────────────────────────────────
    print_welcome(config, theme, engine=engine)

    # ── Input session ──────────────────────────────────────────
    session = make_prompt_session(theme)
    start_time = datetime.now()

    # ── SIGINT handler for cancellation ────────────────────────
    def on_sigint(sig, frame):
        engine.cancel()

    # ── REPL ───────────────────────────────────────────────────
    while True:
        try:
            toolbar = make_toolbar(
                model=engine.config["model"],
                msg_count=len(engine.history),
                max_history=engine.max_history,
                token_total=engine.tokens.total,
                start_time=start_time,
                theme_name=config.get("theme", "minimal"),
                rr_active=bool(key_manager and key_manager.is_active),
                active_files_count=len(engine.repo.active_files),
                memory_count=len(list_memories()),
                permission_mode=engine.permission_mode,
            )

            user_input = session.prompt(
                format_prompt(theme),
                bottom_toolbar=toolbar,
            ).strip()

        except KeyboardInterrupt:
            console.print()
            continue
        except EOFError:
            print_goodbye(len(engine.history), engine.tokens.total,
                         (datetime.now() - start_time).total_seconds(), theme)
            break

        if not user_input:
            continue

        # ── Slash commands (exception boundary: never kill REPL) ──
        if user_input.startswith("/"):
            try:
                keep_running, new_theme = handle_command(engine, user_input, config, theme)
            except Exception as e:
                render_error_panel(f"Command failed: {type(e).__name__}: {e}", theme)
                continue
            if new_theme:
                theme = new_theme
                session = make_prompt_session(theme)
            if not keep_running:
                print_goodbye(len(engine.history), engine.tokens.total,
                             (datetime.now() - start_time).total_seconds(), theme)
                break
            continue

        # ── Send message through agentic loop ──────────────────
        old_handler = signal.getsignal(signal.SIGINT)
        signal.signal(signal.SIGINT, on_sigint)

        try:
            try:
                engine.send(user_input)
            except SystemExit:
                raise
            except Exception as e:
                # Exception boundary: errors render a panel, history is
                # preserved, and the loop continues. Only quit kills the REPL.
                render_error_panel(f"Agent error ({type(e).__name__}): {e}", theme)
                render_info(f"history preserved ({len(engine.history)} messages). keep going.", theme)
        finally:
            signal.signal(signal.SIGINT, old_handler)
