"""Build the income files read by the agriculture costs script,
SSP{n}_IAM-{low|high}_13yr-avg.nc4, with the same format, regions and years
as the existing ones.

The covariate is the projection system's income covariate: a 13 year
Bartlett average of log income per region, built from 2010 to 2014, held
there through 2015 (2015 itself is never used), then updated every year from
2016. Before 13 values exist, the newest Bartlett weights are used and
renormalized.

Sources:
    panel  1.0.0 panel, read by the projection system's own provider
           (gdppc_raw, gdppc only where raw is missing; low = IIASA,
           high = OECD)
    old    the older income inputs (social/baselines), to check the method
           against the existing files

Run with the impact-calculations clone on PYTHONPATH and IMPERICS_SHAREDDIR
set:
    python build_income.py panel SSP3 low OUT_DIR
    python build_income.py old SSP3 low OUT_DIR
"""
import os
import shutil
import sys

import netCDF4
import numpy as np

PANEL_DIR = '/project/cil/gcp/outputs_newsocioeconomics/socioeconomics/1.0.0/'
TEMPLATE_DIR = '/project/cil/sacagawea_shares/gcp/social/baselines/agriculture/income_netcdfs'
START, STOP = 2010, 2100
BASELINE_END = 2015
LENGTH = 13
WEIGHTS = np.arange(1, LENGTH + 1, dtype=float)  # oldest 1, newest 13
VERIFY_REGIONS = 200


def provider(source, iam, ssp):
    """Income provider and the file it reads; get_timeseries gives gdppc for 2010 to 2100."""
    if source == 'panel':
        from adaptation.precomputed.precomputed_provider import PrecomputedGDPpcProvider, _build_filepath
        path = _build_filepath(PANEL_DIR, ssp, iam)
        label = {'low': 'IIASA', 'high': 'OECD'}[iam]
        assert os.path.basename(path) == f'ir_combined_{ssp}_{label}.csv', path
        return PrecomputedGDPpcProvider.from_config(iam=iam, ssp=ssp, data_dir=PANEL_DIR,
                                                    startyear=START, stopyear=STOP), path
    from impactcommon.exogenous_economy.gdppc import GDPpcProvider
    return GDPpcProvider(iam, ssp), 'social/baselines gdppc-merged-nohier.csv and gdppc-growth.csv'


def covariate(series, years):
    """Projection covariate per year from gdppc for 2010 to 2100."""
    series = np.asarray(series, dtype=float)
    base = series[:BASELINE_END - START].copy()
    base[base <= 0] = np.nan
    if np.isnan(base).all():
        base = np.array([1.0])  # uninhabited region: log income 0, never updated
    history = list(np.log(base[np.isfinite(base)]))

    out = np.empty(len(years))
    for ii, year in enumerate(years):
        if year > BASELINE_END:
            value = series[year - START]
            if value > 0:
                history.append(np.log(value))
        recent = np.array(history[-LENGTH:])
        weights = WEIGHTS[-len(recent):]
        out[ii] = weights @ recent / weights.sum()
    return out


def region_names(var):
    var.set_auto_mask(False)
    return [str(name) for name in netCDF4.chartostring(var[:])]


def verify(iam, ssp, regions, years, values):
    """Compare a sample of regions with the projection system's own covariator."""
    from adaptation.covariates import EconomicCovariator
    from adaptation.precomputed.new_econmodel import NewSSPEconomicModel

    covariator = EconomicCovariator(NewSSPEconomicModel(iam, ssp, PANEL_DIR, config={}), BASELINE_END, config={})
    sample = np.random.default_rng(0).choice(len(regions), VERIFY_REGIONS, replace=False)
    worst = 0.0
    for jj in sample:
        region = regions[jj]
        expected = []
        for year in years:
            if year <= BASELINE_END:
                expected.append(covariator.get_current(region)['loggdppc'])
            else:
                expected.append(covariator.get_update(region, year, None)['loggdppc'])
        worst = max(worst, float(np.abs(np.array(expected) - values[:, jj]).max()))
    print(f'checked {VERIFY_REGIONS} regions against EconomicCovariator: max abs diff {worst:.2e}')
    assert worst < 1e-5, 'income does not match the projection covariate'


def main(source, ssp, iam, out_dir):
    assert source in ('panel', 'old') and iam in ('low', 'high')
    name = f'{ssp}_IAM-{iam}_13yr-avg.nc4'
    out_path = os.path.join(out_dir, name)
    os.makedirs(out_dir, exist_ok=True)

    income, source_file = provider(source, iam, ssp)
    print(f'{name} from {source_file}', flush=True)

    # The old file is the template: same dimensions, region order, years and encoding
    shutil.copyfile(os.path.join(TEMPLATE_DIR, name), out_path)
    with netCDF4.Dataset(out_path, 'r+') as nc:
        regions = region_names(nc.variables['regions'])
        years = np.asarray(nc.variables['year'][:]).astype(int)
        assert years[0] == 1981 and years[-1] == 2098 and len(regions) == 24378
        assert nc.variables['loggdppc'].dimensions == ('year', 'region')

        values = np.empty((len(years), len(regions)), dtype=np.float32)
        for jj, region in enumerate(regions):
            values[:, jj] = covariate(income.get_timeseries(region), years)
        assert np.isfinite(values).all()

        nc.variables['loggdppc'][:] = values
        nc.setncattr('source', source_file)
        nc.setncattr('method', 'Bartlett 13 of log gdppc, baseline 2010-2014 held through 2015, updates from 2016')

    print(f'wrote {out_path}; regions at log income 0: {int((np.abs(values).max(0) == 0).sum())}', flush=True)
    if source == 'panel':
        verify(iam, ssp, regions, years, values)


if __name__ == '__main__':
    main(*sys.argv[1:5])
