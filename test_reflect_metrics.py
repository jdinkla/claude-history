"""
Test suite for reflect_metrics.py (stdlib-only, unittest).

Run with:
    python3 -m unittest -v
"""

from __future__ import annotations

import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path

import reflect_metrics as rm


# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------

def make_pair(
    prompt: str | None,
    answer: str = "ok, done.",
    session: str = "aaaaaaaa-1111",
    project: str = "/Users/x/repos/demo",
    model: str | None = "claude-fable-5",
    timestamp: str = "2026-07-01T10:00:00+02:00",
) -> dict:
    return {
        "timestamp": timestamp if prompt is not None else None,
        "session": session,
        "project": project,
        "model": model,
        "prompt": prompt,
        "answer": answer,
        "answer_timestamp": timestamp,
    }


# ---------------------------------------------------------------------------
# 1. Prompt classification
# ---------------------------------------------------------------------------

class TestClassifyPrompt(unittest.TestCase):

    def test_plain_human_prompt(self):
        self.assertEqual(rm.classify_prompt("please add a flag"), "human")

    def test_none_is_assistant_only(self):
        self.assertEqual(rm.classify_prompt(None), "assistant_only")

    def test_slash_command(self):
        text = "<command-name>/commit</command-name>\n<command-args></command-args>"
        self.assertEqual(rm.classify_prompt(text), "slash_command")

    def test_local_command_stdout(self):
        text = "<local-command-stdout>hello</local-command-stdout>"
        self.assertEqual(rm.classify_prompt(text), "local_command")

    def test_interruption_marker_alone(self):
        self.assertEqual(rm.classify_prompt("[Request interrupted by user]"), "interruption")

    def test_interruption_followed_by_text_is_human(self):
        text = "[Request interrupted by user]no, use the other file"
        self.assertEqual(rm.classify_prompt(text), "human")

    def test_context_dump(self):
        self.assertEqual(rm.classify_prompt("## Context Usage\nfoo bar"), "context_dump")


class TestCorrectionDetection(unittest.TestCase):

    def test_positive_signals(self):
        for text in [
            "no, use the other file",
            "Wrong file.",
            "wait, first run the tests",
            "actually I want json",
            "that's not what i asked",
            "I meant the CLI flag",
            "nein, anders",
            "stop",
        ]:
            self.assertTrue(rm.is_correction(text), text)

    def test_negative_signals(self):
        for text in [
            "please add a flag",
            "now add tests",
            "nothing to change, ship it",  # 'no' must be a word boundary
            "can you explain instead-of semantics",  # 'instead' not at start
        ]:
            self.assertFalse(rm.is_correction(text), text)


class TestSlashCommandName(unittest.TestCase):

    def test_extracts_name(self):
        text = "<command-name>/commit</command-name><command-args>-m x</command-args>"
        self.assertEqual(rm.slash_command_name(text), "/commit")

    def test_missing_name(self):
        self.assertIsNone(rm.slash_command_name("plain text"))


# ---------------------------------------------------------------------------
# 2. Metrics computation
# ---------------------------------------------------------------------------

class TestComputeMetrics(unittest.TestCase):

    def build_pairs(self) -> list[dict]:
        s1 = "aaaaaaaa-1111"
        s2 = "bbbbbbbb-2222"
        return [
            make_pair("build me a parser for the config format, edge cases included",
                      session=s1, timestamp="2026-07-01T10:00:00+02:00"),
            make_pair("no, the ini format", session=s1,
                      timestamp="2026-07-01T10:05:00+02:00"),
            make_pair("[Request interrupted by user]", session=s1,
                      timestamp="2026-07-01T10:06:00+02:00"),
            make_pair("<command-name>/commit</command-name>", session=s1,
                      timestamp="2026-07-01T10:30:00+02:00"),
            make_pair("write the docs", answer="Which audience should the docs target?",
                      session=s2, model="claude-opus-4-8",
                      timestamp="2026-07-02T09:00:00+02:00"),
            make_pair("developers", session=s2, model="claude-opus-4-8",
                      timestamp="2026-07-02T09:01:00+02:00"),
        ]

    def setUp(self):
        self.metrics = rm.compute_metrics(self.build_pairs())

    def test_totals(self):
        t = self.metrics["totals"]
        self.assertEqual(t["pairs"], 6)
        self.assertEqual(t["sessions"], 2)
        self.assertEqual(t["projects"], 1)
        self.assertEqual(t["prompt_kinds"]["human"], 4)
        self.assertEqual(t["prompt_kinds"]["slash_command"], 1)
        self.assertEqual(t["prompt_kinds"]["interruption"], 1)

    def test_models(self):
        self.assertEqual(self.metrics["models"]["claude-fable-5"], 4)
        self.assertEqual(self.metrics["models"]["claude-opus-4-8"], 2)

    def test_corrections(self):
        sig = self.metrics["signals"]["corrections"]
        self.assertEqual(sig["count"], 1)
        self.assertIn("no, the ini format", sig["exemplars"][0]["text"])
        self.assertEqual(sig["exemplars"][0]["session"], "aaaaaaaa")

    def test_interruptions(self):
        self.assertEqual(self.metrics["signals"]["interruptions"]["count"], 1)

    def test_slash_commands(self):
        sc = self.metrics["signals"]["slash_commands"]
        self.assertEqual(sc["count"], 1)
        self.assertEqual(sc["by_command"], {"/commit": 1})

    def test_steering_followups(self):
        st = self.metrics["signals"]["steering_followups"]
        # "no, the ini format" (s1) and "developers" (s2) are short follow-ups
        self.assertEqual(st["count"], 2)
        self.assertEqual(st["of_followups"], 2)

    def test_assistant_questions(self):
        aq = self.metrics["signals"]["assistant_questions"]
        self.assertEqual(aq["count"], 1)
        self.assertIn("audience", aq["exemplars"][0]["text"])

    def test_first_prompt_stats(self):
        fp = self.metrics["prompt_length"]["first_prompt"]
        self.assertEqual(fp["count"], 2)

    def test_session_rows(self):
        rows = self.metrics["sessions"]
        self.assertEqual(len(rows), 2)
        s1 = rows[0]
        self.assertEqual(s1["session"], "aaaaaaaa")
        self.assertEqual(s1["corrections"], 1)
        self.assertEqual(s1["interruptions"], 1)
        self.assertEqual(s1["duration_min"], 30.0)

    def test_exemplar_cap(self):
        pairs = [
            make_pair(f"no, attempt {i}", timestamp=f"2026-07-01T10:{i:02d}:00+02:00")
            for i in range(15)
        ]
        m = rm.compute_metrics(pairs, max_exemplars=5)
        self.assertEqual(m["signals"]["corrections"]["count"], 15)  # opening prompts count too
        self.assertEqual(len(m["signals"]["corrections"]["exemplars"]), 5)

    def test_empty_input(self):
        m = rm.compute_metrics([])
        self.assertEqual(m["totals"]["pairs"], 0)
        self.assertIsNone(m["window"]["first"])
        self.assertIsNone(m["prompt_length"]["human"]["median"])


# ---------------------------------------------------------------------------
# 3. Rendering and CLI
# ---------------------------------------------------------------------------

class TestRenderMarkdown(unittest.TestCase):

    def test_smoke(self):
        pairs = TestComputeMetrics().build_pairs()
        md = rm.render_markdown(rm.compute_metrics(pairs))
        self.assertIn("# Collaboration metrics", md)
        self.assertIn("## Correction signals (1)", md)
        self.assertIn("no, the ini format", md)
        self.assertIn("`claude-fable-5`: 4", md)
        self.assertIn("## Method notes", md)

    def test_empty(self):
        md = rm.render_markdown(rm.compute_metrics([]))
        self.assertIn("(none)", md)


class TestMain(unittest.TestCase):

    def run_main(self, argv: list[str]) -> tuple[int, str]:
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            rc = rm.main(argv)
        return rc, out.getvalue()

    def test_json_roundtrip_from_file(self):
        pairs = TestComputeMetrics().build_pairs()
        with tempfile.TemporaryDirectory() as d:
            src = Path(d) / "pairs.json"
            src.write_text(json.dumps(pairs), encoding="utf-8")
            rc, out = self.run_main([str(src), "--format", "json"])
        self.assertEqual(rc, 0)
        metrics = json.loads(out)
        self.assertEqual(metrics["totals"]["pairs"], 6)

    def test_md_default(self):
        pairs = TestComputeMetrics().build_pairs()
        with tempfile.TemporaryDirectory() as d:
            src = Path(d) / "pairs.json"
            src.write_text(json.dumps(pairs), encoding="utf-8")
            rc, out = self.run_main([str(src)])
        self.assertEqual(rc, 0)
        self.assertTrue(out.startswith("# Collaboration metrics"))

    def test_non_array_input_fails(self):
        with tempfile.TemporaryDirectory() as d:
            src = Path(d) / "bad.json"
            src.write_text('{"not": "a list"}', encoding="utf-8")
            err = io.StringIO()
            with contextlib.redirect_stderr(err):
                rc = rm.main([str(src)])
        self.assertEqual(rc, 1)


if __name__ == "__main__":
    unittest.main()
