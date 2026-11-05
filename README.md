# `claude-history` and `codex-history` — Local AI session history

Two command-line tools that extract and display prompt/answer history from **Claude Code** and **Codex** sessions. They read local transcripts, filter by date and project, and render plain text, Markdown, JSON, JSON Lines, or a self-contained interactive HTML page.

## Requirements

- **Python** 3.11 or later
- **uv** (recommended for installation and script execution) — or use `pip` for installation / `python3` to run scripts
- **Optional:** `just` (for task shortcuts in the `justfile`)

## Installation & Usage

Install both commands once from this repository:

```bash
uv tool install --editable .
# If uv reports its command directory is absent from PATH:
uv tool update-shell
# Then open a new terminal.
```

Both commands then work from any directory. The editable install picks up code
changes in this checkout; keep the checkout at its current path. To install a
standalone copy instead, use `uv tool install .`. Alternatively, install in a
Python 3.11+ environment with `python3 -m pip install .`.

```bash
claude-history --days 2
codex-history --days 2
codex-history --days 7 --project my-app --json
codex-history --days 30 --html > codex-history.html
```

To remove both commands: `uv tool uninstall claude-history`.

The scripts also run without installation:

```bash
# Run directly (uv handles Python provisioning)
./src/claude_history.py [options]

# Or with uv explicitly
uv run src/claude_history.py [options]

# Or with Python 3.11+
python3 src/claude_history.py [options]
python3 src/codex_history.py [options]
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

### Codex transcripts

`codex-history` accepts the same flags and produces the same JSON schemas as
`claude-history`. It reads rollout `.jsonl` files recursively from
`~/.codex/sessions/` and `~/.codex/archived_sessions/`. Set `CODEX_HOME` to read a
different Codex data directory. It reads transcripts only and never changes them.

User prompts and assistant text (including progress updates) are included;
tool calls/results, reasoning, system/developer messages, and recognized injected
context are skipped. Mirrored event records are not counted twice. Model names
come from turn context; the project comes from the recorded working directory.
The current parser targets modern rollout logs and older `event_msg` text logs;
image-only messages have no extractable text. Codex's transcript format can change.

Codex exports can also feed `build_table.py`, `stats.py`, and `reflect_metrics.py`:

```bash
codex-history --days 30 --max-chars 0 --json | python3 /path/to/claude-history/src/stats.py
```

The full extraction rules are in [`specs/CODEX_HISTORY.md`](specs/CODEX_HISTORY.md).

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
   interruptions and what was typed right after them, short steering follow-ups, sessions where Claude had to ask
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
./src/build_table.py SRC.json [DST.html]
```

The destination defaults to the source path with an `.html` suffix.

### `stats.py`

Aggregates a pairs JSON file into usage statistics — prompt counts per project,
day, weekday, and hour, plus model breakdown and per-session distribution — as
deterministic JSON or a self-contained HTML page with charts
(spec: [`specs/STATISTICS.md`](specs/STATISTICS.md)). The input must be
extracted **without** `--no-noise` and **with** `--max-chars 0`; the shortcut
does this for you:

```bash
just stats 30        # last 30 days -> stats.html (gitignored)
./src/claude_history.py --days 30 --max-chars 0 --format json | ./src/stats.py   # raw JSON aggregates
```

### `check_transcripts.py` (`just smoke`)

The unit tests run against fixtures, and fixtures only encode what we believe
Claude Code writes. Claude Code's transcript format is undocumented and changes
between releases, so this script checks the extraction against **your real
transcripts** instead:

```bash
just smoke        # last 14 days
just smoke 60     # last 60 days
```

It prints one line per check and exits `1` if any check FAILs:

- `project-paths`: every session's project path equals the `cwd` its transcript recorded
- `orphan-answers`: no answer has lost its prompt (e.g. through interleaved sessions)
- `content-shapes`: every user message has a content shape the extraction handles
- `machine-prompts`: no prompt counted as human is an injected (`isMeta`), a context-compaction summary (`isCompactSummary`) or a machine-originated (`origin.kind` ≠ `human`) event
- `new-fields` (WARN only): event types or user-event keys outside the known baseline in the script

Run it after a Claude Code update and before trusting a `/reflect` report. The
output contains counts, session-id prefixes and field names, never prompt or
answer text. It is not part of `just test`, which stays hermetic.

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
- **[`specs/STATISTICS.md`](specs/STATISTICS.md)** — the behavioral
  specification of `stats.py` (aggregates schema, HTML page, CLI).
- **[`skills/reflect/SKILL.md`](skills/reflect/SKILL.md)** — the `/reflect`
  orchestration procedure and critic methodology.
- **`backlog/`** — task history and open work (Backlog.md).

## Author

[Jörn Dinkla](https://www.dinkla.net) — [github.com/jdinkla](https://github.com/jdinkla).
The code in this repo was generated with Claude Code, directed and reviewed by
the author.

## License

Licensed under the [Apache License 2.0](LICENSE). See the [NOTICE](NOTICE) file
for attribution.
