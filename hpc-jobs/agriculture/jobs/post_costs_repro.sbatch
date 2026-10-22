#!/bin/bash
#SBATCH --job-name=agriculture-costs-repro
#SBATCH --output=logs/agriculture/post/costs_repro_%j.out
#SBATCH --error=logs/agriculture/post/costs_repro_%j.err
#SBATCH --account=cil
#SBATCH --partition=caslake
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=1
#SBATCH --mem=24G
#SBATCH --time=04:00:00

# Create the log folder before submitting: mkdir -p logs/agriculture/post
# (Slurm opens the log before the job starts, so the job cannot create it.)

# Costs for corn, rcp85, CCSM4, low, SSP2 with the older income, to compare
# with the October 2025 file made by the same script. Submit from hpc-jobs/.
module load netcdf curl/7.79.1 udunits geos/3.9.1 sqlite/3.36.0 proj/7.2 gdal/3.3.3 gcc/12.2.0 python/anaconda-2022.05 R/4.2.1
export LD_LIBRARY_PATH=/software/python-anaconda-2022.05-el8-x86_64/lib:$LD_LIBRARY_PATH
source /project/cil/home_dirs/egrenier/repos/agriculture/user_paths.sh
export AG_INCOME_DIR=/project/cil/sacagawea_shares/gcp/social/baselines/agriculture/income_netcdfs

WD=/project/cil/home_dirs/scadavidsanchez/projects/socioeconomics-update/checks/agriculture/corn_costs_old_income/single
mkdir -p "$WD/rcp85/CCSM4/low/SSP2"
Rscript "$SLURM_SUBMIT_DIR/agriculture/post/costs/tmp_and_prcp_costs-bugfixed.R" maize 13 unused "$WD" CCSM4 rcp85 SSP2 low
