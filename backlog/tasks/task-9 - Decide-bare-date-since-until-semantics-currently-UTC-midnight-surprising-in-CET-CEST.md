---
id: TASK-9
title: >-
  Decide bare-date --since/--until semantics (currently UTC midnight, surprising
  in CET/CEST)
status: To Do
assignee: []
created_date: '2026-07-04 23:06'
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
- [ ] #1 Explicit decision recorded: bare dates = local midnight, or documented status quo
- [ ] #2 If semantics change: parse_date, specs/SPECIFICATION.md, justfile recipes and tests updated consistently
- [ ] #3 A regression test pins the chosen midnight semantics so the suite cannot be time-of-day flaky again
<!-- AC:END -->
