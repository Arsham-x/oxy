"""
OXY Repo — Codebase awareness and active file tracker.

Inspired by Aider's repo map and active file management:
  - Detects Git repository root, current branch, and status
  - Scans project file tree (skipping noise dirs like .git, node_modules, .venv)
  - Manages active files added via `/add` and removed via `/drop`
  - Formats repo context into a concise overview injected into the system prompt
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

from .tools import IGNORED_DIRS


class RepoContext:
    """Tracks project root, git status, file structure, and active chat files."""

    def __init__(self, root: str | Path = "."):
        self.root = Path(root).expanduser().resolve()
        self.active_files: set[str] = set()
        self.is_git = False
        self.branch = ""
        self._detect_git()

    def _detect_git(self):
        """Check if current folder or parent is a git repository."""
        try:
            root_out = subprocess.check_output(
                ["git", "rev-parse", "--show-toplevel"],
                cwd=self.root,
                stderr=subprocess.DEVNULL,
                text=True,
            ).strip()
            if root_out:
                self.root = Path(root_out)
                self.is_git = True
                self.branch = subprocess.check_output(
                    ["git", "rev-parse", "--abbrev-ref", "HEAD"],
                    cwd=self.root,
                    stderr=subprocess.DEVNULL,
                    text=True,
                ).strip()
        except (subprocess.CalledProcessError, FileNotFoundError):
            self.is_git = False
            self.branch = ""

    def add_file(self, path: str) -> tuple[bool, str]:
        """Add a file to the active context (/add)."""
        p = Path(path).expanduser()
        if not p.is_absolute():
            p = (self.root / p).resolve()
        else:
            p = p.resolve()

        if not p.exists():
            return False, f"File '{path}' does not exist."
        if p.is_dir():
            return False, f"'{path}' is a directory. Specify individual files."

        rel = os.path.relpath(p, self.root)
        self.active_files.add(rel)
        lines = len(p.read_text(encoding="utf-8", errors="ignore").splitlines())
        return True, f"Added '{rel}' ({lines} lines) to active context."

    def drop_file(self, path: str) -> tuple[bool, str]:
        """Remove a file from active context (/drop)."""
        rel = os.path.relpath(Path(path).expanduser().resolve(), self.root)
        if rel in self.active_files:
            self.active_files.remove(rel)
            return True, f"Dropped '{rel}' from active context."
        # Try matching by filename
        for f in list(self.active_files):
            if f == path or f.endswith(f"/{path}"):
                self.active_files.remove(f)
                return True, f"Dropped '{f}' from active context."
        return False, f"File '{path}' is not in active context."

    def clear_active_files(self):
        """Clear all active files."""
        self.active_files.clear()

    def get_file_tree(self, max_files: int = 50) -> str:
        """Return a compact relative path list of project files."""
        files_found = []
        for root, dirs, files in os.walk(self.root):
            dirs[:] = [d for d in dirs if d not in IGNORED_DIRS and not d.startswith(".")]

            for f in sorted(files):
                if f.startswith("."):
                    continue
                full_path = Path(root) / f
                rel = os.path.relpath(full_path, self.root)
                files_found.append(rel)
                if len(files_found) >= max_files:
                    break
            if len(files_found) >= max_files:
                break

        if not files_found:
            return "(no files found)"

        lines = [f"  - {f}" for f in sorted(files_found)]
        if len(lines) >= max_files:
            lines.append("  ... (more files omitted)")
        return "\n".join(lines)

    def get_active_files_content(self, max_lines_per_file: int = 300) -> str:
        """Format the content of all actively tracked files."""
        if not self.active_files:
            return ""

        chunks = ["### Active Files in Context:"]
        for rel in sorted(self.active_files):
            p = self.root / rel
            if not p.exists():
                continue
            try:
                lines = p.read_text(encoding="utf-8", errors="replace").splitlines()
            except Exception:
                continue

            truncated = False
            if len(lines) > max_lines_per_file:
                lines = lines[:max_lines_per_file]
                truncated = True

            numbered = [f"{i + 1:4d} | {line}" for i, line in enumerate(lines)]
            file_block = f"\n#### `{rel}`\n```\n" + "\n".join(numbered) + "\n```"
            if truncated:
                file_block += f"\n[Note: `{rel}` truncated to {max_lines_per_file} lines]"
            chunks.append(file_block)

        return "\n".join(chunks)

    def get_system_prompt_context(self) -> str:
        """Build the codebase summary block for injection into system prompt."""
        parts = ["## Codebase Context"]

        # Git info
        if self.is_git:
            parts.append(f"Git Repository: `{self.root.name}` (branch: `{self.branch}`)")
        else:
            parts.append(f"Working Directory: `{self.root}`")

        # Active files
        if self.active_files:
            parts.append(f"Active Files tracked: {', '.join(sorted(self.active_files))}")
            active_content = self.get_active_files_content()
            if active_content:
                parts.append(active_content)
        else:
            # File tree overview
            parts.append("Project Structure:\n" + self.get_file_tree(max_files=40))

        return "\n\n".join(parts)
