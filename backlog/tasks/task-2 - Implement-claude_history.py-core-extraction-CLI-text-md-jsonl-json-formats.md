---
id: TASK-2
title: >-
  Implement claude_history.py: core extraction + CLI + text/md/jsonl/json
  formats
status: Done
assignee: []
created_date: '2026-06-11 13:07'
updated_date: '2026-06-11 13:09'
labels:
  - 'model:sonnet'
dependencies: []
ordinal: 2000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Implement per specs/SPECIFICATION.md §1-§9.3: PEP 723 header, constants, NOISE_PATTERNS, Entry dataclass, helpers (is_noise, decode_project, parse_ts, extract_user_text, extract_assistant_text), iter_entries, parse_date, main() with argparse, time window, trunc, jsonl/json/text/md outputs and build_pairs. Leave HTML_TEMPLATE as placeholder for task-3. Executing model: Sonnet.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 All helpers match spec code verbatim
- [x] #2 CLI flags and defaults match §8.1
- [x] #3 build_pairs matches §9.2 exactly
<!-- AC:END -->
