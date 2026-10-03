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

import yaml

HERE = os.path.dirname(os.path.abspath(__file__))

# Rough per-stage runtime and memory per sector, used to invent plausible
# elapsed minutes and MaxRSS values.
STAGE_PROFILE = {
    "mortality":   {"generate": (140, 46, 64), "aggregate": (45, 14, 45)},
    "agriculture": {"generate": (90, 30, 45), "aggregate": (35, 12, 45),
                    "costs": (30, 10, 45), "post": (20, 6, 45)},
    "energy":      {"generate": (210, 38, 64), "aggregate": (60, 16, 45)},
    "labor":       {"generate": (160, 40, 64), "aggregate": (75, 18, 45)},
}

# How far along each sector and run type is in the mock, as rough fractions
# of units in each state. Whatever is left over is not started.
MOCK_PROGRESS = {
    ("mortality", "quick_test"):   {"done": 1.0},
    ("mortality", "single"):       {"done": 1.0},
    ("mortality", "median"):       {"done": 0.55, "running": 0.12, "queued": 0.18, "failed": 0.03, "partial": 0.05},
    ("mortality", "montecarlo"):   {"done": 0.12, "running": 0.04, "queued": 0.05, "failed": 0.01, "partial": 0.02},
    ("agriculture", "quick_test"): {"done": 1.0},
    ("agriculture", "single"):     {"done": 0.60, "running": 0.10, "queued": 0.08, "failed": 0.05, "partial": 0.12},
    ("agriculture", "median"):     {},
    ("agriculture", "montecarlo"): {},
    ("energy", "quick_test"):      {"failed": 1.0},
    ("energy", "single"):          {"done": 0.80, "running": 0.06, "failed": 0.07, "partial": 0.07},
    ("energy", "median"):          {"queued": 0.25, "running": 0.05},
    ("energy", "montecarlo"):      {},
    ("labor", "quick_test"):       {"done": 1.0},
    ("labor", "single"):           {"done": 1.0},
    ("labor", "median"):           {"done": 0.30, "running": 0.15, "queued": 0.25, "failed": 0.02, "partial": 0.08},
    ("labor", "montecarlo"):       {},
}

FAIL_REASONS = ["OUT_OF_MEMORY", "TIMEOUT", "FAILED", "NODE_FAIL"]


def file_spec_for(files_cfg, sector_name):
    """Per-model expected file lists: projection and aggregation combined.

    Twin files (written to the -1pct_winsorization directory) get a
    winsorized/ prefix so the site can show where they live.
    """
    spec = {}
    for model, groups in files_cfg[sector_name].items():
        agg = list(groups["aggregation"])
        agg += [f"winsorized/{n}" for n in groups.get("aggregation_twin", [])]
        spec[model] = {"projection": list(groups["projection"]), "aggregation": agg}
    return spec


def files_for_unit(spec, unit_stages, stages, rng):
    """File counts per group, consistent with the unit's stage states.

    Files appear in list order while a stage runs, so the missing set is
    always the tail of the expected list.
    """
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

    out = {}
    for group, frac in (("projection", gen_frac), ("aggregation", agg_frac)):
        names = spec[group]
        total = len(names)
        found = round(frac * total)
        rec = {"found": found, "total": total}
        if 0 < found < total:
            rec["missing"] = names[found:]
        out[group] = rec
    return out


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
    order = ["done", "partial", "failed", "running", "queued"]
    position = (index + rng.uniform(-0.04, 0.04) * total) / max(total, 1)
    cumulative = 0.0
    for state in order:
        share = fractions.get(state, 0.0)
        cumulative += share
        if share > 0 and position < cumulative:
            return state
    return "not_started"


def make_stage(sector, stage, state, rng, job_base, array_index, now):
    """One stage record: state plus job id, elapsed time and memory."""
    typical_min, typical_gb, req_gb = STAGE_PROFILE[sector][stage]
    record = {"state": state}
    if state == "queued":
        record["job"] = f"{job_base}_{array_index}"
        return record
    if state == "not_started":
        return record
    elapsed = typical_min * rng.uniform(0.6, 1.5)
    record.update({
        "job": f"{job_base}_{array_index}",
        "elapsed_min": round(elapsed if state != "running" else elapsed * rng.uniform(0.2, 0.8), 1),
        "max_rss_gb": round(typical_gb * rng.uniform(0.7, 1.1), 1),
        "req_mem_gb": req_gb,
    })
    if state in ("done", "failed"):
        finished = now - datetime.timedelta(hours=rng.uniform(2, 240))
        record["finished"] = finished.strftime("%Y-%m-%dT%H:%M:%SZ")
    return record


def make_unit(sector, stages, unit, state, rng, job_base, array_index, log_prefix, now):
    """Fill in per-stage records consistent with the unit's overall state."""
    unit = dict(unit)
    unit["state"] = state
    stage_records = {}
    if state == "done":
        done_until = len(stages)
    elif state == "partial":
        done_until = rng.randint(1, max(len(stages) - 1, 1))
    elif state in ("running", "failed"):
        done_until = rng.randint(0, len(stages) - 1)
    else:  # queued
        done_until = 0
    for i, stage in enumerate(stages):
        if i < done_until:
            stage_state = "done"
        elif i == done_until and state in ("running", "failed", "queued"):
            stage_state = state if state != "queued" else "queued"
        else:
            stage_state = "not_started"
        stage_records[stage] = make_stage(sector, stage, stage_state, rng,
                                          job_base, array_index, now)
    if state == "failed":
        unit["fail_reason"] = rng.choice(FAIL_REASONS)
    unit["stages"] = stage_records
    unit["log"] = f"{log_prefix}_{job_base}_{array_index}.out"
    return unit


def eta_for(counts, sector, stages):
    """Plausible time to finish from remaining work and current activity."""
    remaining = counts["not_started"] + counts["queued"] + counts["running"] + counts["partial"]
    if remaining == 0:
        return None, None
    active = max(counts["running"], 1)
    hours_per_unit = sum(STAGE_PROFILE[sector][s][0] for s in stages) / 60.0
    if counts["running"] == 0 and counts["queued"] == 0:
        return None, "no jobs running or queued"
    eta = remaining * hours_per_unit / active
    basis = f"{remaining} units left, {counts['running']} running, ~{hours_per_unit:.1f} h per unit"
    return round(eta, 1), basis


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--out", default=os.path.join(HERE, "site", "status.json"))
    args = parser.parse_args()
    rng = random.Random(args.seed)
    now = datetime.datetime.now(datetime.timezone.utc)

    with open(os.path.join(HERE, "manifest.yml")) as f:
        manifest = yaml.safe_load(f)

    sectors_out = {}
    sector_su = {}
    for sector_name, sector in manifest["sectors"].items():
        files_spec = file_spec_for(manifest["files"], sector_name)
        run_types_out = {}
        for run_type in sector["run_types"]:
            rt_cfg = manifest["run_types"][run_type]
            cells = cells_for(rt_cfg, manifest["scenarios"])
            rcp_gcms = gcms_for(rt_cfg, manifest["gcms"])
            batches = rt_cfg.get("batches")
            all_units = expand_units(cells, rcp_gcms, batches, sector["models"])
            fractions = MOCK_PROGRESS.get((sector_name, run_type), {})

            job_base = rng.randint(59_900_000, 60_100_000)
            log_prefix = sector["log_prefixes"][run_type]
            counts = {s: 0 for s in
                      ["not_started", "queued", "running", "partial", "done", "failed"]}
            listed = []
            for i, unit in enumerate(all_units):
                state = pick_state(i, len(all_units), fractions, rng)
                counts[state] += 1
                if state != "not_started":
                    made = make_unit(sector_name, sector["stages"], unit,
                                     state, rng, job_base, i, log_prefix, now)
                    made["files"] = files_for_unit(files_spec[made["model"]],
                                                   made["stages"], sector["stages"], rng)
                    listed.append(made)
            counts["total"] = len(all_units)

            eta_hours, eta_basis = eta_for(counts, sector_name, sector["stages"])
            cpu_h = sum(st.get("elapsed_min", 0) for u in listed
                        for st in u["stages"].values()) / 60.0 * 28
            run_types_out[run_type] = {
                "dims": {
                    "models": sector["models"],
                    "cells": cells,
                    "gcms": rcp_gcms,
                    "batches": batches,
                },
                "counts": counts,
                "eta_hours": eta_hours,
                "eta_basis": eta_basis,
                "su_used": round(cpu_h),
                "units": listed,
            }
            sector_su[sector_name] = sector_su.get(sector_name, 0) + round(cpu_h)
        sectors_out[sector_name] = {
            "label": sector["label"],
            "stages": sector["stages"],
            "files_spec": files_spec,
            "run_types": run_types_out,
        }

    total_su = sum(sector_su.values())
    people = []
    weights = [rng.uniform(0.5, 2.0) for _ in manifest["people"]]
    for person, w in zip(manifest["people"], weights):
        people.append({
            "name": person["name"],
            "username": person.get("username"),
            "su_used": round(total_su * w / sum(weights)),
        })

    allocation = 5_000_000
    status = {
        "schema_version": 1,
        "source": "mock",
        "generated_at": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "scan_interval_hours": 4,
        "account": {
            "name": manifest["account"]["name"],
            "allocation_su": allocation,
            "used_su": total_su,
            "balance_su": allocation - total_su,
        },
        "people": people,
        "sectors": sectors_out,
    }

    with open(args.out, "w") as f:
        json.dump(status, f, separators=(",", ":"))
    size_kb = os.path.getsize(args.out) / 1024
    n_units = sum(rt["counts"]["total"] for s in sectors_out.values()
                  for rt in s["run_types"].values())
    print(f"wrote {args.out} ({size_kb:.0f} KB, {n_units} units tracked)")


if __name__ == "__main__":
    main()
