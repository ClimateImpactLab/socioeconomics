# HPC jobs

Slurm jobs used to regenerate the projections of the AMEL sectors
(agriculture, mortality, energy, labor) with the new socioeconomic data,
plus the job that builds that socioeconomic panel itself. Kept for reference
and reproducibility. Each sector has its own folder with the configs and
jobs for its runs.

## Layout

```
energy/
  configs/    model configs, plus quick_test/, single/, median/
  jobs/       quick_test.sbatch, single.sbatch, median.sbatch
labor/
  configs/    model config, plus quick_test/, single/, median/, montecarlo/
  jobs/       quick_test.sbatch, single.sbatch, median.sbatch, montecarlo.sbatch
  README.md   specification source and how to run
socioeconomics/
  jobs/       build_panel.sbatch
logs/         Slurm logs (not tracked by git)
```

Run types:
- `quick_test`: one realization per fuel or crop, to check everything works.
- `single`: one realization per fuel or crop and scenario. Run singles first,
  before any median or montecarlo.
- `median`: all GCMs and scenarios.
- `montecarlo`: all GCMs and scenarios, with many draws of the response
  function. Only for sectors that have it (energy doesn't). One batch per
  submission, see the sector README.
- `build_panel` (socioeconomics): builds the new socioeconomic panel itself
  (income, population, and age cohorts per impact region) — the input data
  the sector runs read — and checks it against the climate compensation
  data.

Results go to `/project/cil/gcp/outputs_newsocioeconomics/<sector>/<run type>/`.
The socioeconomic panel goes to
`/project/cil/gcp/outputs_newsocioeconomics/socioeconomics/`.

## How to run

These instructions are for running on Midway3, the cluster of the University
of Chicago Research Computing Center (RCC).

1. Clone [impact-calculations](https://github.com/ClimateImpactLab/impact-calculations/tree/master)
   with SSH, preferably in your repos folder under
   `/project/cil/home_dirs/<your user>/repos/`, and use `master`:

```bash
   mkdir -p /project/cil/home_dirs/<your user>/repos
   cd /project/cil/home_dirs/<your user>/repos
   git clone git@github.com:ClimateImpactLab/impact-calculations.git
   cd impact-calculations
   git checkout master
```

   If you already have a clone, just update it:

```bash
   cd /project/cil/home_dirs/<your user>/repos/impact-calculations
   git checkout master
   git pull
```

2. Go to this folder and tell the jobs where your clone is:

```bash
   cd hpc-jobs
   export IMPACT_CALCULATIONS=/project/cil/home_dirs/<your user>/repos/impact-calculations
```

3. Create the log folder and submit the job:

```bash
   mkdir -p logs/energy/quick_test
   sbatch energy/jobs/quick_test.sbatch
```

   Slurm prints `Submitted batch job <job id>`. Save that job id, you need it
   to check the run and to fill the table below.

   Same for `single`, `median` and `montecarlo`, changing the run type in both
   lines. Montecarlo also needs the batch number
   (`sbatch --export=ALL,BATCH=0 <sector>/jobs/montecarlo.sbatch`); each
   sector's own README has the details.

   For the socioeconomic panel, steps 1 and 2 are not needed (the job runs
   this repository's own pipeline in the `irpanel.sif` container; the main
   README explains how to build the image). From `hpc-jobs/`:

```bash
   mkdir -p logs/socioeconomics
   sbatch socioeconomics/jobs/build_panel.sbatch
```

4. Check the job while it runs:

```bash
   squeue -u $USER
   tail -f logs/energy/quick_test/*_<job id>_0.out
```

   Jobs are arrays, so each task has its own log ending in `_<task number>`.

   To follow it live (state, time and memory so far), refreshing every minute:

```bash
   watch -n 60 "sacct -j <job id> --units=G --format=JobID,State,Elapsed,MaxRSS"
```

   `State` shows `PENDING` while it waits in the queue and `RUNNING` once it
   starts. If `watch` crashes, run `conda deactivate` first.

5. When it finishes, get the resources used and add a row to the table:

```bash
   sacct -j <job id> --units=G --format=JobID,Partition,ReqMem,MaxRSS,Elapsed,State
```

   The peak memory is the `MaxRSS` of the `.batch` lines (take the largest one).

## Resources used

After each run that finishes, add a row using the `sacct` output from step 5:

- `job id`: the number Slurm printed when you submitted the job.
- `partition`: the `Partition` column.
- `memory requested`: the `ReqMem` column.
- `peak memory`: the largest `MaxRSS` among the `.batch` lines.
- `time`: the `Elapsed` column (for arrays, the longest task).
- `date`, `user`, `sector`, `run type` and `notes`: fill them in yourself.

The table lists only runs that finished, as a reference.

| date | user | sector | run type | job id | partition | memory requested | peak memory | time | notes |
|------|------|--------|----------|--------|-----------|------------------|-------------|------|-------|
| 2026-10-15 | Sebastian CS | labor | quick_test | 60760541 | amd | 50G | 43.79G | 01:51:47 | singles now request 60G |
