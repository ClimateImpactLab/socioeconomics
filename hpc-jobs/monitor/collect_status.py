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
import collections
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


def scenario_patterns(agg_names, main):
    """For each aggregation file name holding the main scenario, a pattern that
    finds the same file under another scenario: the main token swapped for any
    one dash-free word. Returns [(index in agg_names, compiled pattern)]."""
    out = []
    for i, name in enumerate(agg_names):
        if main and main in name and not name.startswith("winsorized/"):
            before, after = name.split(main, 1)
            out.append((i, re.compile("^" + re.escape(before).replace(r"\{rcp\}", "{rcp}") + "([^-/]+)"
                                      + re.escape(after).replace(r"\{rcp\}", "{rcp}") + "$")))
    return out


def other_scenarios(patterns, main, rcp, leaf_files):
    """Aggregation files of other scenarios in one leaf: {scenario: {index: hit}}.

    A scenario that names the column's RCP (MERGEETL60_rcp45 in an rcp45
    folder) is kept with the RCP as {rcp}, so it is one scenario across the
    RCP columns."""
    found = {}
    for fname, hit in leaf_files.items():
        if not hit or hit[0] <= 0:
            continue
        for i, pat in patterns:
            m = re.match(pat.pattern.replace("{rcp}", re.escape(rcp)), fname)
            if m and m.group(1) != main:
                found.setdefault(m.group(1).replace(rcp, "{rcp}"), {})[i] = hit
    return found


def extra_files(leaf_files, expected, patterns, rcp):
    """.nc4 files in a leaf that are not expected and not another scenario's
    aggregation file, as [[name, size, mtime]], by name. Listed only, never counted."""
    want = {n.replace("{rcp}", rcp) for n in expected if not n.startswith("winsorized/")}
    out = []
    for name, hit in sorted(leaf_files.items()):
        if not name.endswith(".nc4") or name in want or not hit or hit[0] <= 0:
            continue
        if any(re.match(pat.pattern.replace("{rcp}", re.escape(rcp)), name) for _, pat in patterns):
            continue
        out.append([name, hit[0], hit[1]])
    return out


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

    main_scen = sector.get("aggregation_scenario")
    scenarios_seen = set()
    for model in models:
        names = flat_names(spec[model])
        agg_names = [n for g in GROUPS[1:] for n in spec[model][g]]
        n_proj = len(spec[model]["projection"])
        patterns = scenario_patterns(agg_names, main_scen)
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
                    alt = other_scenarios(patterns, main_scen, cell["rcp"], leaf_files) if patterns else {}
                    scenarios_seen.update(alt)
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

                    any_file = any(hits.values()) or bool(alt)
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
                    key = "|".join([cell["ssp"], cell["rcp"], cell["iam"], gcm])
                    if alt:
                        # Aggregation bits under each other scenario; a file with no
                        # scenario in its name keeps its main bit.
                        held = {i for i, _ in patterns}
                        unit["alt_bits"] = {sc: "".join(
                            ("1" if i in got else "0") if i in held else unit["bits"][n_proj + i]
                            for i in range(len(agg_names))) for sc, got in alt.items()}
                        for sc, got in alt.items():
                            details.setdefault((model, batch_num), {})[f"{sc}#{key}"] = \
                                [list(got[i]) if i in got else (list(hits[n]) if i not in held and hits[n] else 0)
                                 for i, n in enumerate(agg_names)]
                    units.append(unit)
                    if any(hits.values()):
                        details.setdefault((model, batch_num), {})[key] = \
                            [list(hits[n]) if hits[n] else 0 for n in names]
                    extra = extra_files(leaf_files, names, patterns, cell["rcp"])
                    if extra:
                        details.setdefault((model, batch_num), {})[f"extra#{key}"] = extra

    counts["total"] = sum(len(rcp_gcms[c["rcp"]]) for c in cells) * len(batch_list) * len(models)


    return {
        "dims": {"models": models, "cells": cells, "gcms": rcp_gcms, "batches": batches},
        # Aggregation scenarios: the main one counts for progress; the others
        # were found in the same folders and can be picked on the page.
        "agg_scenarios": {"main": main_scen, "others": sorted(scenarios_seen)} if main_scen else None,
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
                "basis": f"{left:,} projection units left; {running:,} being written now at "
                         f"{ut['low_h']:.1f} h per unit ({ut['basis']}), so {pace:.1f} units per hour"}
    if recent >= MIN_RECENT_UNITS:
        pace = recent / PACE_WINDOW_HOURS
        return {"hours": round(left / pace, 1), "method": "recent",
                "basis": f"{left:,} projection units left; {recent:,} finished in the last "
                         f"{PACE_WINDOW_HOURS} h, so {pace:.1f} units per hour"}
    return {"hours": None, "method": None,
            "basis": f"{left:,} projection units left; not enough data yet "
                     f"({recent:,} finished in the last {PACE_WINDOW_HOURS} h, no time per unit known)"}


def plural(n, word):
    return f"{n:,} {word}" if n == 1 else f"{n:,} {word}s"


def estimate_sus(remaining, ut, sector, rt_name, req, rate):
    """Compute hours and RCC SUs to finish the units whose projections are not done.

    Hours per unit: from the run's time per unit (see unit_time), median (low)
    to longest (high); without one, the manifest reference time and its
    longest reference time (or the job time limit). Compute hours = units
    left x hours x billing, as Slurm counts them. SUs = units left x hours x
    RCC's rate for the run's request (see rcc_rate). A sector with no
    reference time is "not known yet".
    """
    ref = sector.get("reference") or {}
    billing = ref.get("billing", 1)
    limit = ref.get("time_limit_hours")
    if isinstance(limit, dict):
        limit = limit.get(rt_name)
    base = {"request": req, "rate": None if rate is None else round(rate, 3)}
    if remaining <= 0:
        return {**base, "remaining": 0, "compute_low": 0, "compute_high": 0, "su_low": 0, "su_high": 0,
                "basis": "nothing left to run"}
    if ut:
        low_h, high_h = ut["low_h"], max(ut["high_h"], ut["low_h"])
        c_lo, c_hi = ut["su_low"], max(ut["su_high"], ut["su_low"])
        source, why = ut["source"], ut["basis"]
    else:
        low_h = ref.get("hours_per_unit")
        if low_h is None:
            return {**base, "remaining": remaining, "compute_low": None, "compute_high": None,
                    "su_low": None, "su_high": None, "source": "unknown",
                    "basis": "not known yet: no reference time per unit"}
        ref_max = ref.get("hours_per_unit_max")
        high_h = max(ref_max or limit or low_h, low_h)
        c_lo, c_hi = low_h * billing, high_h * billing
        source = "reference"
        why = f"reference {low_h:g} h to {high_h:g} h ({'longest reference' if ref_max else 'job limit'})"
    hours = f"{low_h:.1f} h" if round(low_h, 1) == round(high_h, 1) else f"{low_h:.1f} to {high_h:.1f} h"
    if rate is None:
        billed = "request not known"
    elif rate == 0:
        billed = f"{req['partition']} is not billed by RCC"
    else:
        billed = (f"{req['partition']}, {req['cpus']:g} core and {req['mem_gb']:g} GB "
                  f"({req['source']}), {rate:g} SU per hour")
    return {**base, "remaining": remaining, "hours_low": round(low_h, 2), "hours_high": round(high_h, 2),
            "compute_low": round(remaining * c_lo), "compute_high": round(remaining * c_hi),
            "su_low": None if rate is None else round(remaining * low_h * rate),
            "su_high": None if rate is None else round(remaining * high_h * rate),
            "source": source,
            "basis": f"{plural(remaining, 'unit')} left × {hours} per unit ({why}); {billed}"}


# ---------- time per unit ----------

# Fewest finished tasks (one unit each) to trust a time per unit from sacct.
MIN_TASKS = 3


def sacct_time(text):
    """sacct Start ('2026-10-15T16:31:02', local time) as Unix time, or None."""
    try:
        return datetime.datetime.fromisoformat(text).timestamp()
    except (TypeError, ValueError):
        return None


def tres_mem_gb(tres):
    """Memory in GB from an AllocTRES string such as 'cpu=1,mem=45G'."""
    m = re.search(r"(?:^|,)mem=([\d.]+)([KMGT]?)", tres or "")
    if not m:
        return None
    return float(m.group(1)) * {"K": 1 / 1024 ** 2, "M": 1 / 1024, "": 1 / 1024, "G": 1, "T": 1024}[m.group(2)]


def run_request(sector, rt_name, tasks):
    """Partition, cores and memory a run's tasks ask for: the most common
    among its matched tasks, or else the reference in the manifest."""
    seen = [(t["partition"], t["cpus"], t["mem_gb"]) for t in tasks if t.get("cpus") and t.get("mem_gb")]
    if seen:
        (part, cpus, mem), _ = collections.Counter(seen).most_common(1)[0]
        return {"partition": part, "cpus": cpus, "mem_gb": round(mem, 2), "source": "sacct"}
    req = dict((sector.get("reference") or {}).get("request") or {})
    req.update((req.pop("by_run_type", None) or {}).get(rt_name) or {})
    if not req:
        return None
    return {"partition": req.get("partition"), "cpus": req.get("cpus", 1), "mem_gb": req.get("mem_gb"),
            "source": "manifest"}


def rcc_rate(req, rcc):
    """SUs RCC bills per hour of one task: max(cores, memory / RAM per core) on
    a billed partition, 0 elsewhere. None when the request is not known."""
    if not req:
        return None
    if req["partition"] not in rcc.get("billed_partitions", []):
        return 0.0
    ram = (rcc.get("ram_per_core_gb") or {}).get(req["partition"])
    cpus = req["cpus"] or 1
    return max(cpus, req["mem_gb"] / ram) if ram and req.get("mem_gb") else float(cpus)


def run_tasks(account, since_ts):
    """Tasks on the account that started since since_ts: name, state, start,
    elapsed hours and billing. None if sacct failed."""
    since = datetime.datetime.fromtimestamp(since_ts).strftime("%Y-%m-%dT%H:%M:%S")
    out = run_cmd(["sacct", "-a", "-X", "-n", "-P", "-A", account, "--starttime", since,
                   "--endtime", "now", "--format=JobID,JobName,State,ElapsedRaw,AllocTRES,Start,Partition"])
    if out is None:
        return None
    tasks = []
    for line in out.splitlines():
        parts = line.strip().split("|")
        if len(parts) != 7:
            continue
        job, name, state, elapsed, tres, start, partition = parts
        start_ts = sacct_time(start)
        billing = tres_value(tres, "billing")
        try:
            hours = int(elapsed) / 3600.0
        except ValueError:
            continue
        if start_ts is None or billing is None or hours <= 0:
            continue
        tasks.append({"job": job, "name": name, "state": (state.split() or [""])[0],
                      "start": start_ts, "hours": hours, "billing": billing,
                      "partition": partition.split(",")[0], "cpus": tres_value(tres, "cpu"),
                      "mem_gb": tres_mem_gb(tres)})
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
            req = run_request(sector, rt, matched[rt])
            out["su_estimate"] = estimate_sus(timing["left"], ut, sector, rt, req,
                                              rcc_rate(req, manifest["account"].get("rcc_billing") or {}))
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

    Returns ({job id: done}, {job id: failed}, {job id: start of the first
    task, Unix time}). Failed means failed, timeout, out of memory or node
    failure; cancelled tasks are in neither.
    """
    done, failed = {}, {}
    if not bases:
        return done, failed, {}
    started = {}
    out = run_cmd(["sacct", "-a", "-X", "-n", "-P", "-A", account,
                   "-j", ",".join(sorted(bases)), "--format=JobID,State,Start"])
    for line in (out or "").splitlines():
        parts = line.strip().split("|")
        if len(parts) != 3 or not parts[1].split():
            continue
        state, base = parts[1].split()[0], parts[0].split("_")[0]
        if state == "COMPLETED":
            done[base] = done.get(base, 0) + 1
        elif state in FAILED_STATES:
            failed[base] = failed.get(base, 0) + 1
        t = sacct_time(parts[2])
        if t is not None:
            started[base] = min(started.get(base, t), t)
    return done, failed, started


def active_jobs_by_user(account, rows):
    """Running and queued jobs per cluster user, one row per job or array."""
    done, failed, started = completed_task_counts(account, {r["base"] for r in rows})
    jobs = {}
    for row in rows:
        if row["state"] not in ("RUNNING", "COMPLETING", "PENDING"):
            continue
        job = jobs.setdefault((row["user"], row["base"]), {
            "job_name": row["name"], "partitions": [], "running": 0, "queued": 0,
            "elapsed_s": 0, "done": done.get(row["base"], 0), "failed": failed.get(row["base"], 0),
            "limit_s": row["limit_s"], "left_s": None,
            "cpus": row["cpus"], "mem": row["mem"], "on": {},
        })
        # A pending task lists every partition it may use; a running one, the one it runs on.
        for part in row["partition"].split(","):
            if part not in job["partitions"]:
                job["partitions"].append(part)
        if row["state"] != "PENDING":
            job["on"][row["partition"]] = job["on"].get(row["partition"], 0) + 1
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
            "running_on": dict(sorted(job["on"].items(), key=lambda x: -x[1])),   # running tasks per partition
            "started": iso_utc(started[base]) if job["running"] and base in started else None,
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
    rows = sorted(groups.values(), key=lambda g: g["end"], reverse=True)[:limit]
    # sacct gives local cluster time; the page gets UTC.
    for g in rows:
        t = sacct_time(g["end"])
        g["end"] = iso_utc(t) if t is not None else None
    return rows


def tres_value(tres, key):
    """A number from an AllocTRES string such as 'billing=1,cpu=1,mem=45G'."""
    m = re.search(rf"(?:^|,){re.escape(key)}=([\d.]+)", tres or "")
    return float(m.group(1)) if m else None


def usage_table(text, first):
    """Read an rcchelp usage table by its header: the line starting with
    <first> and Usage, then one line per name (name, then SUs), then
    "Total Usage ...: <total>". Returns {"total": SU, "by": {name: SU}}, or
    None if no table was found."""
    rows, total, in_table, seen = {}, None, False, False
    for line in (text or "").splitlines():
        cells = line.split()
        if not cells:
            continue
        if cells[:2] == [first, "Usage"]:
            in_table = seen = True
            continue
        m = re.match(r"^\s*Total Usage\b.*:\s*([\d,.]+)\s*$", line)
        if m:
            total = float(m.group(1).replace(",", ""))
            in_table = False
            continue
        if not in_table or set(line.strip()) <= set("- "):
            continue
        if len(cells) == 2:
            try:
                rows[cells[0]] = rows.get(cells[0], 0.0) + float(cells[1].replace(",", ""))
            except ValueError:
                continue
    if not seen:
        return None
    return {"total": total if total is not None else sum(rows.values()), "by": rows}


def billed_usage(account):
    """Use billed by RCC: per user (rcchelp usage -byuser) and per partition
    (rcchelp usage -bypartition), each read on its own. Either part is None
    when it could not be read. RCC gives no use per user and partition."""
    return {"by_user": usage_table(run_rcchelp(["usage", "-a", account, "-byuser"]), "User"),
            "by_partition": usage_table(run_rcchelp(["usage", "-a", account, "-bypartition"]), "Partition")}


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
    rows, jobs, storage, bad, billed = None, None, None, None, None
    balance = {"allocation_status": "unknown",
               "allocation_su": None, "used_su": None, "balance_su": None}
    if use_slurm:
        rows = live_tasks(account)
        jobs = active_jobs_by_user(account, rows) if rows is not None else None
        bad = ended_badly(account, bad_days)
        balance = account_balance(account)
        billed = billed_usage(account)
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

    # Every user with jobs or billed use on the account, by cluster username;
    # the list gives each user a stable color on the page.
    users = None
    if jobs is not None or billed is not None:
        always = manifest["account"].get("always_show_users", [])
        billed_users = set(((billed or {}).get("by_user") or {}).get("by", {}))
        users = [{"user": u, "active_jobs": (jobs or {}).get(u, []) if jobs is not None else None}
                 for u in sorted(set(jobs or {}) | set(always) | billed_users)]
        log(f"slurm and rcchelp show {len(users)} user(s) on the account")

    status = {
        "schema_version": 8,
        "source": "collector",
        "generated_at": now_dt.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "scan_interval_hours": 1,
        "account": {"name": account, **balance, "storage": storage,
                    # Billed by RCC (rcchelp usage); each part null when it could not be read.
                    "billed": None if billed is None else {k: None if t is None else {
                        "total": round(t["total"], 2),
                        "by": {n: round(v, 2) for n, v in sorted(t["by"].items(), key=lambda x: -x[1])}}
                        for k, t in billed.items()},
                    "highlight_user": manifest["account"].get("highlight_user")},
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
