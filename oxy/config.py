"""
OXY Config — Loading, validation, defaults.

Supports:
  - JSON config file (auto-created on first run)
  - Environment variable overrides
  - System prompt from external file
  - Round-robin API key management
  - Sub-agent configuration
  - Theme selection
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any


# ── Paths ─────────────────────────────────────────────────────────

CONFIG_FILE = "oxy_config.json"
SYSTEM_PROMPT_FILE = "system_prompt.md"
HISTORY_FILE = Path.home() / ".oxy_history"


# ── Defaults ──────────────────────────────────────────────────────

DEFAULT_CONFIG: dict[str, Any] = {
    # Provider
    "base_url":             "https://api.openai.com/v1",
    "api_key":              "",
    "model":                "gpt-4o-mini",

    # System prompt
    "system_prompt":        "You are a helpful assistant. Respond in the same language the user writes in.",
    "system_prompt_file":   "",

    # Generation
    "max_history":          20,
    "temperature":          0.7,
    "max_tokens":           4096,
    "stream":               True,

    # Round-robin keys
    "round_robin":          False,
    "round_robin_keys":     [],
    "round_robin_strategy": "sequential",  # sequential | random | least-used

    # Sub-agent
    "sub_agent_enabled":    False,
    "sub_agent_model":      "",  # empty = use main model
    "sub_agent_max_tokens": 2048,

    # Permissions
    "permission_mode":      "ask",  # ask | auto

    # UI
    "theme":                "minimal",  # minimal | cyber | aurora
}


# ── Loader ────────────────────────────────────────────────────────

def load_config(path: str | None = None) -> dict[str, Any]:
    """Load config from JSON file, merging with defaults."""
    config = DEFAULT_CONFIG.copy()
    file_path = Path(path) if path else Path(CONFIG_FILE)

    if file_path.exists():
        with open(file_path) as f:
            try:
                user_cfg = json.load(f)
            except json.JSONDecodeError as e:
                raise SystemExit(f"Config parse error in {file_path}: {e}")
        config.update(user_cfg)

    # Env var overrides
    if not config["api_key"]:
        config["api_key"] = os.environ.get("OPENAI_API_KEY", "")

    if env_model := os.environ.get("OXY_MODEL"):
        config["model"] = env_model

    if env_base := os.environ.get("OXY_BASE_URL"):
        config["base_url"] = env_base

    if env_theme := os.environ.get("OXY_THEME"):
        config["theme"] = env_theme

    return config


def save_config(config: dict[str, Any], path: Path | None = None):
    """Write config to JSON file."""
    file_path = path or Path(CONFIG_FILE)
    with open(file_path, "w") as f:
        json.dump(config, f, indent=2, ensure_ascii=False)


# ── System Prompt ─────────────────────────────────────────────────

def resolve_system_prompt(config: dict[str, Any]) -> str:
    """Load system prompt from file or inline config.

    Priority:
      1. system_prompt_file in config → read that file
      2. system_prompt.md next to config → read it
      3. system_prompt string in config
    """
    # Explicit file path
    prompt_file = config.get("system_prompt_file", "")
    if prompt_file:
        p = Path(prompt_file).expanduser()
        if p.exists():
            text = p.read_text(encoding="utf-8").strip()
            if text:
                return text

    # Default file next to script
    default = Path(SYSTEM_PROMPT_FILE)
    if default.exists():
        text = default.read_text(encoding="utf-8").strip()
        if text:
            return text

    # Inline string
    return config.get("system_prompt", "")


# ── Validation ────────────────────────────────────────────────────

def validate_config(config: dict[str, Any]) -> list[str]:
    """Return list of warnings (empty = all good)."""
    warnings = []

    if not config["api_key"] and not config.get("round_robin_keys"):
        warnings.append("No API key configured")

    if config["round_robin"] and not config.get("round_robin_keys"):
        warnings.append("Round-robin enabled but no keys configured")

    if config["theme"] not in ("minimal", "cyber", "aurora"):
        warnings.append(f"Unknown theme '{config['theme']}', falling back to 'minimal'")
        config["theme"] = "minimal"

    if config["round_robin_strategy"] not in ("sequential", "random", "least-used"):
        warnings.append(f"Unknown strategy '{config['round_robin_strategy']}', using 'sequential'")
        config["round_robin_strategy"] = "sequential"

    return warnings
