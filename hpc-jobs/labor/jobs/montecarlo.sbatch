#!/bin/bash
#SBATCH --job-name=labor-montecarlo
#SBATCH --output=logs/labor/montecarlo/mc_%A_%a.out
#SBATCH --error=logs/labor/montecarlo/mc_%A_%a.err
#SBATCH --account=cil
#SBATCH --partition=amd
#SBATCH --ntasks=1
#SBATCH --mem=64G
#SBATCH --time=36:00:00
#SBATCH --array=0-63

# Runs one montecarlo batch per submission. Submit from hpc-jobs/ with the
# batch number (0 to 14):
#   sbatch --export=ALL,BATCH=0 labor/jobs/montecarlo.sbatch
# Workers share a config (task % 16, 4 per scenario) and claim one output
# folder at a time.
export PYTHONUNBUFFERED=1

if ! [[ "$BATCH" =~ ^([0-9]|1[0-4])$ ]]; then
    echo "ERROR: BATCH must be a number from 0 to 14. Submit with:" >&2
    echo "  sbatch --export=ALL,BATCH=<batch> labor/jobs/montecarlo.sbatch" >&2
    exit 1
fi

CELLS=(
    "ssp1-rcp45-low" "ssp1-rcp45-high"
    "ssp2-rcp45-low" "ssp2-rcp45-high" "ssp2-rcp85-low" "ssp2-rcp85-high"
    "ssp3-rcp45-low" "ssp3-rcp45-high" "ssp3-rcp85-low" "ssp3-rcp85-high"
    "ssp4-rcp45-low" "ssp4-rcp45-high" "ssp4-rcp85-low" "ssp4-rcp85-high"
    "ssp5-rcp85-low" "ssp5-rcp85-high"
)
SET_SIZE=${#CELLS[@]}
CONFIG="$SLURM_SUBMIT_DIR/labor/configs/montecarlo/${CELLS[$((SLURM_ARRAY_TASK_ID % SET_SIZE))]}.yml"

# Stagger worker starts so folder claims don't collide:
# the first worker per config starts at once, later ones wait.
if [ $SLURM_ARRAY_TASK_ID -lt $SET_SIZE ]; then
    sleep_time=0
else
    group_index=$(( SLURM_ARRAY_TASK_ID / SET_SIZE ))
    sleep_time=$(( 300 + group_index * 10 ))
fi
echo "Task ${SLURM_ARRAY_TASK_ID} sleeping ${sleep_time}s"
sleep $sleep_time

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
echo "Running: $CONFIG (batch $BATCH)"
# generate.sh takes only the config, so call the projection system directly
# to pass the batch number; it reads --KEY=VALUE arguments as config entries.
python -m generate.generate "$CONFIG" --only-batch-number=$BATCH
