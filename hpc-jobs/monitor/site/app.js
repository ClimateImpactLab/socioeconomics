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
const PART_COLORS = { cil: "#2d9e8f", amd: "#7c5cbf", caslake: "#4a8bc2", "amd-hm": "#e8913a" };
const PERSON_COLORS = ["#378ADD", "#7F77DD", "#D85A30", "#1D9E75", "#C74D8F", "#8A9E1D", "#DD9F37", "#5A7FD8"];

const params = new URLSearchParams(location.search);
const BASE = params.get("source") === "mock" ? "mock/" : "data/";

let DATA = null;
const view = { sector: null, runType: null, model: null, ssp: null, selected: null };
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

function sectorRunning(sec) {
  return Object.values(sec.run_types).some((rt) =>
    rt.units.some((u) => u.stages.generate && u.stages.generate.state === "running"));
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

function defaultRunType(sec) {
  const rts = Object.keys(sec.run_types);
  if (rts.includes("montecarlo")) return "montecarlo";
  if (rts.includes("median")) return "median";
  return rts[0];
}

function sspsOf(rt) {
  return [...new Set(rt.dims.cells.map((c) => c.ssp))];
}

function defaultSsp(rt) {
  const ssps = sspsOf(rt);
  return ssps.includes("SSP3") ? "SSP3" : ssps[0];
}

/* ---------- render ---------- */

function renderAll() {
  renderTabs();
  renderCards();
  renderSspTabs();
  renderLegend();
  renderGrid();
}

function selector(el, items, active, onPick) {
  el.innerHTML = "";
  for (const it of items) {
    const b = document.createElement("button");
    b.className = "run-opt" + (it.key === active ? " active" : "");
    b.innerHTML = esc(it.label) + (it.count != null ? `<span class="opt-count">${esc(it.count)}</span>` : "");
    if (it.disabled) { b.disabled = true; b.title = it.title || ""; }
    else b.onclick = () => onPick(it.key);
    el.appendChild(b);
  }
}

function renderTabs() {
  selector($("sector-tabs"), Object.entries(DATA.sectors).map(([k, s]) => {
    const f = sectorFiles(s);
    return { key: k, label: s.label, count: fmtPctShort(pctOf(f.proj + f.agg, f.projExp + f.aggExp)) };
  }), view.sector, (k) => {
    view.sector = k;
    view.runType = defaultRunType(sector());
    view.model = null;
    view.ssp = defaultSsp(runType());
    closeDetail();
    renderAll();
  });

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
    view.ssp = defaultSsp(runType());
    closeDetail();
    renderAll();
  });

  const rt = runType();
  const showModels = gridKind(rt) === "gcms" && rt.dims.models.length > 1;
  $("model-sep").classList.toggle("hidden", !showModels);
  if (!showModels) { $("model-tabs").innerHTML = ""; view.model = null; return; }
  if (!view.model) view.model = rt.dims.models[0];
  selector($("model-tabs"), rt.dims.models.map((m) => ({ key: m, label: m })), view.model, (k) => {
    view.model = k;
    closeDetail();
    renderAll();
  });
}

function pctOf(a, b) { return b ? (100 * a) / b : 0; }

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
    card("Complete", `<span style="color:var(--green)">${fmtN(f.complete)}</span>`, "all files present") +
    card("Partial", `<span style="color:var(--amber)">${fmtN(f.partial)}</span>`, "some files present") +
    card("Not started", `<span style="color:var(--red)">${fmtN(total - f.started)}</span>`, "no files yet") +
    card("Projection", fmtPct2(pp), `${fmtN(f.proj)}/${fmtN(f.projExp)} files`, pbar(pp, "var(--base)")) +
    card("Aggregation", fmtPct2(ap), `${fmtN(f.agg)}/${fmtN(f.aggExp)} files`, pbar(ap, "var(--agg)")) +
    card("Writing", fmtN(rt.counts.running), rt.counts.failed ? `${fmtN(rt.counts.failed)} stopped` : "units being written") +
    card("ETA", fmtEta(rt.eta_hours), rt.eta_basis ? esc(rt.eta_basis) : (total && f.complete === total ? "All complete" : ""));
}

function renderSspTabs() {
  const rt = runType();
  const sec = sector();
  const items = sspsOf(rt).map((ssp) => {
    const cells = rt.dims.cells.filter((c) => c.ssp === ssp);
    const models = gridKind(rt) === "gcms" ? [view.model || rt.dims.models[0]] : rt.dims.models;
    let exp = 0;
    for (const c of cells) exp += rt.dims.gcms[c.rcp].length * (rt.dims.batches || 1) * models.length;
    const done = rt.units.filter((u) => u.ssp === ssp && models.includes(u.model)).filter((u) => {
      const c = unitCounts(u, specOf(sec, u.model));
      return c.proj >= c.projTotal && c.agg >= c.aggTotal;
    }).length;
    return { key: ssp, label: ssp, count: `(${fmtN(done)}/${fmtN(exp)})` };
  });
  if (!view.ssp || !sspsOf(rt).includes(view.ssp)) view.ssp = defaultSsp(rt);
  selector($("ssp-tabs"), items, view.ssp, (k) => { view.ssp = k; closeDetail(); renderSspTabs(); renderGrid(); });
}

function renderLegend() {
  const box = (st) => `<div class="leg-box" style="${st}"></div>`;
  $("legend").innerHTML =
    `<div class="leg-item"><div class="leg-sq" style="background:var(--base)"></div> Present</div>
     <div class="leg-item"><div class="leg-sq" style="background:var(--miss)"></div> Missing</div>
     <span class="leg-sep">|</span>
     <div class="leg-item" title="Some files present, not yet complete">${box("border:1.5px dashed var(--progress)")} In progress</div>
     <div class="leg-item" title="Files changed in the last 6 hours">${box("border:1.5px solid var(--writing);background:rgba(255,99,71,0.06);animation:pulse-writing 2.5s ease-in-out infinite")} Writing</div>
     <div class="leg-item" title="All projection files present, aggregation not started">${box("border:1.5px solid var(--complete)")} Projection complete</div>
     <div class="leg-item" title="Projection complete, aggregation started but not finished">${box("border:2px solid var(--failed);background:var(--failed-bg)")} Aggregation incomplete</div>
     <div class="leg-item" title="All projection and aggregation files present">${box("border:1.5px solid var(--done-bd)")} Aggregation complete</div>
     <span class="leg-sep">|</span>
     <span style="font-weight:500">Aggregation:</span>
     <span style="color:var(--agg-cost)">Costs</span>
     <span style="color:var(--agg-lvl)">Levels</span>
     <span style="color:var(--agg-agg)">Aggregated</span>`;
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
  const cells = rt.dims.cells.filter((c) => c.ssp === view.ssp);
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
    const exp = rt.dims.gcms[c.rcp].length * batches.length * models.length;
    const done = rt.units.filter((u) => u.ssp === c.ssp && u.rcp === c.rcp && u.iam === c.iam && models.includes(u.model))
      .filter((u) => { const n = unitCounts(u, specOf(sec, u.model)); return n.proj >= n.projTotal && n.agg >= n.aggTotal; }).length;
    h1 += `<th colspan="${batches.length}" class="sc-hdr sc-hdr-${c.rcp}">${c.rcp}-${c.iam} <span class="sc-count">${done}/${exp}</span></th>`;
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

  let su;
  if (a.allocation_status === "ok") {
    const pct = a.allocation_su ? (100 * a.used_su) / a.allocation_su : null;
    su = resRow(a.name, pct, `${fmtN(a.used_su)}/${fmtN(a.allocation_su)}`,
      `Used ${fmtN(a.used_su)} SU of ${fmtN(a.allocation_su)} (${fmtN(a.balance_su)} SU remaining)`);
  } else if (a.allocation_status === "none") {
    su = `<div class="res-row"><span class="res-label">${esc(a.name)}</span><span class="res-note">No allocation yet</span></div>`;
  } else {
    su = `<div class="res-row"><span class="res-label">${esc(a.name)}</span><span class="res-note muted">Balance not read in this scan</span></div>`;
  }

  $("resources-content").innerHTML =
    `<div class="res-sec"><div class="res-title">Storage</div>${storage}</div>` +
    `<div class="res-sec"><div class="res-title">Service units</div>${su}</div>` +
    `<div class="res-foot">${new Date(DATA.generated_at).toLocaleString()}</div>`;
}

/* ---------- SLURM jobs ---------- */

function partPill(name, n) {
  const c = PART_COLORS[name] || "var(--tx3)";
  return `<span class="part-pill"><span class="part-dot" style="background:${c}"></span>${esc(name)}${n != null ? ": " + n : ""}</span>`;
}

function stateCounts(running, queued) {
  const p = [];
  if (running) p.push(`<span class="state-run">${fmtN(running)} running</span>`);
  if (queued) p.push(`<span class="state-pend">${fmtN(queued)} pending</span>`);
  return p.join(", ") || `<span class="lbl">none</span>`;
}

function renderJobs() {
  const groups = DATA.people.map((p) => ({ name: p.name, jobs: p.active_jobs, su: p.su_used, linked: p.linked }));
  const o = DATA.other_users || {};
  groups.push({ name: o.users ? `Other users (${o.users})` : "Other users", jobs: o.active_jobs, su: o.su_used, linked: true, other: true });

  const known = DATA.people.some((p) => p.active_jobs != null);
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

  const active = groups.filter((g) => g.jobs && g.jobs.length);
  if (active.length) {
    html += `<div class="jobs-line"><span class="lbl">People</span> ` + active.map((g) => {
      const r = g.jobs.reduce((n, j) => n + j.tasks.running, 0), q = g.jobs.reduce((n, j) => n + j.tasks.queued, 0);
      return `<b>${esc(g.name)}</b>: ${stateCounts(r, q)}`;
    }).join(" | ") + `</div>`;
  }

  // One bar splitting core hours by person.
  const a = DATA.account;
  const withSu = groups.filter((g) => g.su != null && g.su > 0);
  const totalSu = withSu.reduce((n, g) => n + g.su, 0);
  if (withSu.length) {
    html += `<div class="treemap-wrap"><div class="treemap-label">Core hours on the ${esc(a.su_partition)} partition since
      ${esc(fmtDate(a.su_since))}: <b>${fmtN(totalSu)} h</b> total</div><div class="treemap">` +
      withSu.map((g, i) => {
        const c = g.other ? "#99998f" : PERSON_COLORS[i % PERSON_COLORS.length];
        const p = Math.max((100 * g.su) / totalSu, 1);
        return `<div class="treemap-cell" style="flex-basis:${p.toFixed(1)}%;background:${c}22;color:${c}"
          title="${esc(g.name)}: ${fmtN(g.su)} h">${esc(g.name)}<span>${fmtN(g.su)} h</span></div>`;
      }).join("") + `</div></div>`;
  } else if (groups.some((g) => g.su != null)) {
    html += `<div class="jobs-line"><span class="lbl">No core hours on the ${esc(a.su_partition)} partition since ${esc(fmtDate(a.su_since))}</span></div>`;
  }

  // Groups by job name, with one row per person.
  const byName = {};
  for (const j of jobs) (byName[j.job_name] = byName[j.job_name] || []).push(j);
  const names = Object.keys(byName).sort();
  if (!names.length) {
    html += `<div class="jobs-empty">No jobs on the ${esc(a.name)} account right now</div>`;
  }
  for (const name of names) {
    const js = byName[name];
    const r = js.reduce((n, j) => n + j.tasks.running, 0), q = js.reduce((n, j) => n + j.tasks.queued, 0);
    const gp = {};
    for (const j of js) for (const p of j.partition.split(",")) gp[p] = (gp[p] || 0) + 1;
    html += `<div class="grp"><div class="grp-header"><div><b>${esc(name)}</b>
      <span class="grp-counts">${stateCounts(r, q)}</span>
      <span class="grp-parts">${Object.keys(gp).sort().map((p) => `<span style="color:${PART_COLORS[p] || "var(--tx3)"}">${esc(p)}: ${gp[p]}</span>`).join(" | ")}</span></div>
      <span class="grp-arrow">&gt;</span></div><div class="grp-body"><table class="jobs-table">
      <tr><th>Person</th><th>Partition</th><th>State</th><th class="r">Running</th><th class="r">Pending</th><th class="r">Done</th><th class="r">Elapsed</th></tr>` +
      js.map((j) => `<tr><td>${esc(j.person)}</td><td>${j.partition.split(",").map((p) => partPill(p)).join("")}</td>
        <td class="${j.state === "RUNNING" ? "state-run" : "state-pend"}">${j.state === "RUNNING" ? "Running" : "Pending"}</td>
        <td class="r">${fmtN(j.tasks.running)}</td><td class="r">${fmtN(j.tasks.queued)}</td><td class="r">${fmtN(j.tasks.done)}</td>
        <td class="r">${j.state === "RUNNING" ? fmtMin(j.elapsed_min) : ""}</td></tr>`).join("") +
      `</table></div></div>`;
  }
  const unlinked = groups.filter((g) => !g.linked).map((g) => g.name);
  if (unlinked.length) html += `<div class="jobs-line" style="margin-top:6px"><span class="lbl">No cluster user set: ${unlinked.map(esc).join(", ")}</span></div>`;
  $("jobs-content").innerHTML = html;
}

/* ---------- camel ---------- */

// Two-humped camel, facing left, in a 175 by 160 box.
const CAMEL_PATH = "M 12 24 C 12 18 18 13 26 12 C 30 11 33 11 35 12 L 38 6 L 41 13 " +
  "C 46 20 50 38 54 54 C 56 59 59 62 62 62 C 66 44 74 32 82 32 C 90 32 95 44 99 52 " +
  "C 104 42 112 33 120 33 C 130 33 138 46 144 58 C 150 62 154 68 154 76 L 160 86 L 162 100 " +
  "L 158 100 L 154 88 C 153 90 152 92 151 94 L 153 152 L 147 152 L 144 104 L 141 104 " +
  "L 141 152 L 135 152 L 134 96 C 118 99 96 99 78 96 L 78 152 L 72 152 L 70 104 L 67 104 " +
  "L 64 152 L 58 152 L 57 92 C 54 86 52 80 50 74 C 46 60 40 42 34 32 C 30 30 24 30 18 30 " +
  "C 14 30 12 28 12 24 Z";

// One body part per sector, as in the original design.
const CAMEL_SECTIONS = [
  { key: "mortality", label: "Mortality", part: "front legs", poly: "62,64 84,64 84,160 0,160 0,94 56,94" },
  { key: "coastal", label: "Coastal", part: "humps", poly: "62,0 200,0 200,64 62,64" },
  { key: "agriculture", label: "Agriculture", part: "back legs", poly: "130,64 200,64 200,160 130,160" },
  { key: "energy", label: "Energy", part: "neck and head", poly: "0,0 62,0 62,64 56,94 0,94" },
  { key: "labor", label: "Labor", part: "body", poly: "84,64 130,64 130,160 84,160" },
];
const CAMEL_VIEW = "8 2 158 154";

// Area below each height per region, so p percent fills p percent of the area.
let camelAreas = null;
function regionAreas() {
  if (camelAreas) return camelAreas;
  const ctx = document.createElement("canvas").getContext("2d");
  const sil = new Path2D(CAMEL_PATH);
  camelAreas = {};
  for (const sec of CAMEL_SECTIONS) {
    const poly = new Path2D();
    sec.poly.split(" ").map((p) => p.split(",").map(Number))
      .forEach(([x, y], i) => (i ? poly.lineTo(x, y) : poly.moveTo(x, y)));
    poly.closePath();
    const rows = [];
    for (let y = 0; y < 160; y++) {
      let n = 0;
      for (let x = 0; x < 200; x++) {
        if (ctx.isPointInPath(sil, x + 0.5, y + 0.5) && ctx.isPointInPath(poly, x + 0.5, y + 0.5)) n++;
      }
      rows.push(n);
    }
    camelAreas[sec.key] = rows;
  }
  return camelAreas;
}

function fillLine(key, frac) {
  const rows = regionAreas()[key];
  const total = rows.reduce((a, b) => a + b, 0);
  let acc = 0;
  for (let y = rows.length - 1; y >= 0; y--) {
    acc += rows[y];
    if (acc >= frac * total) return y;
  }
  return 0;
}

function camelDefs(prefix) {
  return `<clipPath id="${prefix}-sil"><path d="${CAMEL_PATH}"/></clipPath>` +
    CAMEL_SECTIONS.map((s) => `<clipPath id="${prefix}-${s.key}"><polygon points="${s.poly}"/></clipPath>`).join("") +
    `<pattern id="${prefix}-tex" width="4" height="4" patternUnits="userSpaceOnUse" patternTransform="rotate(45)">` +
    `<line x1="0" y1="0" x2="0" y2="4" stroke="#ffffff" stroke-opacity="0.45" stroke-width="1.3"/></pattern>`;
}

function renderCamel() {
  const prog = CAMEL_SECTIONS.map((s) => {
    const sec = DATA.sectors[s.key];
    if (!sec) return { ...s, tracked: false };
    const f = sectorFiles(sec);
    const proj = pctOf(f.proj, f.projExp), agg = pctOf(f.agg, f.aggExp);
    return { ...s, tracked: true, proj, agg, projDone: proj >= 100, allDone: proj >= 100 && agg >= 100,
      running: sectorRunning(sec) };
  });
  let body = "";
  for (const s of prog) {
    let fill = "", tip;
    if (!s.tracked) {
      tip = `${s.label} (${s.part}): not tracked yet`;
    } else {
      const frac = Math.min(s.proj, 100) / 100;
      const y = frac > 0 ? fillLine(s.key, frac) : 160;
      fill = s.projDone ? `<rect class="fill" x="0" y="0" width="200" height="160"/>` :
        (frac > 0 ? `<rect class="fill" x="0" y="${y}" width="200" height="${160 - y}"/>` : "");
      if (s.allDone) fill += `<rect x="0" y="0" width="200" height="160" fill="url(#cm-tex)"/>`;
      tip = `${s.label} (${s.part}): projection files ${fmtPctShort(s.proj)}, aggregation files ${fmtPctShort(s.agg)}` +
        (s.running ? ", projections running" : "");
    }
    const st = !s.tracked ? "" : s.allDone ? "all-done" : s.projDone ? "proj-done" : s.running ? "pulse" : "";
    body += `<g clip-path="url(#cm-${s.key})" class="sec sec-${s.key} ${st}"><title>${esc(tip)}</title>` +
      `<rect class="base" x="0" y="0" width="200" height="160"/>${fill}</g>`;
  }
  const dividers = CAMEL_SECTIONS.map((s) => `<polygon class="divider" points="${s.poly}"/>`).join("");
  $("camel").innerHTML = `<svg viewBox="${CAMEL_VIEW}" xmlns="http://www.w3.org/2000/svg"><defs>${camelDefs("cm")}</defs>` +
    `<g clip-path="url(#cm-sil)">${body}${dividers}</g></svg>`;

  $("camel-key").innerHTML = prog.map((s) => {
    const note = !s.tracked ? "not tracked" : s.allDone ? "all done" : s.projDone ? "projections done" :
      `${fmtPctShort(s.proj)} projection`;
    return `<span class="ckey" title="${esc(s.part)}"><span class="cdot sec-${s.key}"></span>${esc(s.label)} <span class="muted">${note}</span></span>`;
  }).join("");

  const css = getComputedStyle(document.documentElement);
  const parts = CAMEL_SECTIONS.map((s) => `<g clip-path="url(#fi-${s.key})"><rect width="200" height="160" ` +
    `fill="${css.getPropertyValue(`--sec-${s.key}`).trim()}"/></g>`).join("");
  const icon = `<svg xmlns="http://www.w3.org/2000/svg" viewBox="${CAMEL_VIEW}"><defs>${camelDefs("fi")}</defs>` +
    `<g clip-path="url(#fi-sil)">${parts}<g fill="none" stroke="#ffffff" stroke-width="2.5">` +
    CAMEL_SECTIONS.map((s) => `<polygon points="${s.poly}"/>`).join("") + `</g></g></svg>`;
  $("favicon").setAttribute("href", "data:image/svg+xml," + encodeURIComponent(icon));
}

/* ---------- interactions and boot ---------- */

function setup() {
  document.querySelectorAll(".panel-header").forEach((h) => {
    h.onclick = () => $(h.dataset.panel).classList.toggle("open");
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

  try {
    const r = await fetch(`${BASE}status.json`, { cache: "no-store" });
    if (!r.ok) throw new Error(`HTTP ${r.status}`);
    DATA = await r.json();
  } catch (err) {
    document.body.insertAdjacentHTML("afterbegin",
      `<div class="error">Could not load ${esc(BASE)}status.json (${esc(err.message)}).</div>`);
    return;
  }

  const ageH = (Date.now() - new Date(DATA.generated_at).getTime()) / 3.6e6;
  $("subtitle").textContent = `Last scan: ${new Date(DATA.generated_at).toLocaleString()}, every ${DATA.scan_interval_hours} h`;
  if (DATA.source === "mock") $("mock-badge").classList.remove("hidden");
  if (ageH > 2 * DATA.scan_interval_hours) {
    $("stale-banner").textContent = `The last scan is ${ageH.toFixed(1)} hours old. The scheduled job may have stopped.`;
    $("stale-banner").classList.remove("hidden");
  }

  view.sector = Object.keys(DATA.sectors)[0];
  view.runType = defaultRunType(sector());
  view.ssp = defaultSsp(runType());
  setup();
  renderCamel();
  renderResources();
  renderJobs();
  renderAll();
}

boot();
