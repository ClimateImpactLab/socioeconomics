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

## How to run

1. Have your own clone of `impact-calculations` on `master`.
2. From this folder:

```bash
   cd hpc-jobs
   export IMPACT_CALCULATIONS=/path/to/impact-calculations
   mkdir -p logs/energy/quick_test
   sbatch energy/jobs/quick_test.sbatch
```

   Same for `single`, `median` and `montecarlo`.

Results go to `/project/cil/gcp/outputs_newsocioeconomics/<sector>/<run type>/`.

Run types:
- `quick_test`: one realization per fuel, to check everything works.
- `single`: one realization per fuel and scenario.
- `median`: all GCMs and scenarios.
- `montecarlo`: all GCMs and scenarios, with many draws of the response
  function. Only for sectors that have it (energy doesn't).

## Resources used

| date | sector | run type | job id | partition | memory requested | peak memory | time | status |
|------|--------|----------|--------|-----------|------------------|-------------|------|--------|

To get the numbers after a run:

```bash
sacct -j <job id> --units=G --format=JobID,Partition,ReqMem,MaxRSS,Elapsed,State
```
