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

Steps for the singles (CCSM4; SSP2, SSP3 and SSP4; rcp45 and rcp85; low and
high), after `single.sbatch` has finished. Scripts are in `post/`, jobs in
`jobs/post_*.sbatch`, aggregation configs in `configs/aggregation/`. The
design and the reasons behind it are in `post_projection_plan.md`.

| Step | Job | Writes to `/project/cil/gcp/outputs_newsocioeconomics/agriculture/` |
|------|-----|------|
| Income for the costs | `post_income.sbatch` | `income_netcdfs/1.0.0/SSP{n}_IAM-{low,high}_13yr-avg.nc4` |
| Costs | `post_costs.sbatch` | `<crop>/single/<rcp>/CCSM4/<iam>/<SSP>/adaptation_costs.nc4` |
| wheat_combined | `post_wheat.sbatch` | `wheat_combined/single/...` (8 impact files and costs) |
| Winsorization | `post_winsorize.sbatch` | `<crop>-1pct_winsorization/single/...` |
| Aggregation | `post_aggregate.sbatch` | `*-aggregated.nc4` next to the files, in both `<crop>/single` and `<crop>-1pct_winsorization/single` |

Two jobs exist only to check a method against older results. Their outputs
are tests, so they go to
`/project/cil/home_dirs/scadavidsanchez/projects/socioeconomics-update/checks/agriculture/`,
never under `outputs_newsocioeconomics/`:

- `post_income.sbatch` with `SOURCE=old` writes to `income_method_check_old/`.
- `post_costs_repro.sbatch` writes to `corn_costs_old_income/single/`.

### Order

From `hpc-jobs/`, with `IMPACT_CALCULATIONS` set. Wait for each job to finish
and for its check to end with `OK` before the next line.

**Create the log folder first.** Slurm opens a job's log file before the job
starts, so a job cannot create its own log folder. If the folder is missing,
the job fails without writing any log.

```bash
mkdir -p logs/agriculture/post

# 1. Income for the costs. First rebuild the existing files from the older
#    inputs (must match them), then build from the 1.0.0 panel.
sbatch --export=ALL,SOURCE=old agriculture/jobs/post_income.sbatch
sbatch --export=ALL,STEP=income-old agriculture/jobs/post_check.sbatch
sbatch agriculture/jobs/post_income.sbatch
sbatch --export=ALL,STEP=income agriculture/jobs/post_check.sbatch

# 2. Costs. First one run with the older income (must reproduce the
#    October 2025 file), then one task alone to size memory and time, then the rest.
sbatch agriculture/jobs/post_costs_repro.sbatch
sbatch --export=ALL,STEP=costs-repro agriculture/jobs/post_check.sbatch
sbatch --array=83 agriculture/jobs/post_costs.sbatch
sbatch --array=0-82 agriculture/jobs/post_costs.sbatch
sbatch --export=ALL,STEP=costs agriculture/jobs/post_check.sbatch

# 3. wheat_combined, impacts and costs
sbatch agriculture/jobs/post_wheat.sbatch
sbatch --export=ALL,STEP=wheat agriculture/jobs/post_check.sbatch

# 4. Winsorization, with the costs copied into the winsorized folders
sbatch agriculture/jobs/post_winsorize.sbatch
sbatch --export=ALL,STEP=winsor agriculture/jobs/post_check.sbatch

# 5. Aggregation of impacts and costs, crop folders and winsorized folders
sbatch agriculture/jobs/post_aggregate.sbatch
sbatch --export=ALL,STEP=aggregate agriculture/jobs/post_check.sbatch
```

Costs read only climate, income, irrigation and the csvv, not the projection
files, so steps 1 and 2 can run while the projection runs. Steps 3 to 5 need
the projection files.

`sacct -j <job id> --format=JobID,State,Elapsed,MaxRSS` shows whether a job
finished and how much it used.

### What each check looks at

- `income-old`: the 6 files rebuilt from the older inputs match the existing
  ones to within 1e-6.
- `income`: the 6 new files.
  - They keep the old region order and years, and are flat through 2015.
  - Exactly 23 uninhabited regions sit at log income 0.
  - 500 regions recomputed straight from the panel CSVs match to within 1e-5.
  - `IAM-low` matches IIASA and not OECD.
  - The build job also compares 200 regions with the projection system's own
    income covariate.
- `costs-repro`: the older-income run matches the October 2025 costs file.
- `costs`: 84 files, no missing values, zero up to 2015, and crop area
  weighted means compared with the October 2025 costs for SSP2.
- `wheat`: combined values equal the seasonal weighted sum for a sample of
  regions, in every file.
- `winsor`: all values lie inside their bounds, and the costs copy equals the
  source.
- `aggregate`: both configs per folder ended `Complete`, no claim files were
  left behind, and the global series have no missing values.

### Notes

- **Income** comes from `gdppc_raw`, and from `gdppc` only where raw is
  missing, exactly as the projection reads it. The panel's `gdppc` column is
  already smoothed, so it is not used directly. `low` is IIASA and `high` is
  OECD. Regions keep the order of the existing income files, which the
  climate and irrigation files share.
- **Costs** use a copy of the bug-fixed costs script, `post/costs/`. It has
  two changes:
  - the income folder comes from `AG_INCOME_DIR`, and the script stops if
    that is not set
  - global attributes are added so `generate.aggregate` can read the file

  The calculations are unchanged.
- **Winsorization** pools fulladapt, incadapt, noadapt, global and fulladapt
  minus costs into one 1st and 99th percentile clamp, over all regions and
  years of one folder. That matches the most recent working version, which
  pools the global file.

  Histclim follows the earlier method: only the fulladapt histclim file is
  clamped, on its own. The incadapt, noadapt and global histclim files are
  not written to the winsorized folders, since nothing downstream uses them.

  The costs are copied unchanged, so the clamped `-fulladaptcosts` is not the
  same as clamped fulladapt minus the raw costs.
- **Aggregation** rolls impact regions up to admin regions, countries and
  the globe, weighted by fixed crop area. Spring and winter wheat use the
  total wheat area, as in the published runs.

  Each config treats `single` as the batch level. The impacts and costs of
  one crop run one after the other in the same task. A crashed aggregation
  leaves `status-aggregate.txt` in a folder for 24 hours, during which a
  rerun skips that folder; delete the file before rerunning.
- **R modules**: the costs jobs load the same R modules as the older costs
  jobs. All post jobs run on `caslake`.
- R packages must be installed once on a login node, since compute nodes may
  have no internet. Load the same modules as the costs jobs, then run:

  ```bash
  Rscript -e 'install.packages(c("pracma","ncdf4","abind","matrixStats","reticulate","stringr","dplyr","readxl","data.table","glue","yaml"), repos="https://cloud.r-project.org")'
  ```
