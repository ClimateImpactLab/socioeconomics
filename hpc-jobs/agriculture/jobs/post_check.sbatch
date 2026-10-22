#!/bin/bash
#SBATCH --job-name=agriculture-check
#SBATCH --output=logs/agriculture/post/check_%j.out
#SBATCH --error=logs/agriculture/post/check_%j.err
#SBATCH --account=cil
#SBATCH --partition=caslake
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=1
#SBATCH --mem=32G
#SBATCH --time=02:00:00

# Create the log folder before submitting: mkdir -p logs/agriculture/post
# (Slurm opens the log before the job starts, so the job cannot create it.)

# Short check after a step. Submit from hpc-jobs/ with STEP set, one of:
# income-old, income, costs-repro, costs, wheat, winsor, aggregate.
#   sbatch --export=ALL,STEP=income agriculture/jobs/post_check.sbatch
if [ -z "$STEP" ]; then
    echo "ERROR: STEP is not set." >&2
    exit 1
fi
module load python
source activate /project/cil/home_dirs/rcc/envs/impact-env/
export PYTHONUNBUFFERED=1
echo "check: $STEP"
python "$SLURM_SUBMIT_DIR/agriculture/post/check_step.py" "$STEP"
