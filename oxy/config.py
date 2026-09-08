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
    "sub_agent_max_iterations": 6,  # tool-loop budget for isolated sub-agent runs

    # Permissions
    "permission_mode":      "ask",  # ask | auto

    # UI & Localization
    "theme":                "minimal",  # minimal | cyber | aurora
    "language":             "en",       # en | fa | zh
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

    if env_lang := os.environ.get("OXY_LANG"):
        config["language"] = env_lang

    try:
        from .i18n import set_language
        set_language(config.get("language", "en"))
    except Exception:
        pass

    return config


def save_config(config: dict[str, Any], path: Path | None = None):
    """Atomically write config to JSON file using tmp file + fsync + replace."""
    file_path = path or Path(CONFIG_FILE)
    file_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = file_path.with_suffix(f".tmp.{os.getpid()}")
    try:
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=2, ensure_ascii=False)
            f.flush()
            os.fsync(f.fileno())
        tmp_path.replace(file_path)
    except Exception:
        if tmp_path.exists():
            try:
                tmp_path.unlink()
            except OSError:
                pass
        raise


# ── System Prompt ─────────────────────────────────────────────────

def resolve_system_prompt(config: dict[str, Any]) -> str:
    """Load system prompt from file or inline config.

    Priority:
      1. system_prompt_file in config → read that file (explicit opt-in only)
      2. system_prompt string in config (default)

    NOTE: This function deliberately NEVER auto-loads an adjacent
    ``system_prompt.md`` file. Implicit ambient file loading is a classic
    prompt-injection vector: merely launching OXY from a directory containing
    such a file would silently activate attacker-controlled instructions.
    Users must point ``system_prompt_file`` at the file explicitly.
    """
    # Explicit file path
    prompt_file = config.get("system_prompt_file", "")
    if prompt_file:
        p = Path(prompt_file).expanduser()
        if p.exists():
            text = p.read_text(encoding="utf-8").strip()
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

    try:
        from .themes import THEME_REGISTRY
        THEME_REGISTRY.reload()
        available = THEME_REGISTRY.list_names()
    except Exception:
        available = ["minimal", "cyber", "aurora"]
    if config.get("theme") not in available:
        warnings.append(f"Unknown theme '{config.get('theme')}', falling back to 'minimal'")
        config["theme"] = "minimal"

    if config.get("language") not in ("en", "fa", "zh"):
        warnings.append(f"Unknown language '{config.get('language')}', falling back to 'en'")
        config["language"] = "en"

    if config["round_robin_strategy"] not in ("sequential", "random", "least-used"):
        warnings.append(f"Unknown strategy '{config['round_robin_strategy']}', using 'sequential'")
        config["round_robin_strategy"] = "sequential"

    return warnings
