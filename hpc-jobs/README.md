# HPC jobs

Slurm jobs used to regenerate the projections of the AMEL sectors
(agriculture, mortality, energy, labor) with the new socioeconomic data.
Kept for reference and reproducibility. Each sector has its own folder with
the configs and jobs for its runs.

## Layout

```
energy/
  configs/    model configs, plus quick_test/, single/, median/
  jobs/       quick_test.sbatch, single.sbatch, median.sbatch
logs/         Slurm logs (not tracked by git)
```

Run types:
- `quick_test`: one realization per fuel, to check everything works.
- `single`: one realization per fuel and scenario.
- `median`: all GCMs and scenarios.
- `montecarlo`: all GCMs and scenarios, with many draws of the response
  function. Only for sectors that have it (energy doesn't).

Results go to `/project/cil/gcp/outputs_newsocioeconomics/<sector>/<run type>/`.

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
   lines.

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

After each run, add a row using the `sacct` output from step 5:

- `job id`: the number Slurm printed when you submitted the job.
- `partition`: the `Partition` column.
- `memory requested`: the `ReqMem` column.
- `peak memory`: the largest `MaxRSS` among the `.batch` lines.
- `time`: the `Elapsed` column (for arrays, the longest task).
- `status`: the `State` column (`COMPLETED`, `FAILED`, `TIMEOUT`...).
- `date`, `user`, `sector`, `run type` and `notes`: fill them in yourself.

The first row is only an example of how to fill the table.

| date | user | sector | run type | job id | partition | memory requested | peak memory | time | status | notes |
|------|------|--------|----------|--------|-----------|------------------|-------------|------|--------|-------|
| 2026-10-02 | Sebastian CS | energy | quick_test | 12345678 | cil | 16G | 4G | 02:30:00 | COMPLETED | example only |
