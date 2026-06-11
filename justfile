default:
    @just --list

# Dump prompts for PROJECT over the last DAYS days (machine-generated prompts filtered).
prompts DAYS PROJECT:
    ./claude_history.py --days {{DAYS}} --project {{PROJECT}} --no-noise --format json

# Show yesterday's prompts across all projects (machine-generated prompts filtered).
yesterday FORMAT="text":
    ./claude_history.py --since $(date -v-1d +%F) --until $(date +%F) --no-noise --format {{FORMAT}}
