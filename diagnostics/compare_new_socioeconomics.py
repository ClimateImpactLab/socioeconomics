#!/usr/bin/env python3
"""Check the new-socioeconomics panel against the v4 book reference.

The previous baseline (the July output-wpp run) had broken geometry: it
was built without spherical (s2) validation, which corrupted the area
column everywhere and the grid-to-region assignment in the degenerate
regions. The check that caught this is the one kept here: before the
population handoff year (2023) the book and the new track share the same
historical income and geometry, so the SSP3/IIASA panel is compared
against ir_combined_SSP3_IIASA_v4 for income and area.

Asserts:
  - every v4 (region, year<=2023) row is present in the new output
  - area_km2 matches v4 within rounding (AREA_TOL)
  - gdppc matches v4 within the measured book-reproduction residual:
    a stable ~1,000-region set differs (2.4% of rows, mean rel ~5e-4),
    so the contract is a share-within-tolerance plus a mean bound
  - gdppc_raw matches v4 on rows where both sides are non-NA (the NA
    conventions differ by design in 1981-1989)
  - every scenario pair has equal national populations at 2023 and
    different ones after (internal consistency of the new output)

Prints national population for selected countries and the world in 2050
and 2100, v4 book vs new. Standard library only. Exits nonzero on any
failure. Override locations with NEW_OUTPUT and V4_REF.
"""

import csv
import os
import sys
from itertools import combinations
from multiprocessing import Pool
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
NEW = Path(os.environ.get(
    "NEW_OUTPUT", "/project/cil/gcp/outputs_newsocioeconomics/socioeconomics"))
V4 = Path(os.environ.get(
    "V4_REF", REPO.parent / "ref_data" / "ir_combined_SSP3_IIASA_v4.csv"))
H = 2023
N_ROWS = 24378 * 120
N_PRE = 24378 * (H - 1981 + 1)
FOCUS = ("IND", "NGA", "USA", "CHN")
NAT_YEARS = ("2023", "2024", "2050", "2100")
TOL = 1e-9
# Measured envelope of the book reproduction (see the geometry
# investigation): area matches v4 to 5.8e-7; gdppc matches exactly in
# 97.6% of pre-2023 rows with mean rel diff 5.0e-4; gdppc_raw matches in
# 99.3% of rows where both sides are non-NA.
AREA_TOL = 1e-6
GDPPC_SHARE_TOL = 1e-6
GDPPC_MIN_SHARE = 0.97
GDPPC_MAX_MEAN = 1e-3
RAW_MIN_SHARE = 0.99
SCENARIOS = ("SSP1", "SSP2", "SSP3", "SSP4", "SSP5")
COMBOS = [(s, m) for s in SCENARIOS for m in ("IIASA", "OECD")]
V4_COMBO = ("SSP3", "IIASA")


def rel(a, b):
    m = max(abs(a), abs(b))
    return abs(a - b) / m if m else 0.0


def compare(combo):
    """Stream one new CSV; the v4 combo also checks against the reference."""
    scen, model = combo
    name = "ir_combined_%s_%s.csv" % (scen, model)
    s = {"combo": "%s_%s" % (scen, model), "rows": 0, "nat": {}}

    ref = None
    if combo == V4_COMBO:
        ref = {}
        with open(V4) as fv:
            rv = csv.reader(fv)
            hv = next(rv)
            ih, iy = hv.index("hierid"), hv.index("year")
            ig, igr, ia, ipop = (hv.index("gdppc"), hv.index("gdppc_raw"),
                                 hv.index("area_km2"), hv.index("pop"))
            for v in rv:
                y = v[iy]
                if y in NAT_YEARS:
                    po = float(v[ipop])
                    for key in ((v[0][:3], y), ("GLOBAL", y)):
                        s["nat"].setdefault(key, [0.0, 0.0])
                        # v4 national pop goes in slot 0; new in slot 1
                        s["nat"][key][0] += po
                if int(y) <= H:
                    ref[(v[ih], y)] = (v[ig], v[igr], v[ia])
        s.update(v4_rows=0, v4_missing=0, area_max=0.0,
                 g_within=0, g_total=0, g_relsum=0.0, g_max=0.0,
                 raw_within=0, raw_total=0, raw_max=0.0)

    with open(NEW / name) as fn:
        rn = csv.reader(fn)
        hn = next(rn)
        ih, iy, iiso = hn.index("hierid"), hn.index("year"), hn.index("iso3")
        ig, igr, ia, ipop = (hn.index("gdppc"), hn.index("gdppc_raw"),
                             hn.index("area_km2"), hn.index("pop"))
        for n in rn:
            s["rows"] += 1
            y = n[iy]
            if y in NAT_YEARS:
                pn = float(n[ipop])
                for key in ((n[iiso], y), ("GLOBAL", y)):
                    s["nat"].setdefault(key, [0.0, 0.0])
                    s["nat"][key][1] += pn
            if ref is None or int(y) > H:
                continue
            v = ref.pop((n[ih], y), None)
            if v is None:
                s["v4_missing"] += 1
                continue
            s["v4_rows"] += 1
            s["area_max"] = max(s["area_max"], rel(float(n[ia]), float(v[2])))
            r = rel(float(n[ig]), float(v[0])) if n[ig] and v[0] else 1.0
            s["g_total"] += 1
            s["g_relsum"] += r
            s["g_max"] = max(s["g_max"], r)
            if r <= GDPPC_SHARE_TOL:
                s["g_within"] += 1
            if n[igr] and v[1]:
                r = rel(float(n[igr]), float(v[1]))
                s["raw_total"] += 1
                s["raw_max"] = max(s["raw_max"], r)
                if r <= GDPPC_SHARE_TOL:
                    s["raw_within"] += 1
    if ref is not None:
        s["v4_missing"] += len(ref)
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
        verdict(s["rows"] == N_ROWS,
                "%s has %s rows" % (tag, format(s["rows"], ",")))

    # New output vs the v4 book reference, years <= handoff.
    s = results["%s_%s" % V4_COMBO]
    verdict(s["v4_rows"] == N_PRE and s["v4_missing"] == 0,
            "v4 rows matched through %d (%s matched, %d unmatched)"
            % (H, format(s["v4_rows"], ","), s["v4_missing"]))
    verdict(s["area_max"] <= AREA_TOL,
            "area_km2 matches v4 within %.0e (max rel diff %.2e)"
            % (AREA_TOL, s["area_max"]))
    share = s["g_within"] / s["g_total"] if s["g_total"] else 0.0
    mean = s["g_relsum"] / s["g_total"] if s["g_total"] else 1.0
    verdict(share >= GDPPC_MIN_SHARE and mean <= GDPPC_MAX_MEAN,
            "gdppc matches v4 through %d (%.2f%% of rows within %.0e, "
            "mean rel %.2e, max rel %.2e)"
            % (H, 100 * share, GDPPC_SHARE_TOL, mean, s["g_max"]))
    share = s["raw_within"] / s["raw_total"] if s["raw_total"] else 0.0
    verdict(share >= RAW_MIN_SHARE,
            "gdppc_raw matches v4 on non-NA rows (%.2f%% within %.0e, "
            "max rel %.2e)" % (100 * share, GDPPC_SHARE_TOL, s["raw_max"]))

    # Scenario pairs in the new output: equal at the handoff, apart after it.
    for model in ("IIASA", "OECD"):
        nat = {s: results[s + "_" + model]["nat"] for s in SCENARIOS}
        isos = {k[0] for k in nat["SSP2"]} - {"GLOBAL"}
        eq_h = 0.0
        for s1, s2 in combinations(SCENARIOS, 2):
            a, b = nat[s1], nat[s2]
            eq_h = max([eq_h] + [rel(a[(i, "2023")][1], b[(i, "2023")][1])
                                 for i in isos
                                 if (i, "2023") in a and (i, "2023") in b])
        verdict(eq_h <= TOL,
                "%s: every scenario pair equal at 2023 (max rel %.2e)"
                % (model, eq_h))
        for y in ("2024", "2050", "2100"):
            worst, worst_pair = None, None
            for s1, s2 in combinations(SCENARIOS, 2):
                a, b = nat[s1], nat[s2]
                n_diff = sum(1 for i in isos
                             if (i, y) in a and (i, y) in b
                             and rel(a[(i, y)][1], b[(i, y)][1]) > TOL)
                if worst is None or n_diff < worst:
                    worst, worst_pair = n_diff, (s1, s2)
            verdict(worst > 0,
                    "%s: every scenario pair differs at %s (weakest pair "
                    "%s-%s, %d countries)"
                    % (model, y, worst_pair[0], worst_pair[1], worst))

    # Report: population in millions, v4 climate compensation data
    # (SSP3/IIASA) vs the new scenarios (IIASA files; population is
    # model-independent).
    print("\nPopulation, millions (IIASA files)")
    hdr = ["iso", "year", "v4"] + ["new " + s for s in SCENARIOS]
    print(("%-8s%-6s" + "%11s" * (len(SCENARIOS) + 1)) % tuple(hdr))
    v4nat = results["SSP3_IIASA"]["nat"]
    for iso in FOCUS + ("GLOBAL",):
        for y in ("2050", "2100"):
            o = v4nat.get((iso, y), (0.0, 0.0))[0]
            vals = [results[s + "_IIASA"]["nat"].get((iso, y),
                                                     (0.0, 0.0))[1]
                    for s in SCENARIOS]
            print(("%-8s%-6s" + "%11.1f" * (len(SCENARIOS) + 1))
                  % tuple([iso, y, o / 1e6] + [v / 1e6 for v in vals]))

    print("\n%d failure(s)" % len(failures) if failures else "\nAll passed")
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()
