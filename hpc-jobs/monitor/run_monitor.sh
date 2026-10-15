#!/bin/bash -l
# Scheduled monitor run: collect the status, then publish it to the
# monitor-data branch. Run every hour, on the hour, by monitor_job.sbatch
# (see README), or by hand: bash hpc-jobs/monitor/run_monitor.sh
# A run by hand never queues anything, so the hourly chain is left alone.
set -euo pipefail

MONITOR_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
mkdir -p "$MONITOR_DIR/../logs/monitor"

# If the script ends for any reason before publishing, say so in the log.
STEP="starting"
PUBLISHED=0
on_exit() {
    local code=$?
    if [ "$PUBLISHED" -ne 1 ]; then
        echo "monitor run stopped before publishing (exit code $code, during: $STEP)" >&2
    fi
}
trap on_exit EXIT

echo "monitor run started $(date '+%Y-%m-%d %H:%M:%S') on $(hostname)"

STEP="loading python and impact-env"
module load python
# shellcheck disable=SC1091
source activate /project/cil/home_dirs/rcc/envs/impact-env/

STEP="collecting the status"
cd "$MONITOR_DIR"
python3 collect_status.py

# impact-env's libraries clash with the system ssh (undefined symbol
# EVP_KDF_ctrl), so publish with a clean environment: system git and ssh.
# System profile scripts read unset variables and run commands that may
# fail (for example a grep for a file a node does not have), so neither
# errors nor unset variables may stop the script during this clean up.
STEP="cleaning the environment"
set +eu
source deactivate 2>/dev/null || conda deactivate 2>/dev/null || true
module purge
# shellcheck disable=SC1091
source /etc/profile
set -eu
echo "publishing with $(command -v git) and $(command -v ssh)"

STEP="publishing"
bash "$MONITOR_DIR/publish_data.sh"
PUBLISHED=1

echo "monitor run finished $(date '+%Y-%m-%d %H:%M:%S')"
