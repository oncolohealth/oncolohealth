"use strict";

const TOKEN = document.querySelector('meta[name="cw-token"]').content;
const $ = (sel, el = document) => el.querySelector(sel);
const $$ = (sel, el = document) => [...el.querySelectorAll(sel)];

async function api(path, body) {
  const opts = { headers: { "X-CW-Token": TOKEN } };
  if (body !== undefined) {
    opts.method = "POST";
    opts.headers["Content-Type"] = "application/json";
    opts.body = JSON.stringify(body);
  }
  const res = await fetch(path, opts);
  const data = await res.json().catch(() => ({ error: `Unexpected response (${res.status})` }));
  if (!res.ok) {
    const error = new Error(data.error || `Request failed (${res.status})`);
    error.status = res.status;
    throw error;
  }
  return data;
}

function esc(v) {
  return String(v ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}
// Minimal inline markdown for PROGRESS.md text: `code` and **bold** only, applied after escaping.
function md(s) {
  return esc(s).replace(/`([^`]+)`/g, "<code>$1</code>").replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>");
}
function fmtBytes(n) {
  if (n == null) return "";
  if (n >= 1e9) return `${(n / 1e9).toFixed(n >= 1e10 ? 0 : 1)} GB`;
  if (n >= 1e6) return `${Math.round(n / 1e6)} MB`;
  if (n >= 1e3) return `${Math.round(n / 1e3)} kB`;
  return `${n} B`;
}
function list(v) { return Array.isArray(v) ? v.join(", ") : (v ?? ""); }

let toastTimer;
function toast(msg, bad = false) {
  const t = $("#toast");
  t.textContent = msg;
  t.className = `toast show${bad ? " bad" : ""}`;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => (t.className = "toast"), bad ? 6000 : 3000);
}
async function guard(fn) {
  try { return await fn(); } catch (e) { toast(e.message, true); }
}

/* ---------------- theme ---------------- */
// Dark by default; the choice is a per-browser convenience, so storage failures are ignored.
function setTheme(theme) {
  document.documentElement.dataset.theme = theme;
  const next = theme === "dark" ? "light" : "dark";
  $("#theme-toggle").setAttribute("aria-label", `Switch to ${next} theme`);
  $("#theme-toggle").title = `Switch to ${next} theme`;
}
try { setTheme(localStorage.getItem("cw-theme") === "light" ? "light" : "dark"); } catch { setTheme("dark"); }
$("#theme-toggle").addEventListener("click", () => {
  const theme = document.documentElement.dataset.theme === "dark" ? "light" : "dark";
  setTheme(theme);
  try { localStorage.setItem("cw-theme", theme); } catch { /* not persisted */ }
});

/* ---------------- navigation ---------------- */
const SCREENS = ["catalog", "downloads", "datasets", "images", "experiments", "assistant", "progress"];
const loaders = {};
function show(name) {
  if (!SCREENS.includes(name)) name = "catalog";
  for (const s of SCREENS) $(`#screen-${s}`).hidden = s !== name;
  $$(".nav-btn").forEach(b => { if (b.dataset.screen !== name) b.removeAttribute("aria-current"); else b.setAttribute("aria-current", "page"); });
  $("#title-screen").textContent = $(`.nav-btn[data-screen="${name}"]`).getAttribute("aria-label");
  if (location.hash !== `#${name}`) history.replaceState(null, "", `#${name}`);
  loaders[name]?.();
}
$$(".nav-btn").forEach(b => b.addEventListener("click", () => show(b.dataset.screen)));
window.addEventListener("hashchange", () => show(location.hash.slice(1)));
document.addEventListener("keydown", e => {
  const n = Number(e.key);
  if (e.altKey && !e.ctrlKey && !e.metaKey && n >= 1 && n <= SCREENS.length) { e.preventDefault(); show(SCREENS[n - 1]); }
});
// Status bar: background downloads and live scoring keep running while you switch screens.
function updateActivity() {
  const dl = state.jobs.some(j => j.state === "running" || j.state === "planning");
  const sc = img.scoring?.state === "running" ? `Scoring ${img.scoring.done} of ${img.scoring.total} images` : "";
  const text = [dl ? "Downloading" : "", sc].filter(Boolean).join(" · ");
  $("#status-activity").textContent = text;
  $("#status-activity").hidden = !text;
}

/* ---------------- shared state ---------------- */
const state = { records: [], byId: {}, storage: null, selected: new Set(), jobs: [], typeFilter: "",
  subsets: {}, subsetPlan: {}, subsetDraft: {}, subsetUnits: {}, openSubset: null };

async function loadCatalog() {
  const data = await api("/api/catalog");
  state.records = data.records;
  state.byId = Object.fromEntries(data.records.map(r => [r.id, r]));
  if (data.validation.length) toast(`Catalog has ${data.validation.length} validation problem(s). Run "catalog validate" for details.`, true);
}
async function loadStorage() {
  const s = await api("/api/storage");
  state.storage = s;
  const pct = Math.min(100, (s.used / s.budget) * 100);
  $("#storage-text").textContent = `${fmtBytes(s.used)} of ${fmtBytes(s.budget)}`;
  $("#storage-fill").style.width = `${pct}%`;
  $("#budget-fill").style.width = `${pct}%`;
  $("#budget-used").textContent = fmtBytes(s.used);
  $("#budget-of").textContent = `used of ${fmtBytes(s.budget)} budget`;
  const hf = $("#hf-state");
  hf.className = `status-item token-state ${s.hf_token ? "ok" : "no"}`;
  hf.textContent = s.hf_token ? "Hugging Face token set" : "No Hugging Face token";
  updateSelection();
}

/* ---------------- evidence ladder ---------------- */
const LADDER = [
  ["cataloged", "Cataloged"],
  ["access_obtained", "Files on disk"],
  ["runnable", "Runs here"],
  ["locally_reproduced", "Reproduced here"],
  ["externally_evaluated", "Externally evaluated"],
];
const rank = s => LADDER.findIndex(([k]) => k === s);
function ladder(s) {
  const r = rank(s);
  const label = LADDER[r]?.[1] ?? s;
  return `<span class="ladder" role="img" aria-label="Evidence: ${esc(label)}" title="${esc(label)}">${LADDER.map((_, i) => `<i class="${i <= r ? "on" : ""}"></i>`).join("")}</span>`;
}
function ladderBig(s) {
  const r = rank(s);
  return `<div class="ladder-big" aria-hidden="true">${LADDER.map((_, i) => `<div class="${i <= r ? "on" : ""}"></div>`).join("")}</div>
    <div class="ladder-big-labels">${LADDER.map(([, l], i) => `<span class="${i === r ? "cur" : ""}">${esc(l)}</span>`).join("")}</div>`;
}
$("#ladder-key").innerHTML = LADDER.map(([k, l]) => `<span>${ladder(k)} ${esc(l)}</span>`).join("");

/* ---------------- catalog ---------------- */
function licenseShort(lic) {
  if (!lic) return "";
  const nc = lic.commercial === false;
  return `<span class="pill${nc ? " nc" : ""}" title="${esc(lic.notes || lic.url || "")}">${esc(lic.id)}</span>`;
}
function renderCatalog() {
  const q = $("#catalog-search").value.trim().toLowerCase();
  const rows = state.records.filter(r => (!state.typeFilter || r.record_type === state.typeFilter) &&
    (!q || JSON.stringify([r.id, r.name, r.summary, r.tasks, r.modality, r.anatomy, r.license, r.kind]).toLowerCase().includes(q)));
  const sel = $("#catalog-detail").dataset.id;
  $("#catalog-table tbody").innerHTML = rows.map(r => `
    <tr data-id="${esc(r.id)}" class="${r.id === sel ? "sel" : ""}" tabindex="0">
      <td>${ladder(r.evidence_state)}</td>
      <td class="name"><strong>${esc(r.name)}</strong><span class="mono">${esc(r.id)}</span></td>
      <td>${esc(list(r.modality))}</td>
      <td>${licenseShort(r.license)}</td>
      <td class="num">${r.acquisition?.approx_bytes ? fmtBytes(r.acquisition.approx_bytes) : "?"}</td>
      <td>${r.local ? '<span class="local-yes">On disk</span>' : ""}</td>
    </tr>`).join("") || `<tr><td colspan="6" class="empty">Nothing matches "${esc(q)}".</td></tr>`;
}
function showDetail(id) {
  const r = state.byId[id];
  if (!r) return;
  const box = $("#catalog-detail");
  box.dataset.id = id;
  const lic = r.license || {};
  const acq = r.acquisition || {};
  const rows = [
    ["Kind", r.record_type === "model" ? r.kind : "dataset"],
    ["Tasks", list(r.tasks)],
    ["Modality", list(r.modality)],
    ["Anatomy", list(r.anatomy)],
    ["Input", r.input ? Object.entries(r.input).map(([k, v]) => `${k}: ${Array.isArray(v) ? v.join("×") : v}`).join("; ") : ""],
    ["Output", r.outputs ? Object.entries(r.outputs).map(([k, v]) => `${k}: ${list(v)}`).join("; ") : ""],
    ["Counts", r.counts ? Object.entries(r.counts).map(([k, v]) => `${k.replace(/_/g, " ")}: ${v}`).join("; ") : ""],
    ["Labels", r.labels ? Object.entries(r.labels).map(([k, v]) => `${k.replace(/_/g, " ")}: ${list(v)}`).join("; ") : ""],
    ["Trained on", list(r.pretraining_data)],
    ["License", [lic.id, lic.commercial === false ? "non-commercial" : "", lic.notes].filter(Boolean).join(". ")],
    ["Access", r.access],
    ["Inference", r.inference_permission ? `${r.inference_permission.replace("_", " ")}` : ""],
    ["Adapter", r.record_type === "model" ? (r.adapter || "none installed") : ""],
    ["Pinned at", acq.revision ? `${acq.repo}@${acq.revision.slice(0, 12)}` : acq.record ? `Zenodo ${acq.record}` : acq.article ? `figshare ${acq.article} v${acq.version}` : acq.collection ? `TCIA ${acq.collection}` : ""],
    ["Fetched from", acq.fetcher === "isic" ? "ISIC API v2, live search" : acq.fetcher === "gdc" ? "GDC files API, live query" : acq.fetcher === "s3" ? `s3://${acq.bucket}/${acq.prefix}` : ""],
    ["Subsets", acq.subset ? `By ${acq.subset.unit}: a seeded random sample or picked IDs${acq.subset.required ? " (required)" : ""}` : ""],
  ].filter(([, v]) => v);
  const warnings = [...(r.unresolved || []).map(u => `Open question: ${u}`), ...(r.known_overlap || []).map(o => `Overlaps with ${o}`)];
  const cite = String(r.citation || "");
  const citeHtml = /^https?:\/\//.test(cite) ? `<a href="${esc(cite)}" target="_blank" rel="noopener noreferrer">${esc(cite)}</a>` : esc(cite);
  box.innerHTML = `
    <h2>${esc(r.name)}</h2>
    <p class="hint mono">${esc(r.id)}</p>
    <p>${esc(r.summary || "")}</p>
    ${ladderBig(r.evidence_state)}
    <dl>${rows.map(([k, v]) => `<dt>${esc(k)}</dt><dd>${esc(v)}</dd>`).join("")}<dt>Source</dt><dd>${citeHtml}</dd></dl>
    ${warnings.length ? `<h3>Before you rely on it</h3><ul class="warn-list">${warnings.map(w => `<li>${esc(w)}</li>`).join("")}</ul>` : ""}
    ${acq.instructions ? `<h3>How to get it</h3><p>${esc(acq.instructions)}</p>` : ""}
    <div class="actions">
      ${r.local ? `<button class="btn" data-act="prov">View provenance</button>` : ""}
      ${(!r.local || acq.subset) && acq.tier && acq.tier !== "manual" ? `<button class="btn primary" data-act="queue">${acq.subset ? "Choose a subset" : "Add to downloads"}</button>` : ""}
    </div>
    <div id="detail-extra"></div>
    ${r.record_type === "model" && r.adapter ? specialistPanel(r) : ""}`;
  $$("#catalog-table tbody tr").forEach(tr => tr.classList.toggle("sel", tr.dataset.id === id));
  box.querySelector(".specialist-form")?.addEventListener("submit", e => {
    e.preventDefault();
    const f = e.target, out = box.querySelector(".specialist-result"), btn = f.querySelector("button");
    btn.disabled = true;
    out.innerHTML = '<p class="hint">Running…</p>';
    guard(async () => {
      const res = await api("/api/specialist/run", { model_id: id, task: f.task.value, modality: f.modality.value, anatomy: f.anatomy.value, inputs: { image: f.image.value.trim() } });
      out.innerHTML = specialistResult(res);
    }).finally(() => { btn.disabled = false; if (out.textContent === "Running…") out.innerHTML = ""; });
  });
  box.querySelector('[data-act="prov"]')?.addEventListener("click", () => guard(async () => {
    const p = await api(`/api/provenance/${encodeURIComponent(id)}`);
    const sels = p.selections?.length ? ` ${p.selections.length} fetch${p.selections.length === 1 ? "" : "es"} recorded with their selection.` : "";
    $("#detail-extra").innerHTML = `<h3>Provenance</h3><p class="hint">Last retrieved ${esc(p.retrieved_at)}.${esc(sels)} ${esc(p.note)}</p><pre class="prov">${esc(JSON.stringify(p.files.map(f => ({ path: f.path, bytes: f.bytes, sha256: f.sha256, integrity: f.integrity })), null, 2))}</pre>`;
  }));
  box.querySelector('[data-act="queue"]')?.addEventListener("click", () => {
    if (acq.subset) {
      state.openSubset = id;
      show("downloads");
      return;
    }
    state.selected.add(id);
    show("downloads");
    toast(`${r.name} added to the download selection.`);
  });
}
// Runs through /api/specialist/run, which calls the assistant's own run_specialist tool.
function specialistPanel(r) {
  const st = r.adapter_status;
  const opt = v => `<option>${esc(v)}</option>`;
  return `
    <h3>Run specialist</h3>
    <p class="hint">Calls <code>run_specialist</code>, the tool the assistant uses. ${r.outputs?.type === "embedding" ? "The output is a feature vector, not a probability or diagnosis." : ""}</p>
    ${st && !st.installed ? `<p class="warn-text">Adapter not installed in this app process: ${esc(st.reasons.join("; "))}. A run returns the rejection.</p>` : ""}
    <form class="specialist-form">
      <label>Image<input name="image" value="btxrd:IMG000001" placeholder="btxrd:<sample_id> or uploads:<id>" required></label>
      <div class="field-row">
        <label>Task<select name="task">${(r.tasks || []).map(opt).join("")}</select></label>
        <label>Modality<select name="modality">${(r.modality || []).map(opt).join("")}</select></label>
      </div>
      <label>Anatomy<input name="anatomy" value="bone" required></label>
      <button type="submit" class="btn primary">Run on this image</button>
    </form>
    <div class="specialist-result" aria-live="polite"></div>`;
}
function specialistResult(res) {
  if (res.error) return `<p class="err-text">Tool call refused: ${esc(res.error)}</p>`;
  const env = res.result, o = env.outputs || {};
  const badge = env.status === "ok" ? '<span class="badge ready">ok</span>' : `<span class="badge not">${esc(env.status)}</span>`;
  const raw = `<details class="call${env.status === "ok" ? "" : " bad"}"><summary>Result envelope ${esc(env.run_id)}</summary><pre>${esc(JSON.stringify(env, null, 2))}</pre></details>`;
  if (env.status !== "ok") return `<p>${badge}</p><ul class="warn-list">${env.errors.map(e => `<li>${esc(e)}</li>`).join("")}</ul>${raw}`;
  const enc = o.encoder || {}, inp = o.input || {};
  const rows = [
    ["Output", `${o.type}, ${o.dim} × ${o.dtype}, L2 norm ${o.l2_norm}`],
    ["Meaning", o.semantics],
    ["Vector SHA-256", o.embedding_sha256],
    ["First values", (o.embedding_preview || []).join(", ")],
    ["Image", `${inp.file} (${inp.width}×${inp.height} ${inp.mode}), sha256 ${inp.sha256}`],
    ["Revision", enc.revision],
    ["Weights", `${enc.weights?.sha256} (${fmtBytes(enc.weights?.bytes)})`],
    ["Processor", `${enc.processor_config?.file} ${enc.processor_config?.sha256}`],
    ["Preprocessing", `${enc.variant}: ${enc.preprocessing?.policy}`],
    ["Device", `${enc.device}, ${o.seconds} s`],
    ["Terms", o.terms?.scope],
  ].filter(([, v]) => v);
  return `<p>${badge}${env.synthetic ? ' <span class="badge synthetic">synthetic</span>' : ""}</p>
    <dl>${rows.map(([k, v]) => `<dt>${esc(k)}</dt><dd>${esc(v)}</dd>`).join("")}</dl>${raw}`;
}
$("#catalog-table").addEventListener("click", e => { const tr = e.target.closest("tr[data-id]"); if (tr) showDetail(tr.dataset.id); });
$("#catalog-table").addEventListener("keydown", e => { const tr = e.target.closest("tr[data-id]"); if (tr && (e.key === "Enter" || e.key === " ")) { e.preventDefault(); showDetail(tr.dataset.id); } });
$("#catalog-search").addEventListener("input", renderCatalog);
$$(".catalog-tools .seg button").forEach(b => b.addEventListener("click", () => {
  state.typeFilter = b.dataset.type;
  $$(".catalog-tools .seg button").forEach(x => x.classList.toggle("on", x === b));
  renderCatalog();
}));

let routerLoaded = false;
async function loadRouterOptions() {
  if (routerLoaded) return;
  const o = await api("/api/route/options");
  const f = $("#router-form");
  for (const key of ["task", "modality", "anatomy"]) {
    f[key].innerHTML = o[key].map(v => `<option>${esc(v)}</option>`).join("");
  }
  f.task.value = "feature_extraction"; f.modality.value = "xray"; f.anatomy.value = "bone";
  routerLoaded = true;
}
$("#router-form").addEventListener("submit", e => {
  e.preventDefault();
  guard(async () => {
    const f = e.target;
    const res = await api("/api/route", { task: f.task.value, modality: f.modality.value, anatomy: f.anatomy.value, channels: f.channels.value, spatial_dims: f.spatial_dims.value });
    const name = id => esc(state.byId[id]?.name || id);
    const link = id => `<button type="button" class="linkish" data-open="${esc(id)}">${name(id)}</button>`;
    const can = res.compatible.filter(c => c.runnable), blocked = res.compatible.filter(c => !c.runnable);
    $("#router-result").innerHTML = `
      <div><h3>Can run now (${can.length})</h3><ul class="verdict">${can.map(c => `<li class="can">${link(c.id)}</li>`).join("") || '<li class="no"><small>None. Nothing in the catalog has an installed adapter with reviewed permission yet.</small></li>'}</ul></div>
      <div><h3>Compatible but not runnable (${blocked.length})</h3><ul class="verdict">${blocked.map(c => `<li class="blocked">${link(c.id)}<small>${c.blockers.map(esc).join("; ")}</small></li>`).join("") || '<li class="no"><small>None.</small></li>'}</ul></div>
      <div><h3>Not compatible (${res.rejected.length})</h3><ul class="verdict">${res.rejected.map(c => `<li class="no">${link(c.id)}<small>${c.reasons.map(esc).join("; ")}</small></li>`).join("")}</ul></div>`;
  });
});
$("#router-result").addEventListener("click", e => { const b = e.target.closest("[data-open]"); if (b) { showDetail(b.dataset.open); $("#catalog-detail").scrollIntoView({ behavior: "smooth", block: "nearest" }); } });

loaders.catalog = () => guard(async () => { await loadRouterOptions(); renderCatalog(); });

/* ---------------- downloads ---------------- */
const TIERS = [
  ["default", "Starter set", "Open licenses, small enough for a laptop. Covers the bone X-ray milestone plus quick lung, breast and pathology prototyping."],
  ["optional", "Optional", "Open but heavier or with non-commercial terms. Check the license before using results outside research."],
  ["gated", "Gated models", "Each needs you to accept its terms on Hugging Face with your own account, then start the app with HF_TOKEN set."],
  ["big_machine", "GPU machine only", "Coordinator weights far larger than this laptop's budget. Fetch these on the GPU machine."],
  ["manual", "Manual", "Need registration or are too large to fetch here. Each entry says how to obtain it."],
];
function renderTiers() {
  const hf = state.storage?.hf_token;
  $("#tiers").innerHTML = TIERS.map(([tier, title, desc]) => {
    const recs = state.records.filter(r => r.acquisition?.tier === tier);
    if (!recs.length) return "";
    const selectable = recs.filter(r => !r.local && tier !== "manual" && !(tier === "gated" && !hf) && !r.acquisition.subset?.required);
    const rows = recs.map(r => {
      if (tier === "manual") return `<li class="manual"><div><strong>${esc(r.name)}</strong><div class="why">${esc(r.acquisition.instructions)}</div></div></li>`;
      const sub = r.acquisition.subset;
      const disabled = (r.local && !sub) || (tier === "gated" && !hf);
      const why = r.local && !sub ? "On disk" : tier === "gated" && !hf ? "Needs HF_TOKEN" : "";
      return `<li><input type="checkbox" data-id="${esc(r.id)}" aria-label="Select ${esc(r.name)}" ${state.selected.has(r.id) ? "checked" : ""} ${disabled ? "disabled" : ""}>
        <div><strong>${esc(r.name)}</strong><div class="why">${esc(r.summary || "")}</div>${sub ? subsetLine(r) : ""}</div>
        <span>${licenseShort(r.license)}${r.access?.startsWith("gated") ? ' <span class="pill gated">gated</span>' : ""}</span>
        <span class="num">${why ? `<span class="${r.local ? "local-yes" : "why"}">${esc(why)}</span>` : sub ? subsetSize(r) : fmtBytes(r.acquisition.approx_bytes)}</span></li>
        ${state.openSubset === r.id ? `<li class="subset-row">${subsetPanel(r)}</li>` : ""}`;
    }).join("");
    return `<section class="tier"><div class="tier-head"><div><h2>${esc(title)}</h2><p>${esc(desc)}</p></div>
      ${selectable.length ? `<button class="btn small" data-tier="${tier}">Select all ${selectable.length}</button>` : ""}</div>
      <ul class="tier-rows">${rows}</ul></section>`;
  }).join("");
}
/* Subsets: a record with acquisition.subset can be fetched in part, as whole groups (patients, slides)
   drawn in a seeded order or as picked IDs. Sizes come from the server's plan, never from guesses. */
const plural = unit => ({ patient: "patients", file: "files", image: "images", slide: "slides" }[unit] || `${unit}s`);
function subsetText(sel, unit) {
  if (!sel) return "";
  const q = sel.query ? ` matching ${sel.query}` : "";
  return sel.mode === "sample" ? `${sel.count} random ${plural(unit)} (seed ${sel.seed})${q}` : `${sel.ids.length} picked${q}`;
}
function subsetLine(r) {
  const sub = r.acquisition.subset, sel = state.subsets[r.id];
  const status = sel ? `Subset: ${subsetText(sel, sub.unit)}` : sub.required ? "Choose a subset to download" : "Default files, or choose a subset";
  const disk = r.local_files ? ` · ${r.local_files} files on disk` : "";
  return `<div class="subset-line"><span>${esc(status + disk)}</span>
    <button class="btn small" data-subset="${esc(r.id)}" aria-expanded="${state.openSubset === r.id}">${sel ? "Edit subset" : "Choose subset"}</button></div>`;
}
function subsetSize(r) {
  if (state.subsets[r.id]) return state.subsetPlan[r.id] ? fmtBytes(state.subsetPlan[r.id].bytes) : "…";
  if (r.acquisition.subset.required) return `<span class="why">pick a subset</span>`;
  return r.local ? `<span class="local-yes">On disk</span>` : fmtBytes(r.acquisition.approx_bytes);
}
function subsetDraft(r) {
  const sub = r.acquisition.subset, sel = state.subsets[r.id];
  if (!state.subsetDraft[r.id]) {
    state.subsetDraft[r.id] = {
      mode: sel?.mode || (sub.unit === "file" ? "ids" : "sample"), count: sel?.count || 5, seed: sel?.seed ?? 0,
      picks: new Set(sel?.mode === "ids" ? sel.ids : []), query: sel?.query || "", filter: "", paste: "",
    };
  }
  return state.subsetDraft[r.id];
}
function subsetPanel(r) {
  const sub = r.acquisition.subset, d = subsetDraft(r), units = plural(sub.unit);
  const planned = state.subsetPlan[r.id];
  const modes = sub.unit === "file" ? "" : `<div class="seg" role="group" aria-label="How to choose">
      <button type="button" data-mode="sample" class="${d.mode === "sample" ? "on" : ""}">Random ${esc(units)}</button>
      <button type="button" data-mode="ids" class="${d.mode === "ids" ? "on" : ""}">Pick ${esc(units)}</button></div>`;
  const query = sub.query ? `<label>Search (ISIC syntax; narrows the CC-0 / CC-BY images on offer)
      <input data-f="query" value="${esc(d.query)}" placeholder='diagnosis_3:"Melanoma, NOS"' spellcheck="false"></label>` : "";
  const body = d.mode === "sample" ? `<div class="field-row">
        <label>Number of ${esc(units)}<input type="number" min="1" step="1" data-f="count" value="${esc(d.count)}"></label>
        <label>Seed<input type="number" min="0" step="1" data-f="seed" value="${esc(d.seed)}"></label></div>
      <p class="hint">All ${esc(units)} are shuffled with this seed and the first ones not already on disk are taken, so asking for more later continues the same order. The chosen IDs and seed go into PROVENANCE.json.</p>`
    : `<div class="subset-tools">
        <input type="search" data-f="filter" value="${esc(d.filter)}" placeholder="Filter the list" aria-label="Filter ${esc(units)}">
        <button type="button" class="btn small" data-act="load">${state.subsetUnits[r.id] ? "Reload list" : "Load list"}</button>
        <span class="hint" data-count>${d.picks.size} picked</span></div>
      <ul class="subset-list" data-list>${subsetListHtml(r)}</ul>
      <label>Or paste IDs<textarea rows="2" data-f="paste" placeholder="One per line or comma-separated" spellcheck="false">${esc(d.paste)}</textarea></label>`;
  return `<div class="subset" data-for="${esc(r.id)}">
    ${modes}${query}${body}
    <div class="subset-actions">
      <button type="button" class="btn small primary" data-act="apply">Check size and use</button>
      ${state.subsets[r.id] ? `<button type="button" class="btn small" data-act="clear">Remove subset</button>` : ""}
      <button type="button" class="btn small" data-act="close">Close</button>
    </div>
    <div class="subset-result" aria-live="polite">${planned ? subsetResultHtml(r, planned) : ""}</div></div>`;
}
function subsetListHtml(r) {
  const info = state.subsetUnits[r.id], d = subsetDraft(r);
  if (!info) return `<li class="empty">Load the list to see what this source offers.${r.acquisition.fetcher === "isic" ? " ISIC searches can take a minute or two." : ""}</li>`;
  const f = d.filter.trim().toLowerCase();
  const rows = info.groups.filter(g => !f || `${g.id} ${g.detail}`.toLowerCase().includes(f));
  const shown = rows.slice(0, 400);
  return shown.map(g => `<li><input type="checkbox" data-pick="${esc(g.id)}" aria-label="Pick ${esc(g.id)}" ${d.picks.has(g.id) ? "checked" : ""}>
      <span class="mono">${esc(g.id)}</span><span class="why">${esc(g.detail)}</span>
      <span class="num">${g.on_disk ? `<span class="local-yes">on disk</span>` : fmtBytes(g.bytes)}</span></li>`).join("")
    + (rows.length > shown.length ? `<li class="empty">${rows.length - shown.length} more; filter to narrow the list.</li>` : "")
    + (!rows.length ? `<li class="empty">Nothing matches.</li>` : "");
}
function subsetResultHtml(r, planned) {
  const s = planned.selection, units = plural(r.acquisition.subset.unit);
  const extra = [s.skipped_on_disk ? `${s.skipped_on_disk} already on disk skipped` : "", s.short_by ? `${s.short_by} fewer than asked: none left` : ""].filter(Boolean).join("; ");
  return `<p><strong>${s.groups.length} of ${s.population_groups} ${esc(units)}</strong>, ${s.unit_count} item${s.unit_count === 1 ? "" : "s"}, ${planned.estimated ? `about ${fmtBytes(planned.bytes)} of disk space (estimated: the source does not publish every file's size)` : `${fmtBytes(planned.bytes)} to download`}.${extra ? ` ${esc(extra)}.` : ""}</p>`;
}
function readSubset(r) {
  const sub = r.acquisition.subset, d = subsetDraft(r);
  const sel = d.mode === "sample" ? { mode: "sample", count: Number(d.count), seed: Number(d.seed) }
    : { mode: "ids", ids: [...new Set([...d.picks, ...d.paste.split(/[\s,]+/).filter(Boolean)])] };
  if (sel.mode === "sample" && !(Number.isInteger(sel.count) && sel.count >= 1)) throw new Error("Enter a whole number of at least 1.");
  if (sel.mode === "sample" && !(Number.isInteger(sel.seed) && sel.seed >= 0)) throw new Error("The seed must be a whole number, 0 or more.");
  if (sel.mode === "ids" && !sel.ids.length) throw new Error(`Pick or paste at least one ${sub.unit}.`);
  if (sub.query) {
    if (!d.query.trim()) throw new Error("Enter a search first: the full archive is too large to list.");
    sel.query = d.query.trim();
  }
  return sel;
}
function subsetFor(ids) {
  return Object.fromEntries(ids.filter(id => state.subsets[id]).map(id => [id, state.subsets[id]]));
}
function missingSubsets(ids) {
  return ids.filter(id => state.byId[id]?.acquisition?.subset?.required && !state.subsets[id]);
}
function dropSubset(id) {
  delete state.subsets[id]; delete state.subsetPlan[id]; delete state.subsetDraft[id];
}
$("#tiers").addEventListener("input", e => {
  const panel = e.target.closest(".subset");
  const f = e.target.dataset.f;
  if (!panel || !f) return;
  const r = state.byId[panel.dataset.for], d = subsetDraft(r);
  d[f] = e.target.value;
  if (f === "filter") $("[data-list]", panel).innerHTML = subsetListHtml(r);
});
$("#tiers").addEventListener("change", e => {
  const cb = e.target.closest("input[type=checkbox][data-pick]");
  if (!cb) return;
  const panel = cb.closest(".subset"), d = subsetDraft(state.byId[panel.dataset.for]);
  cb.checked ? d.picks.add(cb.dataset.pick) : d.picks.delete(cb.dataset.pick);
  $("[data-count]", panel).textContent = `${d.picks.size} picked`;
});
$("#tiers").addEventListener("click", e => {
  const open = e.target.closest("[data-subset]");
  if (open) {
    state.openSubset = state.openSubset === open.dataset.subset ? null : open.dataset.subset;
    renderTiers();
    return;
  }
  const panel = e.target.closest(".subset");
  if (!panel) return;
  const r = state.byId[panel.dataset.for], d = subsetDraft(r);
  const mode = e.target.closest("[data-mode]");
  if (mode) { d.mode = mode.dataset.mode; renderTiers(); return; }
  const act = e.target.closest("[data-act]")?.dataset.act;
  if (act === "close") { state.openSubset = null; renderTiers(); }
  if (act === "clear") {
    dropSubset(r.id);
    if (r.acquisition.subset.required) state.selected.delete(r.id);
    renderTiers(); updateSelection();
  }
  if (act === "load") guard(async () => {
    $("[data-list]", panel).innerHTML = `<li class="empty thinking">Listing ${esc(plural(r.acquisition.subset.unit))} from the source…</li>`;
    const body = { id: r.id };
    if (r.acquisition.subset.query) {
      if (!d.query.trim()) { $("[data-list]", panel).innerHTML = `<li class="empty">Enter a search first.</li>`; return; }
      body.query = d.query.trim();
    }
    try {
      state.subsetUnits[r.id] = await api("/api/fetch/units", body);
    } catch (err) {
      $("[data-list]", panel).innerHTML = `<li class="empty subset-error">${esc(err.message)}</li>`;
      return;
    }
    if (state.openSubset === r.id) renderTiers();
  });
  if (act === "apply") guard(async () => {
    const sel = readSubset(r);
    const out = $(".subset-result", panel);
    out.innerHTML = `<p class="thinking">Asking the source for exact files and sizes…</p>`;
    const p = await api("/api/fetch/plan", { ids: [r.id], subsets: { [r.id]: sel } });
    const row = p.rows[0];
    if (row.error) { out.innerHTML = `<p class="subset-error">${esc(row.error)}</p>`; return; }
    state.subsets[r.id] = sel;
    state.subsetPlan[r.id] = { bytes: row.bytes, selection: row.selection, estimated: row.files.some(f => f.size == null) };
    state.selected.add(r.id);
    renderTiers(); updateSelection();
  });
});

function updateSelection() {
  for (const id of [...state.selected]) if (state.byId[id]?.local && !state.byId[id]?.acquisition?.subset) state.selected.delete(id);
  const ids = [...state.selected];
  const sizeOf = id => {
    const r = state.byId[id];
    if (state.subsets[id]) return state.subsetPlan[id]?.bytes || 0;
    return r?.local ? 0 : r?.acquisition?.approx_bytes || 0;
  };
  const bytes = ids.reduce((s, id) => s + sizeOf(id), 0);
  const missing = missingSubsets(ids);
  $("#dl-selected").textContent = !ids.length ? "Nothing selected" : missing.length ? `${ids.length} selected; choose a subset for ${missing.length}` : `${ids.length} selected, about ${fmtBytes(bytes)}`;
  $("#dl-start").disabled = !ids.length || missing.length > 0;
  $("#dl-plan").disabled = !ids.length;
  const s = state.storage;
  if (!s) return;
  const plan = $("#budget-plan");
  const usedPct = Math.min(100, (s.used / s.budget) * 100);
  plan.style.left = `${usedPct}%`;
  plan.style.width = `${Math.max(0, Math.min(100 - usedPct, (bytes / s.budget) * 100))}%`;
  const over = s.used + bytes > s.budget;
  plan.classList.toggle("over", over);
  $("#budget-hint").textContent = !ids.length ? "Select items to see how much they add." :
    over ? `This selection would go ${fmtBytes(s.used + bytes - s.budget)} over budget. Raise CW_STORAGE_BUDGET_GB or pick fewer items.` :
    `After this download: about ${fmtBytes(s.used + bytes)} of ${fmtBytes(s.budget)}.`;
}
$("#tiers").addEventListener("change", e => {
  const cb = e.target.closest("input[type=checkbox][data-id]");
  if (!cb) return;
  const r = state.byId[cb.dataset.id];
  if (cb.checked && r.acquisition.subset?.required && !state.subsets[r.id]) {
    cb.checked = false;
    state.openSubset = r.id;
    renderTiers();
    toast(`Choose which ${plural(r.acquisition.subset.unit)} to fetch first.`);
    return;
  }
  cb.checked ? state.selected.add(cb.dataset.id) : state.selected.delete(cb.dataset.id);
  updateSelection();
});
$("#tiers").addEventListener("click", e => {
  const b = e.target.closest("[data-tier]");
  if (!b) return;
  $$(`#tiers input[data-id]:not(:disabled)`).forEach(cb => {
    const r = state.byId[cb.dataset.id];
    if (r.acquisition.tier === b.dataset.tier && !r.local && !(r.acquisition.subset?.required && !state.subsets[r.id])) { cb.checked = true; state.selected.add(r.id); }
  });
  updateSelection();
});
$("#dl-plan").addEventListener("click", () => guard(async () => {
  $("#dl-plan-result").innerHTML = `<div class="plan-box thinking">Asking each source for exact file sizes and checksums…</div>`;
  const ids = [...state.selected];
  const p = await api("/api/fetch/plan", { ids, subsets: subsetFor(ids) });
  const sel = r => r.selection ? `, ${r.selection.groups.length} ${plural(state.byId[r.id]?.acquisition?.subset?.unit)}` : "";
  $("#dl-plan-result").innerHTML = `<div class="plan-box">
    <strong>${fmtBytes(p.total)} to download.</strong> ${p.fits ? "Fits the budget." : "Over budget: the download will be refused."}
    <ul>${p.rows.map(r => `<li>${esc(state.byId[r.id]?.name || r.id)}: ${r.error ? `<span class="state blocked">blocked</span> ${esc(r.error)}` : `${r.files.length} files${esc(sel(r))}, ${fmtBytes(r.bytes)}${r.files.some(f => f.integrity === "trust_on_first_use") ? " (no publisher checksum; hashed on arrival)" : ""}`}</li>`).join("")}</ul></div>`;
}));
$("#dl-start").addEventListener("click", () => guard(async () => {
  const ids = [...state.selected];
  await api("/api/fetch/start", { ids, allow_big: $("#allow-big").checked, subsets: subsetFor(ids) });
  ids.forEach(dropSubset);
  state.selected.clear();
  state.openSubset = null;
  $("#dl-plan-result").innerHTML = "";
  toast("Download started.");
  renderTiers(); updateSelection();
  pollJobs();
}));

let pollTimer = null;
async function pollJobs() {
  clearTimeout(pollTimer);
  const { jobs } = await api("/api/jobs");
  const wasActive = state.jobs.some(j => j.state === "running" || j.state === "planning");
  state.jobs = jobs;
  renderJobs(); updateActivity();
  const active = jobs.some(j => j.state === "running" || j.state === "planning");
  if (active) pollTimer = setTimeout(() => guard(pollJobs), 1000);
  if (wasActive && !active) {
    await loadCatalog(); await loadStorage(); renderTiers(); renderCatalog();
    toast(jobs[0]?.state === "done" ? "Download finished and verified." : `Download ${jobs[0]?.state}. See activity for details.`, jobs[0]?.state !== "done");
  }
}
function renderJobs() {
  if (!state.jobs.length) return;
  $("#jobs").innerHTML = state.jobs.map(j => `
    <div class="job"><div class="job-head"><strong>Started ${new Date(j.started * 1000).toLocaleTimeString()}</strong>
      <span><span class="state ${esc(j.state)}">${esc(j.state)}</span>
      ${j.state === "running" || j.state === "planning" ? `<button class="btn small" data-cancel="${esc(j.id)}">Cancel</button>` : ""}</span></div>
      <ul class="job-items">${j.items.map(i => {
        const pct = i.total ? Math.min(100, (i.done / i.total) * 100) : i.state === "done" ? 100 : 0;
        return `<li><div class="row"><span>${esc(state.byId[i.id]?.name || i.id)}</span><span class="state ${esc(i.state)}">${esc(i.state)}${i.total && i.state === "downloading" ? ` ${fmtBytes(i.done)} of ${fmtBytes(i.total)}` : ""}</span></div>
          <div class="meter-track"><div class="meter-fill" data-w="${pct}"></div></div>${i.error ? `<small class="state failed">${esc(i.error)}</small>` : ""}</li>`;
      }).join("")}</ul>
      ${j.log.length ? `<div class="log">${esc(j.log.join("\n"))}</div>` : ""}</div>`).join("");
  setWidths($("#jobs"));
}
$("#jobs").addEventListener("click", e => {
  const b = e.target.closest("[data-cancel]");
  if (b) guard(async () => { await api("/api/fetch/cancel", { id: b.dataset.cancel }); toast("Cancelling. Partial files are kept so the next download resumes."); });
});
loaders.downloads = () => guard(async () => { renderTiers(); updateSelection(); await pollJobs(); });

/* ---------------- datasets ---------------- */
let currentAudit = null;
async function loadDatasets() {
  const locals = state.records.filter(r => r.record_type === "dataset" && r.local);
  $("#local-datasets").innerHTML = locals.map(r => `<li><button class="linkish" data-inv="${esc(r.id)}">${esc(r.name)}</button></li>`).join("") ||
    `<li class="empty">No datasets downloaded yet. Get the starter set from Downloads.</li>`;
  const { manifests } = await api("/api/manifests");
  $("#manifest-list").innerHTML = manifests.map(m => `<li><button class="linkish" data-audit="${esc(m.path)}" data-ds="${esc(m.dataset_id)}">${esc(m.path)}</button> <span class="hint">${fmtBytes(m.bytes)}</span></li>`).join("") ||
    `<li class="empty">No manifests yet.</li>`;
  await loadDatasetEvidence();
}
async function loadDatasetEvidence() {
  const panel = $("#dataset-evidence");
  try {
    const data = await api("/api/datasets/btxrd/evidence");
    if (!data.available) {
      panel.innerHTML = `<h2>BTXRD evidence review</h2><p>${esc(data.note)}</p>`;
      return;
    }
    const o = data.observations, e = data.evidence;
    const names = { patient_id: "Patient mapping", lesion_id: "Lesion mapping", grouping_reference: "Grouping evidence", reference_standard: "Diagnostic reference standard", reference_evidence: "Diagnostic evidence reference" };
    panel.innerHTML = `<div class="audit-head"><h2>BTXRD evidence review</h2><span class="badge not">Evidence unresolved</span></div>
      <p class="hint">${esc(data.note)}</p>
      <div class="evidence-stats"><div><strong>${esc(o.images.toLocaleString())}</strong><span>source images</span></div><div><strong>${esc(o.exact_duplicate_pairs)}</strong><span>exact duplicate pairs</span></div><div><strong>${esc(o.conflicting_images)}</strong><span>copies with conflicting labels</span></div></div>
      <p>${Object.entries(o.class_counts).map(([label,n]) => `${esc(n.toLocaleString())} ${esc(label)}`).join(" · ")} images. These are source label counts, not verified patient counts.</p>
      <h3>Evidence still missing</h3><table class="counts evidence-counts"><thead><tr><th>Required evidence</th><th>Rows missing</th></tr></thead><tbody>${Object.entries(e.missing_counts).map(([key,n]) => `<tr><td>${esc(names[key] || key)}</td><td>${esc(n.toLocaleString())}</td></tr>`).join("")}</tbody></table>
      <p class="hint">${e.source_binding_reported ? `The saved evidence report matched ${esc(e.matched_image_count.toLocaleString())} rows to source bytes.` : "The saved report does not establish a source-byte match."} No current archive or model was inspected to open this panel.</p>
      <details class="evidence-details"><summary>Audit findings and next actions</summary><p>${esc(o.pairs_crossing_original_lists)} duplicate pairs cross the authors' original split lists; ${esc(o.original_extension_mismatches)} filename extensions differ. ${esc(o.subtype_label_differences)} subtype-label ${o.subtype_label_differences === 1 ? "difference needs" : "differences need"} review. Duplicate checks cannot establish patient independence.</p><ul>${data.next_actions.map(a => `<li>${esc(a)}</li>`).join("")}</ul><p>For an explicit check of a local archive or returned evidence file, inspect the CLI options:</p>${data.commands.map(c=>`<p><code>${esc(c)}</code></p>`).join("")}<p class="hint">These help commands do not acquire data or run a model.</p></details>
      <div class="evidence-actions"><button class="btn" id="export-evidence-template">Export blank evidence template</button><span class="hint">Public source IDs/flags/hashes; patient and diagnostic evidence fields stay blank.</span></div>
      <details class="evidence-details"><summary>Snapshot provenance</summary><p class="hint">File hashes check consistency with the published handoff; they do not authenticate the publisher or medical assertions.</p><p class="mono">Archive SHA-256: ${esc(data.archive_sha256)}</p>${data.files.map(f=>`<p class="mono">${esc(f.name)}<br>${esc(f.sha256)}</p>`).join("")}</details>`;
    $("#export-evidence-template").addEventListener("click", () => guard(async () => {
      const result = await api("/api/datasets/btxrd/evidence-template");
      const url = URL.createObjectURL(new Blob([result.csv], { type: "text/csv;charset=utf-8" }));
      const link = document.createElement("a"); link.href = url; link.download = result.filename; link.click();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
      toast(`Exported a blank template for ${result.rows.toLocaleString()} source images. No cohort or execution permission created.`);
    }));
  } catch (error) {
    panel.innerHTML = `<h2>BTXRD evidence review</h2><p class="hint">The published snapshot could not be loaded. Local manifest audits remain available.</p>`;
  }
}
$("#local-datasets").addEventListener("click", e => {
  const b = e.target.closest("[data-inv]");
  if (!b) return;
  markActive(b);
  guard(async () => {
    const inv = await api(`/api/inventory/${encodeURIComponent(b.dataset.inv)}`);
    $("#inventory").innerHTML = `<h3>${esc(state.byId[inv.id].name)}</h3>
      <p class="hint">${fmtBytes(inv.bytes)} in <code>${esc(inv.root)}</code></p>
      <div class="facts">${Object.entries(inv.extensions).map(([k, v]) => `<span class="pill">${esc(v)} ${esc(k)}</span>`).join("")}</div>
      <table class="counts"><thead><tr><th>Folder</th><th>Files</th></tr></thead><tbody>${Object.entries(inv.folders).map(([k, v]) => `<tr><td><code>${esc(k)}</code></td><td>${v}</td></tr>`).join("")}</tbody></table>`;
  });
});
$("#manifest-list").addEventListener("click", e => {
  const b = e.target.closest("[data-audit]");
  if (b) { markActive(b); runAudit({ path: b.dataset.audit, dataset_id: b.dataset.ds }); }
});
$("#audit-synthetic").addEventListener("click", () => runAudit({ synthetic: true }));
function markActive(b) { $$("#screen-datasets .tree .linkish").forEach(x => x.classList.toggle("active", x === b)); }
function runAudit(src) {
  guard(async () => {
    currentAudit = src;
    renderAudit(await api("/api/audit", src), src);
  });
}
function renderAudit(rep, src) {
  const parts = Object.keys(rep.class_counts).sort();
  const labels = [...new Set(parts.flatMap(p => Object.keys(rep.class_counts[p])))].sort();
  $("#audit-panel").innerHTML = `<div class="audit">
    <div class="audit-head"><h2>${src.synthetic ? "Synthetic demo manifest" : esc(src.path)}</h2>
      <span>${rep.synthetic ? '<span class="badge synthetic">Synthetic data</span> ' : ""}<span class="badge ${rep.ready_for_training ? "ready" : "not"}">${rep.ready_for_training ? "Ready for training" : "Not ready for training"}</span></span></div>
    ${rep.saved ? `<p>Saved split to <code>${esc(rep.saved)}</code> with a sidecar recording the seed, fractions and source checksum.</p>` : ""}
    <p class="hint">${esc(rep.rows)} rows. ${esc(rep.note)}</p>
    ${rep.findings.length ? `<ul class="findings">${rep.findings.map(f => `<li class="${esc(f.severity)}"><b>${esc(f.code.replace(/_/g, " "))}</b>: ${esc(f.detail)}</li>`).join("")}</ul>` : "<p>No findings.</p>"}
    <table class="counts"><thead><tr><th>Partition</th><th>Patients</th>${labels.map(l => `<th>${esc(l)}</th>`).join("")}</tr></thead>
      <tbody>${parts.map(p => `<tr><td>${esc(p)}</td><td>${rep.patients_per_partition[p] ?? 0}</td>${labels.map(l => `<td>${rep.class_counts[p][l] ?? 0}</td>`).join("")}</tr>`).join("")}</tbody></table>
    <form class="split-form" id="split-form">
      <label>Train<input name="train" type="number" step="0.05" min="0" max="1" value="0.7"></label>
      <label>Validation<input name="val" type="number" step="0.05" min="0" max="1" value="0.15"></label>
      <label>Test<input name="test" type="number" step="0.05" min="0" max="1" value="0.15"></label>
      <label>Seed<input name="seed" value="0"></label>
      <label>Name<input name="name" placeholder="split-seed0" ${src.synthetic ? "disabled" : ""}></label>
      <button class="btn" type="submit" name="preview" value="1">Preview grouped split</button>
      <button class="btn primary" type="submit" name="save" value="1" ${src.synthetic ? 'disabled title="Synthetic demo splits can’t be saved"' : ""}>Save split</button>
    </form></div>`;
  $("#split-form").addEventListener("submit", e => {
    e.preventDefault();
    const f = e.target, save = e.submitter?.name === "save";
    guard(async () => {
      const rep2 = await api("/api/split", { ...src, fractions: { train: f.train.value, val: f.val.value, test: f.test.value }, seed: f.seed.value, name: f.name.value, save });
      renderAudit(rep2, src);
      if (save) { toast("Split saved."); loadDatasets(); }
    });
  });
}
loaders.datasets = () => guard(loadDatasets);

/* ---------------- images ---------------- */
const PAGE = 48;
const img = { src: "btxrd", meta: null, rows: [], byId: {}, uploads: [], upById: {}, runs: [], review: null, page: 0,
  sel: new Map(), live: {}, liveRun: null, scoring: null, scoreTimer: null, scoreClock: null,
  batch: [], open: null, overlay: true, f: { part: "test" } };
const keyOf = (set, id) => `${set}:${id}`;
const media = (set, file) => `/media/${encodeURIComponent(set)}/${file.split("/").map(encodeURIComponent).join("/")}?t=${encodeURIComponent(TOKEN)}`;
const fmtP = p => (p == null ? "" : p.toFixed(2));
const humanize = s => ({ image_stratified: "image split", source_holdout: "source hold-out", three_class: "3-class" }[s] ?? String(s).replaceAll("_", " "));
const variantTag = (variant, selected) => (variant && variant !== "pad" ? ` · ${variant}${selected ? " (selected)" : ""}` : variant ? " · pad" : "");
function setWidths(root) { $$("[data-w]", root).forEach(el => { el.style.width = `${Math.max(0, Math.min(100, Number(el.dataset.w)))}%`; }); }
function selectedResult() {
  const run = img.runs.find(r => r.id === $("#img-tools").run.value);
  return run && run.results.find(r => r.id === $("#img-tools").result.value) ? { run: run.id, result: $("#img-tools").result.value } : null;
}

function setRunResults() {
  const t = $("#img-tools"), run = img.runs.find(r => r.id === t.run.value);
  t.result.innerHTML = run ? run.results.map(r => `<option value="${esc(r.id)}">${esc(`${humanize(r.protocol)} · ${humanize(r.endpoint)} · ${r.encoder}${variantTag(r.variant, r.selected)}`)} (test ${r.macro ? "macro " : ""}AUC ${fmtP(r.roc_auc)})</option>`).join("") : "";
  t.result.disabled = !run;
}
async function loadImages() {
  const firstLoad = !img.meta;
  if (firstLoad) {
    img.meta = await api("/api/images");
    const [{ runs }, set] = await Promise.all([api("/api/runs"), img.meta.sets[0]?.available ? api("/api/images/btxrd") : null]);
    img.runs = runs;
    if (set) { img.rows = set.rows; img.byId = Object.fromEntries(set.rows.map(r => [r.sample_id, r])); }
    const t = $("#img-tools");
    t.run.innerHTML = `<option value="">None (browse images only)</option>` + runs.map(r => `<option value="${esc(r.id)}">${esc(r.id)}</option>`).join("");
    const miss = img.meta.ml_missing;
    $("#img-ml").textContent = miss.length ? `Live scoring is off in this app process: ${miss.join(", ")} not installed. Start it with .venv/bin/python -m cancer_workbench app.` : "";
  }
  await loadUploads();
  if (firstLoad) await resumeScore();
  renderFilters(); renderImages();
}
async function resumeScore() {
  const { job } = await api("/api/score/current");
  if (!job) return;
  img.scoring = job;
  const t = $("#img-tools");
  t.run.value = job.run;
  setRunResults(); t.result.value = job.result;
  img.review = await api("/api/runs/review", { run: job.run, result: job.result });
  img.batch = job.keys.map(key => itemFromKey(key) || { key, title: key });
  for (const it of img.batch) {
    const item = itemFromKey(it.key);
    if (item) img.sel.set(it.key, { set: item.set, id: item.id });
  }
  if (img.batch.every(it => it.key.startsWith("uploads:"))) {
    img.src = "uploads"; $("#upload-zone").hidden = false;
    $$("#img-source button").forEach(b => b.classList.toggle("on", b.dataset.src === img.src));
  }
  renderScoring();
  if (scoringActive()) img.scoreClock = setInterval(updateScoreClock, 1000);
  await pollScore();
}
async function loadUploads() {
  img.uploads = (await api("/api/uploads")).uploads;
  img.upById = Object.fromEntries(img.uploads.map(u => [u.id, u]));
}

$("#img-source").addEventListener("click", e => {
  const b = e.target.closest("[data-src]");
  if (!b) return;
  img.src = b.dataset.src; img.page = 0;
  $$("#img-source button").forEach(x => x.classList.toggle("on", x === b));
  $("#upload-zone").hidden = img.src !== "uploads";
  renderFilters(); renderImages();
});
$("#img-tools").addEventListener("change", e => guard(async () => {
  const t = $("#img-tools");
  if (e.target === t.run) setRunResults();
  img.review = null;
  img.live = {}; img.liveRun = null; img.scoring = null;
  $("#img-live").innerHTML = "";
  $("#img-scoring").hidden = true;
  const sr = selectedResult();
  if (sr) img.review = await api("/api/runs/review", sr);
  img.page = 0;
  renderFilters(); renderImages();
  if (img.open) openImage(img.open);
}));

function opts(values, cur, all = "All") {
  return `<option value="">${esc(all)}</option>` + values.map(v => `<option value="${esc(v)}" ${v === cur ? "selected" : ""}>${esc(v)}</option>`).join("");
}
function renderFilters() {
  const f = img.f, el = $("#img-filters");
  if (img.src === "uploads") {
    el.innerHTML = `<label class="grow">Search name<input name="q" type="search" value="${esc(f.q || "")}"></label>`;
    return;
  }
  const uniq = k => [...new Set(img.rows.map(r => r[k]).filter(Boolean))].sort();
  const rv = img.review;
  el.innerHTML = `
    <label>Label<select name="label">${opts(["normal", "benign", "malignant", "unlabeled"], f.label)}</select></label>
    <label>Center<select name="center">${opts(uniq("center"), f.center)}</select></label>
    <label>View<select name="view">${opts(uniq("view"), f.view)}</select></label>
    <label>Region<select name="region">${opts(uniq("region"), f.region)}</select></label>
    <label>Annotations<select name="ann">${opts(["yes", "no"], f.ann, "Any")}</select></label>
    <label>Audit flags<select name="flags">${opts(["flagged"], f.flags, "Any")}</select></label>
    ${rv ? `<label>In this run<select name="part">${["test", "val", "train", "excluded"].map(p => `<option ${f.part === p ? "selected" : ""}>${p}</option>`).join("")}<option value="all" ${f.part === "all" ? "selected" : ""}>all</option></select></label>
    <label>Prediction<select name="pred">${opts(["wrong", "right"], f.pred, "Any")}</select></label>
    <label>Sort<select name="sort">${[["", "Image id"], ["conf_desc", "Most confident first"], ["conf_asc", "Least confident first"], ...(rv.positive_class ? [["pos_desc", `P(${rv.positive_class}) high to low`]] : [])].map(([v, l]) => `<option value="${v}" ${f.sort === v ? "selected" : ""}>${esc(l)}</option>`).join("")}</select></label>` : ""}
    <label class="grow">Search id<input name="q" type="search" value="${esc(f.q || "")}" placeholder="IMG000123"></label>`;
}
$("#img-filters").addEventListener("input", e => {
  const el = e.target;
  if (!el.name) return;
  img.f[el.name] = el.value; img.page = 0;
  renderImages();
});
$("#img-filters").addEventListener("submit", e => e.preventDefault());

function visibleItems() {
  const f = img.f, q = (f.q || "").trim().toLowerCase();
  if (img.src === "uploads") {
    return img.uploads.filter(u => !q || u.original_name.toLowerCase().includes(q))
      .map(u => ({ key: keyOf("uploads", u.id), set: "uploads", id: u.id, title: u.original_name, url: media("uploads", u.file) }));
  }
  const rv = img.review?.rows;
  let rows = img.rows.filter(r => (!f.label || (f.label === "unlabeled" ? !r.label : r.label === f.label)) &&
    (!f.center || r.center === f.center) && (!f.view || r.view === f.view) && (!f.region || r.region === f.region) &&
    (!f.ann || (f.ann === "yes") === (Number(r.annotation_shapes) > 0)) && (!f.flags || !!r.audit_flags) &&
    (!q || r.sample_id.toLowerCase().includes(q)));
  if (rv) {
    rows = rows.filter(r => {
      const v = rv[r.sample_id];
      if (!v) return f.part === "all";
      return (f.part === "all" || v.partition === f.part) && (!f.pred || (v.pred != null && (f.pred === "wrong") === !v.correct));
    });
    const conf = r => { const p = rv[r.sample_id]?.probs; return p ? Math.max(...p) : -1; };
    if (f.sort === "conf_desc") rows.sort((a, b) => conf(b) - conf(a));
    if (f.sort === "conf_asc") rows.sort((a, b) => (conf(a) < 0) - (conf(b) < 0) || conf(a) - conf(b));
    if (f.sort === "pos_desc") rows.sort((a, b) => (rv[b.sample_id]?.probs?.[1] ?? -1) - (rv[a.sample_id]?.probs?.[1] ?? -1));
  }
  return rows.map(r => ({ key: keyOf("btxrd", r.sample_id), set: "btxrd", id: r.sample_id, title: r.sample_id, url: media("btxrd", r.file), row: r, rv: rv?.[r.sample_id] }));
}

function predTag(v) {
  if (!v || v.probs == null) return "";
  return `<span class="tag ${v.correct ? "ok" : "bad"}" title="Prediction saved by the run for this ${esc(v.partition)} image, checked against its label">${v.correct ? "" : "✗ "}${esc(v.pred)} ${fmtP(Math.max(...v.probs))}</span>`;
}
function renderImages() {
  const items = visibleItems(), rv = img.review;
  const pages = Math.max(1, Math.ceil(items.length / PAGE));
  img.page = Math.min(img.page, pages - 1);
  img.pageItems = items.slice(img.page * PAGE, img.page * PAGE + PAGE);
  if (img.src === "btxrd" && !img.rows.length) {
    $("#img-summary").textContent = "No BTXRD manifest yet. Download BTXRD, then run python -m cancer_workbench btxrd manifest.";
  } else if (rv) {
    const scored = items.filter(i => i.rv?.probs);
    const wrong = scored.filter(i => !i.rv.correct).length;
    $("#img-summary").textContent = `${items.length} images in this view. ${scored.length ? `${wrong} of the ${scored.length} saved predictions disagree with the label` : "None has a saved prediction (the run only predicts val and test images)"}${rv.threshold != null ? `; ${rv.positive_class} when P ≥ ${fmtP(rv.threshold)} (val threshold)` : "; argmax over classes"}. Counts in a filtered view are for finding patterns, not performance: the run's summary.md has the test-set results. ${rv.label}`;
  } else {
    $("#img-summary").textContent = img.src === "uploads" ? `${items.length} uploaded image${items.length === 1 ? "" : "s"}.` : `${items.length} of ${img.rows.length} images. Pick a trained model to compare its predictions with these labels.`;
  }
  $("#img-grid").innerHTML = img.pageItems.map(it => {
    const r = it.row, live = img.live[it.key];
    return `<div class="img-card${img.sel.has(it.key) ? " picked" : ""}${img.open === it.key ? " cur" : ""}">
      <button type="button" class="thumb" data-open="${esc(it.key)}" aria-label="Open ${esc(it.title)}"><img loading="lazy" src="${esc(it.url)}" alt=""></button>
      <label class="pick"><input type="checkbox" data-pick="${esc(it.key)}" aria-label="Select ${esc(it.title)}" ${img.sel.has(it.key) ? "checked" : ""} ${scoringActive() ? "disabled" : ""}><span class="mono" title="${esc(it.title)}">${esc(it.title)}</span></label>
      <div class="tags">${r ? `<span class="tag">${esc(rv ? (it.rv?.label || it.rv?.partition || "") : (r.label || "unlabeled"))}</span>` : ""}
        ${it.rv ? partTag(it.rv) : ""}${predTag(it.rv)}${live?.probs ? `<span class="tag live">live ${esc(live.pred)}</span>` : ""}</div></div>`;
  }).join("") || `<p class="empty">No images match these filters.</p>`;
  $("#img-pager").innerHTML = pages > 1 ? `<button class="btn small" data-page="-1" ${img.page ? "" : "disabled"}>Previous</button><span>Page ${img.page + 1} of ${pages}</span><button class="btn small" data-page="1" ${img.page < pages - 1 ? "" : "disabled"}>Next</button>` : "";
  updateImgSelection();
}
function partTag(v) { return img.f.part === "all" ? `<span class="tag">${esc(v.partition)}</span>` : ""; }
$("#img-pager").addEventListener("click", e => {
  const b = e.target.closest("[data-page]");
  if (!b) return;
  img.page += Number(b.dataset.page);
  renderImages();
  $("#img-grid").scrollIntoView({ block: "start", behavior: "smooth" });
});
function itemFromKey(key) {
  const [set, id] = [key.slice(0, key.indexOf(":")), key.slice(key.indexOf(":") + 1)];
  if (set === "uploads") { const u = img.upById[id]; return u && { key, set, id, title: u.original_name, url: media("uploads", u.file), up: u }; }
  const r = img.byId[id];
  return r && { key, set, id, title: id, url: media(set, r.file), row: r, rv: img.review?.rows[id] };
}
$("#img-grid").addEventListener("change", e => {
  const cb = e.target.closest("[data-pick]");
  if (!cb) return;
  const it = itemFromKey(cb.dataset.pick);
  cb.checked ? img.sel.set(it.key, { set: it.set, id: it.id }) : img.sel.delete(it.key);
  cb.closest(".img-card").classList.toggle("picked", cb.checked);
  updateImgSelection();
});
$("#img-grid").addEventListener("click", e => { const b = e.target.closest("[data-open]"); if (b) openImage(b.dataset.open); });
$("#img-select-page").addEventListener("click", () => {
  for (const it of img.pageItems || []) {
    if (img.sel.size >= (img.meta?.max_score ?? 24)) break;
    img.sel.set(it.key, { set: it.set, id: it.id });
  }
  renderImages();
});
$("#img-clear").addEventListener("click", () => { img.sel.clear(); renderImages(); });
function scoringActive() { return img.scoring?.state === "running"; }
function updateImgSelection() {
  const n = img.sel.size, max = img.meta?.max_score ?? 24, sr = selectedResult(), busy = scoringActive();
  const selectedMetadata = sr && img.runs.find(r => r.id === sr.run)?.results.find(r => r.id === sr.result);
  const bound = selectedMetadata?.has_binding === true;
  const shown = (img.pageItems || []).filter(it => img.sel.has(it.key)).length;
  $("#img-selected").textContent = n ? `${n} of ${max} images selected` : "No images selected";
  const b = $("#img-score");
  const why = busy ? "Scoring this batch. You can keep browsing images." : !sr ? "Choose a training run and trained model first." : !bound ? "Replay only: this legacy run needs measured feature/head bindings before live scoring." : img.meta?.ml_missing?.length ? "Live scoring needs the ml extra; see the note below." : !n ? "Tick images below to build a scoring batch." : n > max ? `Select at most ${max} images.` : "";
  $("#img-ready").textContent = why || `Ready to score${n > shown ? ` · ${n - shown} selected outside this page` : ""}`;
  b.disabled = !!why; b.title = why;
  b.textContent = busy ? "Scoring…" : n ? `Score ${n} image${n === 1 ? "" : "s"} live` : "Score selected live";
  $("#img-clear").disabled = busy || !n;
  const pick = $("#img-select-page");
  pick.textContent = `Select up to ${max}`;
  pick.disabled = busy || n >= max || !(img.pageItems || []).some(it => !img.sel.has(it.key));
  $("#img-tools").run.disabled = busy;
  $("#img-tools").result.disabled = busy || !sr;
  $$("[data-pick]", $("#img-grid")).forEach(cb => { cb.disabled = busy; });
  if ($("#img-delete")) $("#img-delete").disabled = busy;
  $("#img-run-context").textContent = img.review ? `Predictions are checked against each image's dataset label: green tags match it, red ✗ tags disagree. Saved predictions cover validation and test images. ${bound ? `Live scoring checks the measured identity of ${img.review.encoder}${img.review.variant !== "pad" ? ` (${img.review.variant} preprocessing)` : ""} and this ${humanize(img.review.endpoint)} classifier, and refuses the images it was trained on.` : "This legacy run can be replayed but not scored live. Regenerate a bound exploratory run first."}` : "Pick a training run, then one of the models it trained. Its predictions are checked against each image's label from the dataset.";
}

function probBars(probs, classes, pred, threshold) {
  return `<div class="probs">${classes.map((c, i) => `<div class="prob-row${c === pred ? " pred" : ""}"><span>${esc(c)}</span><div class="bar"><i data-w="${probs[i] * 100}"></i>${threshold != null && i === 1 ? `<b class="thr" data-left="${threshold * 100}" title="Val threshold ${fmtP(threshold)}"></b>` : ""}</div><span class="v">${fmtP(probs[i])}</span></div>`).join("")}</div>`;
}
async function openImage(key) {
  const it = itemFromKey(key);
  if (!it) return;
  img.open = key;
  $$("#img-grid .img-card").forEach(c => c.classList.toggle("cur", c.querySelector("[data-open]")?.dataset.open === key));
  const rv = img.review, v = it.rv, live = img.live[key], r = it.row;
  const box = $("#img-detail");
  const meta = r ? [["Label (manifest)", r.label || "unlabeled"], ["Raw indicators", r.label_raw], ["Subtype", r.subtype], ["Site", r.site], ["Region", r.region], ["View", r.view],
    ["Center", r.center], ["Age / sex", [r.age, r.gender].filter(Boolean).join(" / ")], ["Duplicate group", r.duplicate_group], ["Audit flags", r.audit_flags], ["File", r.file]]
    : [["Original name", it.up.original_name], ["Size", fmtBytes(it.up.bytes)], ["Uploaded", it.up.uploaded_at], ["sha256", it.up.sha256]];
  box.innerHTML = `
    <h2>${esc(it.title)}</h2>
    ${Number(r?.annotation_shapes) > 0 ? `<label class="check"><input type="checkbox" id="img-overlay" ${img.overlay ? "checked" : ""}> Show tumor annotations (${esc(r.annotation_shapes)})</label>` : ""}
    <div class="stage"><img id="img-full" src="${esc(it.url)}" alt="${esc(it.title)}"><svg id="img-svg" aria-hidden="true"></svg></div>
    <ul class="shape-list" id="img-shapes"></ul>
    ${rv ? `<h3>Saved prediction vs label</h3>${v?.probs ? `<p class="hint">In this model's ${esc(v.partition)} set. Label: <strong>${esc(v.label)}</strong>. Predicted: <strong class="${v.correct ? "ok-text" : "err-text"}">${esc(v.pred)}</strong>${v.correct ? "" : " (wrong)"}.</p>${probBars(v.probs, rv.classes, v.pred, rv.threshold)}`
      : `<p class="hint">${v ? (v.partition === "excluded" ? `Not in this run's cohort: ${esc(v.why)}.` : `A ${esc(v.partition)} image: the run stores predictions for val and test images only.`) : "Not in this run."}</p>`}` : ""}
    ${live ? `<h3>Live score</h3>${liveDetail(live)}` : ""}
    <h3>Details</h3>
    <dl>${meta.filter(([, x]) => x).map(([k, x]) => `<dt>${esc(k)}</dt><dd>${esc(x)}</dd>`).join("")}</dl>
    ${it.up ? `<div class="actions"><button class="btn danger" id="img-delete" ${scoringActive() ? "disabled" : ""}>Delete upload</button></div>` : ""}`;
  setWidths(box);
  $$("[data-left]", box).forEach(el => { el.style.left = `${el.dataset.left}%`; });
  $("#img-overlay")?.addEventListener("change", e => { img.overlay = e.target.checked; $("#img-svg").classList.toggle("off", !img.overlay); });
  $("#img-delete")?.addEventListener("click", () => {
    if (!confirm(`Delete ${it.up.original_name} from data/uploads?`)) return;
    guard(async () => {
      await api("/api/uploads/delete", { id: it.id });
      img.sel.delete(key); delete img.live[key]; img.open = null;
      box.innerHTML = `<p class="empty">Upload deleted.</p>`;
      await loadUploads(); renderImages();
    });
  });
  if (Number(r?.annotation_shapes) > 0) {
    const a = await api(`/api/annotation/${encodeURIComponent(it.set)}/${encodeURIComponent(it.id)}`);
    if (img.open !== key || !a.width) return;
    const svg = $("#img-svg");
    svg.setAttribute("viewBox", `0 0 ${a.width} ${a.height}`);
    svg.setAttribute("preserveAspectRatio", "none");
    svg.classList.toggle("off", !img.overlay);
    svg.innerHTML = a.shapes.map(s => {
      const pts = s.points;
      if (s.type === "rectangle" && pts.length === 2) {
        const [[x1, y1], [x2, y2]] = pts;
        return `<rect class="shape" x="${Math.min(x1, x2)}" y="${Math.min(y1, y2)}" width="${Math.abs(x2 - x1)}" height="${Math.abs(y2 - y1)}"></rect>`;
      }
      return `<polygon class="shape" points="${pts.map(p => p.join(",")).join(" ")}"></polygon>`;
    }).join("");
    $("#img-shapes").innerHTML = a.shapes.map(s => `<li><span class="mono">${esc(s.type)}</span> ${esc(s.label)}</li>`).join("");
  }
}
function liveDetail(e) {
  const m = img.liveRun;
  if (e.refused) return `<p class="err-text">${esc(e.refused)}</p>`;
  if (e.error) return `<p class="err-text">Could not score: ${esc(e.error)}</p>`;
  return `<p class="hint">${esc(m.result)} on ${esc(m.device)}.${e.label ? ` Label: <strong>${esc(e.label)}</strong>.` : " No label to check against."} Predicted: <strong>${esc(e.pred)}</strong>.</p>
    ${probBars(e.probs, m.classes, e.pred, m.threshold)}
    ${e.stored_probs ? `<p class="hint">Prediction saved by the run: ${m.classes.map((c, i) => `${esc(c)} ${fmtP(e.stored_probs[i])}`).join(", ")}. Largest difference ${Math.max(...e.stored_probs.map((p, i) => Math.abs(p - e.probs[i]))).toFixed(4)}.</p>` : ""}
    ${e.notes.map(n => `<p class="hint warn-text">${esc(n)}</p>`).join("")}`;
}

$("#img-score").addEventListener("click", async () => {
  const sr = selectedResult();
  if (!sr || scoringActive() || $("#img-score").disabled) return;
  const items = [...img.sel.values()];
  img.batch = items.map(it => itemFromKey(keyOf(it.set, it.id)));
  img.live = {}; img.liveRun = null;
  $("#img-live").innerHTML = "";
  img.scoring = { ...sr, state: "running", stage: "preparing", done: 0, total: items.length, items: [], started: Date.now() / 1000 };
  renderScoring(); renderImages();
  if (img.open) openImage(img.open);
  $("#img-scoring").scrollIntoView({ behavior: "smooth", block: "start" });
  img.scoreClock = setInterval(updateScoreClock, 1000);
  try {
    img.scoring = await api("/api/score/start", { ...sr, items });
    await pollScore();
  } catch (err) {
    img.scoring.state = "failed"; img.scoring.error = err.message;
    finishScore();
  }
});
function updateScoreClock() {
  const job = img.scoring;
  if (!job) return;
  const seconds = scoringActive() ? Math.max(0, Math.floor(Date.now() / 1000 - job.started)) : Math.round(job.seconds || 0);
  $("#img-elapsed").textContent = `${seconds}s elapsed`;
}
function renderScoring() {
  const j = img.scoring;
  if (!j) return;
  $("#img-scoring").hidden = false;
  const titles = { preparing: "Checking the selected model", head: "Loading the classifier", scoring: "Scoring images", done: "Batch complete", failed: "Scoring stopped" };
  $("#img-scoring-title").textContent = titles[j.state === "failed" ? "failed" : j.stage];
  $("#img-scoring-context").textContent = `${j.run} / ${j.result}`;
  const step = j.state === "done" ? 3 : ({ preparing: 0, head: 1, scoring: 2 }[j.stage] ?? -1);
  $("#img-scoring-steps").innerHTML = ["Check model", "Load classifier", "Score images", "Review results"].map((label, i) => `<li class="${i < step ? "complete" : i === step ? "current" : ""}" ${i === step ? 'aria-current="step"' : ""}><span>${i < step ? "✓" : i + 1}</span>${label}</li>`).join("");
  $("#img-score-count").textContent = `${j.done} of ${j.total} images processed`;
  const scored = j.items.filter(e => e.probs).length, refused = j.items.filter(e => e.refused).length, failed = j.items.filter(e => e.error).length;
  $("#img-score-outcomes").textContent = `${scored} scored · ${refused} refused · ${failed} failed`;
  $("#img-score-progress").max = j.total;
  $("#img-score-progress").value = j.done;
  const current = itemFromKey(j.current || "");
  $("#img-score-current").textContent = j.state === "done" ? "All images processed. Review scores and any refusals below." : j.state === "failed" ? "Completed image results are kept below. Select images to try again." : j.current ? `Processing ${current?.title || j.current}. The encoder loads on its first image; this can take a minute.` : j.stage === "head" ? "Loading a saved head, or rebuilding and verifying it against this run. This may take a minute." : "Preparing the batch. Progress advances only when an image has been processed.";
  $("#img-score-error").hidden = !j.error;
  $("#img-score-error").textContent = j.error || "";
  $("#img-score-queue").innerHTML = img.batch.map(it => {
    const e = j.items.find(e => e.key === it.key);
    const status = e?.refused ? "Refused" : e?.error ? "Failed" : e?.probs ? `Scored · ${e.pred}` : j.current === it.key ? "Processing" : j.state === "failed" ? "Not processed" : "Queued";
    return `<li><button class="linkish mono" type="button" data-open="${esc(it.key)}">${esc(it.title)}</button><span class="${e?.error || e?.refused ? "err-text" : e?.probs ? "ok-text" : "hint"}">${esc(status)}</span></li>`;
  }).join("");
  updateScoreClock(); updateImgSelection(); updateActivity();
}
async function pollScore() {
  clearTimeout(img.scoreTimer);
  $("#img-score-reconnect").hidden = true;
  try {
    const previous = img.scoring.done;
    img.scoring = await api(`/api/score/jobs/${encodeURIComponent(img.scoring.id)}`);
    const j = img.scoring;
    if (j.metadata || j.response) {
      img.liveRun = j.response || { ...j.metadata, seconds: j.seconds, items: j.items };
      for (const e of j.items) img.live[e.key] = e;
      if (j.items.length) renderLive(img.liveRun);
    }
    renderScoring();
    if (j.done !== previous) {
      renderImages();
      if (img.open) openImage(img.open);
    }
    if (scoringActive()) img.scoreTimer = setTimeout(pollScore, 500);
    else finishScore();
  } catch (err) {
    if (err.status === 404 || err.status === 403) {
      img.scoring.state = "failed"; img.scoring.stage = "failed"; img.scoring.error = err.message;
      finishScore();
      return;
    }
    $("#img-score-error").hidden = false;
    $("#img-score-error").textContent = `Progress connection interrupted: ${err.message} The batch may still be running. Reconnect or reload this page to resume following it.`;
    $("#img-score-reconnect").hidden = false;
  }
}
function finishScore() {
  clearInterval(img.scoreClock); clearTimeout(img.scoreTimer);
  renderScoring(); renderImages();
  if (img.open) openImage(img.open);
}
$("#img-score-reconnect").addEventListener("click", pollScore);
$("#img-score-queue").addEventListener("click", e => {
  const b = e.target.closest("[data-open]");
  if (b) { openImage(b.dataset.open); $("#img-detail").scrollIntoView({ behavior: "smooth", block: "nearest" }); }
});
function renderLive(res) {
  const labeled = res.items.filter(e => e.correct != null);
  const right = labeled.filter(e => e.correct).length;
  $("#img-live").innerHTML = `<div class="live">
    <div class="audit-head"><h2>${scoringActive() ? "Results so far" : "Live scores"}</h2><span class="badge synthetic">Exploratory</span></div>
    <p class="hint">${esc(res.run)} / ${esc(res.result)}, encoder ${esc(res.encoder)}${res.variant && res.variant !== "pad" ? ` (${esc(res.variant)} preprocessing)` : ""} on ${esc(res.device)}, ${res.seconds} s. ${res.threshold != null ? `${esc(res.positive_class)} when P ≥ ${fmtP(res.threshold)}.` : "Argmax over classes."}
      ${labeled.length ? `${right} of ${labeled.length} labeled images match their dataset label${labeled.some(e => e.partition === "val") ? ", including val images, which are optimistic" : ""}.` : ""} ${esc(res.note)}</p>
    <div class="table-scroll" tabindex="0" role="region" aria-label="Live score results"><table><thead><tr><th aria-label="Preview"></th><th>Image</th><th>Split</th><th>Label</th><th>Live</th><th>Saved by run</th><th>Notes</th></tr></thead><tbody>
    ${res.items.map(e => {
      const it = itemFromKey(e.key);
      const probs = p => res.classes.map((c, i) => `${esc(c)} ${fmtP(p[i])}`).join("<br>");
      return `<tr><td>${it ? `<button type="button" class="thumb small" data-open="${esc(e.key)}" aria-label="Open ${esc(it.title)}"><img src="${esc(it.url)}" alt=""></button>` : ""}</td>
        <td class="mono">${esc(it?.title || e.key)}</td><td>${esc(e.partition)}</td><td>${esc(e.label || "none")}</td>
        <td>${e.refused ? '<span class="err-text">refused</span>' : e.error ? '<span class="err-text">failed</span>' : `<strong class="${e.correct === false ? "err-text" : e.correct ? "ok-text" : ""}">${esc(e.pred)}</strong><br><small>${probs(e.probs)}</small>`}</td>
        <td>${e.stored_probs ? `<small>${probs(e.stored_probs)}</small>` : ""}</td>
        <td><small>${[e.refused, e.error, ...e.notes].filter(Boolean).map(esc).join("<br>")}</small></td></tr>`;
    }).join("")}</tbody></table></div></div>`;
}
$("#img-live").addEventListener("click", e => { const b = e.target.closest("[data-open]"); if (b) { openImage(b.dataset.open); $("#img-detail").scrollIntoView({ behavior: "smooth", block: "nearest" }); } });

async function uploadFiles(files) {
  const max = img.meta?.max_upload ?? 20e6;
  let ok = 0;
  for (const file of files) {
    if (file.size > max) { toast(`${file.name} is over ${fmtBytes(max)}.`, true); continue; }
    const data = await new Promise((resolve, reject) => {
      const rd = new FileReader();
      rd.onload = () => resolve(String(rd.result).split(",", 2)[1] || "");
      rd.onerror = () => reject(new Error(`Could not read ${file.name}.`));
      rd.readAsDataURL(file);
    });
    try { await api("/api/uploads/add", { name: file.name, data }); ok++; } catch (e) { toast(`${file.name}: ${e.message}`, true); }
  }
  if (ok) toast(`Uploaded ${ok} image${ok === 1 ? "" : "s"}.`);
  await loadUploads(); renderImages();
}
$("#upload-input").addEventListener("change", e => { guard(() => uploadFiles([...e.target.files])); e.target.value = ""; });
const zone = $("#upload-zone");
zone.addEventListener("dragover", e => { e.preventDefault(); zone.classList.add("over"); });
zone.addEventListener("dragleave", () => zone.classList.remove("over"));
zone.addEventListener("drop", e => { e.preventDefault(); zone.classList.remove("over"); guard(() => uploadFiles([...e.dataTransfer.files])); });
loaders.images = () => guard(loadImages);

/* ---------------- assistant ---------------- */
const chat = { profiles: {}, defaultName: null, picked: new Set(), up: {}, turns: {}, histories: {}, editing: null };
async function loadProfiles() {
  const p = await api("/api/coordinator/profiles");
  chat.profiles = p.profiles; chat.defaultName = p.default;
  $("#config-file").innerHTML = p.is_local ? `Saved in <code>${esc(p.config_file)}</code>.` : `Showing the example config. Saving a model creates <code>configs/coordinator.json</code>.`;
  if (!chat.picked.size && p.default) chat.picked.add(p.default);
  for (const n of [...chat.picked]) if (!p.profiles[n]) chat.picked.delete(n);
  renderProfiles(); renderColumns();
}
function renderProfiles() {
  $("#profile-list").innerHTML = Object.entries(chat.profiles).map(([name, p]) => `
    <li class="${chat.picked.has(name) ? "picked" : ""}">
      <input type="checkbox" data-pick="${esc(name)}" ${chat.picked.has(name) ? "checked" : ""} aria-label="Use ${esc(name)}">
      <span class="pname">${esc(name)}${name === chat.defaultName ? ' <span class="pill">default</span>' : ""}</span>
      <span class="dot ${chat.up[name] === true ? "up" : chat.up[name] === false ? "down" : ""}" title="${chat.up[name] === true ? "Reachable" : chat.up[name] === false ? "Not reachable" : "Not tested"}"></span>
      <span class="pmeta">${esc(p.model)}<br>${esc(p.base_url)}${p.base_url_env ? ` (or $${esc(p.base_url_env)})` : ""}</span>
      <span class="pactions"><button class="linkish" data-ping="${esc(name)}">Test connection</button><button class="linkish" data-edit="${esc(name)}">Edit</button></span>
    </li>`).join("");
}
$("#profile-list").addEventListener("change", e => {
  const cb = e.target.closest("[data-pick]");
  if (!cb) return;
  cb.checked ? chat.picked.add(cb.dataset.pick) : chat.picked.delete(cb.dataset.pick);
  renderProfiles(); renderColumns();
});
$("#profile-list").addEventListener("click", e => {
  const ping = e.target.closest("[data-ping]"), edit = e.target.closest("[data-edit]");
  if (ping) guard(async () => {
    ping.textContent = "Testing…";
    const r = await api("/api/coordinator/ping", { profile: ping.dataset.ping });
    chat.up[ping.dataset.ping] = r.ok;
    renderProfiles();
    toast(r.ok ? `${ping.dataset.ping} is reachable. Models served: ${r.models.join(", ") || "none listed"}.` : r.error, !r.ok);
  });
  if (edit) openProfileForm(edit.dataset.edit);
});
function openProfileForm(name) {
  const f = $("#profile-form");
  f.hidden = false; f.reset(); $("#profile-error").textContent = "";
  chat.editing = name || null;
  $("#profile-form-title").textContent = name ? `Edit ${name}` : "Add a model";
  $("#profile-delete").hidden = !name;
  f.name.readOnly = !!name;
  if (name) {
    const p = chat.profiles[name];
    f.name.value = name; f.base_url.value = p.base_url || ""; f.model.value = p.model || ""; f.api_key_env.value = p.api_key_env || "";
    f.extra_body.value = p.extra_body && Object.keys(p.extra_body).length ? JSON.stringify(p.extra_body) : "";
    f.timeout_s.value = p.timeout_s || 120; f.make_default.checked = name === chat.defaultName;
  }
  f.name.focus();
}
$("#profile-new").addEventListener("click", () => openProfileForm(null));
$("#profile-cancel").addEventListener("click", () => ($("#profile-form").hidden = true));
$("#profile-form").addEventListener("submit", e => {
  e.preventDefault();
  const f = e.target;
  let extra = {};
  if (f.extra_body.value.trim()) {
    try { extra = JSON.parse(f.extra_body.value); } catch { $("#profile-error").textContent = "Extra request fields must be valid JSON, for example {\"temperature\": 0.2}."; return; }
  }
  const old = chat.editing ? chat.profiles[chat.editing] : {};
  const profile = { ...old, base_url: f.base_url.value.trim(), model: f.model.value.trim(), api_key_env: f.api_key_env.value.trim(), extra_body: extra, timeout_s: Number(f.timeout_s.value) || 120 };
  api("/api/coordinator/profiles/save", { name: f.name.value.trim(), profile, make_default: f.make_default.checked })
    .then(() => { f.hidden = true; toast("Model saved."); return loadProfiles(); })
    .catch(err => ($("#profile-error").textContent = err.message));
});
$("#profile-delete").addEventListener("click", () => {
  if (!chat.editing || !confirm(`Delete the profile ${chat.editing}? This only removes it from configs/coordinator.json.`)) return;
  api("/api/coordinator/profiles/delete", { name: chat.editing })
    .then(() => { chat.picked.delete(chat.editing); $("#profile-form").hidden = true; toast("Model deleted."); return loadProfiles(); })
    .catch(err => ($("#profile-error").textContent = err.message));
});

function renderTurn(t) {
  if (t.pending) return `<div class="turn"><div class="q">${esc(t.q)}</div><div class="thinking">Waiting for the model…</div></div>`;
  const r = t.result;
  if (r.error) return `<div class="turn"><div class="q">${esc(t.q)}</div><div class="err">${esc(r.error)}</div></div>`;
  const calls = r.steps.flatMap(s => s.tool_calls);
  const latency = r.steps.reduce((a, s) => a + (s.latency_s || 0), 0);
  const tokens = r.steps.reduce((a, s) => a + (s.usage?.total_tokens || 0), 0);
  return `<div class="turn"><div class="q">${esc(t.q)}</div>
    ${calls.map(c => {
      const bad = !!c.observed.error || ["rejected", "failed"].includes(c.observed.result?.status);
      const status = c.observed.error ? "error" : c.observed.result?.status || "returned a result";
      return `<details class="call${bad ? " bad" : ""}"><summary>Called <code>${esc(c.name)}</code>: ${esc(status)}</summary>
        <pre>arguments ${esc(c.arguments)}\n\nobserved ${esc(JSON.stringify(c.observed, null, 2))}</pre></details>`;
    }).join("")}
    <div class="a">${r.final ? esc(r.final) : '<span class="err">Stopped after the step limit without a final answer.</span>'}</div>
    <div class="meta">${calls.length} tool call${calls.length === 1 ? "" : "s"}, ${latency.toFixed(1)} s${tokens ? `, ${tokens} tokens` : ""}</div></div>`;
}
function renderColumns() {
  const names = [...chat.picked];
  if (!names.length) { $("#chat-columns").innerHTML = `<p class="empty">Tick one model to chat, or several to compare their answers side by side.</p>`; return; }
  $("#chat-columns").innerHTML = names.map(n => `<div class="column"><div class="column-head"><strong>${esc(n)}</strong><span class="model">${esc(chat.profiles[n]?.model)}</span></div>
    ${(chat.turns[n] || []).map(renderTurn).join("") || '<p class="empty">No messages yet.</p>'}</div>`).join("");
}
$("#ask-form").addEventListener("submit", e => {
  e.preventDefault();
  const f = e.target, q = f.question.value.trim(), names = [...chat.picked];
  if (!q) return;
  if (!names.length) { toast("Tick at least one model first.", true); return; }
  const btn = f.querySelector("button[type=submit]");
  btn.disabled = true;
  for (const n of names) (chat.turns[n] ||= []).push({ q, pending: true });
  renderColumns();
  f.question.value = "";
  api("/api/coordinator/ask", { question: q, profiles: names, histories: chat.histories, synthetic_demo: f.synthetic_demo.checked })
    .then(({ results }) => {
      results.forEach((r, i) => {
        const n = names[i], turn = chat.turns[n].findLast(t => t.pending);
        Object.assign(turn, { pending: false, result: r });
        if (r.messages) chat.histories[n] = r.messages;
        if (r.error) chat.up[n] = false; else chat.up[n] = true;
      });
    })
    .catch(err => { for (const n of names) { const t = chat.turns[n].findLast(t => t.pending); if (t) Object.assign(t, { pending: false, result: { error: err.message } }); } })
    .finally(() => { btn.disabled = false; renderProfiles(); renderColumns(); });
});
$("#ask-form").question.addEventListener("keydown", e => { if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) $("#ask-form").requestSubmit(); });
$("#chat-reset").addEventListener("click", () => { chat.turns = {}; chat.histories = {}; renderColumns(); });
loaders.assistant = () => guard(loadProfiles);

/* ---------------- progress ---------------- */
const NEXT_MARK = { " ": "~", "~": "x", "x": " " };
function renderProgress(p) {
  $("#owners tbody").innerHTML = p.owners.map(o => `<tr><td><strong>${esc(o.ws)}</strong></td><td>${md(o.focus)}</td><td>${md(o.depends)}</td>
    <td><input value="${esc(o.owner)}" placeholder="Claim it" data-owner-line="${o.line}" data-ws="${esc(o.ws)}" aria-label="Owner of workstream ${esc(o.ws)}"></td></tr>`).join("");
  const blocks = [];
  for (const s of p.sections) {
    if (s.level === 2 || !blocks.length) blocks.push({ title: s.title, parts: [] });
    blocks[blocks.length - 1].parts.push(s);
  }
  const tally = b => { const items = b.parts.flatMap(s => s.items); return [items.filter(i => i.mark === "x").length, items.length]; };
  $("#progress-outline").innerHTML = `<li><button class="linkish" data-goto="owners-head">Who owns what</button></li>` + blocks.map((b, n) => {
    const [done, total] = tally(b);
    return `<li><button class="linkish" data-goto="sec-${n}"><span>${md(b.title)}</span><span class="cnt">${done}/${total}</span></button></li>`;
  }).join("");
  $("#checklist").innerHTML = blocks.map((b, n) => {
    const [done, total] = tally(b);
    return `<section class="section-block" id="sec-${n}"><div class="section-head"><h2>${md(b.title)}</h2><span class="count">${done} of ${total} done</span></div>
      <div class="section-bar"><div data-w="${total ? (done / total) * 100 : 0}"></div></div>
      ${b.parts.map(s => `${s.level === 3 ? `<h3 class="lvl3">${md(s.title)}</h3>` : ""}<ul class="items">${s.items.map(i => `
        <li class="${i.mark === "x" ? "done" : ""} ${i.blocked ? "blocked" : ""}">
          <button class="mark ${i.mark === "x" ? "x" : i.mark === "~" ? "p" : ""}" data-line="${i.line}" data-mark="${esc(i.mark)}"
            aria-label="${i.mark === "x" ? "Done" : i.mark === "~" ? "In progress" : "Not started"}. Change status"></button>
          <span class="txt">${md(i.text.replace("🔒", "").trim())}</span></li>`).join("")}</ul>`).join("")}</section>`;
  }).join("");
  setWidths($("#checklist"));
  state.progress = p;
}
$("#progress-outline").addEventListener("click", e => {
  const b = e.target.closest("[data-goto]");
  if (b) document.getElementById(b.dataset.goto)?.scrollIntoView({ behavior: "smooth", block: "start" });
});
$("#checklist").addEventListener("click", e => {
  const b = e.target.closest("button.mark");
  if (!b) return;
  const line = Number(b.dataset.line);
  const item = state.progress.sections.flatMap(s => s.items).find(i => i.line === line);
  guard(async () => renderProgress(await api("/api/progress/mark", { line, text: item.text, mark: NEXT_MARK[b.dataset.mark] })));
});
$("#owners").addEventListener("change", e => {
  const inp = e.target.closest("[data-owner-line]");
  if (inp) guard(async () => { renderProgress(await api("/api/progress/owner", { line: Number(inp.dataset.ownerLine), ws: inp.dataset.ws, name: inp.value })); toast(`Workstream ${inp.dataset.ws} owner saved.`); });
});
loaders.progress = () => guard(async () => renderProgress(await api("/api/progress")));

/* ---------------- experiments ---------------- */
const experiments = { items: [], preview: null, detail: null };
const experimentForm = $("#experiment-form");
const PATH_NAMES = { specialist_tools: "Specialist tool", transfer_learning: "Transfer learning", distillation: "Teacher-guided distillation" };
const experimentStateLabel = s => String(s ?? "unknown").replaceAll("_", " ").replace(/^./, c => c.toUpperCase());

function experimentInputs() {
  return { question: experimentForm.question.value, reuse_path: experimentForm.reuse_path.value,
    model_id: experimentForm.model_id.value, manifest: experimentForm.manifest.value,
    planned_bytes: Number(experimentForm.planned_bytes.value), synthetic: experimentForm.synthetic.checked };
}
function experimentMode() {
  const synthetic = experimentForm.synthetic.checked;
  for (const name of ["model_id", "manifest", "planned_bytes"]) experimentForm[name].closest("label").hidden = synthetic;
  $("#experiment-example-note").hidden = !synthetic;
  experimentForm.model_id.disabled = synthetic;
  experimentForm.manifest.disabled = synthetic;
  experimentForm.planned_bytes.disabled = synthetic;
  if (synthetic) experimentForm.planned_bytes.value = "0";
}
function invalidateExperiment() {
  experiments.preview = null;
  $("#experiment-save").disabled = true;
  $("#experiment-error").textContent = "";
  $("#experiment-preview").innerHTML = `<h2>Draft review</h2><p class="empty">Inputs changed. Preview the current draft to refresh its checks.</p>`;
}
function renderExecutionReview(review) {
  if (!review) return "";
  return `<h3>Before execution</h3><p>${esc(review.input_binding)}</p><p>${esc(review.evidence_scope)}</p>
    <dl class="experiment-facts"><dt>Model revision</dt><dd class="mono">${esc(review.model_revision || "Not recorded")}</dd>
      <dt>Execution</dt><dd>Not authorized. Job dispatch is unavailable in this workspace.</dd></dl>
    <ul class="experiment-blockers">${review.required_review.map(r => `<li><strong>${esc(r.label)}:</strong> ${esc(r.detail)}</li>`).join("")}</ul>
    <p class="hint">${esc(review.note)}</p>`;
}
function renderExperimentPreview(d) {
  experiments.preview = d;
  const p = d.plan;
  $("#experiment-preview").innerHTML = `<div class="experiment-review-head"><h2>${p.state === "blocked" ? "Needs review" : "Draft checks passed"}</h2>${d.synthetic ? '<span class="badge synthetic">Synthetic example</span>' : ""}</div>
    <p>${p.state === "blocked" ? "Resolve these blockers before progressing the experiment." : "This draft is ready for protocol review. It does not authorize execution."}</p>
    <dl class="experiment-facts"><dt>Model</dt><dd>${esc(p.model_id)}</dd><dt>Reuse path</dt><dd>${esc(PATH_NAMES[p.path])}</dd>
      <dt>Dataset</dt><dd>${esc(d.audit.dataset_id)} · ${d.audit.rows} rows</dd><dt>Manifest identity</dt><dd class="mono">${esc(d.manifest.sha256)}</dd>
      <dt>Storage reservation</dt><dd>${fmtBytes(p.budget.planned_bytes)} additional · ${fmtBytes(p.budget.used_bytes)} used of ${fmtBytes(p.budget.limit_bytes)}</dd></dl>
    ${p.blockers.length ? `<h3>Blockers</h3><ul class="experiment-blockers">${p.blockers.map(b => `<li>${esc(b)}</li>`).join("")}</ul>` : ""}
    <h3>Dataset audit</h3>${d.audit.findings.length ? `<ul class="experiment-blockers">${d.audit.findings.map(f => `<li>${esc(f.code)}: ${esc(f.detail)}</li>`).join("")}</ul>` : '<p>No findings in these declared-record checks.</p>'}
    ${renderExecutionReview(d.execution_review)}
    <p class="hint">${esc(p.note)}</p><p class="hint">${esc(d.note)}</p>`;
  $("#experiment-save").disabled = false;
}
function renderExperimentHistory() {
  const query = $("#experiment-search").value.toLowerCase();
  const items = experiments.items.filter(r => [r.id, r.model, r.task, r.state, r.kind].join(" ").toLowerCase().includes(query));
  $("#experiment-history").innerHTML = items.length ? `<div class="table-scroll"><table class="records"><thead><tr><th scope="col">Record</th><th scope="col">Question / task</th><th scope="col">Model</th><th scope="col">Saved state</th></tr></thead><tbody>${items.map(r => `<tr><td><button class="link" type="button" data-experiment-key="${esc(r.key)}">${r.kind === "draft" ? "Draft" : "Run record"} ${esc(r.id)}</button>${r.synthetic ? '<span class="badge synthetic">Synthetic</span>' : ""}</td><td>${esc(r.task)}</td><td>${esc(r.model)}</td><td>${esc(experimentStateLabel(r.state))}</td></tr>`).join("")}</tbody></table></div>` : `<p class="empty">${experiments.items.length ? "No records match this search." : "No saved drafts or experiment records yet. Preview a draft above to start."}</p>`;
}
async function refreshExperimentHistory() {
  const history = await api("/api/experiments/history");
  experiments.items = history.items;
  $("#experiment-history-warnings").innerHTML = history.warnings.length ? `<ul class="experiment-blockers">${history.warnings.map(w => `<li>${esc(w)}</li>`).join("")}</ul>` : "";
  renderExperimentHistory();
}
async function openExperiment(key) {
  const d = await api("/api/experiments/record", { key });
  experiments.detail = d;
  const el = $("#experiment-detail");
  el.hidden = false;
  const r = d.record, draft = d.kind === "draft", p = r.plan || {};
  const facts = draft ? [["Saved state", experimentStateLabel(p.state)], ["Question", r.question || "Unspecified"], ["Model", p.model_id],
    ["Dataset", p.dataset_id], ["Manifest SHA-256", r.manifest?.sha256], ["Created", r.created_at],
    ["Source revision", r.source_revision], ["Execution scope", "Review only. This draft authorizes no execution."]] :
    [["Recorded state", experimentStateLabel(r.state)], ["Task", r.task], ["Model", r.model], ["Cohort", r.cohort], ["Split", r.split],
     ["Source revision", r.source_revision], ["Execution scope", r.execution_scope], ["Outputs", list(r.outputs) || "Not recorded"]];
  const blockers = draft ? p.blockers || [] : r.blockers || [];
  el.innerHTML = `<h2>${draft ? "Saved draft" : "Recorded experiment"}${r.synthetic ? ' <span class="badge synthetic">Synthetic</span>' : ""}</h2>
    <p class="mono">${esc(d.file)}</p><p class="hint">${esc(d.note || r.note)}</p>
    <dl class="experiment-facts">${facts.map(([label, value]) => `<dt>${esc(label)}</dt><dd>${esc(value ?? "Not recorded")}</dd>`).join("")}</dl>
    ${blockers.length ? `<h3>Recorded blockers</h3><ul class="experiment-blockers">${blockers.map(b => `<li>${esc(b)}</li>`).join("")}</ul>` : ""}
    ${draft ? renderExecutionReview(r.execution_review) : ""}
    <details><summary>Full record JSON</summary><pre tabindex="0" aria-label="Saved record JSON">${esc(JSON.stringify(r, null, 2))}</pre></details>`;
  $("#experiment-export").hidden = false;
}
experimentForm.addEventListener("input", invalidateExperiment);
experimentForm.synthetic.addEventListener("change", () => { experimentMode(); invalidateExperiment(); });
experimentForm.addEventListener("submit", async e => {
  e.preventDefault();
  const button = experimentForm.querySelector('[type="submit"]');
  button.disabled = true;
  $("#experiment-save").disabled = true;
  $("#experiment-error").textContent = "";
  const inputs = experimentInputs();
  try {
    const result = await api("/api/experiments/preview", inputs);
    if (JSON.stringify(inputs) === JSON.stringify(experimentInputs())) renderExperimentPreview(result);
  }
  catch (err) { $("#experiment-error").textContent = err.message; }
  finally { button.disabled = false; }
});
$("#experiment-save").addEventListener("click", async () => {
  $("#experiment-save").disabled = true;
  const inputs = experimentInputs();
  try {
    const result = await api("/api/experiments/save", inputs);
    if (JSON.stringify(inputs) === JSON.stringify(experimentInputs())) renderExperimentPreview(result.draft);
    await refreshExperimentHistory();
    await openExperiment(result.key);
    toast("Draft saved. No experiment was launched.");
  } catch (err) { $("#experiment-error").textContent = err.message; }
  finally { $("#experiment-save").disabled = !experiments.preview; }
});
$("#experiment-history").addEventListener("click", e => {
  const button = e.target.closest("[data-experiment-key]");
  if (button) guard(() => openExperiment(button.dataset.experimentKey));
});
$("#experiment-refresh").addEventListener("click", () => guard(refreshExperimentHistory));
$("#experiment-search").addEventListener("input", renderExperimentHistory);
$("#experiment-export").addEventListener("click", () => {
  if (!experiments.detail) return;
  const blob = new Blob([JSON.stringify(experiments.detail.record, null, 2) + "\n"], { type: "application/json" });
  const url = URL.createObjectURL(blob), link = document.createElement("a");
  link.href = url; link.download = "oncolohealth-experiment-record.json"; link.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
});
loaders.experiments = () => guard(async () => {
  const options = await api("/api/experiments/options");
  for (const [field, rows, empty] of [["model_id", options.models.map(m => [m.id, m.name]), "Select a model"],
    ["manifest", options.manifests.map(m => [m.path, m.path]), "Select a local manifest"]]) {
    const prior = experimentForm[field].value;
    experimentForm[field].innerHTML = `<option value="">${empty}</option>` + rows.map(([v, label]) => `<option value="${esc(v)}">${esc(label)}</option>`).join("");
    if (rows.some(([v]) => v === prior)) experimentForm[field].value = prior;
  }
  experimentMode();
  await refreshExperimentHistory();
});

/* ---------------- boot ---------------- */
guard(async () => {
  await Promise.all([loadCatalog(), loadStorage()]);
  show(location.hash.slice(1));
  pollJobs();
});
