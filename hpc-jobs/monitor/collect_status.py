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
import json
import os
import re
import shutil
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

# Window for the time-to-finish estimate.
ETA_WINDOW_HOURS = 24

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
    subdir = rt_cfg.get("subdir")

    root = sector["output_root"].replace("/project/cil", cil_root, 1)
    rt_root = os.path.join(root, rt_name)

    counts = {s: 0 for s in ["not_started", "running", "partial", "done", "failed"]}
    units = []
    steps_done_recent = 0
    steps_left = 0
    gen_done = 0
    unit_hours = []
    last_projection_write = 0

    for model in models:
        names = flat_names(spec[model])
        per_stage = {st: stage_files(st, spec[model], stages) for st in stages}
        # A stage that writes nothing for this sub-model (spring and winter
        # wheat are never aggregated themselves) does not apply to it.
        model_stages = [st for st in stages if st == "generate" or per_stage[st]]
        has_twin = any(n.startswith("winsorized/") for n in names)
        model_dir = rt_root if model == "main" else os.path.join(rt_root, model)
        twin_dir = None if model == "main" else os.path.join(rt_root, f"{model}-1pct_winsorization")
        for batch_name in batch_list:
            batch_num = int(batch_name[5:]) if batch_name else None
            for cell in cells:
                rcp_dir = leaf_path(model_dir, subdir, batch_name, cell["rcp"])
                rcp_exists = os.path.isdir(rcp_dir)
                for gcm in rcp_gcms[cell["rcp"]]:
                    info = read_leaf(os.path.join(rcp_dir, gcm, cell["iam"], cell["ssp"])) \
                        if rcp_exists else None
                    twin_files = {}
                    if info and has_twin and twin_dir:
                        twin = read_leaf(leaf_path(twin_dir, subdir, batch_name, cell["rcp"],
                                                   gcm, cell["iam"], cell["ssp"]))
                        twin_files = twin["files"] if twin else {}
                    leaf_files = info["files"] if info else {}
                    hits = {n: lookup(n, cell["rcp"], leaf_files, twin_files) for n in names}
                    for n in spec[model]["projection"]:
                        if hits[n]:
                            last_projection_write = max(last_projection_write, hits[n][1])

                    stage_recs, fail_reason = {}, None
                    for stage in model_stages:
                        rec, reason = stage_record(stage, info, hits, per_stage[stage], now)
                        stage_recs[stage] = rec
                        fail_reason = fail_reason or reason
                        if rec["state"] == "done":
                            fin = info["markers"].get(stage, (None, None))[1] if info else None
                            if fin and now - fin < ETA_WINDOW_HOURS * 3600:
                                steps_done_recent += 1
                        else:
                            steps_left += 1

                    if stage_recs["generate"]["state"] == "done":
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

    eta_hours, eta_basis = None, None
    if steps_left:
        if steps_done_recent:
            rate = steps_done_recent / ETA_WINDOW_HOURS
            eta_hours = round(steps_left / rate, 1)
            eta_basis = (f"{steps_left} stage steps left, {steps_done_recent} finished "
                         f"in the last {ETA_WINDOW_HOURS} h")
        else:
            eta_basis = f"nothing finished in the last {ETA_WINDOW_HOURS} h"

    su_estimate = estimate_sus(counts["total"] - gen_done, unit_hours, sector, rt_name)

    return {
        "dims": {"models": models, "cells": cells, "gcms": rcp_gcms, "batches": batches},
        "root": os.path.join(sector["output_root"], rt_name),
        "subdir": subdir,
        "counts": counts,
        "eta_hours": eta_hours,
        "eta_basis": eta_basis,
        "su_estimate": su_estimate,
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


def plural(n, word):
    return f"{n} {word}" if n == 1 else f"{n} {word}s"


def estimate_sus(remaining, unit_hours, sector, rt_name):
    """Lower and upper SUs to finish the units whose projections are not done.

    Lower: remaining units x the median time per unit seen so far.
    Upper: remaining units x the longest time seen so far.
    With fewer than MIN_OBSERVED_UNITS finished units, the manifest
    reference time is the lower bound, and its longest reference time (or
    the job time limit) the upper one. A sector with no reference time is
    "not known yet". SUs = hours x billing.
    """
    ref = sector.get("reference") or {}
    billing = ref.get("billing", 1)
    limit = ref.get("time_limit_hours")
    if isinstance(limit, dict):
        limit = limit.get(rt_name)
    if remaining <= 0:
        return {"remaining": 0, "su_low": 0, "su_high": 0, "basis": "nothing left to run"}
    if len(unit_hours) >= MIN_OBSERVED_UNITS:
        unit_hours = sorted(unit_hours)
        low_h = unit_hours[len(unit_hours) // 2] if len(unit_hours) % 2 else \
            (unit_hours[len(unit_hours) // 2 - 1] + unit_hours[len(unit_hours) // 2]) / 2
        high_h = unit_hours[-1]
        n = len(unit_hours)
        basis = (f"{plural(remaining, 'unit')} left x {low_h:.1f} h (median) to {high_h:.1f} h (longest) "
                 f"of {plural(n, 'finished unit')}, {billing:g} SU per hour")
        source = "observed"
    else:
        low_h = ref.get("hours_per_unit")
        if low_h is None:
            return {"remaining": remaining, "su_low": None, "su_high": None,
                    "source": "unknown", "basis": "not known yet: no reference time per unit"}
        ref_max = ref.get("hours_per_unit_max")
        high_h = ref_max or limit or low_h
        what = "longest reference" if ref_max else "job limit"
        basis = (f"{plural(remaining, 'unit')} left x {low_h:g} h (reference) to {high_h:g} h ({what}), "
                 f"{billing:g} SU per hour")
        source = "reference"
    high_h = max(high_h, low_h)
    return {"remaining": remaining, "hours_low": round(low_h, 2), "hours_high": round(high_h, 2),
            "su_low": round(remaining * low_h * billing), "su_high": round(remaining * high_h * billing),
            "source": source, "basis": basis}


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


def live_tasks(account):
    """One row per running or queued task on the account, or None on failure."""
    # -r gives one row per array task instead of one row per array.
    out = run_cmd(["squeue", "-r", "-h", "-A", account, "-o", "%i|%u|%j|%T|%P|%M|%l|%L"])
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
        if len(parts) != 8:
            continue
        ids, user, name, state, partition, elapsed, limit, left = parts
        running = state == "RUNNING"
        rows.append({"id": ids, "base": ids.split("_")[0], "user": user, "name": name,
                     "state": state, "partition": partition,
                     "elapsed_s": (seconds(elapsed) or 0) if running else 0,
                     "limit_s": seconds(limit),
                     "left_s": seconds(left) if running else None})
    return rows


def completed_task_counts(account, bases):
    """Number of tasks that finished successfully, per job id."""
    counts = {}
    if not bases:
        return counts
    out = run_cmd(["sacct", "-a", "-X", "-n", "-P", "-A", account,
                   "-j", ",".join(sorted(bases)), "--format=JobID,State"])
    for line in (out or "").splitlines():
        parts = line.strip().split("|")
        if len(parts) == 2 and parts[1].split() and parts[1].split()[0] == "COMPLETED":
            base = parts[0].split("_")[0]
            counts[base] = counts.get(base, 0) + 1
    return counts


def active_jobs_by_user(account, rows):
    """Running and queued jobs per cluster user, one row per job or array."""
    done = completed_task_counts(account, {r["base"] for r in rows})
    jobs = {}
    for row in rows:
        if row["state"] not in ("RUNNING", "COMPLETING", "PENDING"):
            continue
        job = jobs.setdefault((row["user"], row["base"]), {
            "job_name": row["name"], "partitions": [], "running": 0, "queued": 0,
            "elapsed_s": 0, "done": done.get(row["base"], 0),
            "limit_s": row["limit_s"], "left_s": None,
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
            "tasks": {"running": job["running"], "queued": job["queued"], "done": job["done"]},
            "elapsed_min": round(job["elapsed_s"] / 60.0, 1),
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


def usage_by_user(account, since, compute_partitions, live):
    """Compute used and core hours on the account since the start date, per user and partition.

    Compute used follows the RCC formula for SUs on non GPU jobs,
    ElapsedRaw / 3600 x billing, with billing read from each job's
    AllocTRES, on every compute partition, charged or not. Which of them
    RCC charges is decided later, from the manifest. Core hours = elapsed
    hours x allocated CPUs. GPU and bigmem jobs, other partitions and jobs without
    a billing value are flagged, with their elapsed hours, instead of
    guessed. These are estimates; the official use comes from rcchelp.

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
        if "gres/gpu" in (tres or "") or "gpu" in partition:
            reason = "GPU job"
        elif "bigmem" in partition:
            reason = "bigmem partition"
        elif partition not in compute_partitions:
            reason = "partition without a known formula"
        elif billing is None:
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


def usage_summary(entry, charged_partitions):
    """Rounded totals and per-partition values for one user, largest first.

    su_charged is the part of compute used on the partitions RCC charges.
    """
    def by_part(d):
        return {p: round(v, 2) for p, v in sorted(d.items(), key=lambda x: -x[1]) if v >= 0.005}
    flagged = {p: {**f, "hours": round(f["hours"], 2)} for p, f in entry["flagged"].items()}
    return {
        "compute_used": round(sum(entry["su"].values()), 2),
        "compute_by_partition": by_part(entry["su"]),
        "su_charged": round(sum(v for p, v in entry["su"].items() if p in charged_partitions), 2),
        "core_hours": round(sum(entry["core_hours"].values()), 2),
        "core_hours_by_partition": by_part(entry["core_hours"]),
        "su_flagged": flagged,
    }


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
    charged_partitions = manifest["account"].get("su_charged_partitions", [])
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
    rows, su, jobs, storage, stale, bad = None, None, None, None, None, None
    balance = {"allocation_status": "unknown",
               "allocation_su": None, "used_su": None, "balance_su": None}
    if use_slurm:
        rows = live_tasks(account)
        su, stale = usage_by_user(account, since, compute_partitions, rows)
        jobs = active_jobs_by_user(account, rows) if rows is not None else None
        bad = ended_badly(account, bad_days)
        balance = account_balance(account)
        storage = storage_quotas(account)
    else:
        log("slurm tools not used; resources and jobs will show n/a")

    # Every user with jobs or usage on the account, by cluster username.
    users = None
    if su is not None or jobs is not None:
        users = []
        always = manifest["account"].get("always_show_users", [])
        for user in sorted(set(su or {}) | set(jobs or {}) | set(always)):
            entry = (su or {}).get(user, {"su": {}, "core_hours": {}, "flagged": {}})
            row = {"user": user, **usage_summary(entry, charged_partitions)} if su is not None else \
                {"user": user, "compute_used": None, "compute_by_partition": None, "su_charged": None,
                 "core_hours": None, "core_hours_by_partition": None, "su_flagged": None}
            row["active_jobs"] = jobs.get(user, []) if jobs is not None else None
            users.append(row)
        users = [r for r in users if r["compute_used"] or r["su_flagged"] or r["active_jobs"] or r["user"] in always]
        users.sort(key=lambda r: (-(r["compute_used"] or 0), -(r["core_hours"] or 0), r["user"]))
        log(f"slurm shows {len(users)} user(s) on the account")
    # Estimated from sacct; RCC's own figure (rcchelp) is the official one.
    compute_total = None if su is None else round(sum(r["compute_used"] for r in users), 2)
    charged_total = None if su is None else round(sum(r["su_charged"] for r in users), 2)

    status = {
        "schema_version": 4,
        "source": "collector",
        "generated_at": now_dt.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "scan_interval_hours": 4,
        "account": {"name": account, **balance, "su_since": since, "storage": storage,
                    "compute_total": compute_total,
                    "su_charged_total": charged_total,
                    "su_stale_records": stale,
                    "highlight_user": manifest["account"].get("highlight_user"),
                    "compute_partitions": compute_partitions,
                    "su_charged_partitions": charged_partitions},
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
