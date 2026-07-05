---
id: TASK-12
title: Add prompt statistics tool (stats.py) per specs/STATISTICS.md
status: Done
assignee:
  - Claude
created_date: '2026-07-05 09:34'
updated_date: '2026-07-05 09:49'
labels:
  - feature
dependencies: []
documentation:
  - specs/STATISTICS.md
  - specs/SPECIFICATION.md
modified_files:
  - src/stats.py
  - tests/test_stats.py
  - specs/STATISTICS.md
  - justfile
  - .gitignore
  - README.md
  - CLAUDE.md
priority: medium
ordinal: 12000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Users want to see when and where they work with Claude Code: prompt counts across sessions, projects, days, weekdays, and hours of day, plus a model breakdown and per-session distribution.

The behavior is fully specified in specs/STATISTICS.md (design decisions fixed with Jörn on 2026-07-05): a new companion script src/stats.py consumes pairs JSON from claude_history.py --format json (run without --no-noise and with --max-chars 0), classifies every pair via reflect_metrics.classify_prompt (imported, not duplicated — do not create a third copy of the noise logic), and emits either a deterministic aggregates JSON object or a self-contained HTML page with charts. Out of scope for v1: weekday×hour heatmap, markdown output, any filtering inside stats.py.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 stats.py produces the aggregates JSON exactly as specified in specs/STATISTICS.md §5 (dimensions, ordering, zero-filling, empty-input shape)
- [x] #2 stats.py --format html produces a self-contained page per §6 with no external resources, rendering summary tiles, per-day/weekday/hour charts, project, model, and session tables
- [x] #3 Prompt classification is imported from reflect_metrics; no third copy of the noise patterns exists
- [x] #4 Time dimensions are derived from the local time written in the timestamps, with answer_timestamp fallback for assistant-only pairs
- [x] #5 `just stats [DAYS]` writes stats.html and stats.html is gitignored
- [x] #6 tests/test_stats.py covers at least the minimum list in §8 and passes via `just test` with fixtures that are timezone- and time-of-day-stable
- [x] #7 README.md and CLAUDE.md command overviews mention the new tool and recipe
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
Approach (spec = specs/STATISTICS.md, decisions already fixed with Jörn):

1. src/stats.py — uv run --script shebang, stdlib only. `from reflect_metrics import classify_prompt` (verified working under the shebang). Structure mirrors reflect_metrics.py: compute_stats(pairs, top_n) -> dict per §5 (reference ts = timestamp, fallback answer_timestamp; date/weekday/hour from local time as written; Mon-first weekdays; zero-filled day gaps, 7 weekday rows, 24 hour rows; models with "(none)" key; per-session distributions min/median/mean/max, mean rounded 1 decimal; top-N by human desc, pairs desc, first asc). render_html embeds the aggregates via __DATA__/__TITLE__ placeholders, CSS-variable light/dark theme like claude_history.HTML_TEMPLATE, vanilla JS + SVG/div bars (dataviz skill consulted for chart choices).
2. tests/test_stats.py — unittest, in-memory pairs fixtures with explicit UTC offsets (TZ-stable); §8 minimum list.
3. justfile: `stats DAYS="30"` recipe piping claude_history (--max-chars 0, no --no-noise) into stats.py --format html > stats.html; add stats.html to .gitignore.
4. README.md + CLAUDE.md: mention tool + recipe in command overviews.
5. Verify: just test; end-to-end run on real history; check HTML has no external URLs and JSON matches empty-input shape.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Deviations/decisions during implementation: (1) HTML project/session tables display project paths with the common path prefix stripped instead of the bare last segment — the last segment collided for 9 of 75 real projects (two "test", two "ai", …); full path stays in the cell's title attribute. (2) Chart design per the dataviz skill: stacked columns human (blue #2a78d6/#3987e5) + machine noise (aqua #1baf7a/#199e70), palette validated with the skill's validator in both modes (light-mode aqua contrast WARN mitigated by hover tooltips + per-chart "View data" table view). (3) Session top-list sort key uses .timestamp() floats, not aware-datetime min sentinels, to avoid tz-underflow edge cases.

Verification: 127 tests pass (just test). End-to-end on real data (30 days: 4,534 pairs, 368 sessions, 75 projects) with cross-dimension sum consistency asserts. Page rendered via Playwright in light AND dark mode, zero page errors; tooltip and table-view interactions exercised. stats.html confirmed absent from git status.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Adds src/stats.py, the prompt-statistics companion tool specified in specs/STATISTICS.md.

What changed
- src/stats.py: consumes pairs JSON (from claude_history.py --format json, without --no-noise, --max-chars 0) and emits either a deterministic aggregates JSON object (range, totals with per-kind noise breakdown, by_project, gap-filled by_day, fixed Mon-first by_weekday, fixed 24-row by_hour, by_model, per-session distributions + top-N sessions) or a self-contained HTML page (stat tiles, three stacked-column charts with tooltips and per-chart data tables, project/model/session tables, light+dark via prefers-color-scheme, zero external resources). Classification is imported from reflect_metrics (no third copy of the noise logic).
- tests/test_stats.py: 13 tests covering the §8 minimum list; fixtures use explicit UTC offsets so the suite is timezone- and time-of-day-stable.
- justfile: new `stats DAYS="30"` recipe writing stats.html; .gitignore: stats.html.
- README.md (Companion Tools + documentation map) and CLAUDE.md (layers, commands, noise-duplication note) updated.

Verification
- just test: 127 tests OK.
- Real-data run (30 days, 4,534 pairs): cross-dimension sums consistent; page rendered and visually checked in light and dark mode via Playwright with no page errors; hover tooltips and table views work.

Risks/notes
- HTML display names strip the common project-path prefix (kept unique on purpose); aggregates JSON is untouched by this and remains the byte-deterministic contract.
<!-- SECTION:FINAL_SUMMARY:END -->
