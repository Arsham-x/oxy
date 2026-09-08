# OXY Security Architecture & Host Protection

OXY operates directly in your local environment with native shell execution and file modification privileges. To prevent system compromise, accidental data destruction, and adversarial prompt injections, OXY implements a **hardened, defense-in-depth security model**.

---

## 1. Threat Model & Design Principles

| Threat Vector | Attack Scenario | OXY Mitigation |
| :--- | :--- | :--- |
| **Catastrophic Hallucination** | Model outputs `rm -rf /` or formats a partition during automated cleanup. | **Hardline Floor**: Categorically blocked before execution; cannot be overridden. |
| **Indirect Prompt Injection** | Untrusted repository file contains hidden instructions to rewrite agent steering files. | **Steering Protection Gate**: Edits to steering files (`system_prompt.md`, `.cursorrules`) require mandatory human confirmation. |
| **Credential Exfiltration** | Model attempts to read or curl private keys (`~/.ssh/id_rsa`, `~/.aws/credentials`). | **Credential Shield**: Direct reads or pipe extractions of private keys are categorically blocked. |
| **Autonomous Privilege Escalation** | Attacker leverages `--yolo` mode to overwrite system binaries or change configs. | **Non-Bypassable Constraint**: The security floor is decoupled from user permission flags. |

---

## 2. The Non-Bypassable Hardline Floor

Regardless of whether OXY is launched with `--permission-mode auto` or `--yolo`, the following operations are **unconditionally rejected**:

### Catastrophic Shell Patterns
```python
# Destructive root / home deletions
re.compile(r'\brm\s+(-[a-zA-Z]*r[a-zA-Z]*f[a-zA-Z]*)\s+(/|/\*|~|\$HOME|\./\.\.)(?:\s|$)')

# Filesystem formatting
re.compile(r'\bmkfs(?:\.[a-z0-9]+)?\s+')

# Raw block device overwrites
re.compile(r'\bdd\s+.*of=/dev/(?:sd|hd|nvme|vd|mmcblk)[a-z0-9]*')
re.compile(r'>\s*/dev/(?:sd|hd|nvme|vd|mmcblk)[a-z0-9]*')

# Fork bombs & denial of service
re.compile(r':\(\)\s*\{\s*:\s*\|\s*:\s*&\s*\}\s*;')

# System power control
re.compile(r'\b(shutdown|reboot|poweroff|halt|init\s+[06])\b')
```

### Protected Credential Paths
Access to the following paths (via `read_file`, `bash` redirection, or extraction utilities) is blocked:
- `~/.ssh/id_*` (SSH private & public keys)
- `~/.aws/credentials`
- `~/.netrc`
- `~/.pgpass`
- `/etc/shadow`, `/etc/master.passwd`

---

## 3. Agent Steering File Protection Gate

Indirect prompt injection occurs when an agent reads an untrusted file (e.g., in a cloned repo or user issue) that instructs it to alter its own system prompt or rules to maintain persistence.

To mitigate this, OXY maintains a strict registry of **Steering Files**:
- `system_prompt.md`
- `claude.md` / `CLAUDE.md`
- `agents.md` / `AGENTS.md`
- `.cursorrules`
- `.windsurfrules`
- `oxy_config.json`
- `.env`, `.env.local`, `.env.production`
- `.git/hooks/*`, `.git/config`

**Policy:** Any attempt by an LLM to mutate these files (via `write_file`, `edit_file`, or shell redirection `> file`) pauses execution and requires explicit interactive human confirmation, even in autonomous mode.

---

## 4. Permission Modes

| Mode | Flag | Behavior |
| :--- | :--- | :--- |
| **Interactive (Default)** | `--permission-mode ask` | Read-only tools execute automatically. Mutating operations (`write_file`, `edit_file`, `bash`, `save_memory`) prompt for confirmation (`yes` / `no` / `always for session`). |
| **Autonomous** | `--permission-mode auto` | Safe mutations execute automatically without interactive prompts. Hardline floor and steering file gate remain active. |
| **YOLO** | `--yolo` | Convenience flag for `--permission-mode auto`. **The Hardline Security Floor remains fully active.** |
