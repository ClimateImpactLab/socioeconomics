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
const DOT_CLASS = { projection: "proj", costs: "cost", levels: "lvl", aggregated: "agr", other: "oth" };
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
// The collector pushes its data to the monitor-data branch every hour, so
// the page reads it from there; the copy deployed with the site is the fallback.
const REMOTE_BASE = "https://raw.githubusercontent.com/ClimateImpactLab/socioeconomics/monitor-data/data/";
let BASE = params.get("source") === "mock" ? "mock/" : REMOTE_BASE;

let DATA = null;
const view = { sector: null, runType: null, model: null, modelOff: false, ssps: [], picks: null,
  selected: null, aggScen: null, hl: "all" };
const detailCache = new Map();
let cellIndex = new Map();

const $ = (id) => document.getElementById(id);

/* ---------- formatting ---------- */

function esc(s) {
  return String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
}
function fmtN(n) { return n == null ? "n/a" : Math.round(n).toLocaleString("en-US"); }
// A complete percent is written "100%" and nothing done "0%"; one in between
// never rounds to either.
function fmtPct2(p) {
  if (p == null || isNaN(p)) return "n/a";
  if (p >= 100) return "100%";
  if (p <= 0) return "0%";
  if (p >= 99.995) return "99.99%";
  return `${p.toFixed(2)}%`;
}
function fmtPctShort(p) {
  if (p >= 100) return "100%";
  if (!(p > 0)) return "0%";
  if (p > 0 && p < 0.1) return "<0.1%";
  return p < 10 ? `${p.toFixed(1)}%` : `${Math.min(99, Math.round(p))}%`;
}
function fmtMin(min) {
  if (min == null) return "";
  if (min < 60) return `${Math.round(min)}m`;
  return `${Math.floor(min / 60)}h ${String(Math.round(min % 60)).padStart(2, "0")}m`;
}
function fmtEta(hours) {
  if (hours == null) return "n/a";
  if (hours < 48) return `~${Math.max(1, Math.round(hours))}h`;
  if (hours > 24 * 365) return "over a year";
  return `~${Math.round(hours / 24)}d`;
}
// A moment in local time, short: "Oct 19, 08:00", or with the year:
// "Oct 19, 2026, 08:00".
function fmtWhen(iso, withYear) {
  return new Date(iso).toLocaleString("en-US", { month: "short", day: "numeric", year: withYear ? "numeric" : undefined,
    hour: "2-digit", minute: "2-digit", hourCycle: "h23" });
}
function fmtSize(bytes) {
  if (!bytes) return "";
  if (bytes >= 1048576) return `${(bytes / 1048576).toFixed(1)} MB`;
  if (bytes >= 1024) return `${Math.round(bytes / 1024)} KB`;
  return `${bytes} B`;
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
// A unit's file bits, with the aggregation part taken from another
// aggregation scenario when one is picked (scen); projection stays the same.
function unitBits(unit, spec, scen) {
  if (!unit) return "";
  const alt = scen && unit.alt_bits && unit.alt_bits[scen];
  if (scen && !alt) return unit.bits.slice(0, spec.projection.length) + "0".repeat(groupTotal(spec, AGG_GROUPS));
  return alt ? unit.bits.slice(0, spec.projection.length) + alt : unit.bits;
}

function unitGroups(unit, spec, scen) {
  const bits = unitBits(unit, spec, scen);
  const out = {};
  let i = 0;
  for (const g of GROUPS) {
    out[g] = spec[g].map(() => bits[i++] === "1");
  }
  return out;
}

function unitCounts(unit, spec, scen) {
  const pres = unitGroups(unit, spec, scen);
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
function filesOf(sec, rt, scen) {
  const out = { proj: 0, projExp: 0, agg: 0, aggExp: 0, complete: 0, partial: 0, started: 0, running: 0, failed: 0 };
  const perModel = rt.counts.total / rt.dims.models.length;
  for (const m of rt.dims.models) {
    const s = specOf(sec, m);
    out.projExp += perModel * s.projection.length;
    out.aggExp += perModel * groupTotal(s, AGG_GROUPS);
  }
  for (const u of rt.units) {
    const c = unitCounts(u, specOf(sec, u.model), scen);
    out.proj += c.proj;
    out.agg += c.agg;
    if (u.state === "running") out.running += 1;
    if (u.state === "failed") out.failed += 1;
    if (c.proj + c.agg === 0) continue;
    out.started += 1;
    if (c.proj >= c.projTotal && c.agg >= c.aggTotal) out.complete += 1;
    else out.partial += 1;
  }
  return out;
}

// A sector's progress is the progress of its main run only (montecarlo,
// or median where there is no montecarlo); singles and tests do not count.
// "Projection 100% (64/64), Aggregation 0% (0/496)"; a part with no
// expected files is left out.
// While another aggregation scenario is picked, the overall figures say they
// count the main one.
function progressText(f) {
  const part = (name, n, exp) => exp ? `${name} ${fmtPctShort(pctOf(n, exp))} (${fmtN(n)}/${fmtN(exp)})` : null;
  return [part("Projection", f.proj, f.projExp), part(`Aggregation${mainMark()}`, f.agg, f.aggExp)].filter(Boolean).join(", ");
}
function mainMark() {
  return view.sector && view.runType && curScen() ? " (main)" : "";
}

// The aggregation scenario picked for the current run type, or null for the main one.
function curScen() {
  const sc = runType() && runType().agg_scenarios;
  return view.aggScen && sc && sc.others.includes(view.aggScen) ? view.aggScen : null;
}
// A scenario that changes with the RCP is shown by its name only:
// "MERGEETL60_{rcp}" reads "MERGEETL60". File names keep the full form.
function scenLabel(sc) {
  return sc.replace(/[_-]?\{rcp\}/, "");
}
// An aggregation file name under the picked scenario, for one column's RCP.
function scenName(name, info, sc) {
  const main = runType().agg_scenarios && runType().agg_scenarios.main;
  return sc && main && name.includes(main) ? name.replace(main, sc.replace("{rcp}", info.rcp)) : name;
}

function sectorFiles(sec) {
  const rt = sec.run_types[defaultRunType(sec)];
  return rt ? filesOf(sec, rt) : { proj: 0, projExp: 0, agg: 0, aggExp: 0 };
}

// A sector is active when projection files were written in its folders in
// the last 24 hours before the scan, or a unit is being written right now.
function sectorActive(sec) {
  const scan = new Date(DATA.generated_at).getTime();
  return sectorRunning(sec) || Object.values(sec.run_types).some((rt) =>
    rt.last_projection_write && scan - new Date(rt.last_projection_write).getTime() < 24 * 3.6e6);
}


function sectorRunning(sec) {
  return Object.values(sec.run_types).some((rt) =>
    rt.units.some((u) => u.stages.generate && u.stages.generate.state === "running"));
}

// Projection (P) and aggregation (A) files present out of expected, for a
// set of units; expUnits is the number of expected units per sub-model.
function paFiles(sec, units, expUnits, models, scen) {
  const out = { p: 0, pExp: 0, a: 0, aExp: 0 };
  for (const m of models) {
    const spec = specOf(sec, m);
    out.pExp += expUnits * spec.projection.length;
    out.aExp += expUnits * groupTotal(spec, AGG_GROUPS);
  }
  for (const u of units) {
    const c = unitCounts(u, specOf(sec, u.model), scen);
    out.p += c.proj;
    out.a += c.agg;
  }
  return out;
}

// "P 54% (4,174/7,680), A 0% (0/17,280)", or with short set the percents
// only, for narrow columns.
function paText(n, short) {
  const part = (name, a, exp) => `${name} ${fmtPctShort(pctOf(a, exp))}` + (short ? "" : ` (${fmtN(a)}/${fmtN(exp)})`);
  return `${part("P", n.p, n.pExp)}, ${part("A", n.a, n.aExp)}`;
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

/* ---------- render ---------- */

function renderAll() {
  // Nothing below the sector tabs shows until a sector is picked, and the
  // grid waits for a sub-model when the sector has several (crops, fuels).
  document.body.classList.toggle("no-sector", !view.sector);
  if (DATA) renderCamel();
  pickDefaults();
  renderTree();
  const noRun = !!view.sector && !view.runType;
  const needModel = !!view.sector && !noRun && gridKind(runType()) === "gcms" && runType().dims.models.length > 1 && !view.model;
  document.body.classList.toggle("no-run", noRun);
  document.body.classList.toggle("no-model", needModel || noRun);
  $("pick-note").textContent = "Pick a sector in the list to see its progress.";
  const mainNote = $("main-note");
  if (mainNote) mainNote.textContent = noRun ? "Select a run type to see progress"
    : needModel ? "Select a sub-model to see progress" : "";
  if (!view.sector || noRun) return;
  renderCards();
  if (needModel) return;
  renderSspTabs();
  renderLegend();
  renderGrid();
}

/* ---------- tree navigation ---------- */

// Phones held upright are narrow; held sideways they are short. Either way
// the tree is a menu at the top, so the grid keeps the full width.
const PHONE = matchMedia("(max-width: 600px), (max-height: 500px)");

const RUN_TYPE_ORDER = ["single", "median", "montecarlo"];

// "P 18% · A 13%" for a set of files.
function paShort(f) {
  const bits = [];
  if (f.projExp) bits.push(`P ${fmtPctShort(pctOf(f.proj, f.projExp))}`);
  if (f.aggExp) bits.push(`A ${fmtPctShort(pctOf(f.agg, f.aggExp))}`);
  return bits.join(" · ");
}

// Moves the cards, SSP row and grid into a right-hand column, with the tree
// on the left. On phones the tree folds into a menu at the top.
function buildTreeLayout() {
  const layout = document.createElement("div");
  layout.className = "tree-layout";
  layout.innerHTML = `<div class="tree-side" id="tree-side"><details class="tree-menu" id="tree-menu" open>
    <summary id="tree-summary">Menu</summary><nav class="tree" id="tree" aria-label="Sectors and runs"></nav></details></div>
    <div class="tree-main" id="tree-main"><div class="tree-path" id="tree-path"></div></div>`;
  const cards = $("cards");
  cards.parentNode.insertBefore(layout, cards);
  const main = $("tree-main");
  let el = layout.nextSibling;
  while (el && el.id !== "global-tip") {
    const next = el.nextSibling;
    main.appendChild(el);
    el = next;
  }
  // The "pick a sector" note sits right below the list, then the P and A
  // key, then one box with the SSP, RCP and IAM badges ("Scenario") and the
  // state filter ("Filter").
  $("tree-side").appendChild($("pick-note"));
  const key = document.createElement("div");
  key.className = "tree-key";
  key.innerHTML = "<b>P</b> projection files present | <b>A</b> aggregation files present, out of expected.";
  $("tree-menu").appendChild(key);
  const box = document.createElement("div");
  box.className = "scen-box";
  box.id = "scen-box";
  box.innerHTML = `<div class="sbx-title">Scenario</div>`;
  box.appendChild($("scen-graph"));
  box.insertAdjacentHTML("beforeend", `<div class="sbx-title sbx-filter">Filter</div>`);
  box.appendChild($("hl-tabs"));
  $("tree-menu").appendChild(box);
  // The note where the grid would be, until a run type (and sub-model) is picked.
  const note = document.createElement("div");
  note.className = "main-note";
  note.id = "main-note";
  $("tree-path").after(note);
  $("tree-menu").open = !PHONE.matches;
  PHONE.addEventListener("change", () => { $("tree-menu").open = !PHONE.matches; });
  $("tree").addEventListener("click", (e) => {
    const b = e.target.closest(".tnode[data-act]");
    if (!b || b.disabled) return;
    // On phones the menu stays open after a pick, so the badges and the
    // filter stay at hand.
    treePick(b.dataset.act, b.dataset.key);
  });
}

// No sub-model unless the run's grid has several; then the user picks one.
function pickDefaults() {
  if (!view.sector || !view.runType) return;
  const rt = runType();
  if (!(gridKind(rt) === "gcms" && rt.dims.models.length > 1)) view.model = null;
}

function treePick(act, key) {
  closeDetail();
  if (act === "sector") {
    view.modelOff = false;
    if (key === view.sector) {
      view.sector = view.runType = view.model = null;
      view.ssps = [];
    } else {
      view.sector = key;
      view.aggScen = null;
      view.runType = null;
      view.model = null;
      view.ssps = [];
    }
  } else if (act === "run") {
    view.aggScen = null;
    view.model = null;
    view.modelOff = false;
    if (key === view.runType) {
      view.runType = null;
      view.ssps = [];
    } else {
      view.runType = key;
      view.picks = null;
      view.hl = "all";
    }
  } else if (act === "model") {
    view.modelOff = key === view.model;
    view.model = view.modelOff ? null : key;
  } else if (act === "scen") {
    view.aggScen = key || null;
  }
  renderAll();
}

function tnode(act, key, label, figure, { on = false, off = false, cls = "", style = "", leaf = false, title = "" } = {}) {
  return `<button class="tnode ${cls}${on ? " on" : ""}${off ? " off" : ""}" ${off ? "disabled" : ""}
    data-act="${act}" data-key="${esc(key)}" data-leaf="${leaf ? 1 : 0}" style="${style}"${title ? ` title="${esc(title)}"` : ""}>
    <span class="tlabel">${label}</span>${figure ? `<span class="tfig">${esc(figure)}</span>` : ""}</button>`;
}

function renderTree() {
  let html = "";
  for (const cs of CAMEL_SECTIONS) {
    const sec = DATA.sectors[cs.key];
    const color = `--tc:var(--sec-${cs.key})`;
    if (!sec) {
      html += tnode("sector", cs.key, esc(cs.label), "not tracked (yet)", { off: true, cls: "tsector", style: color });
      continue;
    }
    const open = view.sector === cs.key;
    html += tnode("sector", cs.key, esc(sec.label), paShort(sectorFiles(sec)), { on: open, cls: "tsector", style: color });
    if (!open) continue;
    html += `<div class="tkids">`;
    const names = [...new Set([...RUN_TYPE_ORDER, ...Object.keys(sec.run_types), ...(sec.disabled_run_types || [])])]
      .filter((k) => k in sec.run_types || (sec.disabled_run_types || []).includes(k) || RUN_TYPE_ORDER.includes(k));
    for (const k of names) {
      const rt = sec.run_types[k];
      const usable = rt && rt.units.length > 0;
      const why = !rt ? ((sec.disabled_run_types || []).includes(k) ? "not part of this sector" : "not run for this sector")
        : !usable ? "no files yet" : "";
      const here = view.runType === k;
      const hasModels = usable && gridKind(rt) === "gcms" && rt.dims.models.length > 1;
      html += tnode("run", k, esc(k), rt ? (usable ? paShort(filesOf(sec, rt)) : "no files yet") : "n/a",
        { on: here, off: !usable, leaf: usable && !hasModels, title: why });
      if (!here || !usable) continue;
      html += `<div class="tkids">`;
      if (hasModels) {
        const perModel = rt.counts.total / rt.dims.models.length;
        for (const m of rt.dims.models) {
          const units = rt.units.filter((u) => u.model === m);
          const n = paFiles(sec, units, perModel, [m], curScen());
          html += tnode("model", m, esc(m), units.length ? paShort({ proj: n.p, projExp: n.pExp, agg: n.a, aggExp: n.aExp }) : "no files yet",
            { on: view.model === m, off: !units.length, leaf: true, title: units.length ? "" : "no files yet" });
        }
      }
      // Aggregation scenarios, as the selector shows them.
      const sc = rt.agg_scenarios || { main: null, others: [] };
      const anyAgg = rt.units.some((u) => u.bits.slice(specOf(sec, u.model).projection.length).includes("1")
        || Object.values(u.alt_bits || {}).some((b) => b.includes("1")));
      if (!anyAgg) {
        // Nothing to pick yet: the branch stays folded.
        html += tnode("scen", "", "Aggregation", sc.main ? "none yet" : "-", { off: true, cls: "tfold", title: "no aggregation files yet" });
        html += `</div>`;
        continue;
      }
      html += `<div class="tgroup">Aggregation</div><div class="tkids">`;
      {
        const cur = curScen();
        const aggPct = (scen) => { const f = filesOf(sec, rt, scen); return f.aggExp ? `A ${fmtPctShort(pctOf(f.agg, f.aggExp))}` : ""; };
        html += tnode("scen", "", sc.main ? `${esc(sc.main)} <span class="muted">(main)</span>` : "main", aggPct(null), { on: !cur, leaf: true });
        for (const o of sc.others) html += tnode("scen", o, esc(scenLabel(o)), aggPct(o), { on: cur === o, leaf: true });
      }
      html += `</div></div>`;
    }
    html += `</div>`;
  }
  $("tree").innerHTML = html;

  // The current path, at the top of the grid and on the phone menu.
  const parts = [];
  if (view.sector) {
    const rt = runType(), sec = sector();
    parts.push(sec.label);
    if (view.runType) parts.push(view.runType);
    if (rt && gridKind(rt) === "gcms" && rt.dims.models.length > 1 && view.model) parts.push(view.model);
    const sc = rt && rt.agg_scenarios;
    const cur = curScen();
    if (cur) parts.push(scenLabel(cur));
    else if (sc && sc.main) parts.push(sc.main);
  }
  $("tree-path").textContent = parts.join(" / ");
  $("tree-summary").textContent = parts.length ? parts.join(" / ") : "Pick a sector";
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

function card(label, val, sub, bar, tip) {
  return `<div class="card"${tip ? ` title="${esc(tip)}"` : ""}><div class="card-label">${label}</div><div class="card-val">${val}</div>` +
    (bar || "") + (sub ? `<div class="card-sub">${sub}</div>` : "") + `</div>`;
}
function pbar(pct, color) {
  return `<div class="pbar"><div class="pbar-fill" style="width:${Math.min(pct, 100).toFixed(2)}%;background:${color}"></div></div>`;
}

// Time to finish the projections only, with the pace used in the tooltip.
const ETA_METHOD = {
  writing: "Pace: units being written now, at the time per unit.",
  recent: "Pace: projection units finished in the last 6 hours.",
};
function etaCard(rt, total) {
  if (rt.eta_method === undefined) return card("ETA", fmtEta(rt.eta_hours), rt.eta_basis ? esc(rt.eta_basis) : "");
  const val = rt.eta_hours === 0 ? "done" : rt.eta_hours == null ? `<span class="card-val-small">not enough data yet</span>` : fmtEta(rt.eta_hours);
  const ag = rt.aggregation || {};
  const sub = ag.started ? `projection only; aggregation ${fmtN(ag.done)}/${fmtN(total)} units, not estimated`
    : "projection only; aggregation not started";
  const tip = [rt.eta_basis, ETA_METHOD[rt.eta_method], rt.eta_method === "writing" ? UNIT_SOURCE[rt.unit_time_source] : null,
    sub[0].toUpperCase() + sub.slice(1)].filter(Boolean).join(". ");
  return card("Time to finish", val, sub, "", tip);
}

function renderCards() {
  const sec = sector(), rt = runType();
  const f = filesOf(sec, rt);
  const total = rt.counts.total;
  const pp = pctOf(f.proj, f.projExp), ap = pctOf(f.agg, f.aggExp);
  $("cards").innerHTML =
    card("Expected", fmtN(total), "units of work") +
    card(`Complete${mainMark()}`, `<span style="color:var(--st-done)">${fmtN(f.complete)}</span>`, "all files present") +
    card(`Partial${mainMark()}`, `<span style="color:var(--progress)">${fmtN(f.partial)}</span>`, "some files present") +
    card(`Not started${mainMark()}`, `<span style="color:var(--st-none)">${fmtN(total - f.started)}</span>`, "no files yet") +
    card("Projection", fmtPct2(pp), `${fmtN(f.proj)}/${fmtN(f.projExp)} files`, pbar(pp, "var(--base)")) +
    card(`Aggregation${mainMark()}`, fmtPct2(ap), `${fmtN(f.agg)}/${fmtN(f.aggExp)} files`, pbar(ap, "var(--agg)")) +
    card("Writing", `<span style="color:var(--st-run)">${fmtN(f.running)}</span>`, f.failed ? `${fmtN(f.failed)} stopped` : "units being written") +
    etaCard(rt, total) +
    suCard(rt.su_estimate);
}

// Where the time per unit came from, for the tooltips.
const UNIT_SOURCE = {
  sacct: "Time per unit from sacct (elapsed time × billing of the run's tasks).",
  "file dates": "Time per unit from file dates, plus the start up time measured from the singles.",
  reference: "Time per unit from the reference in the manifest; not enough finished units yet.",
};
// SUs to finish with RCC's billing formula, and the compute hours under it.
function suCard(e) {
  const info = infoPop("About the SUs", "SUs = hours × max(cores requested, RAM requested ÷ RAM per core), " +
    "on the partitions RCC bills (now caslake, 3.75 GB per core); other partitions are 0 SUs.");
  const label = `SUs to finish${info}`;
  if (!e) return card(label, "n/a", "");
  const tip = [e.basis, UNIT_SOURCE[e.source]].filter(Boolean).join(". ");
  const compute = e.compute_low == null ? "compute hours not known yet" : `${hRange(e.compute_low, e.compute_high)} compute`;
  const val = e.su_low == null ? (e.compute_low == null ? "not known yet" : "request not known") : suRange(e.su_low, e.su_high);
  return card(label, val, esc(compute), "", tip);
}
function hRange(low, high) {
  const f = (n) => fmtSU(n).replace(/ SU$/, "");
  return low === high ? `${f(low)} h` : `${f(low)} to ${f(high)} h`;
}

// P and A per scenario cell (SSP, RCP, IAM), added up in one pass over the
// run's units and kept until the next scan, sub-model or aggregation pick.
const statsCache = new Map();
function cellStats(rt, sec, models, scen) {
  const sig = [view.sector, view.runType, models.join(","), scen || "", DATA.generated_at].join("#");
  if (statsCache.has(sig)) return statsCache.get(sig);
  const out = new Map();
  const per = rt.dims.batches || 1;
  for (const c of rt.dims.cells) {
    let pExp = 0, aExp = 0;
    for (const m of models) {
      const spec = specOf(sec, m);
      pExp += rt.dims.gcms[c.rcp].length * per * spec.projection.length;
      aExp += rt.dims.gcms[c.rcp].length * per * groupTotal(spec, AGG_GROUPS);
    }
    out.set(`${c.ssp}|${c.rcp}|${c.iam}`, { p: 0, pExp, a: 0, aExp });
  }
  for (const u of rt.units) {
    if (!models.includes(u.model)) continue;
    const t = out.get(`${u.ssp}|${u.rcp}|${u.iam}`);
    if (!t) continue;
    const c = unitCounts(u, specOf(sec, u.model), scen);
    t.p += c.proj;
    t.a += c.agg;
  }
  statsCache.set(sig, out);
  return out;
}
// SSP, RCP and IAM badges in three rows under the sector list. Each badge
// turns on or off on its own; the grid shows the columns whose SSP, RCP and
// IAM are all on. Built once per run; a click only switches the badge and
// the grid's columns.
function cellOn(c) {
  const p = view.picks;
  return !!p && p.ssp.includes(c.ssp) && p.rcp.includes(c.rcp) && p.iam.includes(c.iam);
}

function renderSspTabs() {
  const rt = runType();
  const uniq = (f) => [...new Set(rt.dims.cells.map((c) => c[f]))];
  const all = { ssp: uniq("ssp"), rcp: uniq("rcp"), iam: uniq("iam") };
  // A newly picked run type starts with every SSP, RCP and IAM on.
  if (!view.picks) view.picks = { ssp: all.ssp.slice(), rcp: all.rcp.slice(), iam: all.iam.slice() };
  view.ssps = view.picks.ssp.slice();
  const box = $("scen-graph");
  const sig = [view.sector, view.runType, DATA.generated_at].join("#");
  if (box.dataset.sig !== sig) {
    box.dataset.sig = sig;
    const cls = { ssp: (v) => `ssp-${v}`, rcp: (v) => `sb-${v}`, iam: (v) => `sb-iam sb-iam-${v}` };
    box.innerHTML = ["ssp", "rcp", "iam"].map((f) => `<div class="sb-row">` + all[f].map((v) =>
      `<button class="sb ${cls[f](v)}" data-f="${f}" data-v="${esc(v)}" aria-pressed="false">${esc(v)}</button>`).join("") + `</div>`).join("") +
      `<div class="sb-note">Select a full combination of at least one SSP, one emissions scenario and one IAM.</div>` +
      (all.iam.some((v) => v === "low" || v === "high") ? `<div class="sb-note">low: IIASA, high: OECD</div>` : "");
  }
  for (const b of box.querySelectorAll(".sb")) {
    const on = view.picks[b.dataset.f].includes(b.dataset.v);
    b.classList.toggle("on", on);
    b.setAttribute("aria-pressed", String(on));
  }
}

// Highlight by state: the grid stays whole, and cells of other states are
// shown blank so the matching ones stand out.
const HIGHLIGHTS = [["all", "All"], ["complete", "Complete"], ["incomplete", "Incomplete"],
  ["projdone", "Projection complete"], ["projmiss", "Projection incomplete"],
  ["writing", "Being written"], ["failed", "Failed"], ["notstarted", "Not started"]];
// The last two look at the projection files only, whatever the aggregation.
// Units are counted by their files, the same way as the summary cards:
// complete, incomplete and not started add up to all, and so do the two
// projection options. Being written and failed follow the unit's state.
function cellMatches(hl, unit, cnt) {
  const started = cnt.proj + cnt.agg > 0;
  const done = started && cnt.proj >= cnt.projTotal && cnt.agg >= cnt.aggTotal;
  switch (hl) {
    case "all": return true;
    case "complete": return done;
    case "incomplete": return started && !done;
    case "notstarted": return !started;
    case "writing": return !!unit && unit.state === "running";
    case "failed": return !!unit && unit.state === "failed";
    case "projdone": return cnt.projTotal > 0 && cnt.proj >= cnt.projTotal;
    case "projmiss": return cnt.proj < cnt.projTotal;
  }
  return false;
}
function renderHighlight(counts) {
  $("hl-tabs").innerHTML = HIGHLIGHTS.map(([k, label]) =>
    `<button class="hl-opt${view.hl === k ? " active" : ""}" data-hl="${k}"><span class="hl-lbl">${label}</span>` +
    `<span class="muted">${fmtN(counts[k] || 0)}</span></button>`).join("");
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
     <div class="leg-item" title="All projection and aggregation files present">${box("border:1.5px solid color-mix(in srgb, var(--st-done) 55%, transparent);background:var(--st-done-bg)")} Aggregation complete</div>
     <span class="leg-sep">|</span>
     <span style="font-weight:500">Aggregation:</span>
     ${aggTypes(sector()).map((g) => `<span style="color:var(--agg-${AGG_STYLE[g].v})">${AGG_STYLE[g].label}</span>`).join(" ")}`;
}

// A cell's file squares as one small picture instead of one element per file,
// cached by pattern and theme: most cells share the same few patterns, and
// the grid stays light enough to show and hide columns quickly.
const SQ = { size: 4, gap: 0.5, cols: 4 };
const sqCache = new Map();
let sqColors = null;
function squares(pres, groups) {
  if (!sqColors) {
    const css = getComputedStyle(document.documentElement);
    const v = (name) => css.getPropertyValue(name).trim();
    sqColors = { miss: v("--miss"), projection: v("--base"), costs: v("--agg-cost"), levels: v("--agg-lvl"), aggregated: v("--agg-agg") };
  }
  const fills = groups.flatMap((g) => pres[g].map((on) => (on ? sqColors[g] : sqColors.miss)));
  const key = fills.join(",");
  let img = sqCache.get(key);
  if (!img) {
    const rows = Math.ceil(fills.length / SQ.cols), step = SQ.size + SQ.gap;
    const w = SQ.cols * step - SQ.gap, h = rows * step - SQ.gap;
    const rects = fills.map((f, i) => `<rect x="${(i % SQ.cols) * step}" y="${Math.floor(i / SQ.cols) * step}" width="${SQ.size}" ` +
      `height="${SQ.size}" rx="0.5" fill="${f}"/>`).join("");
    const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="${w}" height="${h}" viewBox="0 0 ${w} ${h}">${rects}</svg>`;
    img = `<i class="sq-img" style="width:${w}px;height:${h}px;background-image:url('data:image/svg+xml,${encodeURIComponent(svg)}')"></i>`;
    sqCache.set(key, img);
  }
  return img;
}

function cellHtml(key, unit, spec, hlCounts) {
  const cnt = unitCounts(unit, spec, curScen());
  const cls = cellState(unit, cnt);
  const states = HIGHLIGHTS.map(([k]) => k).filter((k) => cellMatches(k, unit, cnt));
  if (hlCounts) for (const k of states) hlCounts[k] = (hlCounts[k] || 0) + 1;
  let html = `<div class="batch ${cls}" data-key="${esc(key)}" data-st="${states.join(" ")}">`;
  html += `<div class="batch-row">${squares(cnt.pres, ["projection"])}` +
    (cnt.proj ? `<span class="row-count proj">${cnt.proj}/${cnt.projTotal}</span>` : "") + `</div>`;
  if (cnt.aggTotal) {
    html += `<div class="batch-sep"></div><div class="batch-row">${squares(cnt.pres, AGG_GROUPS)}` +
      (cnt.agg ? `<span class="row-count agg">${cnt.agg}/${cnt.aggTotal}</span>` : "") + `</div>`;
  }
  return html + `</div>`;
}

// The grid is built once per run with every scenario column. Turning cards
// on and off only rewrites one style rule that hides columns, and a
// highlight only sets an attribute on the table.
let gridCols = { keys: [], hl: new Map() };
function renderGrid() {
  const sec = sector(), rt = runType();
  const kind = gridKind(rt);
  const batches = rt.dims.batches ? [...Array(rt.dims.batches).keys()] : [null];
  const cells = rt.dims.cells;
  const byKey = new Map(rt.units.map((u) => [[u.model, u.ssp, u.rcp, u.iam, u.gcm, u.batch ?? ""].join("|"), u]));
  cellIndex = new Map();

  const rows = kind === "gcms" ? gcmUnion(rt.dims.gcms) : rt.dims.models;
  const fixedModel = kind === "gcms" ? (view.model || rt.dims.models[0]) : null;
  const stats = cellStats(rt, sec, fixedModel ? [fixedModel] : rt.dims.models, curScen());
  const edge = (rcp, i, n) => {
    const t = rcp === "rcp45" ? "45" : "85";
    return (i === 0 ? ` edge-l${t}` : "") + (i === n - 1 ? ` edge-r${t}` : "");
  };
  const ck = (c) => `${c.ssp}|${c.rcp}|${c.iam}`;
  gridCols = { keys: cells.map(ck), hl: new Map(cells.map((c) => [ck(c), {}])) };

  let h1 = `<thead><tr><th class="model-th">${kind === "gcms" ? "Climate model" : "Sub-model"}</th>`;
  let h2 = `<tr><th class="model-th sub">${batches[0] != null ? "batch" : ""}</th>`;
  cells.forEach((c) => {
    const k = esc(ck(c));
    h1 += `<th class="sep-col" data-c="${k}"></th>`; h2 += `<th class="sep-col" data-c="${k}"></th>`;
    const n = stats.get(ck(c));
    h1 += `<th colspan="${batches.length}" class="sc-hdr sc-hdr-${c.rcp}" data-c="${k}"><span class="hb-row">` +
      `<span class="sb on hb ssp-${esc(c.ssp)}">${esc(c.ssp)}</span><span class="sb on hb sb-${esc(c.rcp)}">${esc(c.rcp)}</span>` +
      `<span class="sb on hb sb-iam sb-iam-${esc(c.iam)}">${esc(c.iam)}</span></span>` +
      // Columns of one or two cells are too narrow for the counts: they go in the tooltip.
      `<span class="sc-count" title="${paText(n)}">${paText(n, batches.length < 3)}</span></th>`;
    batches.forEach((b, bi) => {
      h2 += `<th class="sub${edge(c.rcp, bi, batches.length)}" data-c="${k}">${b != null ? "b" + b : (kind === "gcms" ? "" : rt.dims.gcms[c.rcp][0])}</th>`;
    });
  });
  h1 += `</tr>`; h2 += `</tr></thead>`;

  let body = "<tbody>";
  for (const row of rows) {
    const label = kind === "gcms" ? row.replace("surrogate_", "surr_") : row;
    body += `<tr><td class="model-cell" title="${esc(row)}">${esc(label)}</td>`;
    cells.forEach((c) => {
      const k = ck(c);
      body += `<td class="sep-col" data-c="${esc(k)}"></td>`;
      batches.forEach((b, bi) => {
        const model = fixedModel || row;
        const gcm = kind === "gcms" ? row : rt.dims.gcms[c.rcp][0];
        const cls = `sc-cell${edge(c.rcp, bi, batches.length)}`;
        if (!rt.dims.gcms[c.rcp].includes(gcm)) { body += `<td class="${cls}" data-c="${esc(k)}"></td>`; return; }
        const key = [model, c.ssp, c.rcp, c.iam, gcm, b ?? ""].join("|");
        const unit = byKey.get(key) || null;
        cellIndex.set(key, { unit, model, ssp: c.ssp, rcp: c.rcp, iam: c.iam, gcm, batch: b });
        body += `<td class="${cls}" data-c="${esc(k)}">${cellHtml(key, unit, specOf(sec, model), gridCols.hl.get(k))}</td>`;
      });
    });
    body += `</tr>`;
  }
  crossCells = [];
  $("grid").innerHTML = h1 + h2 + body + "</tbody>";
  $("grid").dataset.hl = view.hl;
  applyColumns();
  if (view.selected) {
    const el = document.querySelector(`.batch[data-key="${CSS.escape(view.selected)}"]`);
    if (el) el.classList.add("selected");
    crossHighlight(el);
  }
}

// Shows the columns whose SSP, RCP and IAM are on, by one style rule, and
// updates the highlight counts for them.
function applyColumns() {
  let style = $("col-style");
  if (!style) { style = document.createElement("style"); style.id = "col-style"; document.head.appendChild(style); }
  const cells = runType().dims.cells;
  const shown = cells.filter(cellOn).map((c) => `${c.ssp}|${c.rcp}|${c.iam}`);
  const hidden = gridCols.keys.filter((k) => !shown.includes(k));
  style.textContent = hidden.map((k) => `#grid [data-c="${CSS.escape(k)}"]`).join(",") + (hidden.length ? "{display:none}" : "");
  // The first shown column needs no separator before it.
  if (shown.length) style.textContent += `#grid .sep-col[data-c="${CSS.escape(shown[0])}"]{display:none}`;
  const grid = $("grid");
  grid.classList.toggle("no-cols", !shown.length);
  $("grid-empty").classList.toggle("hidden", !!shown.length);
  const counts = {};
  for (const k of shown) for (const [st, n] of Object.entries(gridCols.hl.get(k) || {})) counts[st] = (counts[st] || 0) + n;
  renderHighlight(counts);
  fitGrid();
}

// The grid shrinks to fit the screen width, down to GRID_MIN_ZOOM; wider
// grids (montecarlo) scroll sideways inside their own box.
const GRID_MIN_ZOOM = 0.6;
function fitGrid() {
  const wrap = document.querySelector(".grid-wrap"), table = $("grid");
  table.style.zoom = "";
  const head = table.tHead && table.tHead.rows[0];
  if (head) table.style.setProperty("--hdr1", `${head.getBoundingClientRect().height}px`);
  const avail = wrap.clientWidth, natural = table.offsetWidth;
  if (!avail || !natural || natural <= avail) return;
  // One measure and one zoom: thin borders do not shrink with the zoom, so
  // leave a little room for them instead of stepping down in a loop.
  table.style.zoom = String(Math.max(GRID_MIN_ZOOM, Math.floor((avail / natural) * 985) / 1000));
}

// Softly marks the row and column of a cell, with its row label and its
// column and scenario headers.
let crossCells = [];
function crossHighlight(batch) {
  crossCells.forEach((el) => el.classList.remove("xh"));
  crossCells = [];
  if (!batch) return;
  const td = batch.closest("td"), tr = td.parentElement, table = $("grid");
  const col = td.cellIndex;
  crossCells.push(...tr.cells);
  for (const row of table.tBodies[0].rows) if (row.cells[col]) crossCells.push(row.cells[col]);
  const [h1, h2] = table.tHead.rows;
  if (h2 && h2.cells[col]) crossCells.push(h2.cells[col]);
  if (h1) {
    let at = 0;
    for (const th of h1.cells) {
      if (col >= at && col < at + th.colSpan) { crossCells.push(th); break; }
      at += th.colSpan;
    }
  }
  crossCells.forEach((el) => el.classList.add("xh"));
}
function selectedBatch() {
  return view.selected ? document.querySelector(`.batch[data-key="${CSS.escape(view.selected)}"]`) : null;
}

/* ---------- detail panel ---------- */

function cellPath(info) {
  const rt = runType();
  const parts = [];
  if (rt.model_dirs) parts.push(rt.model_dirs[info.model]);
  else {
    parts.push(rt.root);
    if (info.model !== "main") parts.push(info.model);
    if (rt.subdir) parts.push(rt.subdir);
  }
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
    `<span class="meta">${fmtSize(rec[0])}</span><span class="meta">${fmtWhen(rec[1] * 1000, true)}</span></div>`;
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
  crossHighlight(el);

  const sec = sector();
  const spec = specOf(sec, info.model);
  // The aggregation files shown are those of the scenario picked in the selector.
  const scen = curScen();
  const cnt = unitCounts(info.unit, spec, scen);
  const path = cellPath(info);
  $("info-bar").textContent = `${cellTitle(info)}  ${cnt.proj}/${cnt.projTotal} projection, ${cnt.agg}/${cnt.aggTotal} aggregation`;
  $("info-bar").title = path;

  const box = $("file-detail");
  box.className = "file-detail";
  box.innerHTML = `<div class="fd-note">Loading file sizes and dates</div>`;
  const details = cnt.proj + cnt.agg ? await loadDetails(info.model, info.batch) : {};
  if (view.selected !== key) return;
  const cellKey = [info.ssp, info.rcp, info.iam, info.gcm].join("|");
  let recs = details[cellKey] || [];
  if (scen) {
    const nProj = spec.projection.length;
    recs = [...(recs.length ? recs.slice(0, nProj) : new Array(nProj).fill(0)), ...(details[`${scen}#${cellKey}`] || [])];
  }
  let i = 0;
  const byGroup = {};
  for (const g of GROUPS) byGroup[g] = spec[g].map((n) => ({ name: g === "projection" ? n : scenName(n, info, scen), rec: recs[i++] || null }));
  const rows = (g) => byGroup[g].map((f) => fileRow(g, f.name, f.rec)).join("");
  const found = (g) => byGroup[g].filter((f) => f.rec).length;

  const state = STATE_NAMES[cellState(info.unit, cnt)];
  const reason = info.unit && info.unit.fail_reason ? `, ${esc(info.unit.fail_reason)}` : "";
  // The arrow folds the panel; the red button closes it.
  let html = `<div class="fd-head">
      <span class="fd-title">${esc(cellTitle(info))}: ${cnt.proj}/${cnt.projTotal} projection
      | <span class="agg-count">${cnt.agg}/${cnt.aggTotal} aggregation</span>
      <span class="state">${esc(state)}${reason}</span>${scen ? ` <span class="state">aggregation: ${esc(scen.replace("{rcp}", info.rcp))}, not counted</span>` : ""}</span>
      <button class="fd-fold" id="fd-fold" aria-expanded="${!fdFolded}" aria-label="Fold" title="Fold or open"><span class="panel-arrow">&gt;</span></button>
      <button class="fd-close" id="fd-close" aria-label="Close" title="Close (Esc)">` +
      `<svg viewBox="0 0 12 12" width="6" height="6" aria-hidden="true"><path d="M2 2l8 8M10 2l-8 8" stroke="currentColor" stroke-width="2" stroke-linecap="round"/></svg></button></div>
    <div class="fd-root">${esc(path)}</div>`;
  // Files in the folder that are not expected: listed under the projection
  // files, never counted.
  const extra = details[`extra#${cellKey}`] || [];
  const extraHtml = extra.length ? `<div class="fd-sub fd-sub-other">Other files (not counted) (${extra.length})</div>` +
    extra.map(([name, size, mtime]) => fileRow("other", name, [size, mtime])).join("") : "";
  html += section("fd-proj", "Projections", `${found("projection")}/${spec.projection.length}`, rows("projection") + extraHtml, true);
  const aggParts = ["levels", "aggregated"].filter((g) => spec[g].length);
  if (aggParts.length) {
    const sub = aggParts.map((g) => `<div class="fd-sub" style="color:var(--agg-${g === "levels" ? "lvl" : "agg"})">` +
      `${g === "levels" ? "Levels" : "Aggregated"} (${found(g)}/${spec[g].length})</div>${rows(g)}`).join("");
    const n = aggParts.reduce((s, g) => s + found(g), 0), t = aggParts.reduce((s, g) => s + spec[g].length, 0);
    html += section("fd-agg", "Aggregation", `${n}/${t}`, sub, true);
  }
  if (spec.costs.length) {
    html += section("fd-costs", "Costs", `${found("costs")}/${spec.costs.length}`, rows("costs"), false);
  }
  box.innerHTML = html;
  box.classList.toggle("fd-folded", fdFolded);
  $("fd-close").onclick = closeDetail;
  $("fd-fold").onclick = foldDetail;
}

// Folded or open, kept while other cells are picked.
let fdFolded = false;
function foldDetail() {
  fdFolded = !fdFolded;
  $("file-detail").classList.toggle("fd-folded", fdFolded);
  const b = $("fd-fold");
  if (b) b.setAttribute("aria-expanded", String(!fdFolded));
}

function closeDetail() {
  view.selected = null;
  const box = $("file-detail");
  box.className = "";
  box.innerHTML = "";
  $("info-bar").textContent = "Click or tap a cell to see its files";
  $("info-bar").title = "";
  document.querySelectorAll(".batch.selected").forEach((e) => e.classList.remove("selected"));
  crossHighlight(null);
}

/* ---------- resources ---------- */

function barColor(pct) {
  if (pct == null) return "var(--bd2)";
  return pct >= 90 ? "var(--red)" : pct >= 70 ? "var(--amber)" : "var(--green)";
}

function resRow(label, pct, counts, tip, countsOnly, extra) {
  const col = barColor(pct);
  const p = Math.min(pct == null ? 0 : pct, 100);
  return `<div class="res-row"${tip ? ` title="${esc(tip)}"` : ""}><span class="res-label">${esc(label)}</span>` +
    `<span class="res-bar"><span class="fill" style="width:${p.toFixed(1)}%;background:${col}"></span><span class="ticks"></span></span>` +
    (countsOnly ? `<span class="res-counts res-only">${esc(counts)}</span>${extra || ""}</div>` :
      `<span class="res-pct" style="color:${col}">${fmtPct2(pct)}</span><span class="res-counts">${esc(counts)}</span></div>`);
}

// Sizes such as "500.00T" lose the zeros after the point ("500T", "118.1T").
function trimSize(text) {
  return String(text ?? "").replace(/^(\d+)\.(\d*?)0+([A-Za-z]*)$/, (m, i, d, u) => `${i}${d ? "." + d : ""}${u}`);
}

function renderResources() {
  const a = DATA.account;
  let storage;
  if (a.storage == null) storage = `<div class="res-note muted">Not available in this scan</div>`;
  else if (!a.storage.length) storage = `<div class="res-note muted">No group storage found</div>`;
  else storage = a.storage.map((s) => resRow(s.label, s.used_pct, `${trimSize(s.used)} / ${trimSize(s.quota)}`,
    `Used ${trimSize(s.used)} of ${trimSize(s.quota)}`)).join("");

  $("resources-content").innerHTML =
    `<div class="res-sec"><div class="res-title">Storage</div>${storage}</div>` +
    `<div class="res-sec"><div class="res-title">Service units</div>${serviceUnitsHtml()}</div>` +
    `<div class="res-foot">${fmtWhen(DATA.generated_at, true)}</div>`;
}

// Service units, RCC's official numbers only: the total from rcchelp
// balance, and the billed use per user and per partition from rcchelp
// usage. RCC gives no user by partition, so those are separate bars.
function infoPop(title, text) {
  return `<span class="info-wrap"><button class="info-btn" aria-expanded="false" title="${esc(title)}">i</button>` +
    `<span class="su-pop hidden" role="dialog">${text}</span></span>`;
}

// One bar of billed use: a segment and a key entry per name with use.
function billedBar(box, title, part, segStyle, keyMark) {
  let html = `<div class="su-est su-blocks" data-box="${box}">`;
  if (!part) {
    return html + `<div class="su-bar-block"><div class="su-est-head">${title}
      <span class="lbl">not available in this scan</span></div></div></div>`;
  }
  const rows = Object.entries(part.by).filter(([, v]) => v > 0).sort((x, y) => y[1] - x[1]);
  const sum = rows.reduce((n, [, v]) => n + v, 0) || 1;
  const attr = box === "users" ? "data-user" : "data-part";
  const bar = rows.map(([n, v]) => `<span class="seg ${segStyle(n).cls}" ${attr}="${esc(n)}"
      style="width:${((100 * v) / sum).toFixed(2)}%;${segStyle(n).style}" title="${esc(n)}: ${fmtN(v)} SU"></span>`).join("");
  html += `<div class="su-bar-block"><div class="su-est-head">${title}</div>
    <div class="su-bar-all">${bar}</div></div>`;
  html += `<div class="ukey ukey-left">` + (rows.length ? [...rows].sort((x, y) => x[0].localeCompare(y[0])).map(([n, v]) =>
    `<span class="ukey-item" ${attr}="${esc(n)}">${keyMark(n)}${box === "users" ? userName(n) : esc(n)}
      <span class="mono">${fmtN(v)} SU, ${fmtPctShort((100 * v) / sum)}</span></span>`).join("")
    : `<span class="lbl">no billed use yet</span>`) + `</div>`;
  return html + `</div>`;
}

function serviceUnitsHtml() {
  const a = DATA.account;
  let html;
  if (a.allocation_status === "ok") {
    const pct = a.allocation_su ? (100 * a.used_su) / a.allocation_su : null;
    html = resRow("Total", pct, `${fmtN(a.used_su)} / ${fmtN(a.allocation_su)} SU, ${fmtN(a.balance_su)} left`,
      `Used ${fmtN(a.used_su)} SU of ${fmtN(a.allocation_su)}, ${fmtN(a.balance_su)} SU left`, true,
      infoPop("About these numbers", "RCC's official numbers, updated by RCC in batches, so the newest jobs may not show yet."));
  } else {
    const note = a.allocation_status === "none" ? "no allocation listed" : "not available in this scan";
    html = `<div class="res-row"><span class="res-label">Total</span>` +
      `<span class="res-bar placeholder"><span class="ticks"></span></span>` +
      `<span class="res-counts res-only">${esc(note)}</span></div>`;
  }
  const billed = a.billed || {};
  html += billedBar("users", "Per user", billed.by_user,
    (u) => ({ cls: "", style: `background-color:${userColor(u)}` }),
    (u) => `<span class="udot" style="background:${userColor(u)}"></span>`);
  html += billedBar("parts", "Per partition", billed.by_partition,
    (p) => ({ cls: `pbar-seg ${partTexture(p)}`, style: "" }),
    (p) => partSwatch(p));
  return html;
}

// The bar and its key highlight each other. A selection is a user,
// a partition, or both (one segment); hovering shows it and a click keeps it
// until the same thing is clicked again.
const suPicked = {};
function suSelection(el) {
  if (!el) return null;
  return { user: el.dataset.user || null, part: el.dataset.part || null };
}
function suHighlight(box, sel) {
  if (!box) return;
  const hit = (el) => !!sel && (el.dataset.part
    ? (!sel.user || el.dataset.user === sel.user) && (!sel.part || el.dataset.part === sel.part)
    : !!sel.user && el.dataset.user === sel.user);
  box.classList.toggle("has-hl", !!sel);
  box.querySelectorAll(".seg").forEach((el) => el.classList.toggle("hl", hit(el)));
  box.querySelectorAll(".ukey-item[data-user]").forEach((el) => el.classList.toggle("hl", !!sel && el.dataset.user === sel.user));
  box.querySelectorAll(".ukey-item[data-part]").forEach((el) => el.classList.toggle("hl", !!sel && el.dataset.part === sel.part));
}

/* ---------- SLURM jobs ---------- */

const END_CLASS = { timeout: "end-timeout", "out of memory": "end-oom", failed: "end-failed",
  "node failure": "end-failed", cancelled: "end-cancelled" };

// Recent jobs that ended badly, in a group that starts collapsed.
function endedBadlyHtml() {
  const rows = DATA.ended_badly;
  if (rows == null) return "";
  const days = DATA.ended_badly_days || 3;
  const kinds = {};
  for (const r of rows) kinds[r.ended] = (kinds[r.ended] || 0) + 1;
  const summary = Object.keys(kinds).map((k) => `<span class="${END_CLASS[k] || ""}">${fmtN(kinds[k])} ${esc(k)}</span>`).join(", ");
  const head = `<div class="grp-header"><span><span class="grp-arrow">&gt;</span> Ended badly, last ${days} days
    <span class="grp-counts">${rows.length ? `${fmtN(rows.length)} ${rows.length === 1 ? "job" : "jobs"}: ${summary}` : "none"}</span></span></div>`;
  if (!rows.length) return `<div class="grp bad-jobs">${head}<div class="grp-body"><div class="jobs-empty">No jobs ended badly</div></div></div>`;
  const table = `<div class="table-scroll"><table class="jobs-table"><tr><th>Job ID</th><th>Name</th><th>User</th><th>Partition</th><th>How it ended</th>
      <th class="r">Elapsed</th></tr>` + rows.map((r) => `<tr title="${r.end ? `Ended ${esc(fmtWhen(r.end, true))}` : ""}">
      <td class="mono">${esc(r.job_id)}${r.tasks > 1 ? ` <span class="lbl">(${fmtN(r.tasks)} tasks)</span>` : ""}</td>
      <td>${esc(r.job_name)}</td>
      <td><span class="ukey-item"><span class="udot" style="background:${userColor(r.user)}"></span>${userName(r.user)}</span></td>
      <td>${partPill(r.partition)}</td>
      <td class="${END_CLASS[r.ended] || ""}">${esc(r.ended[0].toUpperCase() + r.ended.slice(1))}</td>
      <td class="r">${r.elapsed_min ? fmtMin(r.elapsed_min) : "did not start"}</td></tr>`).join("") + `</table></div>`;
  return `<div class="grp bad-jobs">${head}<div class="grp-body">${table}</div></div>`;
}

function partPill(name, n) {
  return `<span class="part-pill">${partSwatch(name)}${esc(name)}${n != null ? ` <span class="mono">${fmtN(n)}</span>` : ""}</span>`;
}

// Each partition a job may use, once, with its running tasks: running ones
// first, by count, then the ones it may use but has nothing on yet.
function jobPartitions(j) {
  const on = j.running_on || {};
  const rest = j.partition.split(",").filter((p) => p && !(p in on));
  return [...Object.entries(on).map(([p, n]) => partPill(p, n)), ...rest.map((p) => partPill(p))].join("");
}

// Task counts as small letter badges: R running, P pending, D done, F failed.
const TASK_BADGES = [["running", "R", "running"], ["queued", "P", "pending"], ["done", "D", "done"], ["failed", "F", "failed"]];
function taskBadges(t, keys) {
  const out = TASK_BADGES.filter(([k]) => (!keys || keys.includes(k)) && t[k])
    .map(([k, letter, word]) => `<span class="tb tb-${letter.toLowerCase()}" title="${fmtN(t[k])} ${word}">${letter} ${fmtN(t[k])}</span>`);
  return out.length ? `<span class="tbs">${out.join("")}</span>` : `<span class="lbl">none</span>`;
}
function sumTasks(jobs) {
  const t = { running: 0, queued: 0, done: 0, failed: 0 };
  for (const j of jobs) for (const k of Object.keys(t)) t[k] += j.tasks[k] || 0;
  return t;
}

// Time left under this many minutes shows in amber.
const LEFT_WARN_MIN = 120;

function renderJobs() {
  const groups = (DATA.users || []).map((u) => ({ name: u.user, jobs: u.active_jobs }));
  const known = DATA.users != null && DATA.users.some((u) => u.active_jobs != null);
  const jobs = groups.flatMap((g) => (g.jobs || []).map((j) => ({ ...j, person: g.name })));
  const run = jobs.reduce((n, j) => n + j.tasks.running, 0);
  const pend = jobs.reduce((n, j) => n + j.tasks.queued, 0);
  $("badge-run").textContent = `${fmtN(run)} running`;
  $("badge-pend").textContent = `${fmtN(pend)} pending`;

  if (!known) {
    $("jobs-content").innerHTML = `<div class="jobs-empty">Jobs not available in this scan</div>` + endedBadlyHtml();
    return;
  }

  // Live tasks per partition; a pending job that may run on several
  // partitions counts on the first one.
  const parts = {};
  for (const j of jobs) {
    const p = j.partition.split(",")[0];
    const t = (parts[p] = parts[p] || { running: 0, queued: 0 });
    t.running += j.tasks.running;
    t.queued += j.tasks.queued;
  }
  const live = ["running", "queued"];
  let html = `<div class="jobs-line">${fmtN(jobs.length)} ${jobs.length === 1 ? "job" : "jobs"}
    (${fmtN(run + pend)} tasks) ${taskBadges({ running: run, queued: pend }, live)}
    ${Object.keys(parts).length ? `<span class="lbl" style="margin-left:10px">Partitions</span> ` +
      Object.keys(parts).sort().map((p) => `<span class="part-pill">${partSwatch(p)}${esc(p)} ${taskBadges(parts[p], live)}</span>`).join(" ") : ""}</div>`;

  const always = DATA.account.always_show_users || [];
  const shown = groups.filter((g) => (g.jobs && g.jobs.length) || always.includes(g.name) || g.name === DATA.account.highlight_user);
  if (shown.length) {
    html += `<div class="jobs-line"><span class="lbl">Users</span> ` + shown.map((g) => {
      const js = g.jobs || [];
      return `<span class="juser"><span class="udot" style="background:${userColor(g.name)}"></span> <b>${userName(g.name)}</b> ` +
        (js.length ? taskBadges(sumTasks(js), live) : `<span class="lbl">no jobs</span>`) + `</span>`;
    }).join("") + `</div>`;
  }

  const a = DATA.account;

  // Every running or queued job, one row per job or array.
  if (!jobs.length) {
    html += `<div class="jobs-empty">No jobs on the ${esc(a.name)} account right now</div>`;
  } else {
    const order = [...jobs].sort((x, y) => (x.state !== "RUNNING") - (y.state !== "RUNNING") || y.elapsed_min - x.elapsed_min);
    html += `<div class="tb-key">` + TASK_BADGES.map(([, letter, word]) =>
      `<span class="tb tb-${letter.toLowerCase()}">${letter}</span> ${word}`).join(`<span class="tb-key-sep"></span>`) + ` <span class="lbl">(tasks)</span></div>`;
    html += `<div class="table-scroll"><table class="jobs-table"><tr><th>Job ID</th><th>Name</th><th>User</th>
      <th title="Running tasks on each partition">Partition</th><th>State</th>
      <th>Tasks</th><th class="r" title="When the first task started">Started</th><th class="r">Elapsed</th>
      <th class="r" title="Per task">CPUs</th><th class="r" title="Per task">Memory</th>
      <th class="r">Time limit</th><th class="r">Time left</th></tr>` +
      order.map((j) => `<tr><td class="mono">${esc(j.job_id || "")}</td><td>${esc(j.job_name)}</td>
        <td><span class="ukey-item"><span class="udot" style="background:${userColor(j.person)}"></span>${userName(j.person)}</span></td>
        <td>${jobPartitions(j)}</td>
        <td class="${j.state === "RUNNING" ? "state-run" : "state-pend"}">${j.state === "RUNNING" ? "Running" : "Pending"}</td>
        <td>${taskBadges(j.tasks)}</td>
        <td class="r">${j.started ? fmtWhen(j.started) : ""}</td>
        <td class="r">${j.state === "RUNNING" ? fmtMin(j.elapsed_min) : ""}</td>
        <td class="r">${j.cpus != null ? fmtN(j.cpus) : ""}</td>
        <td class="r">${esc(j.mem || "")}</td>
        <td class="r">${j.limit_min != null ? fmtMin(j.limit_min) : ""}</td>
        <td class="r${j.left_min != null && j.left_min < LEFT_WARN_MIN ? " time-short" : ""}"${j.left_min != null && j.left_min < LEFT_WARN_MIN ? ' title="Under 2 hours left before the time limit"' : ""}>${j.left_min != null ? fmtMin(j.left_min) : ""}</td></tr>`).join("") + `</table></div>`;
  }
  html += endedBadlyHtml();
  $("jobs-content").innerHTML = html;
}

/* ---------- camel ---------- */

// The camel has 100 pieces per sector (camel/camel.svg), filled from the
// bottom up. A sector fills with its share of projection files, pulses
// while projections run, turns solid when they are all there, and gets a
// fine texture when aggregation is complete too.
// In CAMEL order: Coastal, Agriculture, Mortality, Energy, Labor.
const CAMEL_SECTIONS = [
  { key: "coastal", label: "Coastal", part: "back and humps" },
  { key: "agriculture", label: "Agriculture", part: "hindquarters, back legs and tail" },
  { key: "mortality", label: "Mortality", part: "shoulder and front legs" },
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
    return { ...s, tracked: true, proj, agg, files: f, projDone: proj >= 100, allDone: proj >= 100 && agg >= 100,
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

  // A compact table: one row per sector in camel order, its mark on the left
  // (softly pulsing in its color while the sector is being computed, still
  // and dim when idle); its main run's projection and aggregation; a symbol
  // per run type; the run types being written now; and the SUs to finish.
  const cell = (n, exp) => exp
    ? `<span class="ck-pct">${fmtPctShort(pctOf(n, exp))}</span> <span class="ck-n">(${fmtN(n)}/${fmtN(exp)})</span>` : "";
  const totals = { low: 0, high: 0 };
  const rows = prog.map((s) => {
    const sec = DATA.sectors[s.key];
    const on = s.tracked && sectorActive(sec);
    const mark = `<td class="ck-name" title="${esc(s.part)}${on ? ", active: files written in the last day" : ""}">` +
      `<span class="ck-mark${on ? " on" : ""}" style="--mk:var(--sec-${s.key})"></span>${esc(s.label)}</td>`;
    if (!s.tracked) return `<tr>${mark}<td colspan="6" class="ck-none">not tracked (yet)</td></tr>`;
    const runs = RUN_TYPE_ORDER.map((k) => {
      const rt = sec.run_types[k];
      if (!rt) return `<td class="ck-sym" title="${esc(k)}: does not apply">${ICON.na}</td>`;
      const f = filesOf(sec, rt);
      const done = f.projExp > 0 && f.proj >= f.projExp;
      const live = runActive(rt);
      const tip = `${k}: projection ${fmtPctShort(pctOf(f.proj, f.projExp))}` +
        (f.aggExp ? `, aggregation ${fmtPctShort(pctOf(f.agg, f.aggExp))}` : "") + (live ? ", being computed now" : "");
      const icon = live ? ICON.busy.replace("{c}", `var(--sec-${s.key})`) : done ? ICON.yes : ICON.no;
      return `<td class="ck-sym" title="${esc(tip)}">${icon}</td>`;
    }).join("");
    const su = sectorSUs(sec);
    if (su) { totals.low += su.low; totals.high += su.high; }
    return `<tr>${mark}<td>${cell(s.files.proj, s.files.projExp)}</td><td>${cell(s.files.agg, s.files.aggExp)}</td>${runs}` +
      `<td class="ck-su">${su ? suShort(su.low, su.high) : `<span class="ck-n">no data</span>`}</td></tr>`;
  }).join("");
  const a = DATA.account;
  const avail = a.allocation_status === "ok" && a.balance_su != null ? ` <span class="ck-n">of ${fmtN(a.balance_su)} available</span>` : "";
  $("camel-key").innerHTML = `<div class="ck-wrap"><table class="ck-table"><thead><tr><th></th><th>Projection</th>
      <th>Aggregation${mainMark()}</th><th class="ck-sym">Single</th><th class="ck-sym">Median</th><th class="ck-sym">Montecarlo</th>
      <th class="ck-su">SUs to finish</th></tr></thead><tbody>${rows}</tbody>
    <tfoot><tr><td>Total</td><td colspan="5"></td><td class="ck-su">${suShort(totals.low, totals.high)}${avail ? `<div class="ck-avail">${avail.trim()}</div>` : ""}</td></tr></tfoot>
    </table></div><div class="ck-total-phone">Total SUs to finish: <b>${suShort(totals.low, totals.high)}</b>${avail}</div>
    <div class="ck-foot">Percents refer to each sector's main run (montecarlo; median for energy).</div>`;
}

// Line symbols for the run type columns: complete, not complete, does not
// apply, and a slowly spinning circle in the sector color while being computed.
const ICON = {
  busy: `<svg class="ck-ico ck-busy" viewBox="0 0 12 12" aria-label="being computed" style="color:{c}">` +
    `<circle cx="6" cy="6" r="3.8" class="ck-busy-track"/><path d="M6 2.2a3.8 3.8 0 0 1 3.8 3.8"/></svg>`,
  yes: `<svg class="ck-ico ck-yes" viewBox="0 0 12 12" aria-label="complete"><path d="M2.6 6.4l2.3 2.3 4.5-5"/></svg>`,
  no: `<svg class="ck-ico ck-no" viewBox="0 0 12 12" aria-label="not complete"><path d="M3.6 3.6l4.8 4.8M8.4 3.6l-4.8 4.8"/></svg>`,
  na: `<svg class="ck-ico ck-na" viewBox="0 0 12 12" aria-label="does not apply"><path d="M3.5 6h5"/></svg>`,
};

// A run type is active when its projection files were written in the last
// day or a unit is being written now (the same signal as the pulsing mark).
function runActive(rt) {
  const scan = new Date(DATA.generated_at).getTime();
  return rt.units.some((u) => u.stages.generate && u.stages.generate.state === "running") ||
    (rt.last_projection_write && scan - new Date(rt.last_projection_write).getTime() < 24 * 3.6e6);
}

// SUs to finish a sector, summed over its run types; null when one of them
// with units left has no estimate yet.
function sectorSUs(sec) {
  let low = 0, high = 0;
  for (const rt of Object.values(sec.run_types)) {
    const e = rt.su_estimate;
    if (!e || !e.remaining) continue;
    if (e.su_low == null) return null;
    low += e.su_low;
    high += e.su_high;
  }
  return { low, high };
}
function suShort(low, high) {
  if (!high) return "0";
  return low === high ? fmtSU(low) : `${fmtSU(low)} to ${fmtSU(high)}`;
}

/* ---------- interactions and boot ---------- */

function setup() {
  document.querySelectorAll(".panel-header").forEach((h) => {
    h.onclick = () => $(h.dataset.panel).classList.toggle("open");
  });
  $("scen-graph").addEventListener("click", (e) => {
    const b = e.target.closest(".sb");
    if (!b) return;
    const list = view.picks[b.dataset.f], v = b.dataset.v;
    const order = [...$("scen-graph").querySelectorAll(`.sb[data-f="${b.dataset.f}"]`)].map((x) => x.dataset.v);
    view.picks[b.dataset.f] = list.includes(v) ? list.filter((x) => x !== v) : order.filter((x) => x === v || list.includes(x));
    view.ssps = view.picks.ssp.slice();
    b.classList.toggle("on");
    b.setAttribute("aria-pressed", String(b.classList.contains("on")));
    applyColumns();
  });
  $("hl-tabs").addEventListener("click", (e) => {
    const b = e.target.closest(".hl-opt");
    if (!b) return;
    view.hl = b.dataset.hl;
    $("grid").dataset.hl = view.hl;
    for (const o of document.querySelectorAll(".hl-opt")) o.classList.toggle("active", o.dataset.hl === view.hl);
  });
  $("pa-info-btn").addEventListener("click", () => {
    const open = $("pa-info").classList.toggle("hidden") === false;
    $("pa-info-btn").setAttribute("aria-expanded", String(open));
    $("pa-info-btn").classList.toggle("on", open);
  });
  const rc = $("resources-content");
  const SU_TARGET = ".su-bar-all .seg, .su-blocks .ukey-item[data-user], .su-blocks .ukey-item[data-part]";
  rc.addEventListener("mouseover", (e) => {
    const t = e.target.closest(SU_TARGET);
    if (t) suHighlight(t.closest(".su-blocks"), suSelection(t));
  });
  rc.addEventListener("mouseout", (e) => {
    const t = e.target.closest(SU_TARGET);
    if (t && !t.contains(e.relatedTarget)) { const box = t.closest(".su-blocks"); suHighlight(box, suPicked[box.dataset.box]); }
  });
  const closePop = (except) => {
    document.querySelectorAll(".info-wrap").forEach((w) => {
      const pop = w.querySelector(".su-pop"), b = w.querySelector(".info-btn");
      if (w === except || !pop || pop.classList.contains("hidden")) return;
      pop.classList.add("hidden");
      b.setAttribute("aria-expanded", "false");
      b.classList.remove("on");
    });
  };
  document.addEventListener("click", (e) => closePop(e.target.closest(".info-wrap")));
  // Escape closes an open "i" box first, then the cell details.
  document.addEventListener("keydown", (e) => {
    if (e.key !== "Escape") return;
    if (document.querySelector(".info-wrap .su-pop:not(.hidden)")) closePop();
    else if (view.selected) closeDetail();
  });
  // Any "i" on the page opens the box next to it.
  document.addEventListener("click", (e) => {
    const b = e.target.closest(".info-wrap > .info-btn");
    if (!b) return;
    e.preventDefault();   // an "i" inside a summary must not open or close it
    const pop = b.parentElement.querySelector(".su-pop");
    if (!pop.classList.contains("hidden")) { closePop(); return; }
    pop.classList.remove("hidden");
    b.setAttribute("aria-expanded", "true");
    b.classList.add("on");
    // Keep the box on screen on narrow screens.
    pop.style.left = "";
    const r = pop.getBoundingClientRect();
    if (r.right > innerWidth - 8) pop.style.left = `${Math.round(innerWidth - 8 - r.right)}px`;
  });

  rc.addEventListener("click", (e) => {
    const t = e.target.closest(SU_TARGET);
    if (t) {
      const sel = suSelection(t), box = t.closest(".su-blocks"), pick = suPicked[box.dataset.box];
      const same = pick && pick.user === sel.user && pick.part === sel.part;
      suPicked[box.dataset.box] = same ? null : sel;
      suHighlight(box, suPicked[box.dataset.box]);
      return;
    }
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
  let touch = false;
  document.addEventListener("pointerdown", (e) => {
    touch = e.pointerType !== "mouse";
    if (touch && !e.target.closest(".batch")) tip.style.display = "none";
  }, true);
  const fillTip = (b) => {
    const info = cellIndex.get(b.dataset.key);
    const spec = specOf(sector(), info.model), cnt = unitCounts(info.unit, spec), sc = curScen();
    const alt = sc ? unitCounts(info.unit, spec, sc) : null;
    tip.innerHTML = `${esc(cellTitle(info))}<br>${cnt.proj}/${cnt.projTotal} projection` +
      (cnt.aggTotal ? `<br>${cnt.agg}/${cnt.aggTotal} aggregation` : "") +
      (alt ? `<br><span class="muted">${esc(scenLabel(sc, runType()))}: ${alt.agg}/${alt.aggTotal}, not counted</span>` : "") +
      `<br><span class="muted">${esc(STATE_NAMES[cellState(info.unit, cnt)])}</span>`;
    tip.style.display = "block";
    return tip.getBoundingClientRect();
  };
  const placeTip = (x, y) => { tip.style.left = `${Math.max(8, x)}px`; tip.style.top = `${Math.max(8, y)}px`; };
  let quietUntil = 0;
  grid.addEventListener("click", async (e) => {
    const b = e.target.closest(".batch");
    if (!b) return;
    const before = b.getBoundingClientRect().top;
    await showDetail(b.dataset.key);
    if (!touch) return;
    // The file list opens above the grid; keep the tapped cell under the finger.
    const shift = b.getBoundingClientRect().top - before;
    if (Math.abs(shift) > 1) { quietUntil = Date.now() + 400; scrollBy(0, shift); }
    const c = b.getBoundingClientRect(), r = fillTip(b);
    let x = c.left + c.width / 2 - r.width / 2, y = c.bottom + 6;
    if (x + r.width > innerWidth - 8) x = innerWidth - 8 - r.width;
    if (y + r.height > innerHeight - 8) y = c.top - r.height - 6;
    placeTip(x, y);
  });
  grid.addEventListener("mousemove", (e) => {
    if (touch) return;
    const b = e.target.closest(".batch");
    if (!b) { tip.style.display = "none"; crossHighlight(selectedBatch()); return; }
    if (!crossCells.includes(b.closest("td"))) crossHighlight(b);
    const r = fillTip(b);
    let x = e.clientX + 12, y = e.clientY + 12;
    if (x + r.width > innerWidth - 8) x = e.clientX - r.width - 12;
    if (y + r.height > innerHeight - 8) y = e.clientY - r.height - 12;
    placeTip(x, y);
  });
  grid.addEventListener("mouseleave", () => {
    if (!touch) tip.style.display = "none";
    crossHighlight(selectedBatch());
  });
  const hideTip = () => { if (Date.now() > quietUntil) tip.style.display = "none"; };
  addEventListener("scroll", hideTip, { passive: true });
  document.querySelector(".grid-wrap").addEventListener("scroll", hideTip, { passive: true });
  let fitTimer = null;
  addEventListener("resize", () => {
    clearTimeout(fitTimer);
    fitTimer = setTimeout(() => { hideTip(); if (view.sector && !document.body.classList.contains("no-model")) fitGrid(); }, 120);
  });
  $("theme-toggle").onclick = () => {
    const root = document.documentElement;
    const next = getComputedStyle(root).colorScheme.includes("dark") ? "light" : "dark";
    root.dataset.theme = next;
    try { localStorage.setItem("amel-theme", next); } catch (e) { /* storage may be blocked */ }
    // The file squares are pictures in the theme's colors: redraw them.
    sqCache.clear();
    sqColors = null;
    if (view.sector && view.runType && !document.body.classList.contains("no-model")) renderGrid();
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
  const every = DATA.scan_interval_hours === 1 ? "every hour" : `every ${DATA.scan_interval_hours} h`;
  $("subtitle").textContent = `Last scan: ${fmtWhen(DATA.generated_at, true)}, ${every}` +
    (localCopy ? " (local copy)" : "");
  if (DATA.source === "mock") $("mock-badge").classList.remove("hidden");
  if (ageH > 2 * DATA.scan_interval_hours) {
    $("stale-banner").textContent = `The last scan is ${ageH.toFixed(1)} hours old. The scheduled job may have stopped.`;
    $("stale-banner").classList.remove("hidden");
  }

  view.sector = null;
  view.runType = null;
  view.ssps = [];
  buildTreeLayout();
  setup();
  renderCamel();
  loadCamel();
  renderResources();
  renderJobs();
  renderAll();
}

boot();
