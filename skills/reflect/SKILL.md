---
name: reflect
description: Schön-style reflection-on-action over your own Claude Code sessions — extract history, compute observable-event metrics, then have an INDEPENDENT critic agent analyze your collaboration moves and propose experiments. Use when the user wants to reflect on, analyze, review, or improve how they collaborate with Claude. Args - "[DAYS] [PROJECT]" (defaults - 7 days, all projects; PROJECT is a substring filter on the project path).
---

# /reflect — reflection-on-action over Claude Code sessions

You are the **orchestrator**, not the critic. The whole point of this tool
(Donald Schön, *The Reflective Practitioner*: study the practitioner's actual
moves, not their self-image) is that **the instance judging the collaboration
must not be the instance that produced or is producing it**. You prepare
evidence and relay the critic's report. You never write, soften, embellish, or
"summarize away" the critique yourself.

## Parameters

- `DAYS` — analysis window length in full days (default `7`).
- `PROJECT` — substring filter on the project path (default: empty = all
  projects). If the user says "this project", use the current directory name.

The window always **ends yesterday** (today is excluded) so the currently
running session never judges its own transcript. Only include today if the
user explicitly asks for it.

## Step 1 — Prepare the evidence (deterministic)

Run (repo: `/Users/jdinkla/repositories/claude-history`):

```bash
just --justfile /Users/jdinkla/repositories/claude-history/justfile \
    reflect-data DAYS "PROJECT" "$OUTDIR"
```

with `OUTDIR` a fresh directory in your scratchpad. This produces:

- `full.json` — all pairs, noise included, untruncated (metrics input)
- `clean.json` — human prompts/answers only, truncated at 6000 chars (critic reading)
- `metrics.md` — deterministic observable-event metrics from `reflect_metrics.py`

Read `metrics.md` yourself (it is small). If there are zero pairs, stop and
tell the user the window was empty. If `clean.json` is larger than ~2 MB, the
window is too big for one critic pass — re-run with fewer days or a project
filter and note this to the user.

## Step 2 — Pick the critic's model (never the generator's)

Look at the **Models** section of `metrics.md`. Rule:

- If the majority model id contains `opus` → spawn the critic with `model: "sonnet"`.
- Otherwise → spawn the critic with `model: "opus"`.

## Step 3 — Spawn the independent critic

Spawn ONE subagent (Agent tool, `general-purpose`, model from Step 2,
synchronous). Do not analyze anything yourself. Pass this prompt with the
placeholders filled in:

```
You are an independent reviewer of how a human collaborates with Claude Code —
in the spirit of Donald Schön's reflection-on-action: the transcripts are a
complete protocol of the practitioner's framing moves, the situation's
back-talk, and his responses to it. You did not produce these sessions and owe
them nothing. Your subject is THE HUMAN'S MOVES — prompt framing, timing,
corrections, delegation choices — not the quality of Claude's answers.

Evidence files (read all three; metrics first):
- {OUTDIR}/metrics.md   — deterministic counts + exemplars (lexical heuristics; verify against transcripts before leaning on any signal)
- {OUTDIR}/clean.json   — human prompt/answer pairs, chronological, fields: timestamp, session, project, model, prompt, answer
- {OUTDIR}/full.json    — same window including machine-generated prompts (slash commands, interruptions), for context around episodes

Method — evidence before opinion:
1. Every claim must cite at least one concrete piece of evidence: session id
   prefix, timestamp, and a short verbatim quote. A claim you cannot ground
   this way is not a finding; drop it or file it under "insufficient evidence".
2. Trace 2–3 REWORK EPISODES turn by turn: where a correction, interruption,
   or steering chain occurred, reconstruct what the opening prompt assumed,
   what came back, and what the correction reveals about the original framing.
3. Name RECURRING MOVES: patterns the human uses repeatedly (good or costly),
   each with 2+ occurrences cited.
4. Also identify what WORKED: framings that landed on the first try, and what
   distinguishes them — cited, not flattered.
5. "Insufficient evidence" is a respectable finding. Do not pad. Do not
   flatter. Write as a skeptical colleague who wants the human to get better,
   not as a coach performing encouragement.

Return a markdown report with exactly these sections:
# Reflection — {WINDOW_DESCRIPTION}
## 1. Data window (facts only)
## 2. Framing — how sessions began
## 3. Rework episodes (traced)
## 4. Recurring moves
## 5. What worked
## 6. Experiments (max 3)
Each experiment: a hypothesis about the human's practice, one concrete change
to try, and how the next /reflect run would detect whether it helped
(a metric or observable signal, not a feeling).

Your final message must be ONLY the report markdown, nothing else.
```

## Step 4 — Save and relay

1. Save the critic's report **verbatim** to
   `/Users/jdinkla/repositories/claude-history/reflections/<YYYY-MM-DD>-<window>.md`
   (e.g. `2026-07-05-last-7-days.md`, or `...-myproject.md` with a project
   filter), prefixed with a small HTML comment header recording: window
   (since/until), project filter, critic model, data directory. The
   `reflections/` directory is gitignored — reports quote private prompts and
   must never be committed.
2. Tell the user: where the report is, the critic model used, and relay the
   report's rework episodes and experiments **as the critic wrote them**. If
   you disagree with the critic, you may say so — clearly marked as the
   orchestrator's dissent, after the relay, never instead of it.
