#!/bin/bash -l
#SBATCH --job-name=amel-monitor
#SBATCH --account=cil
#SBATCH --partition=cil
#SBATCH --time=00:15:00
#SBATCH --mem=2G
#SBATCH --output=/project/cil/home_dirs/scadavidsanchez/projects/socioeconomics-update/cil2/hpc-jobs/logs/monitor/monitor_%j.log
#SBATCH --mail-type=FAIL
#SBATCH --mail-user=cadavidsanchez@uchicago.edu
#
# Self-scheduling monitor run (scrontab is disabled on Midway3). It first
# queues its own next run for the next full hour (America/Chicago), then
# collects and publishes. A failed run sends an email; the reason is at the
# end of its log.
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
# Only one run is ever waiting. A waiting run that begins later than the
# next full hour (a leftover from an older schedule) is replaced; one that
# begins at or before it is kept.
# Slurm reads --begin in the cluster's local time, which is America/Chicago.
queue_next() {
    local next waiting id begin keep=0
    next=$(TZ=America/Chicago date -d "+1 hour" "+%Y-%m-%dT%H:00:00")
    waiting=$(squeue -h --me -n "$JOB_NAME" -t PENDING -o "%i %S")
    while read -r id begin; do
        [ -n "$id" ] || continue
        # A start time that is not a date (N/A while waiting on another job) is kept.
        if [[ "$begin" =~ ^[0-9]{4}- ]] && [[ "$begin" > "$next" ]]; then
            echo "replacing waiting run $id (begins $begin, later than $next)"
            scancel "$id"
        else
            echo "keeping waiting run $id (begins $begin)"
            keep=1
        fi
    done <<< "$waiting"
    if [ "$keep" -eq 0 ]; then
        echo "queuing the next run for $next (America/Chicago)"
        sbatch --begin="$next" --dependency=singleton "$MONITOR_DIR/monitor_job.sbatch"
    fi
}

if [ "${MONITOR_ONCE:-0}" = "1" ]; then
    echo "one-time run, the chain is left as it is"
else
    queue_next
fi

bash "$MONITOR_DIR/run_monitor.sh"
code=$?
if [ "$code" -ne 0 ]; then
    echo "monitor run failed with exit code $code; the reason is in the lines above"
fi
exit "$code"
