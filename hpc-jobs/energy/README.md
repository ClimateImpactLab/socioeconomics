# Energy jobs

Projection jobs for the two fuels (electricity, other_energy) with the new
socioeconomic panel.

Model specification: `/project/cil/home_dirs/egrenier/repos/energy-code-release-2020/projection_inputs/csvv/TINV_clim/`.

## How to run

From `hpc-jobs/`, with `IMPACT_CALCULATIONS` set (see the main README).
Run singles first, before median.

```bash
mkdir -p logs/energy/quick_test
sbatch energy/jobs/quick_test.sbatch

mkdir -p logs/energy/single
sbatch energy/jobs/single.sbatch

mkdir -p logs/energy/median
sbatch energy/jobs/median.sbatch
```

Outputs go to
`/project/cil/gcp/outputs_newsocioeconomics/energy/<run type>/<fuel>/`.
Logs go to `logs/energy/<run type>/`.
