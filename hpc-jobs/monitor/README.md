# AMEL run-status monitor

A status dashboard for the new socioeconomics projection runs of the four
AMEL sectors (agriculture, mortality, energy, labor). It shows run status
only, never projection results. The page follows the design of the old
mortality monitor (/project/cil/home_dirs/scadavidsanchez/repos/mortality-monitor):

- The camel at the top (from camel-progress-kit): a two-humped camel made
  of 100 pieces per sector: head and neck energy (yellow), shoulder and
  front legs mortality (red), back and humps coastal (blue), belly labor
  (grey), hindquarters, back legs and tail agriculture (green). Pieces fill
  from the bottom up with the sector's share of projection files and pulse
  softly while projections run; the sector turns solid when all projection
  files are there, and gets fine light stripes when aggregation is complete
  too. Coastal is not tracked yet. The tab icon is the kit's color favicon
  in the same five colors (site/camel/).
- A row of small cards for the selected sector and run type: expected
  units, complete, partial, not started, projection and aggregation
  progress, units being written, time to finish, and SUs to finish.
- Right above the grid: sector, run type and sub-model tabs (montecarlo by
  default, median for energy, whose montecarlo tab is greyed out). Each
  sector tab shows its progress and the SUs needed to finish it, with a
  one-line explanation underneath.
- An info bar with the path of the clicked cell, and a detail panel that
  lists the cell's files grouped into Projections, Aggregation (levels and
  aggregated) and Costs, each with a small dot, the file size and the date
  it was written.
- Resources: storage and service units of the cil account, as thin bars.
  When the account has no allocation, it says "No allocation yet". Below
  them, service units since the start date in the manifest, on every
  partition of the account: one bar per person in the manifest (display
  names) plus one "Other users" bar for everyone else. Each bar is split by
  partition with shades and light textures, and a small key gives each
  partition's name and total. Jobs whose formula is different (bigmem,
  GPU) are listed under the bars, not counted.
- SLURM jobs: running and pending counts, partitions, and the jobs grouped
  by job name.
- SSP tabs, the legend, and the grid. Each cell has one small square per
  expected file with the counts next to them: projection squares on top,
  then a thin line, then the aggregation squares colored by type (costs
  orange, levels purple, aggregated blue). The border gives the state:
  in progress, writing, projection complete, aggregation incomplete,
  aggregation complete.

The grid comes only from the output folders. Slurm and rcchelp are used
only for Resources and SLURM jobs.

## Expected files per unit

Taken from the official production outputs under /project/cil/gcp/outputs,
not from the cil2 or cil2-wpp test runs, and checked against finished
production leaves (every expected file present and not empty). They live
in the `files:` section of `manifest.yml`.

| Sector | Production folder used | Projection | Aggregation |
|---|---|---|---|
| Mortality | `mortality/impacts-darwin/montecarlo` (and the old monitor's `run_monitor.sh` counts, checked on `mortality_new-socioeconomics/impacts-darwin`) | 16: four age groups (combined, older, oldest, young) times four variants (full adaptation, histclim, incadapt, noadapt) | 36: 4 costs (`<age>-costs`), 16 levels, 16 aggregated |
| Agriculture | `agriculture/impacts-mealy/montecarlo/<crop>-2025` and `<crop>-2025_1pct_winsorization` | 4: `<crop>-<id>` in the four variants | 12: 4 costs (`adaptation_costs`, its aggregated file, and the winsorized `fulladaptcosts` pair), 8 aggregated (four variants in the crop folder and four in the winsorized folder) |
| Energy | `energy_pixel_interaction/impacts-blueghost/median` | 4: the four variants per fuel | 4: levels and aggregated at the price014 price scenario, for full adaptation and histclim |
| Labor | `labor/impacts-woodwork/montecarlo/uninteracted_main_model_agnonag_27_28_41` | 5: full adaptation, histclim, incadapt, noadapt, histclim-noadapt | 30: 15 levels and 15 aggregated (each variant weighted by gdp, pop and wage) |

Not counted: mortality's polymins .csv files, its `-costs-levels` and
`-costs-aggregated` files (the old monitor did not count them either),
and the winsorized copies of the agriculture projection files.

Agriculture crop ids: cassava 110221; corn, rice, sorghum, soy 160221;
wheat 280823. If the new aggregation configs use another price scenario
for energy (the cil2 tests used MERGEETL60_<rcp>), only those four names
in the manifest need to change.

## Layout

```
monitor/
  manifest.yml          what the dashboard tracks (sectors, scenarios, GCMs, files, people)
  collect_status.py     scans the output folders, Slurm and rcchelp, writes site/data/
  make_mock_status.py   writes a realistic mock to site/mock/
  site/                 the static site (deployable as-is)
    index.html
    style.css
    app.js
    camel/              camel.svg (100 pieces per sector) and favicon.svg
    data/status.json    the real data the page reads
    data/details/...    file sizes and dates per cell, loaded on click
    mock/               the same files for the mock
```

## Running

On the cluster, from this directory:

```
module load python
source activate /project/cil/home_dirs/rcc/envs/impact-env/
python3 collect_status.py
```

From a Mac with the volume mounted (no Slurm there, so Resources and
SLURM jobs show n/a):

```
python3 collect_status.py --cil-root /Volumes/cil
```

The mock: `python3 make_mock_status.py`, then open the page with
`?source=mock`.

Preview locally:

```
cd site
python3 -m http.server 8000          # http://localhost:8000, or ?source=mock
```

## How the collector reads the folders

- It walks
  `<output_root>/<run type>/[<sub-model>/][<subdir>/][batch<N>/]<rcp>/<GCM>/<iam>/<SSP>/`.
  `subdir` is the folder the engine adds itself: median mode writes under
  an extra `median/` level, so the manifest sets `subdir: median` there.
- A file counts as present only if it exists and is not empty.
- `status-global.txt` gives finished stages and their times. A stage that
  a worker claimed (`status-<stage>.txt`) is running while files keep
  changing, and counts as stopped after 6 hours with no file changes.
- The time to finish comes from how many stage steps finished in the last
  24 hours.
- SUs to finish, per sector and run type, for the units whose projections
  are not done yet:
  - lower bound: remaining units x the median generate time per unit seen
    so far; upper bound: remaining units x the longest time seen so far;
  - a unit's time comes from its projection file dates: the files are
    written one after another, so the time from the first to the last of
    n files, times n / (n - 1), covers the whole run;
  - when nothing has finished yet, the lower bound uses the reference time
    per unit and the upper bound the job time limit, both set per sector in
    the manifest (`reference:`), with their sources written next to them:
    mortality 20.5 h, energy 6.5 h, labor 1.4 h, agriculture 2.1 h, from
    earlier production runs and the cil2 single run logs;
  - SUs = hours x billing (1 for these jobs). Aggregation is not included;
    it is much shorter than generate.
- Service units follow the RCC formula for non GPU jobs:
  SUs = ElapsedRaw / 3600 x billing, with billing read from each job's
  AllocTRES (not assumed equal to the CPUs). For example, a job on amd with
  billing=1, cpu=1, mem=45G that ran 36 h 25 s used 36.01 SUs. The sum
  covers every job on the cil account since `account.su_since`, per
  person and partition. The formula is applied on the partitions in
  `account.su_billing_partitions` (amd, caslake, amd-hm, and cil, which is
  counted the same way until RCC says otherwise). GPU jobs, bigmem, other
  partitions and jobs without a billing value are flagged with their
  elapsed hours instead of counted. The
  allocation and balance come from `rcchelp balance -a cil`, and storage
  from `rcchelp quota` (group filesets of the cil account).

## status.json format (schema 2)

The contract between the collector and the page; the mock follows it.

```jsonc
{
  "schema_version": 2,
  "source": "collector",             // "mock" or "collector"
  "generated_at": "2026-10-13T18:00:00Z",
  "scan_interval_hours": 4,
  "account": {
    "name": "cil",
    "allocation_status": "none",     // "ok", "none" (no allocation yet) or "unknown"
    "allocation_su": null, "used_su": null, "balance_su": null,
    "su_since": "2026-10-01",        // start of the cycle for core hours per person
    "storage": [                     // null when rcchelp could not be read
      {"label": "cil /project", "used": "412.6T", "quota": "500.0T", "used_pct": 82.5}
    ]
  },
  "people": [                        // only people in the manifest, by display name
    {"name": "Sebastian", "linked": true,
     "su_used": 219.4,               // SUs since su_since, all partitions
     "su_by_partition": {"amd": 150.2, "cil": 69.2},   // largest first
     "su_flagged": {"bigmem": {"jobs": 2, "hours": 30.5, "reason": "bigmem partition"}},
     "active_jobs": [{"job_name": "energy-median", "partition": "amd", "state": "RUNNING",
                      "tasks": {"running": 32, "queued": 0, "done": 16}, "elapsed_min": 1391.0}]}
  ],
  "other_users": {"users": 2, "su_used": 1850, "su_by_partition": {"amd": 1850}, "su_flagged": {}, "active_jobs": []},
  "sectors": {
    "mortality": {
      "label": "Mortality",
      "stages": ["generate", "aggregate"],
      "disabled_run_types": [],
      "files_spec": {"main": {"projection": ["..."], "costs": ["..."], "levels": ["..."], "aggregated": ["..."]}},
      "run_types": {
        "median": {
          "dims": {"models": ["main"], "cells": [{"ssp": "SSP3", "rcp": "rcp45", "iam": "low"}],
                   "gcms": {"rcp45": ["..."], "rcp85": ["..."]}, "batches": null},
          "root": "/project/cil/gcp/outputs_newsocioeconomics/mortality/median",
          "subdir": "median",
          "counts": {"not_started": 0, "running": 0, "partial": 0, "done": 0, "failed": 0, "total": 520},
          "eta_hours": null, "eta_basis": null,
          "su_estimate": {"remaining": 520, "hours_low": 20.5, "hours_high": 36, "su_low": 10660,
                          "su_high": 18720, "source": "reference",   // or "observed"
                          "basis": "520 units left x 20.5 h (reference) to 36 h (job limit), 1 SU per hour"},
          "units": [                 // only units with something on disk
            {"model": "main", "ssp": "SSP3", "rcp": "rcp45", "iam": "low", "gcm": "CCSM4", "batch": null,
             "state": "partial",     // not_started|running|partial|done|failed, from the folder
             "fail_reason": null,
             "stages": {"generate": {"state": "done", "finished": "2026-10-13T17:32:54Z"},
                        "aggregate": {"state": "not_started"}},
             "files": {"projection": {"found": 16, "total": 16}, "costs": {"found": 0, "total": 4},
                       "levels": {"found": 0, "total": 16}, "aggregated": {"found": 0, "total": 16}},
             "bits": "1111111111111111000..."}   // one character per expected file, in files_spec order
          ]
        }
      }
    }
  }
}
```

`details/<sector>/<run type>/<sub-model>.json` (and
`<sub-model>/batch<N>.json` for montecarlo) maps
`"<SSP>|<rcp>|<iam>|<GCM>"` to one entry per expected file, in files_spec
order: `[size in bytes, written time in Unix seconds]`, or `0` if missing.

## Deploying to Vercel

From a Mac, in `site/`:

```
npx vercel --prod
```

Run the collector on the cluster first; the repo is on the shared volume,
so the Mac sees the new `data/` at once.
