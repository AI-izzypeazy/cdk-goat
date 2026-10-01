"use strict";
const $ = (id) => document.getElementById(id);
let jobId = null, poll = null;

const CFG_FIELDS = {
  max_pages:"int", max_depth:"int", concurrency:"int", per_host_concurrency:"int",
  max_retries:"int", max_queries:"int",
  min_delay:"float", max_delay:"float",
  same_host_only:"bool", include_subdomains:"bool", rotate_user_agents:"bool",
  http2:"bool", respect_robots:"bool", render_js:"bool", run_queries:"bool",
};

function collectConfig() {
  const cfg = { start_url: $("url").value.trim() };
  for (const [k, t] of Object.entries(CFG_FIELDS)) {
    const el = $(k); if (!el) continue;
    cfg[k] = t === "bool" ? el.checked : t === "int" ? parseInt(el.value,10) : parseFloat(el.value);
  }
  return cfg;
}

async function startCrawl() {
  const url = $("url").value.trim();
  if (!/^https?:\/\//.test(url)) { $("url").focus(); flash($("url")); return; }
  const res = await fetch("/api/crawl", {method:"POST",
    headers:{"Content-Type":"application/json"}, body: JSON.stringify(collectConfig())});
  const data = await res.json();
  if (data.error) { alert(data.error); return; }
  jobId = data.job_id;
  $("startBtn").disabled = true; $("stopBtn").disabled = false;
  $("log").textContent = "";
  clearInterval(poll); poll = setInterval(refresh, 900); refresh();
}

async function stopCrawl() {
  if (!jobId) return;
  await fetch("/api/stop?job="+jobId, {method:"POST"});
}

async function refresh() {
  if (!jobId) return;
  let snap;
  try { snap = await (await fetch("/api/report?job="+jobId)).json(); }
  catch(e){ return; }
  if (snap.error) return;
  render(snap);
  if (["done","stopped","error"].includes(snap.status)) {
    clearInterval(poll); poll = null;
    $("startBtn").disabled = false; $("stopBtn").disabled = true;
  }
}

function render(s) {
  // phase pill
  const pill = $("phasePill"), txt = $("phaseText");
  txt.textContent = s.status + (s.phase && s.phase!==s.status ? " · "+s.phase : "");
  pill.className = "phase " + ({crawling:"run",querying:"run",done:"done",
    stopped:"done",error:"err"}[s.status] || "");

  // tiles
  $("m_pages").textContent    = s.pages_fetched ?? 0;
  $("m_products").textContent = s.products_found ?? 0;
  $("m_rate").textContent     = s.pages_per_sec ?? 0;
  $("m_queued").textContent   = s.queued ?? 0;
  $("m_blocked").textContent  = s.fetcher?.blocked ?? 0;
  $("m_rendered").textContent = s.fetcher?.rendered ?? 0;
  const health = s.search?.score?.health;
  $("m_health").textContent = (health==null) ? "—" : health+"%";

  renderOverview(s);
  renderCatalogue(s.catalogue_sample || []);
  renderQueries(s.search?.results || []);
  renderLog(s.events || []);

  $("c_catalogue").textContent = s.catalogue?.total_products ?? 0;
  $("c_queries").textContent   = (s.search?.results || []).length;
}

function renderOverview(s) {
  const se = s.search;
  $("searchInfo").className = "kv" + (se ? "" : " muted");
  $("searchInfo").innerHTML = se ? `
    <div>endpoint: <b>${esc(se.endpoint||"—")}</b></div>
    <div>param: <b>${esc(se.param||"—")}</b> · via <b>${esc(se.discovered_via)}</b></div>
    <div>pass <b>${se.score.pass}</b> · weak <b>${se.score.weak}</b> ·
         fail <b>${se.score.fail}</b> · blocked <b>${se.score.blocked}</b></div>` :
    "Search endpoint is discovered after the crawl collects a catalogue.";

  const ps = s.catalogue?.price_stats;
  $("priceInfo").className = "kv" + (ps ? "" : " muted");
  $("priceInfo").innerHTML = ps ? `
    <div>min <b>${ps.min}</b> · median <b>${ps.median}</b> · max <b>${ps.max}</b></div>
    <div>avg <b>${ps.avg}</b> across <b>${ps.count}</b> priced items</div>
    <div>currencies: <b>${(s.catalogue.currencies||[]).join(", ")||"—"}</b></div>` :
    "Prices appear once products with pricing are found.";

  $("brandChips").className = "chips" + ((s.catalogue?.top_brands||[]).length ? "" : " muted");
  $("brandChips").innerHTML = chips(s.catalogue?.top_brands, s.catalogue?.unique_brands);
  $("catChips").className = "chips" + ((s.catalogue?.top_categories||[]).length ? "" : " muted");
  $("catChips").innerHTML = chips(s.catalogue?.top_categories, s.catalogue?.unique_categories);
}

function chips(items, total) {
  if (!items || !items.length) return "—";
  return items.map(x => `<span class="chip">${esc(x)}</span>`).join("");
}

function renderCatalogue(items) {
  const body = $("catBody");
  if (!items.length) { body.innerHTML = `<tr><td colspan="5" class="muted">No products yet.</td></tr>`; return; }
  body.innerHTML = items.map(p => `<tr>
    <td>${p.url ? `<a href="${esc(p.url)}" target="_blank" rel="noopener">${esc(p.name)}</a>` : esc(p.name)}</td>
    <td>${esc(p.brand||"—")}</td>
    <td>${esc(p.category||"—")}</td>
    <td class="price">${p.price!=null ? esc((p.currency? p.currency+" ":"")+p.price) : "—"}</td>
    <td class="src">${esc(p.source||"")}</td></tr>`).join("");
}

function renderQueries(rows) {
  const body = $("qBody");
  if (!rows.length) { body.innerHTML = `<tr><td colspan="6" class="muted">No query tests yet.</td></tr>`; return; }
  body.innerHTML = rows.map(r => `<tr>
    <td><code>${esc(r.query)}</code></td>
    <td class="src">${esc(r.intent)}</td>
    <td>${r.expected_results ? "hits" : "none"}</td>
    <td><span class="badge b-${r.verdict}">${r.verdict}</span></td>
    <td><div class="rel-bar"><i style="width:${Math.round((r.relevance||0)*100)}%"></i></div>
        <span class="src">${(r.relevance!=null?r.relevance:0)}</span></td>
    <td class="muted">${esc(r.rationale||"")}</td></tr>`).join("");
}

function renderLog(events) {
  const el = $("log");
  if (!events.length) return;
  const atBottom = el.scrollHeight - el.scrollTop - el.clientHeight < 40;
  el.className = "log";
  el.innerHTML = events.map(e => {
    const ts = new Date(e.t*1000).toLocaleTimeString();
    return `<span class="l-${e.level}"><span class="ts">${ts}</span>  ${esc(e.msg)}</span>`;
  }).join("\n");
  if (atBottom) el.scrollTop = el.scrollHeight;
}

function esc(s){ return String(s==null?"":s).replace(/[&<>"]/g, c =>
  ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c])); }
function flash(el){ el.style.borderColor="var(--danger)"; setTimeout(()=>el.style.borderColor="",600); }

// tabs
document.querySelectorAll(".tab").forEach(t => t.onclick = () => {
  document.querySelectorAll(".tab").forEach(x=>x.classList.remove("active"));
  document.querySelectorAll(".tabview").forEach(x=>x.classList.add("hidden"));
  t.classList.add("active");
  $("tab-"+t.dataset.tab).classList.remove("hidden");
});

$("startBtn").onclick = startCrawl;
$("stopBtn").onclick = stopCrawl;
$("url").addEventListener("keydown", e => { if (e.key==="Enter") startCrawl(); });
