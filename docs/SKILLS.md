# OXY Skills & Progressive Disclosure

OXY adopts the **AgentSkills standard** for progressive disclosure of domain knowledge. Instead of bloating the system prompt with thousands of tokens of procedural rules, instructions are organized into modular, on-demand skill packages.

---

## 1. Why Progressive Disclosure?

Monolithic system prompts have three critical failure modes:
1. **Token Inefficiency**: Storing deploy guidelines, review rules, and testing procedures in the system prompt consumes 5,000–15,000 tokens on every turn.
2. **Instruction Drift**: Conflicting instructions between different workflows cause the model to ignore critical constraints.
3. **KV Cache Invalidation**: Frequently editing monolithic prompts invalidates the KV cache, driving up latency and cost.

**The OXY Solution:**
- Skills are indexed in the system prompt as a compact, single-line summary (~15 tokens per skill).
- Full instructions are loaded into context only when triggered by user slash commands (e.g., `/review`) or when the model calls `load_skill(name)`.

---

## 2. Directory Layout & Discovery Hierarchy

OXY discovers skills across two tiers:

```
~/.oxy/skills/                     # User-Level Skills (Available in all projects)
└── benchmark/
    └── SKILL.md

<project_root>/.oxy/skills/        # Project-Level Skills (Highest priority)
├── deploy/
│   └── SKILL.md
└── migrate-db/
    └── SKILL.md
```

---

## 3. The `SKILL.md` Specification

Each skill is a markdown file with YAML frontmatter:

```markdown
---
name: deploy
description: Deploy application to staging or production environments
triggers: [deploy, release, انتشار, دیپلوی]
---

# Procedural Workflow: Deployment

## Prerequisites
1. Ensure all local tests pass before deployment.
2. Check `git_status` to ensure no uncommitted changes remain.

## Steps
1. Run `bash` with `npm run build` or `cargo build --release`.
2. Execute deployment script: `./scripts/deploy.sh staging`.
3. Verify endpoint health: `curl -s https://staging.example.com/health`.
```

### Frontmatter Schema

| Field | Type | Description |
| :--- | :--- | :--- |
| `name` | `string` | Unique identifier (e.g., `test`, `review`, `deploy`). Used in slash commands (`/<name>`). |
| `description` | `string` | 1-line description displayed in `/skills` and the compact system prompt index. |
| `triggers` | `list[str]` | Keywords (English & Persian) that trigger automatic skill resolution. |

---

## 4. Built-in Skills Catalog

OXY includes four production-ready built-in skills:

### 1. `/test` — Test Suite Runner & Diagnostician
- **Triggers**: `test`, `pytest`, `npm test`, `تست`, `آزمون`
- **Workflow**: Discovers the project test runner (pytest, vitest, jest, cargo test), isolates exact failure traces, inspects relevant code with `read_file`, produces minimal targeted fixes, and re-verifies.

### 2. `/review` — Senior Architectural & Simplicity Review
- **Triggers**: `review`, `code review`, `بررسی کد`, `بازبینی`
- **Philosophy**: *"Never write complex or bloated code when a simpler architecture achieves the exact same result."*
- **Dimensions**: Simplicity, edge-case resilience, security floor adherence, and algorithmic performance.

### 3. `/refactor` — Clean Code Refactoring
- **Triggers**: `refactor`, `simplify`, `clean code`, `ساده سازی`, `ریفکتور`
- **Workflow**: Reads target files, formulates a step-by-step simplification plan, preserves 100% backward compatibility, eliminates dead code, and verifies via targeted diffs.

### 4. `/git-commit` — Conventional Git Commit Generator
- **Triggers**: `commit`, `git commit`, `کامیتر`, `ثبت تغییرات`
- **Workflow**: Inspects staged and unstaged diffs via `git_status` and `git diff`, drafting precise imperative commit messages following standard conventional specifications.

---

## 5. Authoring a Custom Skill (Quick Tutorial)

To add a custom skill for database migrations in your project:

1. Create the directory:
   ```bash
   mkdir -p .oxy/skills/db-migrate
   ```

2. Create `.oxy/skills/db-migrate/SKILL.md`:
   ```markdown
   ---
   name: db-migrate
   description: Run and verify database schema migrations
   triggers: [migrate, migration, دیتابیس, مایگریشن]
   ---

   # Skill: Database Migration Protocol
   1. Run `git status` to verify current migration scripts in `alembic/versions/`.
   2. Execute migration in dry-run mode: `bash` with `alembic upgrade --sql head`.
   3. Review SQL output for table locks or dangerous drop statements.
   4. Apply migrations: `alembic upgrade head`.
   ```

3. Type `/skills` in the OXY cockpit to see your new skill registered immediately.
