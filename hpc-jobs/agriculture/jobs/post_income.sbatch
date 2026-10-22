#!/bin/bash
#SBATCH --job-name=agriculture-income
#SBATCH --output=logs/agriculture/post/income_%A_%a.out
#SBATCH --error=logs/agriculture/post/income_%A_%a.err
#SBATCH --account=cil
#SBATCH --partition=amd,caslake
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=1
#SBATCH --mem=24G
#SBATCH --time=02:00:00
#SBATCH --array=0-5

# Income files for the costs script, one task per SSP x IAM.
# Submit from hpc-jobs/ with IMPACT_CALCULATIONS set.
# SOURCE=panel (default) builds them from the 1.0.0 panel; SOURCE=old rebuilds
# the existing files from the older inputs, to check the method.
SOURCE=${SOURCE:-panel}
CELLS=("SSP2 low" "SSP2 high" "SSP3 low" "SSP3 high" "SSP4 low" "SSP4 high")
read -r SSP IAM <<< "${CELLS[$SLURM_ARRAY_TASK_ID]}"

ROOT=/project/cil/gcp/outputs_newsocioeconomics/agriculture/income_netcdfs
if [ "$SOURCE" = "panel" ]; then OUT=$ROOT/1.0.0; else OUT=$ROOT/method_check_old; fi

if [ -z "$IMPACT_CALCULATIONS" ]; then
    echo "ERROR: IMPACT_CALCULATIONS is not set." >&2
    exit 1
fi

module load python
source activate /project/cil/home_dirs/rcc/envs/impact-env/
export IMPERICS_SHAREDDIR=/project/cil/gcp
export PYTHONPATH=$IMPACT_CALCULATIONS
export PYTHONUNBUFFERED=1

echo "impact-calculations: $(git -C "$IMPACT_CALCULATIONS" rev-parse --abbrev-ref HEAD) @ $(git -C "$IMPACT_CALCULATIONS" rev-parse --short HEAD)"
python "$SLURM_SUBMIT_DIR/agriculture/post/income/build_income.py" "$SOURCE" "$SSP" "$IAM" "$OUT"
