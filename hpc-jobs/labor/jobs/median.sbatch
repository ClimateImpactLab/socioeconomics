#!/bin/bash
#SBATCH --job-name=labor-median
#SBATCH --output=logs/labor/median/med_%A_%a.out
#SBATCH --error=logs/labor/median/med_%A_%a.err
#SBATCH --account=cil
#SBATCH --partition=amd
#SBATCH --ntasks=1
#SBATCH --mem=64G
#SBATCH --time=36:00:00
#SBATCH --array=0-39

# Submit from hpc-jobs/ : config and log paths resolve against the
# submission directory. Workers share a config (task % 2, 20 per RCP) and
# claim one output folder at a time; finished folders are skipped.
export PYTHONUNBUFFERED=1

# Stagger worker starts so folder claims don't collide:
# the first worker per config starts at once, later ones wait.
if [ $SLURM_ARRAY_TASK_ID -lt 2 ]; then
    sleep_time=0
else
    pair_index=$(( (SLURM_ARRAY_TASK_ID - 2) / 2 ))
    sleep_time=$(( 300 + pair_index * 10 ))
fi
echo "Task ${SLURM_ARRAY_TASK_ID} sleeping ${sleep_time}s"
sleep $sleep_time

CONFIG_FILES=(rcp45 rcp85)
CONFIG="$SLURM_SUBMIT_DIR/labor/configs/median/${CONFIG_FILES[$((SLURM_ARRAY_TASK_ID % 2))]}.yml"

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
