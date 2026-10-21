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
