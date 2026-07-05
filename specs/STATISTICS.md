# `stats.py` — Prompt Statistics Specification

Status: **implemented** (spec written and implemented 2026-07-05, TASK-12).

A companion script that aggregates the prompt/answer history into usage
statistics: how many prompts, across which sessions, projects, days, weekdays,
and hours of the day. It answers "when and where do I work with Claude Code",
complementing `reflect_metrics.py`, which answers "how do I collaborate".

Design decisions fixed with the user on 2026-07-05:

1. **All pairs are counted, with a noise breakdown** — statistics are not
   restricted to human prompts; every pair is classified (human vs. the
   machine-noise kinds) and both totals and the human share are reported.
2. **Outputs: JSON aggregates and a self-contained HTML page.** No
   Markdown/text renderer in v1.
3. **In scope beyond flat counts:** model breakdown and session-level
   distribution. **Out of scope for v1:** the weekday×hour heatmap (future
   work, see §9).
4. **Placement: new companion script `src/stats.py`** consuming pairs JSON,
   following the `build_table.py` / `reflect_metrics.py` pattern. The spec'd
   `claude_history.py` is not touched.

## 1. Overview

```
claude_history.py --format json  ──►  stats.py  ──►  aggregates JSON (stdout)
        (pairs JSON)                              └─►  self-contained HTML page (stdout)
```

- Standard library only, Python ≥ 3.11, `uv run --script` shebang with an
  empty PEP 723 dependency block (house constraint).
- Reads a pairs-JSON file or stdin; writes only stdout.
- Deterministic: same input ⇒ byte-identical output (no wall-clock reads,
  no environment-dependent ordering).

## 2. Input contract

Input is the pairs JSON array produced by `claude_history.py --format json`
(schema: `timestamp, session, project, model, prompt, answer,
answer_timestamp`; see `specs/SPECIFICATION.md` §9.2–9.3).

**The extraction MUST be run:**

- **without `--no-noise`** — otherwise the noise breakdown is empty and
  totals undercount;
- **with `--max-chars 0`** — the truncation marker
  (`… [truncated, N chars total]`) appended by `claude_history.py` leaves
  residue after the noise patterns are subtracted, which makes
  `classify_prompt` misclassify truncated machine prompts as `human`.
  (Same reason `just reflect-data` extracts `full.json` with `--max-chars 0`.)

`stats.py` does not verify these conditions; the justfile recipe (§7)
encodes the correct invocation.

## 3. Prompt classification

Each pair's `prompt` is classified into exactly one kind:

| kind | meaning |
|---|---|
| `human` | text the user actually typed |
| `slash_command` | `<command-name/message/args>` wrapper |
| `interruption` | `[Request interrupted by user …]` marker |
| `local_command` | `<local-command-stdout/caveat>` wrapper |
| `context_dump` | `## Context Usage …` dump |
| `assistant_only` | pair has `prompt: null` (assistant text with no preceding user prompt) |

Classification is **imported, not duplicated**:
`from reflect_metrics import classify_prompt` (sibling module in `src/`;
works under the `uv run --script` shebang because the script's directory is
on `sys.path`). `CLAUDE.md` documents two deliberate copies of the noise
logic (`claude_history.NOISE_PATTERNS`, `reflect_metrics.NOISE_KINDS`);
this script must not become a third — any classification change continues
to touch exactly those two places.

## 4. Time handling

- Every timestamp in the pairs JSON is a local-time ISO-8601 string with a
  UTC offset (produced via `.astimezone().isoformat()`). Parse with
  `datetime.fromisoformat` and derive date / weekday / hour **from the
  local time as written** — do not re-convert to the executing machine's
  timezone. This keeps output deterministic and tests time-of-day/TZ stable
  (fixtures carry explicit offsets).
- A pair's **reference timestamp** for all time dimensions is `timestamp`,
  falling back to `answer_timestamp` when `timestamp` is `null`
  (assistant-only pairs). Pairs where both are `null` cannot occur per the
  pairing algorithm, but if encountered they are counted in the non-time
  dimensions (totals, project, kind, model) and skipped in `by_day`,
  `by_weekday`, `by_hour`, and session duration.
- Weekday keys are `Mon`…`Sun`, **Monday first** (ISO order).

## 5. Aggregates (the JSON output)

`--format json` emits a single pretty-printed object (`indent=2`,
`ensure_ascii=False`, trailing newline — matching house JSON style):

```jsonc
{
  "range": { "first": "<ISO|null>", "last": "<ISO|null>" },   // min/max reference timestamps
  "totals": {
    "pairs": 0,               // number of pairs in the input
    "human": 0,               // pairs classified `human`
    "kinds": {                // every kind always present, zero-filled
      "human": 0, "slash_command": 0, "interruption": 0,
      "local_command": 0, "context_dump": 0, "assistant_only": 0
    },
    "sessions": 0,            // distinct session ids
    "projects": 0,            // distinct project paths
    "active_days": 0          // distinct dates with ≥1 pair
  },
  "by_project": [             // sorted by human desc, then pairs desc, then project asc
    { "project": "/Users/…", "pairs": 0, "human": 0, "sessions": 0,
      "models": { "<model-or-'(none)'>": 0 } }   // pairs per model, keys sorted
  ],
  "by_day": [                 // ascending; gaps between first and last date zero-filled
    { "date": "YYYY-MM-DD", "pairs": 0, "human": 0 }
  ],
  "by_weekday": [             // always exactly 7 rows, Mon..Sun
    { "weekday": "Mon", "pairs": 0, "human": 0 }
  ],
  "by_hour": [                // always exactly 24 rows, 0..23
    { "hour": 0, "pairs": 0, "human": 0 }
  ],
  "by_model": [               // sorted by pairs desc, then model asc; null model → "(none)"
    { "model": "claude-opus-4-6", "pairs": 0 }
  ],
  "sessions": {
    "per_session_pairs":  { "min": 0, "median": 0, "mean": 0.0, "max": 0 },
    "per_session_human":  { "min": 0, "median": 0, "mean": 0.0, "max": 0 },
    "top": [                  // top N sessions by human desc, then pairs desc, then first asc
      { "session": "<uuid>", "project": "/Users/…",
        "first": "<ISO>", "last": "<ISO>", "duration_minutes": 0,
        "pairs": 0, "human": 0 }
    ]
  }
}
```

Details:

- `models` / `by_model`: the pair's `model` field; `null` is rendered as
  the literal key `"(none)"`.
- `mean` is rounded to one decimal (`round(x, 1)`); `median` via
  `statistics.median`; distributions over the empty set render all four
  values as `0` / `0.0`.
- `duration_minutes` = (max − min over the session's non-null `timestamp`
  and `answer_timestamp` values), as integer minutes (`round(seconds/60)`).
- `top` length is capped by `--top` (default 10).
- Empty input (`[]`) is valid: `range` nulls, zeroed totals, empty
  `by_project` / `by_model` / `top`, empty `by_day`, but `by_weekday` and
  `by_hour` still zero-filled at full length.

## 6. HTML output (`--format html`)

A self-contained interactive page on stdout — same discipline as
`claude_history.py --format html` (see `specs/SPECIFICATION.md` §10):

- No external resources of any kind; vanilla JS, no libraries.
- The aggregates object is embedded by replacing a `__DATA__` placeholder
  with `json.dumps(aggregates, ensure_ascii=False).replace("</", "<\\/")`;
  the title via a `__TITLE__` placeholder (HTML-escaped `<`).
- Visual conventions follow the existing template: CSS variables on
  `:root`, `color-scheme: light dark`, `prefers-color-scheme: dark`
  override, system font stack.
- Sections, top to bottom:
  1. **Summary tiles** — pairs, human prompts, sessions, projects, active
     days, date range.
  2. **Prompts per day** — bar chart over `by_day` (human vs. total
     distinguishable).
  3. **By weekday** and **by hour** — two bar charts.
  4. **By project** — table with count columns and an inline bar, top
     projects first.
  5. **By model** — table.
  6. **Sessions** — the distribution stats plus the top-N session table.
- Charts are plain SVG or styled divs. The implementer must load the
  `dataviz` skill before writing chart markup and follow it for color,
  axis, and legend choices (within the no-external-resources constraint).
- Empty input renders the page with a visible "no data" note instead of
  charts.

## 7. CLI and justfile

```
usage: stats.py [SRC] [--format {json,html}] [--top N] [--title TITLE]
```

| argument | default | meaning |
|---|---|---|
| `SRC` (positional) | `-` (stdin) | pairs JSON file from `claude_history.py --format json` |
| `--format` | `json` | `json` = aggregates object; `html` = self-contained page. JSON is the default so bare terminal runs stay readable; the recipe opts into HTML. |
| `--top` | `10` | number of sessions in `sessions.top` |
| `--title` | `Claude Code statistics` | HTML page title (ignored for `json`) |

justfile recipe (group `history`):

```just
[group('history')]
[doc("Prompt statistics for the last DAYS days as a self-contained HTML page (stats.html)")]
stats DAYS="30":
    ./src/claude_history.py --days {{DAYS}} --max-chars 0 --format json | ./src/stats.py --format html > stats.html
    @echo "Written stats.html"
```

`stats.html` is added to `.gitignore`: the aggregates contain no prompt
text, but project paths and session ids are still the user's private
usage data.

## 8. Tests

`tests/test_stats.py`, stdlib `unittest`, run by the existing `just test`
discovery. Fixtures are in-memory pairs lists (no `PROJECTS_DIR` patching
needed — the script never touches the filesystem beyond `SRC`). All fixture
timestamps are full ISO strings **with explicit UTC offsets**, so derived
date/weekday/hour values are independent of the machine's timezone and
time of day (house rule: no time-of-day-flaky fixtures).

Minimum coverage:

- classification counts per kind, including `assistant_only`
  (`prompt: null`) and the `(none)` model key;
- `by_day` gap zero-filling; `by_weekday` fixed 7-row Mon-first order;
  `by_hour` fixed 24 rows;
- reference-timestamp fallback to `answer_timestamp`;
- session distribution values and `top` ordering/capping;
- empty-input shape (§5 last bullet);
- HTML output embeds the data, escapes `</`, and contains no external
  URLs (`http://` / `https://` in `src=`/`href=` forbidden).

## 9. Non-goals / future work

- **Weekday×hour heatmap** — explicitly deferred out of v1 by the user.
  The `by_weekday` / `by_hour` aggregates do not suffice for it; adding it
  later means adding a `by_weekday_hour` matrix to §5 and a heatmap section
  to §6.
- Markdown/terminal renderer.
- Filtering — none in `stats.py` itself; window and project selection is
  done upstream via `claude_history.py --days/--since/--until/--project`.
- Trend/rolling aggregates (per-week, moving averages).
