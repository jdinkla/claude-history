"""Codex rollout extraction and shared CLI regression tests."""
import contextlib
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
import codex_history as cx
import claude_history as ch


def event(kind, payload, timestamp="2026-11-04T12:00:00Z"):
    return {"type": kind, "timestamp": timestamp, "payload": payload}


def message(role, text, **extra):
    return event("response_item", {"type": "message", "role": role,
                 "content": [{"type": "input_text" if role == "user" else "output_text",
                              "text": text}], **extra})


class TestCodexHistory(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.home = Path(self.tmp.name)
        self.env = patch.dict(os.environ, CODEX_HOME=str(self.home))
        self.env.start()
        self.addCleanup(self.tmp.cleanup)
        self.addCleanup(self.env.stop)

    def write(self, events, session="s1", archived=False):
        root = "archived_sessions" if archived else "sessions/2026/11/04"
        path = self.home / root / f"rollout-{session}.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        records = [event("session_meta", {"id": session, "cwd": "/work/my-app"}),
                   event("turn_context", {"model": "codex-test", "cwd": "/work/my-app"})]
        path.write_text("\n".join(json.dumps(e) for e in records + events) + "\n")
        return path

    def collect(self, until=None, project=None, noise=False):
        return list(cx.iter_entries(ch.parse_date("2026-11-04T00:00:00Z"),
                                   until, project, noise))

    def run_cli(self, *args):
        output, errors = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(output), contextlib.redirect_stderr(errors):
            result = cx.main(["--since", "2026-11-04T00:00:00Z", *args])
        self.assertEqual(result, 0)
        return output.getvalue(), errors.getvalue()

    def test_response_items_skip_tools_reasoning_and_instructions(self):
        self.write([message("system", "system"), message("developer", "instructions"),
                    message("user", "question"), event("response_item", {"type": "reasoning"}),
                    event("response_item", {"type": "function_call_output", "output": "tool"}),
                    message("assistant", "private", channel="analysis"),
                    message("assistant", "answer", phase="final_answer")])
        entries = self.collect()
        self.assertEqual([e.text for e in entries], ["question", "answer"])
        self.assertEqual(entries[1].model, "codex-test")
        self.assertEqual(entries[0].project, "/work/my-app")
        self.assertIsNone(entries[0].model)

    def test_injected_user_context_skipped_even_without_noise_flag(self):
        self.write([message("user", "<environment_context>cwd</environment_context>"),
                    message("user", "# AGENTS.md instructions for /work\nrules"),
                    message("user", '<external_codex_apps_open_page>{}</external_codex_apps_open_page>'),
                    message("user", "real prompt")])
        self.assertEqual([e.text for e in self.collect()], ["real prompt"])

    def test_multiple_blocks_and_images(self):
        self.write([event("response_item", {"type": "message", "role": "user", "content": [
            {"type": "input_text", "text": "<environment_context>x</environment_context>"},
            {"type": "input_text", "text": "one"}, {"type": "input_image", "image_url": "data:"},
            {"type": "input_text", "text": "two"}, "bad", {"type": "input_text", "text": 3}]})])
        self.assertEqual(self.collect()[0].text, "one\ntwo")

    def test_event_messages_fallback_without_duplicates(self):
        self.write([event("event_msg", {"type": "user_message", "message": "prompt"}),
                    message("user", "prompt"),
                    event("event_msg", {"type": "agent_message", "message": "answer"}),
                    message("assistant", "answer"),
                    event("event_msg", {"type": "task_complete", "last_agent_message": "answer"})])
        self.assertEqual([e.text for e in self.collect()], ["prompt", "answer"])

    def test_older_event_only_log(self):
        self.write([event("event_msg", {"type": "user_message", "message": "prompt"}),
                    event("event_msg", {"type": "agent_message", "message": "answer"})])
        self.assertEqual([e.text for e in self.collect()], ["prompt", "answer"])

    def test_archives_and_duplicate_sessions(self):
        self.write([message("user", "active")])
        self.write([message("user", "duplicate")], archived=True)
        self.write([message("user", "archived")], session="s2", archived=True)
        self.assertEqual([e.text for e in self.collect()], ["active", "archived"])

    def test_missing_home(self):
        self.assertEqual(self.collect(), [])
        output, _ = self.run_cli("--json")
        self.assertEqual(json.loads(output), [])

    def test_malformed_records_and_partial_line(self):
        path = self.write([message("user", "ok"), event("response_item", None),
                           message("assistant", "bad timestamp") | {"timestamp": "invalid"}])
        with path.open("a") as stream:
            stream.write('null\n[]\n{"type":')
        self.assertEqual([e.text for e in self.collect()], ["ok"])

    def test_date_boundaries_and_project_filter(self):
        self.write([message("user", "in"),
                    message("user", "out") | {"timestamp": "2026-11-05T00:00:00Z"}])
        until = ch.parse_date("2026-11-05T00:00:00Z")
        self.assertEqual([e.text for e in self.collect(until, "my-app")], ["in"])
        self.assertEqual(self.collect(project="other"), [])

    def test_noise_filter(self):
        self.write([message("user", "[Request interrupted by user]"), message("user", "/help")])
        self.assertEqual(len(self.collect()), 2)
        self.assertEqual([e.text for e in self.collect(noise=True)], ["/help"])

    def test_pairing_is_per_session_and_appends_answers(self):
        self.write([message("user", "prompt1"), message("assistant", "progress"),
                    message("assistant", "done") | {"timestamp": "2026-11-04T12:02:00Z"}])
        self.write([message("user", "prompt2") | {"timestamp": "2026-11-04T12:01:00Z"},
                    message("assistant", "other") | {"timestamp": "2026-11-04T12:03:00Z"}], session="s2")
        output, _ = self.run_cli("--json")
        pairs = json.loads(output)
        self.assertEqual([p["answer"] for p in pairs], ["progress\n\ndone", "other"])
        self.assertEqual(set(pairs[0]), {"timestamp", "session", "project", "model", "prompt", "answer", "answer_timestamp"})

    def test_formats_and_truncation(self):
        self.write([message("user", "question"), message("assistant", "answer")])
        for fmt, marker in [("text", "USER"), ("md", "## Session"),
                            ("html", "Codex history — since")]:
            with self.subTest(fmt=fmt):
                output, _ = self.run_cli("--format", fmt)
                self.assertIn(marker, output)
        output, _ = self.run_cli("--format", "jsonl", "--max-chars", "3")
        entries = [json.loads(line) for line in output.splitlines()]
        self.assertTrue(entries[0]["text"].startswith("que\n… [truncated"))

    def test_default_argv_supports_console_entry_point(self):
        self.write([message("user", "question")])
        with patch.object(sys, "argv", ["codex-history", "--since", "2026-11-04", "--json"]):
            with contextlib.redirect_stdout(io.StringIO()) as output:
                self.assertEqual(cx.main(), 0)
        self.assertEqual(json.loads(output.getvalue())[0]["prompt"], "question")


if __name__ == "__main__":
    unittest.main()
