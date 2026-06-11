---
id: TASK-6
title: Test suite for claude_history.py
status: Done
assignee: []
created_date: '2026-06-11 13:07'
updated_date: '2026-06-11 13:16'
labels:
  - 'model:sonnet'
dependencies: []
ordinal: 6000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Pytest-style tests using stdlib unittest (no third-party deps) covering: helpers, noise patterns, iter_entries filtering (date window, project filter, noise, malformed lines), parse_date, build_pairs pairing rules, trunc, all 5 output formats, edge cases §14. Use a temp HOME with fixture transcripts. Executing model: Sonnet.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Tests cover §5-§9 behaviors and §14 edge cases
- [x] #2 All tests pass with python3 -m unittest
<!-- AC:END -->
