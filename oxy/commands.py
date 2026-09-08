"""
OXY Commands — All slash commands for chat, agent tools, memory, and codebase navigation.
"""

from __future__ import annotations

import os
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any

from rich.table import Table
from rich.panel import Panel
from rich import box

from .config import SYSTEM_PROMPT_FILE, save_config, resolve_system_prompt
from .render import (
    console, render_info, render_error, render_system_prompt,
    render_token_table, render_error_panel, get_theme, THEMES,
)
from .engine import ChatEngine, SubAgent, SUB_AGENT_PERSONAS
from .memory import list_memories, recall_memory, delete_memory, clear_all_memories, get_memory_index_text
from .session import Session, SessionRegistry
from .skills import SkillManager


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  /help
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def cmd_help(theme: dict):
    t = Table(box=box.SIMPLE_HEAVY, show_edge=False)
    t.add_column("command", style=theme["accent"], no_wrap=True)
    t.add_column("description")

    rows = [
        # Core
        ("/help",                  "show this help reference"),
        ("/clear",                 "clear conversation history"),
        ("/quit",                  "exit OXY"),
        ("", ""),
        # Tools & Permissions
        ("/tools",                 "list all 10 agent tools and safety status"),
        ("/permissions [ask|auto]","view or toggle permission mode"),
        ("/skills [name]",         "list installed skills or view skill instructions"),
        ("", ""),
        # Codebase & Files (Aider-style)
        ("/add <file>",            "add file to active chat context"),
        ("/drop <file>",           "drop file from active chat context"),
        ("/files",                 "list active files and project tree"),
        ("/git",                   "show git status, branch, and changes"),
        ("", ""),
        # Memory (Claude Code-style)
        ("/memory",                "list all persistent memories"),
        ("/memory view <slug>",    "view detailed memory contents"),
        ("/memory clear",          "clear all stored memories"),
        ("", ""),
        # Agent & Model
        ("/agent [role] <task>",   "run sub-agent (architect/debugger/reviewer)"),
        ("/model [name]",          "view or switch AI model"),
        ("/system [text|edit]",    "view, set, or edit system prompt"),
        ("/keys",                  "manage round-robin API keys"),
        ("", ""),
        # Session & Durability
        ("/sessions",              "list saved session transaction ledgers"),
        ("/resume <id>",           "resume past session from disk"),
        ("/history",               "show conversation history turns"),
        ("/save [file]",           "export conversation to markdown"),
        ("/copy",                  "copy last AI response to clipboard"),
        ("/tokens",                "show token usage summary"),
        ("/theme [name]",          "switch theme (minimal/cyber/aurora)"),
        ("/config",                "view current configuration"),
        ("", ""),
        ("[dim]enter[/]",          "[dim]send message[/]"),
        ("[dim]alt+enter[/]",      "[dim]new line[/]"),
        ("[dim]ctrl+c[/]",         "[dim]cancel generation / tool[/]"),
        ("[dim]↑ / ↓[/]",         "[dim]browse input history[/]"),
    ]
    for cmd, desc in rows:
        t.add_row(cmd, desc)

    console.print(t)
    console.print()


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  /tools
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def cmd_tools(engine: ChatEngine, theme: dict):
    """List available agent tools and their safety classification."""
    t = Table(box=box.SIMPLE_HEAVY, show_edge=False)
    t.add_column("tool", style=theme["accent"], no_wrap=True)
    t.add_column("safety", justify="center")
    t.add_column("description")

    schemas = engine.tools.get_schemas()
    for s in schemas:
        fn = s["function"]
        name = fn["name"]
        desc = fn["description"]
        is_safe = engine.tools.is_safe(name)
        safety = "[green]read-only[/]" if is_safe else "[yellow]mutating[/]"
        t.add_row(name, safety, desc)

    console.print(t)
    mode = f"[bold cyan]{engine.permission_mode}[/]"
    console.print(f"  Permission mode: {mode}  ·  Use [cyan]/permissions auto[/] or [cyan]/permissions ask[/] to change.")
    console.print()


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  /permissions
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def cmd_permissions(engine: ChatEngine, arg: str, theme: dict):
    """View or toggle permission mode (ask / auto)."""
    arg = arg.strip().lower()
    if arg in ("auto", "bypass", "accept"):
        engine.permission_mode = "auto"
        render_info("permission mode → auto (auto-approves tools)", theme)
    elif arg in ("ask", "default", "prompt"):
        engine.permission_mode = "ask"
        render_info("permission mode → ask (interactive confirmation for mutating tools)", theme)
    else:
        render_info(
            f"current permission mode: {engine.permission_mode}\n"
            f"  - ask: interactive confirmation before running shell commands or modifying files\n"
            f"  - auto: auto-approve all tools\n"
            f"Usage: /permissions [ask|auto]",
            theme,
        )


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  /add, /drop, /files, /git
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def cmd_add(engine: ChatEngine, arg: str, theme: dict):
    if not arg:
        render_error("usage: /add <file-path>", theme)
        return
    ok, msg = engine.repo.add_file(arg)
    if ok:
        render_info(f"✓ {msg}", theme)
    else:
        render_error(msg, theme)


def cmd_drop(engine: ChatEngine, arg: str, theme: dict):
    if not arg:
        render_error("usage: /drop <file-path>", theme)
        return
    ok, msg = engine.repo.drop_file(arg)
    if ok:
        render_info(f"✓ {msg}", theme)
    else:
        render_error(msg, theme)


def cmd_files(engine: ChatEngine, theme: dict):
    active = engine.repo.active_files
    if active:
        console.print(f"[{theme['accent']}]Active Files in Context:[/]")
        for f in sorted(active):
            console.print(f"  [green]●[/] {f}")
        console.print()

    console.print(f"[{theme['dim']}]Project Structure ({engine.repo.root.name}):[/]")
    console.print(engine.repo.get_file_tree(max_files=35))
    console.print()


def cmd_git(engine: ChatEngine, theme: dict):
    res = engine.tools.execute("git_status", {})
    if res.success:
        console.print(Panel(
            res.output,
            title="[bold cyan]Git Status[/]",
            border_style=theme["accent"],
            box=box.ROUNDED,
        ))
    else:
        render_error(res.output, theme)
    console.print()


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  /memory
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def cmd_memory(arg: str, theme: dict):
    parts = arg.split(maxsplit=1)
    sub = parts[0].lower() if parts else ""
    sub_arg = parts[1].strip() if len(parts) > 1 else ""

    if sub == "clear":
        clear_all_memories()
        render_info("all persistent memories cleared", theme)
        return

    if sub == "view" and sub_arg:
        hits = recall_memory(sub_arg)
        if not hits:
            render_error(f"memory '{sub_arg}' not found", theme)
            return
        h = hits[0]
        console.print(Panel(
            f"Title: {h['title']}\nCategory: {h['category']}\n\n{h['body']}",
            title=f"Memory: {h['slug']}",
            box=box.ROUNDED,
            border_style=theme["accent"],
        ))
        console.print()
        return

    # List memories
    mems = list_memories()
    if not mems:
        render_info("no persistent memories stored yet (agent learns automatically during chat)", theme)
        return

    t = Table(box=box.SIMPLE_HEAVY, show_edge=False)
    t.add_column("slug", style=theme["accent"])
    t.add_column("category", style="dim")
    t.add_column("description")

    for m in mems:
        t.add_row(m["slug"], m["category"], m["description"])

    console.print(t)
    console.print(f"  [{theme['dim']}]Use /memory view <slug> to view details, or /memory clear to reset.[/]")
    console.print()


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  /agent — Sub-Agent with Personas
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def cmd_agent(engine: ChatEngine, arg: str, config: dict, theme: dict):
    """Run a sub-agent with a specialized persona."""
    if not arg:
        _show_agent_status(config, theme)
        return

    parts = arg.split(maxsplit=1)
    first = parts[0].lower()
    rest = parts[1].strip() if len(parts) > 1 else ""

    if first == "on":
        config["sub_agent_enabled"] = True
        render_info("sub-agent enabled", theme)
        return
    elif first == "off":
        config["sub_agent_enabled"] = False
        render_info("sub-agent disabled", theme)
        return
    elif first == "model":
        if rest:
            config["sub_agent_model"] = rest
            render_info(f"sub-agent model → {rest}", theme)
        else:
            current = config.get("sub_agent_model") or config["model"]
            render_info(f"sub-agent model: {current}", theme)
        return

    # Persona check
    persona = "general"
    task = arg
    if first in SUB_AGENT_PERSONAS and rest:
        persona = first
        task = rest

    # Build context from recent history
    context = ""
    if engine.history:
        recent = engine.history[-4:]
        context = "\n".join(
            f"{'User' if m.get('role') == 'user' else 'Assistant'}: {str(m.get('content', ''))[:200]}"
            for m in recent
        )

    sa = SubAgent(engine, persona=persona)
    sa.run(task, context)


def _show_agent_status(config: dict, theme: dict):
    enabled = config.get("sub_agent_enabled", True)
    model = config.get("sub_agent_model") or config.get("model", "?")
    max_tok = config.get("sub_agent_max_tokens", 2048)

    t = Table(box=box.SIMPLE_HEAVY, show_edge=False)
    t.add_column("", style=theme["dim"])
    t.add_column("")
    t.add_row("status", "enabled" if enabled else "disabled")
    t.add_row("model", model)
    t.add_row("max tokens", str(max_tok))
    console.print(t)
    console.print()

    d = theme["dim"]
    console.print(f"  [{d}]Personas available: architect, debugger, reviewer, general[/]")
    console.print(f"  [{d}]Usage:[/] /agent architect <design task>")
    console.print(f"         /agent debugger <error/bug investigation>")
    console.print(f"         /agent reviewer <audit task>")
    console.print(f"         /agent <general task>")
    console.print()


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  Standard Commands (/clear, /system, /model, /history, /save, etc.)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def cmd_clear(engine: ChatEngine, theme: dict):
    engine.clear_history()
    render_info("history cleared", theme)


def cmd_system(engine: ChatEngine, arg: str, theme: dict):
    if not arg:
        render_system_prompt(engine.system_prompt or "<default>", theme)
    elif arg == "edit":
        path = Path(SYSTEM_PROMPT_FILE)
        if not path.exists():
            path.write_text(engine.system_prompt or "You are OXY.", encoding="utf-8")
        editor = os.environ.get("EDITOR", "nano")
        os.system(f'{editor} "{path}"')
        text = path.read_text(encoding="utf-8").strip()
        if text:
            engine.set_system(text)
            render_info(f"system prompt reloaded ({len(text):,} chars)", theme)
    elif arg == "reload":
        new = resolve_system_prompt(engine.config)
        engine.set_system(new)
        render_info(f"system prompt reloaded ({len(new):,} chars)", theme)
    else:
        engine.set_system(arg)
        render_info(f"system prompt updated ({len(arg):,} chars)", theme)


def cmd_model(engine: ChatEngine, arg: str, theme: dict):
    if arg:
        engine.set_model(arg)
        render_info(f"model → {arg}", theme)
    else:
        render_info(f"model: {engine.config['model']}", theme)


def cmd_history(engine: ChatEngine, theme: dict):
    if not engine.history:
        render_info("no messages yet", theme)
        return

    d = theme["dim"]
    for i, msg in enumerate(engine.history, 1):
        role = msg.get("role", "")
        content = str(msg.get("content", ""))
        label = "you" if role == "user" else ("oxy" if role == "assistant" else role)
        color = theme["user_style"] if role == "user" else theme["accent"]

        preview = content[:120].replace("\n", " ")
        if len(content) > 120:
            preview += "…"
        console.print(f"  [{d}]{i:>3}.[/]  [{color}]{label}[/]  {preview}")

    console.print(f"\n  [{d}]{len(engine.history)} turns in working context[/]\n")


def cmd_save(engine: ChatEngine, arg: str, theme: dict):
    if not engine.history:
        render_error("no conversation to save", theme)
        return

    filename = arg or f"chat_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md"
    lines = [
        f"# OXY Chat — {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        f"**Model:** {engine.config['model']}",
        "",
        "---",
        "",
    ]
    for msg in engine.history:
        role = msg.get("role", "")
        content = str(msg.get("content", ""))
        role_label = "**You**" if role == "user" else ("**OXY**" if role == "assistant" else f"**{role}**")
        lines.append(f"### {role_label}\n\n{content}\n\n---\n")

    Path(filename).write_text("\n".join(lines), encoding="utf-8")
    render_info(f"saved → {Path(filename).absolute()}", theme)


def cmd_config(config: dict, theme: dict):
    t = Table(box=box.SIMPLE_HEAVY, show_edge=False)
    t.add_column("key", style=theme["accent"])
    t.add_column("value")

    for k, v in config.items():
        display = str(v)
        if k == "api_key" and v:
            display = v[:4] + "..." + v[-4:] if len(str(v)) > 12 else "****"
        elif k == "round_robin_keys" and v:
            display = f"[{len(v)} keys]"
        elif k == "system_prompt" and len(display) > 60:
            display = display[:60] + "…"
        t.add_row(k, display)

    console.print(t)
    console.print()


def cmd_tokens(engine: ChatEngine, theme: dict):
    render_token_table(engine.tokens, theme)


def cmd_copy(engine: ChatEngine, theme: dict):
    for msg in reversed(engine.history):
        if msg.get("role") == "assistant" and msg.get("content"):
            if _copy_to_clipboard(msg["content"]):
                render_info("copied to clipboard ✓", theme)
            else:
                render_error("no clipboard tool found (install xclip, xsel, or wl-copy)", theme)
            return
    render_info("no response to copy", theme)


def _copy_to_clipboard(text: str) -> bool:
    for tool in ["xclip -selection clipboard", "xsel --clipboard --input", "pbcopy", "wl-copy"]:
        parts = tool.split()
        try:
            proc = subprocess.run(parts, input=text.encode(), capture_output=True, timeout=3)
            if proc.returncode == 0:
                return True
        except (FileNotFoundError, subprocess.TimeoutExpired):
            continue
    return False


def cmd_theme(arg: str, config: dict, theme: dict) -> dict | None:
    if not arg:
        available = ", ".join(THEMES.keys())
        current = config.get("theme", "minimal")
        render_info(f"theme: {current}  (available: {available})", theme)
        return None

    if arg not in THEMES:
        render_error(f"unknown theme: {arg}  (try: minimal, cyber, aurora)", theme)
        return None

    config["theme"] = arg
    new_theme = get_theme(arg)
    render_info(f"theme → {new_theme['name']}", new_theme)
    return new_theme


def cmd_keys(engine: ChatEngine, arg: str, config: dict, theme: dict):
    if not arg:
        _show_keys_status(engine, config, theme)
        return

    parts = arg.split(maxsplit=1)
    sub = parts[0].lower()
    sub_arg = parts[1].strip() if len(parts) > 1 else ""

    if sub == "on":
        config["round_robin"] = True
        render_info("round-robin enabled ⟳", theme)
    elif sub == "off":
        config["round_robin"] = False
        render_info("round-robin disabled", theme)
    elif sub == "add" and sub_arg:
        keys = config.setdefault("round_robin_keys", [])
        keys.append(sub_arg)
        if engine.key_manager:
            engine.key_manager.add_key(sub_arg)
        render_info(f"key added (total: {len(keys)})", theme)
    elif sub == "strategy" and sub_arg in ("sequential", "random", "least-used"):
        config["round_robin_strategy"] = sub_arg
        if engine.key_manager:
            engine.key_manager.strategy = sub_arg
        render_info(f"strategy → {sub_arg}", theme)
    elif sub == "save":
        save_config(config)
        render_info("key config saved to disk", theme)
    else:
        _show_keys_status(engine, config, theme)


def _show_keys_status(engine: ChatEngine, config: dict, theme: dict):
    enabled = config.get("round_robin", False)
    keys = config.get("round_robin_keys", [])
    strategy = config.get("round_robin_strategy", "sequential")

    t = Table(box=box.SIMPLE_HEAVY, show_edge=False)
    t.add_column("", style=theme["dim"])
    t.add_column("")
    t.add_row("status", f"{'enabled ⟳' if enabled else 'disabled'}")
    t.add_row("strategy", strategy)
    t.add_row("keys", str(len(keys)))

    if keys and engine.key_manager:
        for s in engine.key_manager.stats():
            t.add_row(f"  [{s['index']}]", f"{s['key_preview']}  ({s['uses']} uses)")

    console.print(t)
    console.print()


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  /skills — Progressive Disclosure Procedural Instructions
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def cmd_skills(engine: ChatEngine, arg: str, theme: dict):
    mgr = getattr(engine, "skills", None) or SkillManager()

    if not arg:
        skills = mgr.list_skills()
        t = Table(title="Procedural Skills Registry", box=box.ROUNDED, border_style=theme["accent"])
        t.add_column("Command", style="bold cyan")
        t.add_column("Description", style="white")
        t.add_column("Triggers", style=theme["dim"])
        t.add_column("Source", style=theme["dim"])

        for s in skills:
            t.add_row(f"/{s.name}", s.description, ", ".join(s.triggers[:4]), s.source_path)

        console.print(t)
        console.print(f"  [{theme['dim']}]Run any skill with: [bold cyan]/<skill-name>[/] (e.g. /review, /test)[/]\n")
        return

    # View skill details
    skill = mgr.get_skill(arg)
    if not skill:
        render_error(f"Skill '{arg}' not found. Type /skills to see all installed skills.", theme)
        return

    console.print(Panel(
        skill.content,
        title=f"[bold cyan]Skill: {skill.name}[/]",
        subtitle=f"[dim]{skill.source_path}[/]",
        border_style=theme["accent"],
        box=box.ROUNDED,
    ))


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  /sessions & /resume — Durability Ledger Management
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def cmd_sessions(engine: ChatEngine, arg: str, theme: dict):
    sessions = SessionRegistry.list_sessions()
    if not sessions:
        render_info("No saved sessions found in current workspace.", theme)
        return

    t = Table(title="Saved Sessions Ledger", box=box.ROUNDED, border_style=theme["accent"])
    t.add_column("Session ID", style="bold cyan")
    t.add_column("Title", style="white")
    t.add_column("Turns", style="green", justify="right")
    t.add_column("Modified", style=theme["dim"])

    for s in sessions[:15]:
        mod_str = datetime.fromtimestamp(s["modified"]).strftime("%Y-%m-%d %H:%M")
        is_current = engine.session and engine.session.session_id == s["id"]
        id_display = f"● {s['id']}" if is_current else s['id']
        t.add_row(id_display, s["title"], str(s["turns"]), mod_str)

    console.print(t)
    console.print(f"  [{theme['dim']}]Resume any session with: [bold cyan]/resume <session-id>[/]\n")


def cmd_resume(engine: ChatEngine, session_id: str, theme: dict):
    if not session_id:
        render_error("Usage: /resume <session-id>", theme)
        return

    try:
        new_session = Session(session_id=session_id)
        engine.session = new_session
        engine.history = [m for m in new_session.messages if m.get("role") in ("user", "assistant", "tool")]
        render_info(f"Resumed session '{session_id}' ({len(engine.history)} turns loaded)", theme)
    except Exception as e:
        render_error(f"Failed to resume session '{session_id}': {e}", theme)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  Command Dispatcher
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def handle_command(engine: ChatEngine, line: str, config: dict, theme: dict) -> tuple[bool, dict | None]:
    """Dispatch slash commands. Returns (continue_running, new_theme_or_none)."""
    parts = line.split(maxsplit=1)
    cmd = parts[0].lower()
    arg = parts[1].strip() if len(parts) > 1 else ""

    new_theme = None

    match cmd:
        case "/quit" | "/exit" | "/q":
            return (False, None)
        case "/help" | "/h" | "/?":
            cmd_help(theme)
        case "/tools":
            cmd_tools(engine, theme)
        case "/permissions" | "/permission":
            cmd_permissions(engine, arg, theme)
        case "/skills" | "/skill":
            cmd_skills(engine, arg, theme)
        case "/sessions":
            cmd_sessions(engine, arg, theme)
        case "/resume":
            cmd_resume(engine, arg, theme)
        case "/add":
            cmd_add(engine, arg, theme)
        case "/drop":
            cmd_drop(engine, arg, theme)
        case "/files":
            cmd_files(engine, theme)
        case "/git":
            cmd_git(engine, theme)
        case "/memory":
            cmd_memory(arg, theme)
        case "/clear":
            cmd_clear(engine, theme)
        case "/system":
            cmd_system(engine, arg, theme)
        case "/model":
            cmd_model(engine, arg, theme)
        case "/history":
            cmd_history(engine, theme)
        case "/save":
            cmd_save(engine, arg, theme)
        case "/config":
            cmd_config(config, theme)
        case "/tokens":
            cmd_tokens(engine, theme)
        case "/copy":
            cmd_copy(engine, theme)
        case "/theme":
            new_theme = cmd_theme(arg, config, theme)
        case "/keys":
            cmd_keys(engine, arg, config, theme)
        case "/agent":
            cmd_agent(engine, arg, config, theme)
        case _:
            # Check if cmd is a direct invocation of an installed procedural skill (e.g. /review, /test)
            skill = getattr(engine, "skills", None) and engine.skills.get_skill(cmd.lstrip("/"))
            if skill:
                task_prompt = f"Execute procedural skill: {skill.name}\n\nTask: {arg or 'Analyze current workspace and run skill workflow.'}"
                engine.send(task_prompt)
            else:
                render_error(f"unknown command: {cmd}  (type /help)", theme)

    return (True, new_theme)
