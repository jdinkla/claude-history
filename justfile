# justfile for claude-history — extract and reflect on Claude Code session history
# Run `just --list` to see all targets, e.g. `just days 3 md`

# --- Dev ---

[group('dev')]
[doc("Show available commands")]
default:
    @just --list --unsorted

[group('dev')]
[doc("Run the test suite (or a single test: just test test_claude_history.TestParseDate)")]
test *ARGS="discover -s tests -v":
    PYTHONPATH=tests python3 -m unittest {{ARGS}}

# --- History ---

[group('history')]
[doc("Dump prompts for PROJECT over the last DAYS days as JSON pairs (noise filtered)")]
prompts DAYS PROJECT:
    ./src/claude_history.py --days {{DAYS}} --project {{PROJECT}} --no-noise --format json

[group('history')]
[doc("Show prompts across all projects for the last K days (today + K-1 previous; noise filtered)")]
days K FORMAT="text":
    ./src/claude_history.py --days {{K}} --no-noise --format {{FORMAT}}

[group('history')]
[doc("Show yesterday's prompts across all projects (noise filtered)")]
yesterday FORMAT="text":
    ./src/claude_history.py --since $(date -v-1d +%F) --until $(date +%F) --no-noise --format {{FORMAT}}

# --- Reflection ---

[group('reflection')]
[doc("Prepare reflection data for the last DAYS full days (today excluded): full/clean pairs + metrics")]
reflect-data DAYS="7" PROJECT="" OUTDIR="reflections/data":
    mkdir -p "{{OUTDIR}}"
    ./src/claude_history.py --since $(date -v-{{DAYS}}d +%F) --until $(date +%F) --project "{{PROJECT}}" --max-chars 0 --format json > "{{OUTDIR}}/full.json"
    ./src/claude_history.py --since $(date -v-{{DAYS}}d +%F) --until $(date +%F) --project "{{PROJECT}}" --no-noise --max-chars 6000 --format json > "{{OUTDIR}}/clean.json"
    ./src/reflect_metrics.py "{{OUTDIR}}/full.json" > "{{OUTDIR}}/metrics.md"
    @echo "Reflection data written to {{OUTDIR}}"

[group('reflection')]
[doc("Install the /reflect skill into ~/.claude/skills (symlink into this repo)")]
install-skill:
    mkdir -p ~/.claude/skills
    ln -sfn "$(pwd)/skills/reflect" ~/.claude/skills/reflect
    @echo "Installed: ~/.claude/skills/reflect -> $(pwd)/skills/reflect"
