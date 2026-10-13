# AMEL run-status monitor

A status dashboard for the new socioeconomics projection runs of the four
AMEL sectors (agriculture, mortality, energy, labor). It shows run status
only, never projection results. Everything is on one page:

- Summary cards for the selected sector and run type: files present,
  units with all files, units being written, failed units, and an
  estimated time to finish.
- The cluster strip (open by default, can be collapsed): the jobs each
  person has running or queued on the cil account right now, and the
  account's service units (allocation, used, remaining balance, and use
  per person since a start date).
- The progress grid: one cell per unit of work (scenario, IAM, GCM, and
  batch for montecarlo). Each cell has two bars, projection files on top
  and aggregation files below, filling in as files appear on disk. The
  whole grid fits the screen; click a scenario header to zoom into it,
  and click a cell for the list of expected files (present or missing)
  and the state of each stage.

The grid comes only from the output folders. Slurm is used only for the
cluster strip.

Opening a sector selects its montecarlo tab, or median when the sector has
no montecarlo. Run types a sector does not have (energy montecarlo) are
shown as greyed-out tabs.

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
  collect_status.py     scans the output folders and Slurm, writes status.json
  make_mock_status.py   writes a realistic mock to site/status.mock.json
  site/                 the static site (deployable as-is)
    index.html
    style.css
    app.js
    status.json         the data the site reads
    status.mock.json    the mock, kept separate
```

## How it fits together

1. `manifest.yml` describes the run universe: sectors and their sub-models
   (crops, fuels), pipeline stages, run types, the valid SSP-RCP pairs, both
   IAMs, the GCM lists per RCP (surrogates included), the Monte Carlo batch
   count, the expected files per unit, and the people to show in the
   cluster strip. `username` links a display name to a cluster user and is
   never published. Nothing about the universe is hardcoded in code.
2. `collect_status.py` reads the manifest and writes `site/status.json`.

   For the grid, from the output folders only:
   - walks `<output_root>/<run type>/[<sub-model>/][<subdir>/][batch<N>/]<rcp>/<GCM>/<iam>/<SSP>/`.
     `subdir` is the folder the engine adds itself: median mode writes
     under an extra `median/` level, so the manifest sets `subdir: median`
     for that run type;
   - counts the expected files per unit (existing and not empty);
   - reads `status-global.txt` for finished stages and their times;
   - reads the `status-<stage>.txt` claim files that workers leave while
     they run: a claimed stage is running while files keep changing, and
     counts as stopped (failed) after 6 hours with no file changes and no
     finish marker;
   - estimates the time to finish from how many stage steps finished in
     the last 24 hours.

   For the cluster strip, from Slurm:
   - `squeue -r -A cil`: every running or queued task on the account,
     grouped into one row per job or array for each listed person, with
     job name, partition, state, task counts and elapsed time;
   - `sacct -a -A cil`: tasks that finished successfully (the "done"
     count), and core hours (elapsed time times allocated CPUs) of every
     job on the account since `account.su_since`, per person;
   - `rcchelp balance -a cil`: allocation, used and remaining balance.
     When the account has no allocation, rcchelp lists no line for it and
     the site shows "No allocation yet"; the use per person still shows.
3. The site is static. It fetches `status.json` at load time and renders it.
   Updating the data never requires a redeploy.

Run the collector on the cluster, from this directory:

```
module load python
source activate /project/cil/home_dirs/rcc/envs/impact-env/
python3 collect_status.py
```

impact-env is the same environment the projection jobs use and has
everything the collector needs (Python 3 and PyYAML). To test from a Mac
with the volume mounted (no Slurm there, so the cluster strip shows n/a):

```
python3 collect_status.py --cil-root /Volumes/cil
```

The mock is kept separate so the site can always be demoed:

```
python3 make_mock_status.py              # writes site/status.mock.json
cp site/status.mock.json site/status.json   # only if you want the mock shown
```

Preview locally:

```
cd site
python3 -m http.server 8000          # then open http://localhost:8000
```

## status.json format

This format is the contract between the collector and the site. The mock
follows it exactly.

```jsonc
{
  "schema_version": 1,
  "source": "collector",             // "mock" or "collector"
  "generated_at": "2026-10-13T18:00:00Z",
  "scan_interval_hours": 4,
  "account": {
    "name": "cil",
    "allocation_status": "none",     // "ok", "none" (no allocation yet) or "unknown" (rcchelp failed)
    "allocation_su": null,           // from rcchelp balance, only when status is "ok"
    "used_su": null,
    "balance_su": null,
    "su_since": "2026-10-01"         // start date of the use per person (manifest)
  },
  "people": [                        // only people listed in the manifest, in that order
    {
      "name": "Sebastian",           // display name; cluster usernames are never written
      "linked": true,                // false when the manifest has no username yet
      "su_used": 32399,              // core hours of all their jobs on the account since su_since
      "active_jobs": [               // running or queued right now, whatever the job name
        {
          "job_name": "energy-median", "partition": "caslake",
          "state": "RUNNING",        // RUNNING, or PENDING when no task has started
          "tasks": {"running": 11, "queued": 32, "done": 53},
          "elapsed_min": 1882.0      // longest elapsed among running tasks
        }
      ]
    }
  ],
  "sectors": {
    "energy": {
      "label": "Energy",
      "stages": ["generate", "aggregate"],
      "disabled_run_types": ["montecarlo"],   // shown as greyed-out tabs
      "files_spec": {                // expected files per unit, by sub-model
        "electricity": {
          "projection": ["FD_FGLS_inter_OTHERIND_electricity_TINV_clim.nc4", "..."],
          "aggregation": ["FD_FGLS_inter_OTHERIND_electricity_TINV_clim-MERGEETL60_{rcp}-levels.nc4", "..."]
          // {rcp} in a name is replaced by the unit's RCP.
          // winsorized/ prefix marks files in the -1pct_winsorization twin
          // directory (agriculture).
        }
      },
      "run_types": {
        "median": {
          "dims": {                  // the full expected universe for the grid
            "models": ["electricity", "other_energy"],   // "main" = no sub-model
            "cells": [{"ssp": "SSP3", "rcp": "rcp45", "iam": "low"}],
            "gcms": {"rcp45": ["ACCESS1-0", "..."], "rcp85": ["ACCESS1-0", "..."]},
            "batches": null          // 15 for montecarlo (batch0..batch14)
          },
          "counts": {"not_started": 874, "running": 32, "partial": 134,
                     "done": 0, "failed": 0, "total": 1040},
          "eta_hours": 348.5,        // null when nothing is left or nothing moved lately
          "eta_basis": "1946 stage steps left, 134 finished in the last 24 h",
          "units": [                 // sparse: units with nothing on disk are omitted
            {
              "model": "electricity", "ssp": "SSP3", "rcp": "rcp45", "iam": "low",
              "gcm": "surrogate_CanESM2_89", "batch": null,
              "state": "partial",    // not_started|running|partial|done|failed
              "fail_reason": null,   // set when failed, e.g. "aggregate ended as Incomplete"
              "stages": {
                "generate": {"state": "done", "finished": "2026-10-13T17:32:54Z"},
                "aggregate": {"state": "not_started"}
              },
              "files": {             // counts of non-empty expected files
                "projection": {"found": 4, "total": 4},
                "aggregation": {"found": 0, "total": 4,
                                "missing": ["names, only when 0 < found < total"]}
              }
            }
          ]
        }
      }
    }
  }
}
```

Unit states, all from the folder:
- `done`: every required stage is done (finish marker in
  `status-global.txt`, or all of the stage's files present);
- `running`: a stage is claimed and files changed in the last 6 hours;
- `failed`: the last marker for a stage is not the done word (for example
  `Incomplete`), or a claimed stage had no file changes for 6 hours;
- `partial`: some stages are done and nothing is running;
- `not_started`: nothing on disk.

Queued work cannot be seen in the folders, so the grid has no queued
state; queued jobs show in the cluster strip.

File rules: a file counts as present only if it exists and has size above
zero. The `missing` list is included only when a group is partly
complete; the site derives the full missing list from `files_spec` when
`found` is 0, and an empty one when `found` equals `total`.

Cluster strip rules: it uses Slurm only, for the cil account, and shows
only people listed in the manifest. `su_used` and `active_jobs` are null
when Slurm could not be read (for example when the collector runs on a
Mac), and the site shows "n/a". The use per person is plain core hours,
so it can differ from the official "Used" figure in `rcchelp balance`.

## Deploying the site to Vercel

From a Mac, in this directory:

```
cd site
npx vercel login          # once; use the account that owns the project
npx vercel                # creates the project; accept the defaults
npx vercel --prod         # publish to the production URL
```

There is no build step; answer "no" if asked about build settings (it is a
plain static site). To refresh the deployed data by hand: run the
collector on the cluster, then `npx vercel --prod` from the Mac (the repo
is on the shared volume, so the Mac sees the new `status.json` at once).

Later, when the collector writes `status.json` somewhere public (for
example a data branch on GitHub), change the fetch path at the top of
`boot()` in `app.js` to that URL. The site itself will not need to change
otherwise.
