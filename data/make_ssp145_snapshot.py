#!/usr/bin/env python3
"""Build the SSP1/SSP4/SSP5 projection snapshot from the release 3.1 workbook.

Source: 1721734326790-ssp_basic_drivers_release_3.1_full.xlsx from IIASA's
ssp2024_amended repository (commit 325b83c), cloned under
../source_data/ssp2024_amended/. The script verifies the workbook's sha256,
then gates on the existing snapshot: every SSP2/SSP3 value of the pipeline's
models and variables must be matched by the workbook exactly. Only then does
it write ssp_snapshot_ssp145.csv with SSP1, SSP4 and SSP5 in the same wide
format, variables, years and per-model region sets as the existing snapshot.

Two known representation artifacts are handled explicitly: the 2024 snapshot
export replaced accented characters in three region names with literal "?"
(C?te d'Ivoire, Cura?ao, R?union), so region names are matched after mapping
non-ASCII characters to "?", while the output keeps the workbook's proper
spellings (the reader's region matching accepts both); and the workbook
serializes floats with fewer digits than the CSV export, so values agree to
~1e-12 rather than bit-exactly.

Standard library only. Exits nonzero (writing nothing) on any mismatch.
"""

import csv
import hashlib
import re
import sys
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT.parent / "source_data"
XLSX = (SRC / "ssp2024_amended" / "data"
        / "1721734326790-ssp_basic_drivers_release_3.1_full.xlsx")
XLSX_SHA256 = ("5feb3b0aead3d0e7dbf80def75b89cc0e138e4dc"
               "13f4517e776b903cea258546")
SNAP = SRC / "ssp_book_snapshots" / "ssp_snapshot_1773244388.csv"
OUT = SRC / "ssp_book_snapshots" / "ssp_snapshot_ssp145.csv"
NS = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
ID_COLS = ["Model", "Scenario", "Region", "Variable", "Unit"]
MODELS = ("OECD ENV-Growth 2023", "IIASA GDP 2023", "IIASA-WiC POP 2023")
GATE_SSPS = ("SSP2", "SSP3")
NEW_SSPS = ("SSP1", "SSP4", "SSP5")
MATCH_TOL = 1e-12


def ascii_q(s):
    """Region name as the 2024 snapshot export spelled it: every non-ASCII
    character became a literal question mark."""
    return "".join(ch if ord(ch) < 128 else "?" for ch in s)


def read_snapshot():
    """Snapshot cells, year columns, and per-model variable/region sets."""
    cells, vars_, regions = {}, {}, {}
    with open(SNAP, encoding="utf-8-sig") as fh:
        r = csv.reader(fh)
        hdr = next(r)
        years = [c for c in hdr if c.isdigit()]
        yix = [(hdr.index(y), y) for y in years]
        for row in r:
            if len(row) < 5 or row[0].startswith("©"):
                continue
            vars_.setdefault(row[0], set()).add(row[3])
            regions.setdefault(row[0], set()).add(row[2])
            for i, y in yix:
                if row[i]:
                    cells[(row[0], row[1], row[2], row[3], y)] = float(row[i])
    return cells, years, vars_, regions


def scan_workbook(vars_, regions, years):
    """One pass over the workbook's data sheet.

    Returns the SSP2/SSP3 cells for the gate and the SSP1/4/5 rows for the
    output, both restricted to the snapshot's models, variables and
    per-model regions.
    """
    z = zipfile.ZipFile(XLSX)
    strings = []
    for ev, el in ET.iterparse(z.open("xl/sharedStrings.xml")):
        if el.tag == NS + "si":
            strings.append("".join(t.text or "" for t in el.iter(NS + "t")))
            el.clear()

    gate, rows, header = {}, [], {}
    for ev, el in ET.iterparse(z.open("xl/worksheets/sheet2.xml")):
        if el.tag != NS + "row":
            continue
        cells = {}
        for c in el.iter(NS + "c"):
            v = c.find(NS + "v")
            if v is None:
                continue
            val = strings[int(v.text)] if c.get("t") == "s" else v.text
            cells[re.match(r"[A-Z]+", c.get("r", "")).group()] = val
        el.clear()
        if not header:
            header = {col: str(val) for col, val in cells.items()}
            continue
        model, scen = cells.get("A"), cells.get("B")
        region, var = cells.get("C"), cells.get("D")
        if (model not in MODELS or var not in vars_.get(model, ())
                or region is None
                or ascii_q(region) not in regions.get(model, ())):
            continue
        by_year = {header.get(col, ""): val for col, val in cells.items()}
        if scen in GATE_SSPS:
            for y in years:
                if by_year.get(y) is not None:
                    gate[(model, scen, ascii_q(region), var, y)] = \
                        float(by_year[y])
        elif scen in NEW_SSPS:
            rows.append([model, scen, region, var, cells.get("E", "")]
                        + [by_year.get(y, "") or "" for y in years])
    return gate, rows


def main():
    sha = hashlib.sha256(XLSX.read_bytes()).hexdigest()
    if sha != XLSX_SHA256:
        sys.exit("ERROR: workbook sha256 %s does not match the pinned %s"
                 % (sha, XLSX_SHA256))
    print("workbook sha256 verified")

    snap, years, vars_, regions = read_snapshot()
    print("snapshot: %d cells, %d year columns" % (len(snap), len(years)))
    gate, rows = scan_workbook(vars_, regions, years)

    missing, worst = 0, 0.0
    for key, val in snap.items():
        w = gate.get(key)
        if w is None:
            missing += 1
            continue
        m = max(abs(val), abs(w))
        worst = max(worst, abs(val - w) / m if m else 0.0)
    print("gate: %d snapshot cells, %d missing in workbook, max rel diff "
          "%.3e" % (len(snap), missing, worst))
    if missing > 0 or worst > MATCH_TOL:
        sys.exit("ERROR: workbook does not reproduce the SSP2/SSP3 snapshot; "
                 "nothing written")

    rows.sort(key=lambda r: r[:4])
    with open(OUT, "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(ID_COLS + years)
        w.writerows(rows)

    counts = {}
    for r in rows:
        counts[(r[0], r[1])] = counts.get((r[0], r[1]), 0) + 1
    print("rows per model x scenario:")
    for (m, s), n in sorted(counts.items()):
        print("  %-24s %-5s %d" % (m, s, n))
    md5 = hashlib.md5(OUT.read_bytes()).hexdigest()
    print("wrote %s (%d rows, md5 %s)" % (OUT, len(rows), md5))


if __name__ == "__main__":
    main()
