#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Show prompt/answer history from Claude Code CLI sessions.

Sessions are read from ~/.claude/projects/<encoded-cwd>/<session-id>.jsonl.
Each line is a JSON event; this script extracts user prompts and assistant
text responses (skipping tool_use, tool_result, and thinking blocks).
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterable, Iterator

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

PROJECTS_DIR = Path.home() / ".claude" / "projects"

NOISE_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"\s*<local-command-caveat>.*?</local-command-caveat>\s*", re.DOTALL),
    re.compile(r"\s*<local-command-stdout>.*?</local-command-stdout>\s*", re.DOTALL),
    re.compile(r"\s*(?:<command-(?:name|message|args)>.*?</command-(?:name|message|args)>\s*)+", re.DOTALL),
    re.compile(r"\s*\[Request interrupted by user.*?\]\s*", re.DOTALL),
    re.compile(r"\s*##\s*Context Usage\b.*", re.DOTALL),
]

HTML_TEMPLATE = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>__TITLE__</title>
<style>
:root {
  color-scheme: light dark;
  --bg: #f6f1e7;
  --fg: #2b2622;
  --muted: #8a7f70;
  --border: #e0d6c4;
  --card: #fffdf8;
  --accent: #b5651d;
  --prompt-bg: #efe7d6;
  --answer-bg: #fbf8f1;
  --kbd-bg: #ece3d2;
}
@media (prefers-color-scheme: dark) {
  :root {
    --bg: #1c1a17;
    --fg: #e8e2d8;
    --muted: #9b9183;
    --border: #34302a;
    --card: #25221d;
    --accent: #d98a4b;
    --prompt-bg: #2c2823;
    --answer-bg: #211e1a;
    --kbd-bg: #332e27;
  }
}
* { box-sizing: border-box; }
body {
  margin: 0;
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
  background: var(--bg);
  color: var(--fg);
  line-height: 1.5;
}
#sidebar {
  position: fixed;
  top: 0;
  left: 0;
  width: 220px;
  height: 100vh;
  overflow-y: auto;
  padding: 16px;
  border-right: 1px solid var(--border);
  background: var(--card);
}
#sidebar h2 {
  font-size: 0.75rem;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  color: var(--muted);
  margin: 20px 0 8px;
}
#sidebar h2:first-child { margin-top: 0; }
#field-toggles label {
  display: block;
  font-size: 0.85rem;
  margin: 4px 0;
  cursor: pointer;
}
#field-toggles input { margin-right: 6px; }
#filter {
  width: 100%;
  padding: 6px 8px;
  font-size: 0.85rem;
  border: 1px solid var(--border);
  border-radius: 6px;
  background: var(--bg);
  color: var(--fg);
}
#actions button {
  display: block;
  width: 100%;
  margin: 6px 0;
  padding: 6px 8px;
  font-size: 0.8rem;
  border: 1px solid var(--border);
  border-radius: 6px;
  background: var(--bg);
  color: var(--fg);
  cursor: pointer;
}
#actions button:hover { border-color: var(--accent); color: var(--accent); }
main {
  margin-left: 270px;
  max-width: 1000px;
  padding: 24px 24px 64px;
}
h1 { font-size: 1.5rem; margin: 0 0 4px; }
#meta { color: var(--muted); font-size: 0.85rem; margin: 0 0 24px; }
.entry {
  background: var(--card);
  border: 1px solid var(--border);
  border-radius: 10px;
  margin: 0 0 14px;
  overflow: hidden;
}
.entry-header {
  display: flex;
  align-items: baseline;
  gap: 10px;
  padding: 12px 16px;
  cursor: pointer;
  user-select: none;
}
.entry-header:hover { background: var(--prompt-bg); }
.chevron {
  display: inline-block;
  transition: transform 0.15s ease;
  color: var(--muted);
  font-size: 0.8rem;
}
.entry.collapsed .chevron { transform: rotate(-90deg); }
.entry-time { color: var(--muted); font-size: 0.8rem; white-space: nowrap; }
.entry-preview {
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 0.9rem;
}
.entry-body { padding: 0 16px 16px; }
.entry.collapsed .entry-body { display: none; }
.field { margin: 12px 0; }
.field-label {
  font-size: 0.72rem;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  color: var(--muted);
  margin-bottom: 4px;
}
.field-prompt .field-value {
  background: var(--prompt-bg);
  padding: 10px 12px;
  border-radius: 8px;
  white-space: pre-wrap;
  word-wrap: break-word;
}
.field-answer .field-value {
  background: var(--answer-bg);
  padding: 10px 12px;
  border-radius: 8px;
  white-space: pre-wrap;
  word-wrap: break-word;
}
.field-meta .field-value {
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  font-size: 0.85rem;
  background: var(--kbd-bg);
  padding: 2px 6px;
  border-radius: 4px;
  display: inline-block;
}
.empty {
  color: var(--muted);
  text-align: center;
  padding: 48px 0;
  font-style: italic;
}
body.hide-timestamp .field-timestamp { display: none; }
body.hide-prompt .field-prompt { display: none; }
body.hide-answer .field-answer { display: none; }
body.hide-model .field-model { display: none; }
body.hide-session .field-session { display: none; }
body.hide-project .field-project { display: none; }
body.hide-answer_timestamp .field-answer_timestamp { display: none; }
</style>
</head>
<body>
<aside id="sidebar">
  <h2>Show fields</h2>
  <div id="field-toggles"></div>
  <h2>Search</h2>
  <input id="filter" type="search" placeholder="Filter entries…" autocomplete="off">
  <h2>Actions</h2>
  <div id="actions">
    <button id="expand-all">Expand all</button>
    <button id="collapse-all">Collapse all</button>
    <button id="reset">Reset to defaults</button>
  </div>
</aside>
<main>
  <h1>__TITLE__</h1>
  <div id="meta"></div>
  <div id="entries"></div>
</main>
<script>
const DATA = __DATA__;
const FIELDS = [
  { key: "timestamp",        label: "Timestamp",        default: true,  kind: "meta" },
  { key: "prompt",           label: "Prompt",           default: true,  kind: "prompt" },
  { key: "answer",           label: "Answer",           default: true,  kind: "answer" },
  { key: "model",            label: "Model",            default: false, kind: "meta" },
  { key: "session",          label: "Session",          default: false, kind: "meta" },
  { key: "project",          label: "Project",          default: false, kind: "meta" },
  { key: "answer_timestamp", label: "Answer timestamp", default: false, kind: "meta" },
];
const STORAGE_KEY = "claude-history-visible-fields";

function escapeHtml(s) {
  if (s === null || s === undefined) return "";
  return String(s)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");
}

function formatTimestamp(iso) {
  if (!iso) return "—";
  const d = new Date(iso);
  if (isNaN(d.getTime())) return iso;
  return d.toLocaleString();
}

function loadVisibility() {
  let stored = {};
  try {
    stored = JSON.parse(localStorage.getItem(STORAGE_KEY)) || {};
  } catch (e) {
    stored = {};
  }
  const v = {};
  FIELDS.forEach(f => {
    v[f.key] = (f.key in stored) ? !!stored[f.key] : f.default;
  });
  return v;
}

function saveVisibility(v) {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(v));
  } catch (e) {}
}

function applyVisibility(v) {
  FIELDS.forEach(f => {
    document.body.classList.toggle("hide-" + f.key, !v[f.key]);
  });
}

function renderToggles(v) {
  const container = document.getElementById("field-toggles");
  container.innerHTML = "";
  FIELDS.forEach(f => {
    const label = document.createElement("label");
    const cb = document.createElement("input");
    cb.type = "checkbox";
    cb.checked = !!v[f.key];
    cb.addEventListener("change", () => {
      v[f.key] = cb.checked;
      saveVisibility(v);
      applyVisibility(v);
    });
    label.appendChild(cb);
    label.appendChild(document.createTextNode(f.label));
    container.appendChild(label);
  });
}

function renderEntry(entry, idx) {
  const preview = String(entry.prompt || entry.answer || "")
    .replace(/\s+/g, " ")
    .trim()
    .slice(0, 200);

  const promptHtml = entry.prompt
    ? escapeHtml(entry.prompt)
    : "<span class=\"muted\">(no prompt — assistant text only)</span>";
  const answerHtml = entry.answer
    ? escapeHtml(entry.answer)
    : "<span class=\"muted\">(empty)</span>";
  const answerLabel = entry.model
    ? "Answer (" + escapeHtml(entry.model) + ")"
    : "Answer";

  return (
    '<article class="entry collapsed" data-idx="' + idx + '">' +
      '<div class="entry-header">' +
        '<span class="chevron">▾</span>' +
        '<span class="entry-time field-timestamp">' + escapeHtml(formatTimestamp(entry.timestamp)) + '</span>' +
        '<span class="entry-preview">' + escapeHtml(preview) + '</span>' +
      '</div>' +
      '<div class="entry-body">' +
        '<div class="field field-timestamp field-meta">' +
          '<div class="field-label">Timestamp</div>' +
          '<div class="field-value">' + escapeHtml(formatTimestamp(entry.timestamp)) + '</div>' +
        '</div>' +
        '<div class="field field-prompt">' +
          '<div class="field-label">Prompt</div>' +
          '<div class="field-value">' + promptHtml + '</div>' +
        '</div>' +
        '<div class="field field-answer">' +
          '<div class="field-label">' + answerLabel + '</div>' +
          '<div class="field-value">' + answerHtml + '</div>' +
        '</div>' +
        '<div class="field field-model field-meta">' +
          '<div class="field-label">Model</div>' +
          '<div class="field-value">' + escapeHtml(entry.model) + '</div>' +
        '</div>' +
        '<div class="field field-session field-meta">' +
          '<div class="field-label">Session</div>' +
          '<div class="field-value">' + escapeHtml(entry.session) + '</div>' +
        '</div>' +
        '<div class="field field-project field-meta">' +
          '<div class="field-label">Project</div>' +
          '<div class="field-value">' + escapeHtml(entry.project) + '</div>' +
        '</div>' +
        '<div class="field field-answer_timestamp field-meta">' +
          '<div class="field-label">Answer timestamp</div>' +
          '<div class="field-value">' + escapeHtml(formatTimestamp(entry.answer_timestamp)) + '</div>' +
        '</div>' +
      '</div>' +
    '</article>'
  );
}

function applyFilter(q) {
  const needle = String(q || "").toLowerCase();
  document.querySelectorAll(".entry").forEach(el => {
    const match = needle === "" || el.textContent.toLowerCase().includes(needle);
    el.style.display = match ? "" : "none";
  });
}

(function init() {
  const v = loadVisibility();
  renderToggles(v);
  applyVisibility(v);

  const entriesEl = document.getElementById("entries");
  if (!DATA.length) {
    entriesEl.innerHTML = '<div class="empty">No entries in this window.</div>';
  } else {
    entriesEl.innerHTML = DATA.map((e, i) => renderEntry(e, i)).join("");
  }

  document.querySelectorAll(".entry-header").forEach(h => {
    h.addEventListener("click", () => {
      h.parentElement.classList.toggle("collapsed");
    });
  });

  const meta = document.getElementById("meta");
  const n = DATA.length;
  meta.textContent = n + (n === 1 ? " entry" : " entries");

  document.getElementById("expand-all").addEventListener("click", () => {
    document.querySelectorAll(".entry").forEach(el => el.classList.remove("collapsed"));
  });
  document.getElementById("collapse-all").addEventListener("click", () => {
    document.querySelectorAll(".entry").forEach(el => el.classList.add("collapsed"));
  });
  document.getElementById("reset").addEventListener("click", () => {
    FIELDS.forEach(f => { v[f.key] = f.default; });
    saveVisibility(v);
    renderToggles(v);
    applyVisibility(v);
  });

  document.getElementById("filter").addEventListener("input", (ev) => {
    applyFilter(ev.target.value);
  });
})();
</script>
</body>
</html>
"""

# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class Entry:
    timestamp: datetime
    role: str            # "user" or "assistant"
    model: str | None    # assistant model name; always None for user entries
    text: str
    session_id: str
    project: str         # decoded project path

# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------

def is_noise(text: str) -> bool:
    return any(p.fullmatch(text) for p in NOISE_PATTERNS)


def decode_project(name: str) -> str:
    return "/" + name.lstrip("-").replace("-", "/")


def parse_ts(s: str) -> datetime | None:
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except Exception:
        return None


def extract_user_text(message: dict) -> str | None:
    content = message.get("content")
    if isinstance(content, str):
        return content.strip() or None
    if isinstance(content, list):
        parts = []
        for block in content:
            if not isinstance(block, dict):
                continue
            if block.get("type") != "text":
                continue
            if not block.get("text"):
                continue
            parts.append(block["text"])
        if parts:
            return "\n".join(parts).strip() or None
    return None


def extract_assistant_text(message: dict) -> str | None:
    content = message.get("content")
    if isinstance(content, str):
        return content.strip() or None
    if isinstance(content, list):
        parts = []
        for block in content:
            if not isinstance(block, dict):
                continue
            if block.get("type") != "text":
                continue
            if not block.get("text"):
                continue
            parts.append(block["text"])
        if parts:
            return "\n".join(parts).strip() or None
    return None

# ---------------------------------------------------------------------------
# Core extraction
# ---------------------------------------------------------------------------

def iter_entries(since, until, project_filter, drop_noise) -> Iterator[Entry]:
    if not PROJECTS_DIR.is_dir():
        return

    for project_dir in sorted(PROJECTS_DIR.iterdir()):
        if not project_dir.is_dir():
            continue
        decoded = decode_project(project_dir.name)
        if project_filter is not None:
            if project_filter not in decoded and project_filter not in project_dir.name:
                continue

        for jsonl in sorted(project_dir.glob("*.jsonl")):
            mtime = datetime.fromtimestamp(jsonl.stat().st_mtime, tz=timezone.utc)
            if mtime < since:
                continue

            try:
                f = open(jsonl, "r", encoding="utf-8", errors="replace")
            except OSError:
                continue

            with f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        ev = json.loads(line)
                    except json.JSONDecodeError:
                        continue

                    etype = ev.get("type")
                    if etype not in ("user", "assistant"):
                        continue

                    ts = parse_ts(ev.get("timestamp", ""))
                    if ts is None:
                        continue
                    if ts < since:
                        continue
                    if until is not None and ts >= until:
                        continue

                    message = ev.get("message") or {}

                    if etype == "user":
                        text = extract_user_text(message)
                        if text is None:
                            continue
                        if drop_noise and is_noise(text):
                            continue
                        yield Entry(ts, "user", None, text, ev.get("sessionId", ""), decoded)
                    else:
                        text = extract_assistant_text(message)
                        if text is None:
                            continue
                        yield Entry(ts, "assistant", message.get("model"), text, ev.get("sessionId", ""), decoded)

# ---------------------------------------------------------------------------
# Date parsing
# ---------------------------------------------------------------------------

def parse_date(s: str):
    dt = parse_ts(s)
    if dt is None:
        dt = datetime.strptime(s, "%Y-%m-%d")
    if dt.tzinfo is None:
        # Naive input (bare date or ISO without offset) means local time on
        # the machine running this — a bare date is local midnight.
        dt = dt.astimezone()
    return dt

# ---------------------------------------------------------------------------
# HTML rendering
# ---------------------------------------------------------------------------

def render_html(pairs, title):
    data_json = json.dumps(pairs, ensure_ascii=False).replace("</", "<\\/")
    return (HTML_TEMPLATE
            .replace("__TITLE__", title.replace("<", "&lt;"))
            .replace("__DATA__", data_json))

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main(argv):
    ap = argparse.ArgumentParser(description=__doc__)

    date_group = ap.add_mutually_exclusive_group()
    date_group.add_argument(
        "--days",
        type=int,
        default=None,
        help="Show entries from the last N days (default: 1 = today).",
    )
    date_group.add_argument(
        "--since",
        type=parse_date,
        default=None,
        help="Show entries on/after this date (YYYY-MM-DD or ISO).",
    )

    ap.add_argument(
        "--until",
        type=parse_date,
        default=None,
        help="Show entries before this date (exclusive).",
    )
    ap.add_argument(
        "--project",
        default=None,
        help="Substring filter on the project path.",
    )
    ap.add_argument(
        "--no-noise",
        action="store_true",
        default=False,
        help="Drop machine-generated prompts (slash-command tags, local-command stdout/caveat, /context dumps, interruption markers).",
    )
    ap.add_argument(
        "--max-chars",
        type=int,
        default=2000,
        help="Truncate each message to this many characters (0 = no limit).",
    )
    ap.add_argument(
        "--format",
        choices=["text", "md", "jsonl", "json", "html"],
        default="text",
        help="Output format.",
    )
    ap.add_argument(
        "--json",
        action="store_true",
        default=False,
        help="Shortcut for --format json (emit a single JSON array).",
    )
    ap.add_argument(
        "--html",
        action="store_true",
        default=False,
        help="Shortcut for --format html (self-contained interactive page).",
    )

    args = ap.parse_args(argv)

    if args.json:
        args.format = "json"
    if args.html:
        args.format = "html"

    # Compute time window
    now = datetime.now().astimezone()
    if args.since:
        since = args.since
    else:
        days = args.days if args.days is not None else 1
        midnight = now.replace(hour=0, minute=0, second=0, microsecond=0)
        since = midnight - timedelta(days=max(days - 1, 0))
    until = args.until

    # Collect and sort entries
    entries = list(iter_entries(
        since.astimezone(timezone.utc),
        until.astimezone(timezone.utc) if until else None,
        args.project,
        drop_noise=args.no_noise,
    ))
    entries.sort(key=lambda e: e.timestamp)

    # Truncation helper
    def trunc(s: str) -> str:
        if args.max_chars and len(s) > args.max_chars:
            return s[:args.max_chars].rstrip() + f"\n… [truncated, {len(s)} chars total]"
        return s

    # Serializer for jsonl/json
    def to_obj(e: Entry) -> dict:
        return {
            "timestamp": e.timestamp.astimezone().isoformat(),
            "role": e.role,
            "model": e.model,
            "session": e.session_id,
            "project": e.project,
            "text": trunc(e.text),
        }

    # Pair builder for json/html
    def build_pairs() -> list[dict]:
        pairs = []
        current = None
        for e in entries:
            if e.role == "user":
                if current is not None:
                    pairs.append(current)
                current = {
                    "timestamp": e.timestamp.astimezone().isoformat(),
                    "session": e.session_id,
                    "project": e.project,
                    "model": None,
                    "prompt": trunc(e.text),
                    "answer": "",
                    "answer_timestamp": None,
                }
            else:  # assistant
                if current is None or current["session"] != e.session_id:
                    # assistant with no preceding user, or a session change
                    if current is not None:
                        pairs.append(current)
                    current = {
                        "timestamp": None,
                        "session": e.session_id,
                        "project": e.project,
                        "model": e.model,
                        "prompt": None,
                        "answer": trunc(e.text),
                        "answer_timestamp": e.timestamp.astimezone().isoformat(),
                    }
                else:
                    # append to the current pair's answer
                    sep = "\n\n" if current["answer"] else ""
                    current["answer"] = trunc(
                        current["answer"] + sep + e.text if current["answer"] else e.text
                    )
                    if current["answer_timestamp"] is None:
                        current["answer_timestamp"] = e.timestamp.astimezone().isoformat()
                    if current["model"] is None:
                        current["model"] = e.model
        if current is not None:
            pairs.append(current)
        return pairs

    # Output
    if args.format == "jsonl":
        for e in entries:
            json.dump(to_obj(e), sys.stdout, ensure_ascii=False)
            sys.stdout.write("\n")
        return 0

    if args.format == "json":
        json.dump(build_pairs(), sys.stdout, ensure_ascii=False, indent=2)
        sys.stdout.write("\n")
        return 0

    if args.format == "html":
        title = "Claude Code history — since " + since.astimezone().date().isoformat()
        sys.stdout.write(render_html(build_pairs(), title))
        return 0

    # text and md formats
    last_session = None
    for e in entries:
        local = e.timestamp.astimezone().strftime("%Y-%m-%d %H:%M:%S")
        if e.session_id != last_session:
            if args.format == "md":
                print(f"\n## Session `{e.session_id[:8]}` — {e.project}\n")
            else:
                print(f"\n=== Session {e.session_id[:8]} — {e.project} ===")
            last_session = e.session_id
        header_role = "USER" if e.role == "user" else f"ASSISTANT ({e.model or '?'})"
        if args.format == "md":
            print(f"### [{local}] {header_role}\n")
            print(trunc(e.text))
            print()
        else:
            print(f"\n[{local}] {header_role}")
            print(trunc(e.text))

    if not entries:
        print(f"No entries found since {since.isoformat()}.", file=sys.stderr)

    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
