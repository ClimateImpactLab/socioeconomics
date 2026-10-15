#!/bin/bash
#SBATCH --job-name=labor-quick-test
#SBATCH --output=logs/labor/quick_test/qt_%A_%a.out
#SBATCH --error=logs/labor/quick_test/qt_%A_%a.err
#SBATCH --account=cil
#SBATCH --partition=amd
#SBATCH --ntasks=1
#SBATCH --mem=50G
#SBATCH --time=08:00:00
#SBATCH --array=0-0

# Submit from hpc-jobs/ : config and log paths resolve against the
# submission directory.
export PYTHONUNBUFFERED=1

CONFIG="$SLURM_SUBMIT_DIR/labor/configs/quick_test/ssp3-rcp45-low.yml"

module load python
source activate /project/cil/home_dirs/rcc/envs/impact-env/
export IMPERICS_SHAREDDIR=/project/cil/gcp

if [ -z "$IMPACT_CALCULATIONS" ]; then
    echo "ERROR: IMPACT_CALCULATIONS is not set. Point it at your impact-calculations clone:" >&2
    echo "  sbatch --export=ALL,IMPACT_CALCULATIONS=/path/to/impact-calculations <this script>" >&2
    exit 1
fi
REPO=$IMPACT_CALCULATIONS
echo "impact-calculations: $(git -C "$REPO" rev-parse --abbrev-ref HEAD) @ $(git -C "$REPO" rev-parse --short HEAD)"
cd "$REPO"
echo "Running: $CONFIG"
./generate.sh "$CONFIG"
