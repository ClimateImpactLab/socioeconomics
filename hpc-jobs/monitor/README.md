# AMEL run-status monitor

A status dashboard for the new socioeconomics projection runs of the four
AMEL sectors (agriculture, mortality, energy, labor). For each sector and
run type it shows every unit of work in two views:

- Files (default): how many of the expected output files exist for each
  unit, split into projection files and aggregation files. Cells fill in
  as files appear on disk. A file counts only if it exists and is not
  empty.
- Jobs: the Slurm state of each unit (not started, queued, running, done,
  failed, partial), one stripe per pipeline stage.

Navigation is a zoomable hierarchy and every level fits the screen with no
scrolling. The first view is one block per sector. Clicking a block zooms
in: sector, then run type, then sub-model (crops, fuels), then scenario
(SSP and RCP with IAM), then GCM, then batch for montecarlo, down to the
single unit. Levels that do not apply are skipped. Each block shows the
same progress, aggregated from the units below it. A breadcrumb at the top
goes back up with one click and the browser back button works too, so any
level can be bookmarked. At the last level, clicking a unit opens a panel
with the full expected file list (present or missing), stage times, memory
use, job id and log file. Summary cards for the current level, an
estimated time to finish, and service-unit (SU) usage are always visible.
The dashboard shows run status only, never projection results.

The expected files per sector, stage and adaptation variant live in the
manifest (`files:` section). They were derived from finished leaves under
/project/cil/gcp/outputs/cil2 and verified to match them exactly. For
agriculture, the aggregation side includes the files written to the
sub-model's -1pct_winsorization twin directory; those names carry a
winsorized/ prefix in the dashboard.

## Layout

```
monitor/
  manifest.yml          what the dashboard tracks (sectors, scenarios, GCMs, people)
  make_mock_status.py   writes a realistic mock site/status.json from the manifest
  site/                 the static site (deployable as-is)
    index.html
    style.css
    app.js
    status.json         the data the site reads; mock now, real collector later
```

## How it fits together

1. `manifest.yml` describes the run universe: sectors and their sub-models
   (crops, fuels), pipeline stages, run types, the valid SSP-RCP pairs, both
   IAMs, the GCM lists per RCP, the Monte Carlo batch count, and the people
   to show in the SU panel. Nothing about the universe is hardcoded in code.
2. A collector (next step, runs on the cluster under scrontab every 4 hours)
   will read the manifest, scan the output trees and `status-global.txt`
   files, query squeue and sacct, and write `status.json`.
3. The site is static. It fetches `status.json` at load time and renders it.
   Updating the data never requires a redeploy.

Until the collector exists, `make_mock_status.py` produces a `status.json`
with the same format and a realistic mix of states:

```
python3 make_mock_status.py          # writes site/status.json (seeded, repeatable)
python3 make_mock_status.py --seed 7 # different mix
```

Preview locally:

```
cd site
python3 -m http.server 8000          # then open http://localhost:8000
```

## status.json format

This format is the contract between the collector and the site. The mock
already follows it exactly.

```jsonc
{
  "schema_version": 1,
  "source": "mock",                  // "mock" or "collector"
  "generated_at": "2026-10-03T18:00:00Z",
  "scan_interval_hours": 4,
  "account": {
    "name": "cil",
    "allocation_su": 5000000, "used_su": 280930, "balance_su": 4719070
  },
  "people": [
    {"name": "Sebastian", "username": null, "su_used": 61789}
  ],
  "sectors": {
    "mortality": {
      "label": "Mortality",
      "stages": ["generate", "aggregate"],
      "files_spec": {                // expected files per unit, by sub-model
        "main": {
          "projection": ["Agespec_interaction_response-combined.nc4", "..."],
          "aggregation": ["Agespec_interaction_response-combined-levels.nc4", "..."]
          // {rcp} in a name is replaced by the unit's RCP (energy).
          // winsorized/ prefix marks files in the -1pct_winsorization twin
          // directory (agriculture).
        }
      },
      "run_types": {
        "single": {
          "dims": {                  // the full expected universe for the grid
            "models": ["main"],      // crops/fuels; "main" = no sub-model
            "cells": [{"ssp": "SSP3", "rcp": "rcp45", "iam": "low"}],
            "gcms": {"rcp45": ["CCSM4"], "rcp85": ["CCSM4"]},
            "batches": null          // 15 for montecarlo (batch0..batch14)
          },
          "counts": {"not_started": 0, "queued": 0, "running": 0,
                     "partial": 0, "done": 16, "failed": 0, "total": 16},
          "eta_hours": null,         // null when nothing is left or nothing moves
          "eta_basis": null,         // short note on how the estimate was made
          "su_used": 2400,
          "units": [                 // sparse: units never started are omitted
            {
              "model": "main", "ssp": "SSP3", "rcp": "rcp45", "iam": "low",
              "gcm": "CCSM4", "batch": null,
              "state": "done",       // not_started|queued|running|partial|done|failed
              "fail_reason": null,   // sacct state when failed (OUT_OF_MEMORY, ...)
              "stages": {
                "generate": {
                  "state": "done", "job": "59931234_7",
                  "elapsed_min": 126.0, "max_rss_gb": 41.2, "req_mem_gb": 64,
                  "finished": "2026-09-24T02:56:12Z"
                },
                "aggregate": {"state": "done", "...": "..."}
              },
              "files": {             // counts of non-empty expected files
                "projection": {"found": 22, "total": 22},
                "aggregation": {"found": 34, "total": 44,
                                "missing": ["names, only when 0 < found < total"]}
              },
              "log": "sg_59931234_7.out"
            }
          ]
        }
      }
    }
  }
}
```

State rules: a unit is `done` when every required stage is done, `failed`
when a stage failed and was not retried successfully, `running`/`queued`
when a job is active or pending for it, `partial` when some stages finished
but nothing is active, and `not_started` otherwise. The site derives the
grid from `dims` and treats every unit not listed in `units` as not started.

File rules: the collector counts a file as present only if it exists and
has size above zero. The `missing` list is included only when a group is
partly complete; the site derives the full missing list from `files_spec`
when `found` is 0, and an empty one when `found` equals `total`.

## Deploying the site to Vercel (first version, mock data)

From a Mac, in this directory:

```
cd site
npx vercel login          # once; use the account that owns the project
npx vercel                # creates the project; accept the defaults
npx vercel --prod         # publish to the production URL
```

There is no build step; answer "no" if asked about build settings (it is a
plain static site). To update the deployed mock later, rerun
`python3 make_mock_status.py` and `npx vercel --prod`.

Later, when the real collector writes `status.json` somewhere public (for
example a data branch on GitHub), change the fetch path at the top of
`boot()` in `app.js` to that URL. The site itself will not need to change
otherwise.
