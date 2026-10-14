---
id: TASK-16
title: 'Count typed slash commands as human prompts, not noise'
status: Done
assignee:
  - '@claude'
created_date: '2026-10-14 12:18'
updated_date: '2026-10-14 12:19'
labels: []
dependencies: []
references:
  - src/claude_history.py
  - src/reflect_metrics.py
  - src/stats.py
  - specs/SPECIFICATION.md
  - specs/STATISTICS.md
priority: medium
type: bug
ordinal: 16000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Skill-driven sessions (e.g. website-factory runs in web-sites/books-about-consulting, session 83708553) consist almost entirely of slash commands, some with human-typed args (a 954-char site brief, "looks good" as a publish approval). Both `claude_history.NOISE_PATTERNS` (--no-noise) and `reflect_metrics.NOISE_KINDS` (classify_prompt) treat every `<command-name/message/args>` wrapper as machine noise. Effect: --no-noise drops the user's actual instructions, the remaining answers collapse into one prompt-less pair (timestamp/prompt null), and stats/reflect under-count human prompts for factory sessions.

Decision (user, 2026-10-14): ALL slash commands count as human — even a bare `/site-design` is a human decision to advance a stage. Local-command stdout/caveat, interruptions, /context dumps and task notifications remain noise. Null timestamp/prompt for genuinely prompt-less pairs stays specified behaviour.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 `--no-noise` keeps prompts consisting of slash-command tag wrappers (with or without args)
- [x] #2 `classify_prompt` returns `human` for slash-command prompts; `slash_command` is no longer a noise kind in reflect_metrics or stats.py
- [x] #3 reflect_metrics still reports slash-command usage by command name
- [x] #4 Human-prompt metrics (length, corrections, steering) are not inflated by the XML tag wrapper
- [x] #5 SPECIFICATION.md, STATISTICS.md, --no-noise help text and README updated consistently
- [x] #6 Tests updated/added; `just test` passes and `just smoke` shows no new FAIL
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
1. claude_history.py: drop the `<command-*>` wrapper pattern from NOISE_PATTERNS; update --no-noise help text. Spec §3.1 + §5 CLI table + historical note.
2. reflect_metrics.py: drop `slash_command` from NOISE_KINDS (slash prompts classify as `human`). Add `prompt_text()` that renders a command wrapper as `/name args` and use it for human length / first-prompt / correction / steering / post-interruption analysis so XML tags don't inflate them. Keep the slash-command usage signal, now counted for any human prompt carrying a `<command-name>`.
3. stats.py: remove `slash_command` from KINDS; STATISTICS.md table + JSON schema.
4. CLAUDE.md noise-kinds list, skills/reflect/SKILL.md wording.
5. Tests: flip is_noise command-tag test to not-noise, classify slash -> human, stats kinds, reflect totals/slash signal, rendered length; end-to-end --no-noise keeps a skill invocation.
6. Verify: just test, just smoke, re-run books-about-consulting extraction (expect no null pair).
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Consequence accepted under the decision: a slash command is a human follow-up everywhere — after an interruption it is the post-interruption follow-up, and a short bare command (e.g. `/commit`) counts as a steering follow-up. Fixtures that used `/clear` or `/context` as stand-ins for machine prompts now use an interruption marker or local-command stdout.

README lists no noise kinds, so it needed no change. `just smoke 365`: all PASS; WARN new-fields `slug` (a raw user-event key) has nothing to do with this change and is left for review.

Real data: `--no-noise` over all history went from 106 pairs with 1 null-timestamp pair to 125 pairs with 0. books-about-consulting now shows its 5 skill invocations as prompts.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Typed slash commands are now human prompts, not noise.

Why: skill-driven sessions (the factory runs) consist mostly of slash commands, and `<command-args>` carries the user's own text, such as a 954-char site brief or a "looks good" approval. `--no-noise` dropped these prompts, the session's answers collapsed into one pair with null timestamp and prompt, and stats/reflect under-counted human prompts.

Changes:
- `claude_history.NOISE_PATTERNS`: the `<command-*>` wrapper pattern is removed. The `--no-noise` help text is updated. SPECIFICATION §3.1 records the old pattern as a historical note.
- `reflect_metrics`: `slash_command` is no longer a noise kind. New `prompt_text()` renders a wrapper as `/name args`, so human length, first-prompt, correction, steering and post-interruption metrics are not inflated by the XML tags. The slash-command usage signal is kept and counted for human prompts that carry a `<command-name>`.
- `stats.py`: `slash_command` is dropped from KINDS, which changes the JSON `kinds` object. STATISTICS.md table and schema are updated.
- CLAUDE.md and skills/reflect/SKILL.md wording updated.

Tests: 161 pass (`just test`), including a new end-to-end test that `--no-noise` keeps a skill invocation with its answer and a non-null timestamp, plus tests for `prompt_text` and tag-free length. `just smoke 365` shows no FAIL.

Risk: the `stats --format json` output loses the `slash_command` key, which matters if anything downstream reads it. Human-prompt counts rise for slash-heavy windows, so metrics are not comparable with reflections written before this change.
<!-- SECTION:FINAL_SUMMARY:END -->
