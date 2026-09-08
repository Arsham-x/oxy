"""
OXY Themes — Theme definitions, custom theme loading, and validation.

Supports:
  - Builtin themes: minimal, cyber, aurora
  - User custom themes loaded from ~/.oxy/themes/*.json and .oxy/themes/*.json
  - Strict key validation with minimal fallback so theme reads never raise KeyError
  - Mapping string box identifiers ("SIMPLE", "DOUBLE", "ROUNDED", etc.) to rich.box
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from rich import box


BOX_MAPPING = {
    "SIMPLE": box.SIMPLE,
    "SIMPLE_HEAD": box.SIMPLE_HEAD,
    "SIMPLE_HEAVY": box.SIMPLE_HEAVY,
    "DOUBLE": box.DOUBLE,
    "DOUBLE_EDGE": box.DOUBLE_EDGE,
    "ROUNDED": box.ROUNDED,
    "HEAVY": box.HEAVY,
    "HEAVY_EDGE": box.HEAVY_EDGE,
    "HEAVY_HEAD": box.HEAVY_HEAD,
    "SQUARE": box.SQUARE,
    "MINIMAL": box.MINIMAL,
    "HORIZONTALS": box.HORIZONTALS,
    "ASCII": box.ASCII,
}


REQUIRED_THEME_KEYS = (
    "name",
    "user_style",
    "ai_title",
    "ai_border",
    "ai_box",
    "system_style",
    "error_style",
    "dim",
    "accent",
    "success",
    "warning",
    "spinner",
    "spinner_style",
    "prompt_char",
    "prompt_style",
    "toolbar_bg",
    "toolbar_fg",
    "welcome_border",
    "welcome_box",
    "rule_style",
    "sub_agent",
    "tool_icon",
    "think_icon",
)


BUILTIN_THEMES: dict[str, dict[str, Any]] = {
    "minimal": {
        "name":           "Minimal",
        "user_style":     "bold",
        "ai_title":       "[dim]oxy[/]",
        "ai_border":      "dim",
        "ai_box":         box.SIMPLE,
        "system_style":   "dim italic",
        "error_style":    "red",
        "dim":            "dim",
        "accent":         "blue",
        "success":        "green",
        "warning":        "yellow",
        "spinner":        "dots",
        "spinner_style":  "dim",
        "prompt_char":    "❯",
        "prompt_style":   "dim",
        "toolbar_bg":     "#1a1a1a",
        "toolbar_fg":     "#888888",
        "welcome_border": "dim",
        "welcome_box":    box.SIMPLE,
        "rule_style":     "dim",
        "sub_agent":      "dim italic",
        "tool_icon":      "●",
        "think_icon":     "◆",
    },
    "cyber": {
        "name":           "Cyber",
        "user_style":     "bold cyan",
        "ai_title":       "[bold green]⟫ OXY[/]",
        "ai_border":      "green",
        "ai_box":         box.DOUBLE,
        "system_style":   "bold yellow",
        "error_style":    "bold red",
        "dim":            "bright_black",
        "accent":         "cyan",
        "success":        "green",
        "warning":        "yellow",
        "spinner":        "dots12",
        "spinner_style":  "cyan",
        "prompt_char":    "❯",
        "prompt_style":   "bold cyan",
        "toolbar_bg":     "#0a0a2e",
        "toolbar_fg":     "#00ff88",
        "welcome_border": "cyan",
        "welcome_box":    box.DOUBLE,
        "rule_style":     "cyan",
        "sub_agent":      "bold magenta",
        "tool_icon":      "●",
        "think_icon":     "◆",
    },
    "aurora": {
        "name":           "Aurora",
        "user_style":     "bold #e0b0ff",
        "ai_title":       "[bold #7fdbca]✦ oxy[/]",
        "ai_border":      "#7fdbca",
        "ai_box":         box.ROUNDED,
        "system_style":   "#f0c674",
        "error_style":    "#ff6b6b",
        "dim":            "#666680",
        "accent":         "#c792ea",
        "success":        "#7fdbca",
        "warning":        "#f0c674",
        "spinner":        "moon",
        "spinner_style":  "#7fdbca",
        "prompt_char":    "❯",
        "prompt_style":   "#c792ea",
        "toolbar_bg":     "#1e1e3f",
        "toolbar_fg":     "#7fdbca",
        "welcome_border": "#c792ea",
        "welcome_box":    box.ROUNDED,
        "rule_style":     "#7fdbca",
        "sub_agent":      "italic #c792ea",
        "tool_icon":      "●",
        "think_icon":     "◆",
    },
}


def _resolve_box(val: Any, default: Any) -> Any:
    if isinstance(val, str):
        return BOX_MAPPING.get(val.upper(), default)
    return val or default


def validate_and_complete_theme(raw_theme: dict[str, Any], fallback: dict[str, Any] | None = None) -> dict[str, Any]:
    """Ensure a theme dictionary has all required keys, filling missing keys from fallback."""
    base = (fallback or BUILTIN_THEMES["minimal"]).copy()
    result = base.copy()
    for k, v in raw_theme.items():
        if v is not None:
            result[k] = v

    # Resolve box types if given as string identifiers
    result["ai_box"] = _resolve_box(result.get("ai_box"), base["ai_box"])
    result["welcome_box"] = _resolve_box(result.get("welcome_box"), base["welcome_box"])

    # Guarantee name is populated
    if "name" not in result or not result["name"]:
        result["name"] = raw_theme.get("name") or "Custom"

    return result


class ThemeRegistry:
    """Registry maintaining builtin and user-defined themes."""

    def __init__(self):
        self._themes: dict[str, dict[str, Any]] = {}
        self.reload()

    def reload(self):
        """Reload builtins and scan user theme directories."""
        self._themes.clear()
        for k, v in BUILTIN_THEMES.items():
            self._themes[k] = v.copy()

        # Scan user theme locations
        search_dirs = [
            Path.home() / ".oxy" / "themes",
            Path.cwd() / ".oxy" / "themes",
        ]
        for sdir in search_dirs:
            if sdir.exists() and sdir.is_dir():
                for json_file in sdir.glob("*.json"):
                    try:
                        with open(json_file, encoding="utf-8") as f:
                            raw = json.load(f)
                        if isinstance(raw, dict):
                            slug = json_file.stem.lower()
                            valid = validate_and_complete_theme(raw, self._themes.get("minimal"))
                            self._themes[slug] = valid
                    except Exception:
                        pass

    def get(self, name: str) -> dict[str, Any]:
        """Get a theme by name with minimal fallback and guaranteed key completeness."""
        normalized = (name or "").lower().strip()
        found = self._themes.get(normalized)
        if found:
            return found
        # Fallback to minimal
        return self._themes.get("minimal", BUILTIN_THEMES["minimal"])

    def list_names(self) -> list[str]:
        """List all available theme slugs."""
        return sorted(self._themes.keys())

    def register(self, name: str, theme_dict: dict[str, Any]):
        """Register or override a theme at runtime."""
        slug = name.lower().strip()
        self._themes[slug] = validate_and_complete_theme(theme_dict, self._themes.get("minimal"))

    @property
    def themes(self) -> dict[str, dict[str, Any]]:
        return self._themes


# Global registry singleton
THEME_REGISTRY = ThemeRegistry()
