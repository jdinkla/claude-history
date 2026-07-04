---
id: TASK-8
title: >-
  Reflection tool: /reflect skill + metrics layer for analyzing collaboration
  with Claude
status: Done
assignee: []
created_date: '2026-07-04 22:53'
updated_date: '2026-07-04 23:05'
labels:
  - feature
  - reflection
dependencies: []
priority: high
ordinal: 8000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Build a reflection tool on top of claude-history that supports Schön-style reflection-on-action over the user's own Claude Code sessions, to analyze and improve how he collaborates with Claude.

Design constraints (decided with the user):
- The critic must NOT be the same instance that generated the sessions or the one orchestrating the reflection — analysis runs in a fresh subagent, preferably a different model than the one that produced the majority of the analyzed sessions.
- Analysis grounds itself in observable events (corrections, interruptions, rework loops, framing shifts), not opinions, to blunt self-serving judgment.

Components:
1. reflect_metrics.py — deterministic, stdlib-only companion script that consumes `claude_history.py --format json` pairs and computes observable-event metrics (sessions, prompt stats, correction signals, interruptions, slash-command usage, model distribution) with exemplar references.
2. skills/reflect/SKILL.md — a Claude Code skill that extracts the window via claude_history.py, runs the metrics script, spawns an independent critic agent with an evidence-grounded methodology prompt, and saves a dated report under reflections/ (gitignored — contains verbatim private prompts).
3. justfile recipes to prepare reflection data and to install the skill into ~/.claude/skills.
4. Tests for reflect_metrics.py in the existing unittest style; README documentation.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 reflect_metrics.py reads a pairs JSON file (claude_history.py --format json, noise included) and emits markdown and json summaries of observable collaboration events
- [x] #2 Metrics include: session/pair counts, model distribution, prompt-length stats, first-prompt framing stats, correction-signal prompts, interruption markers, slash-command usage — each countable signal lists exemplars with session and timestamp
- [x] #3 A reflect skill exists (versioned in the repo, installable to ~/.claude/skills) that orchestrates extraction, metrics, and an independent critic subagent; the orchestrating instance never performs the critique itself
- [x] #4 The critic prompt requires every claim to cite session+timestamp evidence, permits 'insufficient evidence', focuses on the human's moves, and ends with at most 3 concrete falsifiable experiments
- [x] #5 Default analysis window excludes the current (incomplete) day so the reflecting session never judges its own transcript
- [x] #6 Reports are written to reflections/ which is gitignored
- [x] #7 Tests cover the metrics computation and run green alongside the existing suite via python3 -m unittest
- [x] #8 README documents the reflection workflow
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
- reflect_metrics.py: stdlib-only companion (uv shebang, PEP 723) consuming pairs JSON; named noise classification mirroring claude_history.NOISE_PATTERNS (slash_command/interruption/local_command/context_dump), start-anchored EN+DE correction lexicon, steering threshold 100 chars, exemplars capped via --exemplars; md (default) and json output.
- skills/reflect/SKILL.md: orchestrator-only skill; critic model rule = majority-opus→sonnet else opus; critic prompt embedded with evidence-citation methodology and fixed report sections; reports saved verbatim under reflections/ with provenance header.
- justfile: test, reflect-data (DAYS/PROJECT/OUTDIR), install-skill (symlink). reflect-data passes local-midnight ISO timestamps (date +%FT00:00:00%z) instead of bare dates — claude_history.py parses bare dates as UTC midnight, which leaked the first 2h of today in CEST; found during end-to-end verification when the running session appeared in its own window.
- 27 new tests in test_reflect_metrics.py; full suite 114 green.
- End-to-end verified on real data: 7-day window, 900 pairs/87 sessions; sonnet critic produced a fully cited report; first report at reflections/2026-07-05-last-7-days.md. Notably the critic itself flagged two weaknesses of the metrics layer (first-prompt length polluted by slash-command bodies; correction lexicon undercounts) — candidates for a follow-up task.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Reflection tool shipped: /reflect skill (installed to ~/.claude/skills via just install-skill) + reflect_metrics.py observable-events layer + reflect-data/test/install-skill just recipes + 27 tests + README section. Critic/generator separation enforced by design (independent subagent, model chosen outside the window's majority; window ends yesterday). First real reflection report generated and saved to reflections/ (gitignored).
<!-- SECTION:FINAL_SUMMARY:END -->
