---
id: TASK-17
title: Skip context-compaction summaries instead of extracting them as human prompts
status: Done
assignee:
  - '@claude'
created_date: '2026-10-14 12:25'
updated_date: '2026-10-14 12:26'
labels: []
dependencies: []
references:
  - src/claude_history.py
  - src/check_transcripts.py
  - specs/SPECIFICATION.md
priority: medium
type: bug
ordinal: 17000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
When a session runs out of context, Claude Code writes the generated summary ("This session is being continued from a previous conversation…") into the transcript as a user event with `isCompactSummary: true` (and `isVisibleInTranscriptOnly: true`), not `isMeta`. claude_history.py extracts it as a prompt and classify_prompt counts it as human, so every compaction inflates human-prompt counts and prompt lengths and adds a multi-KB "prompt" to reflection data. Observed in claude-history session 17eade9a on 2026-10-14. The smoke check's machine-prompts check only flags isMeta / origin.kind, so it misses this leak.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 User events with `isCompactSummary` truthy are never extracted, with or without --no-noise
- [x] #2 `just smoke`'s machine-prompts check flags a compaction summary that leaks into the extraction
- [x] #3 SPECIFICATION.md documents the skip; README smoke-check description updated
- [x] #4 Tests cover the skip and the smoke detection; `just test` passes and `just smoke` shows no FAIL
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
1. claude_history.iter_entries: skip user events with truthy `isCompactSummary`, alongside the existing `isMeta` skip, before the noise filter so it applies regardless of --no-noise. Key on `isCompactSummary` rather than `isVisibleInTranscriptOnly`: across all local transcripts the latter appears only on compaction summaries, but its meaning is broader and unverified.
2. check_transcripts: flag `isCompactSummary` events as machine ("isCompactSummary") in the machine-prompts check.
3. SPECIFICATION.md: add an `isCompactSummary` row to the event-field table and the skip step in the iter_entries algorithm. README: update the machine-prompts line.
4. Tests: an iter_entries skip test; smoke tests for both PASS (skipped) and FAIL (leaked).
5. Verify with just test, just smoke, and re-extract claude-history (no "This session is being continued" prompt).
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Verified that both new tests fail without the src change: test_compact_summary_skipped and test_leaked_compact_summary_fails FAIL with src stashed and pass with it. `just smoke 365`: all PASS, and the only WARN is new-fields `slug`, which predates this task. A real-data re-extraction finds 0 compaction-summary prompts; there was 1 before.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Context-compaction summaries are no longer extracted as human prompts.

Why: when a session runs out of context, Claude Code writes its generated summary into the transcript as a user event marked `isCompactSummary: true`. The extraction only skipped `isMeta` events, so each compaction added a multi-KB "human" prompt to pairs, stats and reflection data.

Changes:
- `claude_history.iter_entries` skips user events with `isCompactSummary` (next to `isMeta`), with or without `--no-noise`.
- `check_transcripts` machine-prompts check flags a leaked compaction summary as `isCompactSummary`.
- SPECIFICATION.md event-field table and iter_entries algorithm updated; README smoke-check line updated.

Tests: 164 pass. The new extraction skip test and the smoke FAIL-detection test were confirmed to fail without the fix. `just smoke 365` shows no FAIL.

Note: the skip keys on `isCompactSummary`, not the broader `isVisibleInTranscriptOnly`, whose wider meaning is unverified. Locally the two flags only ever appear together.
<!-- SECTION:FINAL_SUMMARY:END -->
