# `claude-history` — Extract and display Claude Code CLI session history

A command-line tool that extracts and displays the prompt/answer history of **Claude Code CLI** sessions. It reads the local session transcript files that Claude Code writes under `~/.claude/projects/`, filters them by date and project, and renders them as plain text, Markdown, JSON, JSON Lines, or a self-contained interactive HTML page.

## Requirements

- **Python** 3.11 or later
- **uv** (for script execution) — or run directly with `python3` on a 3.11+ interpreter
- **Optional:** `just` (for task shortcuts in the `justfile`)

## Installation & Usage

The main script is `claude_history.py`, which self-bootstraps via `uv`:

```bash
# Run directly (uv handles Python provisioning)
./claude_history.py [options]

# Or with uv explicitly
uv run claude_history.py [options]

# Or with Python 3.11+
python3 claude_history.py [options]
```

### CLI Flags

| Flag           | Type    | Default | Description |
|---|---|---|---|
| `--days`       | int     | `None`  | Show entries from the last N days (default: 1 = today). |
| `--since`      | date    | —       | Show entries on/after this date (YYYY-MM-DD or ISO-8601). |
| `--until`      | date    | `None`  | Show entries before this date (exclusive). |
| `--project`    | string  | `None`  | Substring filter on the project path. |
| `--no-noise`   | flag    | `False` | Drop machine-generated prompts (slash-command tags, local-command stdout/caveat, /context dumps, interruption markers). |
| `--max-chars`  | int     | `2000`  | Truncate each message to this many characters (0 = no limit). |
| `--format`     | choice  | `text`  | Output format: one of `text`, `md`, `jsonl`, `json`, `html`. |
| `--json`       | flag    | `False` | Shortcut for `--format json` (emit a single JSON array). |
| `--html`       | flag    | `False` | Shortcut for `--format html` (self-contained interactive page). |

### Worked Examples

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

## Companion Tools

### `build_table.py`

A utility to render a previously saved `--format json` pairs file as a flat interactive HTML table. Usage:

```bash
./build_table.py [SRC.json] [DST.html]
```

Defaults to `last_8_days_backend_no_noise.json` as source and `.html` suffix for destination.

### `justfile`

A `just` task runner for convenience shortcuts. Example:

```bash
just prompts 8 backend
```

This runs:
```bash
./claude_history.py --days 8 --project backend --no-noise --format json
```

## License

See `LICENSE`.
