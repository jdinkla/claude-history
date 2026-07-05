# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

CLI tools that extract and analyze the prompt/answer history of Claude Code sessions from the transcript files under `~/.claude/projects/<encoded-cwd>/<session-id>.jsonl`. Two layers:

1. **Extraction** — `claude_history.py` filters sessions by date/project and renders text, Markdown, JSONL, JSON pairs, or a self-contained interactive HTML page. `build_table.py` renders a saved pairs JSON as a flat HTML table.
2. **Reflection** — `reflect_metrics.py` + the `/reflect` skill (`skills/reflect/SKILL.md`) implement Schön-style reflection-on-action over the user's own collaboration transcripts (see README "Reflection workflow").

## Hard constraints

- **Standard library only, Python ≥ 3.11.** Every script starts with a `uv run --script` shebang plus a PEP 723 block declaring `dependencies = []`. Do not add third-party packages.
- **`specs/SPECIFICATION.md` is a complete behavioral spec** for `claude_history.py` — it claims an agent can re-implement the tool from it with byte-compatible JSON/JSONL/HTML output. Any behavior change to `claude_history.py` MUST update the spec in the same commit (precedent: TASK-9 changed date semantics in code + spec + README + tests together).
- Scripts read only `~/.claude/projects/` and write only stdout (plus one stderr diagnostic).
- **Never commit `reflections/`** (gitignored): reflection reports and extracted data quote private prompts verbatim.

## Commands

```bash
just test                          # full suite (python3 -m unittest -v)
python3 -m unittest test_claude_history.TestParseDate.test_bare_date_is_local_midnight  # single test
just prompts 8 backend             # last 8 days of one project as JSON pairs
just days 3 md                     # last 3 days, all projects
just yesterday                     # yesterday only
just reflect-data 7 "" OUTDIR      # extract full.json/clean.json/metrics.md for reflection
just install-skill                 # symlink skills/reflect into ~/.claude/skills
./claude_history.py --days 8 --no-noise --format json   # run directly (uv bootstraps)
```

## Architecture notes that span files

- **Date semantics (decided 2026-07-05):** bare `--since/--until` dates and naive ISO timestamps mean **local time on the executing machine**; a bare date is local midnight. `parse_date` attaches local tz via `dt.astimezone()`. Tests pin this; don't reintroduce UTC-midnight interpretation.
- **Noise filtering is duplicated by design:** `claude_history.NOISE_PATTERNS` (anonymous, fullmatch, used by `--no-noise`) and `reflect_metrics.NOISE_KINDS` (named kinds: slash_command / interruption / local_command / context_dump, used for classification). Changing what counts as noise means touching both — and the spec.
- **Pairing logic** lives in `main()`'s `build_pairs()` in `claude_history.py`: consecutive assistant texts append to the current pair's answer; a session change or a new user prompt starts a new pair; the first assistant timestamp/model wins. The JSON pairs schema (`timestamp, session, project, model, prompt, answer, answer_timestamp`) is the contract consumed by `build_table.py` and `reflect_metrics.py`.
- **Reflection ground rules** (user's explicit design decisions, encoded in `skills/reflect/SKILL.md`): the critic is never the generator — critique runs in a fresh subagent with a model chosen outside the analyzed window's majority; every claim must cite session + timestamp; the analysis window always ends yesterday so a running session never judges its own transcript.
- **Tests** are stdlib `unittest`; fixtures patch `ch.PROJECTS_DIR` into a temp dir and build `--since` values from full ISO timestamps (bare-date fixtures made the suite time-of-day flaky once — don't regress this).

<!-- BACKLOG.MD MCP GUIDELINES START -->

<CRITICAL_INSTRUCTION>

## BACKLOG WORKFLOW INSTRUCTIONS

This project uses Backlog.md MCP for all task and project management activities.

**CRITICAL GUIDANCE**

- If your client supports MCP resources, read `backlog://workflow/overview` to understand when and how to use Backlog for this project.
- If your client only supports tools or the above request fails, call `backlog.get_backlog_instructions()` to load the tool-oriented overview. Use the `instruction` selector when you need `task-creation`, `task-execution`, or `task-finalization`.

- **First time working here?** Read the overview resource IMMEDIATELY to learn the workflow
- **Already familiar?** You should have the overview cached ("## Backlog.md Overview (MCP)")
- **When to read it**: BEFORE creating tasks, or when you're unsure whether to track work

These guides cover:
- Decision framework for when to create tasks
- Search-first workflow to avoid duplicates
- Links to detailed guides for task creation, execution, and finalization
- MCP tools reference

You MUST read the overview resource to understand the complete workflow. The information is NOT summarized here.

</CRITICAL_INSTRUCTION>

<!-- BACKLOG.MD MCP GUIDELINES END -->
