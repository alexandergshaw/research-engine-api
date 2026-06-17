"use strict";

// ---- settings (persisted) -------------------------------------------------
const LS = "research-console";
function loadCfg() {
  try {
    return JSON.parse(localStorage.getItem(LS)) || {};
  } catch {
    return {};
  }
}
function saveCfg(cfg) {
  localStorage.setItem(LS, JSON.stringify(cfg));
}

const $ = (id) => document.getElementById(id);
const cfg = loadCfg();
$("baseUrl").value = cfg.baseUrl || "";
$("apiKey").value = cfg.apiKey || "";

function base() {
  return ($("baseUrl").value || "").replace(/\/+$/, "");
}
function headers(json) {
  const h = {};
  if (json) h["Content-Type"] = "application/json";
  const key = $("apiKey").value.trim();
  if (key) h["X-API-Key"] = key;
  return h;
}

async function apiGet(path) {
  return fetch(base() + path, { headers: headers(false) });
}
async function apiPost(path, body) {
  return fetch(base() + path, {
    method: "POST",
    headers: headers(true),
    body: JSON.stringify(body),
  });
}

function setStatus(text, ok) {
  const el = $("status");
  el.textContent = text;
  el.className =
    "text-xs " + (ok === true ? "text-emerald-400" : ok === false ? "text-rose-400" : "text-slate-400");
}

// ---- run an intent (shared by search + advanced) --------------------------
async function execute(intent, params) {
  setStatus("searching…");
  const t0 = performance.now();
  let r;
  try {
    r = await apiPost("/v1/research", { intent, params });
  } catch (e) {
    renderError("Request failed (network/CORS): " + e.message);
    setStatus("error", false);
    return;
  }
  const ms = Math.round(performance.now() - t0);
  let body;
  try {
    body = await r.json();
  } catch {
    renderError("HTTP " + r.status + " (non-JSON response)");
    setStatus("error", false);
    return;
  }
  if (r.status === 401) {
    renderError("401 — set a valid API key under ⚙ Settings.");
    setStatus("401 — needs API key", false);
    return;
  }
  if (!r.ok) {
    renderError("HTTP " + r.status + " — " + (body.message || body.detail || JSON.stringify(body)));
    setStatus("HTTP " + r.status, false);
    return;
  }
  setStatus("ok · " + ms + " ms", true);
  renderEnvelope(body);
}

function searchConcept() {
  const term = $("q").value.trim();
  if (!term) return;
  execute("concept.overview", { term });
}

// ---- quick picks ----------------------------------------------------------
const QUICK = [
  { label: "TLS overview", intent: "concept.overview", params: { term: "TLS handshake" } },
  { label: "asyncio examples", intent: "concept.examples", params: { term: "python asyncio" } },
  { label: "OpenSSL CVEs", intent: "security.vulnerabilities", params: { product: "openssl" } },
  { label: "Phishing ATT&CK", intent: "security.techniques", params: { query: "phishing" } },
  { label: "Transformer papers", intent: "academic.papers", params: { query: "transformer attention" } },
  { label: "Microsoft profile", intent: "company.profile", params: { name: "Microsoft" } },
  { label: "Data scientist duties", intent: "role.responsibilities", params: { title: "data scientist" } },
  { label: "Slide outline: RSA", intent: "compose.slide_outline", params: { topic: "RSA encryption" } },
];

function renderQuickPicks() {
  $("quickPicks").innerHTML = "";
  for (const q of QUICK) {
    const b = document.createElement("button");
    b.textContent = q.label;
    b.className = "rounded bg-slate-800 hover:bg-slate-700 border border-slate-700 px-2 py-1 text-xs";
    b.onclick = () => {
      selectIntent({ name: q.intent, accepts: Object.keys(q.params), optional: [] }, q.params);
    };
    $("quickPicks").appendChild(b);
  }
}

// ---- intents (advanced) ---------------------------------------------------
let INTENTS = [];

async function loadIntents() {
  try {
    const r = await apiGet("/v1/intents");
    if (r.status === 401) {
      setStatus("ready — add API key in ⚙ Settings to search", false);
      return;
    }
    if (!r.ok) {
      setStatus("HTTP " + r.status, false);
      return;
    }
    INTENTS = await r.json();
    renderIntents();
    setStatus("connected · " + INTENTS.length + " intents", true);
  } catch {
    setStatus("unreachable — check ⚙ Settings", false);
  }
}

function renderIntents() {
  const box = $("intents");
  box.innerHTML = "";
  for (const spec of INTENTS) {
    const el = document.createElement("button");
    el.className = "w-full text-left rounded px-2 py-1.5 hover:bg-slate-800 border border-transparent hover:border-slate-700";
    el.innerHTML =
      `<div class="font-mono text-xs text-indigo-300">${spec.name}</div>` +
      `<div class="text-[11px] text-slate-400 leading-snug">${spec.description || ""}</div>` +
      `<div class="text-[10px] text-slate-500 mt-0.5">${(spec.sources || []).join(", ") || "—"}</div>`;
    el.onclick = () => selectIntent(spec);
    box.appendChild(el);
  }
}

function selectIntent(spec, values) {
  $("intent").value = spec.name;
  $("intentDesc").textContent = spec.description || "";
  const fields = [...new Set([...(spec.accepts || []), ...(spec.optional || [])])];
  const box = $("params");
  box.innerHTML = "";
  const accepts = new Set(spec.accepts || []);
  for (const f of fields.length ? fields : ["term"]) {
    const wrap = document.createElement("label");
    wrap.className = "text-xs text-slate-400";
    const req = accepts.has(f) ? ' <span class="text-rose-400">*</span>' : "";
    wrap.innerHTML = `${f}${req}`;
    const input = document.createElement("input");
    input.className = "mt-1 block w-full rounded bg-slate-800 border border-slate-700 px-2 py-1 text-sm";
    input.dataset.field = f;
    if (values && values[f] != null) input.value = values[f];
    wrap.appendChild(input);
    box.appendChild(wrap);
  }
  if (values) runAdvanced();
}

function runAdvanced() {
  const intent = $("intent").value.trim();
  if (!intent) return;
  const params = {};
  for (const inp of document.querySelectorAll("#params input")) {
    const v = inp.value.trim();
    if (v) params[inp.dataset.field] = v;
  }
  execute(intent, params);
}

// ---- render ---------------------------------------------------------------
function el(tag, cls, html) {
  const e = document.createElement(tag);
  if (cls) e.className = cls;
  if (html != null) e.innerHTML = html;
  return e;
}

function renderError(msg) {
  $("response").innerHTML = "";
  $("response").appendChild(
    el("div", "rounded-lg border border-rose-800 bg-rose-950/40 text-rose-200 p-3 text-sm", msg)
  );
}

function esc(s) {
  return String(s).replace(/[&<>]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;" }[c]));
}

function renderEnvelope(env) {
  const box = $("response");
  box.innerHTML = "";

  const empty = !env.data || Object.keys(env.data).length === 0;
  if (empty) {
    box.appendChild(
      el(
        "div",
        "rounded-lg border border-slate-700 bg-slate-900/40 text-slate-300 p-3 text-sm",
        `No data found for “${esc(env.query && (env.query.term || env.query.topic || env.query.query) || "")}”. ` +
          `Try the full name or a different spelling.`
      )
    );
  }

  if (env.degraded || (env.warnings && env.warnings.length)) {
    const w = el("div", "rounded-lg border border-amber-800 bg-amber-950/40 text-amber-200 p-3 text-sm");
    w.innerHTML =
      `<div class="font-semibold">${env.degraded ? "Partial result" : "Notice"}</div>` +
      (env.warnings || []).map((x) => `<div class="text-xs mt-0.5">• ${esc(x)}</div>`).join("");
    box.appendChild(w);
  }

  const meta = el("div", "rounded-lg border border-slate-800 bg-slate-900/40 p-3");
  const cache = env.cache || {};
  meta.appendChild(
    el(
      "div",
      "text-xs text-slate-400 mb-2",
      `intent <span class="font-mono text-indigo-300">${esc(env.intent)}</span> · ` +
        `cache ${cache.hit ? "hit (" + (cache.age_s ?? "?") + "s)" : "miss"}` +
        (env.attribution_required ? ` · <span class="text-amber-400">attribution required</span>` : "")
    )
  );
  const sl = el("div", "flex flex-wrap gap-2");
  for (const s of env.sources || []) {
    const chip = el("a", "text-xs rounded border border-slate-700 bg-slate-800 px-2 py-1 hover:border-indigo-600");
    chip.href = s.url || "#";
    chip.target = "_blank";
    chip.rel = "noopener";
    chip.title = s.attribution || "";
    chip.innerHTML = `<span class="text-indigo-300">${esc(s.name)}</span> <span class="text-slate-500">${esc(s.license || "")}</span>`;
    sl.appendChild(chip);
  }
  if (!(env.sources || []).length) sl.appendChild(el("span", "text-xs text-slate-500", "no sources"));
  meta.appendChild(sl);
  box.appendChild(meta);

  if (env.intent === "compose.slide_outline" && env.data && Array.isArray(env.data.slides)) {
    box.appendChild(renderSlides(env.data.slides));
  }

  if (!empty) {
    const pre = el("pre", "rounded-lg border border-slate-800 bg-slate-900/40 p-3 text-xs overflow-auto");
    pre.textContent = JSON.stringify(env.data, null, 2);
    const wrap = el("details", "rounded-lg");
    wrap.open = true;
    wrap.appendChild(el("summary", "text-xs text-slate-400 cursor-pointer mb-2", "data"));
    wrap.appendChild(pre);
    box.appendChild(wrap);
  }
}

function renderSlides(slides) {
  const grid = el("div", "grid grid-cols-1 sm:grid-cols-2 gap-3");
  for (const s of slides) {
    const card = el("div", "rounded-lg border border-slate-800 bg-slate-900/60 p-3");
    card.appendChild(el("div", "text-[10px] uppercase tracking-wide text-slate-500", esc(s.type || "")));
    card.appendChild(el("div", "font-semibold text-sm mb-1", esc(s.title || "")));
    if (s.subtitle) card.appendChild(el("div", "text-xs text-slate-400", esc(s.subtitle)));
    if (Array.isArray(s.bullets))
      card.appendChild(el("ul", "list-disc list-inside text-xs text-slate-300 space-y-0.5",
        s.bullets.map((b) => `<li>${esc(b)}</li>`).join("")));
    if (Array.isArray(s.items))
      card.appendChild(el("ul", "list-disc list-inside text-xs text-slate-300 space-y-0.5",
        s.items.map((i) => `<li>${typeof i === "string" ? esc(i) : esc(i.title || JSON.stringify(i))}</li>`).join("")));
    if (s.facts)
      card.appendChild(el("pre", "text-[11px] text-slate-400 mt-1", esc(JSON.stringify(s.facts, null, 2))));
    grid.appendChild(card);
  }
  return grid;
}

// ---- wire up --------------------------------------------------------------
$("searchBtn").onclick = searchConcept;
$("q").addEventListener("keydown", (e) => {
  if (e.key === "Enter") searchConcept();
});
$("testBtn").onclick = () => {
  saveCfg({ baseUrl: $("baseUrl").value.trim(), apiKey: $("apiKey").value.trim() });
  loadIntents();
};
$("runBtn").onclick = runAdvanced;
$("intent").addEventListener("keydown", (e) => {
  if (e.key === "Enter") runAdvanced();
});

renderQuickPicks();
loadIntents();
$("q").focus();
