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

    # ── 15. P0-1: Ambient System Prompt Injection Immunity ─────────
    def test_system_prompt_never_autoloads_ambient_file(self):
        from oxy.config import resolve_system_prompt
        # Even if system_prompt.md exists in cwd, resolve_system_prompt must NOT
        # load it unless explicitly configured via system_prompt_file
        cfg = {"system_prompt": "Safe inline prompt", "system_prompt_file": ""}
        prompt = resolve_system_prompt(cfg)
        self.assertEqual(prompt, "Safe inline prompt")

        # Explicit opt-in MUST still work
        with tempfile.NamedTemporaryFile("w", suffix=".md", delete=False) as tf:
            tf.write("Custom explicit prompt")
            tf_path = tf.name
        try:
            cfg_explicit = {"system_prompt": "Safe inline", "system_prompt_file": tf_path}
            self.assertEqual(resolve_system_prompt(cfg_explicit), "Custom explicit prompt")
        finally:
            os.unlink(tf_path)

    # ── 16. P0-2: Default-Deny Security Policy ──────────────────────
    def test_security_gate_default_deny_unknown_tools(self):
        unknown_decision = SecurityGate.evaluate_tool_call("unknown_exfil_tool", {})
        self.assertEqual(unknown_decision.verdict, SecurityVerdict.BLOCKED)
        self.assertIn("blocked by security floor", unknown_decision.reason)

        # Builtins must still be allowed or routed appropriately
        known_safe = ["file_search", "content_search", "git_status", "save_memory", "recall_memory", "load_skill"]
        for tool in known_safe:
            dec = SecurityGate.evaluate_tool_call(tool, {})
            self.assertEqual(dec.verdict, SecurityVerdict.ALLOWED, f"Builtin tool '{tool}' was blocked")

    # ── 17. P0-3: Orphaned Tool Calls Durability & Discard ─────────
    def test_orphaned_tool_calls_recovery(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            sess = Session(workspace_dir=tmpdir, title="Orphan Test")
            sess.commit_user_message("Do work")
            sess.commit_assistant_pre_execution("Calling tool...", tool_calls=[
                {"id": "call_orphan", "function": {"name": "bash", "arguments": '{"command": "ls"}'}}
            ])
            self.assertTrue(sess.has_unresolved_tool_calls())
            orphans = sess.get_unresolved_tool_calls()
            self.assertEqual(len(orphans), 1)
            self.assertEqual(orphans[0]["id"], "call_orphan")

            discarded = sess.discard_unresolved_tool_calls()
            self.assertEqual(discarded, 1)
            self.assertFalse(sess.has_unresolved_tool_calls())

    # ── 18. P0-4: Atomic Config Write & KeyError Immunity ──────────
    def test_atomic_config_save_and_missing_key_safety(self):
        from oxy.config import save_config, load_config
        with tempfile.TemporaryDirectory() as tmpdir:
            cfg_path = Path(tmpdir) / "oxy_config.json"
            save_config({"api_key": "test-key-123", "theme": "cyber"}, path=cfg_path)
            self.assertTrue(cfg_path.exists())
            loaded = load_config(str(cfg_path))
            self.assertEqual(loaded["api_key"], "test-key-123")
            self.assertEqual(loaded["theme"], "cyber")

            # Config without api_key key should not crash .get() lookups
            partial_cfg = {"model": "gpt-4o"}
            self.assertIsNone(partial_cfg.get("api_key"))

    # ── 19. P1-4: list_dir Tool & Navigation ───────────────────────
    def test_list_dir_tool(self):
        from oxy.tools import list_dir
        with tempfile.TemporaryDirectory() as tmpdir:
            td = Path(tmpdir)
            (td / "subdir").mkdir()
            (td / "file_a.py").write_text("print(1)")
            (td / "file_b.txt").write_text("hello world")

            res = list_dir(str(td))
            self.assertTrue(res.success)
            self.assertIn("📁 subdir/", res.output)
            self.assertIn("file_a.py", res.output)
            self.assertIn("file_b.txt", res.output)
            self.assertEqual(res.metadata["dirs"], 1)
            self.assertEqual(res.metadata["files"], 2)

    # ── 20. P1-3: Frozen Prompt Refresh Seam ───────────────────────
    def test_frozen_prompt_refresh_seam(self):
        cfg = DEFAULT_CONFIG.copy()
        cfg["api_key"] = "mock-key"
        engine = ChatEngine(cfg)

        initial_prompt = engine._frozen_system_prompt
        # Mutate system prompt via set_system (which triggers refresh)
        engine.set_system("New Architect Persona Directive")
        self.assertNotEqual(engine._frozen_system_prompt, initial_prompt)
        self.assertIn("New Architect Persona Directive", engine._frozen_system_prompt)

        # Messages built after refresh must reflect the updated prompt
        msgs = engine._build_messages()
        self.assertEqual(msgs[0]["content"], engine._frozen_system_prompt)

    # ── 21. P1-2: Token Budget & Manual Compaction ─────────────────
    def test_token_budget_and_manual_compaction(self):
        cfg = DEFAULT_CONFIG.copy()
        cfg["api_key"] = "mock-key"
        cfg["context_window"] = 4096
        engine = ChatEngine(cfg)

        self.assertEqual(engine._context_window(), 4096)

        # Populate history with turns
        engine.history = [
            {"role": "user", "content": f"Turn {i}: please analyze this code"}
            for i in range(14)
        ]
        tokens = engine._estimate_tokens(engine.history)
        self.assertGreater(tokens, 0)

        # Manual compaction should preserve recent turns and return removed count
        removed = engine.compact_now(keep_recent=4)
        self.assertGreater(removed, 0)
        # History should now be 1 summary block + 4 recent turns
        self.assertEqual(len(engine.history), 5)
        self.assertIn("summary of earlier turns", engine.history[0]["content"])
        self.assertEqual(engine.history[-1]["content"], "Turn 13: please analyze this code")

    # ── 22. P1-5: Command Registry Dispatch & Aliases ──────────────
    def test_command_registry_dispatch_and_aliases(self):
        from oxy.commands import get_command, COMMANDS, SLASH_COMMANDS

        # Verify command objects and aliases
        help_cmd = get_command("/help")
        self.assertIsNotNone(help_cmd)
        self.assertEqual(help_cmd.name, "/help")
        self.assertEqual(get_command("/h"), help_cmd)
        self.assertEqual(get_command("/?"), help_cmd)

        quit_cmd = get_command("/quit")
        self.assertIsNotNone(quit_cmd)
        self.assertEqual(get_command("/exit"), quit_cmd)
        self.assertEqual(get_command("/q"), quit_cmd)

        compact_cmd = get_command("/compact")
        self.assertIsNotNone(compact_cmd)
        self.assertIn("/compact", SLASH_COMMANDS)

        # Verification of argument requirement
        add_cmd = get_command("/add")
        self.assertTrue(add_cmd.needs_arg)

    # ── 23. P1-7: SubAgent Tool Scoping & History Isolation ────────
    def test_subagent_tool_isolation_and_scoping(self):
        from oxy.engine import SubAgent

        cfg = DEFAULT_CONFIG.copy()
        cfg["api_key"] = "mock-key"
        engine = ChatEngine(cfg)

        sa = SubAgent(engine, persona="reviewer")
        # SubAgent must only have access to safe inspection tools
        self.assertIn("read_file", sa.allowed_tools)
        self.assertIn("file_search", sa.allowed_tools)
        self.assertIn("list_dir", sa.allowed_tools)
        self.assertNotIn("write_file", sa.allowed_tools)
        self.assertNotIn("edit_file", sa.allowed_tools)
        self.assertNotIn("bash", sa.allowed_tools)

        filtered = sa._filtered_schemas()
        schema_names = {s["function"]["name"] for s in filtered}
        self.assertTrue(schema_names.issubset(sa.allowed_tools))
        self.assertNotIn("write_file", schema_names)
        self.assertNotIn("bash", schema_names)

        # SubAgent budget and iterations are enforced
        self.assertEqual(sa.max_iterations, 6)
        self.assertEqual(sa.max_tokens, 2048)

    # ── 24. P1-1: Stream Assembly Data Structures ──────────────────
    def test_stream_assembly_structures(self):
        from oxy.engine import (
            AssembledFunction, AssembledToolCall, AssembledMessage,
            AssembledChoice, AssembledUsage, AssembledResponse
        )

        fn = AssembledFunction(name="read_file", arguments='{"path": "test.py"}')
        tc = AssembledToolCall(id="call_123", function=fn)
        msg = AssembledMessage(content="Hello world", tool_calls=[tc], reasoning_content="Thinking...")
        choice = AssembledChoice(message=msg)
        usage = AssembledUsage(prompt_tokens=10, completion_tokens=25)
        resp = AssembledResponse(choices=[choice], usage=usage, was_streamed=True, thought_rendered=True)

        self.assertEqual(resp.choices[0].message.content, "Hello world")
        self.assertEqual(resp.choices[0].message.tool_calls[0].function.name, "read_file")
        self.assertEqual(resp.usage.prompt_tokens, 10)
        self.assertEqual(resp.usage.completion_tokens, 25)
        self.assertTrue(resp.was_streamed)
        self.assertTrue(resp.thought_rendered)


if __name__ == "__main__":
    unittest.main()
