/* AMEL run-status dashboard. Reads status.json (written by the collector,
   or by make_mock_status.py for the mock).

   Navigation is a zoomable hierarchy. Every level fits the screen:
     all sectors > sector > run type > sub-model > scenario > GCM > batch
   Levels that do not apply (one sub-model, one GCM, no batches) are
   skipped. Each block aggregates the units below it; the deepest level is
   one unit and opens the detail panel. Two display modes share the
   hierarchy: files (expected output files present) and jobs (Slurm state). */

"use strict";

const STATES = ["done", "running", "queued", "failed", "partial", "not_started"];
const STATE_LABELS = {
  done: "Done",
  running: "Running",
  queued: "Queued",
  failed: "Failed",
  partial: "Partial",
  not_started: "Not started",
};
const STATE_COLORS = {
  done: "var(--st-done)",
  running: "var(--st-running)",
  queued: "var(--st-queued)",
  failed: "var(--st-failed)",
  partial: "var(--st-done)",
  not_started: "var(--st-none)",
};
const GROUPS = ["projection", "aggregation"];

let DATA = null;
let view = { mode: "files", failedOnly: false };
// The zoom position. Fields fill in as the user goes deeper.
let path = { sector: null, runType: null, model: null, cell: null, gcm: null, batch: null };
let currentChildren = [];

const $ = (id) => document.getElementById(id);

/* ---------- formatting ---------- */

function fmtMin(min) {
  if (min == null) return "";
  if (min < 60) return `${Math.round(min)}m`;
  return `${Math.floor(min / 60)}h ${String(Math.round(min % 60)).padStart(2, "0")}m`;
}

function fmtEta(hours) {
  if (hours == null) return "n/a";
  if (hours < 48) return `~${Math.round(hours)} h`;
  return `~${(hours / 24).toFixed(1)} d`;
}

function fmtAgo(iso) {
  const h = (Date.now() - new Date(iso).getTime()) / 3.6e6;
  if (h < 1) return `${Math.round(h * 60)} min ago`;
  if (h < 48) return `${h.toFixed(1)} h ago`;
  return `${(h / 24).toFixed(1)} days ago`;
}

function fmtN(n) {
  return n == null ? "n/a" : Math.round(n).toLocaleString("en-US");
}

function rcpShort(rcp) {
  return rcp.replace("rcp", "").replace("45", "4.5").replace("85", "8.5");
}

function cellLabel(cell) {
  return `${cell.ssp} ${rcpShort(cell.rcp)} ${cell.iam}`;
}

function esc(s) {
  return String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function resolveName(name, rcp) {
  return name.split("{rcp}").join(rcp);
}

/* ---------- hierarchy ---------- */

function rtOf(sectorName, runType) {
  return DATA.sectors[sectorName].run_types[runType];
}

function needModel(rt) { return rt.dims.models.length > 1; }
function needGcm(rt) {
  const anyRcp = Object.keys(rt.dims.gcms)[0];
  return rt.dims.gcms[anyRcp].length > 1;
}
function needBatch(rt) { return !!rt.dims.batches; }

// The dimension the children of this path spread over, or null at a unit.
function nextLevel(p) {
  if (!p.sector) return "sector";
  if (!p.runType) return "runType";
  const rt = rtOf(p.sector, p.runType);
  if (needModel(rt) && !p.model) return "model";
  if (!p.cell) return "cell";
  if (needGcm(rt) && !p.gcm) return "gcm";
  if (needBatch(rt) && p.batch == null) return "batch";
  return null;
}

function childrenOf(p) {
  const level = nextLevel(p);
  if (!level) return [];
  if (level === "sector") {
    return Object.entries(DATA.sectors).map(([name, s]) =>
      ({ label: s.label, path: { ...p, sector: name } }));
  }
  if (level === "runType") {
    return Object.keys(DATA.sectors[p.sector].run_types).map((rtName) =>
      ({ label: rtName, path: { ...p, runType: rtName } }));
  }
  const rt = rtOf(p.sector, p.runType);
  if (level === "model") {
    return rt.dims.models.map((m) => ({ label: m, path: { ...p, model: m } }));
  }
  if (level === "cell") {
    return rt.dims.cells.map((c) => ({ label: cellLabel(c), path: { ...p, cell: c } }));
  }
  if (level === "gcm") {
    return rt.dims.gcms[p.cell.rcp].map((g) => ({ label: g, path: { ...p, gcm: g } }));
  }
  return [...Array(rt.dims.batches).keys()].map((b) =>
    ({ label: `batch ${b}`, path: { ...p, batch: b } }));
}

// Model used when the sector has only one (so the level is skipped).
function effectiveModel(p, rt) {
  return p.model || rt.dims.models[0];
}

function unitMatches(u, p) {
  if (p.model && u.model !== p.model) return false;
  if (p.cell && (u.ssp !== p.cell.ssp || u.rcp !== p.cell.rcp || u.iam !== p.cell.iam)) return false;
  if (p.gcm && u.gcm !== p.gcm) return false;
  if (p.batch != null && u.batch !== p.batch) return false;
  return true;
}

// (sector, run type) pairs inside this path's scope.
function scopePairs(p) {
  const sectors = p.sector ? [p.sector] : Object.keys(DATA.sectors);
  const pairs = [];
  for (const s of sectors) {
    const rts = p.runType ? [p.runType] : Object.keys(DATA.sectors[s].run_types);
    for (const rtName of rts) pairs.push([s, rtName]);
  }
  return pairs;
}

/* ---------- aggregation ---------- */

function specTotals(sectorName, model) {
  const spec = DATA.sectors[sectorName].files_spec[model];
  return { projection: spec.projection.length, aggregation: spec.aggregation.length };
}

// Everything the summary cards and blocks need for one node.
function aggregate(p) {
  const agg = {
    unitsTotal: 0, completeUnits: 0,
    states: Object.fromEntries(STATES.map((s) => [s, 0])),
    files: { projection: { found: 0, expected: 0 }, aggregation: { found: 0, expected: 0 } },
    etaHours: null, etaFrom: null,
  };
  for (const [sectorName, rtName] of scopePairs(p)) {
    const rt = rtOf(sectorName, rtName);
    const models = p.model ? [p.model] : rt.dims.models;
    const cells = p.cell ? [p.cell] : rt.dims.cells;
    const batchN = needBatch(rt) ? (p.batch != null ? 1 : rt.dims.batches) : 1;

    let unitsPerModel = 0;
    for (const cell of cells) {
      const gcmN = p.gcm ? (rt.dims.gcms[cell.rcp].includes(p.gcm) ? 1 : 0)
        : rt.dims.gcms[cell.rcp].length;
      unitsPerModel += gcmN * batchN;
    }
    agg.unitsTotal += unitsPerModel * models.length;
    for (const m of models) {
      const t = specTotals(sectorName, m);
      agg.files.projection.expected += unitsPerModel * t.projection;
      agg.files.aggregation.expected += unitsPerModel * t.aggregation;
    }

    let listed = 0;
    for (const u of rt.units) {
      if (!unitMatches(u, p)) continue;
      listed += 1;
      agg.states[u.state] += 1;
      const t = specTotals(sectorName, u.model);
      let complete = true;
      for (const g of GROUPS) {
        const rec = u.files ? u.files[g] : null;
        const found = rec ? rec.found : 0;
        agg.files[g].found += found;
        if (found < t[g]) complete = false;
      }
      if (complete) agg.completeUnits += 1;
    }
    agg.states.not_started += unitsPerModel * models.length - listed;

    if (rt.eta_hours != null && (agg.etaHours == null || rt.eta_hours > agg.etaHours)) {
      agg.etaHours = rt.eta_hours;
      agg.etaFrom = `slowest: ${DATA.sectors[sectorName].label} ${rtName}`;
      agg.etaBasis = rt.eta_basis;
    }
    agg.pairs = (agg.pairs || 0) + 1;
  }
  if (agg.pairs === 1 && agg.etaBasis) agg.etaFrom = agg.etaBasis;
  return agg;
}

function leafUnit(p) {
  const rt = rtOf(p.sector, p.runType);
  for (const u of rt.units) if (unitMatches(u, p)) return u;
  return null;
}

function leafInfo(p) {
  const rt = rtOf(p.sector, p.runType);
  return {
    unit: leafUnit(p),
    model: effectiveModel(p, rt),
    ssp: p.cell.ssp, rcp: p.cell.rcp, iam: p.cell.iam,
    gcm: p.gcm || rt.dims.gcms[p.cell.rcp][0],
    batch: p.batch,
  };
}

function leafFiles(info, sectorName) {
  const totals = specTotals(sectorName, info.model);
  const out = {};
  for (const g of GROUPS) {
    const rec = info.unit && info.unit.files ? info.unit.files[g] : null;
    out[g] = { found: rec ? rec.found : 0, expected: rec ? rec.total : totals[g] };
  }
  return out;
}

/* ---------- navigation ---------- */

function pathToHash(p) {
  const parts = [];
  if (p.sector) parts.push(`s=${p.sector}`);
  if (p.runType) parts.push(`rt=${p.runType}`);
  if (p.model) parts.push(`m=${p.model}`);
  if (p.cell) parts.push(`c=${p.cell.ssp}.${p.cell.rcp}.${p.cell.iam}`);
  if (p.gcm) parts.push(`g=${p.gcm}`);
  if (p.batch != null) parts.push(`b=${p.batch}`);
  return parts.length ? "#" + parts.join("&") : "#";
}

function hashToPath(hash) {
  const p = { sector: null, runType: null, model: null, cell: null, gcm: null, batch: null };
  const kv = {};
  for (const part of hash.replace(/^#/, "").split("&")) {
    const [k, v] = part.split("=");
    if (k && v != null) kv[k] = decodeURIComponent(v);
  }
  if (!kv.s || !DATA.sectors[kv.s]) return p;
  p.sector = kv.s;
  if (!kv.rt || !DATA.sectors[p.sector].run_types[kv.rt]) return p;
  p.runType = kv.rt;
  const rt = rtOf(p.sector, p.runType);
  if (kv.m && rt.dims.models.includes(kv.m)) p.model = kv.m;
  if (kv.c) {
    const [ssp, rcp, iam] = kv.c.split(".");
    p.cell = rt.dims.cells.find((c) => c.ssp === ssp && c.rcp === rcp && c.iam === iam) || null;
  }
  if (p.cell && kv.g && rt.dims.gcms[p.cell.rcp].includes(kv.g)) p.gcm = kv.g;
  if (kv.b != null && needBatch(rt)) {
    const b = parseInt(kv.b, 10);
    if (b >= 0 && b < rt.dims.batches) p.batch = b;
  }
  return p;
}

function navigate(newPath, push) {
  path = newPath;
  if (push) history.pushState(null, "", pathToHash(path));
  renderAll();
}

/* ---------- rendering ---------- */

function renderAll() {
  renderBreadcrumb();
  renderSummary();
  renderLegend();
  renderBoard();
  renderSU();
}

function crumbSteps() {
  const steps = [{ label: "All sectors", path: { sector: null, runType: null, model: null, cell: null, gcm: null, batch: null } }];
  let p = steps[0].path;
  if (path.sector) {
    p = { ...p, sector: path.sector };
    steps.push({ label: DATA.sectors[path.sector].label, path: p });
  }
  if (path.runType) { p = { ...p, runType: path.runType }; steps.push({ label: path.runType, path: p }); }
  if (path.model) { p = { ...p, model: path.model }; steps.push({ label: path.model, path: p }); }
  if (path.cell) { p = { ...p, cell: path.cell }; steps.push({ label: cellLabel(path.cell), path: p }); }
  if (path.gcm) { p = { ...p, gcm: path.gcm }; steps.push({ label: path.gcm, path: p }); }
  if (path.batch != null) { p = { ...p, batch: path.batch }; steps.push({ label: `batch ${path.batch}`, path: p }); }
  return steps;
}

function renderBreadcrumb() {
  const el = $("breadcrumb");
  el.innerHTML = "";
  const steps = crumbSteps();
  steps.forEach((step, i) => {
    if (i) {
      const sep = document.createElement("span");
      sep.className = "crumb-sep";
      sep.textContent = "/";
      el.appendChild(sep);
    }
    const last = i === steps.length - 1;
    const b = document.createElement(last ? "span" : "button");
    b.className = last ? "crumb current" : "crumb";
    b.textContent = step.label;
    if (!last) b.onclick = () => navigate(step.path, true);
    el.appendChild(b);
  });
}

function renderSummary() {
  const agg = aggregate(path);
  const el = $("summary");
  let html = "";

  if (view.mode === "files") {
    const found = agg.files.projection.found + agg.files.aggregation.found;
    const expected = agg.files.projection.expected + agg.files.aggregation.expected;
    const pct = expected ? (100 * found) / expected : 0;
    html += `<div class="card"><div class="num">${fmtN(found)}</div>
      <div class="lbl">files present of ${fmtN(expected)}</div></div>`;
    html += `<div class="card"><div class="num">${fmtN(agg.completeUnits)}</div>
      <div class="lbl">units with all files, of ${fmtN(agg.unitsTotal)}</div></div>`;
    html += `<div class="card"><div class="num">${fmtN(agg.states.failed)}</div>
      <div class="lbl"><span class="dot" style="background:${STATE_COLORS.failed}"></span>failed units</div></div>`;
    html += `<div class="card progress-card">
      <div class="lbl">${pct.toFixed(1)}% of expected files</div>
      <div class="progress-bar"><span style="width:${pct}%;background:${STATE_COLORS.done}"></span></div></div>`;
  } else {
    for (const s of STATES) {
      html += `<div class="card"><div class="num">${fmtN(agg.states[s])}</div>
        <div class="lbl"><span class="dot" style="background:${STATE_COLORS[s]}"></span>${STATE_LABELS[s]}</div></div>`;
    }
    const pct = agg.unitsTotal ? (100 * agg.states.done) / agg.unitsTotal : 0;
    let bar = "";
    for (const s of STATES) {
      if (s === "not_started" || !agg.states[s]) continue;
      bar += `<span style="width:${(100 * agg.states[s]) / agg.unitsTotal}%;background:${STATE_COLORS[s]};${s === "partial" ? "opacity:.45;" : ""}"></span>`;
    }
    html += `<div class="card progress-card">
      <div class="lbl">${pct.toFixed(1)}% done of ${fmtN(agg.unitsTotal)} units</div>
      <div class="progress-bar">${bar}</div></div>`;
  }

  html += `<div class="card eta"><div class="num">${fmtEta(agg.etaHours)}</div>
    <div class="lbl">est. time to finish</div>
    ${agg.etaFrom && agg.etaHours != null ? `<div class="sub">${esc(agg.etaFrom)}</div>` : ""}</div>`;
  el.innerHTML = html;
}

function renderLegend() {
  let html;
  if (view.mode === "files") {
    html = `<span class="chip"><span class="sw" style="background:var(--st-none)"></span>no files yet</span>
      <span class="chip"><span class="sw half"></span>files appearing</span>
      <span class="chip"><span class="sw" style="background:${STATE_COLORS.done}"></span>all files present</span>
      <span class="chip"><span class="sw ring"></span>failures inside</span>
      <span class="note">Bars show projection and aggregation files. Click a block to zoom in.</span>`;
  } else {
    const chips = STATES.filter((s) => s !== "partial").map((s) =>
      `<span class="chip"><span class="sw ${s === "queued" ? "queued" : ""}"
        style="background:${STATE_COLORS[s]}"></span>${STATE_LABELS[s]}</span>`).join("");
    html = chips + `<span class="note">Bars show the share of units in each state. Click a block to zoom in.</span>`;
  }
  $("legend").innerHTML = html;
}

function filesBars(files, compact) {
  let html = "";
  for (const g of GROUPS) {
    const pct = files[g].expected ? (100 * files[g].found) / files[g].expected : 0;
    html += `<div class="nbar">`;
    if (!compact) html += `<span class="nlbl">${g === "projection" ? "proj" : "aggr"}</span>`;
    html += `<div class="ntrack"><span style="width:${pct.toFixed(2)}%"></span></div>`;
    if (!compact) html += `<span class="nval">${Math.round(pct)}%</span>`;
    html += `</div>`;
  }
  return html;
}

function stateBar(states, total) {
  let html = `<div class="dist">`;
  for (const s of STATES) {
    if (s === "not_started" || !states[s]) continue;
    html += `<span style="width:${(100 * states[s]) / total}%;background:${STATE_COLORS[s]};${s === "partial" ? "opacity:.45;" : ""}"></span>`;
  }
  return html + `</div>`;
}

function renderBoard() {
  const board = $("board");
  board.classList.toggle("failed-only", view.failedOnly);
  currentChildren = [];

  const children = childrenOf(path);
  if (!children.length) {
    // A fully resolved path is a single unit (deep link): show the parent
    // level with the unit's panel open.
    const info = leafInfo(path);
    const parent = crumbSteps().at(-2).path;
    path = parent;
    history.replaceState(null, "", pathToHash(path));
    renderAll();
    showDrawer(info);
    return;
  }

  // Lay the blocks out as a grid that fills the available space.
  const rect = board.getBoundingClientRect();
  const h = Math.max(320, window.innerHeight - rect.top - 120);
  board.style.height = `${h}px`;
  const n = children.length;
  let cols = Math.max(1, Math.round(Math.sqrt((n * rect.width) / h)));
  cols = Math.min(cols, n);
  const rows = Math.ceil(n / cols);
  cols = Math.ceil(n / rows);
  board.style.gridTemplateColumns = `repeat(${cols}, 1fr)`;
  board.style.gridTemplateRows = `repeat(${rows}, 1fr)`;
  const blockH = h / rows;
  const blockW = rect.width / cols;
  const compact = blockH < 84 || blockW < 130;
  board.classList.toggle("compact", compact);

  let html = "";
  children.forEach((child, i) => {
    const leaf = nextLevel(child.path) === null;
    let inner, failed, sub, allDone;
    if (leaf) {
      const info = leafInfo(child.path);
      const files = leafFiles(info, child.path.sector);
      const state = info.unit ? info.unit.state : "not_started";
      failed = state === "failed" ? 1 : 0;
      sub = STATE_LABELS[state];
      currentChildren.push({ child, leaf, info, files, state });
      inner = view.mode === "files" ? filesBars(files, compact) :
        stateBar({ [state]: 1 }, 1);
      allDone = view.mode === "files" ?
        GROUPS.every((g) => files[g].found >= files[g].expected) :
        state === "done";
    } else {
      const agg = aggregate(child.path);
      failed = agg.states.failed;
      sub = `${fmtN(agg.unitsTotal)} ${agg.unitsTotal === 1 ? "unit" : "units"}`;
      currentChildren.push({ child, leaf, agg });
      inner = view.mode === "files" ? filesBars(agg.files, compact) :
        stateBar(agg.states, agg.unitsTotal);
      if (view.mode === "files") {
        const found = agg.files.projection.found + agg.files.aggregation.found;
        const expected = agg.files.projection.expected + agg.files.aggregation.expected;
        allDone = expected > 0 && found >= expected;
      } else {
        allDone = agg.unitsTotal > 0 && agg.states.done === agg.unitsTotal;
      }
    }
    const doneCls = allDone ? " all-done" : "";
    html += `<div class="node${failed ? " has-failed" : ""}${doneCls}" data-i="${i}" role="button" tabindex="0">
      <div class="node-head"><span class="node-label" title="${esc(child.label)}">${esc(child.label)}</span>
      ${failed ? `<span class="fail-chip">${fmtN(failed)} failed</span>` : ""}</div>
      ${inner}
      <div class="node-sub">${esc(sub)}</div>
    </div>`;
  });
  board.innerHTML = html;
}

/* ---------- tooltip and drawer ---------- */

function unitTitle(info) {
  const bits = [];
  if (info.model !== "main") bits.push(info.model);
  bits.push(info.ssp, info.rcp, info.iam, info.gcm);
  if (info.batch != null && info.batch !== "") bits.push(`batch ${info.batch}`);
  return bits.join(" ");
}

function tooltipHtml(entry) {
  if (entry.leaf) {
    const info = entry.info;
    const state = entry.state;
    let html = `<div class="tt-title"><span class="tt-dot" style="background:${STATE_COLORS[state]}"></span>${esc(unitTitle(info))}</div>`;
    html += `<div class="tt-row">${STATE_LABELS[state]}${info.unit && info.unit.fail_reason ? ": " + esc(info.unit.fail_reason) : ""}</div>`;
    html += `<div class="tt-row">projection files ${entry.files.projection.found} of ${entry.files.projection.expected}, ` +
      `aggregation ${entry.files.aggregation.found} of ${entry.files.aggregation.expected}</div>`;
    if (info.unit) {
      for (const [name, rec] of Object.entries(info.unit.stages)) {
        if (rec.state === "not_started") continue;
        let line = `${name}: ${rec.state}`;
        if (rec.elapsed_min != null) line += `, ${fmtMin(rec.elapsed_min)}`;
        if (rec.max_rss_gb != null) line += `, ${rec.max_rss_gb} GB`;
        html += `<div class="tt-row">${esc(line)}</div>`;
      }
    }
    return html + `<div class="tt-row tt-hint">Click for the full file list</div>`;
  }
  const agg = entry.agg;
  let html = `<div class="tt-title">${esc(entry.child.label)}</div>`;
  html += `<div class="tt-row">${fmtN(agg.unitsTotal)} units</div>`;
  const f = agg.files;
  html += `<div class="tt-row">projection files ${fmtN(f.projection.found)} of ${fmtN(f.projection.expected)}</div>`;
  html += `<div class="tt-row">aggregation files ${fmtN(f.aggregation.found)} of ${fmtN(f.aggregation.expected)}</div>`;
  const parts = STATES.filter((s) => agg.states[s])
    .map((s) => `${STATE_LABELS[s].toLowerCase()} ${fmtN(agg.states[s])}`);
  if (parts.length) html += `<div class="tt-row">${esc(parts.join(", "))}</div>`;
  return html + `<div class="tt-row tt-hint">Click to zoom in</div>`;
}

function fileListHtml(info, sectorName) {
  const spec = DATA.sectors[sectorName].files_spec[info.model];
  const files = leafFiles(info, sectorName);
  let html = "";
  for (const g of GROUPS) {
    const names = spec[g].map((n) => resolveName(n, info.rcp));
    const rec = info.unit && info.unit.files ? info.unit.files[g] : null;
    let missing;
    if (!rec || rec.found === 0) missing = new Set(names);
    else if (rec.found >= rec.total) missing = new Set();
    else missing = new Set((rec.missing || []).map((n) => resolveName(n, info.rcp)));
    html += `<h3>${g} files (${files[g].found} of ${files[g].expected})</h3><div class="filelist">`;
    for (const n of names) {
      const miss = missing.has(n);
      html += `<div class="fitem ${miss ? "miss" : "ok"}">
        <span class="mark">${miss ? "x" : "+"}</span><span class="fname">${esc(n)}</span></div>`;
    }
    html += `</div>`;
  }
  return html;
}

function showDrawer(info) {
  const sectorName = path.sector;
  const state = info.unit ? info.unit.state : "not_started";
  $("drawer-title").textContent = unitTitle(info);
  let html = `<div class="state-line"><span class="tt-dot" style="background:${STATE_COLORS[state]}"></span>` +
    `${STATE_LABELS[state]}` +
    (info.unit && info.unit.fail_reason ? `: <span class="fail-reason">${esc(info.unit.fail_reason)}</span>` : "") +
    `</div>`;
  const stages = DATA.sectors[sectorName].stages;
  html += `<table class="stages"><tr><th>stage</th><th>state</th><th>time</th><th>memory</th><th>job</th></tr>`;
  for (const name of stages) {
    const rec = (info.unit && info.unit.stages[name]) || { state: "not_started" };
    const mem = rec.max_rss_gb != null ?
      `${rec.max_rss_gb} / ${rec.req_mem_gb ?? "?"} GB` : "";
    html += `<tr><td>${esc(name)}</td><td>${esc(STATE_LABELS[rec.state] || rec.state)}</td>` +
      `<td>${fmtMin(rec.elapsed_min)}</td><td>${mem}</td><td>${esc(rec.job || "")}</td></tr>`;
  }
  html += `</table>`;
  if (info.unit && info.unit.log) html += `<div class="meta">log: ${esc(info.unit.log)}</div>`;
  if (info.unit) {
    const fin = Object.values(info.unit.stages).map((s) => s.finished).filter(Boolean).sort().pop();
    if (fin) html += `<div class="meta">last stage finished ${fmtAgo(fin)}</div>`;
  }
  html += fileListHtml(info, sectorName);
  $("drawer-body").innerHTML = html;
  $("drawer").classList.remove("hidden");
}

/* ---------- interactions ---------- */

function setupInteractions() {
  const tooltip = $("tooltip");
  const board = $("board");

  board.addEventListener("mousemove", (e) => {
    const el = e.target.closest(".node");
    if (!el) { tooltip.classList.add("hidden"); return; }
    tooltip.innerHTML = tooltipHtml(currentChildren[el.dataset.i]);
    tooltip.classList.remove("hidden");
    const pad = 14;
    let x = e.clientX + pad, y = e.clientY + pad;
    const r = tooltip.getBoundingClientRect();
    if (x + r.width > window.innerWidth - 8) x = e.clientX - r.width - pad;
    if (y + r.height > window.innerHeight - 8) y = e.clientY - r.height - pad;
    tooltip.style.left = `${x}px`;
    tooltip.style.top = `${y}px`;
  });
  board.addEventListener("mouseleave", () => tooltip.classList.add("hidden"));

  function openNode(el) {
    const entry = currentChildren[el.dataset.i];
    if (!entry) return;
    if (entry.leaf) showDrawer(entry.info);
    else navigate(entry.child.path, true);
  }
  board.addEventListener("click", (e) => {
    const el = e.target.closest(".node");
    if (el) openNode(el);
  });
  board.addEventListener("keydown", (e) => {
    if (e.key !== "Enter" && e.key !== " ") return;
    const el = e.target.closest(".node");
    if (el) { e.preventDefault(); openNode(el); }
  });

  window.addEventListener("popstate", () => {
    path = hashToPath(location.hash);
    $("drawer").classList.add("hidden");
    renderAll();
  });

  $("view-toggle").addEventListener("click", (e) => {
    const b = e.target.closest("button[data-mode]");
    if (!b || b.dataset.mode === view.mode) return;
    view.mode = b.dataset.mode;
    for (const btn of $("view-toggle").querySelectorAll("button")) {
      btn.classList.toggle("active", btn.dataset.mode === view.mode);
    }
    renderSummary();
    renderLegend();
    renderBoard();
  });

  $("drawer-close").onclick = () => $("drawer").classList.add("hidden");
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape") $("drawer").classList.add("hidden");
  });

  $("failed-toggle").onclick = () => {
    view.failedOnly = !view.failedOnly;
    $("failed-toggle").classList.toggle("active", view.failedOnly);
    $("board").classList.toggle("failed-only", view.failedOnly);
  };

  $("theme-toggle").onclick = () => {
    const root = document.documentElement;
    const dark = getComputedStyle(root).colorScheme.includes("dark");
    const next = dark ? "light" : "dark";
    root.dataset.theme = next;
    localStorage.setItem("amel-theme", next);
  };

  let resizeTimer = null;
  window.addEventListener("resize", () => {
    clearTimeout(resizeTimer);
    resizeTimer = setTimeout(renderBoard, 150);
  });
}

/* ---------- service units ---------- */

function renderSU() {
  const a = DATA.account;
  const usedPct = a.allocation_su ? (100 * a.used_su) / a.allocation_su : 0;
  let html = `<div class="su-block">
    <h3>Account: ${esc(a.name)}</h3>
    <table class="su">
      <tr><td>Allocation</td><td class="r">${fmtN(a.allocation_su)}</td></tr>
      <tr><td>Used</td><td class="r">${fmtN(a.used_su)}</td></tr>
      <tr><td>Balance</td><td class="r">${fmtN(a.balance_su)}</td></tr>
    </table>
    <div class="su-bar acct-bar"><span style="width:${usedPct.toFixed(1)}%"></span></div>
    <div class="su-note">${usedPct.toFixed(1)}% of allocation used</div>
  </div>`;

  const maxP = Math.max(...DATA.people.map((p) => p.su_used || 0), 1);
  html += `<div class="su-block"><h3>By person</h3><table class="su">
    <tr><th>name</th><th>SU used</th><th></th></tr>` +
    DATA.people.map((p) =>
      `<tr><td>${esc(p.name)}</td><td class="r">${fmtN(p.su_used)}</td>
       <td><div class="su-bar"><span style="width:${(100 * (p.su_used || 0)) / maxP}%"></span></div></td></tr>`
    ).join("") + `</table></div>`;

  let rows = "";
  for (const [sname, sector] of Object.entries(DATA.sectors)) {
    for (const [rtName, rt] of Object.entries(sector.run_types)) {
      if (!rt.su_used) continue;
      rows += `<tr><td>${esc(sector.label)}</td><td>${esc(rtName)}</td>
        <td class="r">${fmtN(rt.su_used)}</td></tr>`;
    }
  }
  html += `<div class="su-block"><h3>By sector and run type</h3><table class="su">
    <tr><th>sector</th><th>run type</th><th>SU used</th></tr>${rows}</table>
    <div class="su-note">SU means service units, the core-hours charged to the account.</div></div>`;

  $("su-content").innerHTML = html;
}

/* ---------- boot ---------- */

async function boot() {
  const saved = localStorage.getItem("amel-theme");
  if (saved) document.documentElement.dataset.theme = saved;

  let status;
  try {
    const resp = await fetch("status.json", { cache: "no-store" });
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
    status = await resp.json();
  } catch (err) {
    $("error").textContent = `Could not load status.json (${err.message}).`;
    $("error").classList.remove("hidden");
    return;
  }
  DATA = status;

  $("last-scan").textContent =
    `last scan ${fmtAgo(status.generated_at)}, every ${status.scan_interval_hours} h`;
  if (status.source === "mock") $("mock-badge").classList.remove("hidden");

  const ageH = (Date.now() - new Date(status.generated_at).getTime()) / 3.6e6;
  if (ageH > 2 * status.scan_interval_hours) {
    const b = $("stale-banner");
    b.textContent = `The last scan is ${ageH.toFixed(1)} hours old (scans run every ` +
      `${status.scan_interval_hours} h). The cluster job may have stopped.`;
    b.classList.remove("hidden");
  }

  path = hashToPath(location.hash);
  setupInteractions();
  renderAll();
}

boot();
