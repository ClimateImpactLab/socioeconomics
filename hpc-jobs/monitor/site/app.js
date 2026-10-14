/* AMEL run-status dashboard, following the old mortality monitor.

   Reads data/status.json (written by collect_status.py), or mock/status.json
   with ?source=mock. File sizes and dates for the detail panel come from
   the details/ folder next to it and are loaded when a cell is clicked.
   The grid comes from the output folders only; Resources and SLURM jobs
   come from Slurm and rcchelp. */

"use strict";

const GROUPS = ["projection", "costs", "levels", "aggregated"];
const AGG_GROUPS = ["costs", "levels", "aggregated"];
const SQ_CLASS = { projection: "base", costs: "cost", levels: "lvl", aggregated: "agr" };
const DOT_CLASS = { projection: "proj", costs: "cost", levels: "lvl", aggregated: "agr" };
// Partitions are told apart by texture and users by color, so a segment of
// the SU bar shows both who and where. The textures live in the stylesheet
// (.ptex-*) and are the same in badges, bars and keys.
const KNOWN_PARTITIONS = ["cil", "amd", "caslake", "amd-hm", "bigmem", "gpu"];
function partTexture(p) {
  return `ptex-${KNOWN_PARTITIONS.includes(p) ? p : "other"}`;
}
function partSwatch(p) {
  return `<span class="pswatch ${partTexture(p)}" title="${esc(p)}"></span>`;
}
// One color per cluster user, by name order, so a user keeps it everywhere.
// These avoid the partition hues (purple, blue, mauve) and the state hues
// (running, pending, done) so a user never looks like a partition or a state.
const USER_COLORS = ["#4f9da6", "#9c6b3f", "#d17a9a", "#7d9a5e", "#c2a878", "#5c6b73", "#a05a7a", "#8fb3c9", "#b5885a", "#3f6e5b"];
function userColor(user) {
  if (user && user === DATA.account.highlight_user) return "var(--hl-user)";
  const names = (DATA.users || []).map((u) => u.user).filter((u) => u !== DATA.account.highlight_user).sort();
  const i = names.indexOf(user);
  return i < 0 ? "var(--tx3)" : USER_COLORS[i % USER_COLORS.length];
}

function userName(user) {
  return esc(user);
}
// Partition looks inside the core-hour bars, in order of total use.
const SU_STYLES = 5;

const params = new URLSearchParams(location.search);
// The collector pushes its data to the monitor-data branch every 4 hours, so
// the page reads it from there; the copy deployed with the site is the fallback.
const REMOTE_BASE = "https://raw.githubusercontent.com/ClimateImpactLab/socioeconomics/monitor-data/data/";
let BASE = params.get("source") === "mock" ? "mock/" : REMOTE_BASE;

let DATA = null;
const view = { sector: null, runType: null, model: null, modelOff: false, ssps: [], selected: null };
const detailCache = new Map();
let cellIndex = new Map();

const $ = (id) => document.getElementById(id);

/* ---------- formatting ---------- */

function esc(s) {
  return String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
}
function fmtN(n) { return n == null ? "n/a" : Math.round(n).toLocaleString("en-US"); }
function fmtPct2(p) {
  if (p == null || isNaN(p)) return "n/a";
  if (p < 100 && p >= 99.995) return "99.99%";
  return `${p.toFixed(2)}%`;
}
function fmtPctShort(p) {
  if (p > 0 && p < 0.1) return "<0.1%";
  return p < 10 ? `${p.toFixed(1)}%` : `${Math.round(p)}%`;
}
function fmtMin(min) {
  if (min == null) return "";
  if (min < 60) return `${Math.round(min)}m`;
  return `${Math.floor(min / 60)}h ${String(Math.round(min % 60)).padStart(2, "0")}m`;
}
function fmtEta(hours) {
  if (hours == null) return "n/a";
  if (hours < 48) return `~${Math.round(hours)} h`;
  if (hours > 24 * 365) return "over a year";
  return `~${Math.round(hours / 24)} d`;
}
function fmtSize(bytes) {
  if (!bytes) return "";
  if (bytes >= 1048576) return `${(bytes / 1048576).toFixed(1)} MB`;
  if (bytes >= 1024) return `${Math.round(bytes / 1024)} KB`;
  return `${bytes} B`;
}
function fmtStamp(sec) {
  const d = new Date(sec * 1000);
  const p = (n) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}`;
}
function fmtDate(iso) {
  return new Date(iso + "T00:00:00").toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" });
}

/* ---------- data helpers ---------- */

const sector = () => DATA.sectors[view.sector];
const runType = () => sector().run_types[view.runType];

function specOf(sec, model) { return sec.files_spec[model]; }
function flatNames(spec) { return GROUPS.flatMap((g) => spec[g]); }
function groupTotal(spec, groups) { return groups.reduce((n, g) => n + spec[g].length, 0); }

// Presence per group for a unit (or all missing when the unit is not listed).
function unitGroups(unit, spec) {
  const bits = unit ? unit.bits : "";
  const out = {};
  let i = 0;
  for (const g of GROUPS) {
    out[g] = spec[g].map(() => bits[i++] === "1");
  }
  return out;
}

function unitCounts(unit, spec) {
  const pres = unitGroups(unit, spec);
  const c = (gs) => gs.reduce((n, g) => n + pres[g].filter(Boolean).length, 0);
  return {
    proj: c(["projection"]), projTotal: spec.projection.length,
    agg: c(AGG_GROUPS), aggTotal: groupTotal(spec, AGG_GROUPS), pres,
  };
}

// The old monitor's cell states.
function cellState(unit, cnt) {
  if (unit && unit.state === "running") return "bst-progress bst-active";
  const projDone = cnt.proj >= cnt.projTotal;
  const aggDone = cnt.aggTotal > 0 && cnt.agg >= cnt.aggTotal;
  if (projDone && aggDone) return "bst-done";
  if (projDone && cnt.agg > 0) return "bst-aggpart";
  if (projDone) return "bst-complete";
  if (cnt.proj > 0 || cnt.agg > 0) return "bst-progress";
  return "bst-empty";
}
const STATE_NAMES = {
  "bst-progress bst-active": "writing", "bst-done": "aggregation complete",
  "bst-aggpart": "aggregation incomplete", "bst-complete": "projection complete",
  "bst-progress": "in progress", "bst-empty": "not started",
};

// Files present and expected for a run type, from its units.
function filesOf(sec, rt) {
  const out = { proj: 0, projExp: 0, agg: 0, aggExp: 0, complete: 0, partial: 0, started: 0 };
  const perModel = rt.counts.total / rt.dims.models.length;
  for (const m of rt.dims.models) {
    const s = specOf(sec, m);
    out.projExp += perModel * s.projection.length;
    out.aggExp += perModel * groupTotal(s, AGG_GROUPS);
  }
  for (const u of rt.units) {
    const c = unitCounts(u, specOf(sec, u.model));
    out.proj += c.proj;
    out.agg += c.agg;
    if (c.proj + c.agg === 0) continue;
    out.started += 1;
    if (c.proj >= c.projTotal && c.agg >= c.aggTotal) out.complete += 1;
    else out.partial += 1;
  }
  return out;
}

function sectorFiles(sec) {
  const t = { proj: 0, projExp: 0, agg: 0, aggExp: 0 };
  for (const rt of Object.values(sec.run_types)) {
    const f = filesOf(sec, rt);
    for (const k of Object.keys(t)) t[k] += f[k];
  }
  return t;
}

// A sector is active when projection files were written in its folders in
// the last 24 hours before the scan, or a unit is being written right now.
function sectorActive(sec) {
  const scan = new Date(DATA.generated_at).getTime();
  return sectorRunning(sec) || Object.values(sec.run_types).some((rt) =>
    rt.last_projection_write && scan - new Date(rt.last_projection_write).getTime() < 24 * 3.6e6);
}

function activeMark(key) {
  return `<span class="sec-spin" style="color:var(--sec-${key})" title="Projection files written in the last 24 hours">` +
    `<i></i><i></i><i></i><i></i></span>`;
}

function sectorRunning(sec) {
  return Object.values(sec.run_types).some((rt) =>
    rt.units.some((u) => u.stages.generate && u.stages.generate.state === "running"));
}

// Units with all projection files, and with all aggregation files.
// Projection (P) and aggregation (A) files present out of expected, for a
// set of units; expUnits is the number of expected units per sub-model.
function paFiles(sec, units, expUnits, models) {
  const out = { p: 0, pExp: 0, a: 0, aExp: 0 };
  for (const m of models) {
    const spec = specOf(sec, m);
    out.pExp += expUnits * spec.projection.length;
    out.aExp += expUnits * groupTotal(spec, AGG_GROUPS);
  }
  for (const u of units) {
    const c = unitCounts(u, specOf(sec, u.model));
    out.p += c.proj;
    out.a += c.agg;
  }
  return out;
}

function paText(n) {
  return `P ${fmtN(n.p)}/${fmtN(n.pExp)}, A ${fmtN(n.a)}/${fmtN(n.aExp)}`;
}

function gridKind(rt) {
  const anyRcp = Object.keys(rt.dims.gcms)[0];
  return rt.dims.gcms[anyRcp].length > 1 ? "gcms" : "models";
}

function gcmUnion(gcms) {
  const lists = Object.values(gcms).sort((a, b) => b.length - a.length);
  const out = [...lists[0]];
  for (const l of lists.slice(1)) for (const g of l) if (!out.includes(g)) out.push(g);
  return out;
}

// Sector tabs follow the AMEL order.
const SECTOR_ORDER = ["agriculture", "mortality", "energy", "labor"];
function sectorOrder() {
  const keys = Object.keys(DATA.sectors);
  return [...SECTOR_ORDER.filter((k) => keys.includes(k)), ...keys.filter((k) => !SECTOR_ORDER.includes(k))];
}

function defaultRunType(sec) {
  const rts = Object.keys(sec.run_types);
  if (rts.includes("montecarlo")) return "montecarlo";
  if (rts.includes("median")) return "median";
  return rts[0];
}

function sspsOf(rt) {
  return [...new Set(rt.dims.cells.map((c) => c.ssp))];
}

function defaultSsps(rt) {
  const ssps = sspsOf(rt);
  if (view.sector === "energy") return ssps;
  return [ssps.includes("SSP3") ? "SSP3" : ssps[0]];
}

/* ---------- render ---------- */

function renderAll() {
  // Nothing below the sector tabs shows until a sector is picked, and the
  // grid waits for a sub-model when the sector has several (crops, fuels).
  document.body.classList.toggle("no-sector", !view.sector);
  renderTabs();
  const needModel = !!view.sector && gridKind(runType()) === "gcms" && runType().dims.models.length > 1 && !view.model;
  document.body.classList.toggle("no-model", needModel);
  $("pick-note").textContent = !view.sector ? "Pick a sector to see its grid." : "Pick a sub-model to see its grid.";
  if (!view.sector) return;
  renderCards();
  if (needModel) return;
  renderSspTabs();
  renderLegend();
  renderGrid();
}

function selector(el, items, active, onPick) {
  el.innerHTML = "";
  for (const it of items) {
    const b = document.createElement("button");
    const on = it.active != null ? it.active : it.key === active;
    b.className = "run-opt" + (on ? " active" : "") + (it.cls ? " " + it.cls : "");
    b.innerHTML = esc(it.label) + (it.extra || "") + (it.count != null ? `<span class="opt-count">${esc(it.count)}</span>` : "");
    if (it.disabled) { b.disabled = true; b.title = it.title || ""; }
    else b.onclick = () => onPick(it.key);
    el.appendChild(b);
  }
}

function renderTabs() {
  selector($("sector-tabs"), sectorOrder().map((k) => [k, DATA.sectors[k]]).map(([k, s]) => {
    const f = sectorFiles(s);
    const est = sectorSuEstimate(s);
    return { key: k, label: s.label, cls: `sec-tab sec-${k}`, extra: sectorActive(s) ? activeMark(k) : "",
      count: fmtPctShort(pctOf(f.proj + f.agg, f.projExp + f.aggExp)) +
        (est ? `, ${suRange(est.low, est.high)} to finish` : ", SUs not known yet") };
  }), view.sector, (k) => {
    closeDetail();
    view.modelOff = false;
    if (k === view.sector) {
      // Clicking the selected sector again clears it.
      view.sector = null;
      view.runType = null;
      view.model = null;
      view.ssps = [];
      renderAll();
      return;
    }
    view.sector = k;
    view.runType = defaultRunType(sector());
    view.model = null;
    view.ssps = defaultSsps(runType());
    closeDetail();
    renderAll();
  });
  if (!view.sector) return;

  const sec = sector();
  const items = Object.entries(sec.run_types).map(([k, rt]) => {
    const f = filesOf(sec, rt);
    return { key: k, label: k, count: fmtPctShort(pctOf(f.proj + f.agg, f.projExp + f.aggExp)) };
  });
  for (const k of sec.disabled_run_types || []) {
    items.push({ key: k, label: k, disabled: true, title: "Not part of this sector" });
  }
  selector($("runtype-tabs"), items, view.runType, (k) => {
    view.runType = k;
    view.model = null;
    view.modelOff = false;
    view.ssps = defaultSsps(runType());
    closeDetail();
    renderAll();
  });

  const rt = runType();
  const showModels = gridKind(rt) === "gcms" && rt.dims.models.length > 1;
  $("model-sep").classList.toggle("hidden", !showModels);
  if (!showModels) { $("model-tabs").innerHTML = ""; view.model = null; return; }
  if (!view.model && !view.modelOff) view.model = rt.dims.models[0];
  const perModel = rt.counts.total / rt.dims.models.length;
  selector($("model-tabs"), rt.dims.models.map((m) => ({ key: m, label: m,
    count: paText(paFiles(sec, rt.units.filter((u) => u.model === m), perModel, [m])) })), view.model, (k) => {
    // Clicking the selected sub-model again clears it and hides its grid.
    view.modelOff = k === view.model;
    view.model = view.modelOff ? null : k;
    closeDetail();
    renderAll();
  });
}

function pctOf(a, b) { return b ? (100 * a) / b : 0; }

function fmtSU(n) {
  if (n == null) return "n/a";
  if (n >= 1e6) return `${(n / 1e6).toFixed(1)}M`;
  if (n >= 1e4) return `${Math.round(n / 1e3)}k`;
  if (n >= 1e3) return `${(n / 1e3).toFixed(1)}k`;
  return fmtN(n);
}

function suRange(low, high) {
  if (low == null) return "n/a";
  if (!high) return "0 SU";
  return low === high ? `${fmtSU(low)} SU` : `${fmtSU(low)} to ${fmtSU(high)} SU`;
}

// Lower and upper SUs to finish a sector, summed over its run types.
function sectorSuEstimate(sec) {
  let low = 0, high = 0;
  for (const rt of Object.values(sec.run_types)) {
    const e = rt.su_estimate;
    if (!e) continue;
    if (e.su_low == null) return null;
    low += e.su_low;
    high += e.su_high;
  }
  return { low, high };
}

function card(label, val, sub, bar) {
  return `<div class="card"><div class="card-label">${label}</div><div class="card-val">${val}</div>` +
    (bar || "") + (sub ? `<div class="card-sub">${sub}</div>` : "") + `</div>`;
}
function pbar(pct, color) {
  return `<div class="pbar"><div class="pbar-fill" style="width:${Math.min(pct, 100).toFixed(2)}%;background:${color}"></div></div>`;
}

function renderCards() {
  const sec = sector(), rt = runType();
  const f = filesOf(sec, rt);
  const total = rt.counts.total;
  const pp = pctOf(f.proj, f.projExp), ap = pctOf(f.agg, f.aggExp);
  $("cards").innerHTML =
    card("Expected", fmtN(total), "units of work") +
    card("Complete", `<span style="color:var(--st-done)">${fmtN(f.complete)}</span>`, "all files present") +
    card("Partial", `<span style="color:var(--progress)">${fmtN(f.partial)}</span>`, "some files present") +
    card("Not started", `<span style="color:var(--st-none)">${fmtN(total - f.started)}</span>`, "no files yet") +
    card("Projection", fmtPct2(pp), `${fmtN(f.proj)}/${fmtN(f.projExp)} files`, pbar(pp, "var(--base)")) +
    card("Aggregation", fmtPct2(ap), `${fmtN(f.agg)}/${fmtN(f.aggExp)} files`, pbar(ap, "var(--agg)")) +
    card("Writing", `<span style="color:var(--st-run)">${fmtN(rt.counts.running)}</span>`, rt.counts.failed ? `${fmtN(rt.counts.failed)} stopped` : "units being written") +
    card("ETA", fmtEta(rt.eta_hours), rt.eta_basis ? esc(rt.eta_basis) : (total && f.complete === total ? "All complete" : "")) +
    suCard(rt.su_estimate);
}

function suCard(e) {
  if (!e) return card("SUs to finish", "n/a", "");
  const sub = e.basis ? `<span title="${esc(e.basis)}">${esc(e.basis)}</span>` : "";
  return card("SUs to finish", e.su_low == null ? "not known yet" : suRange(e.su_low, e.su_high), sub);
}

function renderSspTabs() {
  const rt = runType();
  const sec = sector();
  const models = gridKind(rt) === "gcms" ? [view.model || rt.dims.models[0]] : rt.dims.models;
  const all = sspsOf(rt);
  view.ssps = view.ssps.filter((x) => all.includes(x));
  if (!view.ssps.length) view.ssps = defaultSsps(rt);
  const multi = view.sector === "energy";
  const items = all.map((ssp) => {
    let exp = 0;
    for (const c of rt.dims.cells.filter((c) => c.ssp === ssp)) {
      exp += rt.dims.gcms[c.rcp].length * (rt.dims.batches || 1);
    }
    const n = paFiles(sec, rt.units.filter((u) => u.ssp === ssp && models.includes(u.model)), exp, models);
    return { key: ssp, label: ssp, active: view.ssps.includes(ssp), count: paText(n) };
  });
  selector($("ssp-tabs"), items, null, (k) => {
    if (multi) {
      const on = view.ssps.includes(k);
      if (on && view.ssps.length > 1) view.ssps = view.ssps.filter((x) => x !== k);
      else if (!on) view.ssps = all.filter((x) => x === k || view.ssps.includes(x));
    } else {
      view.ssps = [k];
    }
    closeDetail();
    renderSspTabs();
    renderGrid();
  });
}

// Aggregation types a sector actually has, in a fixed order.
const AGG_STYLE = { costs: { v: "cost", label: "Costs" }, levels: { v: "lvl", label: "Levels" },
  aggregated: { v: "agg", label: "Aggregated" } };
function aggTypes(sec) {
  return AGG_GROUPS.filter((g) => Object.values(sec.files_spec).some((spec) => spec[g].length));
}

function renderLegend() {
  const box = (st) => `<div class="leg-box" style="${st}"></div>`;
  $("legend").innerHTML =
    `<div class="leg-item"><div class="leg-sq" style="background:var(--base)"></div> Present</div>
     <div class="leg-item"><div class="leg-sq" style="background:var(--miss)"></div> Missing</div>
     <span class="leg-sep">|</span>
     <div class="leg-item" title="Some files present, not yet complete">${box("border:1.5px dashed var(--progress)")} In progress</div>
     <div class="leg-item" title="Files changed in the last 6 hours">${box("border:1.5px solid var(--st-run);background:var(--st-run-bg);animation:pulse-writing 2.5s ease-in-out infinite")} Writing</div>
     <div class="leg-item" title="All projection files present, aggregation not started">${box("border:1.5px solid var(--complete)")} Projection complete</div>
     <div class="leg-item" title="Projection complete, aggregation started but not finished">${box("border:2px solid var(--failed);background:var(--failed-bg)")} Aggregation incomplete</div>
     <div class="leg-item" title="All projection and aggregation files present">${box("border:1.5px solid color-mix(in srgb, var(--st-done) 55%, transparent)")} Aggregation complete</div>
     <span class="leg-sep">|</span>
     <span style="font-weight:500">Aggregation:</span>
     ${aggTypes(sector()).map((g) => `<span style="color:var(--agg-${AGG_STYLE[g].v})">${AGG_STYLE[g].label}</span>`).join(" ")}`;
}

function squares(pres, groups) {
  let html = "";
  for (const g of groups) {
    for (const on of pres[g]) html += `<div class="fsq${on ? " " + SQ_CLASS[g] : ""}"></div>`;
  }
  return html;
}

function cellHtml(key, unit, spec) {
  const cnt = unitCounts(unit, spec);
  const cls = cellState(unit, cnt);
  let html = `<div class="batch ${cls}" data-key="${esc(key)}">`;
  html += `<div class="batch-row"><div class="sq-grid">${squares(cnt.pres, ["projection"])}</div>` +
    (cnt.proj ? `<span class="row-count proj">${cnt.proj}/${cnt.projTotal}</span>` : "") + `</div>`;
  if (cnt.aggTotal) {
    html += `<div class="batch-sep"></div><div class="batch-row"><div class="sq-grid">${squares(cnt.pres, AGG_GROUPS)}</div>` +
      (cnt.agg ? `<span class="row-count agg">${cnt.agg}/${cnt.aggTotal}</span>` : "") + `</div>`;
  }
  return html + `</div>`;
}

function renderGrid() {
  const sec = sector(), rt = runType();
  const kind = gridKind(rt);
  const batches = rt.dims.batches ? [...Array(rt.dims.batches).keys()] : [null];
  const cells = rt.dims.cells.filter((c) => view.ssps.includes(c.ssp));
  const showSsp = view.ssps.length > 1;
  const byKey = new Map(rt.units.map((u) => [[u.model, u.ssp, u.rcp, u.iam, u.gcm, u.batch ?? ""].join("|"), u]));
  cellIndex = new Map();

  const rows = kind === "gcms" ? gcmUnion(rt.dims.gcms) : rt.dims.models;
  const fixedModel = kind === "gcms" ? (view.model || rt.dims.models[0]) : null;
  const edge = (rcp, i, n) => {
    const t = rcp === "rcp45" ? "45" : "85";
    return (i === 0 ? ` edge-l${t}` : "") + (i === n - 1 ? ` edge-r${t}` : "");
  };

  let h1 = `<thead><tr><th class="model-th">${kind === "gcms" ? "Climate model" : "Sub-model"}</th>`;
  let h2 = `<tr><th class="model-th sub">${batches[0] != null ? "batch" : ""}</th>`;
  cells.forEach((c, i) => {
    if (i) { h1 += `<th class="sep-col"></th>`; h2 += `<th class="sep-col"></th>`; }
    const models = fixedModel ? [fixedModel] : rt.dims.models;
    const n = paFiles(sec, rt.units.filter((u) => u.ssp === c.ssp && u.rcp === c.rcp && u.iam === c.iam && models.includes(u.model)),
      rt.dims.gcms[c.rcp].length * batches.length, models);
    h1 += `<th colspan="${batches.length}" class="sc-hdr sc-hdr-${c.rcp}">${showSsp ? c.ssp + " " : ""}${c.rcp}-${c.iam}<br><span class="sc-count">${paText(n)}</span></th>`;
    batches.forEach((b, bi) => {
      h2 += `<th class="sub${edge(c.rcp, bi, batches.length)}">${b != null ? "b" + b : (kind === "gcms" ? "" : rt.dims.gcms[c.rcp][0])}</th>`;
    });
  });
  h1 += `</tr>`; h2 += `</tr></thead>`;

  let body = "<tbody>";
  for (const row of rows) {
    const label = kind === "gcms" ? row.replace("surrogate_", "surr_") : row;
    body += `<tr><td class="model-cell" title="${esc(row)}">${esc(label)}</td>`;
    cells.forEach((c, i) => {
      if (i) body += `<td class="sep-col"></td>`;
      batches.forEach((b, bi) => {
        const model = fixedModel || row;
        const gcm = kind === "gcms" ? row : rt.dims.gcms[c.rcp][0];
        const cls = `sc-cell${edge(c.rcp, bi, batches.length)}`;
        if (!rt.dims.gcms[c.rcp].includes(gcm)) { body += `<td class="${cls}"></td>`; return; }
        const key = [model, c.ssp, c.rcp, c.iam, gcm, b ?? ""].join("|");
        const unit = byKey.get(key) || null;
        cellIndex.set(key, { unit, model, ssp: c.ssp, rcp: c.rcp, iam: c.iam, gcm, batch: b });
        body += `<td class="${cls}">${cellHtml(key, unit, specOf(sec, model))}</td>`;
      });
    });
    body += `</tr>`;
  }
  $("grid").innerHTML = h1 + h2 + body + "</tbody>";
  if (view.selected) {
    const el = document.querySelector(`.batch[data-key="${CSS.escape(view.selected)}"]`);
    if (el) el.classList.add("selected");
  }
}

/* ---------- detail panel ---------- */

function cellPath(info) {
  const rt = runType();
  const parts = [rt.root];
  if (info.model !== "main") parts.push(info.model);
  if (rt.subdir) parts.push(rt.subdir);
  if (info.batch != null) parts.push(`batch${info.batch}`);
  parts.push(info.rcp, info.gcm, info.iam, info.ssp);
  return parts.join("/");
}

function cellTitle(info) {
  const bits = [];
  if (info.model !== "main") bits.push(info.model);
  bits.push(info.gcm);
  if (info.batch != null) bits.push(`batch${info.batch}`);
  bits.push(info.ssp, info.rcp, info.iam);
  return bits.join(" / ");
}

async function loadDetails(model, batch) {
  const path = `${BASE}details/${view.sector}/${view.runType}/${model}${batch != null ? "/batch" + batch : ""}.json`;
  if (detailCache.has(path)) return detailCache.get(path);
  let data = {};
  try {
    const r = await fetch(path, { cache: "no-store" });
    if (r.ok) data = await r.json();
  } catch (e) { /* no detail file means no files on disk yet */ }
  detailCache.set(path, data);
  return data;
}

function fileRow(group, name, rec) {
  const shown = name.replace("winsorized/", "winsorized / ");
  if (!rec) {
    return `<div class="fd-row miss"><span class="dot miss"></span><span class="fname">${esc(shown)}</span></div>`;
  }
  const cls = DOT_CLASS[group];
  return `<div class="fd-row ${cls}"><span class="dot ${cls}"></span><span class="fname">${esc(shown)}</span>` +
    `<span class="meta">${fmtSize(rec[0])}</span><span class="meta">${fmtStamp(rec[1])}</span></div>`;
}

function section(id, title, count, bodyHtml, open) {
  return `<div class="fd-sec" data-sec="${id}"><span class="arrow">${open ? "v" : "&gt;"}</span>` +
    `<span class="name">${title}</span><span class="cnt">${count}</span></div>` +
    `<div class="fd-body${open ? "" : " closed"}" id="${id}">${bodyHtml}</div>`;
}

async function showDetail(key) {
  const info = cellIndex.get(key);
  if (!info) return;
  view.selected = key;
  document.querySelectorAll(".batch.selected").forEach((e) => e.classList.remove("selected"));
  const el = document.querySelector(`.batch[data-key="${CSS.escape(key)}"]`);
  if (el) el.classList.add("selected");

  const sec = sector();
  const spec = specOf(sec, info.model);
  const cnt = unitCounts(info.unit, spec);
  const path = cellPath(info);
  $("info-bar").textContent = `${cellTitle(info)}  ${cnt.proj}/${cnt.projTotal} projection, ${cnt.agg}/${cnt.aggTotal} aggregation`;
  $("info-bar").title = path;

  const box = $("file-detail");
  box.className = "file-detail";
  box.innerHTML = `<div class="fd-note">Loading file sizes and dates</div>`;
  const details = cnt.proj + cnt.agg ? await loadDetails(info.model, info.batch) : {};
  if (view.selected !== key) return;
  const recs = details[[info.ssp, info.rcp, info.iam, info.gcm].join("|")] || [];
  let i = 0;
  const byGroup = {};
  for (const g of GROUPS) byGroup[g] = spec[g].map((n) => ({ name: n, rec: recs[i++] || null }));
  const rows = (g) => byGroup[g].map((f) => fileRow(g, f.name, f.rec)).join("");
  const found = (g) => byGroup[g].filter((f) => f.rec).length;

  const state = STATE_NAMES[cellState(info.unit, cnt)];
  const reason = info.unit && info.unit.fail_reason ? `, ${esc(info.unit.fail_reason)}` : "";
  let html = `<div class="fd-root">${esc(path)}</div>
    <div class="fd-head">${esc(cellTitle(info))}: ${cnt.proj}/${cnt.projTotal} projection
      | <span class="agg-count">${cnt.agg}/${cnt.aggTotal} aggregation</span>
      <span class="state">${esc(state)}${reason}</span>
      <button class="fd-close" id="fd-close">[close]</button></div>`;
  html += section("fd-proj", "Projections", `${found("projection")}/${spec.projection.length}`, rows("projection"), true);
  const aggParts = ["levels", "aggregated"].filter((g) => spec[g].length);
  if (aggParts.length) {
    const sub = aggParts.map((g) => `<div class="fd-sub" style="color:var(--agg-${g === "levels" ? "lvl" : "agg"})">` +
      `${g === "levels" ? "Levels" : "Aggregated"} (${found(g)}/${spec[g].length})</div>${rows(g)}`).join("");
    const n = aggParts.reduce((s, g) => s + found(g), 0), t = aggParts.reduce((s, g) => s + spec[g].length, 0);
    html += section("fd-agg", "Aggregation", `${n}/${t}`, sub, false);
  }
  if (spec.costs.length) {
    html += section("fd-costs", "Costs", `${found("costs")}/${spec.costs.length}`, rows("costs"), false);
  }
  box.innerHTML = html;
  $("fd-close").onclick = closeDetail;
}

function closeDetail() {
  view.selected = null;
  const box = $("file-detail");
  box.className = "";
  box.innerHTML = "";
  $("info-bar").textContent = "Click any cell to see its files";
  $("info-bar").title = "";
  document.querySelectorAll(".batch.selected").forEach((e) => e.classList.remove("selected"));
}

/* ---------- resources ---------- */

function barColor(pct) {
  if (pct == null) return "var(--bd2)";
  return pct >= 90 ? "var(--red)" : pct >= 70 ? "var(--amber)" : "var(--green)";
}

function resRow(label, pct, counts, tip) {
  const col = barColor(pct);
  const p = Math.min(pct == null ? 0 : pct, 100);
  return `<div class="res-row"${tip ? ` title="${esc(tip)}"` : ""}><span class="res-label">${esc(label)}</span>` +
    `<span class="res-bar"><span class="fill" style="width:${p.toFixed(1)}%;background:${col}"></span><span class="ticks"></span></span>` +
    `<span class="res-pct" style="color:${col}">${fmtPct2(pct)}</span><span class="res-counts">${esc(counts)}</span></div>`;
}

function renderResources() {
  const a = DATA.account;
  let storage;
  if (a.storage == null) storage = `<div class="res-note muted">Not read in this scan</div>`;
  else if (!a.storage.length) storage = `<div class="res-note muted">No group storage found</div>`;
  else storage = a.storage.map((s) => resRow(s.label, s.used_pct, `${s.used}/${s.quota}`,
    `Used ${s.used} of ${s.quota}`)).join("");

  $("resources-content").innerHTML =
    `<div class="res-sec"><div class="res-title">Storage</div>${storage}</div>` +
    `<div class="res-sec"><div class="res-title">Service units</div>${serviceUnitsHtml()}</div>` +
    `<div class="res-foot">${new Date(DATA.generated_at).toLocaleString()}</div>`;
}

// Official SUs come from RCC (rcchelp). The sacct figure is an estimate,
// shown apart: one bar for the account, one colored segment per user, and
// inside each user's segment one textured part per partition. Scarce
// partitions only (the group's own partition is left out).
function serviceUnitsHtml() {
  const a = DATA.account;
  const free = a.su_free_partitions || [];
  const since = esc(fmtDate(a.su_since));
  const users = (DATA.users || []).map((u) => {
    const su = u.su_used || 0;
    const core = Object.entries(u.core_hours_by_partition || {})
      .filter(([p]) => !free.includes(p)).reduce((n, [, v]) => n + v, 0);
    return { ...u, su, core };
  }).sort((x, y) => y.su - x.su || x.user.localeCompare(y.user));
  const total = users.reduce((n, u) => n + u.su, 0);

  // Official: RCC's own figure.
  let html;
  if (a.allocation_status === "ok") {
    const pct = a.allocation_su ? (100 * a.used_su) / a.allocation_su : null;
    html = resRow("Official (RCC)", pct, `${fmtN(a.used_su)}/${fmtN(a.allocation_su)}`,
      `Charged by RCC: ${fmtN(a.used_su)} SU of ${fmtN(a.allocation_su)} (${fmtN(a.balance_su)} SU remaining)`);
  } else {
    const note = a.allocation_status === "none" ? "no allocation yet, nothing charged" : "not read in this scan";
    html = `<div class="res-row"><span class="res-label">Official (RCC)</span>` +
      `<span class="res-bar placeholder"><span class="ticks"></span></span>` +
      `<span class="res-pct" style="color:var(--tx3)">0 SU</span><span class="res-counts">${esc(note)}</span></div>`;
  }

  if (!DATA.users) return html + `<div class="res-note muted" style="margin-top:6px">Estimate not read in this scan</div>`;

  // Estimate from sacct: users by color, partitions by texture.
  const parts = {};
  let bar = "";
  for (const u of users) {
    if (!u.su) continue;
    const segs = Object.entries(u.su_by_partition || {}).filter(([p, v]) => v > 0 && !free.includes(p))
      .sort((x, y) => y[1] - x[1]);
    for (const [p, v] of segs) {
      parts[p] = (parts[p] || 0) + v;
      bar += `<span class="seg ${partTexture(p)}" style="width:${((100 * v) / (total || 1)).toFixed(2)}%;background-color:${userColor(u.user)}"
        title="${esc(u.user)}, ${esc(p)}: ${fmtN(v)} SU"></span>`;
    }
  }
  html += `<div class="su-est"><div class="su-est-head">Estimated since ${since}
      <span class="est-tag">not charged by RCC yet</span> <b>${fmtN(total)} SU</b>
      <button class="info-btn" id="su-info-btn" aria-expanded="false" aria-controls="su-info" title="About these numbers">i</button></div>
    <div class="su-bar-all">${bar}</div>`;
  html += `<div class="ukey">` + users.map((u) =>
    `<span class="ukey-item"><span class="udot" style="background:${userColor(u.user)}"></span>${userName(u.user)}
      <span class="mono">${u.su ? `${fmtN(u.su)} SU, ${fmtN(u.core)} core h, ${((100 * u.su) / (total || 1)).toFixed(1)}%` : "no jobs yet"}</span></span>`).join("") + `</div>`;
  const order = Object.keys(parts).sort((x, y) => parts[y] - parts[x]);
  if (order.length) {
    html += `<div class="ukey pkey">` + order.map((p) =>
      `<span class="ukey-item">${partSwatch(p)}${esc(p)} <span class="mono">${fmtN(parts[p])} SU</span></span>`).join("") + `</div>`;
  }

  html += `</div>`;

  // Notes behind the "i" button.
  const notes = `<p>The cil account has no allocation yet for the October 2026 to 2027 cycle. This will be updated soon.</p>
    <p>For now, SUs are only an estimate, from jobs on partitions that are not charging SUs yet.</p>
    <p>SUs = elapsed hours &times; billing. To check a job:
    <code>sacct -X -j &lt;jobid&gt; -n -P -o JobID,ElapsedRaw,Partition,AllocTRES</code></p>`;
  html += `<div class="su-info hidden" id="su-info">${notes}</div>`;
  return html;
}

/* ---------- SLURM jobs ---------- */

function partPill(name, n) {
  return `<span class="part-pill">${partSwatch(name)}${esc(name)}${n != null ? ": " + n : ""}</span>`;
}

function stateCounts(running, queued) {
  const p = [];
  if (running) p.push(`<span class="state-run">${fmtN(running)} running</span>`);
  if (queued) p.push(`<span class="state-pend">${fmtN(queued)} pending</span>`);
  return p.join(", ") || `<span class="lbl">none</span>`;
}

function renderJobs() {
  const groups = (DATA.users || []).map((u) => ({ name: u.user, jobs: u.active_jobs }));
  const known = DATA.users != null && DATA.users.some((u) => u.active_jobs != null);
  const jobs = groups.flatMap((g) => (g.jobs || []).map((j) => ({ ...j, person: g.name })));
  const run = jobs.reduce((n, j) => n + j.tasks.running, 0);
  const pend = jobs.reduce((n, j) => n + j.tasks.queued, 0);
  $("badge-run").textContent = `${fmtN(run)} running`;
  $("badge-pend").textContent = `${fmtN(pend)} pending`;

  if (!known) {
    $("jobs-content").innerHTML = `<div class="jobs-empty">No Slurm data in this scan</div>`;
    return;
  }

  const parts = {};
  for (const j of jobs) for (const p of j.partition.split(",")) parts[p] = (parts[p] || 0) + 1;
  let html = `<div class="jobs-line">${fmtN(jobs.length)} ${jobs.length === 1 ? "job" : "jobs"}
    (${fmtN(run + pend)} tasks): ${stateCounts(run, pend)}
    ${Object.keys(parts).length ? `<span class="lbl" style="margin-left:10px">Partitions</span> ` +
      Object.keys(parts).sort().map((p) => partPill(p, parts[p])).join(" ") : ""}</div>`;

  const always = DATA.account.always_show_users || [];
  const shown = groups.filter((g) => (g.jobs && g.jobs.length) || always.includes(g.name) || g.name === DATA.account.highlight_user);
  if (shown.length) {
    html += `<div class="jobs-line"><span class="lbl">Users</span> ` + shown.map((g) => {
      const js = g.jobs || [];
      const r = js.reduce((n, j) => n + j.tasks.running, 0), q = js.reduce((n, j) => n + j.tasks.queued, 0);
      return `<span class="udot" style="background:${userColor(g.name)}"></span> <b>${userName(g.name)}</b>: ` +
        (js.length ? stateCounts(r, q) : `<span class="lbl">no jobs</span>`);
    }).join(" | ") + `</div>`;
  }

  const a = DATA.account;

  // Every running or queued job, one row per job or array.
  if (!jobs.length) {
    html += `<div class="jobs-empty">No jobs on the ${esc(a.name)} account right now</div>`;
  } else {
    const order = [...jobs].sort((x, y) => (x.state !== "RUNNING") - (y.state !== "RUNNING") || y.elapsed_min - x.elapsed_min);
    html += `<table class="jobs-table"><tr><th>Job ID</th><th>Name</th><th>User</th><th>Partition</th><th>State</th>
      <th class="r">Running</th><th class="r">Pending</th><th class="r">Done</th><th class="r">Elapsed</th></tr>` +
      order.map((j) => `<tr><td class="mono">${esc(j.job_id || "")}</td><td>${esc(j.job_name)}</td>
        <td><span class="ukey-item"><span class="udot" style="background:${userColor(j.person)}"></span>${userName(j.person)}</span></td>
        <td>${j.partition.split(",").map((p) => partPill(p)).join("")}</td>
        <td class="${j.state === "RUNNING" ? "state-run" : "state-pend"}">${j.state === "RUNNING" ? "Running" : "Pending"}</td>
        <td class="r">${fmtN(j.tasks.running)}</td><td class="r">${fmtN(j.tasks.queued)}</td><td class="r">${fmtN(j.tasks.done)}</td>
        <td class="r">${j.state === "RUNNING" ? fmtMin(j.elapsed_min) : ""}</td></tr>`).join("") + `</table>`;
  }
  $("jobs-content").innerHTML = html;
}

/* ---------- camel ---------- */

// The camel has 100 pieces per sector (camel/camel.svg), filled from the
// bottom up. A sector fills with its share of projection files, pulses
// while projections run, turns solid when they are all there, and gets a
// fine texture when aggregation is complete too.
const CAMEL_SECTIONS = [
  { key: "mortality", label: "Mortality", part: "shoulder and front legs" },
  { key: "coastal", label: "Coastal", part: "back and humps" },
  { key: "agriculture", label: "Agriculture", part: "hindquarters, back legs and tail" },
  { key: "energy", label: "Energy", part: "head and neck" },
  { key: "labor", label: "Labor", part: "belly" },
];
let camelSvg = null;
// The walking animation is paused for now; set to true to turn it back on.
const CAMEL_WALK = false;

async function loadCamel() {
  try {
    const r = await fetch("camel/camel.svg");
    if (!r.ok) return;
    const doc = new DOMParser().parseFromString(await r.text(), "image/svg+xml");
    const svg = doc.documentElement;
    if (svg.localName !== "svg" || doc.querySelector("parsererror")) return;
    camelSvg = document.importNode(svg, true);
    camelSvg.removeAttribute("width");
    camelSvg.removeAttribute("height");
    camelSvg.dataset.grid = "visible";
    // One texture per sector: the sector color with fine light stripes.
    const ns = "http://www.w3.org/2000/svg";
    const defs = document.createElementNS(ns, "defs");
    defs.innerHTML = CAMEL_SECTIONS.map((s) =>
      `<pattern id="camel-tex-${s.key}" width="7" height="7" patternUnits="userSpaceOnUse" patternTransform="rotate(45)">` +
      `<rect width="7" height="7" class="tex-bg tex-${s.key}"/><line x1="0" y1="0" x2="0" y2="7" class="tex-line"/></pattern>`).join("");
    camelSvg.insertBefore(defs, camelSvg.firstChild);
    $("camel").replaceChildren(camelSvg);
    renderCamel();
  } catch (e) { /* the page works without the camel */ }
}

function renderCamel() {
  const prog = CAMEL_SECTIONS.map((s) => {
    const sec = DATA.sectors[s.key];
    if (!sec) return { ...s, tracked: false, proj: 0, agg: 0 };
    const f = sectorFiles(sec);
    const proj = pctOf(f.proj, f.projExp), agg = pctOf(f.agg, f.aggExp);
    return { ...s, tracked: true, proj, agg, projDone: proj >= 100, allDone: proj >= 100 && agg >= 100,
      running: sectorRunning(sec) };
  });

  if (camelSvg) {
    for (const s of prog) {
      const n = !s.tracked ? 0 : s.projDone ? 100 : Math.max(s.proj > 0 ? 1 : 0, Math.min(99, Math.round(s.proj)));
      camelSvg.querySelectorAll(`.cell[data-sector="${s.key}"]`).forEach((c) => {
        c.dataset.filled = String(Number(c.dataset.index) <= n);
      });
      camelSvg.classList.toggle(`pulse-${s.key}`, s.tracked && s.running && !s.projDone);
      camelSvg.classList.toggle(`solid-${s.key}`, s.tracked && s.projDone);
      camelSvg.classList.toggle(`tex-${s.key}`, s.tracked && s.allDone);
    }
    // Walk only while projection files are being written (the grid's "writing" signal).
    camelSvg.dataset.motion = CAMEL_WALK && Object.values(DATA.sectors).some(sectorRunning) ? "walk" : "none";
    const desc = camelSvg.querySelector("desc");
    if (desc) desc.textContent = "Two-humped camel. " + prog.map((s) => s.tracked ?
      `${s.label}: ${fmtPctShort(s.proj)} of projection files` : `${s.label}: not tracked (yet)`).join("; ") + ".";
  }

  $("camel-key").innerHTML = prog.map((s) => {
    const note = !s.tracked ? "not tracked (yet)" : s.allDone ? "all done" : s.projDone ? "projections done" :
      `${fmtPctShort(s.proj)} projection`;
    return `<span class="ckey" title="${esc(s.part)}"><span class="cdot sec-${s.key}"></span>${esc(s.label)} <span class="muted">${note}</span></span>`;
  }).join("");
}

/* ---------- interactions and boot ---------- */

function setup() {
  document.querySelectorAll(".panel-header").forEach((h) => {
    h.onclick = () => $(h.dataset.panel).classList.toggle("open");
  });
  $("pa-info-btn").addEventListener("click", () => {
    const open = $("pa-info").classList.toggle("hidden") === false;
    $("pa-info-btn").setAttribute("aria-expanded", String(open));
    $("pa-info-btn").classList.toggle("on", open);
  });
  $("resources-content").addEventListener("click", (e) => {
    const b = e.target.closest("#su-info-btn");
    if (!b) return;
    const box = $("su-info");
    const open = box.classList.toggle("hidden") === false;
    b.setAttribute("aria-expanded", String(open));
    b.classList.toggle("on", open);
  });
  $("jobs-content").addEventListener("click", (e) => {
    const h = e.target.closest(".grp-header");
    if (h) h.parentElement.classList.toggle("open");
  });
  $("file-detail").addEventListener("click", (e) => {
    const s = e.target.closest(".fd-sec");
    if (!s) return;
    const body = $(s.dataset.sec);
    body.classList.toggle("closed");
    s.querySelector(".arrow").textContent = body.classList.contains("closed") ? ">" : "v";
  });
  const grid = $("grid"), tip = $("global-tip");
  grid.addEventListener("click", (e) => {
    const b = e.target.closest(".batch");
    if (b) showDetail(b.dataset.key);
  });
  grid.addEventListener("mousemove", (e) => {
    const b = e.target.closest(".batch");
    if (!b) { tip.style.display = "none"; return; }
    const info = cellIndex.get(b.dataset.key);
    const cnt = unitCounts(info.unit, specOf(sector(), info.model));
    tip.innerHTML = `${esc(cellTitle(info))}<br>${cnt.proj}/${cnt.projTotal} projection` +
      (cnt.aggTotal ? `<br>${cnt.agg}/${cnt.aggTotal} aggregation` : "") +
      `<br><span class="muted">${esc(STATE_NAMES[cellState(info.unit, cnt)])}</span>`;
    tip.style.display = "block";
    const r = tip.getBoundingClientRect();
    let x = e.clientX + 12, y = e.clientY + 12;
    if (x + r.width > innerWidth - 8) x = e.clientX - r.width - 12;
    if (y + r.height > innerHeight - 8) y = e.clientY - r.height - 12;
    tip.style.left = `${x}px`; tip.style.top = `${y}px`;
  });
  grid.addEventListener("mouseleave", () => { tip.style.display = "none"; });
  $("theme-toggle").onclick = () => {
    const root = document.documentElement;
    const next = getComputedStyle(root).colorScheme.includes("dark") ? "light" : "dark";
    root.dataset.theme = next;
    try { localStorage.setItem("amel-theme", next); } catch (e) { /* storage may be blocked */ }
  };
}

async function boot() {
  try {
    const saved = localStorage.getItem("amel-theme");
    if (saved) document.documentElement.dataset.theme = saved;
  } catch (e) { /* storage may be blocked */ }

  const load = async (base) => {
    const r = await fetch(`${base}status.json`, { cache: "no-store" });
    if (!r.ok) throw new Error(`HTTP ${r.status}`);
    return r.json();
  };
  let localCopy = false;
  try {
    DATA = await load(BASE);
  } catch (err) {
    if (BASE !== REMOTE_BASE) {
      document.body.insertAdjacentHTML("afterbegin",
        `<div class="error">Could not load ${esc(BASE)}status.json (${esc(err.message)}).</div>`);
      return;
    }
    try {
      BASE = "data/";
      DATA = await load(BASE);
      localCopy = true;
    } catch (err2) {
      document.body.insertAdjacentHTML("afterbegin",
        `<div class="error">Could not load the status data (${esc(err2.message)}).</div>`);
      return;
    }
  }

  const ageH = (Date.now() - new Date(DATA.generated_at).getTime()) / 3.6e6;
  $("subtitle").textContent = `Last scan: ${new Date(DATA.generated_at).toLocaleString()}, every ${DATA.scan_interval_hours} h` +
    (localCopy ? " (local copy)" : "");
  if (DATA.source === "mock") $("mock-badge").classList.remove("hidden");
  if (ageH > 2 * DATA.scan_interval_hours) {
    $("stale-banner").textContent = `The last scan is ${ageH.toFixed(1)} hours old. The scheduled job may have stopped.`;
    $("stale-banner").classList.remove("hidden");
  }

  view.sector = null;
  view.runType = null;
  view.ssps = [];
  setup();
  renderCamel();
  loadCamel();
  renderResources();
  renderJobs();
  renderAll();
}

boot();
