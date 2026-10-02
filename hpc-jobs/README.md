# HPC jobs

Slurm jobs used to regenerate the projections of the AMEL sectors
(agriculture, mortality, energy, labor) with the new socioeconomic panel.
Kept for reference and reproducibility.

All jobs run the `impact-calculations` projection engine (on `master`) in the
shared `impact-env` environment, read the panel from
`/project/cil/gcp/outputs_newsocioeconomics/socioeconomics/`
(`socioeconomic_data_dir` in each config), and write projections to
`/project/cil/gcp/outputs_newsocioeconomics/<sector>/<run type>/<fuel>/`.
Every run produces all adaptation variants: full, noadapt, incadapt, global,
and their histclim counterparts (`do_farmers: 'always'` plus
`do_historical: true`).

Note: the global variant averages covariates across regions weighted by the
engine's legacy year-2000 population baseline
(`population.population_baseline_data` in `GlobalAggregatedCovariator`), not
by the new panel's population.

## Layout

```
energy/
  model/        response-function model configs (csvv path, covariates,
                calculation); copied unchanged from the energy release setup
  configs/
    quick_test/ one config per fuel: SSP3 / rcp45 / low / CCSM4
    single/     one config per fuel and realization (SSP2/SSP3 x
                rcp45/rcp85 x low/high, CCSM4)
    median/     one config per fuel and RCP, all SSP/IAM combinations in
                the panel, all GCMs
  jobs/         quick_test.sbatch, single.sbatch, median.sbatch
logs/           Slurm logs, gitignored: logs/<sector>/<run type>/
```

## Running a job

Always submit from this directory (`hpc-jobs/`): the sbatch scripts locate
configs and logs relative to the submission directory.

1. Check the panel exists:
   `ls /project/cil/gcp/outputs_newsocioeconomics/socioeconomics/` should
   list `ir_combined_<scenario>_<model>.csv` files.
2. Check the engine is on master:
   `git -C /project/cil/home_dirs/scadavidsanchez/repos/impact-calculations branch --show-current`
   (each job also echoes the branch and commit into its log).
3. Create the log directory if it does not exist (gitignored, so absent on a
   fresh clone): `mkdir -p logs/energy/<run type>`
4. Submit:
   ```bash
   cd hpc-jobs
   sbatch energy/jobs/quick_test.sbatch   # 2 tasks, one per fuel
   sbatch energy/jobs/single.sbatch       # 16 tasks, fuel x realization
   sbatch energy/jobs/median.sbatch       # 120 tasks, 30 workers per config
   ```
5. After the run, record resources in the table below (command underneath).

Run types:

- **quick_test**: one realization (rcp45 / CCSM4 / low / SSP3) per fuel.
  Output (flat): `.../energy/quick_test/<fuel>/rcp45/CCSM4/low/SSP3/`.
  About 8 h per task (8 adaptation variants at roughly 1 h each).
- **single**: one task per fuel and realization (SSP2/SSP3 x rcp45/rcp85 x
  low/high, CCSM4). Output (flat):
  `.../energy/single/<fuel>/<rcp>/CCSM4/<iam>/<ssp>/`. About 8 h per task.
- **median**: all GCMs for both RCPs and all panel SSP/IAM combinations.
  Median mode adds its own `median/` level:
  `.../energy/median/<fuel>/median/<rcp>/<GCM>/<iam>/<ssp>/`.
  Workers claim per-GCM directories cooperatively and skip finished ones,
  so a resubmission resumes where the previous one stopped. Sizing: ~33
  GCMs x 4 SSP/IAM = ~132 directories per config at ~8 h each; 30 workers
  x 36 h per config just covers it.

## Resource log

| date | sector | run type | job id | partition | CPUs | memory requested | peak memory (MaxRSS) | elapsed time | status | notes |
|------|--------|----------|--------|-----------|------|------------------|----------------------|--------------|--------|-------|

Print a ready-to-paste row for a job id (for array jobs this reports the
max MaxRSS across tasks and the last task's elapsed/state; use
`JOBID=<id>_<task>` for a single task's row):

```bash
JOBID=12345678 RUNTYPE=quick_test; sacct -j "$JOBID" --units=G -P \
  -o JobID,Partition,AllocCPUS,ReqMem,MaxRSS,Elapsed,State \
| awk -F'|' -v d="$(date +%F)" -v rt="$RUNTYPE" '
    NR > 1 && $1 !~ /\./ {id=$1; pa=$2; cp=$3; rq=$4; el=$6; st=$7}
    $1 ~ /\.batch$/ && ($5+0) > (mx+0) {mx=$5}
    END {printf("| %s | energy | %s | %s | %s | %s | %s | %s | %s | %s |  |\n",
                d, rt, id, pa, cp, rq, mx, el, st)}'
```
