---
id: TASK-14
title: Check extraction assumptions against the user's real transcripts on demand
status: Done
assignee:
  - '@claude'
created_date: '2026-10-13 16:12'
updated_date: '2026-10-13 16:17'
labels:
  - testing
  - extraction
dependencies:
  - TASK-13
references:
  - >-
    backlog/tasks/task-13 -
    Make-claude_history.py-extraction-faithful-to-real-transcript-data.md
  - specs/SPECIFICATION.md
modified_files:
  - src/check_transcripts.py
  - tests/test_check_transcripts.py
  - justfile
  - README.md
  - CLAUDE.md
priority: medium
type: task
ordinal: 14000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
TASK-13 fixed three bugs (injected isMeta prompts, concurrent sessions breaking pairing, lossy project-path decoding) that 127 green unit tests could not catch. The spec, code and fixtures all shared one wrong model of the transcript format, so the tests checked that the code matched the spec, never that the spec matched the data. The bugs only showed up when ad-hoc scripts were run against ~/.claude/projects.

Claude Code's transcript format is undocumented and changes between releases. A repeatable real-data check turns those ad-hoc scripts into a tool the user can run after a Claude Code update, or before trusting a /reflect report, so new format drift shows up before it skews metrics.

Constraints from CLAUDE.md still apply: stdlib only, a Python ≥ 3.11 uv-script shebang, reads only ~/.claude/projects, writes only stdout/stderr. The check reads private prompts, so its output must never echo prompt or answer text; counts, session-id prefixes and timestamps are fine. It's a local diagnostic, not part of `just test`: the unit suite must stay hermetic.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 A single just recipe runs the check over a configurable recent window (default: last 14 days)
- [x] #2 It reports, for the window, at least: project paths in the output that don't match their transcript's recorded cwd; prompt-less pairs whose session has a user prompt earlier in the window; and user events with an unknown or unhandled content shape
- [x] #3 It reports any user-event flags or top-level event types it has never seen before, so new transcript fields are noticed rather than silently ignored
- [x] #4 It exits non-zero when any invariant is violated and zero otherwise, with a one-line summary per check
- [x] #5 Its output never contains prompt or answer text (verified by a test over a fixture with distinctive text)
- [x] #6 Not run by `just test`; the check logic itself has unit tests over temp-dir fixtures and the suite stays green
- [x] #7 README (or CLAUDE.md commands section) documents when to run it
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
Research (2026-10-13, full history of 16 transcripts): event types seen = user, assistant, system, attachment, mode, permission-mode, file-history-snapshot, file-history-delta, cost-state, last-prompt, queue-operation, custom-title, ai-title, agent-name, atis-latch. User content is str or list; list block types = text, tool_result, image. 33 distinct user-event keys. Finding: 14 extracted non-meta prompts carry `origin.kind = "task-notification"` (background-task notices, not typed by the human). isMeta doesn't catch them, so they still count as human prompts.

Design: new `src/check_transcripts.py` (stdlib, uv shebang, imports claude_history like stats imports reflect_metrics), recipe `just smoke DAYS="14"`.
- Runs the real extraction in-process (`ch.main(["--days", N, "--max-chars", "0", "--format", "json"])` with stdout captured) so it checks the real CLI path, then scans the same in-window raw files.
- FAIL checks (exit 1): `project-paths` (the session's extracted project != the first recorded cwd of its transcript); `orphan-answers` (prompt-less pair in a session that already had a prompt); `content-shapes` (in-window user event whose content isn't str/list, or has a non-dict or unknown block type); `machine-origin-prompts` (extracted user prompt whose `origin.kind` is set and isn't "human").
- WARN (reported, exit unaffected): `new-fields`, i.e. event types or user-event keys outside the baseline. A new harmless field shouldn't read as a broken extractor, but it should be seen.
- Output: one line per check (status, name, counts, at most 5 session-id prefixes / kinds / key names). Never prompt or answer text.
- Tests: tests/test_check_transcripts.py over temp-dir fixtures (patch ch.PROJECTS_DIR), one per check plus a privacy test with distinctive text. `just test` stays hermetic.
- Docs: README companion-tools section + CLAUDE.md commands/overview.

Deviation, done during implementation: `machine-origin-prompts` became `machine-prompts`. It compares the extraction's *output* with raw events flagged isMeta or non-human origin, instead of re-implementing the skip rules. Reason: against the pre-TASK-13 code the first version missed the isMeta bug, because it applied the same skip rule the check was meant to verify. Tests use --days 2 so minute-old fixtures are in the window at any time of day.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Verification: 153 tests green (13 new in tests/test_check_transcripts.py, including a privacy test with distinctive prompt/answer strings over a fixture that makes every detail path run). Real data, current code: 4 PASS, machine-prompts FAIL (4 task-notification prompts in 14 days, 14 across full history), exit 1. Against the pre-TASK-13 claude_history.py (4a17f2d): project-paths FAIL 6/9, orphan-answers FAIL 2, machine-prompts FAIL 24 (isMeta 20 + task-notification 4), so the check catches all three bugs TASK-13 fixed.

Open finding (not fixed, out of scope): user events with `origin.kind = "task-notification"` (background-task completion notices) are extracted as human prompts. isMeta doesn't mark them. Fixing it is a claude_history.py behavior change (spec + both noise lists) and needs its own task.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Adds `src/check_transcripts.py` and `just smoke [DAYS=14]`: a check of the extraction's assumptions against the user's real transcripts. The fixture-based suite can't catch transcript-format drift, because the fixtures encode the same assumptions as the code.

- Runs the real extraction in-process (`--max-chars 0 --format json`) and scans the same in-window raw files.
- FAIL checks (exit 1): `project-paths` (extracted project = first recorded cwd), `orphan-answers` (no prompt-less pair after a session's first prompt), `content-shapes` (user content is str or a list of text/tool_result/image blocks), `machine-prompts` (no extracted prompt matches a raw isMeta or non-human-origin event).
- WARN (exit unaffected): `new-fields`, i.e. event types or user-event keys outside a baseline taken from the full history on 2026-10-13.
- Output is counts, session-id prefixes and field names only; a test proves prompt/answer text never appears.
- Not part of `just test`; 13 unit tests over temp-dir fixtures. README section on when to run it; CLAUDE.md commands/overview updated.

Validated against the pre-TASK-13 extraction: it flags all three bugs TASK-13 fixed. On current code it FAILs on a real, still-open issue: task-notification prompts extracted as human (4 in the last 14 days). That needs a follow-up task.
<!-- SECTION:FINAL_SUMMARY:END -->
