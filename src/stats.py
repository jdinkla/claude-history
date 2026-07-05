#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Aggregate Claude Code prompt/answer pairs into usage statistics.

Consumes the output of `claude_history.py --format json` — run WITHOUT
--no-noise and WITH --max-chars 0, see specs/STATISTICS.md §2 — and emits
either a deterministic aggregates JSON object or a self-contained HTML
page: prompt counts per project, day, weekday, and hour, plus model
breakdown and per-session distribution.
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
from collections import Counter
from datetime import date, datetime, timedelta

from reflect_metrics import classify_prompt

WEEKDAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
KINDS = ["human", "slash_command", "interruption", "local_command",
         "context_dump", "assistant_only"]
NO_MODEL = "(none)"

# ---------------------------------------------------------------------------
# Aggregation
# ---------------------------------------------------------------------------

def _parse_ts(s: str | None) -> datetime | None:
    if not s:
        return None
    try:
        return datetime.fromisoformat(s)
    except ValueError:
        return None


def _dist(values: list[int]) -> dict:
    if not values:
        return {"min": 0, "median": 0, "mean": 0.0, "max": 0}
    return {
        "min": min(values),
        "median": statistics.median(values),
        "mean": round(statistics.mean(values), 1),
        "max": max(values),
    }


def compute_stats(pairs: list[dict], top_n: int = 10) -> dict:
    kinds = {k: 0 for k in KINDS}
    projects: dict[str, dict] = {}
    sessions: dict[str, dict] = {}
    day_pairs: Counter[str] = Counter()
    day_human: Counter[str] = Counter()
    wd_pairs: Counter[int] = Counter()
    wd_human: Counter[int] = Counter()
    hr_pairs: Counter[int] = Counter()
    hr_human: Counter[int] = Counter()
    model_pairs: Counter[str] = Counter()
    ref_first: tuple[datetime, str] | None = None
    ref_last: tuple[datetime, str] | None = None

    for p in pairs:
        kind = classify_prompt(p.get("prompt"))
        kinds[kind] += 1
        human = 1 if kind == "human" else 0

        project = p.get("project") or ""
        session = p.get("session") or ""
        model = p.get("model") or NO_MODEL

        pr = projects.setdefault(
            project, {"pairs": 0, "human": 0, "sessions": set(), "models": Counter()})
        pr["pairs"] += 1
        pr["human"] += human
        pr["sessions"].add(session)
        pr["models"][model] += 1
        model_pairs[model] += 1

        se = sessions.setdefault(
            session, {"project": project, "pairs": 0, "human": 0, "ts": []})
        se["pairs"] += 1
        se["human"] += human
        for key in ("timestamp", "answer_timestamp"):
            dt = _parse_ts(p.get(key))
            if dt is not None:
                se["ts"].append((dt, p[key]))

        # Reference timestamp: prompt time, falling back to the answer time
        # (assistant-only pairs). Date/weekday/hour come from the local time
        # as written in the string — no re-conversion (spec §4).
        ref = _parse_ts(p.get("timestamp"))
        ref_iso = p.get("timestamp")
        if ref is None:
            ref = _parse_ts(p.get("answer_timestamp"))
            ref_iso = p.get("answer_timestamp")
        if ref is None:
            continue
        if ref_first is None or ref < ref_first[0]:
            ref_first = (ref, ref_iso)
        if ref_last is None or ref > ref_last[0]:
            ref_last = (ref, ref_iso)
        d = ref.date().isoformat()
        day_pairs[d] += 1
        day_human[d] += human
        wd_pairs[ref.weekday()] += 1
        wd_human[ref.weekday()] += human
        hr_pairs[ref.hour] += 1
        hr_human[ref.hour] += human

    by_project = [
        {"project": name, "pairs": pr["pairs"], "human": pr["human"],
         "sessions": len(pr["sessions"]),
         "models": dict(sorted(pr["models"].items()))}
        for name, pr in projects.items()
    ]
    by_project.sort(key=lambda r: (-r["human"], -r["pairs"], r["project"]))

    by_day = []
    if day_pairs:
        d = date.fromisoformat(min(day_pairs))
        last = date.fromisoformat(max(day_pairs))
        while d <= last:
            key = d.isoformat()
            by_day.append(
                {"date": key, "pairs": day_pairs[key], "human": day_human[key]})
            d += timedelta(days=1)

    by_weekday = [
        {"weekday": WEEKDAYS[i], "pairs": wd_pairs[i], "human": wd_human[i]}
        for i in range(7)
    ]
    by_hour = [
        {"hour": h, "pairs": hr_pairs[h], "human": hr_human[h]}
        for h in range(24)
    ]

    by_model = [{"model": m, "pairs": n} for m, n in model_pairs.items()]
    by_model.sort(key=lambda r: (-r["pairs"], r["model"]))

    top = []
    for sid, se in sessions.items():
        ts = sorted(se["ts"])
        first = ts[0] if ts else None
        last = ts[-1] if ts else None
        duration = int(round((last[0] - first[0]).total_seconds() / 60)) if ts else 0
        top.append({
            "session": sid,
            "project": se["project"],
            "first": first[1] if first else None,
            "last": last[1] if last else None,
            "duration_minutes": duration,
            "pairs": se["pairs"],
            "human": se["human"],
            "_sort": first[0].timestamp() if first else float("inf"),
        })
    top.sort(key=lambda r: (-r["human"], -r["pairs"], r["_sort"]))
    top = top[:max(top_n, 0)]
    for row in top:
        del row["_sort"]

    return {
        "range": {
            "first": ref_first[1] if ref_first else None,
            "last": ref_last[1] if ref_last else None,
        },
        "totals": {
            "pairs": len(pairs),
            "human": kinds["human"],
            "kinds": kinds,
            "sessions": len(sessions),
            "projects": len(projects),
            "active_days": len(day_pairs),
        },
        "by_project": by_project,
        "by_day": by_day,
        "by_weekday": by_weekday,
        "by_hour": by_hour,
        "by_model": by_model,
        "sessions": {
            "per_session_pairs": _dist([s["pairs"] for s in sessions.values()]),
            "per_session_human": _dist([s["human"] for s in sessions.values()]),
            "top": top,
        },
    }

# ---------------------------------------------------------------------------
# HTML rendering
# ---------------------------------------------------------------------------

HTML_TEMPLATE = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>__TITLE__</title>
<style>
:root {
  color-scheme: light dark;
  --bg: #f9f9f7;
  --card: #fcfcfb;
  --fg: #0b0b0b;
  --fg2: #52514e;
  --muted: #898781;
  --grid: #e1e0d9;
  --axis: #c3c2b7;
  --border: rgba(11, 11, 11, 0.10);
  --s1: #2a78d6;   /* human prompts */
  --s2: #1baf7a;   /* machine noise */
  --track: #cde2fb;
}
@media (prefers-color-scheme: dark) {
  :root {
    --bg: #0d0d0d;
    --card: #1a1a19;
    --fg: #ffffff;
    --fg2: #c3c2b7;
    --muted: #898781;
    --grid: #2c2c2a;
    --axis: #383835;
    --border: rgba(255, 255, 255, 0.10);
    --s1: #3987e5;
    --s2: #199e70;
    --track: #184f95;
  }
}
* { box-sizing: border-box; }
body {
  margin: 0;
  padding: 1.25rem;
  font-family: system-ui, -apple-system, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
  background: var(--bg);
  color: var(--fg);
}
main { max-width: 1060px; margin: 0 auto; }
h1 { font-size: 1.25rem; margin: 0 0 0.15rem; }
h2 { font-size: 0.9rem; margin: 0 0 0.6rem; font-weight: 600; }
.sub { color: var(--fg2); font-size: 0.8rem; margin-bottom: 1.1rem; }
.card {
  background: var(--card);
  border: 1px solid var(--border);
  border-radius: 10px;
  padding: 0.9rem 1rem;
  margin-bottom: 1rem;
}
.tiles {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(130px, 1fr));
  gap: 0.75rem;
  margin-bottom: 1rem;
}
.tile {
  background: var(--card);
  border: 1px solid var(--border);
  border-radius: 10px;
  padding: 0.7rem 0.85rem;
}
.tile .label { font-size: 0.72rem; color: var(--fg2); margin-bottom: 0.2rem; }
.tile .value { font-size: 1.45rem; font-weight: 600; }
.legend { display: flex; gap: 1rem; font-size: 0.78rem; color: var(--fg2); margin-bottom: 0.5rem; }
.legend .key { display: inline-flex; align-items: center; gap: 0.4rem; }
.legend .swatch { width: 12px; height: 12px; border-radius: 2px; display: inline-block; }
svg.chart { width: 100%; height: auto; display: block; }
svg.chart text { font-family: inherit; font-size: 10px; fill: var(--muted); font-variant-numeric: tabular-nums; }
.col rect.seg, .col path.seg { transition: filter 80ms; }
.col.hot rect.seg, .col.hot path.seg { filter: brightness(1.12); }
.hit { fill: transparent; outline: none; }
.hit:focus-visible { stroke: var(--s1); stroke-width: 1; }
#tip {
  position: fixed;
  display: none;
  background: var(--card);
  border: 1px solid var(--border);
  border-radius: 8px;
  box-shadow: 0 2px 10px rgba(0, 0, 0, 0.12);
  padding: 0.45rem 0.6rem;
  font-size: 0.75rem;
  pointer-events: none;
  z-index: 10;
  min-width: 130px;
}
#tip .t { color: var(--fg2); margin-bottom: 0.25rem; }
#tip .row { display: flex; align-items: center; gap: 0.4rem; margin-top: 0.12rem; }
#tip .lk { width: 10px; height: 3px; border-radius: 1.5px; display: inline-block; }
#tip .v { font-weight: 600; font-variant-numeric: tabular-nums; }
#tip .n { color: var(--fg2); }
details.tv { margin-top: 0.5rem; font-size: 0.78rem; }
details.tv summary { color: var(--muted); cursor: pointer; }
table { border-collapse: collapse; width: 100%; font-size: 0.8rem; }
th, td { text-align: left; padding: 0.3rem 0.6rem 0.3rem 0; border-bottom: 1px solid var(--grid); }
th { color: var(--fg2); font-weight: 600; font-size: 0.72rem; }
td.num, th.num { text-align: right; font-variant-numeric: tabular-nums; }
td.mono { font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: 0.72rem; }
.meter { width: 120px; height: 8px; border-radius: 4px; background: var(--track); overflow: hidden; }
.meter > div { height: 100%; border-radius: 4px; background: var(--s1); }
.dist { color: var(--fg2); font-size: 0.78rem; margin-bottom: 0.6rem; }
.dist b { color: var(--fg); font-variant-numeric: tabular-nums; }
.empty { color: var(--fg2); font-size: 0.9rem; }
footer { color: var(--muted); font-size: 0.72rem; margin: 1.2rem 0 0.4rem; }
</style>
</head>
<body>
<main id="app"><h1>__TITLE__</h1><div class="sub" id="sub"></div></main>
<div id="tip" role="status"></div>
<script>
"use strict";
const DATA = __DATA__;

const app = document.getElementById("app");
const tip = document.getElementById("tip");
const fmt = n => n.toLocaleString("en-US");
const el = (tag, cls, text) => {
  const e = document.createElement(tag);
  if (cls) e.className = cls;
  if (text !== undefined) e.textContent = text;
  return e;
};
const SERIES = [
  { key: "human", name: "Human prompts", color: "var(--s1)" },
  { key: "machine", name: "Machine noise", color: "var(--s2)" },
];

function subtitle() {
  const r = DATA.range;
  if (!r.first) return "no data";
  return r.first.slice(0, 10) + " → " + r.last.slice(0, 10);
}
document.getElementById("sub").textContent = subtitle();

function tiles() {
  const t = DATA.totals;
  const wrap = el("div", "tiles");
  for (const [label, value] of [
    ["Prompt pairs", t.pairs], ["Human prompts", t.human],
    ["Sessions", t.sessions], ["Projects", t.projects],
    ["Active days", t.active_days],
  ]) {
    const tile = el("div", "tile");
    tile.appendChild(el("div", "label", label));
    tile.appendChild(el("div", "value", fmt(value)));
    wrap.appendChild(tile);
  }
  app.appendChild(wrap);
}

function niceStep(raw) {
  const mag = Math.pow(10, Math.floor(Math.log10(raw)));
  for (const m of [1, 2, 5, 10]) if (raw <= m * mag) return m * mag;
  return 10 * mag;
}

function showTip(evt, title, rows) {
  tip.textContent = "";
  tip.appendChild(el("div", "t", title));
  for (const [color, value, name] of rows) {
    const row = el("div", "row");
    const lk = el("span", "lk");
    lk.style.background = color;
    row.appendChild(lk);
    row.appendChild(el("span", "v", fmt(value)));
    row.appendChild(el("span", "n", name));
    tip.appendChild(row);
  }
  tip.style.display = "block";
  const r = tip.getBoundingClientRect();
  let x = evt.clientX + 12, y = evt.clientY - r.height - 10;
  if (evt.clientX === undefined) { x = 20; y = 20; }
  if (x + r.width > window.innerWidth - 8) x = evt.clientX - r.width - 12;
  if (y < 8) y = evt.clientY + 14;
  tip.style.left = x + "px";
  tip.style.top = y + "px";
}
const hideTip = () => { tip.style.display = "none"; };

// Stacked column chart: human (baseline, --s1) + machine noise (top, --s2).
// Marks per the dataviz specs: <=24px columns, 4px rounded top on the stack's
// top segment only, 2px surface gap carved from the upper segment.
function columnChart(title, rows, xEvery) {
  const card = el("div", "card");
  card.appendChild(el("h2", null, title));
  const legend = el("div", "legend");
  for (const s of SERIES) {
    const key = el("span", "key");
    const sw = el("span", "swatch");
    sw.style.background = s.color;
    key.appendChild(sw);
    key.appendChild(document.createTextNode(s.name));
    legend.appendChild(key);
  }
  card.appendChild(legend);

  const W = 960, H = 240, L = 44, R = 8, T = 8, B = 22;
  const iw = W - L - R, ih = H - T - B;
  const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  svg.setAttribute("viewBox", `0 0 ${W} ${H}`);
  svg.setAttribute("class", "chart");
  svg.setAttribute("role", "img");
  svg.setAttribute("aria-label", title);
  const ns = (tag, attrs) => {
    const n = document.createElementNS("http://www.w3.org/2000/svg", tag);
    for (const k in attrs) n.setAttribute(k, attrs[k]);
    return n;
  };

  const maxV = Math.max(1, ...rows.map(r => r.human + r.machine));
  const step = niceStep(maxV / 4);
  const yMax = Math.ceil(maxV / step) * step;
  const y = v => T + ih - (v / yMax) * ih;

  for (let v = 0; v <= yMax; v += step) {
    svg.appendChild(ns("line", {
      x1: L, x2: W - R, y1: y(v), y2: y(v),
      stroke: v === 0 ? "var(--axis)" : "var(--grid)", "stroke-width": 1,
    }));
    if (v > 0) {
      const t = ns("text", { x: L - 6, y: y(v) + 3, "text-anchor": "end" });
      t.textContent = fmt(v);
      svg.appendChild(t);
    }
  }

  const band = iw / rows.length;
  const bw = Math.min(24, band * 0.72);
  const roundedTop = (x, yTop, w, h) => {
    const r = Math.min(4, h, w / 2);
    return `M${x},${yTop + h} L${x},${yTop + r} Q${x},${yTop} ${x + r},${yTop} ` +
      `L${x + w - r},${yTop} Q${x + w},${yTop} ${x + w},${yTop + r} L${x + w},${yTop + h} Z`;
  };

  rows.forEach((row, i) => {
    const g = ns("g", { class: "col" });
    const x = L + i * band + (band - bw) / 2;
    const hH = (row.human / yMax) * ih;
    const mH = (row.machine / yMax) * ih;
    const base = T + ih;
    if (mH >= 0.5) {
      if (hH >= 0.5) {
        const r = ns("rect", { class: "seg", x, y: base - hH, width: bw, height: hH, fill: "var(--s1)" });
        g.appendChild(r);
      }
      const gap = hH >= 0.5 ? 2 : 0;
      const mDrawn = Math.max(mH - gap, 0.75);
      const p = ns("path", { class: "seg", d: roundedTop(x, base - hH - gap - mDrawn, bw, mDrawn), fill: "var(--s2)" });
      g.appendChild(p);
    } else if (hH >= 0.5) {
      g.appendChild(ns("path", { class: "seg", d: roundedTop(x, base - hH, bw, hH), fill: "var(--s1)" }));
    }
    const hit = ns("rect", { class: "hit", x: L + i * band, y: T, width: band, height: ih, tabindex: 0 });
    const rowsTip = [
      ["var(--s1)", row.human, "human"],
      ["var(--s2)", row.machine, "machine"],
      ["var(--axis)", row.human + row.machine, "total"],
    ];
    const show = evt => {
      g.classList.add("hot");
      showTip(evt.clientX === undefined ? { clientX: 20, clientY: 40 } : evt, row.label, rowsTip);
    };
    const hide = () => { g.classList.remove("hot"); hideTip(); };
    hit.addEventListener("pointermove", show);
    hit.addEventListener("pointerleave", hide);
    hit.addEventListener("focus", show);
    hit.addEventListener("blur", hide);
    g.appendChild(hit);
    svg.appendChild(g);

    if (i % xEvery === 0) {
      const t = ns("text", { x: L + i * band + band / 2, y: H - 7, "text-anchor": "middle" });
      t.textContent = row.short !== undefined ? row.short : row.label;
      svg.appendChild(t);
    }
  });
  card.appendChild(svg);

  const details = el("details", "tv");
  details.appendChild(el("summary", null, "View data"));
  const table = el("table");
  const thead = el("thead");
  const hr = el("tr");
  for (const h of ["", "Human", "Machine", "Total"]) {
    hr.appendChild(el("th", h ? "num" : null, h));
  }
  thead.appendChild(hr);
  table.appendChild(thead);
  const tbody = el("tbody");
  for (const row of rows) {
    const tr = el("tr");
    tr.appendChild(el("td", null, row.label));
    tr.appendChild(el("td", "num", fmt(row.human)));
    tr.appendChild(el("td", "num", fmt(row.machine)));
    tr.appendChild(el("td", "num", fmt(row.human + row.machine)));
    tbody.appendChild(tr);
  }
  table.appendChild(tbody);
  details.appendChild(table);
  card.appendChild(details);
  app.appendChild(card);
}

function tableCard(title, headers, rows, build) {
  const card = el("div", "card");
  card.appendChild(el("h2", null, title));
  const table = el("table");
  const thead = el("thead");
  const hr = el("tr");
  headers.forEach(([name, cls]) => hr.appendChild(el("th", cls, name)));
  thead.appendChild(hr);
  table.appendChild(thead);
  const tbody = el("tbody");
  rows.forEach(r => tbody.appendChild(build(r)));
  table.appendChild(tbody);
  card.appendChild(table);
  app.appendChild(card);
  return card;
}

function meterCell(value, max) {
  const td = el("td");
  const meter = el("div", "meter");
  const fill = el("div");
  fill.style.width = (max > 0 ? (value / max) * 100 : 0) + "%";
  meter.appendChild(fill);
  td.appendChild(meter);
  return td;
}

// Display projects with the common path prefix stripped: short, but unique
// (a bare last segment collides — e.g. two different ".../test" projects).
const commonPrefix = (() => {
  const paths = DATA.by_project.map(r => r.project.split("/"));
  if (paths.length < 2) return paths.length && paths[0].length > 1 ? paths[0].slice(0, -1).join("/") + "/" : "";
  let n = 0;
  while (paths.every(p => n < p.length - 1 && p[n] === paths[0][n])) n++;
  return n ? paths[0].slice(0, n).join("/") + "/" : "";
})();
const projName = p => p.startsWith(commonPrefix) && p !== commonPrefix ? p.slice(commonPrefix.length) : p;
const fmtDur = m => m >= 60 ? Math.floor(m / 60) + "h " + (m % 60) + "m" : m + "m";

function render() {
  tiles();
  if (DATA.totals.pairs === 0) {
    const card = el("div", "card");
    card.appendChild(el("div", "empty", "No data in this extraction window."));
    app.appendChild(card);
    return;
  }

  const mrow = r => ({ human: r.human, machine: r.pairs - r.human });
  columnChart("Prompts per day",
    DATA.by_day.map(r => ({ label: r.date, short: r.date.slice(5), ...mrow(r) })),
    Math.max(1, Math.ceil(DATA.by_day.length / 12)));
  columnChart("By weekday",
    DATA.by_weekday.map(r => ({ label: r.weekday, ...mrow(r) })), 1);
  columnChart("By hour of day",
    DATA.by_hour.map(r => ({ label: String(r.hour).padStart(2, "0") + ":00", short: String(r.hour), ...mrow(r) })), 3);

  const maxProjHuman = Math.max(1, ...DATA.by_project.map(r => r.human));
  tableCard("By project",
    [["Project"], ["Sessions", "num"], ["Human", "num"], ["All", "num"], ["", null]],
    DATA.by_project, r => {
      const tr = el("tr");
      const td = el("td", null, projName(r.project));
      td.title = r.project;
      tr.appendChild(td);
      tr.appendChild(el("td", "num", fmt(r.sessions)));
      tr.appendChild(el("td", "num", fmt(r.human)));
      tr.appendChild(el("td", "num", fmt(r.pairs)));
      tr.appendChild(meterCell(r.human, maxProjHuman));
      return tr;
    });

  const maxModel = Math.max(1, ...DATA.by_model.map(r => r.pairs));
  tableCard("By model",
    [["Model"], ["Pairs", "num"], ["", null]],
    DATA.by_model, r => {
      const tr = el("tr");
      tr.appendChild(el("td", null, r.model));
      tr.appendChild(el("td", "num", fmt(r.pairs)));
      tr.appendChild(meterCell(r.pairs, maxModel));
      return tr;
    });

  const s = DATA.sessions;
  const card = tableCard("Sessions — top " + s.top.length + " by human prompts",
    [["Session"], ["Project"], ["Started"], ["Duration", "num"], ["Human", "num"], ["All", "num"]],
    s.top, r => {
      const tr = el("tr");
      tr.appendChild(el("td", "mono", r.session.slice(0, 8)));
      const td = el("td", null, projName(r.project));
      td.title = r.project;
      tr.appendChild(td);
      tr.appendChild(el("td", null, r.first ? r.first.slice(0, 16).replace("T", " ") : "—"));
      tr.appendChild(el("td", "num", fmtDur(r.duration_minutes)));
      tr.appendChild(el("td", "num", fmt(r.human)));
      tr.appendChild(el("td", "num", fmt(r.pairs)));
      return tr;
    });
  const dist = el("div", "dist");
  const dh = s.per_session_human, dp = s.per_session_pairs;
  dist.append("Per session — human prompts: median ");
  dist.appendChild(el("b", null, String(dh.median)));
  dist.append(" · mean ");
  dist.appendChild(el("b", null, String(dh.mean)));
  dist.append(" · max ");
  dist.appendChild(el("b", null, String(dh.max)));
  dist.append(" — all pairs: median ");
  dist.appendChild(el("b", null, String(dp.median)));
  dist.append(" · max ");
  dist.appendChild(el("b", null, String(dp.max)));
  card.insertBefore(dist, card.children[1]);

  const foot = el("footer", null,
    "Counts include machine-generated prompts; “human” = prompts actually typed. " +
    "Times are local to the machine that recorded the sessions.");
  app.appendChild(foot);
}
render();
</script>
</body>
</html>
"""


def render_html(stats: dict, title: str) -> str:
    data_json = json.dumps(stats, ensure_ascii=False).replace("</", "<\\/")
    return (HTML_TEMPLATE
            .replace("__TITLE__", title.replace("<", "&lt;"))
            .replace("__DATA__", data_json))

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("src", nargs="?", default="-",
                    help="Pairs JSON file from claude_history.py --format json (default: stdin).")
    ap.add_argument("--format", choices=["json", "html"], default="json",
                    help="json = aggregates object (default); html = self-contained page.")
    ap.add_argument("--top", type=int, default=10,
                    help="Number of sessions in the top-sessions list (default: 10).")
    ap.add_argument("--title", default="Claude Code statistics",
                    help="HTML page title (ignored for --format json).")
    args = ap.parse_args(argv)

    if args.src == "-":
        pairs = json.load(sys.stdin)
    else:
        with open(args.src, "r", encoding="utf-8") as f:
            pairs = json.load(f)

    stats = compute_stats(pairs, top_n=args.top)

    if args.format == "json":
        json.dump(stats, sys.stdout, ensure_ascii=False, indent=2)
        sys.stdout.write("\n")
    else:
        sys.stdout.write(render_html(stats, args.title))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
