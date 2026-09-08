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
| **Hallucinated / Injected Tool** | Model invents or is injected with a call to an unregistered tool (`delete_database`, `exfiltrate`). | **Deny-by-Default**: Unknown tools are blocked unless explicitly allowlisted in `KNOWN_TOOLS`. |
| **Ambient Prompt Injection** | Cloned repo ships an attacker-crafted `system_prompt.md` in the working directory. | **Ambient Quarantine**: CWD prompt files are never auto-loaded; explicit `system_prompt_file` opt-in only. |
| **Sub-Agent Scope Escape** | Delegated sub-agent attempts workspace mutation or shell execution beyond its task. | **Tool Scoping**: Sub-agents are restricted to read-only tools; mutations require operator opt-in. |
| **MCP Tool Confusion** | External MCP server offers hostile or unvetted tools to the agent loop. | **Namespace Sandboxing**: MCP tools register as `mcp_{server}_{tool}`, must join `KNOWN_TOOLS`, pass `SecurityGate`. |
| **Background Job Abuse** | Async job tries catastrophic deletion detached from the REPL. | **Floor Routing**: `bash_background` runs through the same hardline checks as `bash`. |
| **Telemetry Leakage** | API keys written to session logs. | **Secret Redaction**: Regex filter scrubs `sk-...` / `Bearer ...` before `.oxy/logs/` write. |

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

The current permission mode is always visible in the status line at the bottom of the terminal (`ask` or `auto`), and can be toggled at runtime with `/permissions [ask|auto]`.

---

## 5. Deny-by-Default Tool Policy

`SecurityGate.evaluate_tool_call()` enforces an explicit allowlist (`KNOWN_TOOLS`). Any tool name not registered — including hallucinated or prompt-injected tool names from the model — is categorically **BLOCKED**:

```
Unknown tool 'delete_database' blocked by security floor.
Add explicit policy branch in SecurityGate.evaluate_tool_call.
```

New tools must be deliberately added to `KNOWN_TOOLS`, assigned a safety classification (`_safe_tools` vs mutating), and given an explicit policy branch before the model can invoke them.

---

## 6. Sub-Agent Tool Scoping & Isolation

Sub-agents (`/agent [role] <task>`) run with least-privilege tool access:

- **Allowed by default** (`SubAgent.DEFAULT_ALLOWED_TOOLS`): `read_file`, `file_search`, `content_search`, `list_dir`, `git_status`, `recall_memory`, `load_skill` — read-only exploration only.
- **Blocked by default**: `write_file`, `edit_file`, `bash`, `save_memory`. A sub-agent cannot mutate workspace files, execute shell commands, or overwrite long-term memory unless the operator explicitly opts in via the `sub_agent_tools` config list.
- Out-of-scope tool calls are denied with a corrective error fed back into the sub-agent loop, so it continues with available tools instead of failing.
- Sub-agents run in an isolated message list — they never touch `engine.history` or the `.oxy/sessions/<id>.jsonl` ledger — while token usage is still aggregated into the parent `TokenTracker` for accurate accounting.
- The bounded loop (`sub_agent_max_iterations`, default 6) caps autonomous tool iterations.

---

## 7. Ambient Prompt Quarantine (CWD Immunity)

OXY **never** implicitly loads a `system_prompt.md` file from the current working directory. `resolve_system_prompt()` only reads a prompt file when the operator explicitly sets `system_prompt_file` in config.

Rationale: auto-loading ambient files is a classic prompt-injection vector — merely launching the agent inside a cloned repository containing an attacker-crafted `system_prompt.md` would silently activate hostile instructions. Explicit opt-in eliminates this entire attack class while `/system [text|edit|reload]` remains available for deliberate prompt control.

---

## 8. Model Context Protocol (MCP) Tool Sandboxing

External MCP servers communicate with OXY over stdio JSON-RPC 2.0 (`initialize`, `tools/list`, `tools/call`). To prevent external MCP tools from executing arbitrary unvetted code:

1. **Namespace Isolation**: Discovered tools are dynamically mapped to namespaced identifiers: `mcp_{server}_{tool}`.
2. **Dynamic KNOWN_TOOLS Registration**: Every connected MCP tool is formally registered into `KNOWN_TOOLS` and `ToolRegistry` with `safe=False`.
3. **Security Gate Enforcement**: Calls to `mcp_*` tools pass through `SecurityGate.evaluate_tool_call()`. In interactive mode (`--permission-mode ask`), they require human confirmation before execution.
4. **Lifecycle Teardown**: All spawned MCP server child processes are tracked and cleanly terminated on session exit via `MCPManager.shutdown()`.

---

## 9. Asynchronous Background Job Sandbox

The background job execution engine (`bash_background`, `job_status`, `job_cancel`) enables long-running tasks without blocking the interactive REPL.

1. **Identical Security Checks**: `bash_background` commands are inspected by `check_bash_command()` and evaluated against the identical non-bypassable hardline security floor as standard synchronous `bash` calls.
2. **Process Containment**: Each background job runs in a dedicated subprocess with its own stdout/stderr pipes, capped concurrency (`max_jobs = 8`), and configurable execution timeouts (default 300s).
3. **Tail Buffer Clamping**: Captured output is bounded to prevent unbounded memory growth or context window flooding.

---

## 10. Structured Telemetry & Secret Redaction

OXY logs session events, tool calls, and LLM telemetry to structured JSONL files (`.oxy/logs/<session_id>.jsonl`).

To prevent sensitive credentials from leaking into log files:
1. **Regex Redaction Filters**: Every log entry is scanned for secret patterns, including:
   - OpenAI / Anthropic / Groq / OpenRouter API keys (`sk-[a-zA-Z0-9_\-]{20,}`)
   - Slack OAuth tokens (`xox[baprs]-[0-9a-zA-Z-]{10,}`)
   - HTTP Authorization Bearer tokens (`Bearer\s+[A-Za-z0-9\-\._~\+\/]+=*`)
2. **Key-Name Scrubbing**: Dictionary fields matching sensitive names (`api_key`, `authorization`, `secret`, `token`, `password`) are automatically scrubbed and replaced with `***REDACTED***` before writing to disk.
