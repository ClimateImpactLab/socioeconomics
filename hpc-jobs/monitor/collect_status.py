#!/usr/bin/env python3
"""Collect real run status and write the dashboard data.

The progress grid comes only from the output folders: expected files that
exist and are not empty, the stage markers in status-global.txt, and the
claim files workers leave while they run. Slurm and rcchelp are used only
for the resources and jobs sections: storage, service units, and the jobs
running or queued on the account. Sectors and run types with no outputs
yet come out as not started.

Writes, under --out-dir (default site/data):
    status.json     everything the page needs at load time
    details/...     file sizes and dates per cell, loaded when a cell is
                    clicked (one file per sector, run type, sub-model and,
                    for montecarlo, batch)

Run it on the cluster from this directory:

    python3 collect_status.py

Useful flags:
    --cil-root PATH   where /project/cil is mounted (default /project/cil);
                      use /Volumes/cil when testing from a Mac
    --no-slurm        skip squeue, sacct and rcchelp (also automatic when absent)
"""

import argparse
import datetime
import fnmatch
import json
import os
import re
import shutil
import statistics
import subprocess

import yaml

HERE = os.path.dirname(os.path.abspath(__file__))

GROUPS = ["projection", "costs", "levels", "aggregated"]

# How status-global.txt lines map to stages, and the word that means done.
STATUS_MARKERS = {
    "generate.generate": ("generate", "Generated"),
    "generate.aggregate": ("aggregate", "Complete"),
}

# A claimed stage with no file changes for this long counts as stopped.
STALE_HOURS = 6

# Time to finish the projections: the pace over this many recent hours, and
# the fewest units finished in that window to trust it.
PACE_WINDOW_HOURS = 6
MIN_RECENT_UNITS = 3

# Observed times per unit replace the manifest reference only from this many
# finished units on.
MIN_OBSERVED_UNITS = 10


def log(msg):
    print(msg, flush=True)


def iso_utc(ts):
    return datetime.datetime.fromtimestamp(ts, datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# ---------- manifest expansion (same rules as the mock) ----------

def cells_for(rt_cfg, scenarios):
    cfg = rt_cfg["cells"]
    if cfg == "all":
        ssps, iams, rcp_filter = scenarios["ssps"], scenarios["iams"], None
    else:
        ssps, iams, rcp_filter = cfg["ssps"], cfg["iams"], cfg["rcps"]
    cells = []
    for ssp in ssps:
        for rcp in scenarios["valid_pairs"][ssp]:
            if rcp_filter and rcp not in rcp_filter:
                continue
            for iam in iams:
                cells.append({"ssp": ssp, "rcp": rcp, "iam": iam})
    return cells


def gcms_for(rt_cfg, gcms):
    cfg = rt_cfg["gcms"]
    if cfg == "per_rcp":
        return {rcp: list(models) for rcp, models in gcms.items()}
    return {rcp: list(cfg) for rcp in gcms}


def file_spec_for(files_cfg, sector_name):
    """Expected files per sub-model, by group, in a fixed order."""
    return {model: {g: list(groups.get(g) or []) for g in GROUPS}
            for model, groups in files_cfg[sector_name].items()}


def flat_names(spec):
    return [n for g in GROUPS for n in spec[g]]


def stage_files(stage, spec, stages):
    """Expected files a stage writes, so its folder state can be judged."""
    in_leaf = lambda names: [n for n in names if not n.startswith("winsorized/")]
    if stage == "generate":
        return spec["projection"]
    if stage == "post":
        return [n for g in GROUPS[1:] for n in spec[g] if n.startswith("winsorized/")]
    if stage == "costs":
        return in_leaf(spec["costs"])
    # aggregate also writes the costs when the sector has no costs stage
    groups = ["levels", "aggregated"] if "costs" in stages else ["costs", "levels", "aggregated"]
    return [n for g in groups for n in in_leaf(spec[g])]


# ---------- output folders ----------

def parse_marker_time(line):
    """Timestamp at the start of a status-global.txt line, as Unix time.

    The engine writes local time ('Mon Oct 12 22:05:25 2026'); on the
    cluster that is Chicago time, which is also the collector's local time.
    """
    try:
        stamp = datetime.datetime.strptime(" ".join(line.split()[:5]), "%a %b %d %H:%M:%S %Y")
        return stamp.timestamp()
    except ValueError:
        return None


def read_leaf(leaf_dir):
    """File sizes and dates, newest change, stage markers and claims for one leaf.

    Returns None if the folder does not exist. markers maps stage to
    (last state word, time of that line).
    """
    files, newest = {}, 0.0
    try:
        with os.scandir(leaf_dir) as entries:
            for e in entries:
                try:
                    st = e.stat()
                    files[e.name] = (st.st_size, int(st.st_mtime))
                    newest = max(newest, st.st_mtime)
                except OSError:
                    files[e.name] = (0, 0)
    except OSError:
        return None
    markers = {}
    if "status-global.txt" in files:
        try:
            with open(os.path.join(leaf_dir, "status-global.txt")) as f:
                for line in f:
                    m = re.search(r"(\S+\.\S+)\s+\S.*?:\s*(\w+)\s*$", line)
                    if m and m.group(1) in STATUS_MARKERS:
                        stage, _ = STATUS_MARKERS[m.group(1)]
                        markers[stage] = (m.group(2), parse_marker_time(line))
        except OSError:
            pass
    claims = {s: f"status-{s}.txt" in files for s in ("generate", "aggregate")}
    return {"files": files, "markers": markers, "claims": claims, "newest": newest}


def lookup(name, rcp, leaf_files, twin_files):
    """(size, mtime) of an expected file, or None if missing or empty."""
    real = name.replace("{rcp}", rcp)
    if real.startswith("winsorized/"):
        hit = twin_files.get(real[len("winsorized/"):])
    else:
        hit = leaf_files.get(real)
    return hit if hit and hit[0] > 0 else None


def leaf_path(root, *parts):
    return os.path.join(root, *[p for p in parts if p])


DEFAULT_LAYOUT = "{run_type}/{model}/{subdir}"


def model_dir_for(sector, rt_name, rt_cfg, model, root=None):
    """Folder of one sub-model and run type, down to where batch or rcp
    folders start, following the sector's layout in the manifest."""
    rel = sector.get("layout", DEFAULT_LAYOUT).format(
        run_type=rt_name, model="" if model == "main" else model, subdir=rt_cfg.get("subdir") or "")
    return leaf_path(root or sector["output_root"], *rel.split("/"))


def stage_record(stage, info, present, stage_names, now):
    """State of one stage from the folder alone, plus a reason when failed."""
    marker = info["markers"].get(stage) if info else None
    done_word = STATUS_MARKERS.get(f"generate.{stage}", (None, None))[1]
    rec = {"state": "not_started"}
    files_done = bool(stage_names) and all(present.get(n) for n in stage_names)
    if (marker and marker[0] == done_word) or files_done:
        rec["state"] = "done"
        if marker and marker[1]:
            rec["finished"] = iso_utc(marker[1])
        return rec, None
    if marker and done_word and marker[0] != done_word:
        rec["state"] = "failed"
        return rec, f"{stage} ended as {marker[0]}"
    if info and info["claims"].get(stage):
        if now - info["newest"] < STALE_HOURS * 3600:
            rec["state"] = "running"
            return rec, None
        rec["state"] = "failed"
        return rec, f"{stage} stopped: no file changes for {STALE_HOURS} h"
    return rec, None


def scan_run_type(sector, rt_name, manifest, spec, cil_root, now, details):
    """Scan one sector and run type. Fills details[(model, batch)] with
    {cell key: [[size, mtime] or 0 per expected file]}."""
    rt_cfg = manifest["run_types"][rt_name]
    cells = cells_for(rt_cfg, manifest["scenarios"])
    rcp_gcms = gcms_for(rt_cfg, manifest["gcms"])
    batches = rt_cfg.get("batches")
    batch_list = [f"batch{i}" for i in range(batches)] if batches else [None]
    models = sector["models"]
    stages = sector["stages"]
    root = sector["output_root"].replace("/project/cil", cil_root, 1)

    counts = {s: 0 for s in ["not_started", "running", "partial", "done", "failed"]}
    units = []
    gen_done = 0
    gen_recent = 0      # projections finished in the last PACE_WINDOW_HOURS
    gen_running = 0     # projections being written now
    agg_done = 0
    agg_started = False
    unit_hours = []
    last_projection_write = 0
    first_projection_write = None

    for model in models:
        names = flat_names(spec[model])
        per_stage = {st: stage_files(st, spec[model], stages) for st in stages}
        # A stage that writes nothing for this sub-model (spring and winter
        # wheat are never aggregated themselves) does not apply to it.
        model_stages = [st for st in stages if st == "generate" or per_stage[st]]
        has_twin = any(n.startswith("winsorized/") for n in names)
        model_dir = model_dir_for(sector, rt_name, rt_cfg, model, root)
        twin_dir = None if model == "main" else \
            model_dir_for(sector, rt_name, rt_cfg, f"{model}-1pct_winsorization", root)
        for batch_name in batch_list:
            batch_num = int(batch_name[5:]) if batch_name else None
            for cell in cells:
                rcp_dir = leaf_path(model_dir, batch_name, cell["rcp"])
                rcp_exists = os.path.isdir(rcp_dir)
                for gcm in rcp_gcms[cell["rcp"]]:
                    info = read_leaf(os.path.join(rcp_dir, gcm, cell["iam"], cell["ssp"])) \
                        if rcp_exists else None
                    twin_files = {}
                    if info and has_twin and twin_dir:
                        twin = read_leaf(leaf_path(twin_dir, batch_name, cell["rcp"],
                                                   gcm, cell["iam"], cell["ssp"]))
                        twin_files = twin["files"] if twin else {}
                    leaf_files = info["files"] if info else {}
                    hits = {n: lookup(n, cell["rcp"], leaf_files, twin_files) for n in names}
                    for n in spec[model]["projection"]:
                        if hits[n]:
                            last_projection_write = max(last_projection_write, hits[n][1])
                            first_projection_write = hits[n][1] if first_projection_write is None \
                                else min(first_projection_write, hits[n][1])

                    stage_recs, fail_reason = {}, None
                    for stage in model_stages:
                        rec, reason = stage_record(stage, info, hits, per_stage[stage], now)
                        stage_recs[stage] = rec
                        fail_reason = fail_reason or reason

                    gen_state = stage_recs["generate"]["state"]
                    if gen_state == "running":
                        gen_running += 1
                    for stage in model_stages:
                        if stage == "generate":
                            continue
                        st = stage_recs[stage]["state"]
                        if st != "not_started" or any(hits[n] for n in per_stage[stage]):
                            agg_started = True
                    if model_stages != ["generate"] and all(
                            stage_recs[st]["state"] == "done" for st in model_stages if st != "generate"):
                        agg_done += 1

                    if gen_state == "done":
                        # Finish time: the marker, or else the newest projection file.
                        fin = info["markers"].get("generate", (None, None))[1] if info else None
                        if not fin:
                            fin = max((hits[n][1] for n in spec[model]["projection"] if hits[n]), default=None)
                        if fin and now - fin < PACE_WINDOW_HOURS * 3600:
                            gen_recent += 1
                        gen_done += 1
                        hours = unit_generate_hours(spec[model]["projection"], hits)
                        if hours:
                            unit_hours.append(hours)

                    stage_states = [stage_recs[s]["state"] for s in model_stages]
                    if "failed" in stage_states:
                        state = "failed"
                    elif "running" in stage_states:
                        state = "running"
                    elif all(s == "done" for s in stage_states):
                        state = "done"
                    elif "done" in stage_states:
                        state = "partial"
                    else:
                        state = "not_started"
                    counts[state] += 1

                    any_file = any(hits.values())
                    if not (any_file or state != "not_started"):
                        continue

                    files = {}
                    for g in GROUPS:
                        group = spec[model][g]
                        files[g] = {"found": sum(1 for n in group if hits[n]), "total": len(group)}
                    unit = {
                        "model": model, "ssp": cell["ssp"], "rcp": cell["rcp"],
                        "iam": cell["iam"], "gcm": gcm, "batch": batch_num,
                        "state": state, "stages": stage_recs, "files": files,
                        "bits": "".join("1" if hits[n] else "0" for n in names),
                    }
                    if fail_reason:
                        unit["fail_reason"] = fail_reason
                    units.append(unit)
                    if any_file:
                        key = "|".join([cell["ssp"], cell["rcp"], cell["iam"], gcm])
                        details.setdefault((model, batch_num), {})[key] = \
                            [list(hits[n]) if hits[n] else 0 for n in names]

    counts["total"] = sum(len(rcp_gcms[c["rcp"]]) for c in cells) * len(batch_list) * len(models)


    return {
        "dims": {"models": models, "cells": cells, "gcms": rcp_gcms, "batches": batches},
        # Folder of each sub-model, down to the batch or rcp folders.
        "model_dirs": {m: model_dir_for(sector, rt_name, rt_cfg, m) for m in models},
        "counts": counts,
        "aggregation": {"started": agg_started, "done": agg_done},
        # Filled in by finish_estimates once Slurm has been read.
        "_timing": {"left": counts["total"] - gen_done, "done": gen_done, "recent": gen_recent,
                    "running": gen_running, "file_hours": unit_hours,
                    "first_write": first_projection_write},
        # Newest projection file date, for the "active sector" sign on the tabs.
        "last_projection_write": iso_utc(last_projection_write) if last_projection_write else None,
        "units": units,
    }


def unit_generate_hours(projection_names, hits):
    """Generate time of one finished unit, from its projection file dates.

    The engine writes the projection files one after another, so the time
    from the first to the last file covers n - 1 of n files; scaling by
    n / (n - 1) adds the first one. Needs at least two files.
    """
    times = [hits[n][1] for n in projection_names if hits.get(n)]
    if len(times) < 2:
        return None
    span = (max(times) - min(times)) / 3600.0
    return span * len(times) / (len(times) - 1) if span > 0 else None


def projection_eta(left, recent, running, ut):
    """Hours to finish the projections left, with the pace used.

    Two paces: the units being written now over the time per unit (method
    "writing", steady because it does not move with bursts of finishes),
    used when a time per unit is known; or the units finished in the last
    PACE_WINDOW_HOURS (method "recent"), used with at least
    MIN_RECENT_UNITS of them. Otherwise there is not enough data yet and
    hours is None.
    """
    if left <= 0:
        return {"hours": 0, "method": None, "basis": "all projections done"}
    if running and ut:
        pace = running / ut["low_h"]
        return {"hours": round(left / pace, 1), "method": "writing",
                "basis": f"{left} projection units left; {running} being written now at "
                         f"{ut['low_h']:.1f} h per unit ({ut['basis']}), so {pace:.1f} units per hour"}
    if recent >= MIN_RECENT_UNITS:
        pace = recent / PACE_WINDOW_HOURS
        return {"hours": round(left / pace, 1), "method": "recent",
                "basis": f"{left} projection units left; {recent} finished in the last "
                         f"{PACE_WINDOW_HOURS} h, so {pace:.1f} units per hour"}
    return {"hours": None, "method": None,
            "basis": f"{left} projection units left; not enough data yet "
                     f"({recent} finished in the last {PACE_WINDOW_HOURS} h, no time per unit known)"}


def plural(n, word):
    return f"{n} {word}" if n == 1 else f"{n} {word}s"


def estimate_sus(remaining, ut, sector, rt_name):
    """Lower and upper SUs to finish the units whose projections are not done.

    With a time per unit (see unit_time): remaining units x its low and high
    SUs per unit. Without one, the manifest reference time is the lower
    bound, and its longest reference time (or the job time limit) the upper
    one. A sector with no reference time is "not known yet".
    """
    ref = sector.get("reference") or {}
    billing = ref.get("billing", 1)
    limit = ref.get("time_limit_hours")
    if isinstance(limit, dict):
        limit = limit.get(rt_name)
    if remaining <= 0:
        return {"remaining": 0, "su_low": 0, "su_high": 0, "basis": "nothing left to run"}
    if ut:
        lo, hi = ut["su_low"], max(ut["su_high"], ut["su_low"])
        per = f"{lo:.1f} SU" if round(lo, 1) == round(hi, 1) else f"{lo:.1f} to {hi:.1f} SU"
        return {"remaining": remaining, "hours_low": round(ut["low_h"], 2), "hours_high": round(ut["high_h"], 2),
                "su_low": round(remaining * lo), "su_high": round(remaining * hi),
                "source": ut["source"],
                "basis": f"{plural(remaining, 'unit')} left x {per} per unit ({ut['basis']})"}
    low_h = ref.get("hours_per_unit")
    if low_h is None:
        return {"remaining": remaining, "su_low": None, "su_high": None,
                "source": "unknown", "basis": "not known yet: no reference time per unit"}
    ref_max = ref.get("hours_per_unit_max")
    high_h = max(ref_max or limit or low_h, low_h)
    what = "longest reference" if ref_max else "job limit"
    return {"remaining": remaining, "hours_low": round(low_h, 2), "hours_high": round(high_h, 2),
            "su_low": round(remaining * low_h * billing), "su_high": round(remaining * high_h * billing),
            "source": "reference",
            "basis": (f"{plural(remaining, 'unit')} left x {low_h:g} h (reference) to {high_h:g} h ({what}), "
                      f"{billing:g} SU per hour")}


# ---------- time per unit ----------

# Fewest finished tasks (one unit each) to trust a time per unit from sacct.
MIN_TASKS = 3


def sacct_time(text):
    """sacct Start ('2026-10-15T16:31:02', local time) as Unix time, or None."""
    try:
        return datetime.datetime.fromisoformat(text).timestamp()
    except (TypeError, ValueError):
        return None


def run_tasks(account, since_ts):
    """Tasks on the account that started since since_ts: name, state, start,
    elapsed hours and billing. None if sacct failed."""
    since = datetime.datetime.fromtimestamp(since_ts).strftime("%Y-%m-%dT%H:%M:%S")
    out = run_cmd(["sacct", "-a", "-X", "-n", "-P", "-A", account, "--starttime", since,
                   "--endtime", "now", "--format=JobID,JobName,State,ElapsedRaw,AllocTRES,Start"])
    if out is None:
        return None
    tasks = []
    for line in out.splitlines():
        parts = line.strip().split("|")
        if len(parts) != 6:
            continue
        job, name, state, elapsed, tres, start = parts
        start_ts = sacct_time(start)
        billing = tres_value(tres, "billing")
        try:
            hours = int(elapsed) / 3600.0
        except ValueError:
            continue
        if start_ts is None or billing is None or hours <= 0:
            continue
        tasks.append({"job": job, "name": name, "state": (state.split() or [""])[0],
                      "start": start_ts, "hours": hours, "billing": billing})
    return tasks


def run_since(sector, rt_name, timing):
    """When a run started: run_started in the manifest, or else its first
    projection file less the job time limit. None with no files yet."""
    started = (sector.get("run_started") or {}).get(rt_name)
    if started:
        return sacct_time(str(started))
    if not timing["first_write"]:
        return None
    limit = (sector.get("reference") or {}).get("time_limit_hours") or 36
    if isinstance(limit, dict):
        limit = limit.get(rt_name) or 36
    return timing["first_write"] - limit * 3600


# A task matching several run types goes to the most specific one.
RUN_TYPE_ORDER = ["montecarlo", "median", "quick_test", "single"]


def name_matches(name, patterns):
    name = name.lower()
    return any(fnmatch.fnmatch(name, p.lower()) for p in patterns)


def matched_tasks(sector, rts, tasks, starts, exclude):
    """The tasks of each run type of a sector: job name matches the sector's
    job_names (and none of exclude), started since the run's start. Returns
    {run type: [tasks]}."""
    out = {rt: [] for rt in rts}
    names = sector.get("job_names") or {}
    order = [rt for rt in RUN_TYPE_ORDER if rt in rts] + [rt for rt in rts if rt not in RUN_TYPE_ORDER]
    for t in tasks or []:
        if name_matches(t["name"], exclude):
            continue
        for rt in order:
            if name_matches(t["name"], names.get(rt) or []):
                if starts.get(rt) is not None and t["start"] >= starts[rt]:
                    out[rt].append(t)
                break
    return out


def one_unit_each(rt_cfg, timing, tasks):
    """True when the run's tasks each do one unit: set in the manifest, or
    seen in the numbers (as many tasks as units started, within 25%)."""
    if rt_cfg.get("one_unit_per_task"):
        return True
    started = timing["done"] + timing["running"]
    return bool(tasks) and started > 0 and 0.8 <= len(tasks) / started <= 1.25


def unit_time(rt_cfg, timing, tasks, startup_h, ref_h):
    """Time and SUs per unit for one run, with the source used, or None.

    Observed times count only with at least MIN_OBSERVED_UNITS finished
    units of the run, and only when they are within a factor of 2 of the
    reference time (when there is one); otherwise the reference is used.
    - Tasks of one unit each: elapsed x billing of the finished tasks only,
      median to longest. Running tasks are left out, since their unit is
      not done yet.
    - Tasks of several units each: the SUs of all the run's tasks over the
      units finished, only once none of them is still running.
    - Otherwise: file dates (first to last file of a unit), plus the start
      up time measured from the sector's singles, which file dates miss.
    """
    def plausible(hours):
        return ref_h is None or ref_h / 2 <= hours <= ref_h * 2

    rejected = None
    if timing["done"] >= MIN_OBSERVED_UNITS and tasks:
        billing = statistics.median(t["billing"] for t in tasks)
        finished = [t for t in tasks if t["state"] == "COMPLETED"]
        if one_unit_each(rt_cfg, timing, tasks):
            done = sorted(t["hours"] * t["billing"] for t in finished)
            if len(done) >= MIN_OBSERVED_UNITS:
                lo, hi = statistics.median(done), done[-1]
                if plausible(lo / billing):
                    return {"low_h": lo / billing, "high_h": hi / billing, "su_low": lo, "su_high": hi,
                            "source": "sacct", "basis": f"sacct, {len(done)} finished tasks of one unit each"}
                rejected = f"sacct gave {lo / billing:.1f} h per unit"
        elif len(finished) == len(tasks):
            su = sum(t["hours"] * t["billing"] for t in tasks)
            per = su / timing["done"]
            if plausible(per / billing):
                return {"low_h": per / billing, "high_h": per / billing, "su_low": per, "su_high": per,
                        "source": "sacct",
                        "basis": f"sacct, {su:,.0f} SU over {len(tasks)} finished tasks, {timing['done']} units"}
            rejected = f"sacct gave {per / billing:.1f} h per unit"
    hours = timing["file_hours"]
    if len(hours) >= MIN_OBSERVED_UNITS:
        hours = sorted(hours)
        add = startup_h or 0
        lo, hi = statistics.median(hours) + add, hours[-1] + add
        if plausible(lo):
            note = (f"file dates of {len(hours)} units plus {add:.1f} h start up time from the singles"
                    if startup_h is not None else f"file dates of {len(hours)} units, start up time not known")
            return {"low_h": lo, "high_h": hi, "su_low": lo, "su_high": hi, "source": "file dates", "basis": note}
        rejected = rejected or f"file dates gave {lo:.1f} h per unit"
    if rejected:
        log(f"   {rejected}, more than twice or under half the reference {ref_h:g} h; using the reference")
    return None


def finish_estimates(manifest, sectors_out, all_tasks):
    """Fill in each run's time to finish and SUs to finish from its time per unit."""
    exclude = manifest["account"].get("job_names_exclude", [])
    for name, sector in manifest["sectors"].items():
        rts = sectors_out[name]["run_types"]
        starts = {rt: run_since(sector, rt, out["_timing"]) for rt, out in rts.items()}
        matched = matched_tasks(sector, list(rts), all_tasks, starts, exclude)
        # Start up time: a single task's elapsed time less its first to last file span.
        startup = None
        single = rts.get("single")
        if single:
            done = [t["hours"] for t in matched["single"] if t["state"] == "COMPLETED"]
            spans = single["_timing"]["file_hours"]
            if len(done) >= MIN_TASKS and spans:
                startup = max(0.0, statistics.median(done) - statistics.median(spans))
        for rt, out in rts.items():
            timing = out.pop("_timing")
            ut = unit_time(manifest["run_types"][rt], timing, matched[rt], startup,
                           (sector.get("reference") or {}).get("hours_per_unit"))
            eta = projection_eta(timing["left"], timing["recent"], timing["running"], ut)
            out["eta_hours"], out["eta_method"], out["eta_basis"] = eta["hours"], eta["method"], eta["basis"]
            out["unit_time_source"] = ut["source"] if ut else None
            out["su_estimate"] = estimate_sus(timing["left"], ut, sector, rt)
            log(f"{name}/{rt}: time per unit {ut['basis'] + ', ' + format(ut['su_low'], '.1f') + ' SU' if ut else 'not known'}")


def write_details(out_dir, sector_name, rt_name, details):
    for (model, batch), cells in details.items():
        name = f"{model}.json" if batch is None else f"{model}/batch{batch}.json"
        path = os.path.join(out_dir, "details", sector_name, rt_name, name)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as f:
            json.dump(cells, f, separators=(",", ":"))


# ---------- slurm and rcchelp (resources and jobs only) ----------

def run_cmd(args, login_shell=False):
    """Run a command and return its output, or None on failure.

    rcchelp is set up by the login profile, so it can run through bash -lc.
    """
    try:
        if login_shell:
            args = ["bash", "-lc", " ".join(args)]
        res = subprocess.run(args, capture_output=True, text=True, timeout=120)
        if res.returncode != 0:
            log(f"warning: {' '.join(args[:3])} failed: {res.stderr.strip()[:200]}")
            return None
        return res.stdout
    except Exception as err:
        log(f"warning: {' '.join(args[:3])} failed: {err}")
        return None


def run_rcchelp(args):
    if shutil.which("rcchelp"):
        return run_cmd(["rcchelp"] + args)
    return run_cmd(["rcchelp"] + args, login_shell=True)


def squeue_elapsed_s(text):
    """Squeue time ('5:03', '1:02:03', '1-02:03:04') in seconds."""
    days = 0
    if "-" in text:
        d, text = text.split("-", 1)
        days = int(d)
    parts = [int(x) for x in text.split(":")]
    while len(parts) < 3:
        parts.insert(0, 0)
    return days * 86400 + parts[0] * 3600 + parts[1] * 60 + parts[2]


def mem_text(text):
    """Requested memory from squeue ('45G', '4000M') in a short form ('45G', '3.9G')."""
    m = re.match(r"^([\d.]+)([KMGT]?)$", (text or "").strip())
    if not m:
        return None
    size = float(m.group(1)) * {"K": 1 / 1024, "": 1, "M": 1, "G": 1024, "T": 1024 ** 2}[m.group(2)]
    if size >= 1024 ** 2:
        t = size / 1024 ** 2
        return f"{t:.0f}T" if t == int(t) else f"{t:.1f}T"
    if size >= 1024:
        g = size / 1024
        return f"{g:.0f}G" if g >= 10 or g == int(g) else f"{g:.1f}G"
    return f"{size:.0f}M"


def live_tasks(account):
    """One row per running or queued task on the account, or None on failure."""
    # -r gives one row per array task instead of one row per array.
    out = run_cmd(["squeue", "-r", "-h", "-A", account, "-o", "%i|%u|%j|%T|%P|%M|%l|%L|%C|%m"])
    if out is None:
        return None

    def seconds(text):
        # UNLIMITED, NOT_SET and INVALID have no number of seconds.
        try:
            return squeue_elapsed_s(text)
        except ValueError:
            return None

    rows = []
    for line in out.splitlines():
        parts = line.strip().split("|")
        if len(parts) != 10:
            continue
        ids, user, name, state, partition, elapsed, limit, left, cpus, mem = parts
        running = state == "RUNNING"
        rows.append({"id": ids, "base": ids.split("_")[0], "user": user, "name": name,
                     "state": state, "partition": partition,
                     "elapsed_s": (seconds(elapsed) or 0) if running else 0,
                     "limit_s": seconds(limit),
                     "left_s": seconds(left) if running else None,
                     "cpus": int(cpus) if cpus.isdigit() else None, "mem": mem_text(mem)})
    return rows


FAILED_STATES = ("FAILED", "TIMEOUT", "OUT_OF_MEMORY", "NODE_FAIL")


def completed_task_counts(account, bases):
    """Tasks that finished well and tasks that failed, per job id.

    Returns ({job id: done}, {job id: failed}). Failed means failed, timeout,
    out of memory or node failure; cancelled tasks are in neither.
    """
    done, failed = {}, {}
    if not bases:
        return done, failed
    out = run_cmd(["sacct", "-a", "-X", "-n", "-P", "-A", account,
                   "-j", ",".join(sorted(bases)), "--format=JobID,State"])
    for line in (out or "").splitlines():
        parts = line.strip().split("|")
        if len(parts) != 2 or not parts[1].split():
            continue
        state, base = parts[1].split()[0], parts[0].split("_")[0]
        if state == "COMPLETED":
            done[base] = done.get(base, 0) + 1
        elif state in FAILED_STATES:
            failed[base] = failed.get(base, 0) + 1
    return done, failed


def active_jobs_by_user(account, rows):
    """Running and queued jobs per cluster user, one row per job or array."""
    done, failed = completed_task_counts(account, {r["base"] for r in rows})
    jobs = {}
    for row in rows:
        if row["state"] not in ("RUNNING", "COMPLETING", "PENDING"):
            continue
        job = jobs.setdefault((row["user"], row["base"]), {
            "job_name": row["name"], "partitions": [], "running": 0, "queued": 0,
            "elapsed_s": 0, "done": done.get(row["base"], 0), "failed": failed.get(row["base"], 0),
            "limit_s": row["limit_s"], "left_s": None,
            "cpus": row["cpus"], "mem": row["mem"],
        })
        if row["partition"] not in job["partitions"]:
            job["partitions"].append(row["partition"])
        if row["state"] == "PENDING":
            job["queued"] += 1
        else:
            job["running"] += 1
            job["elapsed_s"] = max(job["elapsed_s"], row["elapsed_s"])
            # The task closest to its limit decides the time left.
            if row["left_s"] is not None:
                job["left_s"] = row["left_s"] if job["left_s"] is None else min(job["left_s"], row["left_s"])
        if row["limit_s"] is not None:
            job["limit_s"] = max(job["limit_s"] or 0, row["limit_s"])

    by_user = {}
    for (user, base), job in jobs.items():
        by_user.setdefault(user, []).append({
            "job_id": base,
            "job_name": job["job_name"],
            "partition": ",".join(job["partitions"]),
            "state": "RUNNING" if job["running"] else "PENDING",
            "tasks": {"running": job["running"], "queued": job["queued"], "done": job["done"],
                      "failed": job["failed"]},
            "elapsed_min": round(job["elapsed_s"] / 60.0, 1),
            "cpus": job["cpus"],   # per task
            "mem": job["mem"],     # per task, as squeue shows it
            "limit_min": None if job["limit_s"] is None else round(job["limit_s"] / 60.0, 1),
            "left_min": None if job["left_s"] is None else round(job["left_s"] / 60.0, 1),
        })
    for rows_ in by_user.values():
        rows_.sort(key=lambda r: (r["state"] != "RUNNING", -r["elapsed_min"], r["job_name"]))
    return by_user


# sacct state names for jobs that did not finish well, and how the page names them.
BAD_ENDS = {"TIMEOUT": "timeout", "OUT_OF_MEMORY": "out of memory", "FAILED": "failed",
            "CANCELLED": "cancelled", "NODE_FAIL": "node failure"}


def ended_badly(account, days, limit=25):
    """Jobs on the account that ended badly in the last few days, newest first.

    Array tasks that ended the same way are grouped under their job id, with
    the number of tasks and the longest run time. Returns a list of rows, or
    None if sacct failed.
    """
    out = run_cmd(["sacct", "-a", "-X", "-n", "-P", "-A", account,
                   "--starttime", f"now-{int(days)}days", "--endtime", "now",
                   "--state", "TO,OOM,F,CA,NF",
                   "--format=JobID,User,Partition,State,ElapsedRaw,End,JobName"])
    if out is None:
        return None
    groups = {}
    for line in out.splitlines():
        parts = line.strip().split("|", 6)
        if len(parts) != 7 or not parts[1]:
            continue
        job, user, partition, state, elapsed, end, name = parts
        state = state.split()[0] if state else ""
        if state not in BAD_ENDS or end in ("", "Unknown", "None"):
            continue
        base = job.split("_")[0]
        try:
            elapsed_s = int(elapsed)
        except ValueError:
            elapsed_s = 0
        g = groups.setdefault((base, state), {
            "job_id": base, "job_name": name, "user": user,
            "partition": partition.split(",")[0], "ended": BAD_ENDS[state],
            "tasks": 0, "elapsed_min": 0.0, "end": end})
        g["tasks"] += 1
        g["elapsed_min"] = max(g["elapsed_min"], round(elapsed_s / 60.0, 1))
        g["end"] = max(g["end"], end)
    rows = sorted(groups.values(), key=lambda g: g["end"], reverse=True)
    return rows[:limit]


def tres_value(tres, key):
    """A number from an AllocTRES string such as 'billing=1,cpu=1,mem=45G'."""
    m = re.search(rf"(?:^|,){re.escape(key)}=([\d.]+)", tres or "")
    return float(m.group(1)) if m else None


def usage_by_user(account, since, live):
    """Compute used and core hours on the account since the start date, per user and partition.

    Compute used = ElapsedRaw / 3600 x billing, with billing read from each
    job's AllocTRES, on every partition, including the time so far of jobs
    still running. Core hours = elapsed hours x allocated CPUs. Jobs without
    a billing value are flagged, with their elapsed hours, instead of
    guessed.

    Only jobs that finished (they have an end time) or that squeue shows
    right now count. sacct sometimes keeps a job as RUNNING or PENDING long
    after it ended, when its record was never closed; those stale records
    are not counted and are returned apart.
    --truncate clips jobs that started earlier to the start date.
    Returns ({user: {"su": {}, "core_hours": {}, "flagged": {}}}, stale),
    or (None, None) if sacct failed.
    """
    out = run_cmd(["sacct", "-a", "-X", "-n", "-P", "-A", account,
                   "--starttime", since, "--endtime", "now", "--truncate",
                   "--format=JobID,User,Partition,ElapsedRaw,AllocTRES,State,End"])
    if out is None:
        return None, None
    live_ids = {r["id"] for r in live or []}
    live_bases = {r["base"] for r in live or []}

    def in_squeue(job):
        if job in live_ids:
            return True
        base = job.split("_")[0]
        return base in live_bases and ("_" not in job or "[" in job)

    totals, stale = {}, []
    for line in out.splitlines():
        parts = line.strip().split("|")
        if len(parts) != 7 or not parts[1]:
            continue
        job, user, partition, elapsed, tres, state, end = parts
        state = state.split()[0] if state else ""
        open_record = state in ("RUNNING", "PENDING", "REQUEUED", "SUSPENDED") or end in ("", "Unknown", "None")
        if open_record and live is not None and not in_squeue(job):
            try:
                stale_h = round(int(elapsed) / 3600.0, 1)
            except ValueError:
                stale_h = None
            stale.append({"job_id": job, "user": user, "state": state,
                          "partition": partition.split(",")[0], "hours": stale_h})
            continue
        try:
            hours = int(elapsed) / 3600.0
        except ValueError:
            continue
        if hours <= 0:
            continue
        # A job that could run on several partitions lists them all; it ran on the first.
        partition = partition.split(",")[0] or "unknown"
        per = totals.setdefault(user, {"su": {}, "core_hours": {}, "flagged": {}})
        cpus = tres_value(tres, "cpu")
        billing = tres_value(tres, "billing")
        if billing is None:
            reason = "no billing value"
        else:
            per["su"][partition] = per["su"].get(partition, 0.0) + hours * billing
            if cpus:
                per["core_hours"][partition] = per["core_hours"].get(partition, 0.0) + hours * cpus
            continue
        f = per["flagged"].setdefault(partition, {"jobs": 0, "hours": 0.0, "reason": reason})
        f["jobs"] += 1
        f["hours"] += hours
    return totals, stale


def usage_summary(entry):
    """Rounded totals and per-partition values for one user, largest first."""
    def by_part(d):
        return {p: round(v, 2) for p, v in sorted(d.items(), key=lambda x: -x[1]) if v >= 0.005}
    flagged = {p: {**f, "hours": round(f["hours"], 2)} for p, f in entry["flagged"].items()}
    return {
        "compute_used": round(sum(entry["su"].values()), 2),
        "compute_by_partition": by_part(entry["su"]),
        "core_hours": round(sum(entry["core_hours"].values()), 2),
        "core_hours_by_partition": by_part(entry["core_hours"]),
        "su_flagged": flagged,
    }


def sreport_usage(account, since):
    """Use per user since the start date, counted the way RCC counts it.

    sreport cluster AccountUtilizationByUser, in hours, matches the usage in
    rcchelp balance (RCC updates about a day later): every partition, and
    the time so far of jobs still running. Returns {"total": hours,
    "by_user": {user: hours}}, or None if sreport failed.
    """
    out = run_cmd(["sreport", "-P", "cluster", "AccountUtilizationByUser", f"account={account}",
                   f"start={since}", "end=now", "-t", "hours"])
    if out is None:
        return None
    header, total, by_user = None, None, {}
    for line in out.splitlines():
        parts = [p.strip() for p in line.split("|")]
        if header is None:
            if "Login" in parts and "Used" in parts:
                header = parts
            continue
        if len(parts) != len(header):
            continue
        row = dict(zip(header, parts))
        if row.get("Account") != account:
            continue
        try:
            used = float(row["Used"])
        except ValueError:
            continue
        if row["Login"]:
            by_user[row["Login"]] = by_user.get(row["Login"], 0.0) + used
        else:
            total = used
    if header is None:
        return None
    return {"total": total if total is not None else sum(by_user.values()), "by_user": by_user}


def account_balance(account):
    """Allocation, used and balance in SU from rcchelp.

    status is "ok" when the account line was found, "none" when rcchelp ran
    but listed no allocation for the account, and "unknown" when it failed.
    """
    result = {"allocation_status": "unknown",
              "allocation_su": None, "used_su": None, "balance_su": None}
    out = run_rcchelp(["balance", "-a", account])
    if out is None:
        return result
    result["allocation_status"] = "none"
    for line in out.splitlines():
        cells = [c.strip() for c in line.strip().strip("|").split("|")] \
            if "|" in line else line.split()
        if not cells or cells[0] != account:
            continue
        try:
            nums = [float(c.replace(",", "")) for c in cells[1:4]]
        except ValueError:
            continue
        if len(nums) == 3:
            result["allocation_su"], result["used_su"], result["balance_su"] = nums
            result["allocation_status"] = "ok"
            break
    return result


SIZE_UNITS = {"K": 1024, "M": 1024 ** 2, "G": 1024 ** 3, "T": 1024 ** 4, "P": 1024 ** 5}


def parse_size(text):
    m = re.match(r"^([\d.]+)([KMGTP])?$", (text or "").strip())
    return float(m.group(1)) * SIZE_UNITS.get(m.group(2) or "", 1) if m else None


def storage_quotas(account):
    """Group storage of the account from rcchelp quota, one row per filesystem.

    Same parsing as the old monitor: a '>>> ... Filesystem: <fs>' marker
    line, then rows of 'fileset blocks (group) used quota limit grace'.
    """
    out = run_rcchelp(["quota"])
    if out is None:
        return None
    rows, fs = [], None
    marker = re.compile(r">>>\s+\S.*?Filesystem:\s+(\S+)")
    row = re.compile(r"^\s*(\S+)\s+(blocks|files)\s+\(\s*(\w+)\s*\)\s+(\S+)\s+(\S+)\s+(\S+)\s+(\S+)\s*$")
    for line in out.splitlines():
        m = marker.search(line)
        if m:
            fs = m.group(1)
            continue
        m = row.match(line)
        if not m:
            continue
        fileset, kind, scope, used, quota, _limit, _grace = m.groups()
        if kind != "blocks" or scope != "group" or fileset != account:
            continue
        used_b, quota_b = parse_size(used), parse_size(quota)
        rows.append({
            "label": f"{fileset} /{fs or 'home'}",
            "used": used, "quota": quota,
            "used_pct": round(100 * used_b / quota_b, 1) if used_b is not None and quota_b else None,
        })
    return rows


# ---------- main ----------

def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--cil-root", default="/project/cil",
                        help="where /project/cil is mounted")
    parser.add_argument("--no-slurm", action="store_true",
                        help="skip squeue, sacct and rcchelp")
    parser.add_argument("--out-dir", default=os.path.join(HERE, "site", "data"))
    args = parser.parse_args()
    now_dt = datetime.datetime.now(datetime.timezone.utc)
    now = now_dt.timestamp()

    with open(os.path.join(HERE, "manifest.yml")) as f:
        manifest = yaml.safe_load(f)
    account = manifest["account"]["name"]
    since = manifest["account"]["su_since"]
    compute_partitions = manifest["account"]["compute_partitions"]
    bad_days = manifest["account"].get("ended_badly_days", 3)

    os.makedirs(args.out_dir, exist_ok=True)
    shutil.rmtree(os.path.join(args.out_dir, "details"), ignore_errors=True)

    sectors_out = {}
    for sector_name, sector in manifest["sectors"].items():
        spec = file_spec_for(manifest["files"], sector_name)
        run_types_out = {}
        for rt_name in sector["run_types"]:
            if not manifest["run_types"][rt_name].get("enabled", True):
                continue
            details = {}
            out = scan_run_type(sector, rt_name, manifest, spec, args.cil_root, now, details)
            write_details(args.out_dir, sector_name, rt_name, details)
            run_types_out[rt_name] = out
            c = out["counts"]
            log(f"{sector_name}/{rt_name}: total {c['total']}, done {c['done']}, "
                f"partial {c['partial']}, running {c['running']}, failed {c['failed']}")
        sectors_out[sector_name] = {
            "label": sector["label"],
            "stages": sector["stages"],
            "disabled_run_types": sector.get("disabled_run_types", []),
            "files_spec": spec,
            "run_types": run_types_out,
        }

    use_slurm = not args.no_slurm and shutil.which("sacct") and shutil.which("squeue")
    rows, su, jobs, storage, stale, bad, report = None, None, None, None, None, None, None
    balance = {"allocation_status": "unknown",
               "allocation_su": None, "used_su": None, "balance_su": None}
    if use_slurm:
        rows = live_tasks(account)
        su, stale = usage_by_user(account, since, rows)
        report = sreport_usage(account, since) if shutil.which("sreport") else None
        jobs = active_jobs_by_user(account, rows) if rows is not None else None
        bad = ended_badly(account, bad_days)
        balance = account_balance(account)
        storage = storage_quotas(account)
    else:
        log("slurm tools not used; resources and jobs will show n/a")

    all_tasks = None
    if use_slurm:
        starts = [run_since(manifest["sectors"][n], rt, out["_timing"])
                  for n, sec in sectors_out.items() for rt, out in sec["run_types"].items()]
        starts = [t for t in starts if t]
        if starts:
            all_tasks = run_tasks(account, min(starts))
    finish_estimates(manifest, sectors_out, all_tasks)

    # Every user with jobs or usage on the account, by cluster username.
    users = None
    if su is not None or jobs is not None:
        users = []
        always = manifest["account"].get("always_show_users", [])
        reported = (report or {}).get("by_user", {})
        for user in sorted(set(su or {}) | set(jobs or {}) | set(always) | set(reported)):
            entry = (su or {}).get(user, {"su": {}, "core_hours": {}, "flagged": {}})
            row = {"user": user, **usage_summary(entry)} if su is not None else \
                {"user": user, "compute_used": None, "compute_by_partition": None,
                 "core_hours": None, "core_hours_by_partition": None, "su_flagged": None}
            # Service units the way RCC counts them (sreport); None if sreport failed.
            row["su_estimate"] = round(reported.get(user, 0.0), 2) if report is not None else None
            row["active_jobs"] = jobs.get(user, []) if jobs is not None else None
            users.append(row)
        users = [r for r in users if r["compute_used"] or r["su_estimate"] or r["su_flagged"] or r["active_jobs"]
                 or r["user"] in always]
        users.sort(key=lambda r: (-(r["compute_used"] or 0), -(r["core_hours"] or 0), r["user"]))
        log(f"slurm shows {len(users)} user(s) on the account")
    # Estimated from sacct; RCC's own figure (rcchelp) is the official one.
    compute_total = None if su is None else round(sum(r["compute_used"] for r in users), 2)
    su_estimate_total = None if report is None else round(report["total"], 2)

    status = {
        "schema_version": 5,
        "source": "collector",
        "generated_at": now_dt.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "scan_interval_hours": 1,
        "account": {"name": account, **balance, "su_since": since, "storage": storage,
                    "compute_total": compute_total,
                    "su_estimate_total": su_estimate_total,   # sreport, the way RCC counts
                    "su_stale_records": stale,
                    "highlight_user": manifest["account"].get("highlight_user"),
                    "compute_partitions": compute_partitions},
        "users": users,
        "ended_badly": bad,
        "ended_badly_days": bad_days,
        "sectors": sectors_out,
    }

    path = os.path.join(args.out_dir, "status.json")
    with open(path, "w") as f:
        json.dump(status, f, separators=(",", ":"))
    log(f"wrote {path} ({os.path.getsize(path) / 1024:.0f} KB)")


if __name__ == "__main__":
    main()
