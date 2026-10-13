#!/usr/bin/env python3
"""Collect real run status and write status.json for the dashboard.

The progress grid comes only from the output folders: expected files that
exist and are not empty, the stage markers in status-global.txt, and the
claim files workers leave while they run. Slurm is used only for the
cluster strip: each listed person's running and queued jobs, service units
since a start date, and the account balance. Sectors and run types with no
outputs yet come out as not started.

Run it on the cluster from this directory:

    python3 collect_status.py

Useful flags:
    --cil-root PATH   where /project/cil is mounted (default /project/cil);
                      use /Volumes/cil when testing from a Mac
    --no-slurm        skip squeue, sacct and rcchelp (also automatic when absent)
    --out PATH        output file (default site/status.json)
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

# How status-global.txt lines map to stages, and the word that means done.
STATUS_MARKERS = {
    "generate.generate": ("generate", "Generated"),
    "generate.aggregate": ("aggregate", "Complete"),
}

# A claimed stage with no file changes for this long counts as stopped.
STALE_HOURS = 6

# Window for the time-to-finish estimate.
ETA_WINDOW_HOURS = 24


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
    """Per-model expected files; twin files get the winsorized/ prefix."""
    spec = {}
    for model, groups in files_cfg[sector_name].items():
        agg = list(groups["aggregation"])
        agg += [f"winsorized/{n}" for n in groups.get("aggregation_twin", [])]
        spec[model] = {
            "projection": list(groups["projection"]),
            "aggregation": agg,
            "twin": list(groups.get("aggregation_twin", [])),
            "leaf_aggregation": list(groups["aggregation"]),
        }
    return spec


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
    """File sizes, newest change, stage markers and claims for one leaf.

    Returns None if the folder does not exist. markers maps stage to
    (last state word, time of that line).
    """
    sizes, newest = {}, 0.0
    try:
        with os.scandir(leaf_dir) as entries:
            for e in entries:
                try:
                    st = e.stat()
                    sizes[e.name] = st.st_size
                    newest = max(newest, st.st_mtime)
                except OSError:
                    sizes[e.name] = 0
    except OSError:
        return None
    markers = {}
    if "status-global.txt" in sizes:
        try:
            with open(os.path.join(leaf_dir, "status-global.txt")) as f:
                for line in f:
                    m = re.search(r"(\S+\.\S+)\s+\S.*?:\s*(\w+)\s*$", line)
                    if m and m.group(1) in STATUS_MARKERS:
                        stage, _ = STATUS_MARKERS[m.group(1)]
                        markers[stage] = (m.group(2), parse_marker_time(line))
        except OSError:
            pass
    claims = {s: f"status-{s}.txt" in sizes for s in ("generate", "aggregate")}
    return {"sizes": sizes, "markers": markers, "claims": claims, "newest": newest}


def count_group(names, rcp, sizes):
    found, missing = 0, []
    for name in names:
        if sizes.get(name.replace("{rcp}", rcp), 0) > 0:
            found += 1
        else:
            missing.append(name)
    return found, missing


def stage_file_done(stage, spec, rcp, sizes, twin_sizes):
    """Whether a stage's own files are all present and non-empty."""
    if stage == "generate":
        return count_group(spec["projection"], rcp, sizes)[0] == len(spec["projection"])
    if stage == "aggregate":
        names = [n for n in spec["leaf_aggregation"] if n != "adaptation_costs.nc4"]
        return bool(names) and count_group(names, rcp, sizes)[0] == len(names)
    if stage == "costs":
        return sizes.get("adaptation_costs.nc4", 0) > 0
    if stage == "post":
        return bool(spec["twin"]) and \
            count_group(spec["twin"], rcp, twin_sizes)[0] == len(spec["twin"])
    return False


def leaf_path(root, *parts):
    return os.path.join(root, *[p for p in parts if p])


def stage_record(stage, info, spec, rcp, sizes, twin_sizes, now):
    """State of one stage from the folder alone, plus a reason when failed."""
    marker = info["markers"].get(stage) if info else None
    done_word = STATUS_MARKERS.get(f"generate.{stage}", (None, None))[1]
    rec = {"state": "not_started"}
    if (marker and marker[0] == done_word) or \
            (info and stage_file_done(stage, spec, rcp, sizes, twin_sizes)):
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


def scan_run_type(sector, rt_name, manifest, spec, cil_root, now):
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

    for model in models:
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
                    sizes = info["sizes"] if info else {}
                    twin_sizes = {}
                    if info and twin_dir and spec[model]["twin"]:
                        twin_info = read_leaf(leaf_path(twin_dir, subdir, batch_name, cell["rcp"],
                                                        gcm, cell["iam"], cell["ssp"]))
                        twin_sizes = twin_info["sizes"] if twin_info else {}

                    stage_recs, fail_reason = {}, None
                    for stage in stages:
                        rec, reason = stage_record(stage, info, spec[model], cell["rcp"],
                                                   sizes, twin_sizes, now)
                        stage_recs[stage] = rec
                        fail_reason = fail_reason or reason
                        if rec["state"] == "done":
                            fin = info["markers"].get(stage, (None, None))[1] if info else None
                            if fin and now - fin < ETA_WINDOW_HOURS * 3600:
                                steps_done_recent += 1
                        else:
                            steps_left += 1

                    stage_states = [stage_recs[s]["state"] for s in stages]
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

                    proj_found, proj_missing = count_group(spec[model]["projection"], cell["rcp"], sizes)
                    leaf_found, leaf_missing = count_group(spec[model]["leaf_aggregation"], cell["rcp"], sizes)
                    twin_found, twin_missing = count_group(spec[model]["twin"], cell["rcp"], twin_sizes)
                    agg_found = leaf_found + twin_found
                    agg_missing = leaf_missing + [f"winsorized/{n}" for n in twin_missing]
                    agg_total = len(spec[model]["aggregation"])
                    if not (proj_found or agg_found or state != "not_started"):
                        continue

                    files = {
                        "projection": {"found": proj_found, "total": len(spec[model]["projection"])},
                        "aggregation": {"found": agg_found, "total": agg_total},
                    }
                    if 0 < proj_found < len(spec[model]["projection"]):
                        files["projection"]["missing"] = proj_missing
                    if 0 < agg_found < agg_total:
                        files["aggregation"]["missing"] = agg_missing

                    unit = {
                        "model": model, "ssp": cell["ssp"], "rcp": cell["rcp"],
                        "iam": cell["iam"], "gcm": gcm, "batch": batch_num,
                        "state": state, "stages": stage_recs, "files": files,
                    }
                    if fail_reason:
                        unit["fail_reason"] = fail_reason
                    units.append(unit)

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

    return {
        "dims": {"models": models, "cells": cells, "gcms": rcp_gcms, "batches": batches},
        "counts": counts,
        "eta_hours": eta_hours,
        "eta_basis": eta_basis,
        "units": units,
    }


# ---------- slurm (cluster strip only) ----------

def run_cmd(args):
    try:
        res = subprocess.run(args, capture_output=True, text=True, timeout=120)
        if res.returncode != 0:
            log(f"warning: {' '.join(args[:2])} failed: {res.stderr.strip()[:200]}")
            return None
        return res.stdout
    except Exception as err:
        log(f"warning: {' '.join(args[:2])} failed: {err}")
        return None


def squeue_elapsed_s(text):
    """Squeue elapsed time ('5:03', '1:02:03', '1-02:03:04') in seconds."""
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
    out = run_cmd(["squeue", "-r", "-h", "-A", account, "-o", "%i|%u|%j|%T|%P|%M"])
    if out is None:
        return None
    rows = []
    for line in out.splitlines():
        parts = line.strip().split("|")
        if len(parts) != 6:
            continue
        ids, user, name, state, partition, elapsed = parts
        try:
            elapsed_s = squeue_elapsed_s(elapsed) if state == "RUNNING" else 0
        except ValueError:
            elapsed_s = 0
        rows.append({"base": ids.split("_")[0], "user": user, "name": name,
                     "state": state, "partition": partition, "elapsed_s": elapsed_s})
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
        })
        if row["partition"] not in job["partitions"]:
            job["partitions"].append(row["partition"])
        if row["state"] == "PENDING":
            job["queued"] += 1
        else:
            job["running"] += 1
            job["elapsed_s"] = max(job["elapsed_s"], row["elapsed_s"])

    by_user = {}
    for (user, _), job in jobs.items():
        by_user.setdefault(user, []).append({
            "job_name": job["job_name"],
            "partition": ",".join(job["partitions"]),
            "state": "RUNNING" if job["running"] else "PENDING",
            "tasks": {"running": job["running"], "queued": job["queued"], "done": job["done"]},
            "elapsed_min": round(job["elapsed_s"] / 60.0, 1),
        })
    for rows_ in by_user.values():
        rows_.sort(key=lambda r: (r["state"] != "RUNNING", -r["elapsed_min"], r["job_name"]))
    return by_user


def su_by_user(account, since):
    """Core hours of every job on the account since the start date, per user.

    --truncate clips jobs that started earlier to the start date. Returns
    None if sacct failed.
    """
    out = run_cmd(["sacct", "-a", "-X", "-n", "-P", "-A", account,
                   "--starttime", since, "--endtime", "now", "--truncate",
                   "--format=User,ElapsedRaw,AllocCPUS"])
    if out is None:
        return None
    totals = {}
    for line in out.splitlines():
        parts = line.strip().split("|")
        if len(parts) != 3 or not parts[0]:
            continue
        try:
            hours = int(parts[1]) * int(parts[2]) / 3600.0
        except ValueError:
            continue
        totals[parts[0]] = totals.get(parts[0], 0.0) + hours
    return totals


def account_balance(account):
    """Allocation, used and balance in SU from rcchelp.

    status is "ok" when the account line was found, "none" when rcchelp ran
    but listed no allocation for the account, and "unknown" when it failed.
    """
    result = {"allocation_status": "unknown",
              "allocation_su": None, "used_su": None, "balance_su": None}
    out = run_cmd(["rcchelp", "balance", "-a", account])
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


def report_visible_users(manifest, rows, su):
    """Log which users Slurm shows, and listed people with nothing visible."""
    seen = {r["user"] for r in rows or []} | set(su or {})
    log(f"slurm shows jobs from {len(seen)} user(s)")
    for person in manifest["people"]:
        user = person.get("username")
        if user and user not in seen:
            log(f"note: no jobs or usage seen for {person['name']} since the start date")


# ---------- main ----------

def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--cil-root", default="/project/cil",
                        help="where /project/cil is mounted")
    parser.add_argument("--no-slurm", action="store_true",
                        help="skip squeue, sacct and rcchelp")
    parser.add_argument("--out", default=os.path.join(HERE, "site", "status.json"))
    args = parser.parse_args()
    now_dt = datetime.datetime.now(datetime.timezone.utc)
    now = now_dt.timestamp()

    with open(os.path.join(HERE, "manifest.yml")) as f:
        manifest = yaml.safe_load(f)
    account = manifest["account"]["name"]
    since = manifest["account"]["su_since"]

    sectors_out = {}
    for sector_name, sector in manifest["sectors"].items():
        spec = file_spec_for(manifest["files"], sector_name)
        run_types_out = {}
        for rt_name in sector["run_types"]:
            out = scan_run_type(sector, rt_name, manifest, spec, args.cil_root, now)
            run_types_out[rt_name] = out
            c = out["counts"]
            log(f"{sector_name}/{rt_name}: total {c['total']}, done {c['done']}, "
                f"partial {c['partial']}, running {c['running']}, failed {c['failed']}")
        sectors_out[sector_name] = {
            "label": sector["label"],
            "stages": sector["stages"],
            "disabled_run_types": sector.get("disabled_run_types", []),
            "files_spec": {m: {"projection": g["projection"], "aggregation": g["aggregation"]}
                           for m, g in spec.items()},
            "run_types": run_types_out,
        }

    use_slurm = not args.no_slurm and shutil.which("sacct") and shutil.which("squeue")
    rows, su, jobs = None, None, None
    balance = {"allocation_status": "unknown",
               "allocation_su": None, "used_su": None, "balance_su": None}
    if use_slurm:
        rows = live_tasks(account)
        su = su_by_user(account, since)
        jobs = active_jobs_by_user(account, rows) if rows is not None else None
        if shutil.which("rcchelp"):
            balance = account_balance(account)
        report_visible_users(manifest, rows, su)
    else:
        log("slurm tools not used; the cluster strip will show n/a")

    # People are published by display name only, never the cluster username.
    people = []
    for person in manifest["people"]:
        user = person.get("username")
        people.append({
            "name": person["name"],
            "linked": bool(user),
            "su_used": None if su is None else round(su.get(user, 0.0)) if user else 0,
            "active_jobs": None if jobs is None else jobs.get(user, []) if user else [],
        })

    status = {
        "schema_version": 1,
        "source": "collector",
        "generated_at": now_dt.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "scan_interval_hours": 4,
        "account": {"name": account, **balance, "su_since": since},
        "people": people,
        "sectors": sectors_out,
    }

    with open(args.out, "w") as f:
        json.dump(status, f, separators=(",", ":"))
    log(f"wrote {args.out} ({os.path.getsize(args.out) / 1024:.0f} KB)")


if __name__ == "__main__":
    main()
