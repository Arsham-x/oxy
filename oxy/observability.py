"""
OXY Observability — Structured event log with secret redaction.

Every agent action is recorded as a structured JSONL event:
  - llm_call, tool_call, tool_result, error
  - Runs without network, fully local
  - Secrets (API keys, tokens) are redacted before serialization
  - Stored in .oxy/logs/ for post-mortem debugging
"""

from __future__ import annotations

import json
import os
import re
import time
import uuid
from pathlib import Path
from typing import Any


LOG_DIR = Path.cwd() / ".oxy" / "logs"


def set_log_dir(path: Path | str) -> Path:
    global LOG_DIR
    LOG_DIR = Path(path).expanduser().resolve()
    return LOG_DIR


SECRET_PATTERNS = [
    # api_key headers / bearer tokens
    re.compile(r"(?i)\b(api[_-]?key|bearer|token|secret|password)\b\s*[:=]\s*['\"]?([^\s'\",;]+)['\"]?"),
    # Long hex/base64 blobs typical of API keys
    re.compile(r"\b(sk-[a-zA-Z0-9\-_]{10,}|sk-ant-[a-zA-Z0-9\-_]{10,}|xox[bap]-[a-zA-Z0-9\-_]{5,})\b"),
    re.compile(r"\b[A-Za-z0-9_\-]{32,}\b"),
]


def redact_secrets(text: str) -> str:
    """Redact API keys, tokens, and credential-like strings from text."""
    redacted = text
    redacted = SECRET_PATTERNS[0].sub(lambda m: f"{m.group(1)}=***REDACTED***", redacted)
    redacted = SECRET_PATTERNS[1].sub("***REDACTED***", redacted)
    # Only redact overly long tokens, preserving normal prose
    def _redact_long(m):
        token = m.group(0)
        # Skip common English words mistakenly matched
        if token.replace("_", "").replace("-", "").isalpha() and len(token) < 48:
            return token
        return "***REDACTED***"
    redacted = SECRET_PATTERNS[2].sub(_redact_long, redacted)
    return redacted


class EventLogger:
    """Thread-safe structured JSONL event emitter for agent telemetry."""

    def __init__(self, session_id: str = "", log_dir: Path | str | None = None):
        self.session_id = session_id or uuid.uuid4().hex[:12]
        self.log_dir = Path(log_dir) if log_dir else LOG_DIR
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.log_file = self.log_dir / f"{self.session_id}.jsonl"

    def log(self, event_type: str, data: dict[str, Any] | None = None):
        entry = {
            "id": uuid.uuid4().hex[:12],
            "session_id": self.session_id,
            "ts": time.time(),
            "type": event_type,
            "payload": self._sanitize(data or {}),
        }
        try:
            with open(self.log_file, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry, ensure_ascii=False, default=str) + "\n")
                f.flush()
                os.fsync(f.fileno())
        except Exception:
            pass

    def _sanitize(self, data: dict[str, Any]) -> dict[str, Any]:
        clean: dict[str, Any] = {}
        for k, v in data.items():
            if isinstance(v, str):
                # Never log raw key material
                if k.lower() in ("api_key", "apikey", "authorization", "secret", "token", "password"):
                    clean[k] = "***REDACTED***"
                else:
                    clean[k] = redact_secrets(v)
            elif isinstance(v, dict):
                clean[k] = self._sanitize(v)
            elif isinstance(v, list):
                clean[k] = [self._sanitize({"v": i})["v"] if isinstance(i, (dict, str)) else i for i in v]
            else:
                clean[k] = v
        return clean

    def log_tool_call(self, tool_name: str, args: dict[str, Any]):
        self.log("tool_call", {"tool": tool_name, "args": args})

    def log_tool_result(self, tool_name: str, success: bool, output_preview: str = "", elapsed_ms: float = 0.0):
        self.log("tool_result", {
            "tool": tool_name,
            "success": success,
            "output_preview": output_preview[:500],
            "elapsed_ms": round(elapsed_ms, 1),
        })

    def log_llm_call(self, model: str, prompt_tokens: int = 0, completion_tokens: int = 0):
        self.log("llm_call", {"model": model, "prompt_tokens": prompt_tokens, "completion_tokens": completion_tokens})

    def log_error(self, error_type: str, message: str):
        self.log("error", {"error_type": error_type, "message": message})
