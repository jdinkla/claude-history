# `claude-history` — Service Specification

A command-line tool that extracts and displays the prompt/answer history of
**Claude Code CLI** sessions. It reads the local session transcript files that
Claude Code writes under `~/.claude/projects/`, filters them by date and
project, and renders them as plain text, Markdown, JSON, JSON Lines, or a
self-contained interactive HTML page.

This document is a complete behavioral specification. An agent should be able to
re-implement the tool from this alone, producing byte-compatible output for the
JSON/JSONL/HTML formats and equivalent output for the text/Markdown formats.

---

## 1. Overview

- **Language / runtime:** Python 3 (standard library only — no third-party
  dependencies). The script declares `requires-python = ">=3.11"` (see the
  PEP 723 block below); 3.11 is the effective floor because `parse_ts` relies on
  `datetime.fromisoformat` accepting a `+00:00` offset, and the `str | None`
  annotation syntax needs 3.10+ (though `from __future__ import annotations`,
  which the script uses, would otherwise relax that).
- **Entry point:** an executable script `claude_history.py` that
  self-bootstraps via [`uv`](https://docs.astral.sh/uv/). It begins with a
  `uv run --script` shebang followed by a [PEP 723](https://peps.python.org/pep-0723/)
  inline-metadata block declaring the Python version and an empty dependency
  set, and ends with `if __name__ == "__main__": sys.exit(main(sys.argv[1:]))`:

  ```python
  #!/usr/bin/env -S uv run --script
  # /// script
  # requires-python = ">=3.11"
  # dependencies = []
  # ///
  ```

  Running `./claude_history.py …` directly lets `uv` provision the interpreter;
  `uv run claude_history.py …` and `python3 claude_history.py …` (on a 3.11+
  interpreter) are equivalent.
- **Imports used:** `argparse`, `json`, `os`, `re`, `sys`, `dataclasses.dataclass`,
  `datetime` (`datetime`, `timedelta`, `timezone`), `pathlib.Path`,
  `typing` (`Iterable`, `Iterator`), and `from __future__ import annotations`.
- **Side effects:** reads files under `~/.claude/projects/`; writes only to
  `stdout` (and one diagnostic line to `stderr`). It never modifies the
  transcript files.

The module docstring (also used as the `--help` description) is:

```
Show prompt/answer history from Claude Code CLI sessions.

Sessions are read from ~/.claude/projects/<encoded-cwd>/<session-id>.jsonl.
Each line is a JSON event; this script extracts user prompts and assistant
text responses (skipping tool_use, tool_result, and thinking blocks).
```

---

## 2. Input data model

### 2.1 On-disk layout

Claude Code stores one directory per project (working directory) under:

```
~/.claude/projects/<encoded-cwd>/<session-id>.jsonl
```

- `<encoded-cwd>` is the project's absolute path with every `/` replaced by `-`
  and a leading `-` (because the path starts with `/`). Example:
  `/Users/jane/code/app` → `-Users-jane-code-app`.
- Each `<session-id>.jsonl` file is a **JSON Lines** transcript: one JSON object
  ("event") per line.

### 2.2 Relevant event shape

Each line is parsed as a JSON object. The tool only cares about these fields:

| Field        | Meaning                                                              |
|--------------|----------------------------------------------------------------------|
| `type`       | Event type. Only `"user"` and `"assistant"` are processed.           |
| `timestamp`  | ISO-8601 timestamp string (may end in `Z`).                          |
| `sessionId`  | Session identifier (string). Missing → `""`.                         |
| `message`    | The message object. Missing/falsy → treated as `{}`.                 |

The `message` object contains:

| Field      | Meaning                                                                |
|------------|------------------------------------------------------------------------|
| `content`  | Either a plain string, or a list of content blocks (each a dict).      |
| `model`    | Model name (assistant events only). May be absent → `None`.            |

A content block in the list form has a `type` (e.g. `"text"`, `"thinking"`,
`"tool_use"`, `"tool_result"`) and, for text blocks, a `"text"` string. Only
`"text"` blocks are extracted; all others (thinking, tool_use, tool_result) are
ignored.

---

## 3. Constants

```python
PROJECTS_DIR = Path.home() / ".claude" / "projects"
```

### 3.1 Noise patterns

A list of regular expressions, each compiled with `re.DOTALL`. They identify
machine-generated user prompts that should be dropped when `--no-noise` is set.
Matching uses **`fullmatch`** (the entire prompt text must match the pattern).

```python
NOISE_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"\s*<local-command-caveat>.*?</local-command-caveat>\s*", re.DOTALL),
    re.compile(r"\s*<local-command-stdout>.*?</local-command-stdout>\s*", re.DOTALL),
    re.compile(r"\s*(?:<command-(?:name|message|args)>.*?</command-(?:name|message|args)>\s*)+", re.DOTALL),
    re.compile(r"\s*\[Request interrupted by user.*?\]\s*", re.DOTALL),
    re.compile(r"\s*##\s*Context Usage\b.*", re.DOTALL),
]
```

These correspond to: local slash-command caveat blocks, local-command stdout
dumps, slash-command tag wrappers (`<command-name>` / `<command-message>` /
`<command-args>`), user-interruption markers, and `/context`-style "Context
Usage" dumps.

---

## 4. Data structures

### 4.1 `Entry` (dataclass)

Represents a single extracted message (one user prompt **or** one assistant
text response).

```python
@dataclass
class Entry:
    timestamp: datetime
    role: str            # "user" or "assistant"
    model: str | None    # assistant model name; always None for user entries
    text: str
    session_id: str
    project: str         # decoded project path
```

Field order matters for positional construction in `iter_entries`.

---

## 5. Helper functions

### 5.1 `is_noise(text: str) -> bool`

```python
def is_noise(text):
    return any(p.fullmatch(text) for p in NOISE_PATTERNS)
```

### 5.2 `decode_project(name: str) -> str`

Reverses the `<encoded-cwd>` encoding back into an absolute path.

```python
def decode_project(name):
    return "/" + name.lstrip("-").replace("-", "/")
```

(Strip leading dashes, replace remaining `-` with `/`, prepend `/`.)

### 5.3 `parse_ts(s: str) -> datetime | None`

Parses an ISO-8601 timestamp; tolerant of a trailing `Z`. Returns `None` on any
failure.

```python
def parse_ts(s):
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except Exception:
        return None
```

### 5.4 `extract_user_text(message: dict) -> str | None`

Returns the user's prompt text, or `None` if there is no usable text (e.g. the
event is a tool_result or meta event).

```python
def extract_user_text(message):
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
```

### 5.5 `extract_assistant_text(message: dict) -> str | None`

Identical logic to `extract_user_text` but applied to assistant messages.
Collects only `"text"` blocks (skipping `thinking`, `tool_use`, `tool_result`),
joins them with `"\n"`, strips, and returns `None` if empty.

---

## 6. Core extraction — `iter_entries`

```python
def iter_entries(since, until, project_filter, drop_noise) -> Iterator[Entry]:
```

A generator yielding `Entry` objects. Parameters:

- `since: datetime` — inclusive lower bound (timezone-aware, UTC).
- `until: datetime | None` — exclusive upper bound (UTC), or `None` for no upper
  bound.
- `project_filter: str | None` — substring filter.
- `drop_noise: bool` — whether to apply `is_noise` filtering to user prompts.

Algorithm:

1. If `PROJECTS_DIR` is not a directory, return immediately (yield nothing).
2. For each `project_dir` in `sorted(PROJECTS_DIR.iterdir())`:
   1. Skip if not a directory.
   2. `decoded = decode_project(project_dir.name)`.
   3. If `project_filter` is set **and** it is not a substring of `decoded`
      **and** it is not a substring of `project_dir.name`, skip this project.
      (The filter matches against either the decoded path or the raw encoded
      directory name.)
   4. For each `jsonl` in `sorted(project_dir.glob("*.jsonl"))`:
      1. `mtime = datetime.fromtimestamp(jsonl.stat().st_mtime, tz=timezone.utc)`.
      2. If `mtime < since`, skip the file entirely (a fast pre-filter — a file
         last modified before the window cannot contain in-window events).
      3. Open the file with `open(jsonl, "r", encoding="utf-8", errors="replace")`,
         wrapped so that an `OSError` skips the file. For each `line`:
         1. `line = line.strip()`; if empty, skip.
         2. Parse `ev = json.loads(line)`; on `json.JSONDecodeError`, skip the
            line.
         3. `etype = ev.get("type")`; if not in `("user", "assistant")`, skip.
         4. `ts = parse_ts(ev.get("timestamp", ""))`; if `None`, skip.
         5. If `ts < since`, skip.
         6. If `until is not None and ts >= until`, skip.
         7. `message = ev.get("message") or {}`.
         8. If `etype == "user"`:
            - `text = extract_user_text(message)`; if `None`, skip.
            - If `drop_noise and is_noise(text)`, skip.
            - `yield Entry(ts, "user", None, text, ev.get("sessionId", ""), decoded)`.
         9. Else (assistant):
            - `text = extract_assistant_text(message)`; if `None`, skip.
            - `yield Entry(ts, "assistant", message.get("model"), text, ev.get("sessionId", ""), decoded)`.

---

## 7. Date parsing — `parse_date`

Used as the `type=` for `--since` / `--until`.

```python
def parse_date(s):
    dt = parse_ts(s)
    if dt is None:
        dt = datetime.strptime(s, "%Y-%m-%d")
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc).astimezone()
    return dt
```

Accepts a full ISO-8601 timestamp or a bare `YYYY-MM-DD` date. Naive results are
interpreted as UTC and then converted to the local timezone.

---

## 8. CLI — `main(argv)`

Built with `argparse.ArgumentParser(description=__doc__)`.

### 8.1 Arguments

| Flag           | Type / action | Default | Help text |
|----------------|---------------|---------|-----------|
| `--days`       | `int`         | `None`  | `Show entries from the last N days (default: 1 = today).` |
| `--since`      | `parse_date`  | —       | `Show entries on/after this date (YYYY-MM-DD or ISO).` |
| `--until`      | `parse_date`  | `None`  | `Show entries before this date (exclusive).` |
| `--project`    | string        | `None`  | `Substring filter on the project path.` |
| `--no-noise`   | `store_true`  | `False` | `Drop machine-generated prompts (slash-command tags, local-command stdout/caveat, /context dumps, interruption markers).` |
| `--max-chars`  | `int`         | `2000`  | `Truncate each message to this many characters (0 = no limit).` |
| `--format`     | choice        | `text`  | one of `text`, `md`, `jsonl`, `json`, `html` |
| `--json`       | `store_true`  | `False` | `Shortcut for --format json (emit a single JSON array).` |
| `--html`       | `store_true`  | `False` | `Shortcut for --format html (self-contained interactive page).` |

- `--days` and `--since` are **mutually exclusive** (added via
  `ap.add_mutually_exclusive_group()`).
- `--json` and `--html` are convenience overrides applied after parsing:
  if `args.json:` set `args.format = "json"`; if `args.html:` set
  `args.format = "html"`.

### 8.2 Computing the time window

```python
now = datetime.now().astimezone()
if args.since:
    since = args.since
else:
    days = args.days if args.days is not None else 1
    midnight = now.replace(hour=0, minute=0, second=0, microsecond=0)
    since = midnight - timedelta(days=max(days - 1, 0))
until = args.until
```

So `--days 1` (the default) means "since local midnight today"; `--days N`
means "since local midnight `N-1` days ago" (i.e. today plus the previous `N-1`
days). `days <= 1` is clamped via `max(days - 1, 0)`.

### 8.3 Collecting and sorting

```python
entries = list(iter_entries(
    since.astimezone(timezone.utc),
    until.astimezone(timezone.utc) if until else None,
    args.project,
    drop_noise=args.no_noise,
))
entries.sort(key=lambda e: e.timestamp)
```

### 8.4 Truncation helper

Defined inside `main` as a closure over `args`:

```python
def trunc(s: str) -> str:
    if args.max_chars and len(s) > args.max_chars:
        return s[:args.max_chars].rstrip() + f"\n… [truncated, {len(s)} chars total]"
    return s
```

`--max-chars 0` disables truncation.

---

## 9. Output formats

### 9.1 `jsonl` — one JSON object per entry (un-paired)

Uses a per-entry serializer:

```python
def to_obj(e: Entry) -> dict:
    return {
        "timestamp": e.timestamp.astimezone().isoformat(),
        "role": e.role,
        "model": e.model,
        "session": e.session_id,
        "project": e.project,
        "text": trunc(e.text),
    }
```

For each entry: `json.dump(to_obj(e), sys.stdout, ensure_ascii=False)` followed
by `sys.stdout.write("\n")`. Returns `0`.

### 9.2 Pairing — `build_pairs()`

`json` and `html` formats group consecutive entries into **prompt/answer
pairs**. Each pair is a dict with this schema:

```json
{
  "timestamp": "<prompt time, ISO local>" | null,
  "session": "<session id>",
  "project": "<decoded project path>",
  "model": "<assistant model>" | null,
  "prompt": "<user text>" | null,
  "answer": "<assistant text>",
  "answer_timestamp": "<first assistant time, ISO local>" | null
}
```

Algorithm:

```python
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
```

Notes:
- A new user entry always starts a new pair (flushing any current one).
- An assistant entry starts a new (prompt-less) pair if there is no current
  pair, or if the session id differs from the current pair.
- Otherwise the assistant text is appended to the current pair's answer,
  separated by a blank line (`"\n\n"`) when an answer already exists. The whole
  concatenation is re-run through `trunc`. The first assistant timestamp and
  first non-null model win.

### 9.3 `json` — single pretty-printed array

```python
json.dump(build_pairs(), sys.stdout, ensure_ascii=False, indent=2)
sys.stdout.write("\n")
return 0
```

### 9.4 `html` — self-contained interactive page

```python
title = "Claude Code history — since " + since.astimezone().date().isoformat()
sys.stdout.write(render_html(build_pairs(), title))
return 0
```

`render_html` injects the pairs as JSON and the title into a static HTML
template (see §10):

```python
def render_html(pairs, title):
    data_json = json.dumps(pairs, ensure_ascii=False).replace("</", "<\\/")
    return (HTML_TEMPLATE
            .replace("__TITLE__", title.replace("<", "&lt;"))
            .replace("__DATA__", data_json))
```

The `.replace("</", "<\\/")` guards against a `</script>` sequence inside the
embedded JSON breaking out of the `<script>` block.

### 9.5 `text` (default) and `md`

Both iterate over the sorted `entries` (not pairs), printing a session header
whenever the session id changes, then one block per entry. `last_session`
starts as `None`.

For each entry `e`:
- `local = e.timestamp.astimezone().strftime("%Y-%m-%d %H:%M:%S")`
- If `e.session_id != last_session`:
  - `md`: `print(f"\n## Session \`{e.session_id[:8]}\` — {e.project}\n")`
  - `text`: `print(f"\n=== Session {e.session_id[:8]} — {e.project} ===")`
  - set `last_session = e.session_id`
- `header_role = "USER" if e.role == "user" else f"ASSISTANT ({e.model or '?'})"`
- `md`:
  - `print(f"### [{local}] {header_role}\n")`
  - `print(trunc(e.text))`
  - `print()`  (trailing blank line)
- `text`:
  - `print(f"\n[{local}] {header_role}")`
  - `print(trunc(e.text))`

After the loop, if `entries` is empty:
`print(f"No entries found since {since.isoformat()}.", file=sys.stderr)`.

`main` returns `0` in all formats.

---

## 10. HTML template (`HTML_TEMPLATE`)

A single string constant containing a complete static HTML document with two
placeholders, `__TITLE__` (appears in both `<title>` and the `<h1>`) and
`__DATA__` (the embedded JSON array). It requires no network access and no build
step. Behavior:

### 10.1 Structure & styling

- Responsive, "warm paper" light theme with a dark-mode variant via
  `@media (prefers-color-scheme: dark)` and `color-scheme: light dark`. Colors
  are CSS custom properties (`--bg`, `--fg`, `--muted`, `--border`, `--card`,
  `--accent`, `--prompt-bg`, `--answer-bg`, `--kbd-bg`).
- A fixed left **sidebar** (`#sidebar`, 220px) with: a "Show fields" section of
  checkboxes (`#field-toggles`), a search input (`#filter`, `type=search`), and
  an actions block with three buttons: **Expand all** (`#expand-all`),
  **Collapse all** (`#collapse-all`), **Reset to defaults** (`#reset`).
- A `<main>` (left margin 270px, max-width 1000px) containing a page header
  (`<h1>` = title, plus a `#meta` line) and an `#entries` container.
- Each entry is an `<article class="entry">` with a clickable `.entry-header`
  (chevron + timestamp + one-line preview) that toggles a `collapsed` class to
  show/hide the `.entry-body`.

### 10.2 Embedded data and field config

```js
const DATA = __DATA__;  // the array of pair objects from build_pairs()
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
```

### 10.3 Client behavior (vanilla JS, no libraries)

- **Field visibility** is persisted in `localStorage` under `STORAGE_KEY`.
  `loadVisibility()` reads it (falling back to each field's `default`).
  `applyVisibility(v)` toggles a `hide-<key>` class on `<body>`; CSS rules
  `body.hide-<key> .field-<key> { display: none; }` hide the corresponding
  fields. `renderToggles(v)` builds the checkboxes; changing one updates the
  object, saves, and re-applies.
- **Each entry** renders via `renderEntry(entry, idx)`: a header (chevron,
  `formatTimestamp(entry.timestamp)`, and a `preview` = first 200 chars of
  `entry.prompt || entry.answer` with whitespace collapsed), and a body with all
  seven fields. The Prompt field shows `(no prompt — assistant text only)` when
  empty; the Answer field shows `(empty)` when empty and appends the model name
  in parentheses to its label when present. Clicking the header toggles
  `collapsed`.
- **`escapeHtml(s)`** escapes `&`, `<`, `>` (returns `""` for null/undefined).
  **`formatTimestamp(iso)`** returns `"—"` for falsy input, the result of
  `new Date(iso).toLocaleString()` for a valid date, or the raw string if
  `Date` parsing yields `NaN`.
- **Filter:** `applyFilter(q)` lowercases the query and shows only entries whose
  `el.textContent` contains it (empty query shows all). Wired to the `input`
  event of `#filter`.
- **Init** (`(function init(){…})()`): load/render toggles, apply visibility,
  render all entries (or a `<div class="empty">No entries in this window.</div>`
  if `DATA` is empty), set `#meta` to `"<n> entr(y|ies)"`, and wire the
  Expand-all / Collapse-all / Reset buttons. Expand/Collapse add or remove
  `collapsed` on every `.entry`. Reset restores defaults, saves, and
  re-renders toggles + visibility.

---

## 11. Companion script — `build_table.py`

A small, **independent** utility (not imported by `claude_history.py`) that
renders a flat HTML table from a previously saved `--format json` pairs file. It
is convenience tooling; re-implementing it is optional.

- **Usage:** `build_table.py [SRC.json] [DST.html]`. `SRC` defaults to
  `last_8_days_backend_no_noise.json`; `DST` defaults to `SRC` with an `.html`
  suffix.
- Reads the JSON array, maps each record to `{model, prompt, answer}` (missing
  values → `""`), and embeds it as JSON (`.replace("</", "<\\/")`) into a static
  HTML template.
- The page is a three-column sticky-header table (`model`, `prompt`, `answer`)
  with light/dark support. Answers longer than 80 chars are truncated with a
  **reveal/hide** toggle button (per-row, toggles an `expanded` class). Prints
  `wrote <DST> (<n> rows, <bytes> bytes)`.

---

## 12. Companion runner — `justfile`

A [`just`](https://github.com/casey/just) task file:

```just
default:
    @just --list

# Dump prompts for PROJECT over the last DAYS days (machine-generated prompts filtered).
prompts DAYS PROJECT:
    ./claude_history.py --days {{DAYS}} --project {{PROJECT}} --no-noise --format json
```

---

## 13. Worked examples

```bash
# Today's history as plain text (default)
./claude_history.py

# Last 8 days, only the "backend" project, drop machine prompts, as paired JSON
./claude_history.py --days 8 --project backend --no-noise --json

# A date range as Markdown, untruncated
./claude_history.py --since 2026-05-01 --until 2026-05-08 --max-chars 0 --format md

# Self-contained interactive HTML page
./claude_history.py --days 30 --html > history.html
```

---

## 14. Edge cases & invariants

- **No projects dir:** `iter_entries` yields nothing; text/md print the
  "No entries found since …" line to stderr; json/jsonl emit empty array / no
  lines; html renders the empty-state message.
- **Unparseable lines / timestamps:** silently skipped (per-line `try/except`
  on `JSONDecodeError`; `parse_ts` returns `None` → skipped).
- **Unreadable files:** an `OSError` opening a transcript skips that file.
- **Encoding:** files are read as UTF-8 with `errors="replace"`.
- **Ordering:** projects and files are processed in sorted order; the final
  `entries` list is sorted by timestamp before output, so global chronological
  order holds even across projects/files.
- **Timezones:** the window is computed in local time, converted to UTC for
  comparison against event timestamps; output timestamps are rendered in local
  time via `.astimezone().isoformat()`.
- **`ensure_ascii=False`** everywhere, so non-ASCII text is emitted verbatim.
