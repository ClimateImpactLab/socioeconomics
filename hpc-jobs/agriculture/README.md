# Agriculture jobs

Projection jobs for the seven crops with the new socioeconomic panel.

Model specification: `/project/cil/home_dirs/egrenier/repos/agriculture/1_code/3_projections/2_run_projection/projection/model_config/`.

## How to run

From `hpc-jobs/`, with `IMPACT_CALCULATIONS` set (see the main README).
Run singles first, before median or montecarlo.

```bash
mkdir -p logs/agriculture/quick_test
sbatch agriculture/jobs/quick_test.sbatch

mkdir -p logs/agriculture/single
sbatch agriculture/jobs/single.sbatch

mkdir -p logs/agriculture/median
sbatch agriculture/jobs/median.sbatch

# one batch (0 to 14) per submission
mkdir -p logs/agriculture/montecarlo
sbatch --export=ALL,BATCH=0 agriculture/jobs/montecarlo.sbatch
```

Outputs go to
`/project/cil/gcp/outputs_newsocioeconomics/agriculture/<crop>/<run type>/`
(`quick_test/`, `single/`, `median/` or `montecarlo/`; the projection system
adds the first three itself).
Logs go to `logs/agriculture/<run type>/`.

## After the projection: singles through aggregation

For the singles (CCSM4; SSP2, SSP3, SSP4; rcp45, rcp85; low, high). Run from
`hpc-jobs/` with `IMPACT_CALCULATIONS` set, one step at a time, and wait for
each check to end with `OK` before the next. Income and costs can run while
the projection runs; the rest needs the projection files.

```bash
# Once: log folder (Slurm needs it before the job starts) and R packages
# (on a login node, with the modules from post_costs.sbatch loaded)
mkdir -p logs/agriculture/post
Rscript -e 'install.packages(c("pracma","ncdf4","abind","matrixStats","reticulate","stringr","dplyr","readxl","data.table","glue","yaml"), repos="https://cloud.r-project.org")'

# 1. Income for the costs: rebuild the old files to check the method, then build from the 1.0.0 panel
sbatch --export=ALL,SOURCE=old agriculture/jobs/post_income.sbatch
sbatch --export=ALL,STEP=income-old agriculture/jobs/post_check.sbatch
sbatch agriculture/jobs/post_income.sbatch
sbatch --export=ALL,STEP=income agriculture/jobs/post_check.sbatch

# 2. Costs: reproduce the October 2025 file with the old income, run one task alone, then the rest
sbatch agriculture/jobs/post_costs_repro.sbatch
sbatch --export=ALL,STEP=costs-repro agriculture/jobs/post_check.sbatch
sbatch --array=83 agriculture/jobs/post_costs.sbatch
sbatch --array=0-82 agriculture/jobs/post_costs.sbatch
sbatch --export=ALL,STEP=costs agriculture/jobs/post_check.sbatch

# 3. wheat_combined from spring and winter wheat, impacts and costs
sbatch agriculture/jobs/post_wheat.sbatch
sbatch --export=ALL,STEP=wheat agriculture/jobs/post_check.sbatch

# 4. Winsorization at the 1st and 99th percentiles, with the costs copied in
sbatch agriculture/jobs/post_winsorize.sbatch
sbatch --export=ALL,STEP=winsor agriculture/jobs/post_check.sbatch

# 5. Aggregation to countries, admin regions and the globe, impacts then costs
sbatch agriculture/jobs/post_aggregate.sbatch
sbatch --export=ALL,STEP=aggregate agriculture/jobs/post_check.sbatch
```

Outputs, under `/project/cil/gcp/outputs_newsocioeconomics/agriculture/`:

- income: `income_netcdfs/1.0.0/`
- costs: `<crop>/single/<rcp>/CCSM4/<iam>/<SSP>/adaptation_costs.nc4`
- wheat_combined: `wheat_combined/single/`
- winsorized: `<crop>-1pct_winsorization/single/`
- aggregated: `*-aggregated.nc4` next to the files in `<crop>/single/` and `<crop>-1pct_winsorization/single/`

The two method checks (old income rebuild, costs with the old income) write to
`/project/cil/home_dirs/scadavidsanchez/projects/socioeconomics-update/checks/agriculture/`.
Logs go to `logs/agriculture/post/`.
