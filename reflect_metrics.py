#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Compute observable collaboration metrics from claude_history pairs JSON.

Consumes the output of `claude_history.py --format json` (run WITHOUT
--no-noise, so machine-generated prompts are still present) and reports
deterministic, countable events: sessions, prompt shape, correction signals,
interruptions, slash-command usage, model distribution.

The point is methodological: an LLM critic reviewing collaboration transcripts
should argue from observable events, not vibes. This script provides those
events. All signal detectors are heuristics and are labeled as such.
"""

from __future__ import annotations

import argparse
import json
import re
import statistics
import sys
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

# ---------------------------------------------------------------------------
# Noise classification (mirrors claude_history.NOISE_PATTERNS, but named)
# ---------------------------------------------------------------------------

NOISE_KINDS: list[tuple[str, re.Pattern[str]]] = [
    ("slash_command", re.compile(r"<command-(?:name|message|args)>.*?</command-(?:name|message|args)>", re.DOTALL)),
    ("interruption", re.compile(r"\[Request interrupted by user.*?\]", re.DOTALL)),
    ("local_command", re.compile(r"<local-command-(?:stdout|caveat)>.*?</local-command-(?:stdout|caveat)>", re.DOTALL)),
    ("context_dump", re.compile(r"##\s*Context Usage\b.*", re.DOTALL)),
]

INTERRUPTION_RE = re.compile(r"\[Request interrupted by user.*?\]", re.DOTALL)
COMMAND_NAME_RE = re.compile(r"<command-name>\s*(.*?)\s*</command-name>", re.DOTALL)

# Correction lexicon: start-anchored, high-precision heuristics for prompts
# that push back on the previous answer. English + German.
CORRECTION_RES: list[re.Pattern[str]] = [
    re.compile(r"^(no|nope|nah)\b", re.IGNORECASE),
    re.compile(r"^(not|don'?t)\b", re.IGNORECASE),
    re.compile(r"^wrong\b", re.IGNORECASE),
    re.compile(r"^(stop|wait|halt)\b", re.IGNORECASE),
    re.compile(r"^actually\b", re.IGNORECASE),
    re.compile(r"^(undo|revert)\b", re.IGNORECASE),
    re.compile(r"^(that'?s|that is|this is) not\b", re.IGNORECASE),
    re.compile(r"^instead\b", re.IGNORECASE),
    re.compile(r"\bi (meant|didn'?t mean)\b", re.IGNORECASE),
    re.compile(r"^(nein|falsch|nicht|stopp)\b", re.IGNORECASE),
]

STEERING_MAX_CHARS = 100
EXEMPLAR_CHARS = 120


def classify_prompt(text: str | None) -> str:
    """Classify a pair's prompt as human or one of the machine-noise kinds."""
    if text is None:
        return "assistant_only"
    residue = text
    hits: list[str] = []
    for kind, pattern in NOISE_KINDS:
        if pattern.search(residue):
            hits.append(kind)
            residue = pattern.sub(" ", residue)
    if hits and not residue.strip():
        return hits[0]
    return "human"


def is_correction(text: str) -> bool:
    stripped = text.strip()
    return any(p.search(stripped) for p in CORRECTION_RES)


def slash_command_name(text: str) -> str | None:
    m = COMMAND_NAME_RE.search(text)
    return m.group(1) if m else None


# ---------------------------------------------------------------------------
# Metrics computation
# ---------------------------------------------------------------------------

def exemplar(pair: dict, text: str) -> dict:
    snippet = " ".join(text.split())
    if len(snippet) > EXEMPLAR_CHARS:
        snippet = snippet[:EXEMPLAR_CHARS].rstrip() + "…"
    return {
        "session": (pair.get("session") or "")[:8],
        "timestamp": pair.get("timestamp") or pair.get("answer_timestamp"),
        "text": snippet,
    }


@dataclass
class SessionStats:
    session: str
    project: str
    timestamps: list[str] = field(default_factory=list)
    pairs: int = 0
    human_prompts: int = 0
    corrections: int = 0
    interruptions: int = 0
    first_prompt_chars: int | None = None


def compute_metrics(pairs: list[dict], max_exemplars: int = 10) -> dict:
    sessions: dict[str, SessionStats] = {}
    models: Counter[str] = Counter()
    projects: Counter[str] = Counter()
    prompt_kinds: Counter[str] = Counter()
    slash_commands: Counter[str] = Counter()

    human_lengths: list[int] = []
    corrections: list[dict] = []
    interruptions: list[dict] = []
    steering: list[dict] = []
    assistant_questions: list[dict] = []
    human_followups = 0

    for pair in pairs:
        sid = pair.get("session") or "?"
        project = pair.get("project") or "?"
        stats = sessions.setdefault(sid, SessionStats(session=sid, project=project))
        stats.pairs += 1
        projects[project] += 1
        if pair.get("model"):
            models[pair["model"]] += 1
        ts = pair.get("timestamp") or pair.get("answer_timestamp")
        if ts:
            stats.timestamps.append(ts)

        prompt = pair.get("prompt")
        kind = classify_prompt(prompt)
        prompt_kinds[kind] += 1

        if prompt and INTERRUPTION_RE.search(prompt):
            stats.interruptions += 1
            interruptions.append(exemplar(pair, prompt))

        if kind == "slash_command":
            slash_commands[slash_command_name(prompt) or "?"] += 1
        elif kind == "human":
            stats.human_prompts += 1
            human_lengths.append(len(prompt))
            if stats.human_prompts == 1:
                stats.first_prompt_chars = len(prompt)
            else:
                human_followups += 1
                if len(prompt) < STEERING_MAX_CHARS:
                    steering.append(exemplar(pair, prompt))
            if is_correction(prompt):
                stats.corrections += 1
                corrections.append(exemplar(pair, prompt))

        answer = pair.get("answer") or ""
        if answer.rstrip().endswith("?"):
            assistant_questions.append(exemplar(pair, answer.rstrip()[-EXEMPLAR_CHARS:]))

    all_ts = sorted(t for s in sessions.values() for t in s.timestamps)
    first_prompt_lengths = [
        s.first_prompt_chars for s in sessions.values() if s.first_prompt_chars is not None
    ]

    def length_stats(values: list[int]) -> dict:
        if not values:
            return {"count": 0, "mean": None, "median": None, "max": None}
        return {
            "count": len(values),
            "mean": round(statistics.mean(values), 1),
            "median": statistics.median(values),
            "max": max(values),
        }

    session_rows = []
    for s in sorted(sessions.values(), key=lambda s: s.timestamps[0] if s.timestamps else ""):
        duration_min = None
        if len(s.timestamps) >= 2:
            t0, t1 = parse_iso(s.timestamps[0]), parse_iso(s.timestamps[-1])
            if t0 and t1:
                duration_min = round((t1 - t0).total_seconds() / 60, 1)
        session_rows.append({
            "session": s.session[:8],
            "project": s.project,
            "start": s.timestamps[0] if s.timestamps else None,
            "duration_min": duration_min,
            "pairs": s.pairs,
            "human_prompts": s.human_prompts,
            "corrections": s.corrections,
            "interruptions": s.interruptions,
            "first_prompt_chars": s.first_prompt_chars,
        })

    return {
        "window": {
            "first": all_ts[0] if all_ts else None,
            "last": all_ts[-1] if all_ts else None,
        },
        "totals": {
            "pairs": len(pairs),
            "sessions": len(sessions),
            "projects": len(projects),
            "prompt_kinds": dict(prompt_kinds),
        },
        "models": dict(models.most_common()),
        "projects": dict(projects.most_common()),
        "sessions": session_rows,
        "prompt_length": {
            "human": length_stats(human_lengths),
            "first_prompt": length_stats(first_prompt_lengths),
        },
        "signals": {
            "corrections": {
                "count": len(corrections),
                "exemplars": corrections[:max_exemplars],
            },
            "interruptions": {
                "count": len(interruptions),
                "exemplars": interruptions[:max_exemplars],
            },
            "steering_followups": {
                "count": len(steering),
                "of_followups": human_followups,
                "exemplars": steering[:max_exemplars],
            },
            "assistant_questions": {
                "count": len(assistant_questions),
                "exemplars": assistant_questions[:max_exemplars],
            },
            "slash_commands": {
                "count": sum(slash_commands.values()),
                "by_command": dict(slash_commands.most_common()),
            },
        },
    }


def parse_iso(s: str) -> datetime | None:
    try:
        return datetime.fromisoformat(s)
    except (ValueError, TypeError):
        return None


# ---------------------------------------------------------------------------
# Markdown rendering
# ---------------------------------------------------------------------------

def fmt_ts(iso: str | None) -> str:
    dt = parse_iso(iso) if iso else None
    return dt.strftime("%Y-%m-%d %H:%M") if dt else "—"


def render_exemplars(items: list[dict]) -> list[str]:
    return [
        f"- `{e['session']}` {fmt_ts(e['timestamp'])} — “{e['text']}”"
        for e in items
    ]


def render_markdown(m: dict) -> str:
    out: list[str] = []
    out.append(f"# Collaboration metrics — {fmt_ts(m['window']['first'])} → {fmt_ts(m['window']['last'])}")
    out.append("")

    t = m["totals"]
    kinds = t["prompt_kinds"]
    out.append("## Totals")
    out.append("")
    out.append(f"- Pairs: **{t['pairs']}** across **{t['sessions']}** sessions in **{t['projects']}** projects")
    out.append(f"- Human prompts: **{kinds.get('human', 0)}** — machine: "
               + ", ".join(f"{k} {v}" for k, v in sorted(kinds.items()) if k != "human"))
    out.append("")

    out.append("## Models (answers per model)")
    out.append("")
    for model, count in m["models"].items():
        out.append(f"- `{model}`: {count}")
    out.append("")

    out.append("## Projects")
    out.append("")
    for project, count in m["projects"].items():
        out.append(f"- `{project}`: {count} pairs")
    out.append("")

    out.append("## Sessions")
    out.append("")
    out.append("| Session | Project | Start | Min | Pairs | Human | Corr. | Intr. | 1st prompt chars |")
    out.append("|---|---|---|---|---|---|---|---|---|")
    for s in m["sessions"]:
        project_short = (s["project"] or "?").rsplit("/", 1)[-1]
        out.append(
            f"| `{s['session']}` | {project_short} | {fmt_ts(s['start'])} "
            f"| {s['duration_min'] if s['duration_min'] is not None else '—'} "
            f"| {s['pairs']} | {s['human_prompts']} | {s['corrections']} "
            f"| {s['interruptions']} | {s['first_prompt_chars'] if s['first_prompt_chars'] is not None else '—'} |"
        )
    out.append("")

    pl = m["prompt_length"]
    out.append("## Prompt shape")
    out.append("")
    out.append(f"- Human prompt chars: mean {pl['human']['mean']}, median {pl['human']['median']}, max {pl['human']['max']} (n={pl['human']['count']})")
    out.append(f"- First prompt per session: median {pl['first_prompt']['median']} chars (n={pl['first_prompt']['count']}) — framing investment at session start")
    out.append("")

    sig = m["signals"]
    out.append(f"## Correction signals ({sig['corrections']['count']})")
    out.append("")
    out.append("Human prompts opening with pushback (no / wrong / stop / actually / i meant / nein / …).")
    out.append("")
    out.extend(render_exemplars(sig["corrections"]["exemplars"]) or ["(none)"])
    out.append("")

    out.append(f"## Interruptions ({sig['interruptions']['count']})")
    out.append("")
    out.append("The user hit Escape while Claude was working.")
    out.append("")
    out.extend(render_exemplars(sig["interruptions"]["exemplars"]) or ["(none)"])
    out.append("")

    st = sig["steering_followups"]
    ratio = f" ({round(100 * st['count'] / st['of_followups'])}% of follow-ups)" if st["of_followups"] else ""
    out.append(f"## Short steering follow-ups ({st['count']}{ratio})")
    out.append("")
    out.append(f"Follow-up prompts under {STEERING_MAX_CHARS} chars — course corrections that may indicate an under-specified opening.")
    out.append("")
    out.extend(render_exemplars(st["exemplars"]) or ["(none)"])
    out.append("")

    aq = sig["assistant_questions"]
    out.append(f"## Assistant ended on a question ({aq['count']})")
    out.append("")
    out.append("Turns where Claude needed input — potential under-specification upstream.")
    out.append("")
    out.extend(render_exemplars(aq["exemplars"]) or ["(none)"])
    out.append("")

    sc = sig["slash_commands"]
    out.append(f"## Slash commands ({sc['count']})")
    out.append("")
    for cmd, count in sc["by_command"].items():
        out.append(f"- `{cmd}`: {count}")
    if not sc["by_command"]:
        out.append("(none)")
    out.append("")

    out.append("## Method notes")
    out.append("")
    out.append("All signals are lexical heuristics over prompt/answer text; counts are lower/upper bounds, not truth. "
               "Corrections are start-anchored pushback phrases; steering is a length threshold; "
               "assistant questions match a trailing `?`. Use exemplars to check each signal before trusting it.")
    out.append("")
    return "\n".join(out)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("src", nargs="?", default="-",
                    help="Pairs JSON file from claude_history.py --format json (default: stdin).")
    ap.add_argument("--format", choices=["md", "json"], default="md",
                    help="Output format (default: md).")
    ap.add_argument("--exemplars", type=int, default=10,
                    help="Max exemplars per signal (default: 10).")
    args = ap.parse_args(argv)

    if args.src == "-":
        pairs = json.load(sys.stdin)
    else:
        pairs = json.loads(Path(args.src).read_text(encoding="utf-8"))
    if not isinstance(pairs, list):
        print("error: input must be a JSON array of pairs", file=sys.stderr)
        return 1

    metrics = compute_metrics(pairs, max_exemplars=args.exemplars)
    if args.format == "json":
        json.dump(metrics, sys.stdout, ensure_ascii=False, indent=2)
        sys.stdout.write("\n")
    else:
        sys.stdout.write(render_markdown(metrics))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
