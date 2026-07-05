---
id: TASK-9
title: >-
  Decide bare-date --since/--until semantics (currently UTC midnight, surprising
  in CET/CEST)
status: Done
assignee: []
created_date: '2026-07-04 23:06'
updated_date: '2026-07-05 07:09'
labels:
  - bug
  - spec
dependencies: []
priority: medium
ordinal: 9000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
claude_history.py's parse_date interprets a bare date like `--until 2026-07-05` as UTC midnight (parse_ts → naive → replace(tzinfo=utc) → astimezone). In CET/CEST that is 01:00/02:00 local, so a date-only window silently includes the first hours of the "excluded" day. This bit twice on 2026-07-05: (1) the reflect-data recipe initially leaked the running session into its own reflection window, worked around by passing `date +%FT00:00:00%z`; (2) the test suite was flaky between 01:00–02:00 local because fixtures built `--since` from a bare date (fixed by switching fixtures to full ISO timestamps).

Decision needed (spec change — specs/SPECIFICATION.md declares byte-compatible behavior, so this is the user's call): should bare dates mean LOCAL midnight? If yes: change parse_date, update the spec, simplify the justfile recipes (`yesterday`, `reflect-data`) back to bare dates. If no: document the quirk prominently in README/spec instead.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Explicit decision recorded: bare dates = local midnight, or documented status quo
- [x] #2 If semantics change: parse_date, specs/SPECIFICATION.md, justfile recipes and tests updated consistently
- [x] #3 A regression test pins the chosen midnight semantics so the suite cannot be time-of-day flaky again
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
Decision from user (2026-07-05): bare dates = LOCAL midnight on the executing machine (CET/CEST for him).

1. parse_date: naive datetimes attach the local timezone (dt.astimezone()) instead of replace(tzinfo=utc). Applies to bare dates and naive ISO timestamps alike.
2. specs/SPECIFICATION.md: update the parse_date description accordingly.
3. justfile: simplify reflect-data back to bare dates; drop the UTC-workaround comment (yesterday recipe already uses bare dates and becomes correct under the new semantics).
4. Tests: adjust any tests pinning UTC semantics; add regression tests pinning local-midnight for bare dates and offset-preservation for explicit ISO input.
5. README: note local-midnight semantics in the flags table.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Decision (user, 2026-07-05): bare dates = LOCAL midnight on the executing machine (CET/CEST for him).

- parse_date: naive input now gets dt.astimezone() (local) instead of replace(tzinfo=utc); applies uniformly to bare dates and naive ISO timestamps.
- specs/SPECIFICATION.md §7 updated (code + prose, with a historical note on the pre-2026-07-05 UTC behavior).
- justfile reflect-data simplified back to bare $(date +%F) dates; UTC-workaround comment removed. `yesterday` recipe unchanged and now correct.
- README flags table documents local-time semantics for --since/--until.
- Tests: replaced test_bare_date_gets_utc_then_local with test_bare_date_is_local_midnight (pins local midnight + correct utcoffset, DST-aware via datetime(...).astimezone()) and added test_naive_iso_timestamp_is_local. Suite: 115 green.
- Verified against real data: --since 2026-07-04 --until 2026-07-05 yields entries 00:08–23:16 +02:00 (exact local calendar day); reflect-data smoke run excludes the running session.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Bare --since/--until dates (and naive ISO timestamps) now mean local time on the executing machine — a bare date is local midnight. parse_date, spec, README, justfile recipes and tests updated consistently; regression tests pin the semantics so the suite can no longer go time-of-day flaky.
<!-- SECTION:FINAL_SUMMARY:END -->
