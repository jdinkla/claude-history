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
