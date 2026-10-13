/* AMEL run-status dashboard. Reads status.json (written by the collector,
   or by make_mock_status.py for the mock) and renders one view:
   - the cluster strip: jobs each person has running or queued, and
     service units on the cil account (from Slurm);
   - the progress grid: each cell shows two bars, projection files on top
     and aggregation files below, filling in as files appear on disk
     (from the output folders only). */

"use strict";

const STATE_LABELS = {
  done: "Done",
  running: "Running",
  failed: "Failed",
  partial: "Partial",
  not_started: "Not started",
};
const STATE_COLORS = {
  done: "var(--st-done)",
  running: "var(--st-running)",
  failed: "var(--st-failed)",
  partial: "var(--st-done)",
  not_started: "var(--st-none)",
};
const GROUPS = ["projection", "aggregation"];

let DATA = null;
let view = { sector: null, runType: null, model: null, failedOnly: false, focusGroup: null };
let openPeople = new Set();
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
}

function defaultRunType(sector) {
  const rts = Object.keys(sector.run_types);
  if (rts.includes("montecarlo")) return "montecarlo";
  if (rts.includes("median")) return "median";
  return rts[0];
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
      view.runType = defaultRunType(sector);
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
  for (const name of sector.disabled_run_types || []) {
    const b = document.createElement("button");
    b.className = "disabled";
    b.disabled = true;
    b.title = "Not part of this sector";
    b.textContent = name;
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
  const ft = fileTotals(rt);
  const pct = ft.expected ? (100 * ft.found) / ft.expected : 0;
  let html = `<div class="card"><div class="num">${fmtN(ft.found)}</div>
      <div class="lbl">files present of ${fmtN(ft.expected)}</div></div>
    <div class="card"><div class="num">${fmtN(ft.complete)}</div>
      <div class="lbl">units with all files, of ${fmtN(c.total)}</div></div>
    <div class="card"><div class="num">${fmtN(c.running)}</div>
      <div class="lbl"><span class="dot" style="background:${STATE_COLORS.running}"></span>units being written</div></div>
    <div class="card"><div class="num">${fmtN(c.failed)}</div>
      <div class="lbl"><span class="dot" style="background:${STATE_COLORS.failed}"></span>failed units</div></div>
    <div class="card progress-card">
      <div class="lbl">${pct.toFixed(1)}% of expected files</div>
      <div class="progress-bar"><span style="width:${pct}%;background:${STATE_COLORS.done}"></span></div></div>`;
  html += `<div class="card eta"><div class="num">${fmtEta(rt.eta_hours)}</div>
    <div class="lbl">est. time to finish</div>
    ${rt.eta_basis ? `<div class="sub">${esc(rt.eta_basis)}</div>` : ""}</div>`;
  $("summary").innerHTML = html;
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
  $("legend").innerHTML = `<span class="chip"><span class="sw" style="background:var(--st-none)"></span>no files yet</span>
    <span class="chip"><span class="sw half"></span>files appearing</span>
    <span class="chip"><span class="sw" style="background:${STATE_COLORS.done}"></span>all files present</span>
    <span class="chip"><span class="sw ring"></span>failed</span>
    <span class="note">Each box has two bars: projection files on top, aggregation files below.
    Click a scenario header to zoom into it, click a box for the file list.</span>`;
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

function cellInner(unit, model) {
  const f = unitFiles(unit, model);
  let html = "";
  for (const g of GROUPS) {
    const pct = f[g].total ? (100 * f[g].found) / f[g].total : 0;
    const run = unit && unit.state === "running" ? "fill-run" : "";
    html += `<div class="fbar"><span class="${run}" style="width:${pct}%"></span></div>`;
  }
  return html;
}

function unitHtml(key, unit, model, wide) {
  const state = unit ? unit.state : "not_started";
  const ring = state === "failed" ? " ring" : "";
  const fx = unit && state === "failed" && wide ? `<span class="fx">x</span>` : "";
  return `<div class="unit st-${state}${ring}" data-key="${esc(key)}">` +
    cellInner(unit, model) + fx + `</div>`;
}

function renderGrid() {
  const rt = currentRT();
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
          const inner = valid ? unitHtml(key, unit, m, wide) :
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
      let line = `${name}: ${STATE_LABELS[rec.state].toLowerCase()}`;
      if (rec.finished) line += `, ${fmtAgo(rec.finished)}`;
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
  html += `<table class="stages"><tr><th>stage</th><th>state</th><th>finished</th></tr>`;
  for (const name of stages) {
    const rec = (info.unit && info.unit.stages[name]) || { state: "not_started" };
    const fin = rec.finished ? `${fmtStamp(rec.finished)} (${fmtAgo(rec.finished)})` : "";
    html += `<tr><td>${esc(name)}</td><td>${esc(STATE_LABELS[rec.state] || rec.state)}</td>` +
      `<td>${fin}</td></tr>`;
  }
  html += `</table>`;
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

  $("jobs-content").addEventListener("click", (e) => {
    const head = e.target.closest(".person-row.has-jobs");
    if (!head) return;
    const name = head.dataset.name;
    if (openPeople.has(name)) openPeople.delete(name);
    else openPeople.add(name);
    renderJobs();
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

/* ---------- cluster strip ---------- */

function fmtDate(iso) {
  return new Date(iso + "T00:00:00").toLocaleDateString("en-US",
    { month: "short", day: "numeric", year: "numeric" });
}

function fmtStamp(iso) {
  return new Date(iso).toLocaleString("en-US",
    { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" });
}

function taskTotals(jobs) {
  let running = 0, queued = 0;
  for (const j of jobs || []) { running += j.tasks.running; queued += j.tasks.queued; }
  return { running, queued };
}

function renderCluster() {
  const people = DATA.people;
  const known = people.some((p) => p.active_jobs != null);
  const t = taskTotals(people.flatMap((p) => p.active_jobs || []));
  const a = DATA.account;
  const su = a.allocation_status === "ok" ? `${fmtN(a.balance_su)} SU left` :
    a.allocation_status === "none" ? "no allocation yet" : "balance n/a";
  $("cluster-badges").innerHTML = known ?
    `<span class="cbadge run">${fmtN(t.running)} running</span>
     <span class="cbadge queue">${fmtN(t.queued)} queued</span>
     <span class="cbadge">${esc(su)}</span>` :
    `<span class="cbadge">no Slurm data in this scan</span>`;
  renderJobs();
  renderSU();
}

function renderJobs() {
  let html = "";
  for (const p of DATA.people) {
    const jobs = p.active_jobs;
    const t = taskTotals(jobs);
    let status;
    if (!p.linked) status = `<span class="muted">no cluster user set</span>`;
    else if (jobs == null) status = `<span class="muted">n/a</span>`;
    else if (!jobs.length) status = `<span class="muted">no jobs</span>`;
    else {
      const parts = [];
      if (t.running) parts.push(`<span class="jstate run">${fmtN(t.running)} running</span>`);
      if (t.queued) parts.push(`<span class="jstate queue">${fmtN(t.queued)} queued</span>`);
      status = parts.join(", ") +
        ` <span class="muted">in ${jobs.length} ${jobs.length === 1 ? "job" : "jobs"}</span>`;
    }
    const has = jobs && jobs.length;
    const open = has && openPeople.has(p.name);
    html += `<div class="person-row${has ? " has-jobs" : ""}" data-name="${esc(p.name)}">
      <span class="caret">${has ? (open ? "v" : ">") : ""}</span>
      <span class="person-name">${esc(p.name)}</span><span class="person-status">${status}</span></div>`;
    if (open) {
      html += `<table class="su jobs"><tr><th>job name</th><th>partition</th><th>state</th>
        <th class="r">running</th><th class="r">queued</th><th class="r">done</th><th class="r">elapsed</th></tr>` +
        jobs.map((j) => `<tr><td>${esc(j.job_name)}</td><td>${esc(j.partition)}</td>
          <td><span class="jstate ${j.state === "RUNNING" ? "run" : "queue"}">${j.state === "RUNNING" ? "Running" : "Queued"}</span></td>
          <td class="r">${fmtN(j.tasks.running)}</td><td class="r">${fmtN(j.tasks.queued)}</td>
          <td class="r">${fmtN(j.tasks.done)}</td><td class="r">${j.state === "RUNNING" ? fmtMin(j.elapsed_min) : ""}</td></tr>`
        ).join("") + `</table>`;
    }
  }
  html += `<div class="su-note">All jobs on the ${esc(DATA.account.name)} account, whatever the job name.
    Click a name for the job list. Done means tasks that finished successfully.</div>`;
  $("jobs-content").innerHTML = html;
}

function renderSU() {
  const a = DATA.account;
  $("su-title").textContent = `Service units, ${a.name} account`;
  let html;
  if (a.allocation_status === "ok") {
    const usedPct = a.allocation_su ? (100 * a.used_su) / a.allocation_su : 0;
    html = `<table class="su">
      <tr><td>Allocation</td><td class="r">${fmtN(a.allocation_su)}</td></tr>
      <tr><td>Used</td><td class="r">${fmtN(a.used_su)}</td></tr>
      <tr><td>Remaining balance</td><td class="r">${fmtN(a.balance_su)}</td></tr>
    </table>
    <div class="su-bar acct-bar"><span style="width:${usedPct.toFixed(1)}%"></span></div>
    <div class="su-note">${usedPct.toFixed(1)}% of allocation used</div>`;
  } else if (a.allocation_status === "none") {
    html = `<div class="no-alloc">No allocation yet</div>
      <div class="su-note">The ${esc(a.name)} account has no allocation, so there is no balance to show.</div>`;
  } else {
    html = `<div class="no-alloc muted">Balance not read in this scan</div>`;
  }

  const maxP = Math.max(...DATA.people.map((p) => p.su_used || 0), 1);
  html += `<h4>Use per person since ${esc(fmtDate(a.su_since))}</h4><table class="su">` +
    DATA.people.map((p) => {
      const val = !p.linked ? `<span class="muted">no cluster user set</span>` :
        p.su_used == null ? "n/a" : fmtN(p.su_used);
      return `<tr><td>${esc(p.name)}</td><td class="r">${val}</td>
        <td><div class="su-bar"><span style="width:${(100 * (p.su_used || 0)) / maxP}%"></span></div></td></tr>`;
    }).join("") + `</table>
    <div class="su-note">Core hours of all jobs on the account, not only projection runs.</div>`;
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
  view.runType = defaultRunType(status.sectors[view.sector]);
  setupInteractions();
  renderCluster();
  renderAll();
}

boot();
