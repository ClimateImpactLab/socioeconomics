/* AMEL run-status dashboard. Reads status.json (written by the collector,
   or by make_mock_status.py for the mock) and renders the grids.

   Two views share the same grid shape:
   - files: each cell shows two bars, projection files on top and
     aggregation files below, filling in as files appear on disk;
   - jobs: each cell shows one stripe per pipeline stage, colored by the
     Slurm state of that stage. */

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
let view = {
  mode: "files", sector: null, runType: null, model: null,
  failedOnly: false, focusGroup: null,
};
let unitIndex = new Map();

const $ = (id) => document.getElementById(id);

/* ---------- formatting helpers ---------- */

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

function esc(s) {
  return String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function unitKey(u) {
  return [u.model, u.ssp, u.rcp, u.iam, u.gcm, u.batch ?? ""].join("|");
}

/* ---------- data access ---------- */

function currentSector() {
  return DATA.sectors[view.sector];
}

function currentRT() {
  return currentSector().run_types[view.runType];
}

function sectorTotals(sector) {
  let done = 0, total = 0;
  for (const rt of Object.values(sector.run_types)) {
    done += rt.counts.done;
    total += rt.counts.total;
  }
  return { done, total };
}

function resolveName(name, rcp) {
  return name.split("{rcp}").join(rcp);
}

// Expected file totals per unit for one model: {projection: n, aggregation: m}.
function specTotals(model) {
  const spec = currentSector().files_spec[model];
  const out = {};
  for (const g of GROUPS) out[g] = spec[g].length;
  return out;
}

function unitFiles(unit, model) {
  const totals = specTotals(model);
  const out = {};
  for (const g of GROUPS) {
    const rec = unit && unit.files ? unit.files[g] : null;
    out[g] = { found: rec ? rec.found : 0, total: rec ? rec.total : totals[g] };
  }
  return out;
}

/* ---------- top-level render ---------- */

function renderAll() {
  renderSectorTabs();
  renderRunTypeTabs();
  renderSummary();
  renderModelPills();
  renderLegend();
  renderGrid();
  renderSU();
}

function renderSectorTabs() {
  const el = $("sector-tabs");
  el.innerHTML = "";
  for (const [name, sector] of Object.entries(DATA.sectors)) {
    const t = sectorTotals(sector);
    const pct = t.total ? Math.round((100 * t.done) / t.total) : 0;
    const b = document.createElement("button");
    b.className = name === view.sector ? "active" : "";
    b.innerHTML = `${esc(sector.label)}<span class="tab-count">${pct}%</span>`;
    b.onclick = () => {
      view.sector = name;
      const rts = Object.keys(sector.run_types);
      if (!rts.includes(view.runType)) view.runType = rts[0];
      view.model = null;
      view.focusGroup = null;
      renderAll();
    };
    el.appendChild(b);
  }
}

function renderRunTypeTabs() {
  const el = $("runtype-tabs");
  el.innerHTML = "";
  const sector = currentSector();
  for (const [name, rt] of Object.entries(sector.run_types)) {
    const b = document.createElement("button");
    b.className = name === view.runType ? "active" : "";
    b.innerHTML = `${esc(name)}<span class="tab-count">${rt.counts.done}/${rt.counts.total}</span>`;
    b.onclick = () => {
      view.runType = name;
      view.model = null;
      view.focusGroup = null;
      renderAll();
    };
    el.appendChild(b);
  }
}

// File totals across the whole run type (all models, all units).
function fileTotals(rt) {
  const perModel = {};
  for (const m of rt.dims.models) {
    const t = specTotals(m);
    perModel[m] = t.projection + t.aggregation;
  }
  const unitsPerModel = rt.counts.total / rt.dims.models.length;
  let expected = 0;
  for (const m of rt.dims.models) expected += unitsPerModel * perModel[m];
  let found = 0, complete = 0;
  for (const u of rt.units) {
    const f = unitFiles(u, u.model);
    const uf = f.projection.found + f.aggregation.found;
    found += uf;
    if (f.projection.found >= f.projection.total &&
        f.aggregation.found >= f.aggregation.total) complete += 1;
  }
  return { expected: Math.round(expected), found, complete };
}

function renderSummary() {
  const rt = currentRT();
  const c = rt.counts;
  const el = $("summary");
  let html = "";

  if (view.mode === "files") {
    const ft = fileTotals(rt);
    const pct = ft.expected ? (100 * ft.found) / ft.expected : 0;
    html += `<div class="card"><div class="num">${fmtN(ft.found)}</div>
      <div class="lbl">files present of ${fmtN(ft.expected)}</div></div>`;
    html += `<div class="card"><div class="num">${fmtN(ft.complete)}</div>
      <div class="lbl">units with all files, of ${fmtN(c.total)}</div></div>`;
    html += `<div class="card"><div class="num">${fmtN(c.failed)}</div>
      <div class="lbl"><span class="dot" style="background:${STATE_COLORS.failed}"></span>failed units</div></div>`;
    html += `<div class="card progress-card">
      <div class="lbl">${pct.toFixed(1)}% of expected files</div>
      <div class="progress-bar"><span style="width:${pct}%;background:${STATE_COLORS.done}"></span></div></div>`;
  } else {
    for (const s of STATES) {
      html += `<div class="card"><div class="num">${c[s].toLocaleString("en-US")}</div>
        <div class="lbl"><span class="dot" style="background:${STATE_COLORS[s]}"></span>${STATE_LABELS[s]}</div></div>`;
    }
    const pct = c.total ? ((100 * c.done) / c.total) : 0;
    let bar = "";
    for (const s of STATES) {
      if (s === "not_started" || !c[s]) continue;
      bar += `<span style="width:${(100 * c[s]) / c.total}%;background:${STATE_COLORS[s]};${s === "partial" ? "opacity:.45;" : ""}"></span>`;
    }
    html += `<div class="card progress-card">
      <div class="lbl">${pct.toFixed(1)}% done of ${fmtN(c.total)} units</div>
      <div class="progress-bar">${bar}</div></div>`;
  }

  html += `<div class="card eta"><div class="num">${fmtEta(rt.eta_hours)}</div>
    <div class="lbl">est. time to finish</div>
    ${rt.eta_basis ? `<div class="sub">${esc(rt.eta_basis)}</div>` : ""}</div>`;
  el.innerHTML = html;
}

function renderModelPills() {
  const rt = currentRT();
  const el = $("model-pills");
  el.innerHTML = "";
  const models = rt.dims.models;
  // In single-style grids the models are the rows, so no picker is needed.
  if (models.length < 2 || gridKind(rt) === "models") { view.model = null; return; }
  if (!view.model) view.model = models[0];
  for (const m of models) {
    const b = document.createElement("button");
    b.className = m === view.model ? "active" : "";
    b.textContent = m;
    b.onclick = () => { view.model = m; renderGrid(); };
    el.appendChild(b);
  }
}

function renderLegend() {
  const sector = currentSector();
  let html;
  if (view.mode === "files") {
    html = `<span class="chip"><span class="sw" style="background:var(--st-none)"></span>no files yet</span>
      <span class="chip"><span class="sw half"></span>files appearing</span>
      <span class="chip"><span class="sw" style="background:${STATE_COLORS.done}"></span>all files present</span>
      <span class="chip"><span class="sw ring"></span>failed job</span>
      <span class="note">Each box has two bars: projection files on top, aggregation files below.
      Click a scenario header to zoom into it, click a box for the file list.</span>`;
  } else {
    const chips = STATES.filter((s) => s !== "partial").map((s) =>
      `<span class="chip"><span class="sw ${s === "queued" ? "queued" : ""}"
        style="background:${STATE_COLORS[s]}"></span>${STATE_LABELS[s]}</span>`).join("");
    html = chips +
      `<span class="note">Each box has one stripe per stage, top to bottom: ${sector.stages.join(", ")}.
      Click a scenario header to zoom into it, click a box for details.</span>`;
  }
  $("legend").innerHTML = html;
}

/* ---------- grid ---------- */

// "models": rows are sub-models (single, quick_test).
// "gcms": rows are GCMs (median, montecarlo).
function gridKind(rt) {
  const anyRcp = Object.keys(rt.dims.gcms)[0];
  return rt.dims.gcms[anyRcp].length > 1 ? "gcms" : "models";
}

function gcmUnion(gcms) {
  const lists = Object.values(gcms).sort((a, b) => b.length - a.length);
  const seen = new Set(lists[0]);
  const union = [...lists[0]];
  for (const list of lists.slice(1)) {
    for (const g of list) if (!seen.has(g)) { seen.add(g); union.push(g); }
  }
  return union;
}

function buildGroups(cells) {
  const groups = [];
  for (const cell of cells) {
    const label = `${cell.ssp} ${rcpShort(cell.rcp)}`;
    const last = groups[groups.length - 1];
    if (last && last.label === label) last.cells.push(cell);
    else groups.push({ label, cells: [cell] });
  }
  return groups;
}

function cellInner(unit, model, stages) {
  if (view.mode === "files") {
    const f = unitFiles(unit, model);
    let html = "";
    for (const g of GROUPS) {
      const pct = f[g].total ? (100 * f[g].found) / f[g].total : 0;
      const run = unit && unit.state === "running" ? " fill-run" : "";
      html += `<div class="fbar"><span class="${run.trim()}" style="width:${pct}%"></span></div>`;
    }
    return html;
  }
  if (!unit) return stages.map(() => `<div class="seg none"></div>`).join("");
  return stages.map((st) => {
    const rec = unit.stages[st] || { state: "not_started" };
    const cls = rec.state === "not_started" ? "none" : rec.state;
    return `<div class="seg ${cls}"></div>`;
  }).join("");
}

function unitHtml(key, unit, model, stages, wide) {
  const state = unit ? unit.state : "not_started";
  const ring = state === "failed" ? " ring" : "";
  const fx = unit && state === "failed" && wide ? `<span class="fx">x</span>` : "";
  return `<div class="unit st-${state}${ring}" data-key="${esc(key)}">` +
    cellInner(unit, model, stages) + fx + `</div>`;
}

function renderGrid() {
  const rt = currentRT();
  const sector = currentSector();
  const stages = sector.stages;
  const wrap = $("grid-wrap");
  wrap.classList.toggle("failed-only", view.failedOnly);

  unitIndex = new Map();
  for (const u of rt.units) unitIndex.set(unitKey(u), u);

  const kind = gridKind(rt);
  const batches = rt.dims.batches;
  const batchList = batches ? [...Array(batches).keys()] : [null];

  let groups = buildGroups(rt.dims.cells);
  if (view.focusGroup && groups.some((g) => g.label === view.focusGroup)) {
    groups = groups.filter((g) => g.label === view.focusGroup);
  } else {
    view.focusGroup = null;
  }
  $("focus-clear").classList.toggle("hidden", !view.focusGroup);

  const rows = kind === "models" ? rt.dims.models : gcmUnion(rt.dims.gcms);
  const model = kind === "models" ? null : (view.model || rt.dims.models[0]);
  const nCols = groups.reduce((n, g) => n + g.cells.length, 0) * batchList.length;

  // Size the cells so the whole grid fits without sideways scrolling.
  const labelW = kind === "gcms" ? 150 : 92;
  const availW = wrap.getBoundingClientRect().width - labelW - groups.length - 24;
  const cw = Math.max(3, Math.min(46, Math.floor(availW / nCols) - 2));
  const availH = Math.max(240, window.innerHeight * 0.62);
  const ch = Math.max(7, Math.min(26, Math.floor(availH / rows.length) - 3));
  wrap.style.setProperty("--cw", `${cw}px`);
  wrap.style.setProperty("--ch", `${ch}px`);
  wrap.style.setProperty("--labelw", `${labelW}px`);
  wrap.classList.toggle("tiny", cw < 9);
  const wide = cw >= 14;

  let head1 = `<tr><th class="corner group"></th>`;
  let head2 = `<tr><th class="corner group"></th>`;
  for (const g of groups) {
    const focused = view.focusGroup === g.label ? " focused" : "";
    head1 += `<th class="group gclick${focused}" data-group="${esc(g.label)}"
      colspan="${g.cells.length * batchList.length}" title="Click to zoom this scenario">${esc(g.label)}</th>`;
    for (const cell of g.cells) {
      head2 += `<th class="group" colspan="${batchList.length}">${esc(cell.iam)}</th>`;
    }
  }
  head1 += "</tr>";
  head2 += "</tr>";

  let body = "";
  for (const row of rows) {
    body += `<tr><th title="${esc(row)}">${esc(row)}</th>`;
    for (const g of groups) {
      for (const cell of g.cells) {
        let first = true;
        for (const b of batchList) {
          const m = kind === "models" ? row : model;
          const gcm = kind === "models" ? rt.dims.gcms[cell.rcp][0] : row;
          const valid = rt.dims.gcms[cell.rcp].includes(gcm);
          const key = [m, cell.ssp, cell.rcp, cell.iam, gcm, b ?? ""].join("|");
          const unit = unitIndex.get(key) || null;
          const inner = valid ? unitHtml(key, unit, m, stages, wide) :
            `<div class="unit void"></div>`;
          body += `<td class="${first ? "cellgroup-start" : ""}">${inner}</td>`;
          first = false;
        }
      }
    }
    body += "</tr>";
  }

  wrap.innerHTML =
    `<table class="grid"><thead>${head1}${head2}</thead><tbody>${body}</tbody></table>`;
}

/* ---------- tooltip and drawer ---------- */

function unitFromEl(el) {
  const key = el.dataset.key;
  const parts = key.split("|");
  const unit = unitIndex.get(key) || null;
  return {
    unit,
    model: parts[0], ssp: parts[1], rcp: parts[2], iam: parts[3],
    gcm: parts[4], batch: parts[5],
  };
}

function unitTitle(info) {
  const bits = [];
  if (info.model !== "main") bits.push(info.model);
  bits.push(info.ssp, info.rcp, info.iam, info.gcm);
  if (info.batch !== "") bits.push(`batch${info.batch}`);
  return bits.join(" ");
}

function tooltipHtml(info) {
  const state = info.unit ? info.unit.state : "not_started";
  let html = `<div class="tt-title"><span class="tt-dot" style="background:${STATE_COLORS[state]}"></span>${esc(unitTitle(info))}</div>`;
  html += `<div class="tt-row">${STATE_LABELS[state]}${info.unit && info.unit.fail_reason ? ": " + esc(info.unit.fail_reason) : ""}</div>`;
  const f = unitFiles(info.unit, info.model);
  html += `<div class="tt-row">projection files ${f.projection.found} of ${f.projection.total}, ` +
    `aggregation ${f.aggregation.found} of ${f.aggregation.total}</div>`;
  if (info.unit) {
    for (const [name, rec] of Object.entries(info.unit.stages)) {
      if (rec.state === "not_started") continue;
      let line = `${name}: ${rec.state}`;
      if (rec.elapsed_min != null) line += `, ${fmtMin(rec.elapsed_min)}`;
      if (rec.max_rss_gb != null) line += `, ${rec.max_rss_gb} GB`;
      html += `<div class="tt-row">${esc(line)}</div>`;
    }
  }
  html += `<div class="tt-row tt-hint">Click for the full file list</div>`;
  return html;
}

function fileListHtml(info) {
  const spec = currentSector().files_spec[info.model];
  const f = unitFiles(info.unit, info.model);
  let html = "";
  for (const g of GROUPS) {
    const names = spec[g].map((n) => resolveName(n, info.rcp));
    const rec = info.unit && info.unit.files ? info.unit.files[g] : null;
    let missing;
    if (!rec || rec.found === 0) missing = new Set(names);
    else if (rec.found >= rec.total) missing = new Set();
    else missing = new Set((rec.missing || []).map((n) => resolveName(n, info.rcp)));
    html += `<h3>${g} files (${f[g].found} of ${f[g].total})</h3><div class="filelist">`;
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
  const state = info.unit ? info.unit.state : "not_started";
  $("drawer-title").textContent = unitTitle(info);
  let html = `<div class="state-line"><span class="tt-dot" style="background:${STATE_COLORS[state]}"></span>` +
    `${STATE_LABELS[state]}` +
    (info.unit && info.unit.fail_reason ? `: <span class="fail-reason">${esc(info.unit.fail_reason)}</span>` : "") +
    `</div>`;
  const stages = currentSector().stages;
  html += `<table class="stages"><tr><th>stage</th><th>state</th><th>time</th><th>memory</th><th>job</th></tr>`;
  for (const name of stages) {
    const rec = (info.unit && info.unit.stages[name]) || { state: "not_started" };
    const mem = rec.max_rss_gb != null ?
      `${rec.max_rss_gb} / ${rec.req_mem_gb ?? "?"} GB` : "";
    html += `<tr><td>${esc(name)}</td><td>${esc(STATE_LABELS[rec.state] || rec.state)}</td>` +
      `<td>${fmtMin(rec.elapsed_min)}</td><td>${mem}</td><td>${esc(rec.job || "")}</td></tr>`;
  }
  html += `</table>`;
  if (info.unit && info.unit.log) {
    html += `<div class="meta">log: ${esc(info.unit.log)}</div>`;
  }
  if (info.unit) {
    const fin = Object.values(info.unit.stages).map((s) => s.finished).filter(Boolean).sort().pop();
    if (fin) html += `<div class="meta">last stage finished ${fmtAgo(fin)}</div>`;
  }
  html += fileListHtml(info);
  $("drawer-body").innerHTML = html;
  $("drawer").classList.remove("hidden");
}

/* ---------- interactions ---------- */

function setupInteractions() {
  const tooltip = $("tooltip");
  const wrap = $("grid-wrap");

  wrap.addEventListener("mousemove", (e) => {
    const el = e.target.closest(".unit");
    if (!el || el.classList.contains("void")) { tooltip.classList.add("hidden"); return; }
    tooltip.innerHTML = tooltipHtml(unitFromEl(el));
    tooltip.classList.remove("hidden");
    const pad = 14;
    let x = e.clientX + pad, y = e.clientY + pad;
    const r = tooltip.getBoundingClientRect();
    if (x + r.width > window.innerWidth - 8) x = e.clientX - r.width - pad;
    if (y + r.height > window.innerHeight - 8) y = e.clientY - r.height - pad;
    tooltip.style.left = `${x}px`;
    tooltip.style.top = `${y}px`;
  });
  wrap.addEventListener("mouseleave", () => tooltip.classList.add("hidden"));
  wrap.addEventListener("click", (e) => {
    const gh = e.target.closest("th.gclick");
    if (gh) {
      view.focusGroup = view.focusGroup === gh.dataset.group ? null : gh.dataset.group;
      renderGrid();
      return;
    }
    const el = e.target.closest(".unit");
    if (el && !el.classList.contains("void")) showDrawer(unitFromEl(el));
  });

  $("focus-clear").onclick = () => { view.focusGroup = null; renderGrid(); };

  $("view-toggle").addEventListener("click", (e) => {
    const b = e.target.closest("button[data-mode]");
    if (!b || b.dataset.mode === view.mode) return;
    view.mode = b.dataset.mode;
    for (const btn of $("view-toggle").querySelectorAll("button")) {
      btn.classList.toggle("active", btn.dataset.mode === view.mode);
    }
    renderSummary();
    renderLegend();
    renderGrid();
  });

  $("drawer-close").onclick = () => $("drawer").classList.add("hidden");
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape") $("drawer").classList.add("hidden");
  });

  $("failed-toggle").onclick = () => {
    view.failedOnly = !view.failedOnly;
    $("failed-toggle").classList.toggle("active", view.failedOnly);
    $("grid-wrap").classList.toggle("failed-only", view.failedOnly);
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
    resizeTimer = setTimeout(renderGrid, 150);
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

  view.sector = Object.keys(status.sectors)[0];
  view.runType = Object.keys(status.sectors[view.sector].run_types)[0];
  setupInteractions();
  renderAll();
}

boot();
