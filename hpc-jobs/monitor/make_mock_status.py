#!/usr/bin/env python3
"""Generate a realistic mock status.json from the manifest.

The mock uses the same file format the real collector will write, so the site
can be built and deployed against it now and switched to real data later
without changes.

Usage:
    python3 make_mock_status.py [--seed N] [--out PATH]
"""

import argparse
import datetime
import json
import os
import random
import shutil

import yaml

HERE = os.path.dirname(os.path.abspath(__file__))

# How far along each sector and run type is in the mock, as rough fractions
# of units in each state. Whatever is left over is not started.
MOCK_PROGRESS = {
    ("mortality", "quick_test"):   {"done": 1.0},
    ("mortality", "single"):       {"done": 1.0},
    ("mortality", "median"):       {"done": 0.55, "running": 0.12, "failed": 0.03, "partial": 0.05},
    ("mortality", "montecarlo"):   {"done": 0.12, "running": 0.04, "failed": 0.01, "partial": 0.02},
    ("agriculture", "quick_test"): {"done": 1.0},
    ("agriculture", "single"):     {"done": 0.60, "running": 0.10, "failed": 0.05, "partial": 0.12},
    ("agriculture", "median"):     {},
    ("agriculture", "montecarlo"): {},
    ("energy", "quick_test"):      {"failed": 1.0},
    ("energy", "single"):          {"done": 0.80, "running": 0.06, "failed": 0.07, "partial": 0.07},
    ("energy", "median"):          {"running": 0.05},
    ("energy", "montecarlo"):      {},
    ("labor", "quick_test"):       {"done": 1.0},
    ("labor", "single"):           {"done": 1.0},
    ("labor", "median"):           {"done": 0.30, "running": 0.15, "failed": 0.02, "partial": 0.08},
    ("labor", "montecarlo"):       {},
}

FAIL_REASONS = ["aggregate ended as Incomplete",
                "generate stopped: no file changes for 6 h",
                "aggregate stopped: no file changes for 6 h"]

# Job names people might have on the account, projection runs or not.
MOCK_JOB_NAMES = [
    ("mortality-median", "caslake", 120), ("labor-median", "caslake", 120),
    ("energy-median", "caslake", 120), ("agriculture-single", "caslake", 56),
    ("energy-quick-test", "cil", 2), ("sccs-pipeline", "caslake", 30),
    ("interactive", "cil", 1), ("jupyter", "amd", 1), ("dscim-run", "amd", 40),
]




def mock_ended_badly(rng, users, now):
    """A few jobs that ended badly in the last days, newest first."""
    ends = ["timeout", "out of memory", "failed", "cancelled"]
    rows = []
    for _ in range(rng.randint(3, 7)):
        name, partition, size = rng.choice(MOCK_JOB_NAMES)
        end = now - datetime.timedelta(minutes=rng.randint(30, 3 * 24 * 60))
        rows.append({"job_id": str(rng.randint(59_900_000, 60_100_000)), "job_name": name,
                     "user": rng.choice(users), "partition": partition, "ended": rng.choice(ends),
                     "tasks": rng.randint(1, min(size, 12)), "elapsed_min": round(rng.uniform(1, 2160), 1),
                     "end": end.strftime("%Y-%m-%dT%H:%M:%SZ")})
    rows.sort(key=lambda r: r["end"], reverse=True)
    return rows


def mock_su_estimate(counts, stages, sector, rt_name):
    """Same rules as the collector: reference time and job limit, since the
    mock has no file dates."""
    ref = sector.get("reference") or {}
    limit = ref.get("time_limit_hours")
    if isinstance(limit, dict):
        limit = limit.get(rt_name)
    remaining = counts["total"] - counts["done"] - counts["partial"]
    if remaining <= 0:
        return {"remaining": 0, "su_low": 0, "su_high": 0, "basis": "nothing left to run"}
    low, billing = ref.get("hours_per_unit"), ref.get("billing", 1)
    if low is None:
        return {"remaining": remaining, "su_low": None, "su_high": None, "source": "unknown",
                "basis": "not known yet: no reference time per unit"}
    high = ref.get("hours_per_unit_max") or limit or low
    what = "longest reference" if ref.get("hours_per_unit_max") else "job limit"
    return {"remaining": remaining, "hours_low": low, "hours_high": high,
            "su_low": round(remaining * low * billing), "su_high": round(remaining * high * billing),
            "source": "reference",
            "basis": f"{remaining:,} units left × {low:g} h (reference) to {high:g} h ({what}), {billing:g} SU per hour"}


def mock_active_jobs(rng, now):
    """Zero to three running or queued jobs for one person."""
    jobs = []
    for name, partition, size in rng.sample(MOCK_JOB_NAMES, rng.randint(0, 3)):
        running = rng.randint(1, min(size, 40))
        queued = rng.randint(0, size - running) if rng.random() < 0.6 else 0
        limit = rng.choice([12, 24, 36]) * 60.0
        elapsed = round(rng.uniform(5, limit - 10), 1)
        jobs.append({
            "job_id": str(rng.randint(59_900_000, 60_100_000)),
            "job_name": name,
            "partition": partition + (",amd" if partition == "caslake" and rng.random() < 0.4 else ""),
            "running_on": ({partition: running} if partition != "caslake" or running < 4 else
                           {partition: running - (k := rng.randint(1, running // 3)), "amd": k}),
            "started": (now - datetime.timedelta(minutes=elapsed + rng.uniform(0, 600))).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "state": "RUNNING",
            "tasks": {"running": running, "queued": queued,
                      "done": rng.randint(0, max(size - running - queued, 0)),
                      "failed": rng.randint(1, 3) if rng.random() < 0.2 else 0},
            "elapsed_min": elapsed,
            "cpus": rng.choice([1, 1, 2, 4]), "mem": rng.choice(["45G", "64G", "8G", "16G"]),
            "limit_min": limit,
            "left_min": round(limit - elapsed, 1),
        })
    if rng.random() < 0.4:
        name, partition, size = rng.choice(MOCK_JOB_NAMES)
        queued = rng.randint(1, size)
        jobs.append({"job_id": str(rng.randint(59_900_000, 60_100_000)),
                     "job_name": name, "partition": partition, "running_on": {}, "started": None, "state": "PENDING",
                     "tasks": {"running": 0, "queued": queued, "done": 0, "failed": 0},
                     "elapsed_min": 0.0, "cpus": 1, "mem": "45G", "limit_min": 36 * 60.0, "left_min": None})
    jobs.sort(key=lambda j: (j["state"] != "RUNNING", -j["elapsed_min"]))
    return jobs


GROUPS = ["projection", "costs", "levels", "aggregated"]


def model_dir_for(sector, rt_name, rt_cfg, model):
    """Same rule as the collector: the sector's layout, empty parts dropped."""
    rel = sector.get("layout", "{run_type}/{model}/{subdir}").format(
        run_type=rt_name, model="" if model == "main" else model, subdir=rt_cfg.get("subdir") or "")
    return os.path.join(sector["output_root"], *[p for p in rel.split("/") if p])


def file_spec_for(files_cfg, sector_name):
    """Expected files per sub-model, by group, in a fixed order."""
    return {model: {g: list(groups.get(g) or []) for g in GROUPS}
            for model, groups in files_cfg[sector_name].items()}


def files_for_unit(spec, unit_stages, stages, rng, now):
    """File counts, presence bits and per-file size and date, consistent
    with the unit's stage states. Files appear in list order while a stage
    runs, so the missing ones are always the tail of each list."""
    agg_stages = [s for s in stages if s != "generate"]

    def fraction(state):
        if state == "done":
            return 1.0
        if state == "running":
            return rng.uniform(0.15, 0.9)
        if state == "failed":
            return rng.uniform(0.0, 0.6)
        return 0.0

    gen_frac = fraction(unit_stages["generate"]["state"])
    agg_frac = sum(fraction(unit_stages[s]["state"]) for s in agg_stages) / len(agg_stages)
    agg_names = [n for g in GROUPS[1:] for n in spec[g]]
    agg_on = set(agg_names[:round(agg_frac * len(agg_names))])
    proj_on = set(spec["projection"][:round(gen_frac * len(spec["projection"]))])

    files, bits, detail = {}, "", []
    base_time = int(now.timestamp() - rng.uniform(3, 200) * 3600)
    for g in GROUPS:
        on = proj_on if g == "projection" else agg_on
        files[g] = {"found": sum(1 for n in spec[g] if n in on), "total": len(spec[g])}
        for i, n in enumerate(spec[g]):
            if n in on:
                bits += "1"
                size = int(rng.uniform(40, 50) * 1e6) if g == "projection" else int(rng.uniform(3, 25) * 1e6)
                detail.append([size, base_time + i * 600 + (0 if g == "projection" else 7200)])
            else:
                bits += "0"
                detail.append(0)
    return files, bits, detail


def cells_for(run_type_cfg, scenarios):
    """List the SSP-RCP-IAM cells a run type covers, in display order."""
    cells_cfg = run_type_cfg["cells"]
    if cells_cfg == "all":
        ssps = scenarios["ssps"]
        iams = scenarios["iams"]
        rcp_filter = None
    else:
        ssps = cells_cfg["ssps"]
        iams = cells_cfg["iams"]
        rcp_filter = cells_cfg["rcps"]
    cells = []
    for ssp in ssps:
        for rcp in scenarios["valid_pairs"][ssp]:
            if rcp_filter and rcp not in rcp_filter:
                continue
            for iam in iams:
                cells.append({"ssp": ssp, "rcp": rcp, "iam": iam})
    return cells


def gcms_for(run_type_cfg, gcms):
    """GCM list per RCP for a run type."""
    cfg = run_type_cfg["gcms"]
    if cfg == "per_rcp":
        return {rcp: list(models) for rcp, models in gcms.items()}
    return {rcp: list(cfg) for rcp in gcms}


def expand_units(cells, rcp_gcms, batches, models):
    """Every unit of work for one sector and run type."""
    units = []
    batch_list = list(range(batches)) if batches else [None]
    for model in models:
        for cell in cells:
            for gcm in rcp_gcms[cell["rcp"]]:
                for batch in batch_list:
                    units.append({"model": model, "ssp": cell["ssp"],
                                  "rcp": cell["rcp"], "iam": cell["iam"],
                                  "gcm": gcm, "batch": batch})
    return units


def pick_state(index, total, fractions, rng):
    """Assign a state so progress looks like a sweep with ragged edges."""
    order = ["done", "partial", "failed", "running"]
    position = (index + rng.uniform(-0.04, 0.04) * total) / max(total, 1)
    cumulative = 0.0
    for state in order:
        share = fractions.get(state, 0.0)
        cumulative += share
        if share > 0 and position < cumulative:
            return state
    return "not_started"


def make_stage(state, rng, now):
    """One stage record: its state, and when it finished if done."""
    record = {"state": state}
    if state == "done":
        finished = now - datetime.timedelta(hours=rng.uniform(1, 240))
        record["finished"] = finished.strftime("%Y-%m-%dT%H:%M:%SZ")
    return record


def make_unit(stages, unit, state, rng, now):
    """Fill in per-stage records consistent with the unit's overall state."""
    unit = dict(unit)
    unit["state"] = state
    if state == "done":
        done_until = len(stages)
    elif state == "partial":
        done_until = rng.randint(1, max(len(stages) - 1, 1))
    else:  # running or failed
        done_until = rng.randint(0, len(stages) - 1)
    stage_records = {}
    for i, stage in enumerate(stages):
        if i < done_until:
            stage_state = "done"
        elif i == done_until and state in ("running", "failed"):
            stage_state = state
        else:
            stage_state = "not_started"
        stage_records[stage] = make_stage(stage_state, rng, now)
    if state == "failed":
        unit["fail_reason"] = rng.choice(FAIL_REASONS)
    unit["stages"] = stage_records
    return unit


def eta_for(counts, stages, rng):
    """Plausible estimate in the collector's terms: projection units left at
    the pace of the units being written now, and aggregation apart."""
    left = counts["not_started"] + counts["running"] + counts["failed"]
    agg = {"started": counts["done"] > 0, "done": counts["done"]}
    if left == 0:
        return {"hours": 0, "method": None, "basis": "all projections done"}, agg
    if counts["running"] == 0:
        return {"hours": None, "method": None,
                "basis": f"{left:,} projection units left; not enough data yet"}, agg
    per_unit = round(rng.uniform(2, 24), 1)
    pace = counts["running"] / per_unit
    return {"hours": round(left / pace, 1), "method": "writing",
            "basis": f"{left:,} projection units left; {counts['running']:,} being written now at "
                     f"{per_unit} h per unit (sacct), so {pace:.1f} units per hour"}, agg


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--out-dir", default=os.path.join(HERE, "site", "mock"))
    args = parser.parse_args()
    rng = random.Random(args.seed)
    now = datetime.datetime.now(datetime.timezone.utc)

    with open(os.path.join(HERE, "manifest.yml")) as f:
        manifest = yaml.safe_load(f)

    os.makedirs(args.out_dir, exist_ok=True)
    shutil.rmtree(os.path.join(args.out_dir, "details"), ignore_errors=True)
    sectors_out = {}
    for sector_name, sector in manifest["sectors"].items():
        files_spec = file_spec_for(manifest["files"], sector_name)
        run_types_out = {}
        for run_type in sector["run_types"]:
            rt_cfg = manifest["run_types"][run_type]
            if not rt_cfg.get("enabled", True):
                continue
            cells = cells_for(rt_cfg, manifest["scenarios"])
            rcp_gcms = gcms_for(rt_cfg, manifest["gcms"])
            batches = rt_cfg.get("batches")
            all_units = expand_units(cells, rcp_gcms, batches, sector["models"])
            fractions = MOCK_PROGRESS.get((sector_name, run_type), {})

            counts = {s: 0 for s in ["not_started", "running", "partial", "done", "failed"]}
            listed = []
            details = {}
            # Sectors with a main aggregation scenario also get one additional
            # scenario on some finished units, as the collector would find it.
            main_scen = sector.get("aggregation_scenario")
            alt_scen = "MERGEETL60_{rcp}" if main_scen else None
            seen_alt = False
            for i, unit in enumerate(all_units):
                state = pick_state(i, len(all_units), fractions, rng)
                counts[state] += 1
                if state != "not_started":
                    made = make_unit(sector["stages"], unit, state, rng, now)
                    made["files"], made["bits"], detail = files_for_unit(
                        files_spec[made["model"]], made["stages"], sector["stages"], rng, now)
                    listed.append(made)
                    key = "|".join([made["ssp"], made["rcp"], made["iam"], made["gcm"]])
                    if "1" in made["bits"]:
                        details.setdefault((made["model"], made["batch"]), {})[key] = detail
                    spec_m = files_spec[made["model"]]
                    n_proj = len(spec_m["projection"])
                    n_agg = len(made["bits"]) - n_proj
                    if alt_scen and n_agg and made["bits"][:n_proj] == "1" * n_proj and rng.random() < 0.6:
                        # Half of these have both scenarios complete; the rest a
                        # partial set of the additional one.
                        both = rng.random() < 0.5
                        k = n_agg if both else rng.randint(1, n_agg - 1)
                        if both:
                            made["bits"] = "1" * len(made["bits"])
                            made["files"] = {g: {"found": f["total"], "total": f["total"]} for g, f in made["files"].items()}
                            made["state"] = "done"
                            for st in made["stages"].values():
                                st["state"] = "done"
                            rec = details.setdefault((made["model"], made["batch"]), {}).setdefault(key, detail)
                            for j in range(n_proj, len(rec)):
                                if not rec[j]:
                                    rec[j] = [int(rng.uniform(3, 25) * 1e6), int(now.timestamp()) - rng.randint(0, 86400)]
                        made["alt_bits"] = {alt_scen: "1" * k + "0" * (n_agg - k)}
                        details.setdefault((made["model"], made["batch"]), {})[f"{alt_scen}#{key}"] = \
                            [[int(rng.uniform(3, 25) * 1e6), int(now.timestamp()) - rng.randint(0, 86400)] if j < k else 0
                             for j in range(n_agg)]
                        seen_alt = True
            counts["total"] = len(all_units)

            eta, agg = eta_for(counts, sector["stages"], rng)
            run_types_out[run_type] = {
                "dims": {
                    "models": sector["models"],
                    "cells": cells,
                    "gcms": rcp_gcms,
                    "batches": batches,
                },
                "model_dirs": {m: model_dir_for(sector, run_type, rt_cfg, m) for m in sector["models"]},
                "agg_scenarios": {"main": main_scen, "others": [alt_scen] if seen_alt else []} if main_scen else None,
                "counts": counts,
                "eta_hours": eta["hours"],
                "eta_method": eta["method"],
                "eta_basis": eta["basis"],
                "aggregation": agg,
                "unit_time_source": "sacct" if eta["method"] == "writing" else None,
                "su_estimate": mock_su_estimate(counts, sector["stages"], sector, run_type),
                "last_projection_write": (now - datetime.timedelta(hours=rng.uniform(1, 12))).strftime("%Y-%m-%dT%H:%M:%SZ")
                    if counts["running"] else None,
                "units": listed,
            }
            for (model, batch), cells_ in details.items():
                name = f"{model}.json" if batch is None else f"{model}/batch{batch}.json"
                path = os.path.join(args.out_dir, "details", sector_name, run_type, name)
                os.makedirs(os.path.dirname(path), exist_ok=True)
                with open(path, "w") as f:
                    json.dump(cells_, f, separators=(",", ":"))
        sectors_out[sector_name] = {
            "label": sector["label"],
            "stages": sector["stages"],
            "disabled_run_types": sector.get("disabled_run_types", []),
            "files_spec": files_spec,
            "run_types": run_types_out,
        }

    # Placeholder usernames: the mock never shows real accounts.
    users = []
    acct = manifest["account"]
    for i in range(1, 10):
        users.append({"user": f"user{i:02d}", "active_jobs": mock_active_jobs(rng, now)})
    if acct.get("highlight_user"):
        users.append({"user": acct["highlight_user"], "active_jobs": mock_active_jobs(rng, now)})
    for name in acct.get("always_show_users", []):
        users.append({"user": name, "active_jobs": []})
    users.sort(key=lambda r: r["user"])

    billed_users = {u["user"]: round(rng.uniform(2_000, 30_000), 2) for u in users[:4]}
    total_su = round(sum(billed_users.values()), 2)
    allocation = 1_200_000
    status = {
        "schema_version": 8,
        "source": "mock",
        "generated_at": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "scan_interval_hours": 1,
        "account": {
            "name": manifest["account"]["name"],
            "allocation_status": "ok",
            "allocation_su": allocation,
            "used_su": round(total_su),
            "balance_su": allocation - round(total_su),
            "billed": {
                "by_user": {"total": total_su, "by": dict(sorted(billed_users.items(), key=lambda x: -x[1]))},
                "by_partition": {"total": total_su, "by": {"caslake": round(total_su * 0.8, 2), "amd": round(total_su * 0.2, 2)}},
            },
            "highlight_user": manifest["account"].get("highlight_user"),
            "storage": [
                {"label": "cil /project", "used": "412.6T", "quota": "500.0T", "used_pct": 82.5},
                {"label": "cil /cds3", "used": "61.2T", "quota": "125.0T", "used_pct": 49.0},
            ],
        },
        "users": users,
        "ended_badly": mock_ended_badly(rng, [u["user"] for u in users if u["active_jobs"]], now),
        "ended_badly_days": manifest["account"].get("ended_badly_days", 3),
        "sectors": sectors_out,
    }

    out = os.path.join(args.out_dir, "status.json")
    with open(out, "w") as f:
        json.dump(status, f, separators=(",", ":"))
    size_kb = os.path.getsize(out) / 1024
    n_units = sum(rt["counts"]["total"] for s in sectors_out.values()
                  for rt in s["run_types"].values())
    print(f"wrote {out} ({size_kb:.0f} KB, {n_units} units tracked)")


if __name__ == "__main__":
    main()
