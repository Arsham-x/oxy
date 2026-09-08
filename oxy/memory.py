"""
OXY Memory — Persistent, file-based auto-memory system.

Inspired by Claude Code's memory architecture:
  - Stores learned rules, user preferences, and project facts across sessions
  - Stored at ~/.oxy/memory/ or project-local .oxy/memory/
  - MEMORY.md is an index clamped to 200 lines / 25KB, injected into system prompt
  - Individual topic files store detailed knowledge
  - Categories: user, feedback, project, reference
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any


MEMORY_DIR = Path.home() / ".oxy" / "memory"
MEMORY_INDEX_FILE = MEMORY_DIR / "MEMORY.md"
MAX_INDEX_LINES = 200
MAX_INDEX_BYTES = 25_000

_project_memory_root: Path | None = None


def set_project_memory_root(path: Path | str | None) -> Path | None:
    """Pin a project-scoped memory overlay root (workspace/.oxy/memory/).

    Passing None clears the overlay, restoring global-only behavior.
    """
    global _project_memory_root
    _project_memory_root = Path(path).expanduser().resolve() if path else None
    return _project_memory_root


def get_project_memory_dir() -> Path | None:
    """Return the active project memory dir, creating it on first use."""
    if _project_memory_root is None:
        return None
    pdir = _project_memory_root / ".oxy" / "memory"
    pdir.mkdir(parents=True, exist_ok=True)
    return pdir


def get_memory_dir() -> Path:
    """Ensure and return the memory directory."""
    MEMORY_DIR.mkdir(parents=True, exist_ok=True)
    if not MEMORY_INDEX_FILE.exists():
        MEMORY_INDEX_FILE.write_text(
            "# OXY Memory Index\n\n"
            "Learned facts, user preferences, and project guidelines across sessions.\n\n",
            encoding="utf-8",
        )
    return MEMORY_DIR


def _read_index_file(index_file: Path) -> str:
    try:
        content = index_file.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return ""
    return content


def _clamp_index(text: str) -> str:
    lines = text.splitlines()
    if len(lines) > MAX_INDEX_LINES:
        lines = lines[:MAX_INDEX_LINES]
        lines.append(f"\n... ({len(text.splitlines()) - MAX_INDEX_LINES} more memories indexed on disk)")
    clamped = "\n".join(lines)
    if len(clamped.encode("utf-8")) > MAX_INDEX_BYTES:
        clamped = clamped[:MAX_INDEX_BYTES] + "\n... (index truncated)"
    return clamped.strip()


def get_memory_index_text() -> str:
    """Return MEMORY.md content (global + project overlay), clamped to 200 lines / 25KB."""
    get_memory_dir()
    parts: list[str] = []
    if MEMORY_INDEX_FILE.exists():
        parts.append(_read_index_file(MEMORY_INDEX_FILE))
    pdir = get_project_memory_dir()
    if pdir is not None:
        p_index = pdir / "MEMORY.md"
        if p_index.exists():
            parts.append("## Project Memory (local overlay)\n" + _read_index_file(p_index))
    return _clamp_index("\n\n".join(p for p in parts if p.strip()))


def _write_memory_file(
    mdir: Path,
    index_file: Path,
    slug: str,
    title: str,
    category: str,
    content: str,
    description: str = "",
) -> str:
    slug_clean = re.sub(r"[^a-zA-Z0-9_\-]", "_", slug.strip().lower()) or "note"
    filename = f"{slug_clean}.md"
    file_path = mdir / filename
    desc = description.strip() or title.strip()
    file_content = (
        f"---\n"
        f"title: {title}\n"
        f"category: {category}\n"
        f"description: {desc}\n"
        f"---\n\n"
        f"{content.strip()}\n"
    )
    file_path.write_text(file_content, encoding="utf-8")
    index_text = index_file.read_text(encoding="utf-8", errors="replace") if index_file.exists() else ""
    pointer = f"- [{title}]({filename}) — {desc}"
    lines = index_text.splitlines()
    found = False
    new_lines = []
    for line in lines:
        if f"({filename})" in line:
            new_lines.append(pointer)
            found = True
        else:
            new_lines.append(line)
    if not found:
        new_lines.append(pointer)
    index_file.write_text("\n".join(new_lines) + "\n", encoding="utf-8")
    return f"Saved memory '{title}' ({category}) → {filename}"


def save_memory(
    slug: str,
    title: str,
    category: str,
    content: str,
    description: str = "",
    scope: str = "global",
) -> str:
    """Save a memory (global ~/.oxy/memory or project .oxy/memory overlay)."""
    if scope == "project":
        pdir = get_project_memory_dir() or get_memory_dir()
        p_index = pdir / "MEMORY.md"
        if not p_index.exists():
            p_index.write_text("# OXY Project Memory\n\nLocal workspace facts and rules.\n\n", encoding="utf-8")
        return _write_memory_file(pdir, p_index, slug, title, category, content, description)
    mdir = get_memory_dir()
    return _write_memory_file(mdir, MEMORY_INDEX_FILE, slug, title, category, content, description)


def _collect_memory_files() -> list[tuple[Path, str]]:
    """Return (file_path, scope) pairs across global and project directories."""
    files: list[tuple[Path, str]] = []
    gdir = get_memory_dir()
    for f in gdir.glob("*.md"):
        if f.name != "MEMORY.md":
            files.append((f, "global"))

    pdir = get_project_memory_dir()
    if pdir and pdir.resolve() != gdir.resolve():
        for f in pdir.glob("*.md"):
            if f.name != "MEMORY.md":
                files.append((f, "project"))
    return files


def recall_memory(query: str) -> list[dict[str, Any]]:
    """Search memory index and topic files using ranked relevance scoring."""
    q_clean = query.strip().lower()
    if not q_clean:
        return []

    q_terms = [t for t in q_clean.split() if len(t) >= 2] or [q_clean]
    results = []

    for f, scope in _collect_memory_files():
        try:
            text = f.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue

        title = f.stem
        category = "general"
        desc = ""
        body = text

        if text.startswith("---"):
            parts = text.split("---", 2)
            if len(parts) >= 3:
                fm = parts[1]
                body = parts[2].strip()
                for line in fm.splitlines():
                    if line.startswith("title:"):
                        title = line.split(":", 1)[1].strip()
                    elif line.startswith("category:"):
                        category = line.split(":", 1)[1].strip()
                    elif line.startswith("description:"):
                        desc = line.split(":", 1)[1].strip()

        # Compute ranked relevance score
        score = 0
        stem_lower = f.stem.lower()
        title_lower = title.lower()
        desc_lower = desc.lower()
        body_lower = body.lower()

        if q_clean == stem_lower or q_clean == title_lower:
            score += 100
        elif q_clean in stem_lower or q_clean in title_lower:
            score += 60

        for term in q_terms:
            if term in title_lower:
                score += 30
            if term in desc_lower:
                score += 20
            occurrences = body_lower.count(term)
            score += min(50, occurrences * 5)

        # Local workspace boost
        if score > 0 and scope == "project":
            score += 15

        if score > 0:
            results.append({
                "slug": f.stem,
                "title": title,
                "category": category,
                "description": desc,
                "body": body[:500] + ("..." if len(body) > 500 else ""),
                "file": f.name,
                "score": score,
                "scope": scope,
            })

    results.sort(key=lambda x: x["score"], reverse=True)
    return results


def list_memories() -> list[dict[str, str]]:
    """Return all stored memories across global and project overlays."""
    memories = []

    for f, scope in sorted(_collect_memory_files(), key=lambda x: (x[1], x[0].stem)):
        try:
            text = f.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue

        title = f.stem
        category = "general"
        desc = ""
        if text.startswith("---"):
            parts = text.split("---", 2)
            if len(parts) >= 3:
                for line in parts[1].splitlines():
                    if line.startswith("title:"):
                        title = line.split(":", 1)[1].strip()
                    elif line.startswith("category:"):
                        category = line.split(":", 1)[1].strip()
                    elif line.startswith("description:"):
                        desc = line.split(":", 1)[1].strip()

        memories.append({
            "slug": f.stem,
            "title": title,
            "category": category,
            "description": desc,
            "file": f.name,
            "scope": scope,
        })

    return memories


def delete_memory(slug: str) -> bool:
    """Delete a memory file from project or global directory and update index."""
    slug_clean = re.sub(r"[^a-zA-Z0-9_\-]", "_", slug.strip().lower())
    deleted = False

    # Check project first, then global
    candidates = []
    pdir = get_project_memory_dir()
    if pdir:
        candidates.append((pdir, pdir / "MEMORY.md"))
    gdir = get_memory_dir()
    candidates.append((gdir, MEMORY_INDEX_FILE))

    for mdir, index_file in candidates:
        target = mdir / f"{slug_clean}.md"
        if target.exists():
            target.unlink()
            deleted = True
            if index_file.exists():
                lines = index_file.read_text(encoding="utf-8").splitlines()
                filtered = [l for l in lines if f"({slug_clean}.md)" not in l]
                index_file.write_text("\n".join(filtered) + "\n", encoding="utf-8")

    return deleted


def clear_all_memories():
    """Clear all memory files in both global and project-scoped storage."""
    gdir = get_memory_dir()
    for f in gdir.glob("*.md"):
        f.unlink()
    MEMORY_INDEX_FILE.write_text(
        "# OXY Memory Index\n\nLearned facts and user preferences across sessions.\n\n",
        encoding="utf-8",
    )

    pdir = get_project_memory_dir()
    if pdir and pdir.exists():
        for f in pdir.glob("*.md"):
            f.unlink()
        p_index = pdir / "MEMORY.md"
        p_index.write_text(
            "# OXY Project Memory\n\nLocal workspace facts and rules.\n\n",
            encoding="utf-8",
        )
