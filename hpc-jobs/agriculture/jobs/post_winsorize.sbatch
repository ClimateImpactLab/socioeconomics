#!/bin/bash
#SBATCH --job-name=agriculture-winsorize
#SBATCH --output=logs/agriculture/post/winsorize_%j.out
#SBATCH --error=logs/agriculture/post/winsorize_%j.err
#SBATCH --account=cil
#SBATCH --partition=caslake
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=12
#SBATCH --mem=32G
#SBATCH --time=03:00:00

# Create the log folder before submitting: mkdir -p logs/agriculture/post
# (Slurm opens the log before the job starts, so the job cannot create it.)

# Winsorization of the 8 crops (including wheat_combined) x 12 cells, with
# the costs copied into agriculture/<crop>-1pct_winsorization/single/.
# Needs costs and wheat_combined. Submit from hpc-jobs/.
module load python
source activate /project/cil/home_dirs/rcc/envs/impact-env/
export PYTHONUNBUFFERED=1
python "$SLURM_SUBMIT_DIR/agriculture/post/winsorization/winsorize.py"
