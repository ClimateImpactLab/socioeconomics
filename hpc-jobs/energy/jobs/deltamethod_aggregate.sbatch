#!/bin/bash
#SBATCH --job-name=energy-deltamethod-agg
#SBATCH --output=logs/energy/deltamethod/agg_%A_%a.out
#SBATCH --error=logs/energy/deltamethod/agg_%A_%a.err
#SBATCH --account=cil
#SBATCH --partition=amd
#SBATCH --ntasks=1
#SBATCH --mem=12G
#SBATCH --time=24:00:00
#SBATCH --array=0-79

# Price014 levels and aggregated files for the delta method median, both
# fuels. Submit from hpc-jobs/ after the delta method median has finished
# (or with --dependency=afterok:<its job id>). Tasks cooperate per fuel
# (task % 2), each claiming one folder at a time.
#
# Sizing, from the same pilot: about 1 h and 3.9 GB per folder (it reads
# the whole gradient of a file at once, about 1.9 GB). The new panel adds
# memory as it did for the median, so 12G. 40 tasks per fuel cover its
# 390 folders in about 10 h.
export PYTHONUNBUFFERED=1

# Stagger worker starts so folder claims don't collide.
sleep $(( (SLURM_ARRAY_TASK_ID / 2) * 15 ))

FUELS=(electricity other_energy)
CONFIG="$SLURM_SUBMIT_DIR/energy/configs/deltamethod/aggregate-price014-${FUELS[$((SLURM_ARRAY_TASK_ID % 2))]}.yml"

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
./aggregate.sh "$CONFIG"
