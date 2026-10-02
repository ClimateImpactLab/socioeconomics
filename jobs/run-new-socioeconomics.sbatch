#!/bin/bash
#SBATCH --job-name=irpanel-newsocio
#SBATCH --output=/project/cil/home_dirs/scadavidsanchez/projects/socioeconomics-update/cil2/jobs/newsocio_%j.out
#SBATCH --error=/project/cil/home_dirs/scadavidsanchez/projects/socioeconomics-update/cil2/jobs/newsocio_%j.err
#SBATCH --account=cil
#SBATCH --partition=cil
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=4
#SBATCH --mem=24G
#SBATCH --time=06:00:00

# Build the new-socioeconomics panel track and compare it against the
# previous run in data/output-wpp. The old outputs stay untouched; this track
# writes to /project/cil/gcp/outputs_newsocioeconomics/socioeconomics.
set -euo pipefail
module load apptainer

cd /project/cil/home_dirs/scadavidsanchez/projects/socioeconomics-update/cil2

apptainer exec --bind /project/cil --env TAR_PROJECT=new-socioeconomics \
  irpanel.sif Rscript -e 'targets::tar_make(callr_function = NULL)'

echo "==== provenance README ===="
cat /project/cil/gcp/outputs_newsocioeconomics/socioeconomics/README.txt

echo "==== old vs new comparison ===="
apptainer exec --bind /project/cil irpanel.sif \
  python3 diagnostics/compare_new_socioeconomics.py
