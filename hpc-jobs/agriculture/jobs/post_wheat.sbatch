#!/bin/bash
#SBATCH --job-name=agriculture-wheat
#SBATCH --output=logs/agriculture/post/wheat_%j.out
#SBATCH --error=logs/agriculture/post/wheat_%j.err
#SBATCH --account=cil
#SBATCH --partition=caslake
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=1
#SBATCH --mem=8G
#SBATCH --time=02:00:00

# wheat_combined from spring and winter wheat, impacts and costs, for all 12
# scenario cells. Needs the wheat projections and their costs. Submit from hpc-jobs/.
module load python
source activate /project/cil/home_dirs/rcc/envs/impact-env/
export PYTHONUNBUFFERED=1
python "$SLURM_SUBMIT_DIR/agriculture/post/wheat/wheat_combined.py"
