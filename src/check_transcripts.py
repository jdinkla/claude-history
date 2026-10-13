#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Check claude_history's assumptions against the real transcripts.

Runs the real extraction over a recent window and scans the same raw
transcript files for facts the extraction relies on: project paths match the
recorded cwd, concurrent sessions don't orphan answers, user content has a
handled shape, and no machine-originated prompt passes as human. It also
reports event types and user-event keys outside a known baseline, so
transcript-format drift after a Claude Code update gets noticed.

Output is one line per check: counts, session-id prefixes and field names,
never prompt or answer text. Exit status 1 if any check FAILs; WARN lines
don't affect it.
"""

from __future__ import annotations

import argparse
import contextlib
import io
import json
import sys
from collections import Counter
from datetime import datetime, timedelta, timezone

import claude_history as ch

# Baseline observed 2026-10-13. Extend it after reviewing a WARN line.
KNOWN_EVENT_TYPES = {
    "user", "assistant", "system", "summary", "attachment", "mode",
    "permission-mode", "file-history-snapshot", "file-history-delta",
    "cost-state", "last-prompt", "queue-operation", "custom-title",
    "ai-title", "agent-name", "atis-latch",
}
KNOWN_USER_KEYS = {
    "classifierMetaLines", "cwd", "entrypoint", "gitBranch", "imagePasteIds",
    "interruptedMessageId", "isCompactSummary", "isMeta", "isSidechain",
    "isVisibleInTranscriptOnly", "mcpMeta", "message", "origin", "parentUuid",
    "permissionDecision", "permissionMode", "promptId", "promptSource",
    "queueSkipAttachments", "serverClassifierContext", "sessionId",
    "session_id", "sourceToolAssistantUUID", "sourceToolUseID", "taskDelivery",
    "timestamp", "toolDenialKind", "toolUseResult", "turnCompanion",
    "turnOrigin", "turnPosition", "type", "userType", "uuid", "version",
}
KNOWN_USER_BLOCKS = {"text", "tool_result", "image"}

MAX_LISTED = 5


def window_start(days: int) -> datetime:
    """Local midnight days-1 days ago, the same window as `--days`."""
    midnight = datetime.now().astimezone().replace(hour=0, minute=0, second=0, microsecond=0)
    return midnight - timedelta(days=max(days - 1, 0))


def extract_pairs(since: datetime) -> list[dict]:
    out = io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
        ch.main(["--since", since.isoformat(), "--max-chars", "0", "--format", "json"])
    return json.loads(out.getvalue())


def content_shape_ok(content) -> bool:
    if isinstance(content, str):
        return True
    if not isinstance(content, list):
        return False
    return all(isinstance(b, dict) and b.get("type") in KNOWN_USER_BLOCKS for b in content)


def scan(since: datetime) -> dict:
    """Collect raw facts from the in-window transcript files."""
    since_utc = since.astimezone(timezone.utc)
    first_cwd: dict[str, str] = {}
    bad_shapes: list[str] = []
    machine: dict[tuple[str, str], str] = {}  # (session, prompt text) -> flag
    new_types: set[str] = set()
    new_keys: set[str] = set()

    result = {"first_cwd": first_cwd, "bad_shapes": bad_shapes, "machine": machine,
              "new_types": new_types, "new_keys": new_keys}
    if not ch.PROJECTS_DIR.is_dir():
        return result

    for jsonl in sorted(ch.PROJECTS_DIR.glob("*/*.jsonl")):
        if datetime.fromtimestamp(jsonl.stat().st_mtime, tz=timezone.utc) < since_utc:
            continue
        try:
            f = open(jsonl, "r", encoding="utf-8", errors="replace")
        except OSError:
            continue
        with f:
            for line in f:
                try:
                    ev = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if not isinstance(ev, dict):
                    continue
                etype = ev.get("type")
                if etype not in KNOWN_EVENT_TYPES:
                    new_types.add(str(etype))
                session = ev.get("sessionId", "")
                if ev.get("cwd") and session and session not in first_cwd:
                    first_cwd[session] = ev["cwd"]
                if etype != "user":
                    continue
                new_keys.update(k for k in ev if k not in KNOWN_USER_KEYS)

                ts = ch.parse_ts(ev.get("timestamp", ""))
                if ts is None or ts < since_utc:
                    continue
                message = ev.get("message") or {}
                if not content_shape_ok(message.get("content")):
                    bad_shapes.append(session)
                text = ch.extract_user_text(message)
                if text is None:
                    continue
                origin = ev.get("origin")
                kind = origin.get("kind") if isinstance(origin, dict) else None
                if ev.get("isMeta"):
                    machine[(session, text)] = "isMeta"
                elif kind not in (None, "human"):
                    machine[(session, text)] = f"origin {kind}"

    return result


def prefixes(sessions) -> str:
    unique = list(dict.fromkeys(s[:8] for s in sessions))
    more = f", +{len(unique) - MAX_LISTED} more" if len(unique) > MAX_LISTED else ""
    return ", ".join(unique[:MAX_LISTED]) + more


def run_checks(days: int) -> list[tuple[str, str, str]]:
    """Return (status, check name, detail) rows; status is PASS, FAIL or WARN."""
    since = window_start(days)
    pairs = extract_pairs(since)
    raw = scan(since)
    rows = []

    session_project = {p["session"]: p["project"] for p in pairs}
    checked = [s for s in session_project if s in raw["first_cwd"]]
    mismatched = [s for s in checked if session_project[s] != raw["first_cwd"][s]]
    rows.append(("FAIL" if mismatched else "PASS", "project-paths",
                 f"{len(mismatched)} of {len(checked)} sessions differ from their recorded cwd"
                 + (f" (sessions: {prefixes(mismatched)})" if mismatched else "")))

    prompted: set[str] = set()
    orphans = []
    for p in pairs:
        if p["prompt"] is not None:
            prompted.add(p["session"])
        elif p["session"] in prompted:
            orphans.append(p["session"])
    rows.append(("FAIL" if orphans else "PASS", "orphan-answers",
                 f"{len(orphans)} prompt-less pairs in sessions that already had a prompt"
                 + (f" (sessions: {prefixes(orphans)})" if orphans else "")))

    bad = raw["bad_shapes"]
    rows.append(("FAIL" if bad else "PASS", "content-shapes",
                 f"{len(bad)} user events with unhandled content"
                 + (f" (sessions: {prefixes(bad)})" if bad else "")))

    # Compare the extraction's output with the raw flags rather than
    # re-implementing its skip rules, so a regression shows up here.
    leaked = [(p["session"], raw["machine"][(p["session"], p["prompt"])])
              for p in pairs if (p["session"], p["prompt"]) in raw["machine"]]
    flags = ", ".join(f"{k} {n}" for k, n in Counter(f for _, f in leaked).most_common())
    rows.append(("FAIL" if leaked else "PASS", "machine-prompts",
                 f"{len(leaked)} extracted prompts flagged as not typed by a human"
                 + (f" ({flags}; sessions: {prefixes(s for s, _ in leaked)})" if leaked else "")))

    new = []
    if raw["new_types"]:
        new.append("event types: " + ", ".join(sorted(raw["new_types"])))
    if raw["new_keys"]:
        new.append("user-event keys: " + ", ".join(sorted(raw["new_keys"])))
    rows.append(("WARN" if new else "PASS", "new-fields",
                 "; ".join(new) if new else "no fields outside the baseline"))

    rows.append(("INFO", "window",
                 f"since {since.isoformat()}: {len(pairs)} pairs, {len(session_project)} sessions"))
    return rows


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--days", type=int, default=14,
                    help="Check the last N days, today included (default: 14).")
    args = ap.parse_args(argv)

    rows = run_checks(args.days)
    width = max(len(name) for _, name, _ in rows)
    for status, name, detail in rows:
        print(f"{status:<4}  {name:<{width}}  {detail}")
    return 1 if any(status == "FAIL" for status, _, _ in rows) else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
