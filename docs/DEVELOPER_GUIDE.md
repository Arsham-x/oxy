# OXY Developer & Extension Guide

> A practical guide for developers extending OXY: authoring custom tools, writing procedural skills, creating lifecycle hooks, integrating external MCP servers, designing custom themes, and adding new language localizations.

---

## Table of Contents

1. [Architecture Principles](#1-architecture-principles)
2. [Adding Custom Tools](#2-adding-custom-tools)
3. [Authoring Procedural Skills](#3-authoring-procedural-skills)
4. [Creating Lifecycle Hooks](#4-creating-lifecycle-hooks)
5. [Connecting Model Context Protocol (MCP) Servers](#5-connecting-model-context-protocol-mcp-servers)
6. [Designing Custom Themes](#6-designing-custom-themes)
7. [Adding New Languages & Internationalization](#7-adding-new-languages--internationalization)
8. [Testing & Verification](#8-testing--verification)

---

## 1. Architecture Principles

When extending OXY, adhere to the core operating directive:

> *"Never write complex, bloated code when a simpler, robust architecture achieves the exact same result."*  
> (تا وقتی میشه با یک کد ساده تر به همون نتیجه رسید، نباید کد پیچیده ای نوشت)

### Non-Bypassable Guarantees:
- **Deny-by-Default**: Every tool must have an explicit policy branch in `SecurityGate.evaluate_tool_call` and be listed in `KNOWN_TOOLS`.
- **Persist-Before-Execute**: Tool intents are written to `.oxy/sessions/<id>.jsonl` with `fsync()` before invocation.
- **Read/Write Segmentation**: Read-only tools execute concurrently; mutating operations act as isolated barriers.
- **Ambient Quarantine**: Never implicitly load untrusted configuration or prompt files from the working directory.

---

## 2. Adding Custom Tools

Tools give the agent capabilities to interact with files, processes, or APIs.

### Step 1: Define the Tool Function

In `oxy/tools.py` (or your custom module), implement your function returning a `ToolResult`:

```python
from .tools import ToolResult

def count_lines(path: str) -> ToolResult:
    """Count lines in a workspace file."""
    p = Path(path).expanduser().resolve()
    if not p.exists():
        return ToolResult(False, f"File '{path}' does not exist.")
    try:
        lines = len(p.read_text(encoding="utf-8", errors="ignore").splitlines())
        return ToolResult(True, f"'{path}' has {lines} lines.", metadata={"lines": lines})
    except Exception as e:
        return ToolResult(False, f"Error reading '{path}': {e}")
```

### Step 2: Define the JSON Schema

Add the schema entry to `TOOL_SCHEMAS` in `oxy/tools.py`:

```python
{
    "type": "function",
    "function": {
        "name": "count_lines",
        "description": "Count the number of lines in a file.",
        "parameters": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Path to the file.",
                },
            },
            "required": ["path"],
        },
    },
}
```

### Step 3: Register in ToolRegistry

In `ToolRegistry.__init__` in `oxy/tools.py`:

```python
self._tools["count_lines"] = count_lines
# If read-only, add to safe tools for concurrent execution:
self._safe_tools.add("count_lines")
```

### Step 4: Register in SecurityGate

In `oxy/security.py`:
1. Add `"count_lines"` to `KNOWN_TOOLS`.
2. Add its security policy in `SecurityGate.evaluate_tool_call`:

```python
elif tool_name == "count_lines":
    path = tool_args.get("path", "")
    return cls.check_file_path(path, operation="read")
```

---

## 3. Authoring Procedural Skills

Skills provide on-demand instructions following the **AgentSkills** standard without polluting the system prompt.

### File Hierarchy
- Project-specific: `<project_root>/.oxy/skills/<skill-name>/SKILL.md`
- User-global: `~/.oxy/skills/<skill-name>/SKILL.md`

### Anatomy of `SKILL.md`

```markdown
---
name: format-code
description: Enforce PEP 8 and project style formatting rules
triggers: [format, ruff, black, فرمت, زیباسازی]
---

# Procedural Workflow: Code Formatting

## Protocol:
1. Check if `ruff` or `black` is available in the environment via `bash`.
2. Run format dry-run: `ruff check --diff .`
3. If clean, execute in-place formatting: `ruff format .`
4. Run `git_status` to verify formatted files.
```

### Automatic Discovery & Invocation
- OXY indexes skills into a ~15-token summary in the system prompt.
- Users invoke via `/<skill-name>` (e.g. `/format-code`).
- The model loads instructions autonomously via `load_skill("format-code")`.

---

## 4. Creating Lifecycle Hooks

Hooks allow custom automation around agent execution without modifying core code.

### Supported Lifecycle Events

| Event | When It Fires |
| :--- | :--- |
| `session_start` | REPL or headless session boots |
| `pre_turn` | Before user prompt is sent to LLM |
| `pre_tool_call` | Before any tool executes (can block or mutate) |
| `post_tool_call` | Immediately after tool finishes execution |
| `post_turn` | After assistant response is rendered |
| `session_end` | On clean agent exit |

### Option A: Shell Script Hooks (Workspace)
Create an executable script in `.oxy/hooks/<event>` or `.oxy/hooks/<event>.sh`:

```bash
mkdir -p .oxy/hooks
cat << 'EOF' > .oxy/hooks/pre_tool_call.sh
#!/bin/bash
# Receives JSON payload via stdin: {"tool_name": "...", "tool_args": {...}}
read -r PAYLOAD
TOOL_NAME=$(echo "$PAYLOAD" | grep -o '"tool_name": *"[^"]*"' | cut -d'"' -f4)

if [ "$TOOL_NAME" = "bash" ]; then
    echo "Audited bash execution: $PAYLOAD" >> /tmp/oxy_audit.log
fi

# Exit 0 allows; non-zero blocks execution
exit 0
EOF
chmod +x .oxy/hooks/pre_tool_call.sh
```

### Option B: In-Memory Python Hooks
Register programmatically via `hooks.register`:

```python
from oxy.hooks import hooks, HookEvent

def audit_listener(**payload):
    print(f"[Hook] Tool executing: {payload.get('tool_name')}")

hooks.register(HookEvent.PRE_TOOL_CALL, audit_listener)
```

*Note: Hook failures are caught and logged; they never crash the active REPL session.*

---

## 5. Connecting Model Context Protocol (MCP) Servers

OXY connects to external tools using the open standard **Model Context Protocol (MCP)** over stdio JSON-RPC 2.0.

### Configuration (`oxy_config.json`)
Add your MCP servers under the `"mcp_servers"` key:

```json
{
  "mcp_servers": {
    "github": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-github"],
      "env": {
        "GITHUB_PERSONAL_ACCESS_TOKEN": "ghp_xxxxxxxxxxxx"
      }
    },
    "postgres": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-postgres", "postgresql://user:pass@localhost:5432/mydb"]
    }
  }
}
```

### Operational Behavior
1. OXY launches the server subprocess during initialization.
2. Performs the `initialize` handshake (`protocolVersion: 2024-11-05`).
3. Discovers tools via `tools/list` and registers them as `mcp_{server}_{tool}`.
4. Dynamically registers them into `KNOWN_TOOLS` and evaluates tool calls through `SecurityGate`.
5. Run `/mcp` in the REPL to inspect active connections and registered tools.

---

## 6. Designing Custom Themes

OXY features a pluggable theme registry with strict validation and user theme discovery.

### Built-in Themes
- `cyber`: Electric cyan and neon green matrix aesthetic.
- `aurora`: Northern lights violet and emerald gradient.
- `minimal`: Clean monochrome for focused terminals.

### Creating a User Theme File
Place your custom theme JSON file in either:
- Global: `~/.oxy/themes/<name>.json`
- Project: `.oxy/themes/<name>.json`

Example: `.oxy/themes/solarized.json`

```json
{
  "name": "Solarized",
  "accent": "yellow",
  "dim": "bright_black",
  "user_style": "bold yellow",
  "ai_title": "[bold cyan]✦ OXY[/]",
  "ai_border": "cyan",
  "ai_box": "ROUNDED",
  "welcome_border": "yellow",
  "welcome_box": "ROUNDED",
  "spinner": "dots",
  "spinner_style": "yellow",
  "tool_icon": "●",
  "think_icon": "◆",
  "sub_agent": "bold blue",
  "rule_style": "yellow",
  "error_style": "bold red",
  "system_style": "dim yellow",
  "warning": "yellow"
}
```

### Activation
```bash
# In REPL
/theme solarized

# From CLI
python3 oxy.py --theme solarized
```

---

## 7. Adding New Languages & Internationalization

OXY supports native internationalization via `oxy/i18n.py`.

### Supported Locales
- `en` (English, default)
- `fa` (Persian / فارسی)
- `zh` (Chinese / 简体中文)

### Adding a New Language (e.g., `es` - Spanish)

1. In `oxy/i18n.py`:
   - Add `"es"` to `SUPPORTED_LANGUAGES`:
     ```python
     SUPPORTED_LANGUAGES = ("en", "fa", "zh", "es")
     ```
   - Add the Spanish string table to `STRINGS["es"]`:
     ```python
     STRINGS["es"] = {
         "turns": "turnos",
         "tok": "tok",
         "auto": "auto",
         "ask": "preguntar",
         "files": "archivos",
         "mem": "mem",
         "rr": "rr",
         "help_shortcut": "/help comandos",
         "welcome_hint": "Enter enviar · Alt+Enter salto · Ctrl+C cancelar · /help comandos",
         "allow_action": "¿Permitir acción de herramienta?",
         "yes_once": "[y] Sí (una vez)",
         "no": "[n] No",
         "yes_always": "[a] Siempre",
         "goodbye_bye": "¡Hasta pronto!",
         "orphaned_tool_calls_detected": "Se detectaron llamadas a herramientas huérfanas ({count})...",
         "unresolved_discarded": "Descartadas {count} llamadas a herramientas no resueltas.",
         "agent_error_history_preserved": "Error del agente: el historial previo se ha preservado.",
     }
     ```
   - In `oxy/render.py`, add accepted affirmative synonyms to `YES_WORDS` and `ALWAYS_WORDS`:
     ```python
     YES_WORDS = ("y", "yes", "بله", "آره", "是", "好", "对", "嗯", "s", "si", "sí")
     ALWAYS_WORDS = ("a", "always", "همیشه", "总是", "永远", "siempre")
     ```

2. Activate at runtime:
   ```bash
   python3 oxy.py --lang es
   # Or in REPL:
   /lang es
   ```

---

## 8. Testing & Verification

Run the end-to-end test suite to verify changes:

```bash
# Run full pytest suite
pytest tests/ -v

# Verify code hygiene and unused imports
python3 -m pyflakes oxy/*.py
```
