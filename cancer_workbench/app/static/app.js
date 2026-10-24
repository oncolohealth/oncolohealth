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

/* ---------------- navigation ---------------- */
const SCREENS = ["catalog", "downloads", "datasets", "images", "assistant", "progress"];
const loaders = {};
function show(name) {
  if (!SCREENS.includes(name)) name = "catalog";
  for (const s of SCREENS) $(`#screen-${s}`).hidden = s !== name;
  $$(".nav-btn").forEach(b => { if (b.dataset.screen !== name) b.removeAttribute("aria-current"); else b.setAttribute("aria-current", "page"); });
  if (location.hash !== `#${name}`) history.replaceState(null, "", `#${name}`);
  loaders[name]?.();
}
$$(".nav-btn").forEach(b => b.addEventListener("click", () => show(b.dataset.screen)));

/* ---------------- shared state ---------------- */
const state = { records: [], byId: {}, storage: null, selected: new Set(), jobs: [], typeFilter: "" };

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
  hf.className = `token-state ${s.hf_token ? "ok" : "no"}`;
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
  return `<div class="ladder-big" aria-hidden="true">${LADDER.map((_, i) => `<div class="${i <= r ? "on" : ""}" style="height:${8 + i * 6}px"></div>`).join("")}</div>
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
      ${r.local ? `<button class="btn" data-act="prov">View provenance</button>` : acq.tier && acq.tier !== "manual" ? `<button class="btn primary" data-act="queue">Add to downloads</button>` : ""}
    </div>
    <div id="detail-extra"></div>`;
  $$("#catalog-table tbody tr").forEach(tr => tr.classList.toggle("sel", tr.dataset.id === id));
  box.querySelector('[data-act="prov"]')?.addEventListener("click", () => guard(async () => {
    const p = await api(`/api/provenance/${encodeURIComponent(id)}`);
    $("#detail-extra").innerHTML = `<h3>Provenance</h3><p class="hint">Retrieved ${esc(p.retrieved_at)}. ${esc(p.note)}</p><pre class="prov">${esc(JSON.stringify(p.files.map(f => ({ path: f.path, bytes: f.bytes, sha256: f.sha256, integrity: f.integrity })), null, 2))}</pre>`;
  }));
  box.querySelector('[data-act="queue"]')?.addEventListener("click", () => {
    state.selected.add(id);
    show("downloads");
    toast(`${r.name} added to the download selection.`);
  });
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
    const selectable = recs.filter(r => !r.local && tier !== "manual" && !(tier === "gated" && !hf));
    const rows = recs.map(r => {
      if (tier === "manual") return `<li class="manual"><div><strong>${esc(r.name)}</strong><div class="why">${esc(r.acquisition.instructions)}</div></div></li>`;
      const disabled = r.local || (tier === "gated" && !hf);
      const why = r.local ? "On disk" : tier === "gated" && !hf ? "Needs HF_TOKEN" : "";
      return `<li><input type="checkbox" data-id="${esc(r.id)}" aria-label="Select ${esc(r.name)}" ${state.selected.has(r.id) ? "checked" : ""} ${disabled ? "disabled" : ""}>
        <div><strong>${esc(r.name)}</strong><div class="why">${esc(r.summary || "")}</div></div>
        <span>${licenseShort(r.license)}${r.access?.startsWith("gated") ? ' <span class="pill gated">gated</span>' : ""}</span>
        <span class="num">${why ? `<span class="${r.local ? "local-yes" : "why"}">${esc(why)}</span>` : fmtBytes(r.acquisition.approx_bytes)}</span></li>`;
    }).join("");
    return `<section class="tier"><div class="tier-head"><div><h2>${esc(title)}</h2><p>${esc(desc)}</p></div>
      ${selectable.length ? `<button class="btn small" data-tier="${tier}">Select all ${selectable.length}</button>` : ""}</div>
      <ul class="tier-rows">${rows}</ul></section>`;
  }).join("");
}
function updateSelection() {
  for (const id of [...state.selected]) if (state.byId[id]?.local) state.selected.delete(id);
  const ids = [...state.selected];
  const bytes = ids.reduce((s, id) => s + (state.byId[id]?.acquisition?.approx_bytes || 0), 0);
  $("#dl-selected").textContent = ids.length ? `${ids.length} selected, about ${fmtBytes(bytes)}` : "Nothing selected";
  $("#dl-start").disabled = !ids.length;
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
  cb.checked ? state.selected.add(cb.dataset.id) : state.selected.delete(cb.dataset.id);
  updateSelection();
});
$("#tiers").addEventListener("click", e => {
  const b = e.target.closest("[data-tier]");
  if (!b) return;
  $$(`#tiers input[data-id]:not(:disabled)`).forEach(cb => { if (state.byId[cb.dataset.id].acquisition.tier === b.dataset.tier) { cb.checked = true; state.selected.add(cb.dataset.id); } });
  updateSelection();
});
$("#dl-plan").addEventListener("click", () => guard(async () => {
  $("#dl-plan-result").innerHTML = `<div class="plan-box thinking">Asking each source for exact file sizes and checksums…</div>`;
  const p = await api("/api/fetch/plan", { ids: [...state.selected] });
  $("#dl-plan-result").innerHTML = `<div class="plan-box">
    <strong>${fmtBytes(p.total)} to download.</strong> ${p.fits ? "Fits the budget." : "Over budget: the download will be refused."}
    <ul>${p.rows.map(r => `<li>${esc(state.byId[r.id]?.name || r.id)}: ${r.error ? `<span class="state blocked">blocked</span> ${esc(r.error)}` : `${r.files.length} files, ${fmtBytes(r.bytes)}${r.files.some(f => f.integrity === "trust_on_first_use") ? " (no publisher checksum; hashed on arrival)" : ""}`}</li>`).join("")}</ul></div>`;
}));
$("#dl-start").addEventListener("click", () => guard(async () => {
  await api("/api/fetch/start", { ids: [...state.selected], allow_big: $("#allow-big").checked });
  state.selected.clear();
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
  renderJobs();
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
          <div class="meter-track"><div class="meter-fill" style="width:${pct}%"></div></div>${i.error ? `<small class="state failed">${esc(i.error)}</small>` : ""}</li>`;
      }).join("")}</ul>
      ${j.log.length ? `<div class="log">${esc(j.log.join("\n"))}</div>` : ""}</div>`).join("");
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
}
$("#local-datasets").addEventListener("click", e => {
  const b = e.target.closest("[data-inv]");
  if (!b) return;
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
  if (b) runAudit({ path: b.dataset.audit, dataset_id: b.dataset.ds });
});
$("#audit-synthetic").addEventListener("click", () => runAudit({ synthetic: true }));
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
function setWidths(root) { $$("[data-w]", root).forEach(el => { el.style.width = `${Math.max(0, Math.min(100, Number(el.dataset.w)))}%`; }); }
function selectedResult() {
  const run = img.runs.find(r => r.id === $("#img-tools").run.value);
  return run && run.results.find(r => r.id === $("#img-tools").result.value) ? { run: run.id, result: $("#img-tools").result.value } : null;
}

function setRunResults() {
  const t = $("#img-tools"), run = img.runs.find(r => r.id === t.run.value);
  t.result.innerHTML = run ? run.results.map(r => `<option value="${esc(r.id)}">${esc(`${r.protocol} · ${r.endpoint} · ${r.encoder}`)} (${r.macro ? "macro " : ""}AUC ${fmtP(r.roc_auc)})</option>`).join("") : "";
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
    t.run.innerHTML = `<option value="">None: browse only</option>` + runs.map(r => `<option value="${esc(r.id)}">${esc(r.id)}</option>`).join("");
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
  return `<span class="tag ${v.correct ? "ok" : "bad"}" title="Stored ${esc(v.partition)} prediction">${v.correct ? "" : "✗ "}${esc(v.pred)} ${fmtP(Math.max(...v.probs))}</span>`;
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
    $("#img-summary").textContent = `${items.length} images in this view. ${scored.length ? `${wrong} of the ${scored.length} with stored predictions are wrong` : "None has a stored prediction (the run only predicts val and test images)"}${rv.threshold != null ? `; ${rv.positive_class} when P ≥ ${fmtP(rv.threshold)} (val threshold)` : "; argmax over classes"}. Counts in a filtered view are for finding patterns, not performance: the run's summary.md has the test-set results. ${rv.label}`;
  } else {
    $("#img-summary").textContent = img.src === "uploads" ? `${items.length} uploaded image${items.length === 1 ? "" : "s"}.` : `${items.length} of ${img.rows.length} images. Pick a baseline run to see its stored predictions.`;
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
  const shown = (img.pageItems || []).filter(it => img.sel.has(it.key)).length;
  $("#img-selected").textContent = n ? `${n} of ${max} images selected` : "No images selected";
  const b = $("#img-score");
  const why = busy ? "Scoring this batch. You can keep browsing images." : img.meta?.ml_missing?.length ? "Live scoring needs the ml extra; see the note below." : !sr ? "Choose a baseline run and result first." : !n ? "Tick images below to build a scoring batch." : n > max ? `Select at most ${max} images.` : "";
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
  $("#img-run-context").textContent = img.review ? `Stored predictions are available for validation and test images. Live scoring uses ${img.review.encoder} with the selected ${img.review.endpoint.replaceAll("_", " ")} head. Training images will be refused.` : "Choose a baseline run to review predictions or score images live.";
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
    ${rv ? `<h3>Stored prediction</h3>${v?.probs ? `<p class="hint">${esc(v.partition)} image in ${esc(rv.result)}. Reference: <strong>${esc(v.label)}</strong>. Predicted: <strong class="${v.correct ? "ok-text" : "err-text"}">${esc(v.pred)}</strong>${v.correct ? "" : " (wrong)"}.</p>${probBars(v.probs, rv.classes, v.pred, rv.threshold)}`
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
  return `<p class="hint">${esc(m.result)} on ${esc(m.device)}.${e.label ? ` Reference: <strong>${esc(e.label)}</strong>.` : ""} Predicted: <strong>${esc(e.pred)}</strong>.</p>
    ${probBars(e.probs, m.classes, e.pred, m.threshold)}
    ${e.stored_probs ? `<p class="hint">Stored prediction from the run: ${m.classes.map((c, i) => `${esc(c)} ${fmtP(e.stored_probs[i])}`).join(", ")}. Largest difference ${Math.max(...e.stored_probs.map((p, i) => Math.abs(p - e.probs[i]))).toFixed(4)}.</p>` : ""}
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
  const titles = { preparing: "Checking the selected run", head: "Preparing the classifier", scoring: "Scoring images", done: "Batch complete", failed: "Scoring stopped" };
  $("#img-scoring-title").textContent = titles[j.state === "failed" ? "failed" : j.stage];
  $("#img-scoring-context").textContent = `${j.run} / ${j.result}`;
  const step = j.state === "done" ? 3 : ({ preparing: 0, head: 1, scoring: 2 }[j.stage] ?? -1);
  $("#img-scoring-steps").innerHTML = ["Check run", "Prepare head", "Score images", "Review results"].map((label, i) => `<li class="${i < step ? "complete" : i === step ? "current" : ""}" ${i === step ? 'aria-current="step"' : ""}><span>${i < step ? "✓" : i + 1}</span>${label}</li>`).join("");
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
  updateScoreClock(); updateImgSelection();
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
    <p class="hint">${esc(res.run)} / ${esc(res.result)}, encoder ${esc(res.encoder)} on ${esc(res.device)}, ${res.seconds} s. ${res.threshold != null ? `${esc(res.positive_class)} when P ≥ ${fmtP(res.threshold)}.` : "Argmax over classes."}
      ${labeled.length ? `${right} of ${labeled.length} labeled images match the reference label${labeled.some(e => e.partition === "val") ? ", including val images, which are optimistic" : ""}.` : ""} ${esc(res.note)}</p>
    <div class="table-scroll" tabindex="0" role="region" aria-label="Live score results"><table><thead><tr><th aria-label="Preview"></th><th>Image</th><th>In run</th><th>Reference</th><th>Live</th><th>Stored</th><th>Notes</th></tr></thead><tbody>
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
  $("#checklist").innerHTML = blocks.map(b => {
    const items = b.parts.flatMap(s => s.items);
    const done = items.filter(i => i.mark === "x").length;
    return `<section class="section-block"><div class="section-head"><h2>${md(b.title)}</h2><span class="count">${done} of ${items.length} done</span></div>
      <div class="section-bar"><div style="width:${items.length ? (done / items.length) * 100 : 0}%"></div></div>
      ${b.parts.map(s => `${s.level === 3 ? `<h3 class="lvl3">${md(s.title)}</h3>` : ""}<ul class="items">${s.items.map(i => `
        <li class="${i.mark === "x" ? "done" : ""} ${i.blocked ? "blocked" : ""}">
          <button class="mark ${i.mark === "x" ? "x" : i.mark === "~" ? "p" : ""}" data-line="${i.line}" data-mark="${esc(i.mark)}"
            aria-label="${i.mark === "x" ? "Done" : i.mark === "~" ? "In progress" : "Not started"}. Change status"></button>
          <span class="txt">${md(i.text.replace("🔒", "").trim())}</span></li>`).join("")}</ul>`).join("")}</section>`;
  }).join("");
  state.progress = p;
}
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

/* ---------------- boot ---------------- */
guard(async () => {
  await Promise.all([loadCatalog(), loadStorage()]);
  show(location.hash.slice(1));
  pollJobs();
});
