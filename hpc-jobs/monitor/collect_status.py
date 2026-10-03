#!/usr/bin/env python3
"""Collect real run status and write status.json for the dashboard.

Reads manifest.yml, scans the output trees, reads the status marker files
written by the projection engine, joins Slurm (squeue and sacct) by job
name and array task id, and writes status.json in the same format the
mock generator uses. Sectors and run types with no outputs yet come out
as not started.

Run it on the cluster from this directory:

    python3 collect_status.py

Useful flags:
    --cil-root PATH   where /project/cil is mounted (default /project/cil);
                      use /Volumes/cil when testing from a Mac
    --no-slurm        skip squeue and sacct (also automatic when absent)
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
HPC_JOBS = os.path.dirname(HERE)

# Sub-states a stage can be in. Unit states are derived from these.
STAGE_ORDER = ["generate", "aggregate", "costs", "post"]
FAILED_STATES = {"FAILED", "OUT_OF_MEMORY", "TIMEOUT", "CANCELLED", "NODE_FAIL",
                 "DEADLINE", "BOOT_FAIL", "PREEMPTED"}

# How status-global.txt lines map to stages, and the word that means done.
STATUS_MARKERS = {
    "generate.generate": ("generate", "Generated"),
    "generate.aggregate": ("aggregate", "Complete"),
}


def log(msg):
    print(msg, flush=True)


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


# ---------- slurm ----------

def expand_task_ids(token):
    """'59946806_3' -> [3]; '59946806_[4-15]' -> [4..15]; '123' -> [None]."""
    if "_" not in token:
        return [(token, None)]
    base, idx = token.split("_", 1)
    if not idx.startswith("["):
        try:
            return [(base, int(idx))]
        except ValueError:
            return [(base, None)]
    out = []
    for part in idx.strip("[]").split(","):
        part = part.split("%")[0]
        if "-" in part:
            a, b = part.split("-")
            out.extend((base, i) for i in range(int(a), int(b) + 1))
        elif part:
            out.append((base, int(part)))
    return out


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


def mem_to_gb(text):
    m = re.match(r"([\d.]+)([KMGT]?)", text or "")
    if not m:
        return None
    val = float(m.group(1))
    unit = m.group(2)
    scale = {"K": 1 / 1024 / 1024, "M": 1 / 1024, "G": 1, "T": 1024, "": 1 / 1024 / 1024}
    return round(val * scale[unit], 1)


def collect_slurm(account, su_since):
    """Current and recent jobs plus service-unit sums.

    Returns (tasks, su). tasks maps job name -> list of task records.
    su has per-user and per-job-name core-hour sums.
    """
    tasks = {}
    su = {"by_user": {}, "by_name": {}}

    out = run_cmd(["squeue", "-h", "-A", account, "-o", "%i|%j|%T"])
    if out:
        for line in out.splitlines():
            parts = line.strip().split("|")
            if len(parts) != 3:
                continue
            ids, name, state = parts
            for base, idx in expand_task_ids(ids):
                tasks.setdefault(name, []).append({
                    "base": base, "task": idx, "state": state,
                    "elapsed_s": None, "max_rss_gb": None, "req_mem_gb": None,
                    "end": "", "user": None,
                })

    out = run_cmd(["sacct", "-X", "-n", "-P", "-A", account,
                   "--starttime", su_since,
                   "--format=JobID,JobName%60,User,State,ElapsedRaw,AllocCPUS,ReqMem,End"])
    rss = {}
    out2 = run_cmd(["sacct", "-n", "-P", "-A", account, "--starttime", su_since,
                    "--format=JobID,MaxRSS"])
    if out2:
        for line in out2.splitlines():
            parts = line.strip().split("|")
            if len(parts) == 2 and parts[0].endswith(".batch"):
                rss[parts[0][:-6]] = mem_to_gb(parts[1])
    if out:
        for line in out.splitlines():
            parts = line.strip().split("|")
            if len(parts) != 8:
                continue
            ids, name, user, state, elapsed, cpus, reqmem, end = parts
            state = state.split()[0]  # "CANCELLED by ..." -> "CANCELLED"
            hours = 0.0
            try:
                hours = int(elapsed) * int(cpus) / 3600.0
            except ValueError:
                pass
            if user:
                su["by_user"][user] = su["by_user"].get(user, 0.0) + hours
            su["by_name"][name] = su["by_name"].get(name, 0.0) + hours
            if state == "PENDING":
                continue  # squeue already covers pending tasks
            for base, idx in expand_task_ids(ids):
                tasks.setdefault(name, []).append({
                    "base": base, "task": idx, "state": state,
                    "elapsed_s": int(elapsed) if elapsed.isdigit() else None,
                    "max_rss_gb": rss.get(ids),
                    "req_mem_gb": mem_to_gb(reqmem),
                    "end": end, "user": user,
                })
    return tasks, su


def account_balance(account):
    """Totals from the RCC accounts tool; nulls when unavailable."""
    out = run_cmd(["accounts", "balance", "-a", account])
    result = {"allocation_su": None, "used_su": None, "balance_su": None}
    if not out:
        return result
    nums = re.findall(r"([\d,]+(?:\.\d+)?)", out)
    vals = [float(n.replace(",", "")) for n in nums]
    if len(vals) >= 3:
        result["allocation_su"], result["used_su"], result["balance_su"] = vals[0], vals[1], vals[2]
    return result


# ---------- leaf scanning ----------

def read_leaf(leaf_dir):
    """File sizes, finished markers and claim markers for one leaf."""
    sizes = {}
    try:
        with os.scandir(leaf_dir) as entries:
            for e in entries:
                try:
                    sizes[e.name] = e.stat().st_size
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
                        stage, done_word = STATUS_MARKERS[m.group(1)]
                        markers[stage] = m.group(2)  # keep the last state
        except OSError:
            pass
    claims = {s: f"status-{s}.txt" in sizes for s in ("generate", "aggregate")}
    return {"sizes": sizes, "markers": markers, "claims": claims,
            "mtime": os.path.getmtime(leaf_dir)}


def count_group(names, rcp, sizes):
    found, missing = 0, []
    for name in names:
        real = name.replace("{rcp}", rcp)
        if sizes.get(real, 0) > 0:
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


def fresh(mtime, hours=6):
    return (datetime.datetime.now().timestamp() - mtime) < hours * 3600


# ---------- main scan ----------

def scan_run_type(sector_name, sector, rt_name, manifest, spec, cil_root, slurm_tasks):
    rt_cfg = manifest["run_types"][rt_name]
    scenarios = manifest["scenarios"]
    cells = cells_for(rt_cfg, scenarios)
    rcp_gcms = gcms_for(rt_cfg, manifest["gcms"])
    batches = rt_cfg.get("batches")
    batch_list = [f"batch{i}" for i in range(batches)] if batches else [None]
    models = sector["models"]
    stages = sector["stages"]
    log_prefix = sector["log_prefixes"][rt_name]

    root = sector["output_root"].replace("/project/cil", cil_root, 1)
    rt_root = os.path.join(root, rt_name)

    total_units = 0
    for cell in cells:
        total_units += len(rcp_gcms[cell["rcp"]]) * len(batch_list)
    total_units *= len(models)

    # Slurm tasks for this sector and run type, mapped to units when the
    # array order is known (quick_test, single).
    job_name = sector["job_names"][rt_name]
    array_cells = rt_cfg.get("array_cells")

    # Keep one task per unit: live tasks beat finished ones, then latest end.
    def task_rank(t):
        return (1 if t["state"] in ("RUNNING", "PENDING") else 0, t["end"] or "")

    by_unit = {}
    for task in slurm_tasks.get(job_name, []):
        if task["task"] is None or not array_cells:
            continue
        mi, ci = divmod(task["task"], len(array_cells))
        if mi >= len(models):
            continue
        ssp, rcp, iam = array_cells[ci].split("-")
        key = (models[mi], ssp.upper(), rcp, iam)
        prev = by_unit.get(key)
        if prev is None or task_rank(task) > task_rank(prev):
            by_unit[key] = task

    counts = {s: 0 for s in ["not_started", "queued", "running", "partial", "done", "failed"]}
    units = []

    for model in models:
        model_dir = rt_root if model == "main" else os.path.join(rt_root, model)
        twin_root = None if model == "main" else os.path.join(rt_root, f"{model}-1pct_winsorization")
        for batch_name in batch_list:
            base_dir = os.path.join(model_dir, batch_name) if batch_name else model_dir
            batch_num = int(batch_name[5:]) if batch_name else None
            for cell in cells:
                rcp_dir = os.path.join(base_dir, cell["rcp"])
                rcp_exists = os.path.isdir(rcp_dir)
                for gcm in rcp_gcms[cell["rcp"]]:
                    leaf = os.path.join(rcp_dir, gcm, cell["iam"], cell["ssp"])
                    info = read_leaf(leaf) if rcp_exists else None
                    task = by_unit.get((model, cell["ssp"], cell["rcp"], cell["iam"])) \
                        if batch_num is None else None

                    sizes = info["sizes"] if info else {}
                    twin_sizes = {}
                    if twin_root and spec[model]["twin"]:
                        twin_leaf = os.path.join(
                            twin_root, batch_name or "", cell["rcp"], gcm,
                            cell["iam"], cell["ssp"]).replace("//", "/")
                        twin_info = read_leaf(twin_leaf)
                        twin_sizes = twin_info["sizes"] if twin_info else {}

                    proj_found, proj_missing = count_group(spec[model]["projection"], cell["rcp"], sizes)
                    agg_leaf_found, agg_leaf_missing = count_group(spec[model]["leaf_aggregation"], cell["rcp"], sizes)
                    twin_found, twin_missing = count_group(spec[model]["twin"], cell["rcp"], twin_sizes)
                    agg_found = agg_leaf_found + twin_found
                    agg_missing = agg_leaf_missing + [f"winsorized/{n}" for n in twin_missing]
                    agg_total = len(spec[model]["aggregation"])

                    # Per-stage states from markers, files and Slurm.
                    stage_recs = {}
                    fail_reason = None
                    for stage in stages:
                        marker = info["markers"].get(stage) if info else None
                        _, done_word = STATUS_MARKERS.get(f"generate.{stage}", (None, None))
                        done = (marker is not None and done_word is not None and marker == done_word) or \
                            (info and stage_file_done(stage, spec[model], cell["rcp"], sizes, twin_sizes))
                        rec = {"state": "not_started"}
                        if done:
                            rec["state"] = "done"
                        elif task and stage == "generate":
                            if task["state"] == "RUNNING":
                                rec["state"] = "running"
                            elif task["state"] == "PENDING":
                                rec["state"] = "queued"
                            elif task["state"] in FAILED_STATES:
                                rec["state"] = "failed"
                                fail_reason = task["state"]
                        elif info and info["claims"].get(stage) and fresh(info["mtime"]):
                            rec["state"] = "running"
                        elif marker is not None and done_word is not None and marker != done_word:
                            rec["state"] = "failed"
                            fail_reason = fail_reason or f"{stage} {marker}"
                        if task and stage == "generate" and rec["state"] != "not_started":
                            rec["job"] = f"{task['base']}_{task['task']}"
                            if task["elapsed_s"]:
                                rec["elapsed_min"] = round(task["elapsed_s"] / 60.0, 1)
                            if task["max_rss_gb"] is not None:
                                rec["max_rss_gb"] = task["max_rss_gb"]
                            if task["req_mem_gb"] is not None:
                                rec["req_mem_gb"] = task["req_mem_gb"]
                        stage_recs[stage] = rec

                    stage_states = [stage_recs[s]["state"] for s in stages]
                    if "failed" in stage_states:
                        state = "failed"
                    elif "running" in stage_states:
                        state = "running"
                    elif "queued" in stage_states:
                        state = "queued"
                    elif all(s == "done" for s in stage_states):
                        state = "done"
                    elif "done" in stage_states:
                        state = "partial"
                    else:
                        state = "not_started"

                    has_signal = proj_found or agg_found or state != "not_started" or \
                        (info and (info["markers"] or any(info["claims"].values())))
                    counts[state] += 1
                    if not has_signal:
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
                    if task:
                        unit["log"] = f"{log_prefix}_{task['base']}_{task['task']}.out"
                    units.append(unit)

    counts["total"] = total_units
    return {
        "dims": {"models": models, "cells": cells, "gcms": rcp_gcms, "batches": batches},
        "counts": counts,
        "units": units,
        "job_name": job_name,
    }


def eta_for(rt_out, slurm_tasks):
    """Estimate from average completed generate-task time and current activity."""
    c = rt_out["counts"]
    remaining = c["not_started"] + c["queued"] + c["running"] + c["partial"]
    if remaining == 0:
        return None, None
    done_secs = [t["elapsed_s"] for t in slurm_tasks.get(rt_out["job_name"], [])
                 if t["state"] == "COMPLETED" and t["elapsed_s"]]
    running = sum(1 for t in slurm_tasks.get(rt_out["job_name"], []) if t["state"] == "RUNNING")
    if not done_secs or not running:
        return None, "no finished jobs to average yet" if not done_secs else "no jobs running"
    avg_h = sum(done_secs) / len(done_secs) / 3600.0
    eta = remaining * avg_h / running
    return round(eta, 1), f"{remaining} units left, {running} running, ~{avg_h:.1f} h per unit"


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--cil-root", default="/project/cil",
                        help="where /project/cil is mounted")
    parser.add_argument("--no-slurm", action="store_true",
                        help="skip squeue and sacct")
    parser.add_argument("--out", default=os.path.join(HERE, "site", "status.json"))
    args = parser.parse_args()
    now = datetime.datetime.now(datetime.timezone.utc)

    with open(os.path.join(HERE, "manifest.yml")) as f:
        manifest = yaml.safe_load(f)

    use_slurm = not args.no_slurm and shutil.which("sacct") and shutil.which("squeue")
    if not use_slurm:
        log("slurm tools not used; job states come from files and markers only")
        slurm_tasks, slurm_su = {}, {"by_user": {}, "by_name": {}}
        balance = {"allocation_su": None, "used_su": None, "balance_su": None}
    else:
        slurm_tasks, slurm_su = collect_slurm(manifest["account"]["name"],
                                              manifest["account"]["su_since"])
        balance = account_balance(manifest["account"]["name"])

    name_to_scope = {}
    for sector_name, sector in manifest["sectors"].items():
        for rt_name, jname in sector["job_names"].items():
            name_to_scope[jname] = (sector_name, rt_name)

    sectors_out = {}
    for sector_name, sector in manifest["sectors"].items():
        spec = file_spec_for(manifest["files"], sector_name)
        run_types_out = {}
        for rt_name in sector["run_types"]:
            out = scan_run_type(sector_name, sector, rt_name, manifest, spec,
                                args.cil_root, slurm_tasks)
            eta, basis = eta_for(out, slurm_tasks)
            job_name = out.pop("job_name")
            out["eta_hours"] = eta
            out["eta_basis"] = basis
            out["su_used"] = round(slurm_su["by_name"].get(job_name, 0))
            run_types_out[rt_name] = out
            c = out["counts"]
            log(f"{sector_name}/{rt_name}: total {c['total']}, done {c['done']}, "
                f"running {c['running']}, queued {c['queued']}, failed {c['failed']}, "
                f"listed {len(out['units'])}")
        sectors_out[sector_name] = {
            "label": sector["label"],
            "stages": sector["stages"],
            "files_spec": {m: {"projection": g["projection"], "aggregation": g["aggregation"]}
                           for m, g in spec.items()},
            "run_types": run_types_out,
        }

    people = []
    for person in manifest["people"]:
        used = slurm_su["by_user"].get(person.get("username") or "", 0.0)
        people.append({"name": person["name"], "username": person.get("username"),
                       "su_used": round(used)})

    used_total = round(sum(slurm_su["by_user"].values()))
    status = {
        "schema_version": 1,
        "source": "collector",
        "generated_at": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "scan_interval_hours": 4,
        "account": {
            "name": manifest["account"]["name"],
            "allocation_su": balance["allocation_su"],
            "used_su": balance["used_su"] if balance["used_su"] is not None else used_total,
            "balance_su": balance["balance_su"],
        },
        "people": people,
        "sectors": sectors_out,
    }

    with open(args.out, "w") as f:
        json.dump(status, f, separators=(",", ":"))
    log(f"wrote {args.out} ({os.path.getsize(args.out) / 1024:.0f} KB)")


if __name__ == "__main__":
    main()
