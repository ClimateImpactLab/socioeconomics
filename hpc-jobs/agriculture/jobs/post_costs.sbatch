#!/bin/bash
#SBATCH --job-name=agriculture-costs
#SBATCH --output=logs/agriculture/post/costs_%A_%a.out
#SBATCH --error=logs/agriculture/post/costs_%A_%a.err
#SBATCH --account=cil
#SBATCH --partition=caslake
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=1
#SBATCH --mem=24G
#SBATCH --time=04:00:00
#SBATCH --array=0-83

# Adaptation costs, one task per crop x rcp x IAM x SSP (7 x 12), with the
# income built from the 1.0.0 panel. Writes adaptation_costs.nc4 into
# agriculture/<crop>/single/<rcp>/CCSM4/<iam>/<SSP>/. Submit from hpc-jobs/.
CROPS=(cassava corn rice sorghum soy wheat_spring wheat_winter)
CODES=(cassava maize rice sorghum soy wheat-spring wheat-winter)
CELLS=(
    "rcp45 low SSP2" "rcp45 low SSP3" "rcp45 low SSP4"
    "rcp45 high SSP2" "rcp45 high SSP3" "rcp45 high SSP4"
    "rcp85 low SSP2" "rcp85 low SSP3" "rcp85 low SSP4"
    "rcp85 high SSP2" "rcp85 high SSP3" "rcp85 high SSP4"
)
CROP=${CROPS[$((SLURM_ARRAY_TASK_ID / 12))]}
CODE=${CODES[$((SLURM_ARRAY_TASK_ID / 12))]}
read -r RCP IAM SSP <<< "${CELLS[$((SLURM_ARRAY_TASK_ID % 12))]}"

module load netcdf curl/7.79.1 udunits geos/3.9.1 sqlite/3.36.0 proj/7.2 gdal/3.3.3 gcc/12.2.0 python/anaconda-2022.05 R/4.2.1
export LD_LIBRARY_PATH=/software/python-anaconda-2022.05-el8-x86_64/lib:$LD_LIBRARY_PATH
source /project/cil/home_dirs/egrenier/repos/agriculture/user_paths.sh
export AG_INCOME_DIR=/project/cil/gcp/outputs_newsocioeconomics/agriculture/income_netcdfs/1.0.0

WD=/project/cil/gcp/outputs_newsocioeconomics/agriculture/$CROP/single
mkdir -p "$WD/$RCP/CCSM4/$IAM/$SSP"
echo "costs: $CROP ($CODE) $RCP CCSM4 $IAM $SSP"
Rscript "$SLURM_SUBMIT_DIR/agriculture/post/costs/tmp_and_prcp_costs-bugfixed.R" "$CODE" 13 unused "$WD" CCSM4 "$RCP" "$SSP" "$IAM"
