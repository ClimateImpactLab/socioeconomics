#!/bin/bash
#SBATCH --job-name=socioeconomics-python_reproduction
#SBATCH --output=logs/socioeconomics/pyrep_%j.out
#SBATCH --error=logs/socioeconomics/pyrep_%j.err
#SBATCH --account=cil
#SBATCH --partition=cil
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=4
#SBATCH --mem=32G
#SBATCH --time=12:00:00

# Submit from hpc-jobs/ : log paths resolve against the submission directory,
# and the pipeline runs from the repository root (its parent). Runs the
# Python port end to end for the new-socioeconomics track (own aggregation
# into data/cache/py, then all scenario x model panels into the validation
# folder) and compares every column against the published R panels. Needs
# the R run to have finished: submit with
# --dependency=afterok:<R job id> when it is still going.
set -euo pipefail
module load apptainer

R_OUT=/project/cil/gcp/outputs_newsocioeconomics/socioeconomics/1.0.0
PY_OUT=/project/cil/gcp/outputs_newsocioeconomics/socioeconomics/validation/python/1.0.0
cd "$SLURM_SUBMIT_DIR/.."

apptainer exec --bind /project/cil \
  --env IRPANEL_CONFIG=configs/new-socioeconomics.yml \
  --env PYTHONPATH=python \
  irpanel.sif python3 -m irpanel track

echo "Python vs R comparison:"
apptainer exec --bind /project/cil \
  --env R_OUTPUT="$R_OUT" --env PY_OUTPUT="$PY_OUT" \
  irpanel.sif python3 diagnostics/compare_python_r.py
