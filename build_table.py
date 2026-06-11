#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
from __future__ import annotations

import json
import sys
from pathlib import Path

HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>__TITLE__</title>
    <style>
        :root {
            --bg: #f5f1ee;
            --fg: #1a1a1a;
            --muted: #888;
            --border: #d0ccc8;
            --card: #fff;
            --accent: #0066cc;
        }

        @media (prefers-color-scheme: dark) {
            :root {
                --bg: #1a1a1a;
                --fg: #e8e8e8;
                --muted: #888;
                --border: #444;
                --card: #2a2a2a;
                --accent: #66b3ff;
            }
        }

        * {
            box-sizing: border-box;
        }

        html, body {
            margin: 0;
            padding: 0;
            background-color: var(--bg);
            color: var(--fg);
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
            line-height: 1.5;
        }

        body {
            color-scheme: light dark;
        }

        h1 {
            margin: 0 0 0.5rem 0;
            font-size: 1.5rem;
        }

        main {
            max-width: 100%;
            padding: 2rem;
        }

        table {
            width: 100%;
            border-collapse: collapse;
            background-color: var(--card);
            border: 1px solid var(--border);
            margin-top: 1rem;
        }

        thead {
            position: sticky;
            top: 0;
            background-color: var(--card);
            border-bottom: 2px solid var(--border);
        }

        th {
            padding: 0.75rem;
            text-align: left;
            font-weight: 600;
            color: var(--fg);
            border-right: 1px solid var(--border);
        }

        th:last-child {
            border-right: none;
        }

        td {
            padding: 0.75rem;
            border-right: 1px solid var(--border);
            word-break: break-word;
            white-space: pre-wrap;
        }

        td:last-child {
            border-right: none;
        }

        tbody tr {
            border-bottom: 1px solid var(--border);
        }

        tbody tr:hover {
            background-color: rgba(0, 102, 204, 0.05);
        }

        .answer-preview {
            display: block;
            white-space: normal;
        }

        .answer-full {
            display: none;
        }

        tr.expanded .answer-preview {
            display: none;
        }

        tr.expanded .answer-full {
            display: block;
        }

        .toggle-btn {
            background-color: var(--accent);
            color: #fff;
            border: none;
            padding: 0.25rem 0.5rem;
            border-radius: 3px;
            cursor: pointer;
            font-size: 0.875rem;
            margin-top: 0.5rem;
        }

        .toggle-btn:hover {
            opacity: 0.9;
        }

        #meta {
            color: var(--muted);
            font-size: 0.9rem;
            margin-top: 0.5rem;
        }
    </style>
</head>
<body>
    <main>
        <h1>__TITLE__</h1>
        <div id="meta"></div>
        <table>
            <thead>
                <tr>
                    <th>Model</th>
                    <th>Prompt</th>
                    <th>Answer</th>
                </tr>
            </thead>
            <tbody id="rows">
            </tbody>
        </table>
    </main>

    <script>
        const DATA = __DATA__;

        function escapeHtml(str) {
            if (!str) return "";
            const map = {
                "&": "&amp;",
                "<": "&lt;",
                ">": "&gt;"
            };
            return str.replace(/[&<>]/g, c => map[c]);
        }

        function renderRows() {
            const tbody = document.getElementById("rows");
            tbody.innerHTML = "";

            DATA.forEach((pair, idx) => {
                const model = pair.model || "";
                const prompt = pair.prompt || "";
                const answer = pair.answer || "";

                const isLong = answer.length > 80;
                const preview = isLong ? answer.substring(0, 80) + "..." : answer;

                const row = document.createElement("tr");
                row.dataset.idx = idx;

                row.innerHTML = `
                    <td>${escapeHtml(model)}</td>
                    <td>${escapeHtml(prompt)}</td>
                    <td>
                        <span class="answer-preview">${escapeHtml(preview)}</span>
                        <span class="answer-full">${escapeHtml(answer)}</span>
                        ${isLong ? `<button class="toggle-btn" onclick="toggleRow(${idx})">Show more</button>` : ""}
                    </td>
                </tr>
                `;
                tbody.appendChild(row);
            });

            const meta = document.getElementById("meta");
            const count = DATA.length;
            meta.textContent = `${count} entr${count === 1 ? "y" : "ies"}`;
        }

        function toggleRow(idx) {
            const row = document.querySelector(`tr[data-idx="${idx}"]`);
            const btn = row.querySelector(".toggle-btn");
            if (row.classList.contains("expanded")) {
                row.classList.remove("expanded");
                btn.textContent = "Show more";
            } else {
                row.classList.add("expanded");
                btn.textContent = "Show less";
            }
        }

        renderRows();
    </script>
</body>
</html>
"""


def main(argv: list[str]) -> int:
    """
    Render an HTML table from a JSON pairs file.

    Usage: build_table.py [SRC.json] [DST.html]
    SRC defaults to last_8_days_backend_no_noise.json
    DST defaults to SRC with .html suffix
    """
    # Parse arguments
    src = argv[0] if len(argv) > 0 else "last_8_days_backend_no_noise.json"

    src_path = Path(src)
    if dst := (argv[1] if len(argv) > 1 else None):
        dst_path = Path(dst)
    else:
        dst_path = src_path.with_suffix(".html")

    # Read JSON pairs
    try:
        with open(src_path, "r", encoding="utf-8") as f:
            pairs = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError) as e:
        print(f"Error reading {src_path}: {e}", file=sys.stderr)
        return 1

    # Map to {model, prompt, answer}
    rows = []
    for pair in pairs:
        rows.append({
            "model": pair.get("model") or "",
            "prompt": pair.get("prompt") or "",
            "answer": pair.get("answer") or "",
        })

    # Embed JSON into template
    data_json = json.dumps(rows, ensure_ascii=False).replace("</", "<\\/")
    title = f"Claude Code history table — {len(rows)} rows"
    html = (HTML_TEMPLATE
            .replace("__TITLE__", title.replace("<", "&lt;"))
            .replace("__DATA__", data_json))

    # Write HTML
    with open(dst_path, "w", encoding="utf-8") as f:
        f.write(html)

    # Print result
    file_bytes = dst_path.stat().st_size
    print(f"wrote {dst_path} ({len(rows)} rows, {file_bytes} bytes)")

    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
