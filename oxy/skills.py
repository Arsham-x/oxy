"""
OXY Skills — Progressive disclosure procedural instructions system (AgentSkills / Claude Code standard).

Architectural Pattern:
  1. Ultra-Lean Footprint: Rather than polluting the system prompt with thousands of tokens
     of domain-specific instructions, skills are indexed as compact 1-line summaries (~15 tokens/skill).
  2. Progressive Disclosure: Full instructions from SKILL.md are loaded on-demand when explicitly
     triggered by user slash commands (e.g. /review, /test) or model tool calls (load_skill).
  3. Multilingual Persian Triggers: Includes Persian synonym triggers to ensure natural
     invocation in both English and Persian conversations.
  4. Layered Discovery: Scans project-level (.oxy/skills/) and user-level (~/.oxy/skills/).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass
class Skill:
    name: str
    description: str
    triggers: list[str]
    content: str
    source_path: str
    is_builtin: bool = False

    def to_summary_line(self) -> str:
        """Compact 1-line summary for system prompt index."""
        trigger_str = f" [triggers: {', '.join(self.triggers)}]" if self.triggers else ""
        return f"- /{self.name}: {self.description}{trigger_str}"


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  Built-in Curated Skills
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

BUILTIN_SKILLS = [
    Skill(
        name="test",
        description="Run test suite, identify failing test cases, and synthesize targeted fixes.",
        triggers=["test", "pytest", "npm test", "تست", "آزمون"],
        content="""# Skill: Test Suite Runner & Diagnostician

## Protocol:
1. Discover the test framework in use (pytest, unittest, vitest, jest, cargo test, go test).
2. Execute test runner via `bash` tool with appropriate flags.
3. If failures occur:
   - Identify the exact failure line, assertion error, and traceback.
   - Use `read_file` to inspect the code around the failure.
   - Do NOT rewrite unrelated code. Propose the minimal, surgical fix.
   - Re-run the specific failing test to verify the fix before declaring completion.
""",
        source_path="<builtin>",
        is_builtin=True,
    ),
    Skill(
        name="review",
        description="Rigorous senior code review focused on correctness, edge cases, and zero-bloat simplicity.",
        triggers=["review", "code review", "بررسی کد", "بازبینی"],
        content="""# Skill: Senior Architectural & Code Review

## Core Directive:
"تا وقتی میشه با یک کد ساده تر به همون نتیجه رسید، نباید کد پیچیده ای نوشت"
(Do not write complex or bloated code when a simpler architecture achieves the exact same result.)

## Review Dimensions:
1. **Simplicity & Anti-Bloat**: Has unnecessary abstraction, over-engineering, or speculative generalization been introduced?
2. **Correctness & Edge Cases**: Empty inputs, unicode handling, race conditions, resource leaks, off-by-one errors.
3. **Security Floor**: Command injections, path traversals, credential exposure, unvalidated inputs.
4. **Performance**: Algorithmic complexity (O(N^2) vs O(N)), redundant I/O, unindexed queries.

Provide structured findings ranked by severity: Critical, High, Medium, Low.
""",
        source_path="<builtin>",
        is_builtin=True,
    ),
    Skill(
        name="refactor",
        description="Cleanly simplify code and remove dead weight without altering external behavior.",
        triggers=["refactor", "simplify", "clean code", "ساده سازی", "ریفکتور"],
        content="""# Skill: Clean Code Refactoring

## Protocol:
1. Read target files completely before touching any code.
2. Formulate a step-by-step simplification plan.
3. Keep public APIs and external contracts 100% backward-compatible.
4. Eliminate duplicated logic, unnecessary layers, and dead variables.
5. Use `edit_file` for targeted replacements to preserve git blame where possible.
6. Verify against existing tests or run basic syntax checks after editing.
""",
        source_path="<builtin>",
        is_builtin=True,
    ),
    Skill(
        name="git-commit",
        description="Draft clean, conventional git commit message adhering to repo conventions.",
        triggers=["commit", "git commit", "کامیتر", "ثبت تغییرات"],
        content="""# Skill: Conventional Git Commit Generator

## Protocol:
1. Run `git_status` to view staged and unstaged modifications.
2. Run `bash` with `git diff --staged` or `git diff` to understand exact diffs.
3. Craft a concise, imperative commit header: `<type>(<scope>): <summary>`
   - Types: feat, fix, refactor, perf, test, docs, chore.
   - Summary: Max 50 characters, present tense, no period at end.
4. Include bullet points explaining the *why* and *what*, not just file listings.
""",
        source_path="<builtin>",
        is_builtin=True,
    ),
]


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  Skill Manager
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class SkillManager:
    """Discovers, indexes, and loads on-demand procedural skills."""

    def __init__(self, workspace_dir: Path | str | None = None):
        self.workspace_dir = Path(workspace_dir or Path.cwd()).resolve()
        self.user_skills_dir = Path.home() / ".oxy" / "skills"
        self.project_skills_dir = self.workspace_dir / ".oxy" / "skills"
        self._skills: dict[str, Skill] = {}
        self.reload_skills()

    def reload_skills(self):
        """Discover all skills from builtins, user directory, and project directory."""
        self._skills = {}

        # 1. Load built-ins
        for b_skill in BUILTIN_SKILLS:
            self._skills[b_skill.name] = b_skill

        # 2. Load user-level skills (~/.oxy/skills/<name>/SKILL.md)
        self._load_from_directory(self.user_skills_dir)

        # 3. Load project-level skills (.oxy/skills/<name>/SKILL.md - highest priority)
        self._load_from_directory(self.project_skills_dir)

    def _load_from_directory(self, base_dir: Path):
        """Parse SKILL.md files from a directory."""
        if not base_dir.exists():
            return

        for skill_file in base_dir.glob("*/SKILL.md"):
            skill_name = skill_file.parent.name.lower()
            try:
                raw_text = skill_file.read_text(encoding="utf-8")
                skill = self._parse_skill_file(skill_name, raw_text, str(skill_file))
                if skill:
                    self._skills[skill.name] = skill
            except Exception:
                continue

    @staticmethod
    def _parse_skill_file(default_name: str, text: str, file_path: str) -> Skill | None:
        """Parse YAML frontmatter and markdown body from SKILL.md."""
        frontmatter_match = re.match(r"^---\s*\n(.*?)\n---\s*\n(.*)$", text, re.DOTALL)
        if not frontmatter_match:
            return Skill(
                name=default_name,
                description="Custom procedural skill",
                triggers=[default_name],
                content=text,
                source_path=file_path,
            )

        fm_text, body = frontmatter_match.groups()
        meta = {}
        for line in fm_text.splitlines():
            line = line.strip()
            if ":" in line:
                k, v = line.split(":", 1)
                k = k.strip()
                v = v.strip()
                if v.startswith("[") and v.endswith("]"):
                    items = [x.strip().strip("'\"") for x in v[1:-1].split(",") if x.strip()]
                    meta[k] = items
                else:
                    meta[k] = v.strip("'\"")

        name = meta.get("name", default_name)
        description = meta.get("description", f"Run {name} procedural skill")
        raw_triggers = meta.get("triggers") or meta.get("trigger") or [name]
        if isinstance(raw_triggers, str):
            triggers = [t.strip() for t in raw_triggers.split(",") if t.strip()]
        else:
            triggers = list(raw_triggers)

        return Skill(
            name=name,
            description=description,
            triggers=triggers,
            content=body.strip(),
            source_path=file_path,
        )

    def get_skill(self, name: str) -> Skill | None:
        """Find a skill by exact name or trigger match."""
        name_clean = name.strip().lower().lstrip("/")
        if name_clean in self._skills:
            return self._skills[name_clean]

        for s in self._skills.values():
            if name_clean in [t.lower() for t in s.triggers]:
                return s
        return None

    def list_skills(self) -> list[Skill]:
        """Return all available skills."""
        return list(self._skills.values())

    def generate_compact_prompt_index(self) -> str:
        """Generate a minimal ~15 tokens/skill index for system prompt injection."""
        if not self._skills:
            return ""

        lines = ["## Available Procedural Skills (Load via `load_skill` or user /<skill>):"]
        for s in self._skills.values():
            lines.append(s.to_summary_line())
        return "\n".join(lines)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  Tool Integration: load_skill
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def tool_load_skill(name: str, manager: SkillManager | None = None) -> dict[str, Any]:
    """Tool implementation for model to load skill instructions on demand."""
    mgr = manager or SkillManager()
    skill = mgr.get_skill(name)
    if not skill:
        available = [s.name for s in mgr.list_skills()]
        return {
            "success": False,
            "error": f"Skill '{name}' not found. Available skills: {', '.join(available)}",
        }

    return {
        "success": True,
        "name": skill.name,
        "description": skill.description,
        "instructions": skill.content,
    }
