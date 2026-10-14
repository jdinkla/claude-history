---
id: TASK-15
title: Stop counting background task notifications as human prompts
status: Done
assignee:
  - '@claude'
created_date: '2026-10-14 07:42'
updated_date: '2026-10-14 07:42'
labels:
  - bug
  - extraction
  - reflection
dependencies:
  - TASK-14
modified_files:
  - src/claude_history.py
  - src/reflect_metrics.py
  - src/stats.py
  - src/check_transcripts.py
  - specs/SPECIFICATION.md
  - specs/STATISTICS.md
  - CLAUDE.md
  - README.md
  - tests/test_claude_history.py
  - tests/test_reflect_metrics.py
  - tests/test_stats.py
  - tests/test_check_transcripts.py
priority: medium
type: bug
ordinal: 15000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
`just smoke` (TASK-14) fails on real data: when a background task finishes, Claude Code injects a user event whose text is a `<task-notification>…</task-notification>` block (origin.kind = "task-notification", not isMeta). claude_history extracts it and reflect_metrics/stats classify it as a human prompt: 14 across the full history, 4 in the last 14 days. That inflates human-prompt counts, steering follow-ups and the material the /reflect critic reads.

Observed on 2026-10-14: every such event is exactly one task-notification block with no other text, and every one is followed by an assistant reply. So these events trigger answers and behave like slash-command events, not like isMeta injections.

Decision: treat them as a machine-noise kind (kept by default, dropped by --no-noise, classified separately), not as skipped events. Skipping would append Claude's reaction to the previous human pair's answer. Per CLAUDE.md, the noise definition lives in two places by design (claude_history.NOISE_PATTERNS and reflect_metrics.NOISE_KINDS); both and the spec change together.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 A prompt consisting only of a task-notification block is dropped by --no-noise and classified as its own machine kind by reflect_metrics and stats
- [x] #2 A task-notification block followed by human-typed text still counts as human
- [x] #3 SPECIFICATION.md (noise patterns, --no-noise help) and STATISTICS.md (kinds) reflect the new kind
- [x] #4 just smoke reports no human-classified prompt that the transcript marks as machine-originated or injected, and passes on the user's real data
- [x] #5 Tests cover the new kind in claude_history, reflect_metrics, stats and check_transcripts; suite green
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
1. claude_history.NOISE_PATTERNS: add `\s*<task-notification>.*?</task-notification>\s*` (fullmatch); extend the --no-noise help. Spec §3.1 + §8.1.
2. reflect_metrics.NOISE_KINDS: append ("task_notification", …). stats.KINDS gets it before "assistant_only"; STATISTICS.md kinds table + JSON example; CLAUDE.md noise note.
3. check_transcripts `machine-prompts`: flag only extracted prompts that match a raw isMeta/non-human-origin event AND classify as "human". Machine text correctly classified as noise is fine.
4. Tests in all four test files; suite + `just smoke` on real data; commit.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Verification: 156 tests green (3 new: is_noise positive/negative, classify task_notification + with-human-text, check_transcripts passes on a noise-classified machine prompt; stats kind dicts extended). Real data: `just smoke` exit 0, all PASS (14 days); full history machine-prompts PASS; stats kinds over full history: task_notification 14, human 103; `--no-noise` leaves 0 task-notification prompts.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Background-task completion notices (`<task-notification>` blocks, origin.kind = task-notification) are now machine noise instead of human prompts.

- `claude_history.NOISE_PATTERNS` and `reflect_metrics.NOISE_KINDS` both gain the pattern (the two deliberate copies stay in sync); `stats.KINDS` gains `task_notification`. Default output keeps the pair, so Claude's reaction stays attached to its trigger; `--no-noise` drops it; metrics/stats count it as its own kind. A notification followed by typed text still counts as human.
- `check_transcripts` `machine-prompts` now flags machine-marked text only when it's *counted as human*, which is the invariant that matters for metrics.
- Spec §3.1/§8.1, STATISTICS.md §3 + JSON example, CLAUDE.md and README updated.
- Result: `just smoke` passes on real data; 14 notifications across the full history move from `human` to `task_notification`.
<!-- SECTION:FINAL_SUMMARY:END -->
