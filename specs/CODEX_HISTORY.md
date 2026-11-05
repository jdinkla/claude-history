# `codex-history`

Python 3.11+, standard library only. Install with `uv tool install --editable .`
to expose `codex-history` (`codex_history:main`) and `claude-history`
(`claude_history:main`). Both can be invoked independently of the working
directory. Direct execution via `python3 src/codex_history.py` or its uv
shebang is also supported.

## Inputs

Read `*.jsonl` recursively in `$CODEX_HOME/sessions`, then
`$CODEX_HOME/archived_sessions`, with paths sorted within each root.
`CODEX_HOME` defaults to `~/.codex`; a leading `~` is expanded. Missing roots
produce no entries. No transcript is modified. `history.jsonl` is not used
because it lacks complete assistant responses.

Read each file twice, first to discover session metadata and mirrored message
roles, then to extract entries. Ignore unreadable files, invalid JSON, non-object
records, and records without an object `payload`. Incomplete trailing JSON is
ignored so running sessions can be read.

- `session_meta.payload.id`, falling back to `session_id`, then the filename
  stem, identifies the session. Read each session once across both roots;
  the active copy wins over an archived copy.
- The initial project is `session_meta.payload.cwd`, or the empty string.
- `turn_context.payload.cwd` updates the project; `model` updates the model
  for following assistant messages. Unknown models are null.
- A `response_item` with `payload.type == "message"` contributes text only
  for roles `user` and `assistant`. Skip channels `analysis` and `summary`.
  Include assistant progress and final messages.
- Join non-empty string `text` values from `input_text`, `output_text`, and
  `text` content blocks with a newline, then strip whitespace. Ignore images
  and other content blocks. Skip messages without text.
- For user messages, always remove whole blocks matching
  `<environment_context>…</environment_context>`,
  `<permissions instructions>…</permissions instructions>`,
  `<external_codex_apps_open_page>…</external_codex_apps_open_page>`,
  `<turn_aborted>…</turn_aborted>`, or
  `<subagent_notification>…</subagent_notification>`, allowing surrounding
  whitespace. Also remove blocks whose left-stripped text starts with
  `# AGENTS.md instructions for `. Other text is retained.
- Older `event_msg` records of type `user_message` or `agent_message` supply
  their string `message` as user/assistant text only when the file has no
  `response_item` message of that role. This prevents counting mirrored records
  twice. `task_complete.last_agent_message` is ignored.
- Tools, reasoning, compaction summaries, and all other record types are ignored.
- Use the outer record's ISO `timestamp`, skipping absent/invalid values.
  Naive transcript timestamps are interpreted as UTC.
- Filter entries using the shared inclusive `since`, exclusive `until`, and
  case-sensitive project substring rules. `--no-noise` additionally applies
  Claude's noise patterns to user text. Strip retained text before emitting it.

## CLI and output

All arguments, local date semantics, sorting, per-session pairing, truncation,
output schemas and text/Markdown rendering follow `SPECIFICATION.md`. In
particular `--days 2` starts at local midnight yesterday, not 48 hours ago.
Default output is text for today. `--format` supports `text`, `md`, `jsonl`,
`json`, `html`; `--json` and `--html` remain shortcuts. Empty machine-readable
output remains valid. HTML titles start with `Codex history — since `.

`--day YYYY-MM-DD` selects exactly that local calendar day; `--day 0` selects
today and `--day -1` yesterday (any signed integer offset is supported within
the date range). Both midnight bounds use the selected dates' local offsets,
including daylight-saving transitions. `--day` cannot be combined with
`--days`, `--since`, or `--until`; invalid dates and conflicting options exit 2.

JSON pair fields are `timestamp`, `session`, `project`, `model`, `prompt`,
`answer`, and `answer_timestamp`, compatible with the existing companion tools.
Consecutive assistant text messages are joined into one answer. Repeated
human prompts are retained, even if their text is identical.

This parser handles the stated rollout schemas, not every historical or future
Codex format. Image-only prompts and answers are omitted. Nested agent sessions
are included if they have their own rollout file; no source-based exclusion is
applied.
