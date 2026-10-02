#!/usr/bin/env python3
"""Compare the new-socioeconomics panel against the previous output-wpp run.

Asserts, per scenario x model combination:
  - identical rows through the population handoff year (2023)
  - identical gdppc, gdppc_raw, gdppc_raw0 and area_km2 in every year
  - population that differs after 2023 (the SSP trajectories took over)
  - SSP2 and SSP3 national populations equal at 2023, different after

Prints national population for selected countries and the world in 2050 and
2100, old vs new. Standard library only. Exits nonzero on any failure.
Override the new output location with the NEW_OUTPUT environment variable.
"""

import csv
import os
import sys
from multiprocessing import Pool
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
OLD = REPO / "data" / "output-wpp"
NEW = Path(os.environ.get(
    "NEW_OUTPUT", "/project/cil/gcp/outputs_newsocioeconomics/socioeconomics"))
H = 2023
N_ROWS = 24378 * 120
IDENTICAL = ("gdppc", "gdppc_raw", "gdppc_raw0", "area_km2")
FOCUS = ("IND", "NGA", "USA", "CHN")
NAT_YEARS = ("2023", "2024", "2050", "2100")
TOL = 1e-9
COMBOS = [(s, m) for s in ("SSP2", "SSP3") for m in ("IIASA", "OECD")]


def rel(a, b):
    m = max(abs(a), abs(b))
    return abs(a - b) / m if m else 0.0


def compare(combo):
    """Stream one old/new CSV pair; return per-combination statistics."""
    scen, model = combo
    name = "ir_combined_%s_%s.csv" % (scen, model)
    s = {"combo": "%s_%s" % (scen, model), "rows": 0, "align_errors": 0,
         "pre_max": 0.0, "ident_max": 0.0, "pop_diff_rows": 0,
         "pop_diff_isos": set(), "pop_max": 0.0, "nat": {}}
    with open(OLD / name) as fo, open(NEW / name) as fn:
        ro, rn = csv.reader(fo), csv.reader(fn)
        ho, hn = next(ro), next(rn)
        if ho != hn:
            s["align_errors"] += 1
            return s
        ix = {c: ho.index(c) for c in ho}
        iy, ipop, iiso = ix["year"], ix["pop"], ix["iso3"]
        ident_ix = [ix[c] for c in IDENTICAL]
        for o, n in zip(ro, rn):
            s["rows"] += 1
            if o[0] != n[0] or o[iy] != n[iy]:
                s["align_errors"] += 1
                if s["align_errors"] > 5:
                    return s
                continue
            y = o[iy]
            if y in NAT_YEARS:
                po, pn = float(o[ipop]), float(n[ipop])
                for key in ((n[iiso], y), ("GLOBAL", y)):
                    og, ng = s["nat"].get(key, (0.0, 0.0))
                    s["nat"][key] = (og + po, ng + pn)
            if int(y) <= H:
                # Every column must match through the handoff.
                for i, (a, b) in enumerate(zip(o, n)):
                    if a == b:
                        continue
                    try:
                        s["pre_max"] = max(s["pre_max"],
                                           rel(float(a), float(b)))
                    except ValueError:
                        s["pre_max"] = max(s["pre_max"], 1.0)
            else:
                # Income and area never change; population is allowed to.
                for i in ident_ix:
                    a, b = o[i], n[i]
                    if a == b:
                        continue
                    if a == "" or b == "":
                        s["ident_max"] = max(s["ident_max"], 1.0)
                        continue
                    s["ident_max"] = max(s["ident_max"],
                                         rel(float(a), float(b)))
                r = rel(float(o[ipop]), float(n[ipop]))
                if r > TOL:
                    s["pop_diff_rows"] += 1
                    s["pop_diff_isos"].add(n[iiso])
                    s["pop_max"] = max(s["pop_max"], r)
    return s


def main():
    failures = []

    def verdict(ok, text):
        print("%s: %s" % ("PASS" if ok else "FAIL", text))
        if not ok:
            failures.append(text)

    with Pool(min(4, os.cpu_count() or 1)) as pool:
        results = {s["combo"]: s for s in pool.map(compare, COMBOS)}

    for tag, s in sorted(results.items()):
        print("== %s (%s rows)" % (tag, format(s["rows"], ",")))
        verdict(s["align_errors"] == 0 and s["rows"] == N_ROWS,
                "%s rows aligned between old and new" % tag)
        verdict(s["pre_max"] <= TOL,
                "%s identical through %d (max rel diff %.2e)"
                % (tag, H, s["pre_max"]))
        verdict(s["ident_max"] <= TOL,
                "%s gdppc/raw/raw0/area identical in all years "
                "(max rel diff %.2e)" % (tag, s["ident_max"]))
        verdict(s["pop_diff_rows"] > 0,
                "%s population changed after %d (%s rows, %d countries, "
                "max rel diff %.2e)" % (tag, H, format(s["pop_diff_rows"], ","),
                                        len(s["pop_diff_isos"]), s["pop_max"]))

    # SSP2 vs SSP3 in the new output: equal at the handoff, apart after it.
    for model in ("IIASA", "OECD"):
        a, b = results["SSP2_" + model]["nat"], results["SSP3_" + model]["nat"]
        isos = {k[0] for k in a} - {"GLOBAL"}
        eq_h = max(rel(a[(i, "2023")][1], b[(i, "2023")][1])
                   for i in isos if (i, "2023") in a and (i, "2023") in b)
        verdict(eq_h <= TOL,
                "%s: SSP2 == SSP3 national pop at 2023 (max rel %.2e)"
                % (model, eq_h))
        for y in ("2024", "2050", "2100"):
            n_diff = sum(1 for i in isos
                         if (i, y) in a and (i, y) in b
                         and rel(a[(i, y)][1], b[(i, y)][1]) > TOL)
            verdict(n_diff > 0,
                    "%s: SSP2 != SSP3 national pop at %s (%d countries "
                    "differ)" % (model, y, n_diff))

    # Report: population in millions, old vs new (IIASA files; population is
    # model-independent).
    print("\nPopulation, millions (IIASA files)")
    print("%-8s%-6s%12s%12s%12s%12s%12s" %
          ("iso", "year", "old", "new SSP2", "new SSP3", "SSP2 vs old",
           "SSP3 vs old"))
    for iso in FOCUS + ("GLOBAL",):
        for y in ("2050", "2100"):
            o2, n2 = results["SSP2_IIASA"]["nat"].get((iso, y), (0.0, 0.0))
            _, n3 = results["SSP3_IIASA"]["nat"].get((iso, y), (0.0, 0.0))
            print("%-8s%-6s%12.1f%12.1f%12.1f%11.2f%%%11.2f%%" %
                  (iso, y, o2 / 1e6, n2 / 1e6, n3 / 1e6,
                   (n2 - o2) / o2 * 100 if o2 else float("nan"),
                   (n3 - o2) / o2 * 100 if o2 else float("nan")))

    print("\n%d failure(s)" % len(failures) if failures else "\nAll passed")
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()
