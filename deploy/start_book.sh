#!/bin/sh
# Start one book for today, from cron. Usage: deploy/start_book.sh <book.toml> [--live]
#
# The rest-day guard runs first. Only its "rest" answer (exit code 10) skips the start; any other
# failure of the guard starts the book anyway, because not starting on a trading day is the costly
# mistake. One log file per book per day.
set -u
cd /opt/quant-engine || exit 1
. ./.env
config="$1"; shift
book=$(basename "$config" .toml)
log="logs/${book}_$(date +%Y-%m-%d).log"
mkdir -p logs

.venv/bin/qe-guard --state "state/${book}.json" >> "$log" 2>&1
if [ $? -eq 10 ]; then
    echo "$(date '+%F %T') rest day, not starting" >> "$log"
    exit 0
fi
exec .venv/bin/qe-live "$config" "$@" >> "$log" 2>&1
