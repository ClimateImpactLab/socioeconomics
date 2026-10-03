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
#
# Runs in the port's own conda environment, not the R container (the
# container has no pyproj or exactextract).
set -euo pipefail

PY=/project/cil/home_dirs/rcc/envs/irpanel-py/bin/python3
R_OUT=/project/cil/gcp/outputs_newsocioeconomics/socioeconomics/1.0.0
PY_OUT=/project/cil/gcp/outputs_newsocioeconomics/socioeconomics/validation/python/1.0.0
cd "$SLURM_SUBMIT_DIR/.."

export IRPANEL_CONFIG=configs/new-socioeconomics.yml
export PYTHONPATH=python
export PYTHONUNBUFFERED=1

"$PY" -m irpanel track

echo "Python vs R comparison:"
R_OUTPUT="$R_OUT" PY_OUTPUT="$PY_OUT" \
  "$PY" diagnostics/compare_python_r.py
