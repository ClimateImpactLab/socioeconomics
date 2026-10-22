"""Clamp the singles' rebased impacts at the 1st and 99th percentiles.

For each crop, rcp, IAM and SSP folder:
- fulladapt, incadapt, noadapt, global and fulladapt minus costs are stacked
  and clamped together, over all regions, years and those five scenarios
- the fulladapt histclim file is clamped on its own
- the incadapt, noadapt and global histclim files are left out (nothing
  downstream uses them)
- adaptation_costs.nc4 is copied unchanged
- the bounds and the share clamped are written to winsorization-bounds.json

Same method as winsorization.py in the agriculture repo (the version that
pools the global file), with the new folder layout.

    python winsorize.py [crop ...]
"""
import itertools
import json
import multiprocessing
import os
import shutil
import sys

import numpy as np
import xarray as xr

ROOT = '/project/cil/gcp/outputs_newsocioeconomics/agriculture'
THRESHOLD = 0.99
BASENAMES = {'cassava': 'cassava-110221', 'corn': 'corn-160221', 'rice': 'rice-160221',
             'sorghum': 'sorghum-160221', 'soy': 'soy-160221', 'wheat_spring': 'wheat_spring-280823',
             'wheat_winter': 'wheat_winter-280823', 'wheat_combined': 'wheat_combined-280823'}
POOLED = {'fulladapt': '', 'incadapt': '-incadapt', 'noadapt': '-noadapt', 'global': '-global'}


def load(path):
    ds = xr.open_dataset(path)
    return ds[['rebased', 'regions']].assign_coords(region=ds.regions)


def clamp(da):
    lower, upper = float(da.quantile(1 - THRESHOLD)), float(da.quantile(THRESHOLD))
    bounds = {'lower': lower, 'upper': upper,
              'share_below': float((da < lower).mean()), 'share_above': float((da > upper).mean())}
    return np.maximum(np.minimum(da, upper), lower), bounds


def winsorize(task):
    crop, rcp, iam, ssp = task
    cell = os.path.join('single', rcp, 'CCSM4', iam, ssp)
    src = os.path.join(ROOT, crop, cell)
    dst = os.path.join(ROOT, f'{crop}-1pct_winsorization', cell)
    os.makedirs(dst, exist_ok=True)
    base = BASENAMES[crop]

    parts = [load(os.path.join(src, base + suffix + '.nc4')).assign_coords(scenario=scn).expand_dims('scenario')
             for scn, suffix in POOLED.items()]

    costs = xr.open_dataset(os.path.join(src, 'adaptation_costs.nc4'))
    costs = costs.assign_coords(region=[r.decode() if isinstance(r, bytes) else str(r) for r in costs['regions'].values])
    full = parts[0].isel(scenario=0, drop=True)
    fac = (full.rebased - costs['adpt.cost.cuml']).to_dataset(name='rebased')
    fac = fac.assign(regions=fac.region).assign_coords(scenario='fulladaptcosts').expand_dims('scenario')
    parts.append(fac)

    combine = xr.concat(parts, dim='scenario')
    if crop != 'wheat_combined':
        combine = combine.drop_vars('region')
    combine['rebased'], pooled = clamp(combine['rebased'])

    suffixes = dict(POOLED, fulladaptcosts='-fulladaptcosts')
    for scn, suffix in suffixes.items():
        combine.sel(scenario=scn, drop=True).to_netcdf(os.path.join(dst, base + suffix + '.nc4'))

    hist = load(os.path.join(src, base + '-histclim.nc4'))
    if crop != 'wheat_combined':
        hist = hist.drop_vars('region')
    hist['rebased'], histclim = clamp(hist['rebased'])
    hist.to_netcdf(os.path.join(dst, base + '-histclim.nc4'))

    shutil.copy(os.path.join(src, 'adaptation_costs.nc4'), os.path.join(dst, 'adaptation_costs.nc4'))
    with open(os.path.join(dst, 'winsorization-bounds.json'), 'w') as fp:
        json.dump({'pooled': pooled, 'histclim': histclim}, fp, indent=1)
    print(dst, pooled, flush=True)


if __name__ == '__main__':
    crops = sys.argv[1:] or list(BASENAMES)
    tasks = list(itertools.product(crops, ['rcp45', 'rcp85'], ['low', 'high'], ['SSP2', 'SSP3', 'SSP4']))
    with multiprocessing.Pool(int(os.environ.get('SLURM_CPUS_PER_TASK', 1))) as pool:
        pool.map(winsorize, tasks)
