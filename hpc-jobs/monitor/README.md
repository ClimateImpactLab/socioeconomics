# CIL | Projections - New Socioeconomics: run-status monitor

A status dashboard for the new socioeconomics projection runs of the four
AMEL sectors (agriculture, mortality, energy, labor). It shows run status
only, never projection results. The page follows the design of the old
mortality monitor (/project/cil/home_dirs/scadavidsanchez/repos/mortality-monitor):

- The camel at the top (from camel-progress-kit): a two-humped camel made
  of 100 pieces per sector: head and neck energy (yellow), shoulder and
  front legs mortality (red), back and humps coastal (blue), belly labor
  (grey), hindquarters, back legs and tail agriculture (green). Pieces fill
  from the bottom up with the sector's share of projection files in its
  main run only (montecarlo for agriculture, mortality and labor, median
  for energy; singles and other run types do not count) and pulse
  softly while projections run; the sector turns solid when all projection
  files are there, and gets fine light stripes when aggregation is complete
  too. Coastal is not tracked yet. The kit's walking animation is paused
  for now (`CAMEL_WALK` in app.js); when on, the camel walks only while
  projection files are being written in the output folders, the same
  signal as the grid's "writing" state.
- Next to the camel, under the title, a compact table: one row per sector
  in camel order with its color mark, which pulses softly in the sector
  color while the sector is active (jobs running or projection files
  written in the last day) and is still and dim otherwise. Columns:
  - Projection and Aggregation: percent and file counts for the sector's
    main run ("100% (64/64)");
  - Single, Median and Montecarlo: a line symbol per run type, a check when
    its projection is complete, an x when it is not (started or not), a
    dash when the run type does not apply (montecarlo for energy), and a
    small circle in the sector color that turns slowly while the run type
    is being computed (projection files written in the last day or a unit
    being written now; still for people who ask for reduced motion); the
    tooltip gives the percents;
  - SUs to finish: the low to high range, summed over the sector's run
    types from the same estimate as the cards (when one of
    them has no estimate it reads "no data").
  Below the rows, a thin line and a total row: the sum of the SUs to finish
  over all sectors with an estimate, with "of X available" (X being RCC's
  remaining balance) on its own line below. A short grey note says that
  percents refer to each sector's main run (montecarlo; median for energy).
  Coastal reads "not tracked (yet)" across its row. On phones the counts go
  under each percent, the table scrolls sideways in its own box, and the
  total is a line under it.
- The CIL logo at the top right (site/cil-logo.svg), inverted and
  desaturated in dark mode, following the same light and dark switch. The tab icon is
  the kit's color favicon in the same five colors (site/camel/).
- Navigation: a tree on the left lists the sectors as badges in their
  camel colors, in camel order (Coastal, Agriculture, Mortality, Energy,
  Labor). A sector opens into its run types (single, median, montecarlo),
  with none picked: the grid shows only once a run type is picked, and a
  sub-model when its grid has several (fuels, crops); until then a short
  note sits where the grid would be ("Select a run type to see progress",
  "Select a sub-model to see progress"). A run type also opens an Aggregation
  branch with its scenarios. Options that do not apply or have no files
  yet are shown dimmed and cannot be picked (montecarlo under energy is
  "n/a"); an unavailable sector (Coastal) keeps its camel color, only
  dimmed. While a run has no aggregation files, its Aggregation branch
  stays folded into one dimmed line ("none yet", or "-" for sectors whose
  file names carry no scenario). Clicking a picked sector, run type or
  sub-model again clears it and hides the grid. Each branch shows its P
  and A figures, and a short key under the list says what P and A mean.
  The tree is built from the data, so each sector gets its own branches.
  The current path shows at the top of the grid ("Energy / median /
  electricity / price014"). On phones, held upright or sideways (narrow up
  to 600px, or short up to 500px), the tree folds into a menu at the top
  that shows the same path: tap it to open, and picking a leaf closes it,
  so the grid keeps the full width. Sector progress counts the main run only
  (montecarlo, or median for energy).
- An info bar with the path of the clicked cell, and a detail panel that
  lists the cell's files grouped into Projections, Aggregation (levels and
  aggregated) and Costs, each with a small dot, the file size and the date
  it was written.
- Resources: storage of the cil account as thin bars, then service units,
  RCC's official numbers only, in three parts:
  - Total: from `rcchelp balance -a cil`, used out of the allocation and
    the balance left, such as "42,872 / 1,200,000 SU, 1,157,128 left". A
    small "i" says these are RCC's official numbers, updated in batches.
  - Per user: from `rcchelp usage -a cil -byuser`, one segment per user
    with billed use, in the shared user colors, and a key with each
    user's billed SUs and share.
  - Per partition: from `rcchelp usage -a cil -bypartition`, one textured
    segment per partition, with each partition's billed SUs and share.
  RCC gives no user by partition, so these stay as separate bars. `-byjob`
  is not used: it fails on RCC's side. Each output is read by its header
  (the line starting "User Usage" or "Partition Usage", then one line per
  name, then "Total Usage"); a part that cannot be read in a scan shows
  "not available in this scan". In each bar, hovering a segment marks it
  in its key and hovering the key marks the segment; a click keeps the
  highlight until the same thing is clicked again.
- Aggregation scenarios: progress and every count use only the main
  scenario in the aggregation file names, set per sector in the manifest
  (`aggregation_scenario`, price014 for energy). Energy aggregation has 8
  files per unit: levels and aggregated for the main variant, histclim,
  global and global-histclim. When the collector finds aggregation files
  of other scenarios in the same folders (such as MERGEETL60_rcp45 in rcp45
  folders and MERGEETL60_rcp85 in rcp85 ones, kept as one scenario and
  shown by its name only, MERGEETL60; the cell details keep the full file
  names):
  - the scenarios are picked in the tree's Aggregation branch, which
    starts on the main one: "price014 (main)" and "MERGEETL60", each with
    its A figure;
  - What follows the picked scenario: the grid cells, the column header
    counts, the SSP badge counts, the sub-model counts in the tree, the hover
    summary and the cell details (which list the picked scenario's
    aggregation files only, all 8 for energy, with sizes and dates, and
    name it, marked "not counted").
  - What always counts the main scenario: the overall progress, that is
    the summary cards, the sector and run type figures in the tree and the
    camel table.
    While another scenario is picked, their aggregation figure reads
    "Aggregation (main)".
  It works for any sector whose aggregation file names carry a scenario:
  set `aggregation_scenario` for it.
- Other files: the cell details also list, under the projection files,
  any `.nc4` file in the folder that is not expected and is not another
  scenario's aggregation file (for energy: `-global.nc4`,
  `-global-histclim.nc4`, `-incadapt-histclim.nc4` and
  `-noadapt-histclim.nc4`), in a grey group "Other files (not counted)"
  with sizes and dates. They never count toward the progress.
- Resources and SLURM jobs start collapsed.
- Run types can be left out with `enabled: false` under `run_types` in the
  manifest. quick_test is off this way: not in the tree, and not in any count,
  percent, card or SU estimate. Set it back to true to show it again.
- Phones and tablets: the grid shrinks to fit the screen width, down to
  60%; wider grids (montecarlo) scroll sideways inside their own box, with
  the climate model names pinned on the left. On a phone held upright the
  grid is hidden and a short note asks to turn the phone. Taps do what
  hover does: a tap on a cell shows its summary and files, and a tap on
  the SU bar marks its user and partition.
- SLURM jobs: task counts for the account, each partition and each user,
  as small letter badges (R running, P pending, D done, F failed, with a
  key above the table), and a table of every running or queued job: job
  id, name, user, partition, state, task badges, when it started (the
  start of its first task, empty while pending), elapsed time, CPUs and
  memory requested (per task for arrays), time limit and time left
  before the limit (from squeue; for an array, the task closest to its
  limit). A job that allows several partitions shows each one once, with
  how many of its tasks run there ("caslake 12, amd 3"); partitions it may
  use but has nothing on yet follow without a count. Time left shows in
  amber when it is under 2 hours. Below it, a collapsed
  list of jobs on the account that ended badly (timeout, out of memory,
  failed, cancelled) in the last `account.ended_badly_days` days: job id,
  name, user, partition, how it ended and how long it ran. Array tasks
  that ended the same way are grouped under their job id.
- A row of small cards for the selected sector and run type, right above
  the grid: expected units, complete, partial, not started,
  projection and aggregation progress, units being written, time to
  finish, and SUs to finish. Time to finish covers the projection only;
  aggregation shows as "not started" (or its units done) and is not
  added in. Its tooltip gives the numbers and the pace used.
- SSP, RCP and IAM badges under the sector list, for the run type
  picked: three rows of round badges, SSPs, then RCPs, then IAMs, with no
  counts (the grid headers show them). SSP badges keep their soft colors
  (SSP2 #86BDE0, SSP3 #CC956B, SSP4 #A6B990), RCP badges the grid's blue
  and red, and IAM badges are white with blue text for low and red for
  high. Each badge turns on or off on its own, and the grid shows the
  columns whose SSP, RCP and IAM are all on. A run type starts with SSP2, both RCPs and both IAMs on. On
  phones the badges are in the menu with the tree.
- Speed: the grid's grouped counts are added up once per scan, run type,
  sub-model and aggregation scenario. The grid is built once per run with
  every column, each cell's file squares drawn as one small cached picture,
  so turning a badge on or off only rewrites one style rule that shows or
  hides columns, and a highlight only sets an attribute on the grid. On the
  largest grid (mortality montecarlo, about 6,000 cells) a click takes
  about 0.03 to 0.13 s.
- Highlight: a row above the grid, "Highlight: All | Incomplete | Complete
  | Being written | Failed | Not started", each with its count of cells in
  the columns shown. The grid stays whole; cells of other states are shown
  blank (the page background), so the matching ones stand out. It combines
  with the SSP, RCP and IAM picks. All is the default.
- Cells with projection and aggregation complete have their green border
  and a soft green inside, like cells being written have their colored
  border and soft fill.
- The legend and the grid. Each scenario column header shows its SSP,
  RCP and IAM as small copies of the badges, in the same colors, wrapping
  to a second line in narrow columns. Below them it shows P, projection
  files present out of expected, and A, aggregation files present out of
  expected, for example "P 917/4,160, A 0/4,160"; the key under the tree
  says so. Each cell has one small square per
  expected file with the counts next to them: projection squares on top,
  then a thin line, then the aggregation squares colored by type (costs
  orange, levels purple, aggregated blue). The border gives the state:
  in progress, writing, projection complete, aggregation incomplete,
  aggregation complete. The grid scrolls inside its own box, so the
  column headers (scenarios, IAMs, batches) and the row labels (climate
  models) stay in view. Hovering or clicking a cell softly marks its whole
  row and column, with its climate model and its scenario headers.

The grid comes only from the output folders. Slurm and rcchelp are used
only for Resources and SLURM jobs.

Colors and textures: each sector, state and user has one color, and each
partition one texture, used the same way everywhere on the page (badges,
bars, keys, tables). States are set once in style.css (`--st-*`) and
partition textures as `.ptex-*`; users get colors from a palette that
avoids the state hues. The tree and the camel table follow the camel
order: Coastal, Agriculture, Mortality, Energy, Labor. Coastal shows "not
tracked (yet)".

## Expected files per unit

Taken from the official production outputs under /project/cil/gcp/outputs,
not from the cil2 or cil2-wpp test runs, and checked against finished
production leaves (every expected file present and not empty). They live
in the `files:` section of `manifest.yml`.

| Sector | Production folder used | Projection | Aggregation |
|---|---|---|---|
| Mortality | `mortality/impacts-darwin/montecarlo` (and the old monitor's `run_monitor.sh` counts, checked on `mortality_new-socioeconomics/impacts-darwin`) | 16: four age groups (combined, older, oldest, young) times four variants (full adaptation, histclim, incadapt, noadapt) | 36: 4 costs (`<age>-costs`), 16 levels, 16 aggregated |
| Agriculture | `agriculture/impacts-mealy/montecarlo/<crop>-2025` and `<crop>-2025_1pct_winsorization` | 4: `<crop>-<id>` in the four variants | 12: 4 costs (`adaptation_costs`, its aggregated file, and the winsorized `fulladaptcosts` pair), 8 aggregated (four variants in the crop folder and four in the winsorized folder). Spring and winter wheat are not aggregated themselves: 2 costs (`adaptation_costs` and the winsorized `fulladaptcosts`), no aggregated. They are combined into `wheat_combined`, tracked as its own sub-model with the full 12. |
| Energy | `energy_pixel_interaction/impacts-blueghost/median` | 4: the four variants per fuel | 8: levels and aggregated at the price014 price scenario, for the main variant, histclim, global and global-histclim |
| Labor | `labor/impacts-woodwork/montecarlo/uninteracted_main_model_agnonag_27_28_41` | 4: full adaptation, histclim, incadapt, noadapt | 31: 15 levels and 16 aggregated (each variant weighted by gdp, pop and wage, plus the histclim-noadapt file, which a separate step after the projection builds with `make_noadapt_histclim.py`) |

Aggregation types per sector: mortality has costs, levels and aggregated;
agriculture costs and aggregated (no levels); energy levels and aggregated
(no costs); labor levels and aggregated, weighted by gdp, pop and wage (no
costs). The legend, the cell squares, the counts and the detail panel show
only the types a sector has. Each list was checked against several finished
production leaves: every expected file is there, for every type.

Not counted: mortality's polymins .csv files, its `-costs-levels` and
`-costs-aggregated` files (the old monitor did not count them either),
the winsorized copies of the agriculture projection and adaptation_costs
files, and energy's `-global` files, which belong only to the global run.

Agriculture crop ids: cassava 110221; corn, rice, sorghum, soy 160221;
wheat 280823. If the new aggregation configs use another price scenario
for energy (the cil2 tests used MERGEETL60_<rcp>), only those four names
in the manifest need to change.

## Layout

```
monitor/
  manifest.yml          what the dashboard tracks (sectors, scenarios, GCMs, files, SU rules)
  collect_status.py     scans the output folders, Slurm and rcchelp, writes site/data/
  monitor_job.sbatch    self-scheduling Slurm job: queues its next run, then runs run_monitor.sh
  run_monitor.sh        one run: collector, then publish
  monitor_watchdog.sh   hourly crontab check: submits a run if none is queued or running
  publish_data.sh       pushes site/data/ to the monitor-data branch
  make_mock_status.py   writes a realistic mock to site/mock/
  site/                 the static site (deployable as-is)
    index.html
    style.css
    app.js
    camel/              camel.svg (100 pieces per sector) and favicon.svg
    data/status.json    local copy of the data (fallback; the page reads monitor-data first)
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

- It walks `<output_root>/<layout>/[batch<N>/]<rcp>/<GCM>/<iam>/<SSP>/`,
  where `layout` comes from each sector in the manifest. The default is
  `{run_type}/{model}/{subdir}`: mortality, agriculture and labor, where
  the median runs write under an extra `median/` level (`subdir: median`).
  Energy uses `{model}/{run_type}`, each fuel first and no extra median
  level: `energy/electricity/single/rcp45/...` and
  `energy/electricity/median/rcp45/...`.
- Scenarios: SSP2, SSP3 and SSP4, each with rcp45 and rcp85 and both IAMs
  (12 scenarios), as in the original specifications.
- A file counts as present only if it exists and is not empty.
- `status-global.txt` gives finished stages and their times. A stage that
  a worker claimed (`status-<stage>.txt`) is running while files keep
  changing, and counts as stopped after 6 hours with no file changes.
- Time per unit, used for both the time to finish and the SUs to finish.
  Observed times count only with at least 10 finished units of that run,
  and only when they are within a factor of 2 of the reference time in the
  manifest (when there is one); otherwise the reference is used. Sources,
  in this order:
  - tasks of one unit each (single and quick_test, set with
    `one_unit_per_task` in the manifest, or any run with about as many
    tasks as units started, such as the mortality montecarlo): sacct,
    elapsed hours x billing of the finished tasks only, median (low) to
    longest (high). Running tasks are left out, since their unit is not
    done yet; counting their time so far against the finished units alone
    roughly doubled the mortality figure;
  - tasks of several units each (such as the energy median): sacct, the
    SUs of all the run's tasks over the units finished, only once none of
    the run's tasks is still running.
    A task belongs to the run
    when its job name matches the sector's `job_names` for that run type
    (patterns such as `*energy*med*` and `*mort*mc*`, in both word orders,
    case ignored; names matching `account.job_names_exclude`, such as
    aggregation and post jobs, never count; a name matching several run
    types goes to montecarlo, then median, then quick_test, then single)
    and it started since the run's start: `run_started` when set, or else
    the run's first projection file less the job time limit;
  - otherwise, file dates: the time from the first to the last projection
    file of each finished unit (times n / (n - 1) for n files), plus the
    start up time measured from the same sector's singles (a single task's
    elapsed time less its file span), which file dates miss;
  - with none of these, the reference time per unit in the manifest
    (`reference:`), and its longest reference time (or the job time limit)
    as the upper bound: mortality 20.5 h (longest 23.7 h), energy 6.5 h
    (job limit 12 h or 36 h), labor 1.4 h (longest 1.42 h). Agriculture has
    no reference time yet, so it shows "not known yet".
  The tooltips of the time to finish and SUs to finish cards say which
  source was used.
- The time to finish covers the projection units left only. The pace is
  either the units being written now over the time per unit ("writing",
  steady because it does not jump with bursts of finishes), or the units
  finished in the last 6 hours ("recent", used with at least 3 of them).
  With less data than that it shows "not enough data yet". A unit's finish
  time is its status marker, or else its newest projection file.
- SUs to finish, per sector and run type, for the units whose projections
  are not done yet, as two numbers:
  - compute hours: units left x hours per unit x billing, as Slurm counts
    them;
  - SUs, with RCC's billing formula: units left x hours per unit x
    max(cores requested, RAM requested / RAM per core), on the partitions
    RCC bills (`account.rcc_billing.billed_partitions`, now only caslake);
    other partitions count 0 SUs. RAM per core is set per partition in
    `account.rcc_billing.ram_per_core_gb`: 3.75 GB for caslake, which
    matches RCC's bills exactly (1 core and 15G billed 4 SUs per hour, 1
    core and 45G billed 12). The partition, cores and memory come from the
    run's matched jobs in sacct, which take priority, or else from the
    sector's `request` in the manifest, from the jobs in use: agriculture
    amd, 1 core, 28G; labor amd, 1 core, 60G; energy single amd, 1 core,
    15G; energy median caslake, 1 core, 15G; mortality caslake, 1 core, 45G.
    The amd ones count 0 SUs while amd is not billed.
  The card shows the SUs, with the compute hours under it, and a small "i"
  with the formula. Aggregation is not included; it is much shorter than
  the projection. The time to finish is not affected.
- The allocation and balance come from `rcchelp balance -a cil`, the
  billed use from `rcchelp usage -a cil -byuser` and `-bypartition`, and
  storage from `rcchelp quota` (group filesets of the cil account). Every
  user with jobs or billed use on the account is listed by cluster
  username, which keeps each user's color the same across the page.

## status.json format (schema 8)

The contract between the collector and the page; the mock follows it.

```jsonc
{
  "schema_version": 8,
  "source": "collector",             // "mock" or "collector"
  "generated_at": "2026-10-13T18:00:00Z",
  "scan_interval_hours": 1,
  "account": {
    "name": "cil",
    "allocation_status": "ok",       // "ok", "none" (no allocation listed) or "unknown"
    "allocation_su": 1200000, "used_su": 0, "balance_su": 1200000,
    "highlight_user": "cadavidsanchez",
    "billed": {                      // what RCC bills (rcchelp usage); each part null when it could not be read
      "by_user": {"total": 42871.57, "by": {"sarahmad": 27632, "adwaitsinha": 15239}},
      "by_partition": {"total": 42871.57, "by": {"caslake": 42871}}
    },
    "storage": [                     // null when rcchelp could not be read
      {"label": "cil /project", "used": "412.6T", "quota": "500.0T", "used_pct": 82.5}
    ]
  },
  "users": [                         // every user with jobs or billed use, by cluster username; null without Slurm
    {"user": "someuser",
     "active_jobs": [{"job_id": "59946806", "job_name": "energy-median", "partition": "caslake,amd", "state": "RUNNING",
                      "running_on": {"caslake": 28, "amd": 4},   // running tasks per partition
                      "started": "2026-10-18T13:05:00Z",         // start of the first task; null while pending
                      "tasks": {"running": 32, "queued": 0, "done": 16, "failed": 1},   // failed: failed, timeout, out of memory, node failure
                      "elapsed_min": 1391.0,
                      "cpus": 1, "mem": "45G",   // requested, per task
                      "limit_min": 2160.0,    // null with no limit
                      "left_min": 769.0}]}    // smallest among running tasks; null while pending
  ],
  "ended_badly": [                   // newest first, at most 25; null without Slurm
    {"job_id": "59939384", "job_name": "labor-median", "user": "someuser", "partition": "caslake",
     "ended": "timeout",              // timeout, out of memory, failed, cancelled or node failure
     "tasks": 11, "elapsed_min": 2160.0, "end": "2026-10-13T13:12:40Z"}   // UTC
  ],
  "ended_badly_days": 3,
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
          "model_dirs": {"main": "/project/cil/gcp/outputs_newsocioeconomics/mortality/median/median"},
          "agg_scenarios": {"main": "price014", "others": ["MERGEETL60_{rcp}"]},   // null without aggregation_scenario
                                     // each sub-model's folder, down to the batch or rcp folders
          "counts": {"not_started": 0, "running": 0, "partial": 0, "done": 0, "failed": 0, "total": 520},
          "eta_hours": 5.4,             // projection only; null when there is not enough data yet
          "eta_method": "writing",      // "writing", "recent" or null
          "eta_basis": "178 projection units left; 146 being written now, ...",
          "aggregation": {"started": false, "done": 0},   // units with aggregation done
          "unit_time_source": "sacct",  // where the time per unit came from; null when not known
          "su_estimate": {"remaining": 520, "hours_low": 20.5, "hours_high": 36,
                          "compute_low": 10660, "compute_high": 18720,   // compute hours to finish
                          "su_low": 127920, "su_high": 224640,           // RCC's formula; null when the request is not known
                          "request": {"partition": "caslake", "cpus": 1, "mem_gb": 45, "source": "manifest"},   // or "sacct"
                          "rate": 12.0,                                  // SUs per hour of one task
                          "source": "reference",   // "sacct", "file dates", "reference" or "unknown"
                          "basis": "520 units left x 20.5 h (reference) to 36 h (job limit), 1 SU per hour"},
          "units": [                 // only units with something on disk
            {"model": "main", "ssp": "SSP3", "rcp": "rcp45", "iam": "low", "gcm": "CCSM4", "batch": null,
             "state": "partial",     // not_started|running|partial|done|failed, from the folder
             "fail_reason": null,
             "stages": {"generate": {"state": "done", "finished": "2026-10-13T17:32:54Z"},
                        "aggregate": {"state": "not_started"}},
             "files": {"projection": {"found": 16, "total": 16}, "costs": {"found": 0, "total": 4},
                       "levels": {"found": 0, "total": 16}, "aggregated": {"found": 0, "total": 16}},
             "bits": "1111111111111111000...",   // one character per expected file, in files_spec order
             "alt_bits": {"MERGEETL60_{rcp}": "11110000"}}   // aggregation files under other scenarios, when found
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
Aggregation files under another scenario use the key
`"<scenario>#<SSP>|<rcp>|<iam>|<GCM>"`, one entry per aggregation file.
Files that are not expected use `"extra#<SSP>|<rcp>|<iam>|<GCM>"`, a list of
`[name, size in bytes, written time in Unix seconds]`.

## Automatic updates

Every hour, on the hour (America/Chicago), a self-scheduling Slurm job on
Midway3 (`monitor_job.sbatch`;
scrontab is disabled on this cluster) runs `run_monitor.sh`: it loads
impact-env, runs `collect_status.py`, then `publish_data.sh` pushes
`site/data/` (status.json and the per cell detail files) to the
`monitor-data` branch of ClimateImpactLab/socioeconomics. Each push is one
fresh commit that replaces the previous one, so the branch never grows.
The publish step works in its own scratch folder (`monitor/.publish/`,
ignored by git), so the working tree and its branch are never touched.

The page reads
`https://raw.githubusercontent.com/ClimateImpactLab/socioeconomics/monitor-data/data/status.json`
when it loads, and falls back to the `data/` copy deployed with the site
if that fails (the subtitle then says "(local copy)"). New data needs no
Vercel redeploy. GitHub caches raw files for about 5 minutes. The repo is
public, so the data on that branch is public too: cluster usernames and
job names, no results.

### 1. Deploy key (once)

The push uses a deploy key without a passphrase, never a personal key.
On a Midway3 login node:

```
ssh-keygen -t ed25519 -N "" -C "amel-monitor deploy key" -f ~/.ssh/cil_monitor_deploy
chmod 600 ~/.ssh/cil_monitor_deploy
ssh-keyscan github.com >> ~/.ssh/known_hosts
cat ~/.ssh/cil_monitor_deploy.pub
```

On GitHub, in ClimateImpactLab/socioeconomics: Settings, Deploy keys, Add
deploy key. Title "amel-monitor (Midway3)", paste the `.pub` line, tick
"Allow write access". This needs admin rights on the repo. With gh:

```
gh repo deploy-key add ~/.ssh/cil_monitor_deploy.pub --repo ClimateImpactLab/socioeconomics \
  --allow-write --title "amel-monitor (Midway3)"
```

Check it (it should say "successfully authenticated"):

```
ssh -i ~/.ssh/cil_monitor_deploy -o IdentitiesOnly=yes -T git@github.com
```

The script pushes with `ssh -i ~/.ssh/cil_monitor_deploy -o IdentitiesOnly=yes`,
so only that key is used. A deploy key with write access can push to any
branch; protecting `main` (require pull requests) closes that gap.

### 2. Start it (once)

`monitor_job.sbatch` runs on partition cil, account cil, for up to 15
minutes with 2G, always with the job name `amel-monitor`. Each run first
queues the next one for the next full hour in America/Chicago (Slurm reads
`--begin` in the cluster's local time, which is Chicago) and logs the time
it asked for, then collects and publishes, so the chain goes on even if one
run fails. There is never more than one run waiting:

- a waiting run that begins at or before the next full hour is kept (the
  log says "keeping waiting run");
- a waiting run that begins later (a leftover from an older schedule) is
  cancelled and replaced (the log says "replacing waiting run").

Logs go to `hpc-jobs/logs/monitor/monitor_<jobid>.log`. The log folder must
exist before the first job (Slurm opens the log before the script starts).
Then submit it once; it runs right away and queues the next run:

```
mkdir -p /project/cil/home_dirs/scadavidsanchez/projects/socioeconomics-update/cil2/hpc-jobs/logs/monitor
sbatch /project/cil/home_dirs/scadavidsanchez/projects/socioeconomics-update/cil2/hpc-jobs/monitor/monitor_job.sbatch
```

Manual runs never touch the chain. To collect and publish once:
`bash .../hpc-jobs/monitor/run_monitor.sh`. To do the same as a Slurm job:
`sbatch --export=ALL,MONITOR_ONCE=1 .../hpc-jobs/monitor/monitor_job.sbatch`;
it skips queuing the next run.

### 3. Email on failure

A run that fails sends an email to cadavidsanchez@uchicago.edu (Slurm
`--mail-type=FAIL`). The email names the job; the reason is at the end of
its log, in a line such as `monitor run stopped before publishing (exit
code 2, during: cleaning the environment)`, followed by `monitor run failed
with exit code 2`. During the environment clean up (deactivate, module
purge and `source /etc/profile`), errors and unset variables are allowed,
so system profile scripts that fail on some nodes cannot stop the run.

### 4. Watchdog

`monitor_watchdog.sh` runs every hour from crontab on a login node. If no
`amel-monitor` run is queued or running, it submits one, which starts the
chain again; otherwise it only writes an "ok" line. It runs at half past
the hour, away from the scans on the hour. Its log is
`hpc-jobs/logs/monitor/watchdog.log`.

Crontab line:

```
30 * * * * /bin/bash -l /project/cil/home_dirs/scadavidsanchez/projects/socioeconomics-update/cil2/hpc-jobs/monitor/monitor_watchdog.sh >> /project/cil/home_dirs/scadavidsanchez/projects/socioeconomics-update/cil2/hpc-jobs/logs/monitor/watchdog.log 2>&1
```

To install it, on a Midway3 login node:

```
hostname                 # crontab is kept per login node: note this one
crontab -l               # see what is there now
crontab -e               # add the line above, save and close
crontab -l               # check it is there
```

Each login node keeps its own crontab, so install it on one node only and
note which (for example `midway3-login3`). To check or remove it later, log
in to that same node (`ssh midway3-login3`).

### 5. Check

```
squeue --me -n amel-monitor -o "%.10i %.8T %.20S %.10M"   # the waiting run and when it starts
sacct -n -X --name=amel-monitor -S now-2days               # recent runs and their state
ls -t hpc-jobs/logs/monitor/monitor_*.log | head -1        # newest run log
grep -h "queuing\|keeping\|replacing" $(ls -t hpc-jobs/logs/monitor/monitor_*.log | head -3)
tail -5 hpc-jobs/logs/monitor/watchdog.log                 # watchdog checks
crontab -l                                                 # on the watchdog's login node
```

There should always be one `amel-monitor` job, PENDING with a start time
at the next full hour (or RUNNING for a few minutes, with the next one
PENDING). On GitHub, the `monitor-data` branch shows the time of the last
push in its single commit ("Monitor data, <time> UTC"). On the page, the
subtitle shows the last scan time, and a warning appears when the last
scan is more than 2 hours old.

### 6. Stop

Stop the watchdog first, or it will start the chain again within the hour.
On the watchdog's login node, `crontab -e` and delete the line (or
`crontab -r` if it is the only line). Then cancel the waiting run and any
run in progress:

```
scancel --me -n amel-monitor
```

Start everything again with the `sbatch` line in step 2 and the crontab
line in step 4.

## Deploying to Vercel

From a Mac, in `site/`:

```
npx vercel --prod
```

A redeploy is only needed for changes to the page itself. New data reaches
the page through the monitor-data branch (see Automatic updates).
