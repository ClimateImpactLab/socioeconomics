"""Combine spring and winter wheat into wheat_combined for the singles.

Impacts (rebased, all eight projection files) and adaptation costs
(adpt.cost.cuml) are each a weighted sum with fixed regional seasonal
shares, which add up to 1, as in wheat_weights.py and wheat_weights_costs.py
in the agriculture repo. The region order of the inputs is kept.

    python wheat_combined.py
"""
import itertools
import os

import pandas as pd
import xarray as xr

ROOT = '/project/cil/gcp/outputs_newsocioeconomics/agriculture'
WEIGHTS = '/project/cil/sacagawea_shares/gcp/estimation/agriculture/Data/1_raw/3_cropped_area/agglomerated-world-new-hierid-wheat-weights_seasonal.csv'
SUFFIXES = ['', '-incadapt', '-noadapt', '-global',
            '-histclim', '-incadapt-histclim', '-noadapt-histclim', '-global-histclim']
FILES = [(f'wheat_{{}}-280823{s}.nc4', 'rebased') for s in SUFFIXES] + [('adaptation_costs.nc4', 'adpt.cost.cuml')]

weights = (pd.read_csv(WEIGHTS)[['hierid', 'wheat_spring', 'wheat_winter']]
           .rename(columns={'hierid': 'region'}).set_index('region').to_xarray())


def load(path, var):
    ds = xr.open_dataset(path)
    regions = [r.decode() if isinstance(r, bytes) else str(r) for r in ds['regions'].values]
    return ds[[var, 'regions']].assign_coords(region=regions), ds.attrs


for rcp, iam, ssp in itertools.product(['rcp45', 'rcp85'], ['low', 'high'], ['SSP2', 'SSP3', 'SSP4']):
    cell = os.path.join('single', rcp, 'CCSM4', iam, ssp)
    out_dir = os.path.join(ROOT, 'wheat_combined', cell)
    os.makedirs(out_dir, exist_ok=True)
    for name, var in FILES:
        spr, attrs = load(os.path.join(ROOT, 'wheat_spring', cell, name.format('spring')), var)
        win, _ = load(os.path.join(ROOT, 'wheat_winter', cell, name.format('winter')), var)
        out = spr.copy()
        # Assigning into the spring dataset keeps its region order
        out[var] = spr[var] * weights['wheat_spring'] + win[var] * weights['wheat_winter']
        assert int(out[var].notnull().sum()) > 0, f'all missing: {cell} {name}'
        out.attrs = dict(attrs, description='weighted sum of spring and winter wheat, fixed seasonal shares')
        path = os.path.join(out_dir, name.format('combined'))
        out.to_netcdf(path)
        print(path, flush=True)
