#!/bin/bash
#SBATCH --job-name=agriculture-median
#SBATCH --output=logs/agriculture/median/med_%A_%a.out
#SBATCH --error=logs/agriculture/median/med_%A_%a.err
#SBATCH --account=cil
#SBATCH --partition=amd
#SBATCH --ntasks=1
#SBATCH --mem=40G
#SBATCH --time=36:00:00
#SBATCH --array=0-351

# Submit from hpc-jobs/ : config and log paths resolve against the
# submission directory. Workers share a config (one per crop and RCP) and
# claim one output folder at a time; finished folders are skipped.
export PYTHONUNBUFFERED=1

# Workers per crop and RCP; slower crops get more.
# --array must cover 2 x the sum (0-351).
CROPS=(cassava corn rice sorghum soy wheat_spring wheat_winter)
WORKERS=(16 24 24 16 24 32 40)

CONFIG_NAMES=()
WORKER_INDEX=()
for i in "${!CROPS[@]}"; do
    for ((w = 0; w < ${WORKERS[$i]}; w++)); do
        CONFIG_NAMES+=("${CROPS[$i]}-rcp45" "${CROPS[$i]}-rcp85")
        WORKER_INDEX+=("$w" "$w")
    done
done
if [ "$SLURM_ARRAY_TASK_ID" -ge "${#CONFIG_NAMES[@]}" ]; then
    echo "Task ${SLURM_ARRAY_TASK_ID} has no config (only ${#CONFIG_NAMES[@]} workers set)"
    exit 0
fi
CONFIG="$SLURM_SUBMIT_DIR/agriculture/configs/median/${CONFIG_NAMES[$SLURM_ARRAY_TASK_ID]}.yml"

# Stagger worker starts so folder claims don't collide:
# the first worker per config starts at once, later ones wait.
w=${WORKER_INDEX[$SLURM_ARRAY_TASK_ID]}
if [ "$w" -eq 0 ]; then
    sleep_time=0
else
    sleep_time=$(( 300 + (w - 1) * 10 ))
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
echo "Running: $CONFIG"
./generate.sh "$CONFIG"
