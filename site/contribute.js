// Contribute form: builds the submission file that `catalog contribute` accepts, with the same checks
// as cancer_workbench/registry/contrib.py, and delivers it the way config.js says.
(() => {
  const SCHEMA = "oncolohealth-contribution/1";
  const cfg = window.ONCOLO_SITE || { submitMode: "download" };
  const form = document.getElementById("contrib");
  const todo = document.getElementById("todo");
  const preview = document.getElementById("preview");
  const status = document.getElementById("status");
  const https = v => /^https:\/\/[^\s/]+\.[^\s]+$/.test(v || "");
  const list = v => (v || "").split(",").map(s => s.trim().toLowerCase()).filter(Boolean);

  function submission() {
    const f = new FormData(form);
    const get = k => (f.get(k) || "").toString().trim();
    const type = get("type");
    const sub = {
      schema: SCHEMA, type, name: get("name"), summary: get("summary"), link: get("link"),
      citation: get("citation"), modality: list(get("modality")), anatomy: list(get("anatomy")),
      license_id: get("license_id"), access: get("access"),
      commercial: get("commercial") === "" ? null : get("commercial") === "true",
      contributor_name: get("contributor_name"), affiliation: get("affiliation"),
      rights_confirmed: f.get("rights_confirmed") === "on",
      contains_identifiable_data: f.get("no_identifiable") === "on" ? false : null,
    };
    if (type === "model") Object.assign(sub, { model_kind: get("model_kind"), tasks: list(get("tasks")), input: get("input"), outputs: get("outputs") });
    else Object.assign(sub, { images: get("images"), patients: get("patients"), patient_ids: get("patient_ids"), labels: get("labels") });
    if (!sub.citation) delete sub.citation;
    return sub;
  }

  function checks(sub) {
    const items = [
      ["A name and a one-line summary", sub.name && sub.summary],
      ["An https link to the files", https(sub.link)],
      ["Citation is an https link (or left blank)", !sub.citation || https(sub.citation)],
      ["Scan type and body part", sub.modality.length && sub.anatomy.length],
      ["A license", sub.license_id],
      ["Your name", sub.contributor_name],
      ["You may share it under that license", sub.rights_confirmed],
      ["No identifiable patient information", sub.contains_identifiable_data === false],
    ];
    if (sub.type === "model") items.push(["At least one task", sub.tasks.length]);
    if (sub.type === "dataset" && /\D/.test(sub.images + sub.patients)) items.push(["Image and patient counts are whole numbers", false]);
    return items.map(([text, ok]) => ({ text, ok: Boolean(ok) }));
  }

  function render() {
    form.dataset.type = new FormData(form).get("type");
    const sub = submission();
    const items = checks(sub);
    todo.replaceChildren(...items.map(i => Object.assign(document.createElement("li"), { textContent: i.text, className: i.ok ? "done" : "" })));
    preview.textContent = JSON.stringify(sub, null, 2);
    return { sub, ready: items.every(i => i.ok) };
  }

  function download(sub) {
    const blob = new Blob([JSON.stringify(sub, null, 2) + "\n"], { type: "application/json" });
    const a = Object.assign(document.createElement("a"), { href: URL.createObjectURL(blob), download: `${sub.type}-${sub.name.toLowerCase().replace(/[^a-z0-9]+/g, "-")}.json` });
    a.click();
    URL.revokeObjectURL(a.href);
  }

  async function deliver(sub) {
    if (cfg.submitMode === "endpoint" && cfg.endpoint) {
      const r = await fetch(cfg.endpoint, { method: "POST", headers: { "Content-Type": "application/json", Accept: "application/json" }, body: JSON.stringify(sub) });
      if (!r.ok) throw new Error(`the server answered ${r.status}`);
      return "Thanks. Your contribution was sent for review.";
    }
    if (cfg.submitMode === "github" && cfg.githubRepo) {
      const body = "Submitted from the OncoloHealth contribute page.\n\n```json\n" + JSON.stringify(sub, null, 2) + "\n```\n";
      window.open(`https://github.com/${cfg.githubRepo}/issues/new?labels=contribution&title=${encodeURIComponent(`Contribution: ${sub.name}`)}&body=${encodeURIComponent(body)}`, "_blank", "noopener");
      return "A prefilled GitHub issue opened in a new tab. Submit it there.";
    }
    download(sub);
    return cfg.contactEmail ? `Saved. Email the file to ${cfg.contactEmail}.` : "Saved. Send the file to the OncoloHealth team.";
  }

  form.addEventListener("input", render);
  form.addEventListener("change", render);
  form.addEventListener("submit", async e => {
    e.preventDefault();
    const { sub, ready } = render();
    if (!ready) {
      status.className = "status err";
      status.textContent = "A few things are still missing. See the checklist.";
      return;
    }
    try {
      status.className = "status ok";
      status.textContent = await deliver(sub);
    } catch (err) {
      status.className = "status err";
      status.textContent = `Couldn't send it: ${err.message}. Your answers are still here.`;
    }
  });
  render();
})();
