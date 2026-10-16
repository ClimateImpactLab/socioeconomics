#!/bin/bash -l
# Hourly check from crontab on a login node: if no amel-monitor run is
# queued or running, submit one, which starts the hourly chain again.
# Install and stop: see "Watchdog" in the README.
set -uo pipefail

MONITOR_DIR="/project/cil/home_dirs/scadavidsanchez/projects/socioeconomics-update/cil2/hpc-jobs/monitor"
JOB_NAME="amel-monitor"
stamp=$(date '+%Y-%m-%d %H:%M:%S')

if ! jobs=$(squeue -h --me -n "$JOB_NAME" -o "%i %T %S"); then
    echo "$stamp could not read squeue, nothing done"
    exit 1
fi
if [ -n "$jobs" ]; then
    echo "$stamp ok: $(echo "$jobs" | tr '\n' ';')"
    exit 0
fi
echo "$stamp no $JOB_NAME run queued or running, submitting one"
mkdir -p "$MONITOR_DIR/../logs/monitor"
sbatch "$MONITOR_DIR/monitor_job.sbatch"
