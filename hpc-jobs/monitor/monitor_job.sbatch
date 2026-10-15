#!/bin/bash -l
#SBATCH --job-name=amel-monitor
#SBATCH --account=cil
#SBATCH --partition=cil
#SBATCH --time=00:15:00
#SBATCH --mem=2G
#SBATCH --output=/project/cil/home_dirs/scadavidsanchez/projects/socioeconomics-update/cil2/hpc-jobs/logs/monitor/monitor_%j.log
#
# Self-scheduling monitor run (scrontab is disabled on Midway3). It first
# queues its own next run for the next full hour (America/Chicago), then
# collects and publishes.
# Start it once with: sbatch hpc-jobs/monitor/monitor_job.sbatch
# Stop it with:       scancel --me -n amel-monitor
# One run through Slurm that leaves the chain alone:
#   sbatch --export=ALL,MONITOR_ONCE=1 hpc-jobs/monitor/monitor_job.sbatch
set -uo pipefail

# Slurm runs a copy of this script from its spool folder, so the monitor
# folder is set here instead of taken from the script's location.
MONITOR_DIR="/project/cil/home_dirs/scadavidsanchez/projects/socioeconomics-update/cil2/hpc-jobs/monitor"
JOB_NAME="amel-monitor"

# Queue the next run first, so the chain goes on even if this run fails.
# Only one run is ever waiting: skip when one is already pending.
# Slurm reads --begin in the cluster's local time, which is America/Chicago.
if [ "${MONITOR_ONCE:-0}" = "1" ]; then
    echo "one-time run, the chain is left as it is"
else
    waiting=$(squeue -h --me -n "$JOB_NAME" -t PENDING -o "%i" | wc -l)
    if [ "$waiting" -eq 0 ]; then
        next=$(TZ=America/Chicago date -d "+1 hour" "+%Y-%m-%dT%H:00:00")
        echo "queuing the next run for $next (America/Chicago)"
        sbatch --begin="$next" --dependency=singleton "$MONITOR_DIR/monitor_job.sbatch"
    else
        echo "next run already queued, not adding another"
    fi
fi

bash "$MONITOR_DIR/run_monitor.sh"
