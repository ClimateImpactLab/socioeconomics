#!/bin/bash
#SBATCH --job-name=energy-median
#SBATCH --output=logs/energy/median/med_%A_%a.out
#SBATCH --error=logs/energy/median/med_%A_%a.err
#SBATCH --account=cil
#SBATCH --partition=cil
#SBATCH --ntasks=1
#SBATCH --mem=50G
#SBATCH --time=36:00:00
#SBATCH --array=0-119

# Submit from hpc-jobs/ : config and log paths resolve against the
# submission directory. Tasks cooperate per config (task % 4), claiming
# per-GCM directories; finished directories are skipped on resubmission.
export PYTHONUNBUFFERED=1

# Stagger worker starts so directory claims don't collide:
# the first worker per config starts at once, later ones wait.
if [ $SLURM_ARRAY_TASK_ID -lt 4 ]; then
    sleep_time=0
else
    group_index=$(( (SLURM_ARRAY_TASK_ID - 4) / 4 ))
    sleep_time=$(( 300 + group_index * 10 ))
fi
echo "Task ${SLURM_ARRAY_TASK_ID} sleeping ${sleep_time}s"
sleep $sleep_time

CONFIG_FILES=(electricity-rcp45 electricity-rcp85 other_energy-rcp45 other_energy-rcp85)
CONFIG="$SLURM_SUBMIT_DIR/energy/configs/median/${CONFIG_FILES[$((SLURM_ARRAY_TASK_ID % 4))]}.yml"

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
