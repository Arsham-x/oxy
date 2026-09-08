"""
OXY End-to-End Architectural Verification Suite.

Tests all 8 core subsystems against production edge cases:
  1. Native Persian Unicode Typography Engine
  2. Non-Bypassable Hardline Security Floor & Steering File Protection
  3. Outgoing Schema Normalizer & Incoming Argument Coercer
  4. Persist-Before-Execute Transaction Ledger
  5. Segmented Parallel Execution Planner & Concurrency Barriers
  6. Progressive Disclosure Skill System & Multilingual Triggers
  7. KV Prefix Cache System Prompt Immutability
  8. CLI Command Dispatcher & Session Resumption
"""

import os
import sys
import tempfile
import unittest
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).parent.parent))

from oxy.ui import PersianFormatter, p
from oxy.security import SecurityGate, SecurityVerdict
from oxy.schemas import sanitize_schema_node, coerce_tool_arguments
from oxy.session import Session, SessionRegistry
from oxy.skills import SkillManager, tool_load_skill
from oxy.tools import ToolRegistry, ToolResult
from oxy.config import DEFAULT_CONFIG
from oxy.engine import ChatEngine
from oxy.commands import handle_command


class TestOXYArchitecture(unittest.TestCase):

    # ── 1. Typography Engine ───────────────────────────────────────
    def test_native_persian_typography(self):
        persian_text = "سلام دنیا! این یک آزمایش برای ایجنت اوکسی است."
        # Native mode must preserve standard Unicode codepoints for HarfBuzz
        formatted = p(persian_text, mode="native")
        self.assertEqual(formatted, persian_text)
        self.assertTrue(PersianFormatter.is_persian(persian_text))
        self.assertFalse(PersianFormatter.is_persian("Hello world"))

    # ── 2. Security Floor ──────────────────────────────────────────
    def test_security_floor_catastrophic_blocks(self):
        dangerous_cmds = [
            "rm -rf /",
            "rm -fr /*",
            "rm -rf ~",
            "mkfs.ext4 /dev/sda1",
            "dd if=/dev/zero of=/dev/nvme0n1",
            ":(){ :|:& };:",
            "shutdown -h now",
        ]
        for cmd in dangerous_cmds:
            decision = SecurityGate.check_bash_command(cmd)
            self.assertEqual(decision.verdict, SecurityVerdict.BLOCKED, f"Failed to block: {cmd}")

    def test_security_steering_file_protection(self):
        steering_files = [
            "system_prompt.md",
            "CLAUDE.md",
            "agents.md",
            ".cursorrules",
            "oxy_config.json",
            ".env",
        ]
        for s_file in steering_files:
            dec = SecurityGate.check_file_path(s_file, operation="write")
            self.assertEqual(dec.verdict, SecurityVerdict.REQUIRES_CONFIRMATION)

    # ── 3. Schemas & Coercion ──────────────────────────────────────
    def test_schema_normalizer_flattens_nullable(self):
        raw_schema = {
            "type": "object",
            "properties": {
                "tag": {"anyOf": [{"type": "string"}, {"type": "null"}]},
                "count": {"type": "integer"}
            }
        }
        clean = sanitize_schema_node(raw_schema)
        self.assertEqual(clean["properties"]["tag"], {"type": "string", "nullable": True})

    def test_argument_coercer_heals_model_hallucinations(self):
        target_schema = {
            "type": "object",
            "properties": {
                "limit": {"type": "integer"},
                "rate": {"type": "number"},
                "verbose": {"type": "boolean"},
                "tags": {"type": "array"},
            }
        }
        # Model hallucinated stringified numbers and stringified JSON array
        import json
        raw = json.dumps({"limit": "50", "rate": "3.14", "verbose": "true", "tags": '["fast", "clean"]'})
        coerced = coerce_tool_arguments(raw, target_schema)
        self.assertEqual(coerced["limit"], 50)
        self.assertEqual(coerced["rate"], 3.14)
        self.assertTrue(coerced["verbose"])
        self.assertEqual(coerced["tags"], ["fast", "clean"])

        # Also test Python single-quote dict hallucination common in open-source models
        raw_python_dict = "{'limit': '100', 'rate': '1.5', 'verbose': 'false', 'tags': 'single'}"
        coerced2 = coerce_tool_arguments(raw_python_dict, target_schema)
        self.assertEqual(coerced2["limit"], 100)
        self.assertEqual(coerced2["rate"], 1.5)
        self.assertFalse(coerced2["verbose"])
        self.assertEqual(coerced2["tags"], ["single"])

    # ── 4. Persist-Before-Execute Transaction Ledger ────────────────
    def test_transaction_ledger_durability(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            sess = Session(workspace_dir=tmpdir, title="Durability Test")
            sess.commit_user_message("Refactor tests")

            # Assistant turn with tool call before execution
            tc = [{
                "id": "call_abc",
                "type": "function",
                "function": {"name": "read_file", "arguments": '{"path": "foo.py"}'}
            }]
            sess.commit_assistant_pre_execution("Inspecting code...", tool_calls=tc)
            self.assertTrue(sess.has_unresolved_tool_calls())

            # Now commit result
            sess.commit_tool_result("call_abc", "read_file", "print('hello')")
            self.assertFalse(sess.has_unresolved_tool_calls())

            # Replay ledger from disk
            replayed = Session(session_id=sess.session_id, workspace_dir=tmpdir)
            self.assertEqual(len(replayed.messages), 3)
            self.assertEqual(replayed.messages[0]["content"], "Refactor tests")
            self.assertEqual(replayed.messages[2]["content"], "print('hello')")

    # ── 5. Segmented Parallel Execution Planner ────────────────────
    def test_segmented_execution_planner(self):
        reg = ToolRegistry()
        plan = reg.plan_execution_batches([
            {"id": "1", "function": {"name": "read_file", "arguments": "{}"}},
            {"id": "2", "function": {"name": "file_search", "arguments": "{}"}},
            {"id": "3", "function": {"name": "write_file", "arguments": "{}"}},  # Mutating barrier
            {"id": "4", "function": {"name": "read_file", "arguments": "{}"}},
        ])
        self.assertEqual(len(plan), 3)
        self.assertEqual(len(plan[0]), 2)  # Concurrent read phase
        self.assertEqual(len(plan[1]), 1)  # Sequential mutation barrier
        self.assertEqual(len(plan[2]), 1)  # Subsequent read phase

    # ── 6. Progressive Disclosure Skill System ─────────────────────
    def test_progressive_disclosure_skills(self):
        mgr = SkillManager()
        # English lookup
        s_review = mgr.get_skill("review")
        self.assertIsNotNone(s_review)
        self.assertEqual(s_review.name, "review")

        # Persian trigger lookup
        s_fa = mgr.get_skill("بررسی کد")
        self.assertIsNotNone(s_fa)
        self.assertEqual(s_fa.name, "review")

        # Test on-demand load_skill tool
        loaded = tool_load_skill("test", mgr)
        self.assertTrue(loaded["success"])
        self.assertIn("Test Suite Runner", loaded["instructions"])

    # ── 7. KV Prefix Cache Immutability ────────────────────────────
    def test_prefix_cache_immutability(self):
        cfg = DEFAULT_CONFIG.copy()
        cfg["api_key"] = "mock-key"
        engine = ChatEngine(cfg)

        frozen_p1 = engine._frozen_system_prompt
        # Message assembly must preserve byte-identical frozen prefix
        msgs = engine._build_messages()
        self.assertEqual(msgs[0]["content"], frozen_p1)
        self.assertIn("Core Philosophy", frozen_p1)
        self.assertIn("Available Procedural Skills", frozen_p1)

    # ── 8. Commands & Dispatcher ───────────────────────────────────
    def test_slash_command_dispatch(self):
        cfg = DEFAULT_CONFIG.copy()
        cfg["api_key"] = "mock-key"
        engine = ChatEngine(cfg)
        theme = {"accent": "cyan", "dim": "dim"}

        # Test /tools command
        cont, _ = handle_command(engine, "/tools", cfg, theme)
        self.assertTrue(cont)

        # Test /skills command
        cont, _ = handle_command(engine, "/skills", cfg, theme)
        self.assertTrue(cont)

        # Test /sessions command
        cont, _ = handle_command(engine, "/sessions", cfg, theme)
        self.assertTrue(cont)

    # ── 9. Raw Terminal Key Parser & Zero-Skip Navigation ───────────
    def test_raw_key_parser(self):
        import os
        from oxy.ui import _read_raw_key

        # Test simulated pipes for byte sequences
        r_fd, w_fd = os.pipe()
        try:
            # Test ANSI Up Arrow (\x1b[A)
            os.write(w_fd, b"\x1b[A")
            self.assertEqual(_read_raw_key(r_fd), "up")

            # Test ANSI Down Arrow (\x1b[B)
            os.write(w_fd, b"\x1b[B")
            self.assertEqual(_read_raw_key(r_fd), "down")

            # Test Application Cursor / SS3 Up (\x1bOA)
            os.write(w_fd, b"\x1bOA")
            self.assertEqual(_read_raw_key(r_fd), "up")

            # Test Application Cursor / SS3 Down (\x1bOB)
            os.write(w_fd, b"\x1bOB")
            self.assertEqual(_read_raw_key(r_fd), "down")

            # Test Vim navigation keys
            os.write(w_fd, b"k")
            self.assertEqual(_read_raw_key(r_fd), "up")
            os.write(w_fd, b"j")
            self.assertEqual(_read_raw_key(r_fd), "down")

            # Test Enter
            os.write(w_fd, b"\r")
            self.assertEqual(_read_raw_key(r_fd), "enter")
            os.write(w_fd, b"\n")
            self.assertEqual(_read_raw_key(r_fd), "enter")

            # Test Direct numeric quick jump (1-9)
            os.write(w_fd, b"3")
            self.assertEqual(_read_raw_key(r_fd), "3")

            # Standalone escape or unhandled key must NOT advance
            os.write(w_fd, b"\x1b")
            self.assertIn(_read_raw_key(r_fd), ("esc", ""))

            os.write(w_fd, b"x")
            self.assertEqual(_read_raw_key(r_fd), "")
        finally:
            os.close(r_fd)
            os.close(w_fd)

    # ── 10. Centered OXY Header & AGENT Lower-Right Layout ──────────
    def test_cockpit_header_layout(self):
        from oxy.ui import render_cockpit_header, OXY_BLOCK_ART
        import io
        from unittest.mock import patch

        self.assertEqual(len(OXY_BLOCK_ART), 7)
        buf = io.StringIO()
        with patch("sys.stdout", buf):
            render_cockpit_header({"name": "Cyber"}, animated=False)
        output = buf.getvalue()
        self.assertIn("██████╗", output)
        self.assertIn("A G E N T", output)
        self.assertIn("━", output)

    # ── 11. Status Line (Grok Build-style toolbar) ──────────────────
    def test_status_line_toolbar(self):
        from oxy.input import make_toolbar
        from datetime import datetime

        toolbar_fn = make_toolbar(
            model="deepseek-chat",
            msg_count=5,
            max_history=20,
            token_total=1234,
            start_time=datetime.now(),
            theme_name="cyber",
            rr_active=False,
            active_files_count=3,
            memory_count=2,
            permission_mode="ask",
        )
        result = toolbar_fn()
        # Result is an HTML formatted text object
        text = result.value  # HTML objects have .value
        self.assertIn("deepseek-chat", text)
        self.assertIn("5 turns", text)
        self.assertIn("1,234 tok", text)
        self.assertIn("ask", text)
        self.assertIn("3 files", text)
        self.assertIn("2 mem", text)

    # ── 12. Turn Metadata in AI Response ────────────────────────────
    def test_ai_response_with_turn_time(self):
        from oxy.render import render_ai_response, get_theme
        import io
        from unittest.mock import patch

        theme = get_theme("cyber")
        buf = io.StringIO()
        with patch("oxy.render.console") as mock_console:
            captured = []
            mock_console.print = lambda *a, **kw: captured.append(str(a[0]) if a else "")
            render_ai_response("Hello world", theme, turn_time=2.5)

        # Should have rendered something (the panel + turn time badge)
        self.assertTrue(len(captured) >= 1)

    # ── 13. Thinking Block with Elapsed Time ────────────────────────
    def test_thinking_block_with_elapsed(self):
        from oxy.render import render_thought, get_theme
        from unittest.mock import patch

        theme = get_theme("cyber")
        captured = []
        with patch("oxy.render.console") as mock_console:
            mock_console.print = lambda *a, **kw: captured.append(str(a[0]) if a else "")
            render_thought("Deep reasoning about architecture...", theme, elapsed_secs=3.8)

        output = " ".join(captured)
        self.assertIn("◆", output)
        self.assertIn("3.8s", output)

    # ── 14. Permission Mode in Toolbar ──────────────────────────────
    def test_toolbar_auto_mode(self):
        from oxy.input import make_toolbar
        from datetime import datetime

        toolbar_fn = make_toolbar(
            model="gpt-4o",
            msg_count=0,
            max_history=20,
            token_total=0,
            start_time=datetime.now(),
            theme_name="minimal",
            rr_active=True,
            permission_mode="auto",
        )
        result = toolbar_fn()
        text = result.value
        self.assertIn("auto", text)
        self.assertIn("rr", text)


if __name__ == "__main__":
    unittest.main()
