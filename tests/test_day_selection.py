"""Single-day selection shared by both installed commands."""
import contextlib
from datetime import date, datetime, timedelta
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
import claude_history as ch
import codex_history as cx


class FixedDateTime(datetime):
    @classmethod
    def now(cls, tz=None):
        return cls(2026, 11, 5, 12, tzinfo=tz)


class TestDaySelection(unittest.TestCase):
    def window(self, command, day):
        module = ch if command is ch.main else cx
        with patch.object(module, "iter_entries", return_value=[]) as reader:
            with patch.object(ch, "datetime", FixedDateTime):
                with contextlib.redirect_stdout(io.StringIO()):
                    self.assertEqual(command(["--day", day, "--json"]), 0)
        return reader.call_args.args[:2]

    def test_relative_offsets_and_explicit_dates(self):
        for command in (ch.main, cx.main):
            for value, expected in [("0", date(2026, 11, 5)), ("-1", date(2026, 11, 4)),
                                    ("-7", date(2026, 10, 29)), ("1", date(2026, 11, 6)),
                                    ("2026-05-01", date(2026, 5, 1))]:
                with self.subTest(command=command.__module__, day=value):
                    since, until = self.window(command, value)
                    self.assertEqual(since.astimezone().date(), expected)
                    self.assertEqual(until.astimezone().date(), expected + timedelta(days=1))
                    self.assertEqual(since.astimezone().hour, 0)
                    self.assertEqual(until.astimezone().hour, 0)

    @unittest.skipUnless(hasattr(time, "tzset"), "requires local timezone switching")
    def test_dst_days_use_two_local_midnights(self):
        try:
            with patch.dict(os.environ, TZ="Europe/Berlin"):
                time.tzset()
                for day, hours in [("2026-03-29", 23), ("2026-10-25", 25)]:
                    for command in (ch.main, cx.main):
                        since, until = self.window(command, day)
                        self.assertEqual((until - since).total_seconds(), hours * 3600)
        finally:
            time.tzset()

    def test_invalid_days_and_conflicting_arguments(self):
        cases = [["--day", value] for value in
                 ("yesterday", "2026-02-30", "2026-1-1", "2026-11-04T12:00:00Z",
                  "999999999999999", "9999-12-31")]
        cases += [["--day", "-1", flag, value] for flag, value in
                  [("--days", "2"), ("--since", "2026-11-01"), ("--until", "2026-11-05")]]
        for command in (ch.main, cx.main):
            for args in cases:
                with self.subTest(command=command.__module__, args=args):
                    with contextlib.redirect_stderr(io.StringIO()):
                        with self.assertRaises(SystemExit) as error:
                            command(args)
                    self.assertEqual(error.exception.code, 2)

    def test_single_day_includes_start_and_excludes_next_midnight(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            project = home / "projects" / "-work-app"
            project.mkdir(parents=True)
            rollout = home / "sessions" / "rollout.jsonl"
            rollout.parent.mkdir()
            timestamps = ["2026-11-03T23:59:59", "2026-11-04T00:00:00",
                          "2026-11-04T23:59:59", "2026-11-05T00:00:00"]
            claude_events, codex_events = [], [{"type": "session_meta", "payload": {"id": "s", "cwd": "/work/app"}}]
            for i, timestamp in enumerate(timestamps):
                ts = datetime.fromisoformat(timestamp).astimezone().isoformat()
                claude_events.append({"type": "user", "sessionId": "s", "cwd": "/work/app",
                                      "timestamp": ts, "message": {"content": str(i)}})
                codex_events.append({"type": "response_item", "timestamp": ts, "payload": {
                    "type": "message", "role": "user", "content": [{"type": "input_text", "text": str(i)}]}})
            transcript = project / "s.jsonl"
            transcript.write_text("\n".join(map(json.dumps, claude_events)))
            # Ensure Claude's mtime shortcut cannot discard the fixture.
            os.utime(transcript, (2000000000, 2000000000))
            rollout.write_text("\n".join(map(json.dumps, codex_events)))
            with patch.object(ch, "PROJECTS_DIR", home / "projects"), patch.dict(os.environ, CODEX_HOME=tmp):
                for command in (ch.main, cx.main):
                    for args in (["--day", "2026-11-04"], ["--day", "-1"]):
                        with patch.object(ch, "datetime", FixedDateTime):
                            with contextlib.redirect_stdout(io.StringIO()) as output:
                                command([*args, "--json"])
                        self.assertEqual([p["prompt"] for p in json.loads(output.getvalue())], ["1", "2"])


if __name__ == "__main__":
    unittest.main()
