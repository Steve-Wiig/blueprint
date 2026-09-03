#!/usr/bin/env bash
set -u

cd /home/swiig/Documents/blueprint

set -a
source .env
set +a

while true; do
    echo "============================================================"
    echo "CONTINUOUS CYCLE: $(date)"
    echo "============================================================"

    PYTHONUNBUFFERED=1 python3 overnight/self_improver.py \
        >> overnight/continuous_loop.log 2>&1

    status=$?

    echo "Cycle exited with status $status at $(date)" \
        >> overnight/continuous_loop.log

    # Don't hammer the APIs if the process crashes immediately.
    sleep 30
done
