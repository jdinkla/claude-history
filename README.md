# `claude-history` — Extract and display Claude Code CLI session history

A command-line tool that extracts and displays the prompt/answer history of **Claude Code CLI** sessions. It reads the local session transcript files that Claude Code writes under `~/.claude/projects/`, filters them by date and project, and renders them as plain text, Markdown, JSON, JSON Lines, or a self-contained interactive HTML page.

## Requirements

- **Python** 3.11 or later
- **uv** (for script execution) — or run directly with `python3` on a 3.11+ interpreter
- **Optional:** `just` (for task shortcuts in the `justfile`)

## Installation & Usage

The main script is `src/claude_history.py`, which self-bootstraps via `uv`:

```bash
# Run directly (uv handles Python provisioning)
./src/claude_history.py [options]

# Or with uv explicitly
uv run src/claude_history.py [options]

# Or with Python 3.11+
python3 src/claude_history.py [options]
```

### CLI Flags

Run `./src/claude_history.py --help` for the full flag reference; the authoritative
description of every flag and its exact behavior is
[`specs/SPECIFICATION.md`](specs/SPECIFICATION.md). One semantic worth knowing
up front: bare `--since`/`--until` dates mean **local midnight** on the
executing machine.

### Worked Examples

```bash
# Today's history as plain text (default)
./src/claude_history.py

# Last 8 days, only the "backend" project, drop machine prompts, as paired JSON
./src/claude_history.py --days 8 --project backend --no-noise --json

# A date range as Markdown, untruncated
./src/claude_history.py --since 2026-05-01 --until 2026-05-08 --max-chars 0 --format md

# Self-contained interactive HTML page
./src/claude_history.py --days 30 --html > history.html
```

## Reflection workflow (`/reflect`)

The repo doubles as a **reflection tool** in the spirit of Donald Schön's
*The Reflective Practitioner*: your Claude Code transcripts are a complete
protocol of your collaboration moves — prompt framings, the situation's
back-talk, your corrections. The reflection workflow analyzes them to improve
how you work with Claude.

Methodological ground rules:

1. **The critic is never the generator.** Analysis runs in a fresh subagent,
   using a different model than the one that produced the majority of the
   analyzed sessions. The orchestrating instance only prepares evidence and
   relays the critique.
2. **Evidence before opinion.** A deterministic metrics layer
   (`reflect_metrics.py`) counts observable events — corrections,
   interruptions, short steering follow-ups, sessions where Claude had to ask
   back — and every claim in the critique must cite session + timestamp.
3. **The window excludes today**, so a running session never judges its own
   transcript.

### Components

- **`reflect_metrics.py`** — computes observable-event metrics from a pairs
  JSON file (`claude_history.py --format json`, noise included):

  ```bash
  ./src/claude_history.py --days 8 --max-chars 0 --format json | ./src/reflect_metrics.py
  ```

- **`skills/reflect/`** — the `/reflect` Claude Code skill that orchestrates
  extraction, metrics, and the independent critic, and saves a dated report
  under `reflections/` (gitignored — reports quote private prompts verbatim).
  Install once with `just install-skill`, then use `/reflect 7` or
  `/reflect 14 myproject` in any Claude Code session.

The full orchestration procedure (including the critic's methodology prompt)
lives in [`skills/reflect/SKILL.md`](skills/reflect/SKILL.md).

## Companion Tools

### `build_table.py`

A utility to render a previously saved `--format json` pairs file as a flat interactive HTML table. Usage:

```bash
./src/build_table.py [SRC.json] [DST.html]
```

Defaults to `last_8_days_backend_no_noise.json` as source and `.html` suffix for destination.

### `justfile`

All workflow shortcuts (history dumps, tests, reflection data, skill install)
are `just` recipes — discover them with:

```bash
just --list
```

## Documentation map

To keep things DRY, each document owns one concern — look things up at the
source rather than in copies:

- **[`README.md`](README.md)** (this file) — what the tools are and how to use them.
- **[`CLAUDE.md`](CLAUDE.md)** — working conventions for Claude Code in this
  repo: commands, hard constraints (stdlib-only, spec sync, `reflections/`
  privacy), and the cross-file architecture notes.
- **[`specs/SPECIFICATION.md`](specs/SPECIFICATION.md)** — the complete
  behavioral specification of `claude_history.py`; the authority on flags,
  formats, and semantics.
- **[`skills/reflect/SKILL.md`](skills/reflect/SKILL.md)** — the `/reflect`
  orchestration procedure and critic methodology.
- **`backlog/`** — task history and open work (Backlog.md).

## License

See `LICENSE`.
