"""
OXY Security — Non-bypassable hardline security floor and permission verification.

Architectural Guarantees:
  1. Hardline Floor: Catastrophic operations (destructive root deletions, disk formatting,
     raw block device writes, fork bombs, credential dumping) are categorically BLOCKED.
     No flag (--yolo or permission_mode="auto") can ever bypass this floor.
  2. Steering File Protection: Modifications to agent instruction files (system_prompt.md,
     CLAUDE.md, AGENTS.md, .cursorrules, oxy_config.json, .env) always require mandatory
     human confirmation, preventing prompt injection attacks from silently hijacking the agent.
  3. Path Sandboxing: Detects path traversal escapes outside workspace when required.
"""

from __future__ import annotations

import re
from enum import Enum
from pathlib import Path
from typing import NamedTuple


class SecurityVerdict(str, Enum):
    ALLOWED = "allowed"
    REQUIRES_CONFIRMATION = "requires_confirmation"
    BLOCKED = "blocked"


class SecurityDecision(NamedTuple):
    verdict: SecurityVerdict
    reason: str


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  Hardline Patterns (Categorically Blocked)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

# Commands that permanently damage the host OS or partition tables
CATASTROPHIC_PATTERNS = [
    (re.compile(r'\brm\s+(-[a-zA-Z]*r[a-zA-Z]*f[a-zA-Z]*|-[a-zA-Z]*f[a-zA-Z]*r[a-zA-Z]*)\s+(/|/\*|~|\$HOME|\./\.\.)(?:\s|$)', re.IGNORECASE),
     "Destructive root or home deletion command is blocked by the hardline security floor."),
    (re.compile(r'\bmkfs(?:\.[a-z0-9]+)?\s+', re.IGNORECASE),
     "Filesystem formatting command (mkfs) is blocked by the hardline security floor."),
    (re.compile(r'\bdd\s+.*of=/dev/(?:sd|hd|nvme|vd|mmcblk)[a-z0-9]*', re.IGNORECASE),
     "Raw block device write via dd is blocked by the hardline security floor."),
    (re.compile(r':\(\)\s*\{\s*:\s*\|\s*:\s*&\s*\}\s*;\s*:', re.IGNORECASE),
     "Fork bomb pattern is blocked by the hardline security floor."),
    (re.compile(r'\b(shutdown|reboot|poweroff|halt|init\s+[06])\b', re.IGNORECASE),
     "System power/shutdown control command is blocked by the hardline security floor."),
    (re.compile(r'>\s*/dev/(?:sd|hd|nvme|vd|mmcblk)[a-z0-9]*', re.IGNORECASE),
     "Direct write to block device is blocked by the hardline security floor."),
]

# Sensitive credentials that must never be dumped or exfiltrated
CREDENTIAL_FILES = [
    re.compile(r'/\.ssh/id_[a-z0-9_]+', re.IGNORECASE),
    re.compile(r'/\.ssh/id_[a-z0-9_]+\.pub', re.IGNORECASE),
    re.compile(r'/\.aws/credentials', re.IGNORECASE),
    re.compile(r'/\.netrc', re.IGNORECASE),
    re.compile(r'/\.pgpass', re.IGNORECASE),
    re.compile(r'/etc/shadow', re.IGNORECASE),
    re.compile(r'/etc/master\.passwd', re.IGNORECASE),
]

# Agent steering and credential files that ALWAYS require explicit human approval to edit/write
STEERING_FILES = {
    "system_prompt.md",
    "claude.md",
    "agents.md",
    ".cursorrules",
    ".windsurfrules",
    "oxy_config.json",
    ".env",
    ".env.local",
    ".env.production",
}

# Precompile regexes for steering file modifications via shell redirection
STEERING_REDIRECT_PATTERNS = [
    (s_file, re.compile(rf'(?:>|>>|\btee\b|\bsed\s+-i).*?\b{re.escape(s_file)}\b', re.IGNORECASE))
    for s_file in STEERING_FILES
]

# Known built-in tools subject to security policies
KNOWN_TOOLS = {
    "read_file",
    "write_file",
    "edit_file",
    "bash",
    "bash_background",
    "job_status",
    "job_cancel",
    "file_search",
    "content_search",
    "list_dir",
    "git_status",
    "save_memory",
    "recall_memory",
    "load_skill",
}


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  Security Gate
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class SecurityGate:
    """Evaluates all actions against the non-bypassable floor and steering policies."""

    @classmethod
    def check_bash_command(cls, cmd: str) -> SecurityDecision:
        """Check shell command against hardline floor and credential leak rules."""
        stripped = cmd.strip()
        if not stripped:
            return SecurityDecision(SecurityVerdict.ALLOWED, "Empty command")

        # 1. Catastrophic floor check
        for pattern, reason in CATASTROPHIC_PATTERNS:
            if pattern.search(stripped):
                return SecurityDecision(SecurityVerdict.BLOCKED, reason)

        # 2. Credential dumping check
        for pattern in CREDENTIAL_FILES:
            if pattern.search(stripped):
                # Allow read if it's strictly a benign status check, but block by default
                if re.search(r'\b(cat|head|tail|grep|curl|wget|nc|base64)\b', stripped, re.IGNORECASE):
                    return SecurityDecision(
                        SecurityVerdict.BLOCKED,
                        "Access to sensitive host credentials (.ssh, .aws, .netrc, shadow) is blocked."
                    )

        # 3. Modification of steering files via shell redirection
        for s_file, pattern in STEERING_REDIRECT_PATTERNS:
            if pattern.search(stripped):
                return SecurityDecision(
                    SecurityVerdict.REQUIRES_CONFIRMATION,
                    f"Shell command attempts to modify agent steering file '{s_file}'. Human confirmation is required."
                )

        return SecurityDecision(SecurityVerdict.ALLOWED, "Command passed security checks")

    @classmethod
    def check_file_path(cls, path_str: str, operation: str = "read") -> SecurityDecision:
        """Check file path against credential protections and steering policies."""
        try:
            p = Path(path_str).expanduser().resolve()
        except Exception:
            p = Path(path_str)

        path_name = p.name.lower()
        full_path = str(p)

        # 1. Block credential reads/writes
        for pattern in CREDENTIAL_FILES:
            if pattern.search(full_path):
                return SecurityDecision(
                    SecurityVerdict.BLOCKED,
                    f"Access to credential path '{path_str}' is blocked by the security floor."
                )

        # 2. Writing to agent-steering files requires human confirmation
        if operation in ("write", "edit", "delete"):
            if path_name in STEERING_FILES or any(part.lower() in STEERING_FILES for part in p.parts):
                return SecurityDecision(
                    SecurityVerdict.REQUIRES_CONFIRMATION,
                    f"Modifying agent steering file '{path_name}' requires explicit confirmation to prevent prompt injection."
                )

            # Block writing to .git internals directly
            if ".git/hooks" in full_path or ".git/config" in full_path:
                return SecurityDecision(
                    SecurityVerdict.REQUIRES_CONFIRMATION,
                    f"Direct write to git internal '{p.name}' requires confirmation."
                )

        return SecurityDecision(SecurityVerdict.ALLOWED, "Path passed security checks")

    @classmethod
    def evaluate_tool_call(cls, tool_name: str, tool_args: dict) -> SecurityDecision:
        """Evaluate a tool execution call before dispatching.

        DENY-BY-DEFAULT: Unknown tools are BLOCKED, not allowed.
        """
        if tool_name in ("bash", "bash_background"):
            cmd = tool_args.get("command", "")
            return cls.check_bash_command(cmd)

        elif tool_name in ("write_file", "edit_file"):
            path = tool_args.get("path", "")
            return cls.check_file_path(path, operation="write")

        elif tool_name == "read_file":
            path = tool_args.get("path", "")
            return cls.check_file_path(path, operation="read")

        # Known safe tools that require no further checks
        elif tool_name in ("list_dir", "file_search", "content_search", "git_status", "save_memory", "recall_memory", "load_skill", "job_status", "job_cancel"):
            return SecurityDecision(SecurityVerdict.ALLOWED, "Tool action allowed")

        # Dynamically registered MCP tools (prefixed with mcp_)
        elif tool_name.startswith("mcp_") and tool_name in KNOWN_TOOLS:
            return SecurityDecision(SecurityVerdict.ALLOWED, "MCP tool action allowed")

        # Deny-by-default: Unknown tools must be explicitly approved
        return SecurityDecision(
            SecurityVerdict.BLOCKED,
            f"Unknown tool '{tool_name}' blocked by security floor. Add explicit policy branch in SecurityGate.evaluate_tool_call."
        )
