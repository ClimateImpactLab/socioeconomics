#!/bin/bash
#SBATCH --job-name=agriculture-aggregate
#SBATCH --output=logs/agriculture/post/aggregate_%A_%a.out
#SBATCH --error=logs/agriculture/post/aggregate_%A_%a.err
#SBATCH --account=cil
#SBATCH --partition=caslake
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=1
#SBATCH --mem=16G
#SBATCH --time=08:00:00
#SBATCH --array=0-15

# Spatial aggregation of impacts and costs, one task per crop and folder:
# tasks 0-7 the crop folders (agriculture/<crop>/single), tasks 8-15 the
# winsorized folders (agriculture/<crop>-1pct_winsorization/single).
# Impacts then costs, one after the other: both claim the same folders, and
# an aggregation that finds a claimed folder skips it without an error.
# Submit from hpc-jobs/ with IMPACT_CALCULATIONS set.
CROPS=(cassava corn rice sorghum soy wheat_spring wheat_winter wheat_combined)
CROP=${CROPS[$((SLURM_ARRAY_TASK_ID % 8))]}
if [ "$SLURM_ARRAY_TASK_ID" -ge 8 ]; then NAME=${CROP}-1pct_winsorization; else NAME=$CROP; fi
CONFIGS=$SLURM_SUBMIT_DIR/agriculture/configs/aggregation

if [ -z "$IMPACT_CALCULATIONS" ]; then
    echo "ERROR: IMPACT_CALCULATIONS is not set." >&2
    exit 1
fi

module load python
source activate /project/cil/home_dirs/rcc/envs/impact-env/
export IMPERICS_SHAREDDIR=/project/cil/gcp
export PYTHONUNBUFFERED=1

cd "$IMPACT_CALCULATIONS"
echo "impact-calculations: $(git rev-parse --abbrev-ref HEAD) @ $(git rev-parse --short HEAD)"
python -m generate.aggregate "$CONFIGS/${NAME}.yml"
python -m generate.aggregate "$CONFIGS/${NAME}-costs.yml"
