# AMEL run-status monitor

A status dashboard for the new socioeconomics projection runs of the four
AMEL sectors (agriculture, mortality, energy, labor). It shows run status
only, never projection results. The page follows the design of the old
mortality monitor (/project/cil/home_dirs/scadavidsanchez/repos/mortality-monitor):

- The camel logo at the top: a lean two-humped camel split into five body
  parts, one per sector: front legs mortality (red), humps coastal (blue),
  back legs agriculture (green), neck and head energy (yellow), body labor
  (grey). Each part fills from the ground up with the sector's share of
  projection files present and pulses softly while projections are
  running; it is solid when all projection files are there, and gets a
  fine striped texture when all aggregation files are there too. Coastal
  is not tracked yet. The tab icon is the same camel in the five colors.
- A row of small cards for the selected sector and run type: expected
  units, complete, partial, not started, projection and aggregation
  progress, units being written, and an estimated time to finish.
- Sector and run type tabs (montecarlo by default, median for energy,
  which has no montecarlo; its montecarlo tab is greyed out), and a
  sub-model tab for crops and fuels.
- An info bar with the path of the clicked cell, and a detail panel that
  lists the cell's files grouped into Projections, Aggregation (levels and
  aggregated) and Costs, each with a small dot, the file size and the date
  it was written.
- Resources: storage and service units of the cil account, as thin bars.
  When the account has no allocation, it says "No allocation yet".
- SLURM jobs: running and pending counts, partitions, one bar splitting
  core hours by person (display names; everyone not in the manifest is
  "Other users"), and the jobs grouped by job name.
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
- Service units are core hours (elapsed time times allocated CPUs) on the
  cil partition since `account.su_since`, per person, from sacct. The
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
    "su_partition": "cil",           // core hours count only this partition
    "storage": [                     // null when rcchelp could not be read
      {"label": "cil /project", "used": "412.6T", "quota": "500.0T", "used_pct": 82.5}
    ]
  },
  "people": [                        // only people in the manifest, by display name
    {"name": "Sebastian", "linked": true, "su_used": 219,
     "active_jobs": [{"job_name": "energy-median", "partition": "amd", "state": "RUNNING",
                      "tasks": {"running": 32, "queued": 0, "done": 16}, "elapsed_min": 1391.0}]}
  ],
  "other_users": {"users": 2, "su_used": 1850, "active_jobs": []},
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
