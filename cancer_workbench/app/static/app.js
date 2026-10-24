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
  if (!res.ok) throw new Error(data.error || `Request failed (${res.status})`);
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
const SCREENS = ["catalog", "downloads", "datasets", "assistant", "progress"];
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
