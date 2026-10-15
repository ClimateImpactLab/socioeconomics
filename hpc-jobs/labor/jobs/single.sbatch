#!/bin/bash
#SBATCH --job-name=labor-single
#SBATCH --output=logs/labor/single/sg_%A_%a.out
#SBATCH --error=logs/labor/single/sg_%A_%a.err
#SBATCH --account=cil
#SBATCH --partition=amd
#SBATCH --ntasks=1
#SBATCH --mem=60G
#SBATCH --time=08:00:00
#SBATCH --array=0-15

# Submit from hpc-jobs/ : config and log paths resolve against the
# submission directory. One task per scenario cell.
export PYTHONUNBUFFERED=1

CELLS=(
    "ssp1-rcp45-low" "ssp1-rcp45-high"
    "ssp2-rcp45-low" "ssp2-rcp45-high" "ssp2-rcp85-low" "ssp2-rcp85-high"
    "ssp3-rcp45-low" "ssp3-rcp45-high" "ssp3-rcp85-low" "ssp3-rcp85-high"
    "ssp4-rcp45-low" "ssp4-rcp45-high" "ssp4-rcp85-low" "ssp4-rcp85-high"
    "ssp5-rcp85-low" "ssp5-rcp85-high"
)
CONFIG="$SLURM_SUBMIT_DIR/labor/configs/single/${CELLS[$SLURM_ARRAY_TASK_ID]}.yml"

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
