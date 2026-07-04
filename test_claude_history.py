"""
Test suite for claude_history.py (stdlib-only, unittest).

Run with:
    python3 -m unittest -v
"""

from __future__ import annotations

import contextlib
import io
import json
import os
import sys
import tempfile
import unittest
import unittest.mock
from datetime import datetime, timedelta, timezone
from pathlib import Path

# ---------------------------------------------------------------------------
# Import the module under test
# ---------------------------------------------------------------------------
import claude_history as ch


# ---------------------------------------------------------------------------
# Helpers shared across tests
# ---------------------------------------------------------------------------

def utc_now() -> datetime:
    return datetime.now(tz=timezone.utc)


def make_ts(dt: datetime) -> str:
    """Return an ISO-8601 string with Z suffix suitable for JSONL fixtures."""
    utc = dt.astimezone(timezone.utc)
    return utc.strftime("%Y-%m-%dT%H:%M:%SZ")


def write_jsonl(path: Path, lines: list[dict]) -> None:
    path.write_text("\n".join(json.dumps(obj) for obj in lines) + "\n", encoding="utf-8")


def capture_main(argv: list[str]) -> tuple[str, str]:
    """Run ch.main(argv) and return (stdout, stderr) as strings."""
    out = io.StringIO()
    err = io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        ch.main(argv)
    return out.getvalue(), err.getvalue()


# ---------------------------------------------------------------------------
# 1. Helper functions
# ---------------------------------------------------------------------------

class TestDecodeProject(unittest.TestCase):

    def test_simple_path(self):
        self.assertEqual(ch.decode_project("-Users-jane-code-app"), "/Users/jane/code/app")

    def test_single_segment(self):
        self.assertEqual(ch.decode_project("-home"), "/home")

    def test_round_trip(self):
        original = "/Users/test/code/app"
        # Encode manually (replace / with - then prepend - for the leading /)
        encoded = original.replace("/", "-")  # gives -Users-test-code-app
        self.assertEqual(ch.decode_project(encoded), original)

    def test_multiple_leading_dashes(self):
        # lstrip("-") removes ALL leading dashes
        result = ch.decode_project("--Users-foo")
        self.assertEqual(result, "/Users/foo")


class TestParseTs(unittest.TestCase):

    def test_z_suffix(self):
        dt = ch.parse_ts("2026-06-10T12:00:00Z")
        self.assertIsNotNone(dt)
        self.assertEqual(dt.tzinfo, timezone.utc)
        self.assertEqual(dt.year, 2026)
        self.assertEqual(dt.hour, 12)

    def test_plus_offset(self):
        dt = ch.parse_ts("2026-06-10T12:00:00+00:00")
        self.assertIsNotNone(dt)
        self.assertEqual(dt.tzinfo, timezone.utc)

    def test_non_utc_offset(self):
        dt = ch.parse_ts("2026-06-10T14:00:00+02:00")
        self.assertIsNotNone(dt)
        # Should be 12:00 UTC
        utc = dt.astimezone(timezone.utc)
        self.assertEqual(utc.hour, 12)

    def test_invalid_returns_none(self):
        self.assertIsNone(ch.parse_ts("not-a-date"))
        self.assertIsNone(ch.parse_ts(""))
        self.assertIsNone(ch.parse_ts("9999-99-99"))


class TestIsNoise(unittest.TestCase):

    def test_local_command_caveat(self):
        self.assertTrue(ch.is_noise("<local-command-caveat>some stuff</local-command-caveat>"))
        self.assertTrue(ch.is_noise("  <local-command-caveat>x</local-command-caveat>  "))

    def test_local_command_stdout(self):
        self.assertTrue(ch.is_noise("<local-command-stdout>output here</local-command-stdout>"))

    def test_command_tags(self):
        self.assertTrue(ch.is_noise("<command-name>foo</command-name>"))
        self.assertTrue(ch.is_noise(
            "<command-name>foo</command-name><command-message>bar</command-message>"
        ))
        self.assertTrue(ch.is_noise(
            "<command-name>a</command-name>\n<command-args>b</command-args>"
        ))

    def test_interrupted(self):
        self.assertTrue(ch.is_noise("[Request interrupted by user mid-turn]"))
        self.assertTrue(ch.is_noise("  [Request interrupted by user]  "))

    def test_context_usage(self):
        self.assertTrue(ch.is_noise("## Context Usage\n\nsome stats"))
        self.assertTrue(ch.is_noise("  ##  Context Usage blah blah"))

    def test_real_prompt_not_noise(self):
        self.assertFalse(ch.is_noise("What is the capital of France?"))

    def test_noise_embedded_in_longer_text_not_noise(self):
        # fullmatch — surrounding real text means it is NOT noise
        self.assertFalse(ch.is_noise(
            "Please run <local-command-caveat>x</local-command-caveat> for me"
        ))

    def test_empty_string(self):
        # Empty string does not match any noise pattern
        self.assertFalse(ch.is_noise(""))


class TestExtractUserText(unittest.TestCase):

    def test_string_content(self):
        self.assertEqual(ch.extract_user_text({"content": "hello"}), "hello")

    def test_string_content_stripped(self):
        self.assertEqual(ch.extract_user_text({"content": "  hi  "}), "hi")

    def test_string_empty_after_strip_returns_none(self):
        self.assertIsNone(ch.extract_user_text({"content": "   "}))

    def test_list_text_block(self):
        msg = {"content": [{"type": "text", "text": "hello"}]}
        self.assertEqual(ch.extract_user_text(msg), "hello")

    def test_list_multiple_text_blocks_joined(self):
        msg = {"content": [
            {"type": "text", "text": "part1"},
            {"type": "text", "text": "part2"},
        ]}
        self.assertEqual(ch.extract_user_text(msg), "part1\npart2")

    def test_list_thinking_block_ignored(self):
        msg = {"content": [
            {"type": "thinking", "thinking": "internal"},
            {"type": "text", "text": "visible"},
        ]}
        self.assertEqual(ch.extract_user_text(msg), "visible")

    def test_list_tool_use_block_ignored(self):
        msg = {"content": [
            {"type": "tool_use", "name": "bash", "input": {}},
            {"type": "text", "text": "real text"},
        ]}
        self.assertEqual(ch.extract_user_text(msg), "real text")

    def test_list_non_dict_block_ignored(self):
        msg = {"content": ["not a dict", {"type": "text", "text": "ok"}]}
        self.assertEqual(ch.extract_user_text(msg), "ok")

    def test_list_missing_text_key_ignored(self):
        msg = {"content": [{"type": "text"}]}  # no "text" key → falsy
        self.assertIsNone(ch.extract_user_text(msg))

    def test_list_all_non_text_returns_none(self):
        msg = {"content": [{"type": "tool_result", "content": "x"}]}
        self.assertIsNone(ch.extract_user_text(msg))

    def test_no_content_returns_none(self):
        self.assertIsNone(ch.extract_user_text({}))

    def test_none_content_returns_none(self):
        self.assertIsNone(ch.extract_user_text({"content": None}))


class TestExtractAssistantText(unittest.TestCase):

    def test_string_content(self):
        self.assertEqual(ch.extract_assistant_text({"content": "answer"}), "answer")

    def test_thinking_block_skipped(self):
        msg = {"content": [
            {"type": "thinking", "thinking": "..."},
            {"type": "text", "text": "the answer"},
        ]}
        self.assertEqual(ch.extract_assistant_text(msg), "the answer")

    def test_tool_use_block_skipped(self):
        msg = {"content": [
            {"type": "tool_use", "name": "bash", "input": {}},
            {"type": "text", "text": "done"},
        ]}
        self.assertEqual(ch.extract_assistant_text(msg), "done")

    def test_only_thinking_returns_none(self):
        msg = {"content": [{"type": "thinking", "thinking": "internal"}]}
        self.assertIsNone(ch.extract_assistant_text(msg))

    def test_empty_message(self):
        self.assertIsNone(ch.extract_assistant_text({}))


# ---------------------------------------------------------------------------
# 2. parse_date
# ---------------------------------------------------------------------------

class TestParseDate(unittest.TestCase):

    def test_bare_date_gets_utc_then_local(self):
        dt = ch.parse_date("2026-01-15")
        # Naive → replaced with UTC → converted to local
        self.assertIsNotNone(dt.tzinfo)
        # The date should still be representable as the 15th in UTC
        utc = dt.astimezone(timezone.utc)
        self.assertEqual(utc.date().isoformat(), "2026-01-15")
        self.assertEqual(utc.hour, 0)
        self.assertEqual(utc.minute, 0)

    def test_full_iso_with_offset_preserved(self):
        dt = ch.parse_date("2026-06-10T14:30:00+02:00")
        self.assertIsNotNone(dt.tzinfo)
        # Offset-aware: 14:30 +02:00 = 12:30 UTC
        utc = dt.astimezone(timezone.utc)
        self.assertEqual(utc.hour, 12)
        self.assertEqual(utc.minute, 30)

    def test_z_suffix_iso(self):
        dt = ch.parse_date("2026-06-10T08:00:00Z")
        utc = dt.astimezone(timezone.utc)
        self.assertEqual(utc.hour, 8)


# ---------------------------------------------------------------------------
# 3. iter_entries
# ---------------------------------------------------------------------------

class TestIterEntries(unittest.TestCase):

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.projects = Path(self.tmpdir) / "projects"
        self.projects.mkdir()
        # Patch PROJECTS_DIR in the module
        self.patcher = unittest.mock.patch.object(ch, "PROJECTS_DIR", self.projects)
        self.patcher.start()
        # Truncate to whole seconds so make_ts() boundary values land exactly on
        # the comparison points (make_ts strips sub-second precision via strftime).
        now_raw = utc_now()
        self.now = now_raw.replace(microsecond=0)
        self.since = self.now - timedelta(hours=2)
        self.until = None

    def tearDown(self):
        self.patcher.stop()
        import shutil
        shutil.rmtree(self.tmpdir)

    def _make_project(self, name: str) -> Path:
        p = self.projects / name
        p.mkdir(exist_ok=True)
        return p

    def _make_session(self, project_dir: Path, session: str, events: list[dict]) -> Path:
        f = project_dir / f"{session}.jsonl"
        write_jsonl(f, events)
        return f

    def _collect(self, project_filter=None, drop_noise=False, since=None, until=None):
        s = since if since is not None else self.since
        return list(ch.iter_entries(s, until, project_filter, drop_noise))

    # --- basic happy path ---

    def test_yields_user_and_assistant(self):
        proj = self._make_project("-Users-test-app")
        ts = make_ts(self.now)
        self._make_session(proj, "sess1", [
            {"type": "user", "timestamp": ts, "sessionId": "sess1",
             "message": {"content": "Hello"}},
            {"type": "assistant", "timestamp": ts, "sessionId": "sess1",
             "message": {"content": "Hi there", "model": "claude-opus-4-5"}},
        ])
        entries = self._collect()
        self.assertEqual(len(entries), 2)
        self.assertEqual(entries[0].role, "user")
        self.assertEqual(entries[0].text, "Hello")
        self.assertEqual(entries[0].session_id, "sess1")
        self.assertEqual(entries[0].project, "/Users/test/app")
        self.assertEqual(entries[1].role, "assistant")
        self.assertEqual(entries[1].text, "Hi there")
        self.assertEqual(entries[1].model, "claude-opus-4-5")

    def test_skips_non_user_assistant_types(self):
        proj = self._make_project("-Users-test-app")
        ts = make_ts(self.now)
        self._make_session(proj, "sess1", [
            {"type": "system", "timestamp": ts, "message": {"content": "ignored"}},
            {"type": "tool_result", "timestamp": ts, "message": {"content": "ignored"}},
            {"type": "user", "timestamp": ts, "sessionId": "sess1",
             "message": {"content": "real"}},
        ])
        entries = self._collect()
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0].text, "real")

    def test_skips_invalid_json_lines(self):
        proj = self._make_project("-Users-test-app")
        ts = make_ts(self.now)
        f = proj / "sess.jsonl"
        f.write_text(
            'not valid json\n'
            + json.dumps({"type": "user", "timestamp": ts, "sessionId": "s",
                          "message": {"content": "ok"}}) + "\n",
            encoding="utf-8"
        )
        entries = self._collect()
        self.assertEqual(len(entries), 1)

    def test_skips_blank_lines(self):
        proj = self._make_project("-Users-test-app")
        ts = make_ts(self.now)
        f = proj / "sess.jsonl"
        f.write_text(
            "\n\n"
            + json.dumps({"type": "user", "timestamp": ts, "sessionId": "s",
                          "message": {"content": "ok"}}) + "\n",
            encoding="utf-8"
        )
        entries = self._collect()
        self.assertEqual(len(entries), 1)

    def test_skips_missing_timestamp(self):
        proj = self._make_project("-Users-test-app")
        self._make_session(proj, "sess1", [
            {"type": "user", "sessionId": "s", "message": {"content": "no ts"}},
        ])
        self.assertEqual(self._collect(), [])

    def test_skips_invalid_timestamp(self):
        proj = self._make_project("-Users-test-app")
        self._make_session(proj, "sess1", [
            {"type": "user", "timestamp": "bad-ts", "sessionId": "s",
             "message": {"content": "bad"}},
        ])
        self.assertEqual(self._collect(), [])

    def test_skips_missing_message(self):
        proj = self._make_project("-Users-test-app")
        ts = make_ts(self.now)
        self._make_session(proj, "sess1", [
            {"type": "user", "timestamp": ts, "sessionId": "s"},
        ])
        # missing message → extract_user_text({}) → None → skipped
        self.assertEqual(self._collect(), [])

    def test_session_id_defaults_to_empty(self):
        proj = self._make_project("-Users-test-app")
        ts = make_ts(self.now)
        self._make_session(proj, "sess1", [
            {"type": "user", "timestamp": ts, "message": {"content": "no session id"}},
        ])
        entries = self._collect()
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0].session_id, "")

    # --- window filtering ---

    def test_since_inclusive(self):
        proj = self._make_project("-Users-test-app")
        # Exactly at since boundary
        ts = make_ts(self.since)
        self._make_session(proj, "sess1", [
            {"type": "user", "timestamp": ts, "sessionId": "s",
             "message": {"content": "at boundary"}},
        ])
        entries = self._collect()
        self.assertEqual(len(entries), 1)

    def test_before_since_excluded(self):
        proj = self._make_project("-Users-test-app")
        old_ts = make_ts(self.since - timedelta(seconds=1))
        self._make_session(proj, "sess1", [
            {"type": "user", "timestamp": old_ts, "sessionId": "s",
             "message": {"content": "too old"}},
        ])
        entries = self._collect()
        self.assertEqual(len(entries), 0)

    def test_until_exclusive(self):
        proj = self._make_project("-Users-test-app")
        # already second-truncated because self.now is truncated
        until = self.now + timedelta(hours=1)
        # exactly at until → excluded (make_ts keeps second precision, so ts_at == until exactly)
        ts_at = make_ts(until)
        # one second before → included
        ts_before = make_ts(until - timedelta(seconds=1))
        self._make_session(proj, "sess1", [
            {"type": "user", "timestamp": ts_before, "sessionId": "s",
             "message": {"content": "included"}},
            {"type": "user", "timestamp": ts_at, "sessionId": "s",
             "message": {"content": "excluded"}},
        ])
        entries = self._collect(until=until)
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0].text, "included")

    # --- project filter ---

    def test_project_filter_matches_decoded_path(self):
        self._make_project("-Users-test-myapp")
        self._make_project("-Users-test-otherapp")
        proj = self.projects / "-Users-test-myapp"
        ts = make_ts(self.now)
        self._make_session(proj, "s", [
            {"type": "user", "timestamp": ts, "sessionId": "s",
             "message": {"content": "myapp entry"}},
        ])
        other = self.projects / "-Users-test-otherapp"
        self._make_session(other, "s", [
            {"type": "user", "timestamp": ts, "sessionId": "s",
             "message": {"content": "otherapp entry"}},
        ])
        entries = self._collect(project_filter="myapp")
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0].text, "myapp entry")

    def test_project_filter_matches_raw_encoded_name(self):
        proj = self._make_project("-Users-test-myapp")
        ts = make_ts(self.now)
        self._make_session(proj, "s", [
            {"type": "user", "timestamp": ts, "sessionId": "s",
             "message": {"content": "hit"}},
        ])
        # Filter by encoded dir name substring
        entries = self._collect(project_filter="-Users-test-myapp")
        self.assertEqual(len(entries), 1)

    # --- drop_noise ---

    def test_drop_noise_filters_user_prompts(self):
        proj = self._make_project("-Users-test-app")
        ts = make_ts(self.now)
        noise = "<local-command-caveat>x</local-command-caveat>"
        self._make_session(proj, "s", [
            {"type": "user", "timestamp": ts, "sessionId": "s",
             "message": {"content": noise}},
            {"type": "user", "timestamp": ts, "sessionId": "s",
             "message": {"content": "real prompt"}},
        ])
        entries = self._collect(drop_noise=True)
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0].text, "real prompt")

    def test_drop_noise_never_filters_assistant(self):
        proj = self._make_project("-Users-test-app")
        ts = make_ts(self.now)
        # Assistant content that matches a noise pattern
        noise_like = "## Context Usage\n\nsome usage stats"
        self._make_session(proj, "s", [
            {"type": "assistant", "timestamp": ts, "sessionId": "s",
             "message": {"content": noise_like, "model": "claude-3"}},
        ])
        entries = self._collect(drop_noise=True)
        self.assertEqual(len(entries), 1)

    # --- old mtime skips file ---

    def test_old_mtime_file_skipped(self):
        proj = self._make_project("-Users-test-app")
        ts = make_ts(self.now)
        f = self._make_session(proj, "s", [
            {"type": "user", "timestamp": ts, "sessionId": "s",
             "message": {"content": "entry in old file"}},
        ])
        # Set mtime to before since window
        old_time = (self.since - timedelta(hours=1)).timestamp()
        os.utime(f, (old_time, old_time))
        entries = self._collect()
        self.assertEqual(len(entries), 0)

    # --- nonexistent PROJECTS_DIR ---

    def test_nonexistent_projects_dir_yields_nothing(self):
        with unittest.mock.patch.object(ch, "PROJECTS_DIR", Path(self.tmpdir) / "nonexistent"):
            entries = list(ch.iter_entries(self.since, self.until, None, False))
        self.assertEqual(entries, [])


# ---------------------------------------------------------------------------
# 4. main / formats
# ---------------------------------------------------------------------------

class TestMainFormats(unittest.TestCase):

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.projects = Path(self.tmpdir) / "projects"
        self.projects.mkdir()
        self.patcher = unittest.mock.patch.object(ch, "PROJECTS_DIR", self.projects)
        self.patcher.start()
        self.now = utc_now()
        # Full ISO timestamp, not a bare date: parse_date treats bare dates as UTC
        # midnight, which makes a date-only --since flaky around local midnight.
        self.since = (self.now - timedelta(hours=1)).astimezone().isoformat()

    def tearDown(self):
        self.patcher.stop()
        import shutil
        shutil.rmtree(self.tmpdir)

    def _make_project(self, name: str) -> Path:
        p = self.projects / name
        p.mkdir(exist_ok=True)
        return p

    def _write_entries(self, proj_name: str, session: str, events: list[dict]) -> None:
        proj = self._make_project(proj_name)
        write_jsonl(proj / f"{session}.jsonl", events)

    def _simple_pair(self, session="sess1", proj="-Users-test-app"):
        """Write a simple user+assistant pair with current timestamps."""
        ts = make_ts(self.now)
        self._write_entries(proj, session, [
            {"type": "user", "timestamp": ts, "sessionId": session,
             "message": {"content": "What is 2+2?"}},
            {"type": "assistant", "timestamp": ts, "sessionId": session,
             "message": {"content": "It is 4.", "model": "claude-opus-4-5"}},
        ])

    # --- jsonl format ---

    def test_jsonl_output_keys(self):
        self._simple_pair()
        out, _ = capture_main(["--format", "jsonl", "--since", self.since])
        lines = [l for l in out.strip().split("\n") if l]
        self.assertEqual(len(lines), 2)
        obj = json.loads(lines[0])
        for key in ("timestamp", "role", "model", "session", "project", "text"):
            self.assertIn(key, obj)

    def test_jsonl_user_entry(self):
        self._simple_pair()
        out, _ = capture_main(["--format", "jsonl", "--since", self.since])
        lines = [json.loads(l) for l in out.strip().split("\n") if l]
        user = next(l for l in lines if l["role"] == "user")
        self.assertEqual(user["text"], "What is 2+2?")
        self.assertIsNone(user["model"])

    def test_jsonl_assistant_entry(self):
        self._simple_pair()
        out, _ = capture_main(["--format", "jsonl", "--since", self.since])
        lines = [json.loads(l) for l in out.strip().split("\n") if l]
        asst = next(l for l in lines if l["role"] == "assistant")
        self.assertEqual(asst["text"], "It is 4.")
        self.assertEqual(asst["model"], "claude-opus-4-5")

    # --- json format ---

    def test_json_format_is_array(self):
        self._simple_pair()
        out, _ = capture_main(["--format", "json", "--since", self.since])
        data = json.loads(out)
        self.assertIsInstance(data, list)

    def test_json_pair_structure(self):
        self._simple_pair()
        out, _ = capture_main(["--format", "json", "--since", self.since])
        pairs = json.loads(out)
        self.assertEqual(len(pairs), 1)
        pair = pairs[0]
        for key in ("timestamp", "session", "project", "model", "prompt", "answer", "answer_timestamp"):
            self.assertIn(key, pair)
        self.assertEqual(pair["prompt"], "What is 2+2?")
        self.assertEqual(pair["answer"], "It is 4.")
        self.assertEqual(pair["model"], "claude-opus-4-5")

    def test_json_shortcut_flag(self):
        self._simple_pair()
        out, _ = capture_main(["--json", "--since", self.since])
        data = json.loads(out)
        self.assertIsInstance(data, list)

    def test_html_shortcut_flag(self):
        self._simple_pair()
        out, _ = capture_main(["--html", "--since", self.since])
        self.assertIn("Claude Code history", out)
        self.assertIn("const DATA", out)

    # --- pairing rules §9.2 ---

    def test_pairing_consecutive_user_prompts(self):
        """Two consecutive user prompts → two pairs (first with empty answer)."""
        ts1 = make_ts(self.now - timedelta(minutes=5))
        ts2 = make_ts(self.now - timedelta(minutes=4))
        ts3 = make_ts(self.now - timedelta(minutes=3))
        proj = self._make_project("-Users-test-app")
        write_jsonl(proj / "sess.jsonl", [
            {"type": "user", "timestamp": ts1, "sessionId": "s",
             "message": {"content": "First question"}},
            {"type": "user", "timestamp": ts2, "sessionId": "s",
             "message": {"content": "Second question"}},
            {"type": "assistant", "timestamp": ts3, "sessionId": "s",
             "message": {"content": "Answer to second", "model": "m"}},
        ])
        out, _ = capture_main(["--format", "json", "--since", self.since])
        pairs = json.loads(out)
        self.assertEqual(len(pairs), 2)
        # First pair has empty answer
        self.assertEqual(pairs[0]["prompt"], "First question")
        self.assertEqual(pairs[0]["answer"], "")
        # Second pair has the answer
        self.assertEqual(pairs[1]["prompt"], "Second question")
        self.assertEqual(pairs[1]["answer"], "Answer to second")

    def test_pairing_assistant_first_prompt_less(self):
        """Assistant entry with no preceding user → prompt-less pair."""
        ts = make_ts(self.now)
        proj = self._make_project("-Users-test-app")
        write_jsonl(proj / "sess.jsonl", [
            {"type": "assistant", "timestamp": ts, "sessionId": "s",
             "message": {"content": "Unsolicited answer", "model": "m"}},
        ])
        out, _ = capture_main(["--format", "json", "--since", self.since])
        pairs = json.loads(out)
        self.assertEqual(len(pairs), 1)
        self.assertIsNone(pairs[0]["prompt"])
        self.assertEqual(pairs[0]["answer"], "Unsolicited answer")

    def test_pairing_session_change_starts_new_pair(self):
        """Mid-answer session change starts a new pair."""
        ts1 = make_ts(self.now - timedelta(minutes=3))
        ts2 = make_ts(self.now - timedelta(minutes=2))
        ts3 = make_ts(self.now - timedelta(minutes=1))
        proj = self._make_project("-Users-test-app")
        write_jsonl(proj / "sess.jsonl", [
            {"type": "user", "timestamp": ts1, "sessionId": "sess-A",
             "message": {"content": "Question A"}},
            {"type": "assistant", "timestamp": ts2, "sessionId": "sess-A",
             "message": {"content": "Answer A", "model": "m"}},
            # Session changes — this assistant goes to new pair
            {"type": "assistant", "timestamp": ts3, "sessionId": "sess-B",
             "message": {"content": "Answer B", "model": "m"}},
        ])
        out, _ = capture_main(["--format", "json", "--since", self.since])
        pairs = json.loads(out)
        self.assertEqual(len(pairs), 2)
        self.assertEqual(pairs[0]["session"], "sess-A")
        self.assertEqual(pairs[1]["session"], "sess-B")
        self.assertIsNone(pairs[1]["prompt"])

    def test_pairing_multiple_assistant_concatenated(self):
        """Multiple consecutive assistant messages concatenated with \\n\\n."""
        ts1 = make_ts(self.now - timedelta(minutes=3))
        ts2 = make_ts(self.now - timedelta(minutes=2))
        ts3 = make_ts(self.now - timedelta(minutes=1))
        proj = self._make_project("-Users-test-app")
        write_jsonl(proj / "sess.jsonl", [
            {"type": "user", "timestamp": ts1, "sessionId": "s",
             "message": {"content": "Question"}},
            {"type": "assistant", "timestamp": ts2, "sessionId": "s",
             "message": {"content": "Part one", "model": "m"}},
            {"type": "assistant", "timestamp": ts3, "sessionId": "s",
             "message": {"content": "Part two", "model": "m"}},
        ])
        out, _ = capture_main(["--format", "json", "--since", self.since])
        pairs = json.loads(out)
        self.assertEqual(len(pairs), 1)
        self.assertEqual(pairs[0]["answer"], "Part one\n\nPart two")

    def test_pairing_first_assistant_timestamp_wins(self):
        """First assistant timestamp is used even when multiple assistant messages."""
        ts1 = make_ts(self.now - timedelta(minutes=3))
        ts2 = make_ts(self.now - timedelta(minutes=2))
        ts3 = make_ts(self.now - timedelta(minutes=1))
        proj = self._make_project("-Users-test-app")
        write_jsonl(proj / "sess.jsonl", [
            {"type": "user", "timestamp": ts1, "sessionId": "s",
             "message": {"content": "Question"}},
            {"type": "assistant", "timestamp": ts2, "sessionId": "s",
             "message": {"content": "First part", "model": "first-model"}},
            {"type": "assistant", "timestamp": ts3, "sessionId": "s",
             "message": {"content": "Second part", "model": "second-model"}},
        ])
        out, _ = capture_main(["--format", "json", "--since", self.since])
        pairs = json.loads(out)
        self.assertEqual(pairs[0]["model"], "first-model")
        # answer_timestamp matches ts2
        expected_ts = ch.parse_ts(ts2).astimezone().isoformat()
        self.assertEqual(pairs[0]["answer_timestamp"], expected_ts)

    def test_pairing_first_non_null_model_wins(self):
        """First non-null model wins over subsequent ones."""
        ts1 = make_ts(self.now - timedelta(minutes=3))
        ts2 = make_ts(self.now - timedelta(minutes=2))
        ts3 = make_ts(self.now - timedelta(minutes=1))
        proj = self._make_project("-Users-test-app")
        write_jsonl(proj / "sess.jsonl", [
            {"type": "user", "timestamp": ts1, "sessionId": "s",
             "message": {"content": "Q"}},
            {"type": "assistant", "timestamp": ts2, "sessionId": "s",
             "message": {"content": "P1"}},  # no model field → None
            {"type": "assistant", "timestamp": ts3, "sessionId": "s",
             "message": {"content": "P2", "model": "second-model"}},
        ])
        out, _ = capture_main(["--format", "json", "--since", self.since])
        pairs = json.loads(out)
        self.assertEqual(pairs[0]["model"], "second-model")

    # --- truncation ---

    def test_trunc_max_chars(self):
        ts = make_ts(self.now)
        proj = self._make_project("-Users-test-app")
        long_text = "A" * 100
        write_jsonl(proj / "sess.jsonl", [
            {"type": "user", "timestamp": ts, "sessionId": "s",
             "message": {"content": long_text}},
        ])
        out, _ = capture_main(["--format", "jsonl", "--max-chars", "10", "--since", self.since])
        obj = json.loads(out.strip())
        self.assertIn("truncated, 100 chars total", obj["text"])
        self.assertIn("… [truncated,", obj["text"])

    def test_trunc_max_chars_zero_no_truncation(self):
        ts = make_ts(self.now)
        proj = self._make_project("-Users-test-app")
        long_text = "B" * 5000
        write_jsonl(proj / "sess.jsonl", [
            {"type": "user", "timestamp": ts, "sessionId": "s",
             "message": {"content": long_text}},
        ])
        out, _ = capture_main(["--format", "jsonl", "--max-chars", "0", "--since", self.since])
        obj = json.loads(out.strip())
        self.assertEqual(obj["text"], long_text)

    # --- text format ---

    def test_text_session_header(self):
        self._simple_pair(session="abcdefgh1234")
        out, _ = capture_main(["--format", "text", "--since", self.since])
        self.assertIn("=== Session abcdefgh — /Users/test/app ===", out)

    def test_text_user_line(self):
        self._simple_pair()
        out, _ = capture_main(["--format", "text", "--since", self.since])
        self.assertIn("] USER", out)

    def test_text_assistant_line(self):
        self._simple_pair()
        out, _ = capture_main(["--format", "text", "--since", self.since])
        self.assertIn("ASSISTANT (claude-opus-4-5)", out)

    # --- md format ---

    def test_md_session_header(self):
        self._simple_pair(session="abcdefgh1234")
        out, _ = capture_main(["--format", "md", "--since", self.since])
        self.assertIn("## Session `abcdefgh`", out)
        self.assertIn("/Users/test/app", out)

    def test_md_entry_header(self):
        self._simple_pair()
        out, _ = capture_main(["--format", "md", "--since", self.since])
        self.assertIn("### [", out)
        self.assertIn("] USER", out)

    # --- empty result stderr ---

    def test_empty_text_prints_to_stderr(self):
        # No entries
        out, err = capture_main(["--format", "text", "--since", "2099-01-01"])
        self.assertIn("No entries found since", err)

    def test_empty_json_no_stderr(self):
        out, err = capture_main(["--format", "json", "--since", "2099-01-01"])
        self.assertNotIn("No entries found since", err)
        data = json.loads(out)
        self.assertEqual(data, [])

    def test_empty_jsonl_no_stderr(self):
        out, err = capture_main(["--format", "jsonl", "--since", "2099-01-01"])
        self.assertNotIn("No entries found since", err)
        self.assertEqual(out.strip(), "")

    def test_empty_html_no_stderr(self):
        out, err = capture_main(["--format", "html", "--since", "2099-01-01"])
        self.assertNotIn("No entries found since", err)
        self.assertIn("const DATA", out)

    def test_empty_md_prints_to_stderr(self):
        out, err = capture_main(["--format", "md", "--since", "2099-01-01"])
        self.assertIn("No entries found since", err)

    # --- html content ---

    def test_html_contains_data(self):
        self._simple_pair()
        out, _ = capture_main(["--html", "--since", self.since])
        self.assertIn("const DATA", out)

    def test_html_escapes_script_end_tag(self):
        """</  in data must be escaped as <\\/ so it can't break out of <script>."""
        ts = make_ts(self.now)
        proj = self._make_project("-Users-test-app")
        # Inject </script> in the prompt text
        write_jsonl(proj / "sess.jsonl", [
            {"type": "user", "timestamp": ts, "sessionId": "s",
             "message": {"content": "foo </script> bar"}},
        ])
        out, _ = capture_main(["--html", "--since", self.since])
        # The literal </script> must not appear unescaped inside the JSON data
        # render_html replaces "</" with "<\/"
        self.assertNotIn("</script>", out.split("const DATA")[1].split(";\n")[0])
        self.assertIn("<\\/script>", out)

    def test_html_title_replaced(self):
        self._simple_pair()
        out, _ = capture_main(["--html", "--since", self.since])
        self.assertNotIn("__TITLE__", out)
        self.assertIn("Claude Code history", out)


# ---------------------------------------------------------------------------
# 5. --days / --since mutual exclusion
# ---------------------------------------------------------------------------

class TestMutualExclusion(unittest.TestCase):

    def test_days_and_since_mutually_exclusive(self):
        with self.assertRaises(SystemExit) as ctx:
            out = io.StringIO()
            err = io.StringIO()
            with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                ch.main(["--days", "3", "--since", "2026-01-01"])
        self.assertEqual(ctx.exception.code, 2)


# ---------------------------------------------------------------------------
# Additional edge-case tests
# ---------------------------------------------------------------------------

class TestIterEntriesEdgeCases(unittest.TestCase):
    """Additional edge-cases not covered by the primary test class."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.projects = Path(self.tmpdir) / "projects"
        self.projects.mkdir()
        self.patcher = unittest.mock.patch.object(ch, "PROJECTS_DIR", self.projects)
        self.patcher.start()
        self.now = utc_now()
        self.since = self.now - timedelta(hours=2)

    def tearDown(self):
        self.patcher.stop()
        import shutil
        shutil.rmtree(self.tmpdir)

    def test_user_entry_with_extract_none_skipped(self):
        """User event where extract_user_text returns None is skipped."""
        proj = self.projects / "-Users-test"
        proj.mkdir()
        ts = make_ts(self.now)
        # content is a list of only tool_result blocks → extract_user_text returns None
        write_jsonl(proj / "s.jsonl", [
            {"type": "user", "timestamp": ts, "sessionId": "s",
             "message": {"content": [{"type": "tool_result", "content": "x"}]}},
        ])
        entries = list(ch.iter_entries(self.since, None, None, False))
        self.assertEqual(entries, [])

    def test_assistant_entry_with_extract_none_skipped(self):
        """Assistant event where extract_assistant_text returns None is skipped."""
        proj = self.projects / "-Users-test"
        proj.mkdir()
        ts = make_ts(self.now)
        write_jsonl(proj / "s.jsonl", [
            {"type": "assistant", "timestamp": ts, "sessionId": "s",
             "message": {"content": [{"type": "tool_use", "name": "bash"}]}},
        ])
        entries = list(ch.iter_entries(self.since, None, None, False))
        self.assertEqual(entries, [])

    def test_files_not_directory_skipped(self):
        """Non-directory items inside projects dir are skipped."""
        (self.projects / "not_a_dir.txt").write_text("irrelevant")
        ts = make_ts(self.now)
        entries = list(ch.iter_entries(self.since, None, None, False))
        self.assertEqual(entries, [])

    def test_falsy_message_treated_as_empty_dict(self):
        """message=null or missing → treated as {} → extract returns None → skipped."""
        proj = self.projects / "-Users-test"
        proj.mkdir()
        ts = make_ts(self.now)
        write_jsonl(proj / "s.jsonl", [
            {"type": "user", "timestamp": ts, "sessionId": "s", "message": None},
        ])
        entries = list(ch.iter_entries(self.since, None, None, False))
        self.assertEqual(entries, [])


class TestMainNoNoise(unittest.TestCase):

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.projects = Path(self.tmpdir) / "projects"
        self.projects.mkdir()
        self.patcher = unittest.mock.patch.object(ch, "PROJECTS_DIR", self.projects)
        self.patcher.start()
        self.now = utc_now()
        # Full ISO timestamp, not a bare date: parse_date treats bare dates as UTC
        # midnight, which makes a date-only --since flaky around local midnight.
        self.since = (self.now - timedelta(hours=1)).astimezone().isoformat()

    def tearDown(self):
        self.patcher.stop()
        import shutil
        shutil.rmtree(self.tmpdir)

    def test_no_noise_flag_drops_noise(self):
        proj = self.projects / "-Users-test"
        proj.mkdir()
        ts = make_ts(self.now)
        write_jsonl(proj / "s.jsonl", [
            {"type": "user", "timestamp": ts, "sessionId": "s",
             "message": {"content": "<local-command-caveat>x</local-command-caveat>"}},
            {"type": "user", "timestamp": ts, "sessionId": "s",
             "message": {"content": "real prompt"}},
        ])
        out, _ = capture_main(["--format", "jsonl", "--no-noise", "--since", self.since])
        lines = [json.loads(l) for l in out.strip().split("\n") if l]
        self.assertEqual(len(lines), 1)
        self.assertEqual(lines[0]["text"], "real prompt")


if __name__ == "__main__":
    unittest.main()
