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


if __name__ == "__main__":
    unittest.main()
