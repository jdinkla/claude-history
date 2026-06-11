default:
    @just --list

# Dump prompts for PROJECT over the last DAYS days (machine-generated prompts filtered).
prompts DAYS PROJECT:
    ./claude_history.py --days {{DAYS}} --project {{PROJECT}} --no-noise --format json
