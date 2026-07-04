---
id: TASK-10
title: Improve reflect_metrics signals per first critic run feedback
status: To Do
assignee: []
created_date: '2026-07-04 23:07'
labels:
  - feature
  - reflection
dependencies: []
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
- [ ] #1 First-prompt stats are computed from the first human-classified prompt of each session, ignoring machine-noise pairs
- [ ] #2 At least one additional correction signal beyond the start-anchored lexicon, reported separately with its own precision caveat in Method notes
- [ ] #3 Tests cover the new signal logic and the suite stays green
<!-- AC:END -->
