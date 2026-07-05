---
id: TASK-11
title: Reorganize Python files into src/ and tests/ folders
status: Done
assignee: []
created_date: '2026-07-05 08:18'
updated_date: '2026-07-05 08:19'
labels:
  - chore
dependencies: []
priority: medium
ordinal: 11000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Move the three scripts (claude_history.py, reflect_metrics.py, build_table.py) into src/ and the two test modules into tests/, keeping everything runnable: uv-shebang direct execution, just recipes, unittest discovery, and single-test invocation. Update every path reference (justfile, README, CLAUDE.md, specs/SPECIFICATION.md entry-point note) so no doc drifts.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Scripts live in src/, tests in tests/; git history preserved via git mv
- [x] #2 just test discovers and runs the full suite green; a single test class can still be run via just test <name>
- [x] #3 Direct execution ./src/claude_history.py still works (uv shebang)
- [x] #4 just reflect-data and the other recipes work with the new paths
- [x] #5 README, CLAUDE.md, and the spec's entry-point reference reflect the new layout
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
- git mv: claude_history.py, reflect_metrics.py, build_table.py → src/; both test modules → tests/ (renames detected 98-100%, history preserved).
- tests/*.py got a 3-line sys.path shim inserting ../src before the module-under-test import, so bare `python3 -m unittest discover -s tests` works from the repo root with no env vars.
- justfile: `test *ARGS="discover -s tests -v"` runs discovery by default with PYTHONPATH=tests, so `just test test_claude_history.TestParseDate` still runs a single class; all script invocations now ./src/....
- Path references updated in README, CLAUDE.md (single-test example now goes through `just test`), and specs/SPECIFICATION.md (entry-point + invocation examples). No behavior change, so no other spec edits needed.
- Verified: full suite 115 green via just test, single-test invocation, direct ./src/claude_history.py execution, reflect-data smoke run, just --list parse. Commit 7677824.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Python sources now live in src/ and tests in tests/, moved with git mv. Tests self-locate src/ via a sys.path shim; just test defaults to unittest discovery while still accepting single-test args; justfile/README/CLAUDE.md/spec references all updated. Suite green, recipes verified.
<!-- SECTION:FINAL_SUMMARY:END -->
