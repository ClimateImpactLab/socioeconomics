#!/bin/bash
#SBATCH --job-name=energy-quick-test
#SBATCH --output=logs/energy/quick_test/qt_%A_%a.out
#SBATCH --error=logs/energy/quick_test/qt_%A_%a.err
#SBATCH --account=cil
#SBATCH --partition=cil
#SBATCH --ntasks=1
#SBATCH --mem=50G
#SBATCH --time=12:00:00
#SBATCH --array=0-1

# Submit from hpc-jobs/ : config and log paths resolve against the
# submission directory.
export PYTHONUNBUFFERED=1

FUELS=(electricity other_energy)
CONFIG="$SLURM_SUBMIT_DIR/energy/configs/quick_test/${FUELS[$SLURM_ARRAY_TASK_ID]}.yml"

module load python
source activate /project/cil/home_dirs/rcc/envs/impact-env/
export IMPERICS_SHAREDDIR=/project/cil/gcp

REPO=/project/cil/home_dirs/scadavidsanchez/repos/impact-calculations
echo "impact-calculations: $(git -C $REPO rev-parse --abbrev-ref HEAD) @ $(git -C $REPO rev-parse --short HEAD)"
cd $REPO
echo "Running: $CONFIG"
./generate.sh "$CONFIG"
