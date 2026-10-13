---
id: TASK-13
title: Make claude_history.py extraction faithful to real transcript data
status: Done
assignee:
  - '@claude'
created_date: '2026-10-13 16:07'
updated_date: '2026-10-13 16:10'
labels:
  - bug
  - extraction
dependencies: []
modified_files:
  - src/claude_history.py
  - src/build_table.py
  - tests/test_claude_history.py
  - specs/SPECIFICATION.md
  - justfile
  - README.md
  - CLAUDE.md
priority: high
type: bug
ordinal: 13000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
A review on 2026-10-12, run against the real ~/.claude/projects (last 14 days), found that the spec, the code and the test fixtures all assume one data model that the transcripts don't follow. The 127 green tests couldn't detect it:

- ~20% of user text events (37/181) carry `isMeta: true`: skill bodies ("Base directory for this skill: …"), messages from other Claude sessions, slash-command bodies. They were counted as human prompts, which distorts reflect_metrics/stats (root cause of TASK-10 item 1, the 8187-char "/website" first prompt).
- Concurrent sessions break pairing: global timestamp sort + "session change closes the pair" splits 3 of 9 sessions into fragments and orphans answers.
- `decode_project` replaces every `-` with `/`; 26 of 29 project dirs decode to non-existent paths (e.g. this repo → /Volumes/JD/repositories/claude/history).
- The truncation marker's "N chars total" is computed on already-truncated text when an answer accumulates.
- Small cleanups: identical extract_user_text/extract_assistant_text, a personal default filename in build_table.py, BSD-only `date -v` in the justfile.

Decision (made by the agent under the user's "fix as many as possible" goal): isMeta user events are dropped unconditionally, because they are never human-authored. Adding a schema flag was the alternative, rejected because it would change the pairs contract that build_table/reflect_metrics/stats consume.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 User events flagged isMeta never appear as prompts in any output format
- [x] #2 Pairs from concurrently running sessions keep their prompt and answer together; output stays ordered chronologically
- [x] #3 Project path is the real cwd when the transcript records one matching the directory encoding; otherwise falls back to the old decoding
- [x] #4 The truncation marker reports the true untruncated length of a paired answer
- [x] #5 build_table.py has no personal default source file; justfile date recipes work with both BSD and GNU date
- [x] #6 specs/SPECIFICATION.md updated for every behavior change; tests cover each fix; suite green
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
1. iter_entries: skip user events with `isMeta` truthy (before noise check).
2. Project path: new `resolve_project(project_dir)` returns the first `cwd` (scanning sorted *.jsonl lines) whose encoding `re.sub(r"[^A-Za-z0-9]", "-", cwd)` equals the dir name; else `decode_project(name)`. Verified on real data: 13 dirs match, 0 mismatch, 15 have no cwd (fallback). The project filter still matches the resolved path or the raw dir name.
3. build_pairs: group entries by session (order of first appearance), pair within each session, then stable-sort pairs by the datetime of their first entry. The text/md/jsonl outputs stay globally chronological.
4. Truncation: accumulate the raw answer text and apply trunc once when a pair is finalized, so the marker's total is the real length.
5. Merge the identical extractors into `extract_text`; keep extract_user_text/extract_assistant_text as aliases (tests and spec name them).
6. build_table.py: SRC becomes required (usage error on missing); justfile: `date -v… 2>/dev/null || date -d …` fallback.
7. Spec §2.1, §2.2, §5, §6, §9.2, §11, §12 + tests for each fix; run the suite; re-run the real-data checks from the review.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Verification: the suite went 127 → 135 tests, all green. The 6 new fix tests fail against HEAD's claude_history.py (checked by running them against the old module); the fallback and ordering tests pass on both, as intended. Real data, 2026-09-29..2026-10-13, old → new: pairs 95 → 75 (meta events gone), orphan prompt-less pairs 2 → 0, human prompts 73 → 60, max first-prompt chars 4653 → 130, non-existent project paths 6 → 3 (the remaining 3 are exact cwds of deleted dirs). Runtime unchanged (~0.22s).

resolve_project only scans in-window files, which iter_entries reads anyway. Directories with no transcript files are skipped before resolution. On this machine, all 15 dirs lacking cwd have zero .jsonl files.

The justfile GNU-date branch was verified with a stub `date` that rejects -v (no GNU date on this Mac), not with real GNU coreutils.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Makes claude_history.py match what Claude Code actually writes. A real-data review found three bugs the fixture-based suite couldn't see.

**Behavior changes (spec §2, §5.4–5.6, §6, §9.2, §11 updated):**
- User events with `isMeta` (skill bodies, slash-command expansions, cross-session messages, caveats) are always skipped. They were ~20% of "prompts" and inflated reflect_metrics/stats; this resolves the symptom behind TASK-10 item 1.
- Pairing runs per session, then pairs are sorted by first entry. Concurrent sessions no longer orphan each other's answers.
- The project path comes from the first event's `cwd` when it re-encodes (`[^A-Za-z0-9]` → `-`) to the directory name; `decode_project` is the fallback. The `--project` filter matches the resolved path or the raw dir name.
- `trunc` runs once on the finished prompt/answer, so `N chars total` is the true length.
- `build_table.py` requires SRC (exit 2 with a usage line); the personal default filename is gone.
- The justfile date recipes fall back to GNU `date -d` when BSD `-v` fails.
- `extract_text` replaces the two identical extractors; the old names remain as aliases.

**Tests:** 8 new (meta skip, cwd resolution/fallback/filter, encode_project, concurrent pairing, cross-session ordering, truncation total); 135 green. CLAUDE.md architecture notes updated.

**Risk:** pairs JSON output changes for existing data (fewer pairs, different project strings). Anything keyed on old project strings, such as saved reflections, won't line up with new extractions.
<!-- SECTION:FINAL_SUMMARY:END -->
