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
`/project/cil/gcp/outputs_newsocioeconomics/energy/<fuel>/<run type>/`
(`quick_test/`, `single/` or `median/`, added by the projection system).
Logs go to `logs/energy/<run type>/`.

## Delta method median

The same point estimate as the median, with `deltamethod: yes`: each file
holds the variance of the impact and its gradient by coefficient, plus the
coefficient covariance. Later steps take the global variance per GCM from
it, as a standard deviation next to the median, to draw the samples for the
damage functions. SSP2, SSP3 and SSP4, rcp45 and rcp85, both IAMs, full
adaptation and its histclim only.

```bash
mkdir -p logs/energy/deltamethod
sbatch energy/jobs/deltamethod.sbatch
# when it has finished: price014 levels and aggregated files
sbatch energy/jobs/deltamethod_aggregate.sbatch
```

Outputs go to
`/project/cil/gcp/outputs_newsocioeconomics/energy/<fuel>/deltamethod/median/<rcp>/<GCM>/<iam>/<ssp>/`,
apart from the normal median. File names are the same as the median's, so
the two must never share a folder. Expect about 4.2 GB per folder (two
files of about 0.95 GB, their price014 levels, and two aggregated files of
about 0.22 GB), about 3.3 TB for the 780 folders.
