#!/usr/bin/env python3
"""Compare the Python port's new-socioeconomics panels against the R ones.

Reads the R panels from R_OUTPUT (the published folder) and the Python
panels from PY_OUTPUT (the validation folder), column by column per
scenario x model combination, split three ways by the known
degenerate-geometry set (docs/residual_irs.csv):

  Tier A  regions outside the set, in countries without any set member:
          hard gate at the established validation tolerance
          (max |%diff| < 1e-2 %), and NA patterns must agree exactly.
  Tier B  regions outside the set but in a country that contains one: the
          geometry residual spills country-wide through the WPP rescale
          shares and the force_gdp_sum weighted mean, so report-only.
  Tier C  the set itself: report-only.

Also reports national population and GDP sums at sample years (they should
agree even in residual countries, since both sides scale to the same
controls). Standard library only. Exits nonzero on Tier A violations.
"""

import csv
import os
import sys
from multiprocessing import Pool
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
R_DIR = Path(os.environ.get(
    "R_OUTPUT", "/project/cil/gcp/outputs_newsocioeconomics/socioeconomics/"
                "1.0.0"))
PY_DIR = Path(os.environ.get(
    "PY_OUTPUT", "/project/cil/gcp/outputs_newsocioeconomics/socioeconomics/"
                 "validation/python/1.0.0"))
RESIDUAL = REPO / "docs" / "residual_irs.csv"
SCENARIOS = ("SSP1", "SSP2", "SSP3", "SSP4", "SSP5")
COMBOS = [(s, m) for s in SCENARIOS for m in ("IIASA", "OECD")]
VALUE_COLS = ["gdppc", "gdppc_raw", "gdppc_raw0", "gdp", "pop", "area_km2",
              "pop_density", "pop_wtd_density", "pop0to4", "pop5to64",
              "pop65plus"]
NAT_YEARS = ("2023", "2050", "2100")
TOL_PCT = 1e-2
TIERS = "ABC"


def residual_sets():
    with open(RESIDUAL) as fh:
        hierids = {row["hierid"] for row in csv.DictReader(fh)}
    return hierids, {h[:3] for h in hierids}


def pct(a, b):
    if a == b:
        return 0.0
    if b == 0.0:
        return float("inf")
    return abs(a - b) / abs(b) * 100.0


def compare(combo):
    scen, model = combo
    name = "ir_combined_%s_%s.csv" % (scen, model)
    res_ids, res_isos = residual_sets()
    s = {"combo": "%s_%s" % (scen, model), "rows": 0, "align_errors": 0,
         "rows_by_tier": dict.fromkeys(TIERS, 0),
         "max_pct": {t: dict.fromkeys(VALUE_COLS, 0.0) for t in TIERS},
         "a_viol": dict.fromkeys(VALUE_COLS, 0),
         "na_mismatch": dict.fromkeys(TIERS, 0),
         "isos_b": set(), "nat": {}}
    with open(R_DIR / name) as fr, open(PY_DIR / name) as fp:
        rr, rp = csv.reader(fr), csv.reader(fp)
        hr, hp = next(rr), next(rp)
        if hr != hp:
            s["align_errors"] += 1
            return s
        ix = {c: hr.index(c) for c in hr}
        iy, iiso = ix["year"], ix["iso3"]
        ipop, igdp = ix["pop"], ix["gdp"]
        val_ix = [(c, ix[c]) for c in VALUE_COLS]
        for r, p in zip(rr, rp):
            s["rows"] += 1
            if r[0] != p[0] or r[iy] != p[iy]:
                s["align_errors"] += 1
                if s["align_errors"] > 5:
                    return s
                continue
            hierid, iso = r[0], r[iiso]
            tier = ("C" if hierid in res_ids
                    else "B" if iso in res_isos else "A")
            s["rows_by_tier"][tier] += 1
            if tier == "B":
                s["isos_b"].add(iso)
            if r[iy] in NAT_YEARS:
                key = (iso, r[iy])
                rp_, pp_ = float(r[ipop]), float(p[ipop])
                rg, pg = float(r[igdp]), float(p[igdp])
                acc = s["nat"].setdefault(key, [0.0] * 4)
                acc[0] += rp_
                acc[1] += pp_
                acc[2] += rg
                acc[3] += pg
            for col, i in val_ix:
                a, b = p[i], r[i]
                if (a == "") != (b == ""):
                    s["na_mismatch"][tier] += 1
                    if tier == "A":
                        s["a_viol"][col] += 1
                    continue
                if a == "":
                    continue
                d = pct(float(a), float(b))
                if d > s["max_pct"][tier][col]:
                    s["max_pct"][tier][col] = d
                if tier == "A" and d > TOL_PCT:
                    s["a_viol"][col] += 1
    return s


def main():
    failures = []

    def verdict(ok, text):
        print("%s: %s" % ("PASS" if ok else "FAIL", text))
        if not ok:
            failures.append(text)

    res_ids, res_isos = residual_sets()
    with Pool(min(4, os.cpu_count() or 1)) as pool:
        results = pool.map(compare, COMBOS)

    first = results[0]
    print("Tier composition: %d degenerate regions in %d countries; "
          "per combination: A=%s B=%s C=%s rows"
          % (len(res_ids), len(res_isos),
             format(first["rows_by_tier"]["A"], ","),
             format(first["rows_by_tier"]["B"], ","),
             format(first["rows_by_tier"]["C"], ",")))
    print("Tier B (report-only) covers %d countries: %s\n"
          % (len(first["isos_b"]),
             " ".join(sorted(first["isos_b"]))))

    nat_worst = 0.0
    for s in sorted(results, key=lambda s: s["combo"]):
        tag = s["combo"]
        verdict(s["align_errors"] == 0 and s["rows"] > 0,
                "%s rows aligned (%s)" % (tag, format(s["rows"], ",")))
        worst_a = max(s["max_pct"]["A"].items(), key=lambda kv: kv[1])
        n_viol = sum(s["a_viol"].values())
        verdict(n_viol == 0 and s["na_mismatch"]["A"] == 0,
                "%s tier A within %.0e%% (worst %s %.2e%%, %d violations, "
                "%d NA mismatches)" % (tag, TOL_PCT, worst_a[0], worst_a[1],
                                       n_viol, s["na_mismatch"]["A"]))
        for t in "BC":
            worst = max(s["max_pct"][t].items(), key=lambda kv: kv[1])
            print("  %s tier %s report-only: worst %s %.3g%%, "
                  "%d NA mismatches"
                  % (tag, t, worst[0], worst[1], s["na_mismatch"][t]))
        for (iso, y), (rp_, pp_, rg, pg) in s["nat"].items():
            nat_worst = max(nat_worst, pct(pp_, rp_), pct(pg, rg))
    verdict(nat_worst <= TOL_PCT,
            "national pop and GDP sums agree at %s (max %.2e%%, "
            "all countries)" % ("/".join(NAT_YEARS), nat_worst))

    print("\n%d failure(s)" % len(failures) if failures else "\nAll passed")
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()
