#!/bin/bash
#SBATCH --job-name=socioeconomics-build_panel
#SBATCH --output=logs/socioeconomics/bp_%j.out
#SBATCH --error=logs/socioeconomics/bp_%j.err
#SBATCH --account=cil
#SBATCH --partition=cil
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=4
#SBATCH --mem=32G
#SBATCH --time=06:00:00

# Submit from hpc-jobs/ : log paths resolve against the submission directory,
# and the pipeline runs from the repository root (its parent). Builds the
# new-socioeconomics track (five scenarios; 32G covers the cross-checks and
# Zarr step over the ten panels) and checks it against the climate
# compensation data. OUT must match paths.output in
# configs/new-socioeconomics.yml.
set -euo pipefail
module load apptainer

OUT=/project/cil/gcp/outputs_newsocioeconomics/socioeconomics/1.0.0
cd "$SLURM_SUBMIT_DIR/.."

apptainer exec --bind /project/cil --env TAR_PROJECT=new-socioeconomics \
  irpanel.sif Rscript -e 'targets::tar_make(callr_function = NULL)'

echo "Provenance README:"
cat "$OUT/README.txt"

echo "Comparison against the climate compensation data:"
apptainer exec --bind /project/cil --env NEW_OUTPUT="$OUT" irpanel.sif \
  python3 diagnostics/compare_new_socioeconomics.py
