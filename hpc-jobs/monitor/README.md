# CIL | Projections, new socioeconomics: run-status monitor

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
- The CIL logo at the top right (site/cil-logo.svg), inverted and
  desaturated in dark mode, following the same light and dark switch. The tab icon is
  the kit's color favicon in the same five colors (site/camel/).
- Right above the grid: sector, run type and sub-model tabs (montecarlo by
  default, median for energy, whose montecarlo tab is greyed out). Each
  sector tab has its camel color, the selected one filled with it, and
  shows the progress of its main run, projection and aggregation apart,
  each with its percent and file counts ("Projection 100% (64/64),
  Aggregation 0% (0/496)"), and the SUs needed to finish it. Run type tabs
  and the sector key next to the camel show the same two parts; the camel
  itself fills with projection progress only ("not known yet" for
  agriculture), with a one-line explanation underneath. A sector is active
  when projection files were written in its folders in the last 24 hours
  (or a unit is being written now); its tab then shows four small squares
  in the sector color, lighting in turn. Sub-model tabs (crops, fuels)
  show their own P and A file counts. Clicking a selected sector or
  sub-model again clears it.
- An info bar with the path of the clicked cell, and a detail panel that
  lists the cell's files grouped into Projections, Aggregation (levels and
  aggregated) and Costs, each with a small dot, the file size and the date
  it was written.
- Resources: storage of the cil account as thin bars, then service units,
  all since the start of the allocation cycle (`su_since`, 2026-10-01):
  - Official (RCC): from `rcchelp balance -a cil`, shown as used out of
    allocation, such as "0 / 1,200,000". RCC counts every partition,
    including the time so far of running jobs, and updates about a day
    later; a small "i" next to the bar says so.
  - Service units, estimate: one plain segment per user, from
    `sreport cluster AccountUtilizationByUser account=cil start=2026-10-01 end=now -t hours`,
    the same count as RCC's (checked on the cluster), so its total lands
    close to the official one apart from RCC's delay. RCC gives no use per
    user (`rcchelp usage -a cil --byuser` returns nothing), so sreport gives
    the split.
  - Compute used: from sacct, elapsed hours x billing (in SU equivalent)
    on every partition, including the time so far of running jobs, with
    one colored segment per user and, inside it, one textured part per
    partition (cil lines, amd stripes, caslake dots, amd-hm solid).
    Records sacct shows as running but squeue does not have are left out,
    since those jobs do not exist.
  The start date shows once, above both bars. One key below both bars,
  from the left and in alphabetical order, gives each user's color with
  service units and compute used side by side, and one texture key gives
  each partition's compute total. Users in `account.always_show_users` and
  the partitions in `account.compute_partitions` are always listed, even
  with no use yet, and `account.highlight_user` shows in charcoal.
  Highlighting works both ways: hovering a segment of either bar marks its
  user (and partition) in the shared key and the matching segments in both
  bars, and hovering a user or a partition in the key does the same. A
  click keeps the highlight until the same thing is clicked again. The "i"
  next to the estimate says in one line that it is counted the same way as
  RCC, which updates about a day later, and gives the compute formula with
  the sacct command to check a job.
- Resources and SLURM jobs start collapsed.
- Run types can be left out with `enabled: false` under `run_types` in the
  manifest. quick_test is off this way: no tab, and it is not in any count,
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
  id, name, user, partition, state, task badges, elapsed time, CPUs and memory requested
  (per task for arrays), time limit and time left
  before the limit (from squeue; for an array, the task closest to its
  limit). Time left shows in amber when it is under 2 hours. Below it, a collapsed
  list of jobs on the account that ended badly (timeout, out of memory,
  failed, cancelled) in the last `account.ended_badly_days` days: job id,
  name, user, partition, how it ended and how long it ran. Array tasks
  that ended the same way are grouped under their job id.
- A row of small cards for the selected sector and run type, right above
  the tabs and the grid: expected units, complete, partial, not started,
  projection and aggregation progress, units being written, time to
  finish, and SUs to finish. Time to finish covers the projection only;
  aggregation shows as "not started" (or its units done) and is not
  added in. Its tooltip gives the numbers and the pace used.
- SSP tabs, the legend, and the grid. The SSP tabs are small round
  badges, each with its own color from a palette apart from the sector,
  user and state colors, following each SSP's story: SSP2 (middle of the
  road) a neutral blue grey, SSP3 (regional rivalry) a muted red, SSP4
  (inequality) a muted purple. The selected one is filled, the others
  outlined. Each SSP tab and each scenario
  column shows P, projection files present out of expected, and A,
  aggregation files present out of expected, for example
  "P 917/4,160, A 0/4,160"; a small "i" next to the SSP tabs says so. Energy shows every SSP at
  once, with all its SSP tabs selected; the other sectors show one SSP at a
  time. Each cell has one small square per
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
avoids the state hues. Sector tabs follow the AMEL order: Agriculture,
Mortality, Energy, Labor. Coastal shows "not tracked (yet)".

## Expected files per unit

Taken from the official production outputs under /project/cil/gcp/outputs,
not from the cil2 or cil2-wpp test runs, and checked against finished
production leaves (every expected file present and not empty). They live
in the `files:` section of `manifest.yml`.

| Sector | Production folder used | Projection | Aggregation |
|---|---|---|---|
| Mortality | `mortality/impacts-darwin/montecarlo` (and the old monitor's `run_monitor.sh` counts, checked on `mortality_new-socioeconomics/impacts-darwin`) | 16: four age groups (combined, older, oldest, young) times four variants (full adaptation, histclim, incadapt, noadapt) | 36: 4 costs (`<age>-costs`), 16 levels, 16 aggregated |
| Agriculture | `agriculture/impacts-mealy/montecarlo/<crop>-2025` and `<crop>-2025_1pct_winsorization` | 4: `<crop>-<id>` in the four variants | 12: 4 costs (`adaptation_costs`, its aggregated file, and the winsorized `fulladaptcosts` pair), 8 aggregated (four variants in the crop folder and four in the winsorized folder). Spring and winter wheat are not aggregated themselves: 2 costs (`adaptation_costs` and the winsorized `fulladaptcosts`), no aggregated. They are combined into `wheat_combined`, tracked as its own sub-model with the full 12. |
| Energy | `energy_pixel_interaction/impacts-blueghost/median` | 4: the four variants per fuel | 4: levels and aggregated at the price014 price scenario, for full adaptation and histclim |
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
  are not done yet: remaining units x the SUs per unit, low to high.
  Aggregation is not included; it is much shorter than the projection.
- Compute used = ElapsedRaw / 3600 x billing, with billing read from each
  job's AllocTRES (not assumed equal to the CPUs), on every partition. For
  example, a job on amd with billing=1, cpu=1, mem=45G that ran 36 h 25 s
  used 36.01. To check a job:
  `sacct -X -j <jobid> -n -P -o JobID,ElapsedRaw,Partition,AllocTRES`.
  Core hours are elapsed hours x the job's allocated CPUs (cpu= in
  AllocTRES). Jobs without a billing value are flagged with their elapsed
  hours instead of counted. Only jobs that have finished (they have an end
  time) or that squeue shows right now count: sacct sometimes keeps a job
  as RUNNING or PENDING long after it ended, when its record was never
  closed, and those stale records are listed apart, not counted. Every
  user with jobs or use on the account is listed by cluster username. The
  allocation and balance come from `rcchelp balance -a cil`, the service
  units estimate from sreport, and storage from `rcchelp quota` (group
  filesets of the cil account).

## status.json format (schema 5)

The contract between the collector and the page; the mock follows it.

```jsonc
{
  "schema_version": 5,
  "source": "collector",             // "mock" or "collector"
  "generated_at": "2026-10-13T18:00:00Z",
  "scan_interval_hours": 1,
  "account": {
    "name": "cil",
    "allocation_status": "ok",       // "ok", "none" (no allocation listed) or "unknown"
    "allocation_su": 1200000, "used_su": 0, "balance_su": 1200000,
    "su_since": "2026-10-01",        // start of the allocation cycle; all use counts from here
    "compute_total": 319.4,          // compute used, sacct, all partitions, SU equivalent
    "su_estimate_total": 310.0,      // sreport, the way RCC counts; null when sreport failed
    "su_stale_records": [{"job_id": "53282084_1", "user": "someuser", "state": "RUNNING",
                          "partition": "caslake", "hours": 1580.2}],   // not counted
    "highlight_user": "cadavidsanchez",
    "compute_partitions": ["cil", "amd", "caslake", "amd-hm"],   // always listed in the key
    "storage": [                     // null when rcchelp could not be read
      {"label": "cil /project", "used": "412.6T", "quota": "500.0T", "used_pct": 82.5}
    ]
  },
  "users": [                         // every user with jobs or usage, by cluster username; null without Slurm
    {"user": "someuser",
     "compute_used": 319.4,          // elapsed hours x billing since su_since, all partitions
     "compute_by_partition": {"amd": 150.2, "cil": 100.0, "caslake": 69.2},   // largest first
     "su_estimate": 310.0,           // sreport hours since su_since; null when sreport failed
     "core_hours": 319.4,            // elapsed hours x CPUs
     "core_hours_by_partition": {"amd": 150.2, "cil": 100.0, "caslake": 69.2},
     "su_flagged": {"gpu": {"jobs": 1, "hours": 3.5, "reason": "no billing value"}},
     "active_jobs": [{"job_id": "59946806", "job_name": "energy-median", "partition": "amd", "state": "RUNNING",
                      "tasks": {"running": 32, "queued": 0, "done": 16, "failed": 1},   // failed: failed, timeout, out of memory, node failure
                      "elapsed_min": 1391.0,
                      "cpus": 1, "mem": "45G",   // requested, per task
                      "limit_min": 2160.0,    // null with no limit
                      "left_min": 769.0}]}    // smallest among running tasks; null while pending
  ],
  "ended_badly": [                   // newest first, at most 25; null without Slurm
    {"job_id": "59939384", "job_name": "labor-median", "user": "someuser", "partition": "caslake",
     "ended": "timeout",              // timeout, out of memory, failed, cancelled or node failure
     "tasks": 11, "elapsed_min": 2160.0, "end": "2026-10-13T08:12:40"}
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
                                     // each sub-model's folder, down to the batch or rcp folders
          "counts": {"not_started": 0, "running": 0, "partial": 0, "done": 0, "failed": 0, "total": 520},
          "eta_hours": 5.4,             // projection only; null when there is not enough data yet
          "eta_method": "writing",      // "writing", "recent" or null
          "eta_basis": "178 projection units left; 146 being written now, ...",
          "aggregation": {"started": false, "done": 0},   // units with aggregation done
          "unit_time_source": "sacct",  // where the time per unit came from; null when not known
          "su_estimate": {"remaining": 520, "hours_low": 20.5, "hours_high": 36, "su_low": 10660,
                          "su_high": 18720, "source": "reference",   // "sacct", "file dates", "reference" or "unknown"
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
