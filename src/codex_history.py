#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Show prompt/answer history from local Codex sessions.

Reads rollout JSONL transcripts in $CODEX_HOME/sessions and archived_sessions
(default: ~/.codex). Tools, reasoning, and injected context are skipped.
"""

from __future__ import annotations

import json
import os
import re
import sys
from datetime import timezone
from pathlib import Path

import claude_history as ch


# These are injected user-role context blocks, rather than human prompts.
CONTEXT_BLOCK = re.compile(
    r"\s*<(environment_context|permissions instructions|external_codex_apps_open_page|"
    r"turn_aborted|subagent_notification)>.*?</\1>\s*", re.DOTALL
)


def read_events(path):
    """Ignore incomplete lines (including a running session's final line)."""
    try:
        with path.open(encoding="utf-8", errors="replace") as stream:
            for line in stream:
                try:
                    event = json.loads(line)
                except ValueError:
                    continue
                if isinstance(event, dict) and isinstance(event.get("payload"), dict):
                    yield event
    except OSError:
        return


def message_text(payload):
    content = payload.get("content")
    if not isinstance(content, list):
        return None
    parts = []
    for block in content:
        if not isinstance(block, dict) or block.get("type") not in ("input_text", "output_text", "text"):
            continue
        text = block.get("text")
        if not isinstance(text, str) or not text.strip():
            continue
        if payload.get("role") == "user" and (
            CONTEXT_BLOCK.fullmatch(text) or text.lstrip().startswith("# AGENTS.md instructions for ")
        ):
            continue
        parts.append(text)
    return "\n".join(parts).strip() or None


def iter_entries(since, until, project_filter, drop_noise):
    home = Path(os.environ.get("CODEX_HOME", "~/.codex")).expanduser()
    seen_sessions = set()
    for root in (home / "sessions", home / "archived_sessions"):
        for path in sorted(root.rglob("*.jsonl")):
            # First pass gets identity and detects mirrored event_msg records.
            meta = {}
            response_roles = set()
            for event in read_events(path):
                payload = event["payload"]
                if event.get("type") == "session_meta":
                    meta = payload
                if event.get("type") == "response_item" and payload.get("type") == "message":
                    response_roles.add(payload.get("role"))
            session = meta.get("id") or meta.get("session_id") or path.stem
            if session in seen_sessions:
                continue
            seen_sessions.add(session)
            project = meta.get("cwd") or ""
            model = None
            for event in read_events(path):
                payload = event["payload"]
                kind = event.get("type")
                if kind == "turn_context":
                    model = payload.get("model", model)
                    project = payload.get("cwd") or project
                    continue
                role = None
                text = None
                if kind == "response_item" and payload.get("type") == "message":
                    role = payload.get("role")
                    if role not in ("user", "assistant") or payload.get("channel") in ("analysis", "summary"):
                        continue
                    text = message_text(payload)
                elif kind == "event_msg":
                    role = {"user_message": "user", "agent_message": "assistant"}.get(payload.get("type"))
                    if role is None or role in response_roles:
                        continue
                    text = payload.get("message")
                if role not in ("user", "assistant") or not isinstance(text, str) or not text.strip():
                    continue
                ts = ch.parse_ts(event.get("timestamp", ""))
                if ts is None:
                    continue
                if ts.tzinfo is None:
                    ts = ts.replace(tzinfo=timezone.utc)
                if ts < since or (until is not None and ts >= until):
                    continue
                if project_filter is not None and project_filter not in project:
                    continue
                if role == "user" and drop_noise and ch.is_noise(text):
                    continue
                yield ch.Entry(ts, role, model if role == "assistant" else None,
                               text.strip(), session, project)


def main(argv=None):
    return ch.main(argv, entry_reader=iter_entries, description=__doc__,
                   title_prefix="Codex history")


if __name__ == "__main__":
    sys.exit(main())
