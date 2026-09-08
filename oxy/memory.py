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

import os
import re
from pathlib import Path
from typing import Any


MEMORY_DIR = Path.home() / ".oxy" / "memory"
MEMORY_INDEX_FILE = MEMORY_DIR / "MEMORY.md"
MAX_INDEX_LINES = 200
MAX_INDEX_BYTES = 25_000


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


def get_memory_index_text() -> str:
    """Return the MEMORY.md content, clamped to 200 lines / 25KB."""
    get_memory_dir()
    if not MEMORY_INDEX_FILE.exists():
        return ""

    try:
        content = MEMORY_INDEX_FILE.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return ""

    lines = content.splitlines()
    if len(lines) > MAX_INDEX_LINES:
        lines = lines[:MAX_INDEX_LINES]
        lines.append(f"\n... ({len(content.splitlines()) - MAX_INDEX_LINES} more memories indexed on disk)")

    clamped = "\n".join(lines)
    if len(clamped.encode("utf-8")) > MAX_INDEX_BYTES:
        clamped = clamped[:MAX_INDEX_BYTES] + "\n... (index truncated)"

    return clamped.strip()


def save_memory(
    slug: str,
    title: str,
    category: str,
    content: str,
    description: str = "",
) -> str:
    """Save a memory to its own file and update MEMORY.md."""
    mdir = get_memory_dir()
    slug_clean = re.sub(r"[^a-zA-Z0-9_\-]", "_", slug.strip().lower())
    if not slug_clean:
        slug_clean = "note"

    filename = f"{slug_clean}.md"
    file_path = mdir / filename

    desc = description.strip() or title.strip()

    # Frontmatter + content
    file_content = (
        f"---\n"
        f"title: {title}\n"
        f"category: {category}\n"
        f"description: {desc}\n"
        f"---\n\n"
        f"{content.strip()}\n"
    )

    file_path.write_text(file_content, encoding="utf-8")

    # Update MEMORY.md index
    index_text = MEMORY_INDEX_FILE.read_text(encoding="utf-8", errors="replace")
    pointer = f"- [{title}]({filename}) — {desc}"

    # Check if pointer already exists, update or append
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

    MEMORY_INDEX_FILE.write_text("\n".join(new_lines) + "\n", encoding="utf-8")
    return f"Saved memory '{title}' ({category}) → {filename}"


def recall_memory(query: str) -> list[dict[str, Any]]:
    """Search memory index and topic files for matching queries."""
    mdir = get_memory_dir()
    q_lower = query.strip().lower()
    results = []

    for f in mdir.glob("*.md"):
        if f.name == "MEMORY.md":
            continue
        try:
            text = f.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue

        if q_lower in text.lower() or q_lower in f.stem.lower():
            # Parse frontmatter if present
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

            results.append({
                "slug": f.stem,
                "title": title,
                "category": category,
                "description": desc,
                "body": body[:500] + ("..." if len(body) > 500 else ""),
                "file": f.name,
            })

    return results


def list_memories() -> list[dict[str, str]]:
    """Return all stored memories."""
    mdir = get_memory_dir()
    memories = []

    for f in sorted(mdir.glob("*.md")):
        if f.name == "MEMORY.md":
            continue
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
        })

    return memories


def delete_memory(slug: str) -> bool:
    """Delete a memory file and remove from index."""
    mdir = get_memory_dir()
    slug_clean = re.sub(r"[^a-zA-Z0-9_\-]", "_", slug.strip().lower())
    f = mdir / f"{slug_clean}.md"
    if not f.exists():
        return False

    f.unlink()

    # Remove from index
    if MEMORY_INDEX_FILE.exists():
        lines = MEMORY_INDEX_FILE.read_text(encoding="utf-8").splitlines()
        filtered = [l for l in lines if f"({slug_clean}.md)" not in l]
        MEMORY_INDEX_FILE.write_text("\n".join(filtered) + "\n", encoding="utf-8")

    return True


def clear_all_memories():
    """Clear all memory files."""
    mdir = get_memory_dir()
    for f in mdir.glob("*.md"):
        f.unlink()
    MEMORY_INDEX_FILE.write_text(
        "# OXY Memory Index\n\nLearned facts and user preferences across sessions.\n\n",
        encoding="utf-8",
    )
