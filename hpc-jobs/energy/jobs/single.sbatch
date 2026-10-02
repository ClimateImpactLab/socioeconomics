#!/bin/bash
#SBATCH --job-name=energy-single
#SBATCH --output=logs/energy/single/sg_%A_%a.out
#SBATCH --error=logs/energy/single/sg_%A_%a.err
#SBATCH --account=cil
#SBATCH --partition=cil
#SBATCH --ntasks=1
#SBATCH --mem=50G
#SBATCH --time=12:00:00
#SBATCH --array=0-15

# Submit from hpc-jobs/ : config and log paths resolve against the
# submission directory. One task per fuel x realization config.
export PYTHONUNBUFFERED=1

FUELS=(electricity other_energy)
CELLS=(
    "ssp2-rcp45-low" "ssp2-rcp45-high" "ssp2-rcp85-low" "ssp2-rcp85-high"
    "ssp3-rcp45-low" "ssp3-rcp45-high" "ssp3-rcp85-low" "ssp3-rcp85-high"
)
FUEL=${FUELS[$((SLURM_ARRAY_TASK_ID / 8))]}
CELL=${CELLS[$((SLURM_ARRAY_TASK_ID % 8))]}
CONFIG="$SLURM_SUBMIT_DIR/energy/configs/single/${FUEL}-${CELL}.yml"

module load python
source activate /project/cil/home_dirs/rcc/envs/impact-env/
export IMPERICS_SHAREDDIR=/project/cil/gcp

REPO=/project/cil/home_dirs/scadavidsanchez/repos/impact-calculations
echo "impact-calculations: $(git -C $REPO rev-parse --abbrev-ref HEAD) @ $(git -C $REPO rev-parse --short HEAD)"
cd $REPO
echo "Running: $CONFIG"
./generate.sh "$CONFIG"
