"""Short checks to run after each post-projection step for the agriculture singles.

    python check_step.py income-old | income | costs-repro | costs | wheat | winsor | aggregate

Each check prints a few numbers and ends with OK, or stops at the first FAIL.
"""
import glob
import itertools
import json
import os
import sys

import numpy as np
import pandas as pd
import xarray as xr

ROOT = '/project/cil/gcp/outputs_newsocioeconomics/agriculture'
CHECKS = '/project/cil/home_dirs/scadavidsanchez/projects/socioeconomics-update/checks/agriculture'
INCOME, INCOME_CHECK = f'{ROOT}/income_netcdfs/1.0.0', f'{CHECKS}/income_method_check_old'
OLD_INCOME = '/project/cil/sacagawea_shares/gcp/social/baselines/agriculture/income_netcdfs'
PANEL = '/project/cil/gcp/outputs_newsocioeconomics/socioeconomics/1.0.0'
AREA = '/project/cil/gcp/estimation/agriculture/Data/1_raw/3_cropped_area/agglomerated-world-new-hierid-crop-weights.csv'
SEASONAL = '/project/cil/sacagawea_shares/gcp/estimation/agriculture/Data/1_raw/3_cropped_area/agglomerated-world-new-hierid-wheat-weights_seasonal.csv'
REPRO_NEW = f'{CHECKS}/corn_costs_old_income/single/rcp85/CCSM4/low/SSP2/adaptation_costs.nc4'
REPRO_REF = '/project/cil/gcp/outputs/agriculture/impacts-mealy/median/corn-global/median/rcp85/CCSM4/low/SSP2/adaptation_costs.nc4'
OLD_COSTS = '/project/cil/gcp/outputs/agriculture/impacts-mealy/median/{crop}-global/median/{cell}/adaptation_costs.nc4'

CROPS = {'cassava': 'cassava-110221', 'corn': 'corn-160221', 'rice': 'rice-160221', 'sorghum': 'sorghum-160221',
         'soy': 'soy-160221', 'wheat_spring': 'wheat_spring-280823', 'wheat_winter': 'wheat_winter-280823'}
ALL = dict(CROPS, wheat_combined='wheat_combined-280823')
AREA_COLUMN = {'cassava': 'cassava', 'corn': 'corn', 'rice': 'rice', 'sorghum': 'sorghum', 'soy': 'soy',
               'wheat_spring': 'wheat', 'wheat_winter': 'wheat', 'wheat_combined': 'wheat'}
CELLS = [f'{rcp}/CCSM4/{iam}/{ssp}' for rcp, iam, ssp in
         itertools.product(['rcp45', 'rcp85'], ['low', 'high'], ['SSP2', 'SSP3', 'SSP4'])]
IMPACT_SUFFIXES = ['', '-incadapt', '-noadapt', '-global',
                   '-histclim', '-incadapt-histclim', '-noadapt-histclim', '-global-histclim']
WINSORIZED_SUFFIXES = ['', '-incadapt', '-noadapt', '-global', '-fulladaptcosts', '-histclim']
LABEL = {'low': 'IIASA', 'high': 'OECD'}
YEARS = np.arange(1981, 2099)
W = np.arange(1, 14, dtype=float)


def raw_dir(crop, cell):
    return f'{ROOT}/{crop}/single/{cell}'


def wins_dir(crop, cell):
    return f'{ROOT}/{crop}-1pct_winsorization/single/{cell}'


def regions_of(ds):
    return [r.decode() if isinstance(r, bytes) else str(r) for r in ds['regions'].values]


ORDER = regions_of(xr.open_dataset(f'{OLD_INCOME}/SSP3_IAM-low_13yr-avg.nc4'))


def fail(msg):
    print('FAIL', msg)
    sys.exit(1)


def by_year_region(ds, var):
    return ds[var].transpose('year', 'region').values


def expected_income(series):
    """Covariate for 1981..2098 from gdppc 2010..2100, written independently of impact-calculations."""
    v = series.astype(float).copy()
    v[v <= 0] = np.nan
    v = np.zeros_like(v) if np.isnan(v).all() else pd.Series(v).ffill().bfill().values
    base = v[:5].copy()
    base[base <= 0] = np.nan
    base = base[np.isfinite(base)]
    history = list(np.log(base)) if len(base) else [0.0]
    out = []
    for year in YEARS:
        if year > 2015 and v[year - 2010] > 0:
            history.append(np.log(v[year - 2010]))
        h = np.array(history[-13:])
        out.append(float(W[-len(h):] @ h / W[-len(h):].sum()))
    return np.array(out)


def income_old():
    files = sorted(glob.glob(f'{INCOME_CHECK}/SSP*_13yr-avg.nc4'))
    if len(files) != 6:
        fail(f'expected 6 files in {INCOME_CHECK}, found {len(files)}')
    for f in files:
        new = xr.open_dataset(f)['loggdppc'].values
        old = xr.open_dataset(f'{OLD_INCOME}/{os.path.basename(f)}')['loggdppc'].values
        diff = float(np.abs(new - old).max())
        print(os.path.basename(f), 'max abs diff against the existing file', f'{diff:.2e}')
        if diff > 1e-6:
            fail('the rebuild from the older inputs does not reproduce the existing file')
    print('OK income-old')


def income():
    sample = np.random.default_rng(0).choice(len(ORDER), 500, replace=False)
    for ssp in ['SSP2', 'SSP3', 'SSP4']:
        expected = {}
        for label in ['IIASA', 'OECD']:
            df = pd.read_csv(f'{PANEL}/ir_combined_{ssp}_{label}.csv', usecols=['hierid', 'year', 'gdppc', 'gdppc_raw'])
            df = df[(df.year >= 2010) & (df.year <= 2100)]
            df['use'] = df['gdppc_raw'].fillna(df['gdppc'])
            wide = df.pivot(index='year', columns='hierid', values='use')
            expected[label] = np.array([expected_income(wide[ORDER[j]].values) for j in sample]).T
        for iam in ['low', 'high']:
            ds = xr.open_dataset(f'{INCOME}/{ssp}_IAM-{iam}_13yr-avg.nc4')
            v = ds['loggdppc'].values
            if v.shape != (118, 24378) or regions_of(ds) != ORDER or not np.isfinite(v).all():
                fail(f'{ssp} {iam}: shape, region order or missing values')
            if np.abs(v[YEARS <= 2015] - v[YEARS == 2015]).max() > 0:
                fail(f'{ssp} {iam}: years up to 2015 are not flat')
            zeros = int((np.abs(v).max(0) == 0).sum())
            right = float(np.abs(v[:, sample] - expected[LABEL[iam]]).max())
            other = float(np.abs(v[:, sample] - expected[LABEL['high' if iam == 'low' else 'low']]).max())
            d = v - xr.open_dataset(f'{OLD_INCOME}/{ssp}_IAM-{iam}_13yr-avg.nc4')['loggdppc'].values
            print(f'{ssp} {iam}: {ds.attrs.get("source")}; zero regions {zeros}; diff vs {LABEL[iam]} {right:.1e}; '
                  f'vs the other model {other:.2f}; new minus old median 2016 {np.median(d[YEARS == 2016]):+.3f} '
                  f'2050 {np.median(d[YEARS == 2050]):+.3f} 2098 {np.median(d[YEARS == 2098]):+.3f}')
            if right > 1e-5 or other < 1e-3 or zeros != 23 or LABEL[iam] not in str(ds.attrs.get('source')):
                fail(f'{ssp} {iam}: income does not match the panel or the IIASA/OECD mapping')
    print('OK income')


def costs_repro():
    new, ref = xr.open_dataset(REPRO_NEW), xr.open_dataset(REPRO_REF)
    for var in ['adpt.cost.cuml', 'adpt.cost.temp.cuml', 'adpt.cost.tmin.cuml', 'adpt.cost.prcp.cuml']:
        diff = float(np.abs(new[var].values - ref[var].values).max())
        print(var, 'max abs diff', f'{diff:.2e}')
        if diff > 1e-6:
            fail('costs with the older income do not reproduce the October 2025 file')
    print('OK costs-repro')


def costs():
    area = pd.read_csv(AREA).set_index('hierid').reindex(ORDER).fillna(0)
    rows = []
    for (crop, base), cell in itertools.product(CROPS.items(), CELLS):
        path = f'{raw_dir(crop, cell)}/adaptation_costs.nc4'
        if not os.path.exists(path):
            fail(f'missing {path}')
        ds = xr.open_dataset(path)
        c = by_year_region(ds, 'adpt.cost.cuml')
        if regions_of(ds) != ORDER or not np.isfinite(c).all() or np.abs(c[YEARS <= 2015]).max() != 0:
            fail(f'{path}: region order, missing values, or nonzero before 2016')
        w = area[AREA_COLUMN[crop]].values / area[AREA_COLUMN[crop]].sum()
        row = dict(crop=crop, cell=cell, mean2050=float(w @ c[YEARS == 2050][0]), mean2098=float(w @ c[YEARS == 2098][0]))
        old_path = OLD_COSTS.format(crop=crop, cell=cell)
        if os.path.exists(old_path):
            o = by_year_region(xr.open_dataset(old_path), 'adpt.cost.cuml')
            row['old_income_mean2098'] = float(w @ o[YEARS == 2098][0])
            row['share_cells_changed'] = float((np.abs(c - o) > 1e-9).mean())
        rows.append(row)
    print(pd.DataFrame(rows).round(5).to_string(index=False))
    print('OK costs')


def wheat():
    sw = pd.read_csv(SEASONAL).set_index('hierid')
    rng = np.random.default_rng(1)
    files = [(f'wheat_{{}}-280823{s}.nc4', 'rebased') for s in IMPACT_SUFFIXES] + [('adaptation_costs.nc4', 'adpt.cost.cuml')]
    for cell in CELLS:
        for name, var in files:
            path = lambda crop: f'{ROOT}/wheat_{crop}/single/{cell}/{name.format(crop)}'
            com, spr, win = xr.open_dataset(path('combined')), xr.open_dataset(path('spring')), xr.open_dataset(path('winter'))
            if regions_of(com) != ORDER:
                fail(f'{cell} {name}: region order')
            idx = rng.choice(len(ORDER), 200, replace=False)
            regs = [ORDER[i] for i in idx]
            a = by_year_region(com, var)[:, idx]
            b = (by_year_region(spr, var)[:, idx] * sw.loc[regs, 'wheat_spring'].values
                 + by_year_region(win, var)[:, idx] * sw.loc[regs, 'wheat_winter'].values)
            if not np.allclose(a, b, equal_nan=True, atol=1e-6) or np.isnan(a).all():
                fail(f'{cell} {name}: combined is not the weighted sum')
    print('OK wheat')


def winsor():
    rows = []
    for (crop, base), cell in itertools.product(ALL.items(), CELLS):
        d = wins_dir(crop, cell)
        bounds = json.load(open(f'{d}/winsorization-bounds.json'))
        for suffix in WINSORIZED_SUFFIXES:
            b = bounds['histclim' if suffix == '-histclim' else 'pooled']
            v = xr.open_dataset(f'{d}/{base}{suffix}.nc4')['rebased'].values
            if np.nanmin(v) < b['lower'] - 1e-9 or np.nanmax(v) > b['upper'] + 1e-9:
                fail(f'{d}/{base}{suffix}: outside its bounds')
        src = xr.open_dataset(f'{raw_dir(crop, cell)}/adaptation_costs.nc4')['adpt.cost.cuml'].values
        if not np.array_equal(src, xr.open_dataset(f'{d}/adaptation_costs.nc4')['adpt.cost.cuml'].values):
            fail(f'{d}: costs copy differs from the source')
        rows.append(dict(crop=crop, cell=cell, **bounds['pooled']))
    print(pd.DataFrame(rows).round(4).to_string(index=False))
    print('OK winsor')


def aggregate():
    rows = []
    trees = [('raw', raw_dir, IMPACT_SUFFIXES, ''), ('winsorized', wins_dir, WINSORIZED_SUFFIXES, '-1pct_winsorization')]
    for (crop, base), cell, (tree, folder, suffixes, tag) in itertools.product(ALL.items(), CELLS, trees):
        d = folder(crop, cell)
        if os.path.exists(f'{d}/status-aggregate.txt'):
            fail(f'{d}: a claim file was left behind')
        status = open(f'{d}/status-global.txt').read()
        for config in [f'{crop}{tag}', f'{crop}{tag}-costs']:
            if f'generate.aggregate {config}: Complete' not in status:
                fail(f'{d}: aggregation {config} is not Complete')
        names = [f'{base}{s}-aggregated' for s in suffixes] + ['adaptation_costs-aggregated']
        row = dict(crop=crop, cell=cell, tree=tree)
        for name in names:
            ds = xr.open_dataset(f'{d}/{name}.nc4')
            var = 'adpt.cost.cuml' if name.startswith('adaptation_costs') else 'rebased'
            g = by_year_region(ds, var)[:, regions_of(ds).index('')]
            if not np.isfinite(g).all():
                fail(f'{d}/{name}: missing values in the global series')
            if name in (f'{base}-aggregated', 'adaptation_costs-aggregated'):
                row[name.replace(base, 'impact') + '_2098'] = float(g[-1])
        rows.append(row)
    print(pd.DataFrame(rows).round(4).to_string(index=False))
    print('OK aggregate')


if __name__ == '__main__':
    {'income-old': income_old, 'income': income, 'costs-repro': costs_repro, 'costs': costs,
     'wheat': wheat, 'winsor': winsor, 'aggregate': aggregate}[sys.argv[1]]()
