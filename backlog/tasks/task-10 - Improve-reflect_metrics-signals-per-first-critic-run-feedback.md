---
id: TASK-10
title: Improve reflect_metrics signals per first critic run feedback
status: Done
assignee:
  - '@claude'
created_date: '2026-07-04 23:07'
updated_date: '2026-10-13 16:14'
labels:
  - feature
  - reflection
dependencies: []
modified_files:
  - src/reflect_metrics.py
  - tests/test_reflect_metrics.py
  - README.md
priority: medium
ordinal: 10000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
The first /reflect critic run (report 2026-07-05, sonnet) explicitly flagged two weaknesses in the deterministic metrics layer it was given:

1. First-prompt length is polluted by slash-command/skill bodies injected verbatim (e.g. 8187-char "/website" expansions counted as human framing investment). The first HUMAN-authored prompt should be measured instead — skip pairs whose prompt classifies as machine noise when picking a session's first prompt.
2. The start-anchored correction lexicon undercounts real corrections: screenshot-plus-question bug reports ("[Image] why is this?"), efficiency complaints ("what is taking so long?"), and scope-narrowing interruption follow-ups don't begin with a trigger word. Consider additional signals: prompts immediately following an interruption, prompts containing image attachments plus a short question, or a mid-prompt lexicon tier (clearly labeled lower-precision).

Purpose: the metrics exist so the critic argues from observable events; more faithful signals raise the floor of every future reflection.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 First-prompt stats are computed from the first human-classified prompt of each session, ignoring machine-noise pairs
- [x] #2 At least one additional correction signal beyond the start-anchored lexicon, reported separately with its own precision caveat in Method notes
- [x] #3 Tests cover the new signal logic and the suite stays green
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
Research (2026-10-13, 90 days of real data, after TASK-13): 7 human prompts directly followed an interruption, and the start-anchored lexicon caught 0 of them. There were 0 "[Image" markers in prompts, so the image signal isn't viable with current extraction.

1. AC #1: compute_metrics already sets first_prompt_chars on the session's first *human*-classified prompt. Pin that with a test (session opening with slash-command + local-command pairs), and verify on real data that max first-prompt length is plausible.
2. AC #2: new signal `post_interruption_followups`. It counts a human prompt that either contains the interruption marker followed by typed text, or is the first human prompt in the same session after a machine-only interruption pair (machine pairs in between don't reset it). It's reported separately in JSON `signals`, gets its own markdown section, and Method notes label it medium precision (a follow-up can be a plain "yes, continue").
3. README component description lists the new signal.
4. Tests: combined-marker case, next-human-after-interruption case, cross-session isolation, no-interruption negative, markdown section present.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
2026-10-13 (TASK-13): item 1's root cause was `isMeta` user events (injected skill/command bodies) being extracted as prompts. claude_history.py now skips them, and the max first-prompt length on 14 days of real data dropped from 4653 to 130 chars. reflect_metrics already measures the first *human-classified* prompt, so AC #1 may already hold; verify on a fresh reflect-data run before closing it. Item 2 (extra correction signals) is untouched.

Verification on 90 days of real data (extracted with TASK-13 fixes): first-prompt stats n=12, median 60.5, max 440 chars (the critic's report had 8187-char skill bodies). Corrections lexicon: 0 hits; post-interruption follow-ups: 7 (one per interruption). Inspected locally (content not recorded here): most are genuine redirections, one is a plain go-ahead, which is consistent with the medium-precision label. Suite: 140 tests green.

Observed but out of scope: the lexicon has `i meant` but not `i mean`; a real 'sry i mean 3 minute' correction was missed by the lexicon, though the new positional signal caught it.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Makes reflect_metrics' correction evidence less blind and pins the first-prompt measurement.

- **First-prompt length (AC #1):** compute_metrics already measured each session's first *human*-classified prompt. The pollution the critic saw came from injected `isMeta` events, which TASK-13 fixed at extraction. A new test pins the behavior (session opening with slash-command + 5000-char local-command pairs → first prompt = the human one).
- **New signal `post_interruption_followups` (AC #2):** the first human prompt after an interruption, either typed inline after the `[Request interrupted by user…]` marker or as the session's next human prompt (machine pairs in between don't reset it; tracked per session). It's reported in JSON `signals`, in its own markdown section, and Method notes label it medium precision. On 90 days of real data it found 7 follow-ups; the start-anchored lexicon found 0 of them.
- An image-attachment signal was rejected: 0 image markers in extracted prompts.
- README lists the signal. 6 new tests (5 metric + 1 render assertion); 140 green.
<!-- SECTION:FINAL_SUMMARY:END -->
