# Labor jobs

Projection jobs for labor with the new socioeconomic panel.

Model specification: `/project/cil/home_dirs/egrenier/repos/labor-code-release-2020/3_projection/1_run_projections/2_model_config/`.

## How to run

From `hpc-jobs/`, with `IMPACT_CALCULATIONS` set (see the main README).
Run singles first, before median or montecarlo.

```bash
mkdir -p logs/labor/quick_test
sbatch labor/jobs/quick_test.sbatch

mkdir -p logs/labor/single
sbatch labor/jobs/single.sbatch

mkdir -p logs/labor/median
sbatch labor/jobs/median.sbatch

# one batch (0 to 14) per submission
mkdir -p logs/labor/montecarlo
sbatch --export=ALL,BATCH=0 labor/jobs/montecarlo.sbatch
```

Outputs go to `/project/cil/gcp/outputs_newsocioeconomics/labor/<run type>/`.
Logs go to `logs/labor/<run type>/`.
