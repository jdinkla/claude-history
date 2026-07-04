default:
    @just --list

# Dump prompts for PROJECT over the last DAYS days (machine-generated prompts filtered).
prompts DAYS PROJECT:
    ./claude_history.py --days {{DAYS}} --project {{PROJECT}} --no-noise --format json

# Show prompts across all projects for the last K days (today + K-1 previous; machine-generated prompts filtered).
days K FORMAT="text":
    ./claude_history.py --days {{K}} --no-noise --format {{FORMAT}}

# Show yesterday's prompts across all projects (machine-generated prompts filtered).
yesterday FORMAT="text":
    ./claude_history.py --since $(date -v-1d +%F) --until $(date +%F) --no-noise --format {{FORMAT}}

# Run the test suite.
test:
    python3 -m unittest -v

# Prepare reflection data for the last DAYS full days (today excluded): full + clean pairs and observable-event metrics.
# Local-midnight timestamps (not bare dates): claude_history.py treats bare dates as UTC midnight,
# which in CET/CEST would leak the first hours of today into the window.
reflect-data DAYS="7" PROJECT="" OUTDIR="reflections/data":
    mkdir -p "{{OUTDIR}}"
    ./claude_history.py --since $(date -v-{{DAYS}}d +%FT00:00:00%z) --until $(date +%FT00:00:00%z) --project "{{PROJECT}}" --max-chars 0 --format json > "{{OUTDIR}}/full.json"
    ./claude_history.py --since $(date -v-{{DAYS}}d +%FT00:00:00%z) --until $(date +%FT00:00:00%z) --project "{{PROJECT}}" --no-noise --max-chars 6000 --format json > "{{OUTDIR}}/clean.json"
    ./reflect_metrics.py "{{OUTDIR}}/full.json" > "{{OUTDIR}}/metrics.md"
    @echo "Reflection data written to {{OUTDIR}}"

# Install the /reflect skill into ~/.claude/skills (symlink into this repo).
install-skill:
    mkdir -p ~/.claude/skills
    ln -sfn "$(pwd)/skills/reflect" ~/.claude/skills/reflect
    @echo "Installed: ~/.claude/skills/reflect -> $(pwd)/skills/reflect"
