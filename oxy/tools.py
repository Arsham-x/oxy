"""
OXY Tools — Built-in tool registry and execution engine for the AI agent.

Provides standard agent capabilities inspired by Claude Code and Codex:
  - read_file: read files with line numbering and range slicing
  - write_file: create or overwrite files safely
  - edit_file: exact string replacement with diff preview
  - bash: execute shell commands with timeout and output truncation
  - file_search: glob file finder skipping common noise dirs
  - content_search: fast text/regex search across project files
  - git_status: view git state, changed files, and current branch
"""

from __future__ import annotations

import difflib
import fnmatch
import json
import os
import re
import subprocess
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Callable

from .schemas import sanitize_tool_definition, coerce_tool_arguments
from .security import SecurityGate, SecurityVerdict


# Directories ignored by search tools to avoid flooding context
IGNORED_DIRS = {
    ".git", ".hg", ".svn", "__pycache__", ".pytest_cache", ".ruff_cache",
    ".mypy_cache", "node_modules", ".venv", "venv", "env", ".env",
    "dist", "build", ".idea", ".vscode", ".claude", ".next",
}

# Maximum lines returned by bash or read to prevent blowing the context window
MAX_OUTPUT_LINES = 250
MAX_OUTPUT_CHARS = 25_000
DEFAULT_BASH_TIMEOUT = 60
TOOL_RESULTS_DIR = Path.home() / ".oxy" / "tool-results"


def spill_large_output(text: str, label: str = "output") -> str:
    """If tool output exceeds MAX_OUTPUT_CHARS, spill full output to disk and return preview."""
    if len(text) <= MAX_OUTPUT_CHARS:
        return text

    TOOL_RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    import time
    ts = int(time.time() * 1000)
    file_path = TOOL_RESULTS_DIR / f"{label}_{ts}.txt"
    try:
        file_path.write_text(text, encoding="utf-8")
        preview = text[:2000]
        size_kb = len(text.encode("utf-8")) / 1024
        return (
            f"[Output too large ({size_kb:.1f} KB). Full output saved to: {file_path}]\n\n"
            f"Preview (first 2,000 chars):\n{preview}\n..."
        )
    except Exception:
        return text[:MAX_OUTPUT_CHARS] + "\n... (truncated)"


class ToolResult:
    """Encapsulates the result of a tool execution."""
    __slots__ = ("success", "output", "diff", "metadata")

    def __init__(
        self,
        success: bool,
        output: str,
        diff: str | None = None,
        metadata: dict[str, Any] | None = None,
    ):
        self.success = success
        self.output = spill_large_output(output)
        self.diff = diff
        self.metadata = metadata or {}

    def __str__(self) -> str:
        return self.output


# In-memory record of files read in this session (path -> mtime) for read-before-edit guarantees
READ_FILE_STATE: dict[str, float] = {}


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  Tool Implementations
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def read_file(path: str, offset: int = 1, limit: int = 2000) -> ToolResult:
    """Read a file with 1-indexed line numbers."""
    p = Path(path).expanduser().resolve()
    if not p.exists():
        return ToolResult(False, f"Error: File '{path}' does not exist.")
    if p.is_dir():
        return ToolResult(False, f"Error: '{path}' is a directory, not a file.")

    try:
        content = p.read_text(encoding="utf-8", errors="replace")
        READ_FILE_STATE[str(p)] = p.stat().st_mtime
    except Exception as e:
        return ToolResult(False, f"Error reading file '{path}': {e}")

    lines = content.splitlines()
    total_lines = len(lines)

    if total_lines == 0:
        return ToolResult(True, f"File '{path}' is empty.")

    # 1-indexed slice
    start = max(1, offset) - 1
    end = min(total_lines, start + limit)
    selected = lines[start:end]

    formatted = [f"{start + i + 1:6d}\t{line}" for i, line in enumerate(selected)]
    header = f"[{path}] lines {start + 1}-{end} of {total_lines}:\n"
    output = header + "\n".join(formatted)

    if end < total_lines:
        output += f"\n... ({total_lines - end} more lines not shown. Use offset={end + 1} to read further)"

    return ToolResult(
        True,
        output,
        metadata={"path": str(p), "lines": total_lines, "read": len(selected)},
    )


def write_file(path: str, content: str) -> ToolResult:
    """Create or overwrite a file with content."""
    p = Path(path).expanduser().resolve()
    key = str(p)

    # Read-before-write check on existing files (Claude Code discipline)
    if p.exists() and key not in READ_FILE_STATE:
        return ToolResult(
            False,
            f"Safety Error: File '{path}' already exists. You must inspect it with read_file first before overwriting, or use edit_file for surgical modifications.",
        )

    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        existed = p.exists()
        p.write_text(content, encoding="utf-8")
        READ_FILE_STATE[key] = p.stat().st_mtime
        lines = content.count("\n") + (1 if content and not content.endswith("\n") else 0)
        action = "Updated" if existed else "Created"
        return ToolResult(
            True,
            f"{action} file '{path}' ({lines} lines, {len(content):,} bytes).",
            metadata={"path": str(p), "action": action.lower(), "lines": lines},
        )
    except Exception as e:
        return ToolResult(False, f"Error writing to file '{path}': {e}")


def edit_file(path: str, old_string: str, new_string: str, replace_all: bool = False) -> ToolResult:
    """Perform exact string replacement in a file and generate a unified diff."""
    p = Path(path).expanduser().resolve()
    key = str(p)

    if not p.exists():
        return ToolResult(False, f"Error: File '{path}' does not exist.")
    if p.is_dir():
        return ToolResult(False, f"Error: '{path}' is a directory.")

    # Read-before-edit guarantee (Claude Code discipline)
    if key not in READ_FILE_STATE:
        return ToolResult(
            False,
            f"Safety Error: File '{path}' has not been read yet in this session. You must call read_file first before editing it.",
        )

    # Anti-staleness check: verify file on disk hasn't changed since last read
    if p.stat().st_mtime > READ_FILE_STATE[key]:
        return ToolResult(
            False,
            f"Safety Error: File '{path}' has been modified on disk since it was last read. Call read_file again to see the updated contents before editing.",
        )

    try:
        content = p.read_text(encoding="utf-8")
    except Exception as e:
        return ToolResult(False, f"Error reading file '{path}': {e}")

    count = content.count(old_string)
    if count == 0:
        return ToolResult(
            False,
            f"Error: old_string not found in '{path}'. Make sure the string matches exactly, including indentation.",
        )
    if count > 1 and not replace_all:
        return ToolResult(
            False,
            f"Error: old_string appears {count} times in '{path}'. Provide more surrounding context to make it unique, or set replace_all=true.",
        )

    if replace_all:
        new_content = content.replace(old_string, new_string)
    else:
        new_content = content.replace(old_string, new_string, 1)

    # Compute unified diff
    orig_lines = content.splitlines(keepends=True)
    new_lines = new_content.splitlines(keepends=True)
    diff_lines = list(difflib.unified_diff(
        orig_lines,
        new_lines,
        fromfile=f"a/{path}",
        tofile=f"b/{path}",
        n=3,
    ))
    diff_text = "".join(diff_lines)

    try:
        p.write_text(new_content, encoding="utf-8")
        READ_FILE_STATE[key] = p.stat().st_mtime
    except Exception as e:
        return ToolResult(False, f"Error saving modified file '{path}': {e}")

    occurrences = f"{count} occurrences" if replace_all else "1 occurrence"
    return ToolResult(
        True,
        f"Successfully edited '{path}' ({occurrences} replaced).\n\nDiff:\n{diff_text}",
        diff=diff_text,
        metadata={"path": str(p), "replacements": count if replace_all else 1},
    )


def bash(command: str, timeout: int = DEFAULT_BASH_TIMEOUT) -> ToolResult:
    """Execute a shell command with timeout, safety checks, and output truncation."""
    cmd_clean = command.strip()
    if not cmd_clean:
        return ToolResult(False, "Error: empty command.")

    # Guardrail against catastrophic system deletion
    dangerous_patterns = [
        r"\brm\s+-[a-zA-Z]*rf\s+/\s*$",
        r"\brm\s+-[a-zA-Z]*rf\s+~\s*$",
        r"\brm\s+-[a-zA-Z]*rf\s+/\*",
        r"\b(mkfs|dd\s+if=.*of=/dev/)",
    ]
    for pat in dangerous_patterns:
        if re.search(pat, cmd_clean):
            return ToolResult(False, "Safety Block: Catastrophic command detected and blocked by OXY guardrails.")

    # Sanitize environment variables (inspired by Goose & Codex process hardening)
    safe_env = os.environ.copy()
    disallowed_env = ["LD_PRELOAD", "LD_LIBRARY_PATH", "DYLD_INSERT_LIBRARIES", "DYLD_LIBRARY_PATH"]
    for k in disallowed_env:
        safe_env.pop(k, None)

    try:
        proc = subprocess.run(
            cmd_clean,
            shell=True,
            executable="/bin/bash",
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=os.getcwd(),
            env=safe_env,
        )
    except subprocess.TimeoutExpired:
        return ToolResult(False, f"Error: Command timed out after {timeout} seconds.")
    except Exception as e:
        return ToolResult(False, f"Error running command: {e}")

    stdout = proc.stdout.strip()
    stderr = proc.stderr.strip()

    combined = []
    if stdout:
        combined.append(stdout)
    if stderr:
        combined.append(f"[stderr]\n{stderr}")

    full_output = "\n\n".join(combined) if combined else "(no output)"

    # Truncate if output exceeds MAX_OUTPUT_LINES
    lines = full_output.splitlines()
    if len(lines) > MAX_OUTPUT_LINES:
        head = lines[:100]
        tail = lines[-100:]
        truncated_count = len(lines) - 200
        full_output = (
            "\n".join(head)
            + f"\n\n[... {truncated_count} lines truncated ...]\n\n"
            + "\n".join(tail)
        )

    status_str = f"Exit code: {proc.returncode}"
    result_text = f"{full_output}\n\n{status_str}"

    return ToolResult(
        proc.returncode == 0,
        result_text,
        metadata={"returncode": proc.returncode, "command": command},
    )


def file_search(pattern: str, path: str = ".", max_results: int = 50) -> ToolResult:
    """Search for files matching a glob pattern, skipping noisy directories."""
    base = Path(path).expanduser().resolve()
    if not base.exists():
        return ToolResult(False, f"Error: Path '{path}' does not exist.")

    matches = []
    pattern_lower = pattern.lower()

    for root, dirs, files in os.walk(base):
        # Prune ignored directories in-place
        dirs[:] = [d for d in dirs if d not in IGNORED_DIRS and not d.startswith(".")]

        for f in files:
            if fnmatch.fnmatch(f.lower(), pattern_lower) or pattern_lower in f.lower():
                rel = os.path.relpath(os.path.join(root, f), base)
                matches.append(rel)
                if len(matches) >= max_results:
                    break
        if len(matches) >= max_results:
            break

    if not matches:
        return ToolResult(True, f"No files matching '{pattern}' in '{path}'.")

    output = f"Found {len(matches)} matching files in '{path}':\n" + "\n".join(f"  - {m}" for m in matches)
    if len(matches) >= max_results:
        output += f"\n  ... capped at {max_results} results."

    return ToolResult(True, output, metadata={"count": len(matches)})


def content_search(pattern: str, path: str = ".", max_results: int = 40) -> ToolResult:
    """Grep search for text or regex across project files."""
    base = Path(path).expanduser().resolve()
    if not base.exists():
        return ToolResult(False, f"Error: Path '{path}' does not exist.")

    try:
        regex = re.compile(pattern, re.IGNORECASE)
    except re.error as e:
        return ToolResult(False, f"Error: Invalid regex pattern '{pattern}': {e}")

    results = []

    for root, dirs, files in os.walk(base):
        dirs[:] = [d for d in dirs if d not in IGNORED_DIRS and not d.startswith(".")]

        for fname in files:
            fpath = Path(root) / fname
            # Skip large or binary files
            try:
                if fpath.stat().st_size > 1_000_000:
                    continue
                content = fpath.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                continue

            for line_no, line in enumerate(content.splitlines(), 1):
                if regex.search(line):
                    rel = os.path.relpath(fpath, base)
                    trimmed = line.strip()
                    if len(trimmed) > 150:
                        trimmed = trimmed[:147] + "..."
                    results.append(f"{rel}:{line_no}: {trimmed}")
                    if len(results) >= max_results:
                        break
            if len(results) >= max_results:
                break

    if not results:
        return ToolResult(True, f"No matches found for '{pattern}' in '{path}'.")

    output = f"Found {len(results)} matches for '{pattern}':\n" + "\n".join(results)
    if len(results) >= max_results:
        output += f"\n... capped at {max_results} results."

    return ToolResult(True, output, metadata={"count": len(results)})


def git_status() -> ToolResult:
    """Return git branch, status, and modified files."""
    try:
        branch = subprocess.check_output(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            stderr=subprocess.DEVNULL,
            text=True,
        ).strip()
        status = subprocess.check_output(
            ["git", "status", "--short"],
            stderr=subprocess.DEVNULL,
            text=True,
        ).strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return ToolResult(False, "Not a git repository or git command not found.")

    output = f"Branch: {branch}\n"
    if status:
        output += f"Changes:\n{status}"
    else:
        output += "Working tree clean."

    return ToolResult(True, output, metadata={"branch": branch, "dirty": bool(status)})


def tool_save_memory(
    slug: str,
    title: str,
    category: str = "project",
    content: str = "",
    description: str = "",
) -> ToolResult:
    """Save knowledge to persistent memory across sessions."""
    from .memory import save_memory as mem_save
    try:
        msg = mem_save(slug=slug, title=title, category=category, content=content, description=description)
        return ToolResult(True, msg)
    except Exception as e:
        return ToolResult(False, f"Error saving memory: {e}")


def tool_recall_memory(query: str) -> ToolResult:
    """Search stored memories for past facts, preferences, and project rules."""
    from .memory import recall_memory as mem_recall
    try:
        hits = mem_recall(query)
        if not hits:
            return ToolResult(True, f"No memories found matching '{query}'.")
        lines = [f"Found {len(hits)} memory items:"]
        for h in hits:
            lines.append(f"\n--- {h['title']} ({h['category']}) [{h['slug']}.md] ---")
            if h['description']:
                lines.append(f"Description: {h['description']}")
            lines.append(h['body'])
        return ToolResult(True, "\n".join(lines))
    except Exception as e:
        return ToolResult(False, f"Error recalling memory: {e}")


def tool_load_skill_wrapper(name: str) -> ToolResult:
    """Load on-demand procedural skill instructions."""
    from .skills import tool_load_skill
    res = tool_load_skill(name)
    if res.get("success"):
        out = f"### Skill: {res['name']}\n{res.get('description')}\n\n{res.get('instructions')}"
        return ToolResult(True, out, metadata={"skill": res['name']})
    else:
        return ToolResult(False, res.get("error", "Failed to load skill"))


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  Tool Registry & Schemas
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

TOOL_SCHEMAS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "Read the contents of a file with line numbers. Use this before modifying any file.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Path to the file to read (relative or absolute).",
                    },
                    "offset": {
                        "type": "integer",
                        "description": "1-indexed line number to start reading from (default: 1).",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Number of lines to read (default: 2000).",
                    },
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "write_file",
            "description": "Create a new file or completely overwrite an existing file with the provided content.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Path to the file to write.",
                    },
                    "content": {
                        "type": "string",
                        "description": "Full content to write to the file.",
                    },
                },
                "required": ["path", "content"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "edit_file",
            "description": "Perform exact search-and-replace on a file. Always read the file first to get the exact lines to match.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Path to the file to modify.",
                    },
                    "old_string": {
                        "type": "string",
                        "description": "Exact text to replace. Must match the file exactly including whitespace and indentation.",
                    },
                    "new_string": {
                        "type": "string",
                        "description": "New text to substitute in place of old_string.",
                    },
                    "replace_all": {
                        "type": "boolean",
                        "description": "If true, replace every occurrence. If false (default), old_string must be unique.",
                    },
                },
                "required": ["path", "old_string", "new_string"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "bash",
            "description": "Execute a shell command (bash) and return stdout, stderr, and exit code.",
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {
                        "type": "string",
                        "description": "The shell command to execute.",
                    },
                    "timeout": {
                        "type": "integer",
                        "description": "Timeout in seconds (default: 60).",
                    },
                },
                "required": ["command"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "file_search",
            "description": "Search for files by name/glob pattern in the project directory, skipping git and dependency folders.",
            "parameters": {
                "type": "object",
                "properties": {
                    "pattern": {
                        "type": "string",
                        "description": "Filename pattern or glob (e.g., '*.py', 'config*', 'test_*.ts').",
                    },
                    "path": {
                        "type": "string",
                        "description": "Directory to search in (default: current directory '.').",
                    },
                    "max_results": {
                        "type": "integer",
                        "description": "Maximum number of results to return (default: 50).",
                    },
                },
                "required": ["pattern"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "content_search",
            "description": "Search for text or regex pattern across files in the project (like grep).",
            "parameters": {
                "type": "object",
                "properties": {
                    "pattern": {
                        "type": "string",
                        "description": "Text or regex pattern to search for.",
                    },
                    "path": {
                        "type": "string",
                        "description": "Directory to search in (default: current directory '.').",
                    },
                    "max_results": {
                        "type": "integer",
                        "description": "Maximum matching lines to return (default: 40).",
                    },
                },
                "required": ["pattern"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "git_status",
            "description": "Get the current git branch, dirty status, and changed files.",
            "parameters": {
                "type": "object",
                "properties": {},
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "save_memory",
            "description": "Save important user preferences, recurring rules, or project facts to persistent memory.",
            "parameters": {
                "type": "object",
                "properties": {
                    "slug": {
                        "type": "string",
                        "description": "Short kebab-case identifier (e.g. 'user_tech_stack', 'testing_rules').",
                    },
                    "title": {
                        "type": "string",
                        "description": "Descriptive title for the memory.",
                    },
                    "category": {
                        "type": "string",
                        "enum": ["user", "feedback", "project", "reference"],
                        "description": "Category of memory.",
                    },
                    "content": {
                        "type": "string",
                        "description": "Full details to remember.",
                    },
                    "description": {
                        "type": "string",
                        "description": "One-line hook summary for the index.",
                    },
                },
                "required": ["slug", "title", "content"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "recall_memory",
            "description": "Search stored persistent memory for facts, preferences, or project guidelines.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Search keyword or topic to recall.",
                    },
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "load_skill",
            "description": "Load complete procedural instructions and workflow for a specialized skill (e.g. 'test', 'review', 'refactor', 'git-commit').",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {
                        "type": "string",
                        "description": "Name of the skill to load (e.g. 'review', 'test', 'refactor').",
                    },
                },
                "required": ["name"],
            },
        },
    },
]


class ToolRegistry:
    """Manages available tools, schemas, and execution."""

    def __init__(self):
        self._tools: dict[str, Callable[..., ToolResult]] = {
            "read_file": read_file,
            "write_file": write_file,
            "edit_file": edit_file,
            "bash": bash,
            "file_search": file_search,
            "content_search": content_search,
            "git_status": git_status,
            "save_memory": tool_save_memory,
            "recall_memory": tool_recall_memory,
            "load_skill": tool_load_skill_wrapper,
        }
        # Tools that are read-only and safe to auto-execute without asking
        self._safe_tools = {
            "read_file", "file_search", "content_search", "git_status", "recall_memory", "load_skill"
        }

    def register(self, name: str, fn: Callable[..., ToolResult], safe: bool = False):
        """Register a custom tool."""
        self._tools[name] = fn
        if safe:
            self._safe_tools.add(name)

    def is_safe(self, name: str) -> bool:
        """Check if a tool is read-only / safe."""
        return name in self._safe_tools

    def get_schemas(self) -> list[dict[str, Any]]:
        """Return sanitized tool definitions for OpenAI function calling."""
        return [sanitize_tool_definition(s) for s in TOOL_SCHEMAS]

    def get_schema_for_tool(self, name: str) -> dict[str, Any] | None:
        """Find the parameter JSON schema for a named tool."""
        for tool_def in TOOL_SCHEMAS:
            fn = tool_def.get("function", {})
            if fn.get("name") == name:
                return fn.get("parameters")
        return None

    def execute(self, name: str, arguments: dict[str, Any] | str) -> ToolResult:
        """Execute a single tool with argument coercion and hardline security checking."""
        if name not in self._tools:
            return ToolResult(False, f"Error: Unknown tool '{name}'. Available: {list(self._tools.keys())}")

        # Coerce arguments based on target schema
        param_schema = self.get_schema_for_tool(name)
        coerced_args = coerce_tool_arguments(arguments, param_schema)

        # Evaluate against non-bypassable security floor
        sec_decision = SecurityGate.evaluate_tool_call(name, coerced_args)
        if sec_decision.verdict == SecurityVerdict.BLOCKED:
            return ToolResult(
                False,
                f"🛑 [Hardline Security Floor] Action blocked: {sec_decision.reason}",
                metadata={"security_verdict": sec_decision.verdict, "blocked": True},
            )

        fn = self._tools[name]
        try:
            return fn(**coerced_args)
        except TypeError as e:
            return ToolResult(False, f"Argument error calling '{name}': {e}")
        except Exception as e:
            return ToolResult(False, f"Unexpected error executing '{name}': {e}")

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    #  Segmented Parallel Execution Planner
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    def plan_execution_batches(self, tool_calls: list[dict[str, Any]]) -> list[list[dict[str, Any]]]:
        """Segment a list of tool calls into concurrent read batches and sequential mutation barriers.

        Consecutive read-only calls (read_file, file_search, content_search, git_status,
        recall_memory) are grouped into concurrent execution batches.
        Any mutating operation (write_file, edit_file, bash, save_memory) acts as a strict
        sequential barrier that executes in isolation.
        """
        batches: list[list[dict[str, Any]]] = []
        current_read_batch: list[dict[str, Any]] = []

        for tc in tool_calls:
            fn_name = tc.get("function", {}).get("name", "")
            is_read_only = self.is_safe(fn_name)

            if is_read_only:
                current_read_batch.append(tc)
            else:
                # Flush previous read batch before mutation barrier
                if current_read_batch:
                    batches.append(current_read_batch)
                    current_read_batch = []
                # Mutating operation runs as its own isolated batch
                batches.append([tc])

        if current_read_batch:
            batches.append(current_read_batch)

        return batches

    def execute_batch(
        self,
        batch: list[dict[str, Any]],
        max_workers: int = 8,
    ) -> list[tuple[dict[str, Any], ToolResult]]:
        """Execute a planned batch of tool calls.

        Read-only batches run concurrently via ThreadPoolExecutor.
        Mutating batches execute sequentially in strict isolation.
        """
        if not batch:
            return []

        # Sequential execution if batch size is 1 or contains mutating operations
        if len(batch) == 1 or not all(self.is_safe(tc.get("function", {}).get("name", "")) for tc in batch):
            results = []
            for tc in batch:
                fn_name = tc.get("function", {}).get("name", "")
                raw_args = tc.get("function", {}).get("arguments", "{}")
                res = self.execute(fn_name, raw_args)
                results.append((tc, res))
            return results

        # Concurrent execution for multi-item read-only batches
        results_map: dict[str, tuple[dict[str, Any], ToolResult]] = {}
        with ThreadPoolExecutor(max_workers=min(len(batch), max_workers)) as executor:
            futures = {}
            for tc in batch:
                tc_id = tc.get("id", str(id(tc)))
                fn_name = tc.get("function", {}).get("name", "")
                raw_args = tc.get("function", {}).get("arguments", "{}")
                future = executor.submit(self.execute, fn_name, raw_args)
                futures[future] = (tc_id, tc)

            for future in as_completed(futures):
                tc_id, tc = futures[future]
                try:
                    res = future.result()
                except Exception as e:
                    res = ToolResult(False, f"Execution error in parallel worker: {e}")
                results_map[tc_id] = (tc, res)

        # Preserve original call ordering
        ordered_results = []
        for tc in batch:
            tc_id = tc.get("id", str(id(tc)))
            ordered_results.append(results_map[tc_id])

        return ordered_results
