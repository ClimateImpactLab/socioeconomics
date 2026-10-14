#!/bin/bash -l
# Scheduled monitor run: collect the status, then publish it to the
# monitor-data branch. Run by scrontab every 4 hours (see README), or by
# hand: bash hpc-jobs/monitor/run_monitor.sh
set -euo pipefail

MONITOR_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
mkdir -p "$MONITOR_DIR/../logs/monitor"

echo "monitor run started $(date '+%Y-%m-%d %H:%M:%S') on $(hostname)"

module load python
# shellcheck disable=SC1091
source activate /project/cil/home_dirs/rcc/envs/impact-env/

cd "$MONITOR_DIR"
python3 collect_status.py

# impact-env's libraries clash with the system ssh (undefined symbol
# EVP_KDF_ctrl), so publish with a clean environment: system git and ssh.
# These setup scripts read unset variables, so nounset is off around them.
set +u
source deactivate 2>/dev/null || conda deactivate 2>/dev/null || true
module purge
# shellcheck disable=SC1091
source /etc/profile
set -u
echo "publishing with $(command -v git) and $(command -v ssh)"

bash "$MONITOR_DIR/publish_data.sh"

echo "monitor run finished $(date '+%Y-%m-%d %H:%M:%S')"
