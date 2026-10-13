"""
Test suite for check_transcripts.py (stdlib-only, unittest).

Run with:
    python3 -m unittest -v
"""

from __future__ import annotations

import contextlib
import io
import json
import shutil
import tempfile
import unittest
import unittest.mock
from datetime import datetime, timedelta, timezone

# Make the modules under src/ importable when tests run from the repo root.
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import check_transcripts as ct
import claude_history as ch


def ts(minutes_ago: int) -> str:
    dt = datetime.now(tz=timezone.utc) - timedelta(minutes=minutes_ago)
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def user(session: str, text, minutes_ago: int = 5, **extra) -> dict:
    return {"type": "user", "timestamp": ts(minutes_ago), "sessionId": session,
            "message": {"content": text}, **extra}


def assistant(session: str, text: str, minutes_ago: int = 4) -> dict:
    return {"type": "assistant", "timestamp": ts(minutes_ago), "sessionId": session,
            "message": {"content": text, "model": "m"}}


class CheckTestCase(unittest.TestCase):

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.projects = Path(self.tmpdir) / "projects"
        self.projects.mkdir()
        self.patcher = unittest.mock.patch.object(ch, "PROJECTS_DIR", self.projects)
        self.patcher.start()

    def tearDown(self):
        self.patcher.stop()
        shutil.rmtree(self.tmpdir)

    def write(self, project: str, session: str, events: list[dict]) -> None:
        d = self.projects / project
        d.mkdir(exist_ok=True)
        (d / f"{session}.jsonl").write_text(
            "\n".join(json.dumps(e) for e in events) + "\n", encoding="utf-8")

    # --days 2 starts at yesterday's local midnight, so fixtures minutes old are
    # always in the window whatever the time of day (a --days 1 window starts
    # at today's midnight and made such fixtures flaky right after midnight).
    def rows(self) -> dict[str, tuple[str, str]]:
        return {name: (status, detail) for status, name, detail in ct.run_checks(2)}

    def run_main(self) -> tuple[int, str]:
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            rc = ct.main(["--days", "2"])
        return rc, out.getvalue()

    def clean_session(self) -> None:
        self.write("-Users-jane-my-app", "s1", [
            user("s1", "hello", cwd="/Users/jane/my-app", origin={"kind": "human"}),
            assistant("s1", "hi"),
        ])


class TestChecks(CheckTestCase):

    def test_clean_data_passes(self):
        self.clean_session()
        rc, out = self.run_main()
        self.assertEqual(rc, 0, out)
        self.assertNotIn("FAIL", out)
        self.assertNotIn("WARN", out)

    def test_empty_projects_dir_passes(self):
        rc, _ = self.run_main()
        self.assertEqual(rc, 0)

    def test_project_path_mismatch_fails(self):
        # Directory encoding no longer matches the recorded cwd (format drift).
        self.write("-Users-jane-renamed", "s1", [
            user("s1", "hello", cwd="/Users/jane/my-app"),
        ])
        status, detail = self.rows()["project-paths"]
        self.assertEqual(status, "FAIL")
        self.assertIn("1 of 1", detail)

    def test_orphan_answer_fails(self):
        self.clean_session()
        pairs = [
            {"session": "s1", "prompt": "q", "project": "/p"},
            {"session": "s1", "prompt": None, "project": "/p"},
        ]
        with unittest.mock.patch.object(ct, "extract_pairs", return_value=pairs):
            status, _ = self.rows()["orphan-answers"]
        self.assertEqual(status, "FAIL")

    def test_leading_promptless_pair_is_not_an_orphan(self):
        # The window can start mid-session; an answer before any prompt is fine.
        self.write("-Users-jane-my-app", "s1", [
            assistant("s1", "late answer", minutes_ago=6),
            user("s1", "next", minutes_ago=5, cwd="/Users/jane/my-app"),
        ])
        self.assertEqual(self.rows()["orphan-answers"][0], "PASS")

    def test_unknown_content_block_fails(self):
        self.write("-Users-jane-my-app", "s1", [
            user("s1", [{"type": "hologram", "data": "x"}], cwd="/Users/jane/my-app"),
        ])
        self.assertEqual(self.rows()["content-shapes"][0], "FAIL")

    def test_non_list_content_fails(self):
        self.write("-Users-jane-my-app", "s1", [
            user("s1", {"text": "dict content"}, cwd="/Users/jane/my-app"),
        ])
        self.assertEqual(self.rows()["content-shapes"][0], "FAIL")

    def test_machine_origin_prompt_fails(self):
        self.write("-Users-jane-my-app", "s1", [
            user("s1", "task done", cwd="/Users/jane/my-app",
                 origin={"kind": "task-notification"}),
        ])
        status, detail = self.rows()["machine-prompts"]
        self.assertEqual(status, "FAIL")
        self.assertIn("origin task-notification 1", detail)

    def test_meta_event_skipped_by_extraction_passes(self):
        self.write("-Users-jane-my-app", "s1", [
            user("s1", "skill body", cwd="/Users/jane/my-app", isMeta=True),
        ])
        self.assertEqual(self.rows()["machine-prompts"][0], "PASS")

    def test_leaked_meta_prompt_fails(self):
        # Guards against the extraction regressing to emit isMeta events.
        self.write("-Users-jane-my-app", "s1", [
            user("s1", "skill body", cwd="/Users/jane/my-app", isMeta=True),
        ])
        pairs = [{"session": "s1", "prompt": "skill body", "project": "/Users/jane/my-app"}]
        with unittest.mock.patch.object(ct, "extract_pairs", return_value=pairs):
            status, detail = self.rows()["machine-prompts"]
        self.assertEqual(status, "FAIL")
        self.assertIn("isMeta 1", detail)

    def test_new_fields_warn_without_failing(self):
        self.write("-Users-jane-my-app", "s1", [
            user("s1", "hello", cwd="/Users/jane/my-app", brandNewFlag=True),
            {"type": "brand-new-event", "sessionId": "s1"},
        ])
        rc, out = self.run_main()
        self.assertEqual(rc, 0, out)
        status, detail = self.rows()["new-fields"]
        self.assertEqual(status, "WARN")
        self.assertIn("brandNewFlag", detail)
        self.assertIn("brand-new-event", detail)

    def test_out_of_window_events_ignored(self):
        self.write("-Users-jane-my-app", "s1", [
            user("s1", [{"type": "hologram"}], minutes_ago=60 * 24 * 3,
                 cwd="/Users/jane/my-app"),
        ])
        self.assertEqual(self.rows()["content-shapes"][0], "PASS")


class TestPrivacy(CheckTestCase):

    def test_output_never_contains_prompt_or_answer_text(self):
        secret_prompt = "ZEBRA-PROMPT-7f3a"
        secret_answer = "QUOKKA-ANSWER-91c2"
        self.write("-Users-jane-renamed", "s1", [
            user("s1", secret_prompt, cwd="/Users/jane/my-app",
                 origin={"kind": "task-notification"}),
            user("s1", [{"type": "hologram", "text": secret_prompt}], minutes_ago=4),
            assistant("s1", secret_answer, minutes_ago=3),
        ])
        rc, out = self.run_main()
        self.assertEqual(rc, 1)  # several checks fail, so every detail path runs
        self.assertNotIn(secret_prompt, out)
        self.assertNotIn(secret_answer, out)


if __name__ == "__main__":
    unittest.main()
