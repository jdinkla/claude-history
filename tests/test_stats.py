"""
Test suite for stats.py (stdlib-only, unittest).

Run with:
    python3 -m unittest -v

All fixture timestamps carry explicit UTC offsets so derived date/weekday/hour
values are independent of the machine's timezone and time of day (stats.py
derives them from the local time as written — specs/STATISTICS.md §4).
"""

from __future__ import annotations

import unittest

# Make the modules under src/ importable when tests run from the repo root.
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import stats


def pair(ts, *, session="s1", project="/p/alpha", model="m1",
         prompt="hello", answer="ok", answer_ts=None):
    return {
        "timestamp": ts,
        "session": session,
        "project": project,
        "model": model,
        "prompt": prompt,
        "answer": answer,
        "answer_timestamp": answer_ts if answer_ts is not None else ts,
    }


# 2026-03-02 is a Monday.
MON_9 = "2026-03-02T09:15:00+01:00"
MON_10 = "2026-03-02T10:05:00+01:00"
THU_22 = "2026-03-05T22:40:00+01:00"


class TestClassificationCounts(unittest.TestCase):
    def test_kinds_and_none_model(self):
        pairs = [
            pair(MON_9),
            pair(MON_10, prompt="<command-name>/clear</command-name>"),
            pair(THU_22, prompt="[Request interrupted by user]"),
            # assistant-only pair: no prompt, no prompt timestamp, no model
            pair(None, prompt=None, model=None, answer_ts=THU_22),
        ]
        s = stats.compute_stats(pairs)
        self.assertEqual(s["totals"]["pairs"], 4)
        self.assertEqual(s["totals"]["human"], 1)
        self.assertEqual(s["totals"]["kinds"], {
            "human": 1, "slash_command": 1, "interruption": 1,
            "local_command": 0, "context_dump": 0, "assistant_only": 1,
        })
        self.assertEqual(s["by_model"], [
            {"model": "m1", "pairs": 3}, {"model": "(none)", "pairs": 1},
        ])

    def test_project_rollup(self):
        pairs = [
            pair(MON_9, project="/p/alpha", session="s1"),
            pair(MON_10, project="/p/alpha", session="s2",
                 prompt="<command-name>/x</command-name>"),
            pair(THU_22, project="/p/beta", session="s3"),
        ]
        s = stats.compute_stats(pairs)
        self.assertEqual(s["totals"]["sessions"], 3)
        self.assertEqual(s["totals"]["projects"], 2)
        # alpha and beta both have 1 human prompt; ties break by project name
        self.assertEqual(
            [(r["project"], r["pairs"], r["human"], r["sessions"]) for r in s["by_project"]],
            [("/p/alpha", 2, 1, 2), ("/p/beta", 1, 1, 1)],
        )
        self.assertEqual(s["by_project"][0]["models"], {"m1": 2})


class TestTimeDimensions(unittest.TestCase):
    def test_by_day_fills_gaps(self):
        s = stats.compute_stats([pair(MON_9), pair(THU_22)])
        self.assertEqual([r["date"] for r in s["by_day"]],
                         ["2026-03-02", "2026-03-03", "2026-03-04", "2026-03-05"])
        self.assertEqual([r["pairs"] for r in s["by_day"]], [1, 0, 0, 1])
        self.assertEqual(s["totals"]["active_days"], 2)
        self.assertEqual(s["range"], {"first": MON_9, "last": THU_22})

    def test_weekday_rows_fixed_monday_first(self):
        s = stats.compute_stats([pair(MON_9), pair(MON_10), pair(THU_22)])
        self.assertEqual([r["weekday"] for r in s["by_weekday"]],
                         ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"])
        self.assertEqual([r["pairs"] for r in s["by_weekday"]],
                         [2, 0, 0, 1, 0, 0, 0])

    def test_hour_rows_fixed_24_local_time_as_written(self):
        s = stats.compute_stats([pair(MON_9), pair(THU_22)])
        self.assertEqual(len(s["by_hour"]), 24)
        # Hours come from the written local time (09 and 22), regardless of
        # the executing machine's timezone.
        self.assertEqual(s["by_hour"][9]["pairs"], 1)
        self.assertEqual(s["by_hour"][22]["pairs"], 1)
        self.assertEqual(sum(r["pairs"] for r in s["by_hour"]), 2)

    def test_answer_timestamp_fallback(self):
        s = stats.compute_stats([pair(None, prompt=None, answer_ts=THU_22)])
        self.assertEqual(s["by_day"][0]["date"], "2026-03-05")
        self.assertEqual(s["by_hour"][22]["pairs"], 1)
        self.assertEqual(s["range"]["first"], THU_22)

    def test_no_timestamps_counted_in_non_time_dims_only(self):
        s = stats.compute_stats([pair(None, prompt=None, model=None, answer_ts=None)])
        self.assertEqual(s["totals"]["pairs"], 1)
        self.assertEqual(s["by_day"], [])
        self.assertEqual(sum(r["pairs"] for r in s["by_weekday"]), 0)
        self.assertEqual(s["range"], {"first": None, "last": None})
        self.assertEqual(s["by_project"][0]["pairs"], 1)


class TestSessions(unittest.TestCase):
    def test_distribution_and_duration(self):
        pairs = [
            pair(MON_9, session="a", answer_ts=MON_10),   # 50 min span
            pair(MON_10, session="a"),
            pair(THU_22, session="b",
                 prompt="<command-name>/x</command-name>"),
        ]
        s = stats.compute_stats(pairs)
        sess = s["sessions"]
        self.assertEqual(sess["per_session_pairs"],
                         {"min": 1, "median": 1.5, "mean": 1.5, "max": 2})
        self.assertEqual(sess["per_session_human"],
                         {"min": 0, "median": 1.0, "mean": 1.0, "max": 2})
        top = sess["top"]
        self.assertEqual(top[0]["session"], "a")
        self.assertEqual(top[0]["duration_minutes"], 50)
        self.assertEqual(top[0]["first"], MON_9)
        self.assertEqual(top[0]["last"], MON_10)
        self.assertEqual(top[1]["session"], "b")
        self.assertEqual(top[1]["human"], 0)

    def test_top_ordering_and_cap(self):
        pairs = []
        for i in range(5):
            sid = f"s{i}"
            for j in range(i + 1):
                pairs.append(pair(MON_9, session=sid, project="/p"))
        s = stats.compute_stats(pairs, top_n=3)
        top = s["sessions"]["top"]
        self.assertEqual(len(top), 3)
        self.assertEqual([r["human"] for r in top], [5, 4, 3])


class TestEmptyInput(unittest.TestCase):
    def test_empty_shape(self):
        s = stats.compute_stats([])
        self.assertEqual(s["range"], {"first": None, "last": None})
        self.assertEqual(s["totals"], {
            "pairs": 0, "human": 0,
            "kinds": {"human": 0, "slash_command": 0, "interruption": 0,
                      "local_command": 0, "context_dump": 0, "assistant_only": 0},
            "sessions": 0, "projects": 0, "active_days": 0,
        })
        self.assertEqual(s["by_project"], [])
        self.assertEqual(s["by_day"], [])
        self.assertEqual(len(s["by_weekday"]), 7)
        self.assertEqual(len(s["by_hour"]), 24)
        self.assertEqual(s["by_model"], [])
        self.assertEqual(s["sessions"]["top"], [])
        self.assertEqual(s["sessions"]["per_session_pairs"],
                         {"min": 0, "median": 0, "mean": 0.0, "max": 0})


class TestHtml(unittest.TestCase):
    def test_embeds_data_and_escapes(self):
        s = stats.compute_stats([pair(MON_9, project="/p/<script>alert</script>")])
        html = stats.render_html(s, "T<itle")
        self.assertIn('"pairs": 1'.replace(" ", ""), html.replace(" ", ""))
        self.assertIn("T&lt;itle", html)
        # embedded </script> in data must be escaped
        self.assertIn("<\\/script>", html)
        self.assertNotIn("</script>alert", html)

    def test_no_external_resources(self):
        html = stats.render_html(stats.compute_stats([]), "t")
        for attr in ("src=", "href="):
            for proto in ("http://", "https://", "//"):
                self.assertNotIn(f'{attr}"{proto}', html)
        self.assertNotIn("@import", html)
        self.assertNotIn("url(http", html)


if __name__ == "__main__":
    unittest.main()
