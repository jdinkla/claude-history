---
id: TASK-11
title: Reorganize Python files into src/ and tests/ folders
status: In Progress
assignee: []
created_date: '2026-07-05 08:18'
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
- [ ] #1 Scripts live in src/, tests in tests/; git history preserved via git mv
- [ ] #2 just test discovers and runs the full suite green; a single test class can still be run via just test <name>
- [ ] #3 Direct execution ./src/claude_history.py still works (uv shebang)
- [ ] #4 just reflect-data and the other recipes work with the new paths
- [ ] #5 README, CLAUDE.md, and the spec's entry-point reference reflect the new layout
<!-- AC:END -->
