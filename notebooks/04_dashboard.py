# %% [markdown]
# # BustRadar — Build the dashboard
#
# Run LAST (after 02, and after 03 if you trained the U-Net), as a new cell in the same Kaggle notebook.
# Creates **`/kaggle/working/bustradar_dashboard/bustradar_dashboard.html`**: one self-contained file.
# Download it and double-click: opens in any browser, works offline, and can go on GitHub Pages as a live link.
# `bundle.json` in the same folder feeds the API server (`app/server.py`).

# %%
# ---- 1. Dashboard page template -------------------------------------------------------
TEMPLATE = r'''<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>BustRadar</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;600&family=IBM+Plex+Sans:wght@400;500;600;700&display=swap">
<style>
:root{
  --bg:#eef2f6; --card:#ffffff; --ink:#122033; --muted:#5a6879; --line:#d9e0e8; --soft:#f5f7fa;
  --accent:#0b5fa5; --accent-ink:#ffffff; --sea:#dce8f3; --noregion:#e7ebf0;
  --hi:#2e9e5b; --mid:#e3a21a; --lo:#d64541; --hi-bg:#e3f4ea; --mid-bg:#fcf1d8; --lo-bg:#fbe4e2;
  --chip:#eaf1f8; --shadow:0 1px 2px rgba(16,32,51,.06),0 2px 8px rgba(16,32,51,.05);
  --live:#b3261e; --live-bg:#fde7e4; --border-map:#1d2b3a;
}
@media (prefers-color-scheme: dark){:root:not([data-theme="light"]){
  --bg:#0c131b; --card:#141e29; --ink:#e4ebf2; --muted:#98a7b8; --line:#26333f; --soft:#101923;
  --accent:#5aa9e6; --accent-ink:#06111c; --sea:#15283a; --noregion:#1c2733;
  --hi:#3fbf73; --mid:#f0b43a; --lo:#ef6b5e; --hi-bg:#123424; --mid-bg:#3a2e10; --lo-bg:#3d1a17;
  --chip:#1a2a3a; --shadow:none; --live:#ff8a80; --live-bg:#3d1a17; --border-map:#cfd9e3; color-scheme:dark}}
:root[data-theme="dark"]{
  --bg:#0c131b; --card:#141e29; --ink:#e4ebf2; --muted:#98a7b8; --line:#26333f; --soft:#101923;
  --accent:#5aa9e6; --accent-ink:#06111c; --sea:#15283a; --noregion:#1c2733;
  --hi:#3fbf73; --mid:#f0b43a; --lo:#ef6b5e; --hi-bg:#123424; --mid-bg:#3a2e10; --lo-bg:#3d1a17;
  --chip:#1a2a3a; --shadow:none; --live:#ff8a80; --live-bg:#3d1a17; --border-map:#cfd9e3; color-scheme:dark}
*{box-sizing:border-box}
html,body{margin:0}
body{background:var(--bg);color:var(--ink);font:14px/1.5 "IBM Plex Sans",system-ui,-apple-system,"Segoe UI",sans-serif}
.num,code,pre{font-family:"IBM Plex Mono",ui-monospace,Menlo,Consolas,monospace;font-variant-numeric:tabular-nums}
header{background:var(--card);border-bottom:1px solid var(--line);position:sticky;top:0;z-index:5}
.bar{max-width:1320px;margin:0 auto;padding:10px 16px;display:flex;flex-wrap:wrap;gap:12px 20px;align-items:center}
.brand{display:flex;align-items:center;gap:10px;margin-right:auto;min-width:0}
.bar .tabs button{padding:9px 10px}
.brand svg{flex:none}
.brand b{font-size:18px;letter-spacing:.2px}
.brand span{color:var(--muted);font-size:12px;display:block;line-height:1.2}
.tabs{display:flex;gap:4px;flex-wrap:wrap}
.tabs button{border:0;background:transparent;color:var(--muted);font:600 13px/1 inherit;padding:9px 12px;border-radius:7px;cursor:pointer}
.tabs button[aria-selected="true"]{background:var(--chip);color:var(--ink)}
.datebox{display:flex;align-items:center;gap:6px}
.datebox input{font:500 13px "IBM Plex Mono",monospace;padding:6px 8px;border:1px solid var(--line);border-radius:7px;background:var(--soft);color:var(--ink)}
.iconbtn{border:1px solid var(--line);background:var(--card);color:var(--ink);border-radius:7px;width:32px;height:32px;cursor:pointer;font-size:15px}
.badge{font:600 11px/1 "IBM Plex Mono",monospace;letter-spacing:.04em;text-transform:uppercase;padding:5px 8px;border-radius:5px}
.badge.test{background:var(--hi-bg);color:var(--hi)} .badge.val{background:var(--mid-bg);color:var(--mid)} .badge.fit{background:var(--lo-bg);color:var(--lo)}
.badge.live{background:var(--live-bg);color:var(--live)} .badge.live::before{content:"";display:inline-block;width:7px;height:7px;border-radius:50%;background:var(--live);margin-right:6px;vertical-align:1px;animation:pulse 1.6s infinite}
@keyframes pulse{50%{opacity:.25}}
@media (prefers-reduced-motion:reduce){.badge.live::before{animation:none}}
.seg{display:inline-flex;border:1px solid var(--line);border-radius:7px;overflow:hidden}
.seg button{border:0;background:var(--card);color:var(--muted);font:600 12px/1 inherit;padding:8px 10px;cursor:pointer}
.seg button[aria-pressed="true"]{background:var(--chip);color:var(--ink)}
.banner{border:1px solid var(--live);background:var(--live-bg);color:var(--ink);border-radius:10px;padding:10px 14px;font-size:13px}
.tiles{display:grid;grid-template-columns:repeat(auto-fit,minmax(130px,1fr));gap:10px;margin:6px 0 14px}
.tile{background:var(--soft);border:1px solid var(--line);border-radius:10px;padding:10px 12px}
.tile b{display:block;font:700 26px/1.1 "IBM Plex Mono",monospace}
.tile span{color:var(--muted);font-size:12px}
.rc td{text-align:center;padding:2px}
.rc .o{display:block;min-width:34px;border-radius:5px;padding:6px 0;font:600 12px "IBM Plex Mono",monospace}
.o.hit{background:var(--hi);color:#fff}.o.fa{background:var(--mid);color:#1b1300}.o.miss{background:var(--lo);color:#fff}.o.cn{background:var(--soft);color:var(--muted);border:1px solid var(--line)}.o.na{color:var(--muted)}
.bullets{display:grid;grid-template-columns:1fr 1fr;gap:10px}
@media (max-width:760px){.bullets{grid-template-columns:1fr}}
.bullets pre.bulletin{margin:0;max-height:260px}
.lh{font:600 11px/1 "IBM Plex Mono",monospace;letter-spacing:.06em;color:var(--muted);margin:10px 0 6px;text-transform:uppercase}
.range{background:var(--soft);border:1px solid var(--line);border-radius:8px;padding:8px 10px;margin:6px 0 10px;font-size:13px}
.range b{font-family:"IBM Plex Mono",monospace}
.rangebar{position:relative;height:10px;border-radius:5px;background:var(--line);margin-top:8px}
.rangebar i{position:absolute;top:0;bottom:0;border-radius:5px;background:var(--accent);opacity:.55}
.rangebar em{position:absolute;top:-3px;width:3px;height:16px;background:var(--ink);border-radius:2px}
.rangebar s{position:absolute;top:-4px;width:10px;height:10px;margin-left:-5px;border-radius:50%;background:var(--lo);border:2px solid var(--card);top:-1px}
.matrix.tall{max-height:560px;overflow:auto}
main{max-width:1320px;margin:0 auto;padding:16px;display:grid;gap:16px}
.card{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:16px;box-shadow:var(--shadow);min-width:0}
.card h2{font-size:15px;margin:0 0 2px}
.card .sub{color:var(--muted);font-size:12px;margin:0 0 12px}
.grid2{display:grid;grid-template-columns:minmax(0,1.05fr) minmax(0,1fr);gap:16px}
.grid3{display:grid;grid-template-columns:minmax(0,1.3fr) minmax(0,1fr);gap:16px}
@media (max-width:980px){.grid2,.grid3{grid-template-columns:1fr}}
.leads{display:flex;flex-wrap:wrap;gap:4px;margin-bottom:10px}
.leads button{min-width:40px;border:1px solid var(--line);background:var(--soft);color:var(--ink);border-radius:6px;padding:6px 8px;font:600 12px "IBM Plex Mono",monospace;cursor:pointer}
.leads button[aria-pressed="true"]{background:var(--accent);border-color:var(--accent);color:var(--accent-ink)}
.mapwrap{overflow-x:auto}
svg text{font-family:"IBM Plex Sans",system-ui,sans-serif}
.legend{display:flex;flex-wrap:wrap;gap:12px;font-size:12px;color:var(--muted);margin-top:8px}
.legend i{display:inline-block;width:12px;height:12px;border-radius:3px;margin-right:5px;vertical-align:-2px}
table{border-collapse:collapse;width:100%}
.matrix{overflow-x:auto}
.matrix th{font:600 11px "IBM Plex Mono",monospace;color:var(--muted);padding:4px;text-align:center}
.matrix th.r{text-align:left;font-family:"IBM Plex Sans",sans-serif;font-size:12px;color:var(--ink);white-space:nowrap;padding-right:8px}
.matrix td{padding:2px}
.cell{display:block;width:100%;min-width:34px;border:0;border-radius:5px;padding:7px 0;font:600 12px "IBM Plex Mono",monospace;color:#fff;cursor:pointer}
.cell.sel{outline:3px solid var(--ink);outline-offset:1px}
.detail-head{display:flex;flex-wrap:wrap;gap:16px;align-items:flex-start;justify-content:space-between}
.big{font:700 44px/1 "IBM Plex Mono",monospace}
.bandlabel{font-weight:600}
.kv{color:var(--muted);font-size:12px}
.bars{display:grid;gap:7px;margin:14px 0}
.brow{display:grid;grid-template-columns:120px 1fr 44px;gap:8px;align-items:center;font-size:12.5px}
.btrack{height:10px;background:var(--soft);border-radius:5px;overflow:hidden;border:1px solid var(--line)}
.bfill{height:100%}
.chips{display:flex;flex-wrap:wrap;gap:6px;margin:6px 0 10px}
.chip{background:var(--chip);border-radius:999px;padding:4px 10px;font-size:12px;font-weight:500}
.chip.warn{background:var(--lo-bg);color:var(--lo)}
ul.reasons{margin:4px 0 12px;padding-left:18px;display:grid;gap:4px}
.sec{font:600 11px/1 "IBM Plex Mono",monospace;letter-spacing:.06em;text-transform:uppercase;color:var(--muted);margin:14px 0 6px}
.analogs{display:grid;gap:6px}
.analog{display:flex;justify-content:space-between;gap:8px;background:var(--soft);border:1px solid var(--line);border-radius:7px;padding:7px 10px;font-size:12.5px}
.ok{color:var(--hi);font-weight:600}.bad{color:var(--lo);font-weight:600}
.reveal{margin-top:12px;border-top:1px dashed var(--line);padding-top:10px}
.btn{border:1px solid var(--accent);background:var(--accent);color:var(--accent-ink);border-radius:7px;padding:8px 12px;font:600 13px inherit;cursor:pointer}
.btn.ghost{background:transparent;color:var(--accent)}
.alerts{display:grid;gap:6px;max-height:420px;overflow:auto}
.alert{display:grid;grid-template-columns:52px 1fr;gap:10px;align-items:start;border:1px solid var(--line);border-radius:8px;padding:8px 10px;background:var(--soft);cursor:pointer}
.alert .p{font:700 16px "IBM Plex Mono",monospace;color:var(--lo)}
.alert .t{font-weight:600;font-size:13px}
.alert .r{color:var(--muted);font-size:12px}
.controls{display:flex;flex-wrap:wrap;gap:10px;align-items:center;margin-bottom:10px;font-size:12.5px;color:var(--muted)}
pre.bulletin{white-space:pre-wrap;background:var(--soft);border:1px solid var(--line);border-radius:8px;padding:10px;font-size:12px;max-height:220px;overflow:auto;margin:8px 0 0}
.events{display:grid;gap:6px}
.event{text-align:left;border:1px solid var(--line);background:var(--soft);color:var(--ink);border-radius:8px;padding:9px 11px;cursor:pointer;font:inherit}
.event[aria-pressed="true"]{border-color:var(--accent);box-shadow:inset 3px 0 0 var(--accent)}
.event b{display:block;font-size:13px}.event span{color:var(--muted);font-size:12px}
.metrics td,.metrics th{padding:7px 8px;border-bottom:1px solid var(--line);text-align:right;font-size:12.5px}
.metrics th{color:var(--muted);font-weight:600;font-size:11.5px}
.metrics td:first-child,.metrics th:first-child{text-align:left}
.tablewrap{overflow-x:auto}
.empty{color:var(--muted);font-size:13px;padding:10px 0}
.api pre{background:var(--soft);border:1px solid var(--line);border-radius:8px;padding:10px;overflow:auto;font-size:12px}
.note{font-size:12px;color:var(--muted)}
button:focus-visible,input:focus-visible{outline:3px solid color-mix(in srgb,var(--accent) 45%,transparent);outline-offset:2px}
[hidden]{display:none!important}
</style>
</head>
<body>
<header>
  <div class="bar">
    <div class="brand">
      <svg width="30" height="30" viewBox="0 0 30 30" aria-hidden="true"><circle cx="15" cy="15" r="13" fill="none" stroke="var(--accent)" stroke-width="2"/><circle cx="15" cy="15" r="8" fill="none" stroke="var(--accent)" stroke-width="1.5" opacity=".6"/><path d="M15 15 L25 8" stroke="var(--lo)" stroke-width="2.4" stroke-linecap="round"/><circle cx="21" cy="19" r="2.2" fill="var(--lo)"/></svg>
      <div><b>BustRadar</b><span>Medium-range forecast bust early warning · SIH 2026 PS 26079</span></div>
    </div>
    <nav class="tabs" role="tablist">
      <button role="tab" data-tab="forecast" aria-selected="true">Forecast</button>
      <button role="tab" data-tab="report" aria-selected="false">Report card</button>
      <button role="tab" data-tab="replay" aria-selected="false">Event replay</button>
      <button role="tab" data-tab="score" aria-selected="false">Scorecard</button>
      <button role="tab" data-tab="api" aria-selected="false">API</button>
    </nav>
    <div class="datebox">
      <button class="iconbtn" id="prevDate" aria-label="Previous forecast date">‹</button>
      <input type="date" id="dateInput" aria-label="Forecast issue date">
      <button class="iconbtn" id="nextDate" aria-label="Next forecast date">›</button>
      <span class="badge" id="splitBadge"></span>
    </div>
    <div style="display:flex;gap:8px;align-items:center">
      <div class="seg" role="group" aria-label="Language">
        <button data-lang="en" aria-pressed="true">EN</button><button data-lang="hi" aria-pressed="false" lang="hi">हिं</button>
      </div>
      <button class="iconbtn" id="themeBtn" aria-label="Switch dark or light theme" title="Dark / light theme"></button>
    </div>
  </div>
</header>

<main>
  <!-- FORECAST -->
  <section id="tab-forecast" class="grid2">
    <div class="banner" id="liveBanner" style="grid-column:1/-1" hidden></div>
    <div class="card">
      <h2>Forecast confidence map</h2>
      <p class="sub" id="mapSub"></p>
      <div class="leads" id="leadBtns" role="group" aria-label="Lead day"></div>
      <div class="leads" id="layerBtns" role="group" aria-label="Map layer">
        <button data-layer="region" aria-pressed="true">Regions</button>
        <button data-layer="state" aria-pressed="false">States / UTs</button>
        <button data-layer="grid" aria-pressed="false">Error-prone areas (U-Net grid)</button>
      </div>
      <div class="mapwrap"><svg id="map" role="img" aria-label="Map of forecast confidence by region"></svg></div>
      <div class="legend">
        <span><i style="background:var(--hi)"></i>High confidence ≥70</span>
        <span><i style="background:var(--mid)"></i>Medium 50–69</span>
        <span><i style="background:var(--lo)"></i>Low &lt;50 · bust-prone</span>
      </div>
      <p class="note" id="mapSource"></p>
      <div class="sec" style="margin-top:18px">10-day outlook for this run</div>
      <svg id="outlook" role="img" aria-label="Number of regions in each confidence band by lead day"></svg>
      <p class="note" id="outlookNote"></p>
    </div>
    <div style="display:grid;gap:16px;min-width:0">
      <div class="card">
        <h2 id="matrixTitle">Region × lead-day confidence</h2>
        <p class="sub">Confidence Index = 100 − P(any bust). Click a cell for details.</p>
        <div class="matrix" id="matrixWrap"><table id="matrix"></table></div>
      </div>
      <div class="card" id="detail"></div>
    </div>
    <div class="card" style="grid-column:1/-1">
      <h2>Bust alerts and bulletin for this forecast run</h2>
      <div class="controls">
        <label for="thr">Alert when P(bust) ≥ <b id="thrVal" class="num">50</b>%</label>
        <input type="range" id="thr" min="20" max="90" step="5" value="50">
        <span id="thrNote"></span>
        <span class="seg" role="group" aria-label="Bulletin by"><button data-by="state" aria-pressed="true">State-wise</button><button data-by="region" aria-pressed="false">Region-wise</button></span>
        <span class="seg" role="group" aria-label="Bulletin language"><button data-bl="both" aria-pressed="true">English + हिन्दी</button><button data-bl="en" aria-pressed="false">English</button><button data-bl="hi" aria-pressed="false">हिन्दी</button></span>
        <button class="btn ghost" id="copyBulletin">Copy bulletin</button>
        <span id="copyStatus" role="status"></span>
      </div>
      <div class="grid3">
        <div class="alerts" id="alerts"></div>
        <div class="bullets" id="bullets"><pre class="bulletin" id="bulletin"></pre><pre class="bulletin" id="bulletinHi" lang="hi"></pre></div>
      </div>
    </div>
  </section>

  <!-- REPORT CARD -->
  <section id="tab-report" hidden style="display:grid;gap:16px">
    <div class="card">
      <h2 id="rcTitle">Yesterday's report card</h2>
      <p class="sub" id="rcSub"></p>
      <div class="tiles" id="rcTiles"></div>
      <div class="lh">Every forecast that was valid yesterday, by how many days ahead it was issued</div>
      <div class="matrix"><table class="rc" id="rcTable"></table></div>
      <div class="legend">
        <span><i style="background:var(--hi)"></i>Caught: alert issued, forecast busted</span>
        <span><i style="background:var(--mid)"></i>False alarm: alert, forecast held up</span>
        <span><i style="background:var(--lo)"></i>Missed: no alert, forecast busted</span>
        <span><i style="background:var(--soft);border:1px solid var(--line)"></i>Correct quiet</span>
      </div>
    </div>
    <div class="grid2">
      <div class="card">
        <h2>Did yesterday's rainfall fall inside the range?</h2>
        <p class="sub">Day-1 forecast of each region: 90% range vs IMD observation (region mean, mm/day)</p>
        <div class="tablewrap"><table class="metrics" id="rcRain"></table></div>
      </div>
      <div class="card">
        <h2>Last 30 days</h2>
        <p class="sub" id="rc30Sub"></p>
        <svg id="rc30" role="img" aria-label="Daily caught, missed and false-alarm counts over the last 30 days"></svg>
        <div class="tiles" id="rc30Tiles" style="margin-top:10px"></div>
      </div>
    </div>
  </section>

  <!-- REPLAY -->
  <section id="tab-replay" class="grid3" hidden>
    <div class="card">
      <h2 id="evTitle">Event replay</h2>
      <p class="sub" id="evSub"></p>
      <svg id="evChart" role="img" aria-label="Bust probability by lead day for the selected event"></svg>
      <p class="note" id="evNote"></p>
      <button class="btn" id="evOpen">Open this forecast in the map</button>
    </div>
    <div class="card">
      <h2>Famous events</h2>
      <p class="sub">How early would BustRadar have warned? Test-year events were never seen in training.</p>
      <div class="events" id="events"></div>
    </div>
  </section>

  <!-- SCORECARD -->
  <section id="tab-score" hidden style="display:grid;gap:16px">
    <div class="card">
      <h2>Skill on held-out years</h2>
      <p class="sub">ROC-AUC: 0.5 = no skill, 1.0 = perfect. Each column adds a layer: climatology → forecast amount only → basic features → full BustRadar.</p>
      <div class="tablewrap"><table class="metrics" id="metrics"></table></div>
    </div>
    <div class="grid2">
      <div class="card"><h2>Rainfall ranges: do they hold?</h2><p class="sub">Share of test-year days where the observed region rain fell inside the 90% range</p><div class="tablewrap"><table class="metrics" id="rangeTable"></table></div></div>
      <div class="card"><h2>Alert threshold</h2><p class="sub">Chosen automatically on the validation year (best hit rate minus false-alarm rate, at most 15 alerts per 100 region-days)</p><p id="thrInfo" style="margin:0"></p></div>
    </div>
    <div class="card" id="unetCard" hidden>
      <h2>Grid-level error-prone areas (U-Net deep ensemble)</h2>
      <p class="sub">Every 1.5° land cell, rain busts, held-out test years</p>
      <div class="tablewrap"><table class="metrics" id="unetTable"></table></div>
    </div>
    <div class="grid2">
      <div class="card"><h2>Skill by lead day</h2><p class="sub">Test years, ROC-AUC</p><svg id="aucChart" role="img" aria-label="AUC by lead day"></svg></div>
      <div class="card"><h2>Which weather systems make forecasts bust?</h2><p class="sub">Bust rate when the system is in the forecast, relative to the usual rate</p><svg id="sysChart" role="img" aria-label="Bust rate multiplier by weather system"></svg></div>
    </div>
  </section>

  <!-- API -->
  <section id="tab-api" class="card api" hidden>
    <h2>API for operational use</h2>
    <p class="sub">Run <code>python app/server.py</code> and these endpoints return JSON. The same data drives this dashboard.</p>
    <pre id="apiDoc"></pre>
    <h2 style="margin-top:14px">Example response</h2>
    <pre id="apiExample"></pre>
  </section>
</main>

<script>
window.BUNDLE = /*__BUNDLE__*/null;
</script>
<script>
(async function () {
  const B = window.BUNDLE || await fetch("api/bundle").then(r => r.json());
  const M = B.meta, REG = M.regions, R = REG.length, LEADS = M.leads, NL = LEADS.length, TYPES = M.types;
  const C = B.cols, DATES = B.dates, ST = B.states ? B.states.states : [];
  const REG_HI = M.regions_hi || REG, TL_HI = M.type_labels_hi || M.type_labels, SL_HI = M.system_labels_hi || M.system_labels;
  const RS_HI = B.reasons_hi || B.reasons;
  const LIVE = new Set(M.live_runs || []);
  // U-Net grid layer: uint8 per (date, lead, land cell); 255 = missing
  let UG = null;
  if (B.unet && B.unet.p_b64) {
    const bin = atob(B.unet.p_b64); const a = new Uint8Array(bin.length);
    for (let i = 0; i < bin.length; i++) a[i] = bin.charCodeAt(i);
    const cellPos = new Map(B.unet.cells.map((c, k) => [c, k]));
    UG = { a, n: B.unet.cells.length, cellPos };
  }
  const gridP = (d, li, i, j) => {
    if (!UG) return null; const k = UG.cellPos.get(i * B.grid.lon.length + j); if (k == null) return null;
    const v = UG.a[(d * NL + li) * UG.n + k]; return v === 255 ? null : v;
  };
  const $ = s => document.querySelector(s);
  const css = v => getComputedStyle(document.documentElement).getPropertyValue(v).trim();
  const esc = s => String(s).replace(/[&<>"]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
  const ix = (d, li, r) => (d * NL + li) * R + r;
  const band = conf => conf >= 70 ? "hi" : conf >= 50 ? "mid" : "lo";
  const bandText = { hi: "High confidence", mid: "Medium confidence", lo: "Low confidence · bust-prone" };
  const bandHi = { hi: "उच्च विश्वसनीयता", mid: "मध्यम विश्वसनीयता", lo: "कम विश्वसनीयता · बस्ट की आशंका" };
  const addDays = (s, n) => { const d = new Date(s + "T00:00:00Z"); d.setUTCDate(d.getUTCDate() + n); return d.toISOString().slice(0, 10); };
  const fmt = s => new Date(s + "T00:00:00Z").toLocaleDateString("en-IN", { day: "numeric", month: "short", year: "numeric", timeZone: "UTC" });
  const fmtHi = s => new Date(s + "T00:00:00Z").toLocaleDateString("hi-IN", { day: "numeric", month: "long", year: "numeric", timeZone: "UTC" });
  const store = { get(k) { try { return localStorage.getItem(k); } catch (e) { return null; } }, set(k, v) { try { localStorage.setItem(k, v); } catch (e) {} } };

  // ---------- state ----------
  let state = { d: 0, li: 0, r: 0, st: -1, tab: "forecast", thr: 50, reveal: false, ev: 0, layer: "region",
                lang: store.get("br-lang") || "en", by: "state", bl: "both" };
  if (M.alert_threshold) state.thr = Math.round(M.alert_threshold * 100);
  const liveIdx = DATES.map((x, k) => LIVE.has(x) ? k : -1).filter(k => k >= 0);
  const tk = DATES.indexOf("2021-05-13");
  if (liveIdx.length) { state.d = liveIdx[liveIdx.length - 1]; }
  else if (tk >= 0) { state.d = tk; state.r = REG.indexOf("West Coast"); state.li = 2; }
  else {
    let best = -1;
    DATES.forEach((_, d) => { let s = 0; for (let i = 0; i < NL * R; i++) s += Math.max(0, C.p[d * NL * R + i]); if (s > best) { best = s; state.d = d; } });
  }
  if (state.r < 0) state.r = 0;
  const HI = () => state.lang === "hi";
  const regName = r => HI() ? REG_HI[r] : REG[r];
  const stName = k => HI() ? ST[k].name_hi : ST[k].name;
  const typeName = t => HI() ? (TL_HI[t] || t) : M.type_labels[t];

  // ---------- theme ----------
  const themeBtn = $("#themeBtn");
  const isDark = () => (document.documentElement.dataset.theme || (matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light")) === "dark";
  const savedTheme = store.get("br-theme"); if (savedTheme) document.documentElement.dataset.theme = savedTheme;
  const paintThemeBtn = () => { themeBtn.textContent = isDark() ? "☀" : "☾"; themeBtn.setAttribute("aria-label", isDark() ? "Switch to light theme" : "Switch to dark theme"); };
  themeBtn.onclick = () => { const t = isDark() ? "light" : "dark"; document.documentElement.dataset.theme = t; store.set("br-theme", t); paintThemeBtn(); render(); };
  paintThemeBtn();
  document.querySelectorAll("[data-lang]").forEach(b => b.onclick = () => { state.lang = b.dataset.lang; store.set("br-lang", state.lang); render(); });

  // ---------- header ----------
  const di = $("#dateInput"); di.min = DATES[0]; di.max = DATES[DATES.length - 1];
  const setDate = d => { state.d = Math.max(0, Math.min(DATES.length - 1, d)); render(); };
  di.addEventListener("change", () => {
    const v = di.value; let k = DATES.findIndex(x => x >= v); if (k < 0) k = DATES.length - 1; setDate(k);
  });
  $("#prevDate").onclick = () => setDate(state.d - 1);
  $("#nextDate").onclick = () => setDate(state.d + 1);
  const TABS = ["forecast", "report", "replay", "score", "api"];
  document.querySelectorAll(".tabs button").forEach(b => b.onclick = () => {
    state.tab = b.dataset.tab;
    document.querySelectorAll(".tabs button").forEach(x => x.setAttribute("aria-selected", x === b));
    TABS.forEach(t => $("#tab-" + t).hidden = t !== state.tab);
    render();
  });
  const lb = $("#leadBtns");
  LEADS.forEach((L, li) => { const b = document.createElement("button"); b.textContent = "D" + L; b.onclick = () => { state.li = li; render(); }; lb.appendChild(b); });
  $("#layerBtns").querySelectorAll("button").forEach(b => {
    if (b.dataset.layer === "grid" && !UG) b.hidden = true;
    if (b.dataset.layer === "state" && !ST.length) b.hidden = true;
    b.onclick = () => { state.layer = b.dataset.layer; if (state.layer === "state" && state.st < 0) state.st = defaultState(); render(); };
  });
  $("#thr").value = state.thr; $("#thrVal").textContent = state.thr;
  if (M.alert_threshold) $("#thrNote").textContent = `(tuned default ${Math.round(M.alert_threshold * 100)}%)`;
  $("#thr").oninput = e => { state.thr = +e.target.value; $("#thrVal").textContent = state.thr; renderAlerts(); };
  document.querySelectorAll("[data-by]").forEach(b => { if (!ST.length && b.dataset.by === "state") { b.hidden = true; state.by = "region"; } b.onclick = () => { state.by = b.dataset.by; renderAlerts(); }; });
  document.querySelectorAll("[data-bl]").forEach(b => b.onclick = () => { state.bl = b.dataset.bl; renderAlerts(); });

  // ---------- helpers ----------
  const val = (col, d, li, r) => (C[col] ? C[col][ix(d, li, r)] : -1);
  const conf = (d, li, r) => { const p = val("p", d, li, r); return p < 0 ? null : 100 - p; };
  const color = c => c == null ? css("--noregion") : css("--" + band(c));
  const reasonsOf = (d, li, r, hi = HI()) => { const k = val("reason", d, li, r); return k >= 0 ? (hi ? RS_HI : B.reasons)[k].split(" | ") : []; };
  const sysOf = (d, li, r, hi = HI()) => { const m = val("sys", d, li, r); return M.systems.filter((s, k) => m >= 0 && (m >> k) & 1).map(s => hi ? (SL_HI[s] || s) : M.system_labels[s]); };
  const mainType = (d, li, r) => TYPES.reduce((a, t) => val("p_" + t, d, li, r) > val("p_" + a, d, li, r) ? t : a, TYPES[0]);
  const rng = (d, li, r) => {
    const lo = val("rain_lo", d, li, r), md = val("rain_med", d, li, r), hi = val("rain_hi", d, li, r);
    return lo < 0 || hi < 0 ? null : { lo: lo / 10, md: md / 10, hi: hi / 10 };
  };
  const mm = v => v >= 10 ? v.toFixed(0) : v.toFixed(1);
  // states: probability = area-weighted mix of the regions the state lies in
  const stateP = (d, li, k, col = "p") => {
    const s = ST[k]; if (!s || !s.scored || !s.regions.length) return null;
    let p = 0; for (const [r, w] of s.regions) { const v = val(col, d, li, r); if (v < 0) return null; p += w * v; }
    return Math.round(p);
  };
  const stateConf = (d, li, k) => { const p = stateP(d, li, k); return p == null ? null : 100 - p; };
  const stateMain = (d, li, k) => TYPES.reduce((a, t) => (stateP(d, li, k, "p_" + t) ?? -1) > (stateP(d, li, k, "p_" + a) ?? -1) ? t : a, TYPES[0]);
  const domReg = k => ST[k].regions.length ? ST[k].regions[0][0] : -1;
  function defaultState() {
    const r = state.r; let best = -1, bw = -1;
    ST.forEach((s, k) => { if (!s.scored) return; const w = (s.regions.find(x => x[0] === r) || [0, 0])[1] * s.cells.length; if (w > bw) { bw = w; best = k; } });
    return best;
  }
  const unetShare = (d, li, cells) => {
    if (!UG) return null; let n = 0, hot = 0;
    for (const [i, j, w] of cells) { const v = gridP(d, li, i, j); if (v != null) { n += w; if (v >= 50) hot += w; } }
    return n ? hot / n : null;
  };

  // ---------- map ----------
  function renderMap() {
    const g = B.grid, nla = g.lat.length, nlo = g.lon.length, s = 19, pad = 30;
    const W = nlo * s + pad + 8, H = nla * s + pad;
    const svg = $("#map"); svg.setAttribute("viewBox", `0 0 ${W} ${H}`); svg.setAttribute("width", "100%");
    svg.style.maxWidth = (W * 1.35) + "px";
    const row = i => (nla - 1 - i);   // lat ascending -> draw north at top
    const X = lon => pad + (lon - g.lon[0] + 0.75) / 1.5 * s, Y = lat => (g.lat[nla - 1] + 0.75 - lat) / 1.5 * s;
    const pathOf = rings => rings.map(rg => "M" + rg.map(([lo, la]) => `${X(lo).toFixed(1)},${Y(la).toFixed(1)}`).join("L") + "Z").join("");
    let out = "";
    const confR = REG.map((_, r) => conf(state.d, state.li, r));
    const stLayer = state.layer === "state" && ST.length;
    for (let i = 0; i < nla; i++) for (let j = 0; j < nlo; j++) {
      const rid = g.region_id[i][j], land = g.land[i][j];
      let fill = rid >= 0 ? color(confR[rid]) : land ? css("--noregion") : css("--sea");
      if (state.layer === "grid" && land) { const gp = gridP(state.d, state.li, i, j); fill = gp == null ? css("--noregion") : color(100 - gp); }
      if (stLayer) fill = css("--sea");
      const op = !stLayer && rid >= 0 ? (rid === state.r ? 1 : 0.82) : 1;
      out += `<rect x="${pad + j * s}" y="${row(i) * s}" width="${s}" height="${s}" fill="${fill}" opacity="${op}" data-r="${stLayer ? -1 : rid}"${rid >= 0 && !stLayer ? ' style="cursor:pointer"' : ""}/>`;
    }
    if (stLayer) {
      ST.forEach((st, k) => {
        const c = stateConf(state.d, state.li, k);
        out += `<path d="${pathOf(st.outline)}" fill="${st.scored ? color(c) : css("--noregion")}" stroke="${css("--card")}" stroke-width="${k === state.st ? 0 : 0.8}" data-st="${k}" style="cursor:${st.scored ? "pointer" : "default"}" opacity="${k === state.st ? 1 : 0.9}"><title>${esc(stName(k))}${c == null ? "" : ": " + c}</title></path>`;
      });
      if (state.st >= 0) out += `<path d="${pathOf(ST[state.st].outline)}" fill="none" stroke="${css("--ink")}" stroke-width="2.2" pointer-events="none"/>`;
    } else {
      // region borders
      const edge = (x1, y1, x2, y2, w, c) => `<line x1="${x1}" y1="${y1}" x2="${x2}" y2="${y2}" stroke="${c}" stroke-width="${w}" stroke-linecap="square"/>`;
      const bc = css("--card"), sc = css("--ink");
      for (let i = 0; i < nla; i++) for (let j = 0; j < nlo; j++) {
        const a = g.region_id[i][j];
        const right = j + 1 < nlo ? g.region_id[i][j + 1] : -2, up = i + 1 < nla ? g.region_id[i + 1][j] : -2;
        const x = pad + (j + 1) * s, y = row(i) * s;
        if (right !== a && (a >= 0 || right >= 0)) out += edge(x, y, x, y + s, (a === state.r || right === state.r) ? 2.2 : 1.2, (a === state.r || right === state.r) ? sc : bc);
        const xu = pad + j * s, yu = row(i) * s;
        if (up !== a && (a >= 0 || up >= 0)) out += edge(xu, yu, xu + s, yu, (a === state.r || up === state.r) ? 2.2 : 1.2, (a === state.r || up === state.r) ? sc : bc);
      }
      if (ST.length) out += `<path d="${ST.map(st => pathOf(st.outline)).join("")}" fill="none" stroke="${css("--border-map")}" stroke-opacity=".28" stroke-width=".6" pointer-events="none"/>`;
    }
    if (B.states && B.states.india_outline) out += `<path d="${pathOf(B.states.india_outline)}" fill="none" stroke="${css("--border-map")}" stroke-opacity=".75" stroke-width="1.1" pointer-events="none"/>`;
    // labels
    const lab = (x, y, t, v, big) => `<g pointer-events="none"><text x="${x}" y="${y - 3}" text-anchor="middle" font-size="${big ? 10.5 : 8.5}" font-weight="600" fill="#fff" stroke="rgba(0,0,0,.4)" stroke-width="2.4" paint-order="stroke">${esc(t)}</text>`
      + (v == null ? "</g>" : `<text x="${x}" y="${y + (big ? 11 : 8)}" text-anchor="middle" font-size="${big ? 12 : 9.5}" font-weight="700" fill="#fff" stroke="rgba(0,0,0,.4)" stroke-width="2.4" paint-order="stroke" font-family="IBM Plex Mono,monospace">${v}</text></g>`);
    if (stLayer) {
      ST.forEach((st, k) => { if (!st.scored || st.cells.length < 3) return;
        const nm = st.cells.length >= 7 ? (HI() ? st.name_hi : st.name.replace(" and Ladakh", "").replace("Pradesh", "Pr.")) : "";
        out += lab(X(st.label[0]), Y(st.label[1]), nm, stateConf(state.d, state.li, k), false); });
    } else {
      REG.forEach((name, r) => {
        let sx = 0, sy = 0, n = 0;
        for (let i = 0; i < nla; i++) for (let j = 0; j < nlo; j++) if (g.region_id[i][j] === r) { sx += pad + (j + .5) * s; sy += row(i) * s + s / 2; n++; }
        if (n) out += lab(sx / n, sy / n, regName(r), state.layer === "grid" ? null : (confR[r] ?? "–"), true);
      });
    }
    // axes
    const mc = css("--muted");
    for (let i = 0; i < nla; i += 4) out += `<text x="${pad - 5}" y="${row(i) * s + s / 2 + 4}" text-anchor="end" font-size="10" fill="${mc}">${g.lat[i].toFixed(0)}°N</text>`;
    for (let j = 0; j < nlo; j += 4) out += `<text x="${pad + j * s + s / 2}" y="${nla * s + 16}" text-anchor="middle" font-size="10" fill="${mc}">${g.lon[j].toFixed(0)}°E</text>`;
    svg.innerHTML = out;
    svg.querySelectorAll("rect[data-r]").forEach(el => { const r = +el.dataset.r; if (r >= 0) el.onclick = () => { state.r = r; state.st = -1; render(); }; });
    svg.querySelectorAll("path[data-st]").forEach(el => { const k = +el.dataset.st; if (ST[k].scored) el.onclick = () => { state.st = k; state.r = domReg(k); render(); }; });
    $("#mapSub").textContent = `Run of ${fmt(DATES[state.d])} 00 UTC · Day ${LEADS[state.li]} valid ${fmt(addDays(DATES[state.d], LEADS[state.li] - 1))} · 1.5° grid`;
    lb.querySelectorAll("button").forEach((b, li) => b.setAttribute("aria-pressed", li === state.li));
    $("#layerBtns").querySelectorAll("button").forEach(b => b.setAttribute("aria-pressed", b.dataset.layer === state.layer));
    if (state.layer === "grid") $("#mapSub").textContent += " · colour = 100 − U-Net P(rain bust) per grid cell";
    if (stLayer) $("#mapSub").textContent += " · state value = area-weighted mix of its forecast regions";
    $("#mapSource").textContent = B.states ? "Boundaries: Survey of India outline and state boundaries via DataMeet (datameet.org). Jammu & Kashmir and Ladakh are shown together." : "";
  }

  // ---------- outlook ----------
  function renderOutlook() {
    const W = 560, H = 150, l = 26, b = 22, t = 6, cw = (W - l) / NL, svg = $("#outlook");
    const stMode = state.layer === "state" && ST.length;
    const units = stMode ? ST.map((s, k) => k).filter(k => ST[k].scored) : REG.map((_, r) => r);
    const N = units.length;
    let s = "", worst = null;
    LEADS.forEach((L, li) => {
      const cs = units.map(u => stMode ? stateConf(state.d, li, u) : conf(state.d, li, u)).filter(c => c != null);
      const n = { lo: cs.filter(c => c < 50).length, mid: cs.filter(c => c >= 50 && c < 70).length, hi: cs.filter(c => c >= 70).length };
      let y = H - b; const x = l + li * cw + cw * .2, w = cw * .6;
      ["hi", "mid", "lo"].forEach(k => { const h = (H - t - b) * n[k] / N; y -= h; if (h > 0) s += `<rect x="${x}" y="${y}" width="${w}" height="${h}" fill="${css("--" + k)}"${li === state.li ? "" : ' opacity=".75"'}/>`; });
      s += `<text x="${x + w / 2}" y="${H - 6}" text-anchor="middle" font-size="10" fill="${li === state.li ? css("--ink") : css("--muted")}" font-weight="${li === state.li ? 700 : 400}">D${L}</text>`;
      if (n.lo && (!worst || n.lo > worst.n)) worst = { L, n: n.lo };
    });
    [0, N].forEach(v => { const yy = t + (H - t - b) * (1 - v / N); s += `<text x="${l - 6}" y="${yy + 4}" text-anchor="end" font-size="10" fill="${css("--muted")}">${v}</text>`; });
    svg.setAttribute("viewBox", `0 0 ${W} ${H}`); svg.setAttribute("width", "100%"); svg.innerHTML = s;
    const unit = stMode ? "states/UTs" : "regions";
    $("#outlookNote").textContent = worst ? `Most bust-prone lead: Day ${worst.L} (${worst.n} of ${N} ${unit} low confidence). Bars stack ${unit} by confidence band.`
      : `All ${unit} are medium or high confidence for Days 1–10.`;
  }

  // ---------- matrix ----------
  function renderMatrix() {
    const stMode = state.layer === "state" && ST.length;
    $("#matrixTitle").textContent = stMode ? "State / UT × lead-day confidence" : "Region × lead-day confidence";
    $("#matrixWrap").classList.toggle("tall", !!stMode);
    const rows = stMode ? ST.map((s, k) => k).filter(k => ST[k].scored) : REG.map((_, r) => r);
    let h = "<thead><tr><th></th>" + LEADS.map(L => `<th>D${L}</th>`).join("") + "</tr></thead><tbody>";
    rows.forEach(u => {
      const name = stMode ? stName(u) : regName(u);
      h += `<tr><th class="r" scope="row">${esc(name)}</th>`;
      LEADS.forEach((L, li) => {
        const c = stMode ? stateConf(state.d, li, u) : conf(state.d, li, u);
        const sel = (stMode ? u === state.st : u === state.r && state.st < 0) && li === state.li ? " sel" : "";
        h += `<td><button class="cell${sel}" style="background:${color(c)}" data-u="${u}" data-li="${li}" aria-label="${esc(name)} day ${L}: confidence ${c ?? "none"}">${c ?? "–"}</button></td>`;
      });
      h += "</tr>";
    });
    const t = $("#matrix"); t.innerHTML = h + "</tbody>";
    t.querySelectorAll(".cell").forEach(b => b.onclick = () => {
      const u = +b.dataset.u; state.li = +b.dataset.li;
      if (stMode) { state.st = u; state.r = domReg(u); } else { state.r = u; state.st = -1; }
      render();
    });
  }

  // ---------- detail ----------
  function rangeBlock(d, li, r, where) {
    const g = rng(d, li, r); if (!g) return "";
    const obs = val("obs_rain", d, li, r), mx = Math.max(g.hi * 1.15, obs > 0 ? obs / 10 * 1.1 : 0, 1);
    const pos = v => (100 * v / mx).toFixed(1) + "%";
    const showObs = state.reveal && obs >= 0;
    const txt = HI() ? `वर्षा (${esc(where)}, क्षेत्र औसत): <b>${mm(g.lo)}–${mm(g.hi)} मिमी/दिन</b> अपेक्षित (90% सीमा), सबसे संभावित <b>${mm(g.md)}</b>`
      : `Rainfall (${esc(where)}, region mean): expect <b>${mm(g.lo)}–${mm(g.hi)} mm/day</b> (90% range), most likely <b>${mm(g.md)}</b>`;
    return `<div class="range">${txt}${showObs ? `<br><span class="kv">Observed ${mm(obs / 10)} mm/day: ${obs / 10 >= g.lo && obs / 10 <= g.hi ? '<span class="ok">inside the range</span>' : '<span class="bad">outside the range</span>'}</span>` : ""}
      <div class="rangebar" aria-hidden="true"><i style="left:${pos(g.lo)};width:calc(${pos(g.hi)} - ${pos(g.lo)})"></i><em style="left:${pos(g.md)}"></em>${showObs ? `<s style="left:${pos(obs / 10)}"></s>` : ""}</div></div>`;
  }
  function whyBlock(d, li, r) {
    const sys = sysOf(d, li, r), rs = reasonsOf(d, li, r);
    return (sys.length ? `<div class="sec">${HI() ? "पूर्वानुमान में मौसम प्रणालियाँ" : "Weather systems in the forecast"}</div><div class="chips">${sys.map(s => `<span class="chip warn">${esc(s)}</span>`).join("")}</div>` : "")
      + `<div class="sec">${HI() ? "कारण" : "Why"}</div>`
      + (rs.length ? `<ul class="reasons"${HI() ? ' lang="hi"' : ""}>${rs.map(x => `<li>${esc(x)}</li>`).join("")}</ul>` : `<p class="empty">${HI() ? "कम जोखिम: कोई स्पष्ट चेतावनी संकेत नहीं।" : "Low risk: no strong warning signs."}</p>`);
  }
  function revealBlock(d, li, r) {
    const act = val("actual", d, li, r);
    const actTypes = act < 0 ? null : TYPES.filter((t, k) => (act >> k) & 1).map(t => M.type_labels[t]);
    const fr = val("fc_rain", d, li, r), orr = val("obs_rain", d, li, r);
    const ft = val("fc_tmax", d, li, r), ot = val("obs_tmax", d, li, r);
    return `<div class="reveal">
        <button class="btn ghost" id="revealBtn">${state.reveal ? "Hide" : "Show"} what actually happened</button>
        ${state.reveal ? `<p style="margin:10px 0 0">${actTypes == null ? (LIVE.has(DATES[d]) ? "Live run: not verified yet (IMD observations arrive about a day after the valid date)." : "No verification available for this date.")
          : actTypes.length ? `<span class="bad">Forecast busted</span> (${actTypes.map(esc).join(", ")}).` : `<span class="ok">Forecast held up.</span>`}
          ${fr >= 0 && orr >= 0 ? `<br><span class="kv">Rain, region mean: forecast ${(fr / 10).toFixed(1)} mm/day, observed ${(orr / 10).toFixed(1)} mm/day (IMD)</span>` : ""}
          ${ft > -9999 && ot > -9999 ? `<br><span class="kv">Max temperature: forecast ${(ft / 10).toFixed(1)} °C, observed ${(ot / 10).toFixed(1)} °C</span>` : ""}</p>` : ""}
      </div>`;
  }
  const bar = (label, v) => { const cc = v == null || v < 0 ? null : 100 - v;
    return `<div class="brow"><span>${esc(label)}</span><div class="btrack"><div class="bfill" style="width:${Math.max(0, v ?? 0)}%;background:${color(cc)}"></div></div><span class="num">${v == null || v < 0 ? "–" : v + "%"}</span></div>`; };
  function head(title, sub, c, p) {
    const b = band(c);
    return `<div class="detail-head"><div><h2>${title}</h2><p class="sub">${sub}</p></div>
      <div style="text-align:right"><div class="big" style="color:${color(c)}">${c}</div>
      <div class="bandlabel" style="color:${color(c)}">${HI() ? bandHi[b] : bandText[b]}</div><div class="kv">P(any bust) ${p}%</div></div></div>`;
  }
  function renderDetail() {
    const { d, li } = state, L = LEADS[li], el = $("#detail");
    const sub = `${HI() ? "मान्य" : "Valid"} ${HI() ? fmtHi(addDays(DATES[d], L - 1)) : fmt(addDays(DATES[d], L - 1))} · ${HI() ? "जारी" : "issued"} ${HI() ? fmtHi(DATES[d]) : fmt(DATES[d])}`;
    if (state.layer === "state" && state.st >= 0 && ST[state.st]) {
      const k = state.st, S = ST[k], c = stateConf(d, li, k);
      if (c == null) { el.innerHTML = `<h2>${esc(stName(k))}</h2><p class="empty">No forecast for this date.</p>`; return; }
      const r = domReg(k), sh = unetShare(d, li, S.cells);
      const mix = S.regions.map(([rr, w]) => `${esc(regName(rr))} ${Math.round(100 * w)}%`).join(" · ");
      el.innerHTML = head(`${esc(S.name)} <span class="kv" lang="hi">${esc(S.name_hi)}</span> · Day ${L}`, sub, c, 100 - c)
        + `<div class="bars">${TYPES.map(t => bar(typeName(t), stateP(d, li, k, "p_" + t))).join("")}</div>`
        + `<p class="kv" style="margin:-4px 0 8px">${HI() ? "आधार" : "Built from"}: ${mix}${S.coverage < 0.8 ? ` · ${Math.round(100 * S.coverage)}% of the state lies inside the forecast regions` : ""}</p>`
        + (sh != null ? `<p class="kv" style="margin:-4px 0 8px">U-Net grid: <b>${Math.round(100 * sh)}%</b> of the state's area is error-prone (P ≥ 50%).</p>` : "")
        + rangeBlock(d, li, r, regName(r)) + whyBlock(d, li, r)
        + `<p class="kv">Reasons and rainfall range come from ${esc(regName(r))}, the region covering most of ${esc(S.name)}.</p>`
        + `<button class="btn ghost" id="toRegion">Open ${esc(regName(r))}</button>` + revealBlock(d, li, r);
      $("#toRegion").onclick = () => { state.layer = "region"; state.r = r; state.st = -1; render(); };
      $("#revealBtn").onclick = () => { state.reveal = !state.reveal; renderDetail(); };
      return;
    }
    const r = state.r, c = conf(d, li, r), p = val("p", d, li, r);
    if (c == null) { el.innerHTML = `<h2>${esc(regName(r))}</h2><p class="empty">No forecast for this date.</p>`; return; }
    const an = (B.analogs[`${DATES[d]}|${L}`] || []).map(ad => {
      const o = (B.analog_outcome[`${ad}|${L}`] || [])[r];
      const tag = o === 1 ? `<span class="bad">busted</span>` : o === 0 ? `<span class="ok">held up</span>` : `<span class="kv">–</span>`;
      return `<div class="analog"><span>Run of ${fmt(ad)}, Day ${L}</span>${tag}</div>`;
    }).join("");
    let unet = "";
    if (UG) { let n = 0, hot = 0; const g = B.grid;
      for (let i = 0; i < g.lat.length; i++) for (let j = 0; j < g.lon.length; j++) if (g.region_id[i][j] === r) { const v = gridP(d, li, i, j); if (v != null) { n++; if (v >= 50) hot++; } }
      if (n) unet = `<p class="kv" style="margin:-4px 0 8px">U-Net grid: <b>${hot} of ${n}</b> cells in this region are error-prone (P ≥ 50%).</p>`; }
    el.innerHTML = head(`${esc(regName(r))} · Day ${L}`, sub, c, p)
      + `<div class="bars">${TYPES.map(t => bar(typeName(t), val("p_" + t, d, li, r))).join("")}</div>`
      + unet + rangeBlock(d, li, r, regName(r)) + whyBlock(d, li, r)
      + (an ? `<div class="sec">Most similar past forecasts</div><div class="analogs">${an}</div>` : "") + revealBlock(d, li, r);
    $("#revealBtn").onclick = () => { state.reveal = !state.reveal; renderDetail(); };
  }

  // ---------- alerts + bulletins ----------
  function alertsFor(d, thr, by) {
    const out = [];
    if (by === "state" && ST.length) {
      ST.forEach((s, k) => { if (!s.scored) return; for (let li = 0; li < NL; li++) {
        const p = stateP(d, li, k); if (p != null && p >= thr) { const r = domReg(k); out.push({ k, r, li, p, main: stateMain(d, li, k) }); } } });
    } else {
      for (let r = 0; r < R; r++) for (let li = 0; li < NL; li++) { const p = val("p", d, li, r); if (p >= thr) out.push({ k: -1, r, li, p, main: mainType(d, li, r) }); }
    }
    const area = a => a.k >= 0 ? ST[a.k].cells.length : 99;
    return out.sort((a, b) => b.p - a.p || area(b) - area(a) || a.li - b.li);
  }
  function bulletinText(A, by, hi) {
    const d = state.d, thr = state.thr, name = a => a.k >= 0 ? (hi ? ST[a.k].name_hi : ST[a.k].name) : (hi ? REG_HI[a.r] : REG[a.r]);
    const L = hi ? [`बस्टरडार पूर्वानुमान-विश्वसनीयता बुलेटिन (${by === "state" ? "राज्यवार" : "क्षेत्रवार"})`,
                    `मॉडल रन: ${fmtHi(DATES[d])}, 00 UTC   चेतावनी सीमा: बस्ट की संभावना ≥ ${thr}%`]
                 : [`BUSTRADAR FORECAST-CONFIDENCE BULLETIN (${by === "state" ? "STATE-WISE" : "REGION-WISE"})`,
                    `Model run: ${fmt(DATES[d])} 00 UTC   Alert threshold: P(bust) >= ${thr}%`];
    if (LIVE.has(DATES[d])) L.push(hi ? `लाइव रन: ${M.live_source}` : `Live run: ${M.live_source}`);
    L.push("");
    if (!A.length) L.push(hi ? "किसी भी क्षेत्र में कम विश्वसनीयता नहीं। मॉडल मार्गदर्शन का सामान्य रूप से उपयोग करें।" : "No low-confidence areas. Model guidance can be used as usual.");
    const groups = new Map();
    A.forEach(a => { const key = a.k >= 0 ? "s" + a.k : "r" + a.r; if (!groups.has(key)) groups.set(key, []); groups.get(key).push(a); });
    for (const g of groups.values()) {
      g.sort((a, b) => a.li - b.li);
      const top = g.reduce((a, b) => a.p >= b.p ? a : b), days = g.map(a => LEADS[a.li]).join(", ");
      const typ = hi ? (TL_HI[top.main] || top.main) : (top.main === "z500" ? M.type_labels[top.main] : M.type_labels[top.main].toLowerCase());
      L.push(hi ? `${name(top)}: दिन ${days} के लिए कम विश्वसनीयता (अधिकतम ${top.p}%, मुख्यतः ${typ})`
                : `${name(top).toUpperCase()}: low confidence on Day ${days} (max ${top.p}%, mainly ${typ})`);
      const why = [...sysOf(d, top.li, top.r, hi), ...reasonsOf(d, top.li, top.r, hi)].slice(0, 3);
      if (why.length) L.push((hi ? "  कारण: " : "  Why: ") + why.join("; "));
      const gr = rng(d, top.li, top.r);
      if (gr && (top.main === "rain" || gr.hi >= 20)) L.push(hi ? `  वर्षा (दिन ${LEADS[top.li]}): ${mm(gr.lo)}–${mm(gr.hi)} मिमी/दिन अपेक्षित (90% सीमा)`
                                                         : `  Rain (Day ${LEADS[top.li]}): expect ${mm(gr.lo)}-${mm(gr.hi)} mm/day (90% range)`);
    }
    L.push("", hi ? "विश्वसनीयता सूचकांक = 100 − बस्ट की संभावना। बस्ट = सामान्य से बहुत बड़ी पूर्वानुमान त्रुटि। बस्टरडार द्वारा स्वतः तैयार।"
                   : "Confidence Index = 100 - P(bust). Bust = forecast error far larger than usual. Generated automatically by BustRadar.");
    return L.join("\n");
  }
  function renderAlerts() {
    const by = ST.length ? state.by : "region";
    const A = alertsFor(state.d, state.thr, by);
    const nm = a => a.k >= 0 ? stName(a.k) : regName(a.r);
    $("#alerts").innerHTML = A.length ? A.slice(0, 80).map(a => `
      <div class="alert" data-r="${a.r}" data-k="${a.k}" data-li="${a.li}" role="button" tabindex="0">
        <div class="p">${a.p}%</div>
        <div><div class="t">${esc(nm(a))} · Day ${LEADS[a.li]} · ${esc(typeName(a.main))} ${HI() ? "जोखिम" : "risk"}</div>
        <div class="r"${HI() ? ' lang="hi"' : ""}>${esc([...sysOf(state.d, a.li, a.r), ...reasonsOf(state.d, a.li, a.r)].slice(0, 3).join(" · ") || "Elevated bust probability")}</div></div>
      </div>`).join("") : `<p class="empty">No ${by === "state" ? "state" : "region"} reaches ${state.thr}% for this run. Forecasts can be used with normal confidence.</p>`;
    $("#alerts").querySelectorAll(".alert").forEach(el => {
      const go = () => { state.li = +el.dataset.li; state.r = +el.dataset.r; const k = +el.dataset.k;
        if (k >= 0) { state.layer = "state"; state.st = k; } else { state.layer = "region"; state.st = -1; }
        render(); window.scrollTo({ top: 0, behavior: "smooth" }); };
      el.onclick = go; el.onkeydown = e => { if (e.key === "Enter") go(); };
    });
    $("#bulletin").textContent = bulletinText(A, by, false);
    $("#bulletinHi").textContent = bulletinText(A, by, true);
    $("#bulletin").hidden = state.bl === "hi"; $("#bulletinHi").hidden = state.bl === "en";
    $("#bullets").style.gridTemplateColumns = state.bl === "both" ? "" : "1fr";
    document.querySelectorAll("[data-by]").forEach(b => b.setAttribute("aria-pressed", b.dataset.by === by));
    document.querySelectorAll("[data-bl]").forEach(b => b.setAttribute("aria-pressed", b.dataset.bl === state.bl));
  }
  $("#copyBulletin").onclick = () => {
    const t = [state.bl !== "hi" ? $("#bulletin").textContent : "", state.bl !== "en" ? $("#bulletinHi").textContent : ""].filter(Boolean).join("\n\n");
    const st = $("#copyStatus");
    const fallback = () => { const rg = document.createRange(); rg.selectNodeContents($("#bullets")); const s = getSelection(); s.removeAllRanges(); s.addRange(rg); st.textContent = "Selected. Press Ctrl+C to copy."; };
    try { navigator.clipboard.writeText(t).then(() => st.textContent = "Copied.", fallback); } catch (e) { fallback(); }
  };

  // ---------- report card: were yesterday's alerts right? ----------
  const outcome = (d, li, r, thr) => {           // hit | fa | miss | cn | na
    const a = val("actual", d, li, r), p = val("p", d, li, r);
    if (a < 0 || p < 0) return "na";
    const bust = a > 0, alert = p >= thr;
    return alert && bust ? "hit" : alert ? "fa" : bust ? "miss" : "cn";
  };
  function verifyDay(V, thr) {                   // all forecasts valid on date V
    const cells = [];
    for (let li = 0; li < NL; li++) {
      const dd = DATES.indexOf(addDays(V, -(LEADS[li] - 1)));
      for (let r = 0; r < R; r++) cells.push({ li, r, d: dd, o: dd < 0 ? "na" : outcome(dd, li, r, thr) });
    }
    return cells;
  }
  const tally = cells => cells.reduce((t, c) => (t[c.o]++, t), { hit: 0, fa: 0, miss: 0, cn: 0, na: 0 });
  function renderReport() {
    const thr = state.thr, today = DATES[state.d], V = addDays(today, -1);
    const cells = verifyDay(V, thr), T = tally(cells), n = T.hit + T.fa + T.miss + T.cn;
    $("#rcTitle").textContent = `Yesterday's report card · ${fmt(V)}`;
    $("#rcSub").textContent = `As seen on ${fmt(today)}: every BustRadar forecast valid on ${fmt(V)} (issued 1 to 10 days earlier), checked against what happened. Alert = P(bust) ≥ ${thr}%.`;
    const pct = (a, b) => b ? Math.round(100 * a / b) + "%" : "–";
    $("#rcTiles").innerHTML = !n ? `<p class="empty">${LIVE.has(today) || LIVE.has(V) ? "Yesterday is not verified yet: IMD observations for live runs arrive about a day later (app/live.py fetches them)." : "No verified forecasts for yesterday in this build."}</p>`
      : [["Alerts issued", T.hit + T.fa], ["Caught", T.hit, "var(--hi)"], ["False alarms", T.fa, "var(--mid)"], ["Missed", T.miss, "var(--lo)"], ["Correct quiet", T.cn],
         ["Busts caught", pct(T.hit, T.hit + T.miss)], ["Alerts that were right", pct(T.hit, T.hit + T.fa)]]
        .map(([k, v, c]) => `<div class="tile"><b${c ? ` style="color:${c}"` : ""}>${v}</b><span>${k}</span></div>`).join("");
    const sym = { hit: "✓", fa: "!", miss: "✗", cn: "·", na: "" };
    const word = { hit: "caught", fa: "false alarm", miss: "missed", cn: "correct quiet", na: "no data" };
    let h = "<thead><tr><th></th>" + LEADS.map(L => `<th title="issued ${L} day(s) ahead">D${L}</th>`).join("") + "</tr></thead><tbody>";
    REG.forEach((nm, r) => {
      h += `<tr><th class="r" scope="row">${esc(regName(r))}</th>` + LEADS.map((L, li) => {
        const c = cells.find(x => x.li === li && x.r === r), p = c.d >= 0 ? val("p", c.d, li, r) : -1;
        return `<td><span class="o ${c.o}" title="${esc(nm)}, Day-${L} forecast issued ${c.d >= 0 ? fmt(DATES[c.d]) : "–"}: P(bust) ${p >= 0 ? p + "%" : "–"}, ${word[c.o]}">${c.o === "na" ? "–" : sym[c.o] + (p >= 0 ? " " + p : "")}</span></td>`;
      }).join("") + "</tr>";
    });
    $("#rcTable").innerHTML = h + "</tbody>";
    // rain ranges for yesterday (Day-1 forecast issued yesterday)
    const dy = DATES.indexOf(V);
    let rr = `<thead><tr><th>Region</th><th>Forecast</th><th>90% range</th><th>Observed</th><th></th></tr></thead><tbody>`, inside = 0, tot = 0;
    REG.forEach((nm, r) => {
      const g = dy >= 0 ? rng(dy, 0, r) : null, o = dy >= 0 ? val("obs_rain", dy, 0, r) : -1, f = dy >= 0 ? val("fc_rain", dy, 0, r) : -1;
      const ok = g && o >= 0 ? (o / 10 >= g.lo && o / 10 <= g.hi) : null; if (ok != null) { tot++; inside += ok; }
      rr += `<tr><td>${esc(regName(r))}</td><td class="num">${f >= 0 ? mm(f / 10) : "–"}</td><td class="num">${g ? mm(g.lo) + "–" + mm(g.hi) : "–"}</td><td class="num">${o >= 0 ? mm(o / 10) : "–"}</td><td>${ok == null ? "" : ok ? '<span class="ok">inside</span>' : '<span class="bad">outside</span>'}</td></tr>`;
    });
    $("#rcRain").innerHTML = rr + `</tbody><tfoot><tr><td colspan="5" class="kv" style="text-align:left">${tot ? `${inside} of ${tot} regions inside the range (expected about 9 in 10)` : "No verified Day-1 rainfall for yesterday."}</td></tr></tfoot>`;
    // last 30 days
    const days = Array.from({ length: 30 }, (_, k) => addDays(V, k - 29));
    const per = days.map(v => tally(verifyDay(v, thr)));
    const S = per.reduce((a, t) => { for (const k in t) a[k] += t[k]; return a; }, { hit: 0, fa: 0, miss: 0, cn: 0, na: 0 });
    const W = 560, H = 170, l = 30, b = 22, t = 8, cw = (W - l) / 30, mx = Math.max(4, ...per.map(q => q.hit + q.fa + q.miss));
    let s = "";
    per.forEach((q, k) => {
      let y = H - b; const x = l + k * cw + cw * .15, w = cw * .7;
      [["hit", "--hi"], ["miss", "--lo"], ["fa", "--mid"]].forEach(([key, col]) => { const hh = (H - t - b) * q[key] / mx; y -= hh; if (hh > 0) s += `<rect x="${x}" y="${y}" width="${w}" height="${hh}" fill="${css(col)}"><title>${days[k]}: ${q[key]} ${word[key]}</title></rect>`; });
      if (k % 5 === 4 || k === 29) s += `<text x="${x + w / 2}" y="${H - 6}" text-anchor="${k === 29 ? "end" : "middle"}" font-size="9.5" fill="${css("--muted")}">${days[k].slice(5)}</text>`;
    });
    [0, mx].forEach(v => { const yy = t + (H - t - b) * (1 - v / mx); s += `<text x="${l - 6}" y="${yy + 4}" text-anchor="end" font-size="10" fill="${css("--muted")}">${v}</text>`; });
    const sv = $("#rc30"); sv.setAttribute("viewBox", `0 0 ${W} ${H}`); sv.setAttribute("width", "100%"); sv.innerHTML = s;
    $("#rc30Sub").textContent = `Valid dates ${fmt(days[0])} to ${fmt(V)}, all regions and lead days. Green = caught, red = missed, amber = false alarm.`;
    $("#rc30Tiles").innerHTML = [["Busts caught", pct(S.hit, S.hit + S.miss)], ["Alerts that were right", pct(S.hit, S.hit + S.fa)],
      ["Quiet days right", pct(S.cn, S.cn + S.miss)], ["Checked forecasts", S.hit + S.fa + S.miss + S.cn]]
      .map(([k, v]) => `<div class="tile"><b>${v}</b><span>${k}</span></div>`).join("");
  }

  // ---------- replay ----------
  function renderEvents() {
    const E = B.events || [];
    if (!E.length) { $("#events").innerHTML = `<p class="empty">No events in the data range.</p>`; return; }
    $("#events").innerHTML = E.map((e, k) => `<button class="event" aria-pressed="${k === state.ev}" data-k="${k}"><b>${esc(e.name)}</b>
      <span>${esc(e.region)} · ${fmt(e.start)} · ${e.split === "test" ? "held-out test year" : e.split === "val" ? "validation year" : "training year"}</span></button>`).join("");
    $("#events").querySelectorAll(".event").forEach(b => b.onclick = () => { state.ev = +b.dataset.k; renderEvents(); });
    const e = E[state.ev];
    $("#evTitle").textContent = e.name;
    $("#evSub").textContent = `${e.region} · ${fmt(e.start)} to ${fmt(e.end)} · ${M.type_labels[e.type] || "Any"} bust risk${e.systems.length ? " · detected: " + e.systems.join(", ") : ""}`;
    const W = 560, H = 250, l = 40, b = 34, t = 14, cw = (W - l - 10) / NL;
    const mc = css("--muted"), lc = css("--line");
    let s = "";
    [0, 25, 50, 75, 100].forEach(v => { const y = t + (H - t - b) * (1 - v / 100); s += `<line x1="${l}" x2="${W - 10}" y1="${y}" y2="${y}" stroke="${lc}"/><text x="${l - 6}" y="${y + 4}" text-anchor="end" font-size="10" fill="${mc}">${v}%</text>`; });
    e.p.forEach((p, i) => {
      const x = l + i * cw + cw * .18, w = cw * .64;
      if (p != null) { const h = (H - t - b) * p / 100, y = H - b - h; s += `<rect x="${x}" y="${y}" width="${w}" height="${h}" rx="3" fill="${color(100 - p)}"/><text x="${x + w / 2}" y="${y - 4}" text-anchor="middle" font-size="10" fill="${css("--ink")}" font-family="IBM Plex Mono,monospace">${p}</text>`; }
      if (e.actual[i] === 1) s += `<text x="${x + w / 2}" y="${H - b + 26}" text-anchor="middle" font-size="12" fill="${css("--lo")}">★</text>`;
      s += `<text x="${x + w / 2}" y="${H - b + 14}" text-anchor="middle" font-size="10" fill="${mc}">D${LEADS[i]}</text>`;
    });
    const svg = $("#evChart"); svg.setAttribute("viewBox", `0 0 ${W} ${H + 10}`); svg.setAttribute("width", "100%"); svg.innerHTML = s;
    const firstWarn = e.p.map((p, i) => p != null && p >= 50 ? LEADS[i] : 0).reduce((a, x) => Math.max(a, x), 0);
    $("#evNote").textContent = (firstWarn ? `BustRadar gave ≥50% bust probability up to ${firstWarn} days ahead. ` : "BustRadar did not reach 50% for this event. ")
      + "Bars: bust probability for forecasts of the event days, by how many days ahead they were issued. ★ = the forecast really busted.";
    const openDate = addDays(e.start, -2), k = DATES.indexOf(openDate);
    $("#evOpen").disabled = k < 0;
    $("#evOpen").textContent = k < 0 ? "Map view covers the validation and test years only" : "Open the Day-3 forecast in the map";
    $("#evOpen").onclick = () => { if (k < 0) return; state.d = k; state.li = 2; state.r = REG.indexOf(e.region); state.layer = "region"; state.st = -1; document.querySelector('[data-tab="forecast"]').click(); };
  }

  // ---------- scorecard ----------
  function renderScore() {
    const m = B.metrics || [];
    const lab = t => t === "bust" ? "Any bust" : t === "bust_rain_rel" ? "Rain (relative)" : (M.type_labels[t.replace("bust_", "")] || t);
    const cols = [["bust_rate", "Bust rate", v => (100 * v).toFixed(1) + "%"], ["AUC_climatology", "Climatology"], ["AUC_amount_only", "Amount only"],
      ["AUC_v1_features", "Basic features"], ["AUC_BustRadar", "BustRadar"], ["Brier_skill_vs_clim", "Brier skill"], ["hit_rate_top10pct", "Top-10% alerts correct", v => (100 * v).toFixed(0) + "%"]];
    $("#metrics").innerHTML = m.length ? `<thead><tr><th>Bust type</th>${cols.map(c => `<th>${c[1]}</th>`).join("")}</tr></thead><tbody>` + m.map(row =>
      `<tr><td>${esc(lab(row.target))}</td>${cols.map(c => `<td class="num"${c[0] === "AUC_BustRadar" ? ' style="font-weight:700"' : ""}>${row[c[0]] == null ? "–" : (c[2] ? c[2](row[c[0]]) : row[c[0]].toFixed(3))}</td>`).join("")}</tr>`).join("") + "</tbody>"
      : `<tr><td class="empty">No metrics file found.</td></tr>`;
    const A = B.auc_by_lead || [], svg = $("#aucChart"), W = 520, H = 260, l = 38, b = 30, t = 10;
    const keys = A.length ? Object.keys(A[0]).filter(k => k !== "lead") : [];
    const pal = { bust_rain: "#0b6fb8", bust_heat: "#d64541", bust_wind: "#7b4fa0", bust_z500: "#2e9e5b", bust: css("--ink"), bust_rain_rel: "#e8772e" };
    const x = i => l + (W - l - 140) * i / Math.max(1, NL - 1), y = v => t + (H - t - b) * (1 - (v - .4) / .6);
    let s = "";
    [.5, .6, .7, .8, .9, 1].forEach(v => s += `<line x1="${l}" x2="${W - 140}" y1="${y(v)}" y2="${y(v)}" stroke="${css("--line")}"/><text x="${l - 6}" y="${y(v) + 4}" font-size="10" text-anchor="end" fill="${css("--muted")}">${v.toFixed(1)}</text>`);
    LEADS.forEach((L, i) => s += `<text x="${x(i)}" y="${H - b + 16}" font-size="10" text-anchor="middle" fill="${css("--muted")}">D${L}</text>`);
    keys.forEach((k, n) => {
      const pts = A.map((row, i) => row[k] == null ? null : [x(i), y(row[k])]).filter(Boolean);
      s += `<polyline fill="none" stroke="${pal[k] || "#888"}" stroke-width="2" points="${pts.map(p => p.join(",")).join(" ")}"/>`;
      pts.forEach(p => s += `<circle cx="${p[0]}" cy="${p[1]}" r="2.5" fill="${pal[k] || "#888"}"/>`);
      s += `<rect x="${W - 128}" y="${t + n * 18}" width="10" height="10" rx="2" fill="${pal[k] || "#888"}"/><text x="${W - 113}" y="${t + n * 18 + 9}" font-size="11" fill="${css("--ink")}">${esc(lab(k))}</text>`;
    });
    svg.setAttribute("viewBox", `0 0 ${W} ${H}`); svg.setAttribute("width", "100%"); svg.innerHTML = keys.length ? s : "";
    const best = {};
    (B.systems_table || []).forEach(rw => { if (rw.cases >= 30 && (!best[rw.system] || rw.times_more_likely > best[rw.system].times_more_likely)) best[rw.system] = rw; });
    const S = Object.values(best).sort((a, b) => b.times_more_likely - a.times_more_likely);
    const sv = $("#sysChart"), rowH = 28, W2 = 560, lab2 = 280, H2 = Math.max(60, S.length * rowH + 30);
    const mx = Math.max(2, ...S.map(r => r.times_more_likely));
    let q = "";
    S.forEach((rw, i) => {
      const w = (W2 - lab2 - 50) * rw.times_more_likely / mx, yy = 10 + i * rowH;
      const name = (M.system_labels[rw.system] || rw.system).replace(/^observed /, "Observed ") + " → " + lab(rw.target).toLowerCase();
      q += `<text x="${lab2 - 8}" y="${yy + 14}" text-anchor="end" font-size="11.5" fill="${css("--ink")}">${esc(name)}</text>`
        + `<rect x="${lab2}" y="${yy + 3}" width="${w}" height="16" rx="3" fill="${rw.times_more_likely > 1 ? css("--lo") : css("--hi")}"/>`
        + `<text x="${lab2 + w + 6}" y="${yy + 15}" font-size="11" fill="${css("--ink")}" font-family="IBM Plex Mono,monospace">${rw.times_more_likely.toFixed(1)}×</text>`;
    });
    const x1 = lab2 + (W2 - lab2 - 50) / mx;
    if (S.length) q += `<line x1="${x1}" x2="${x1}" y1="4" y2="${S.length * rowH + 12}" stroke="${css("--muted")}" stroke-dasharray="3 3"/>`;
    sv.setAttribute("viewBox", `0 0 ${W2} ${H2}`); sv.setAttribute("width", "100%");
    sv.innerHTML = S.length ? q : `<text x="10" y="30" font-size="12" fill="${css("--muted")}">No weather-system statistics in this build.</text>`;
    const RC = B.rain_range_coverage || [];
    $("#rangeTable").innerHTML = RC.length ? `<thead><tr><th>Lead day</th>${RC.map(r => `<th>D${r.lead}</th>`).join("")}</tr></thead><tbody>`
      + `<tr><td>Inside 90% range</td>${RC.map(r => `<td class="num">${Math.round(100 * r.coverage)}%</td>`).join("")}</tr>`
      + `<tr><td>Typical width (mm/day)</td>${RC.map(r => `<td class="num">${r.median_width_mm.toFixed(1)}</td>`).join("")}</tr></tbody>`
      : `<tr><td class="empty">Rainfall ranges not in this build (re-run notebook 02).</td></tr>`;
    $("#thrInfo").innerHTML = M.alert_threshold ? `Default alert threshold: <b class="num">P(bust) ≥ ${Math.round(100 * M.alert_threshold)}%</b>. The slider on the Forecast tab can change it.` : "Not available in this build.";
  }
  function renderUnetScore() {
    const um = B.unet && B.unet.metrics; $("#unetCard").hidden = !um; if (!um) return;
    const rows = [["U-Net deep ensemble", um.AUC_unet], ["Climatology (cell bust rate)", um.AUC_climatology], ["Lagged-run spread only", um.AUC_lagged_spread_only]];
    $("#unetTable").innerHTML = `<thead><tr><th>Method</th><th>ROC-AUC</th></tr></thead><tbody>` + rows.map(r => `<tr><td>${r[0]}</td><td class="num">${r[1] == null ? "–" : r[1].toFixed(3)}</td></tr>`).join("")
      + `<tr><td>Brier skill vs climatology</td><td class="num">${um.Brier_skill_vs_clim?.toFixed(3) ?? "–"}</td></tr>`
      + `<tr><td>AUC by lead day (D1…D10)</td><td class="num">${(um.AUC_by_lead || []).map(v => v == null ? "–" : v.toFixed(2)).join(" ")}</td></tr></tbody>`;
  }

  // ---------- API doc ----------
  function renderApi() {
    $("#apiDoc").textContent = [
      "GET /api/dates                                  -> available model-run dates",
      "GET /api/forecast?date=2021-05-13               -> confidence for every region x lead day",
      "GET /api/forecast?date=2021-05-13&lead=3        -> one lead day",
      "GET /api/region?date=2021-05-13&region=West%20Coast -> Day 1-10 detail with reasons and rain range",
      "GET /api/states?date=2021-05-13[&lead=3]        -> confidence for every state / UT",
      "GET /api/alerts?date=2021-05-13&min_p=50&by=state&lang=hi -> alerts + text bulletin (by=state|region, lang=en|hi)",
      "GET /api/report?date=2021-05-14&min_p=50        -> yesterday's report card (caught / missed / false alarms)",
      "GET /api/events                                  -> event replays",
      "GET /api/metrics                                 -> skill scores",
    ].join("\n");
    const d = state.d, r = state.r;
    const ex = { date: DATES[d], region: REG[r], forecasts: LEADS.slice(0, 3).map((L, li) => ({
      lead: L, valid_date: addDays(DATES[d], L - 1), confidence: conf(d, li, r), p_bust: val("p", d, li, r) / 100,
      p_by_type: Object.fromEntries(TYPES.map(t => [t, val("p_" + t, d, li, r) / 100])), rain_range_mm: rng(d, li, r),
      systems: sysOf(d, li, r, false), reasons: reasonsOf(d, li, r, false), reasons_hi: reasonsOf(d, li, r, true) })) };
    $("#apiExample").textContent = JSON.stringify(ex, null, 2);
  }

  function render() {
    di.value = DATES[state.d];
    const sp = LIVE.has(DATES[state.d]) ? "live" : B.date_split[state.d];
    const bdg = $("#splitBadge"); bdg.className = "badge " + sp;
    bdg.textContent = sp === "live" ? "Live run" : sp === "test" ? "Held-out test year" : sp === "val" ? "Validation year" : sp === "fit" ? "Training year" : "";
    const lbn = $("#liveBanner"); lbn.hidden = sp !== "live";
    if (sp === "live") lbn.innerHTML = `<b>Live forecast</b> from ${esc(M.live_source)}, run of ${fmt(DATES[state.d])}. Not verified yet. The ECMWF model has been upgraded since the 2016–2022 training years, so treat probabilities as indicative.`;
    document.querySelectorAll("[data-lang]").forEach(b => b.setAttribute("aria-pressed", b.dataset.lang === state.lang));
    if (state.tab === "forecast") { renderMap(); renderOutlook(); renderMatrix(); renderDetail(); renderAlerts(); }
    if (state.tab === "report") renderReport();
    if (state.tab === "replay") renderEvents();
    if (state.tab === "score") { renderScore(); renderUnetScore(); }
    if (state.tab === "api") renderApi();
  }
  render();
  matchMedia("(prefers-color-scheme: dark)").addEventListener?.("change", () => { paintThemeBtn(); render(); });
})();
</script>
</body>
</html>
'''

# State boundaries (DataMeet / Survey of India), simplified to the 1.5° grid
STATES_JSON = r'''{"source":"DataMeet (datameet.org): Survey of India national outline; state boundaries as in the DataMeet states map (pre-2019; J&K and Ladakh shown together)","grid":{"lat":[6.0,7.5,9.0,10.5,12.0,13.5,15.0,16.5,18.0,19.5,21.0,22.5,24.0,25.5,27.0,28.5,30.0,31.5,33.0,34.5,36.0,37.5,39.0,40.5],"lon":[66.0,67.5,69.0,70.5,72.0,73.5,75.0,76.5,78.0,79.5,81.0,82.5,84.0,85.5,87.0,88.5,90.0,91.5,93.0,94.5,96.0,97.5,99.0,100.5]},"india_outline":[[[84.77,19.08],[84.34,18.54],[84.14,18.35],[83.99,18.36],[84.12,18.3],[83.56,18.02],[83.22,17.59],[82.62,17.3],[82.31,17.03],[82.25,16.89],[82.36,16.82],[82.34,16.98],[82.38,16.88],[82.31,16.55],[82.15,16.49],[82.18,16.56],[81.71,16.3],[81.55,16.39],[81.31,16.36],[81.01,15.76],[80.94,15.81],[80.99,15.76],[80.94,15.73],[80.86,15.82],[80.92,15.73],[80.84,15.71],[80.76,15.88],[80.5,15.86],[80.22,15.55],[80.13,15.56],[80.21,15.5],[80.08,15.2],[80.03,15.21],[80.07,14.81],[80.18,14.59],[80.09,14.53],[80.19,14.56],[80.13,14.14],[80.35,13.29],[80.16,12.47],[79.77,11.74],[79.88,10.29],[79.53,10.36],[79.28,10.24],[79.26,10.04],[78.89,9.48],[79.05,9.3],[79.19,9.28],[78.86,9.25],[78.27,9.01],[78.21,9.05],[78.27,9.0],[78.17,8.88],[78.21,8.77],[78.07,8.37],[77.55,8.08],[77.32,8.12],[77.01,8.36],[76.55,8.89],[75.82,11.17],[75.53,11.7],[75.32,11.97],[75.2,12.0],[74.83,12.83],[74.69,13.36],[74.69,13.45],[74.74,13.39],[74.75,13.46],[74.69,13.46],[74.66,13.63],[74.76,13.64],[74.67,13.71],[74.67,13.64],[74.63,13.86],[74.52,13.99],[74.43,14.26],[74.53,14.24],[74.43,14.28],[74.36,14.5],[74.44,14.47],[74.37,14.56],[74.31,14.52],[74.29,14.59],[74.43,14.62],[74.28,14.61],[74.25,14.74],[74.09,14.8],[74.25,14.87],[74.12,14.84],[73.91,15.08],[73.96,15.19],[73.78,15.41],[73.94,15.43],[73.79,15.46],[73.83,15.51],[73.77,15.49],[73.77,15.63],[73.49,15.97],[73.37,16.37],[73.47,16.42],[73.37,16.39],[73.32,16.51],[73.32,16.6],[73.4,16.59],[73.32,16.64],[73.33,16.97],[73.26,17.05],[73.31,17.08],[73.19,17.3],[73.25,17.32],[73.17,17.4],[73.13,17.83],[72.93,18.21],[72.93,18.53],[72.79,18.94],[72.8,19.33],[72.67,19.76],[72.72,19.82],[72.64,19.85],[72.68,19.96],[72.77,19.9],[72.7,20.08],[72.89,20.57],[72.78,20.9],[72.85,20.95],[72.76,20.93],[72.72,21.14],[72.63,21.08],[72.65,21.23],[72.59,21.28],[72.74,21.55],[72.61,21.58],[72.84,21.67],[72.54,21.66],[72.64,21.95],[72.52,21.88],[72.5,21.98],[72.59,22.21],[72.75,22.17],[72.92,22.28],[72.54,22.28],[72.49,22.2],[72.36,22.38],[72.42,22.23],[72.36,22.27],[72.34,22.12],[72.29,22.2],[72.28,21.93],[72.24,22.05],[72.3,22.11],[72.17,22.04],[72.22,21.96],[72.15,21.98],[72.25,21.9],[72.27,21.74],[72.18,21.82],[72.31,21.63],[72.09,21.29],[72.11,21.2],[71.44,20.87],[71.07,20.73],[70.85,20.75],[70.82,20.69],[70.44,20.85],[70.1,21.1],[68.94,22.31],[69.07,22.48],[69.07,22.4],[69.19,22.42],[69.16,22.31],[69.23,22.26],[69.49,22.34],[69.5,22.44],[69.58,22.32],[69.73,22.47],[69.8,22.4],[69.98,22.54],[70.16,22.55],[70.49,23.08],[70.35,22.93],[70.2,22.99],[70.16,22.94],[70.14,23.01],[70.13,22.92],[69.8,22.85],[69.71,22.73],[69.63,22.8],[69.45,22.78],[69.19,22.84],[68.65,23.15],[68.58,23.23],[68.69,23.31],[68.56,23.39],[68.48,23.55],[68.52,23.69],[68.76,23.87],[68.6,23.85],[68.53,23.76],[68.51,23.82],[68.66,23.92],[68.55,23.97],[68.75,23.97],[68.81,24.31],[68.87,24.21],[68.94,24.3],[69.01,24.22],[69.59,24.29],[69.73,24.17],[70.02,24.17],[70.11,24.29],[70.57,24.42],[70.58,24.25],[70.71,24.22],[71.12,24.4],[71.0,24.45],[70.99,24.55],[71.1,24.69],[70.89,25.15],[70.67,25.4],[70.66,25.71],[70.28,25.71],[70.1,25.94],[70.17,26.55],[69.8,26.6],[69.51,26.75],[69.58,27.17],[70.02,27.56],[70.13,27.81],[70.37,28.01],[70.59,28.01],[70.74,27.74],[70.88,27.71],[71.9,27.96],[71.94,28.13],[72.21,28.39],[72.39,28.77],[72.95,29.03],[73.28,29.56],[73.4,29.94],[73.97,30.19],[73.89,30.36],[73.97,30.43],[73.94,30.49],[74.08,30.53],[74.57,31.05],[74.7,31.07],[74.69,31.13],[74.58,31.09],[74.52,31.14],[74.53,31.32],[74.65,31.46],[74.49,31.72],[74.61,31.89],[74.93,32.07],[75.27,32.1],[75.38,32.24],[75.34,32.34],[75.11,32.47],[74.69,32.48],[74.63,32.6],[74.7,32.84],[74.63,32.75],[74.37,32.76],[73.63,33.09],[73.66,33.21],[73.56,33.37],[73.63,33.53],[73.56,33.62],[73.59,33.88],[73.39,34.38],[73.45,34.57],[73.65,34.57],[73.75,34.79],[74.03,34.88],[74.13,35.11],[73.72,35.23],[73.78,35.53],[73.27,35.63],[73.14,35.72],[73.1,35.88],[72.69,35.83],[72.53,35.92],[72.6,36.26],[72.69,36.25],[72.88,36.44],[72.99,36.46],[73.11,36.61],[73.09,36.7],[73.88,36.7],[73.69,36.91],[74.06,36.81],[74.43,36.99],[74.58,36.95],[74.58,37.04],[74.69,37.08],[74.92,36.91],[75.33,37.06],[75.47,36.81],[75.62,36.76],[75.77,36.57],[76.64,36.18],[76.8,36.05],[76.72,35.95],[76.81,35.84],[77.36,35.72],[77.49,35.53],[77.32,35.54],[77.38,35.48],[77.73,35.52],[77.98,35.46],[77.95,35.61],[78.14,35.54],[78.2,35.67],[78.42,35.79],[78.96,35.89],[79.13,35.84],[79.22,35.98],[79.38,36.0],[79.42,35.9],[79.74,35.8],[80.0,35.84],[80.11,35.68],[80.29,35.61],[80.33,35.47],[80.07,34.71],[79.78,34.63],[79.79,34.49],[79.51,34.47],[79.59,34.24],[79.43,34.02],[79.17,34.07],[78.91,33.98],[79.11,33.62],[78.92,33.63],[78.95,33.38],[79.1,33.29],[79.45,33.26],[79.33,33.01],[79.63,32.74],[79.45,32.53],[79.32,32.59],[78.99,32.34],[78.83,32.44],[78.77,32.7],[78.46,32.58],[78.4,32.53],[78.54,32.41],[78.46,32.24],[78.61,32.21],[78.61,32.12],[78.79,32.0],[78.71,31.79],[78.85,31.61],[78.72,31.51],[78.89,31.27],[79.06,31.47],[79.14,31.43],[79.43,31.03],[79.6,30.94],[79.87,30.97],[80.24,30.76],[80.23,30.57],[80.6,30.48],[81.03,30.25],[80.9,30.22],[80.74,30.0],[80.37,29.75],[80.41,29.6],[80.25,29.44],[80.3,29.2],[80.15,29.1],[80.07,28.83],[80.51,28.56],[80.57,28.69],[80.91,28.46],[81.21,28.36],[81.32,28.14],[81.43,28.17],[81.89,27.86],[82.07,27.92],[82.46,27.68],[82.71,27.73],[82.74,27.5],[83.18,27.45],[83.31,27.33],[83.4,27.48],[83.87,27.34],[83.85,27.45],[84.03,27.44],[84.15,27.52],[84.29,27.38],[84.63,27.34],[84.69,27.22],[84.65,27.05],[84.96,26.96],[85.03,26.85],[85.2,26.87],[85.21,26.76],[85.64,26.87],[85.85,26.57],[86.03,26.67],[86.35,26.62],[86.74,26.42],[87.07,26.59],[87.09,26.45],[87.34,26.35],[87.46,26.44],[87.61,26.38],[87.89,26.49],[88.02,26.35],[88.19,26.73],[88.13,26.99],[87.99,27.11],[88.05,27.49],[88.2,27.79],[88.14,27.96],[88.4,27.98],[88.63,28.13],[88.84,28.01],[88.89,27.86],[88.77,27.56],[88.82,27.4],[88.93,27.33],[88.76,27.14],[88.88,27.11],[88.88,26.95],[89.03,26.94],[89.14,26.81],[89.38,26.87],[89.78,26.7],[90.13,26.75],[90.22,26.85],[90.41,26.9],[90.72,26.77],[91.69,26.8],[91.89,26.92],[92.06,26.85],[92.12,26.96],[92.03,27.16],[92.04,27.27],[92.12,27.29],[92.02,27.48],[91.65,27.48],[91.56,27.63],[91.64,27.76],[91.55,27.86],[91.83,27.81],[91.92,27.71],[92.22,27.86],[92.32,27.78],[92.57,27.82],[92.74,27.99],[92.69,28.13],[93.22,28.33],[93.19,28.44],[93.34,28.64],[93.93,28.67],[94.22,29.08],[94.56,29.23],[94.63,29.35],[94.8,29.16],[95.45,29.03],[95.6,29.26],[96.09,29.46],[96.25,29.23],[96.4,29.25],[96.12,29.07],[96.17,28.9],[96.53,29.08],[96.48,28.99],[96.62,28.77],[96.27,28.41],[96.4,28.34],[96.67,28.46],[97.0,28.31],[97.09,28.36],[97.4,28.19],[97.31,28.07],[97.42,28.01],[97.39,27.89],[97.26,27.9],[96.9,27.61],[96.91,27.45],[97.14,27.09],[96.87,27.18],[96.88,27.26],[96.71,27.37],[96.23,27.28],[95.43,26.69],[95.15,26.61],[95.07,26.44],[95.14,26.38],[95.12,26.1],[95.18,26.07],[95.02,25.9],[95.05,25.76],[94.9,25.56],[94.64,25.4],[94.58,25.21],[94.74,25.13],[94.72,24.94],[94.32,24.33],[94.16,23.85],[93.81,23.92],[93.75,24.0],[93.51,23.94],[93.35,24.11],[93.44,23.68],[93.39,23.13],[93.3,23.0],[93.13,23.04],[93.11,22.53],[93.21,22.26],[93.15,22.18],[93.04,22.2],[93.01,21.98],[92.95,22.03],[92.91,21.94],[92.72,22.15],[92.61,21.98],[92.52,22.7],[92.38,22.93],[92.41,23.24],[92.28,23.72],[92.22,23.65],[92.15,23.73],[92.05,23.65],[91.96,23.73],[91.98,23.48],[91.78,23.28],[91.84,23.1],[91.62,22.94],[91.42,23.28],[91.42,23.07],[91.37,23.07],[91.32,23.36],[91.16,23.6],[91.24,23.92],[91.39,23.98],[91.38,24.1],[91.6,24.08],[91.67,24.23],[91.76,24.14],[91.75,24.24],[91.91,24.14],[91.93,24.34],[92.17,24.42],[92.28,24.79],[92.24,24.9],[92.5,24.87],[92.44,25.03],[92.07,25.19],[91.65,25.12],[91.27,25.21],[90.45,25.14],[89.84,25.3],[89.88,25.62],[89.82,25.82],[89.89,25.94],[89.7,26.22],[89.6,26.16],[89.65,26.07],[89.58,25.97],[89.36,26.01],[89.16,26.14],[89.09,26.4],[88.97,26.46],[88.92,26.4],[89.05,26.24],[88.91,26.29],[88.85,26.23],[88.8,26.31],[88.68,26.27],[88.75,26.35],[88.4,26.62],[88.34,26.47],[88.49,26.46],[88.53,26.36],[88.18,26.15],[88.11,25.8],[88.27,25.81],[88.54,25.51],[88.8,25.52],[88.85,25.36],[89.01,25.27],[88.92,25.17],[88.44,25.21],[88.4,24.94],[88.33,24.87],[88.23,24.96],[88.14,24.93],[88.18,24.86],[88.01,24.66],[88.34,24.38],[88.74,24.27],[88.7,24.11],[88.77,23.99],[88.58,23.86],[88.57,23.64],[88.8,23.5],[88.72,23.26],[89.0,23.21],[88.85,23.01],[88.97,22.85],[88.96,22.61],[88.85,22.43],[88.77,22.56],[88.67,22.55],[88.85,22.43],[88.88,22.36],[88.82,22.36],[88.95,22.23],[88.84,22.29],[88.92,22.17],[88.88,22.25],[88.81,22.21],[88.81,22.28],[88.84,22.17],[88.75,22.2],[88.79,22.26],[88.64,22.21],[88.67,22.34],[88.62,22.11],[88.57,22.19],[88.61,21.91],[88.55,21.97],[88.57,21.9],[88.49,21.88],[88.55,22.04],[88.47,21.9],[88.46,22.01],[88.41,21.89],[88.38,21.97],[88.39,21.8],[88.36,21.92],[88.35,21.86],[88.27,21.88],[88.27,21.73],[88.16,21.88],[88.2,22.17],[88.07,22.21],[88.11,22.3],[88.05,22.22],[87.98,22.25],[87.88,22.44],[87.94,22.26],[88.19,22.1],[88.06,22.01],[87.96,22.1],[88.05,22.01],[87.81,21.7],[87.2,21.53],[86.95,21.36],[86.84,21.16],[86.97,20.79],[86.79,20.75],[87.06,20.72],[86.73,20.48],[86.78,20.33],[86.54,20.18],[86.38,19.95],[85.34,19.58],[84.77,19.08]],[[93.85,7.24],[93.95,7.0],[93.83,6.76],[93.66,7.13],[93.85,7.24]],[[92.52,10.9],[92.59,10.79],[92.57,10.58],[92.39,10.53],[92.38,10.78],[92.52,10.9]],[[92.7,12.24],[92.78,12.05],[92.68,11.8],[92.79,11.92],[92.76,11.7],[92.67,11.65],[92.76,11.66],[92.71,11.48],[92.51,11.85],[92.56,11.95],[92.61,11.86],[92.7,12.24]],[[92.9,12.92],[92.97,12.5],[92.91,12.41],[92.81,12.44],[92.9,12.32],[92.72,12.3],[92.68,12.61],[92.79,12.68],[92.73,12.67],[92.72,12.83],[92.9,12.92]],[[93.03,13.57],[93.03,13.37],[93.09,13.34],[92.95,13.34],[93.07,13.27],[93.03,13.08],[92.97,13.01],[92.9,13.08],[92.94,12.97],[92.84,12.88],[92.79,13.02],[92.84,13.4],[92.91,13.53],[93.03,13.57]]],"states":[{"name":"Andaman & Nicobar Islands","name_hi":"अंडमान और निकोबार द्वीप समूह","cells":[[1,18,0.028],[1,19,0.021],[2,18,0.007],[3,18,0.028],[4,18,0.111],[5,18,0.062]],"area_cells":0.26,"centroid_cell":[4,18],"label":[92.68,11.86],"outline":[[[93.85,7.24],[93.95,7.0],[93.83,6.76],[93.66,7.13],[93.85,7.24]],[[92.52,10.9],[92.57,10.58],[92.39,10.53],[92.38,10.78],[92.52,10.9]],[[92.7,12.24],[92.78,12.05],[92.68,11.8],[92.79,11.92],[92.76,11.7],[92.67,11.65],[92.76,11.66],[92.71,11.48],[92.51,11.85],[92.56,11.95],[92.61,11.86],[92.7,12.24]],[[92.83,12.3],[92.88,12.2],[92.76,12.06],[92.74,12.25],[92.83,12.3]],[[92.9,12.92],[92.97,12.5],[92.91,12.41],[92.81,12.44],[92.9,12.32],[92.72,12.3],[92.68,12.61],[92.79,12.68],[92.72,12.83],[92.9,12.92]],[[93.03,13.57],[93.09,13.34],[92.95,13.34],[93.07,13.27],[93.03,13.08],[92.97,13.01],[92.9,13.08],[92.94,12.97],[92.84,12.88],[92.84,13.4],[93.03,13.57]]]},{"name":"Andhra Pradesh","name_hi":"आंध्र प्रदेश","cells":[[4,8,0.014],[5,7,0.021],[5,8,0.431],[5,9,0.646],[6,7,0.181],[6,8,0.993],[6,9,0.917],[7,7,0.014],[7,8,0.139],[7,9,0.535],[7,10,0.743],[7,11,0.208],[8,10,0.069],[8,11,0.625],[8,12,0.312],[9,12,0.097]],"area_cells":5.94,"centroid_cell":[7,10],"label":[80.82,16.16],"outline":[[[84.68,19.17],[84.77,19.08],[84.55,18.78],[84.14,18.35],[83.99,18.36],[84.12,18.3],[83.56,18.02],[83.22,17.59],[82.31,17.03],[82.25,16.89],[82.36,16.82],[82.34,16.98],[82.38,16.88],[82.31,16.55],[81.71,16.3],[81.55,16.39],[81.31,16.36],[81.01,15.76],[80.86,15.82],[80.92,15.73],[80.84,15.71],[80.76,15.88],[80.5,15.86],[80.22,15.55],[80.14,15.56],[80.21,15.5],[80.03,15.21],[80.18,14.59],[80.09,14.53],[80.19,14.56],[80.12,14.24],[80.24,13.47],[80.01,13.54],[79.94,13.35],[79.73,13.28],[79.76,13.21],[79.41,13.33],[79.44,13.2],[79.23,13.15],[79.16,13.02],[78.71,13.07],[78.56,12.7],[78.5,12.75],[78.47,12.62],[78.38,12.62],[78.2,12.69],[78.25,12.86],[78.36,12.94],[78.47,12.86],[78.41,12.94],[78.59,13.27],[78.38,13.33],[78.4,13.59],[78.09,13.64],[78.11,13.86],[77.95,13.83],[77.99,13.96],[77.83,13.94],[77.72,13.74],[77.46,13.68],[77.43,13.84],[77.18,13.92],[77.17,13.76],[77.0,13.75],[77.04,13.93],[76.9,14.17],[77.03,14.18],[77.03,14.06],[77.15,14.0],[77.32,14.03],[77.4,13.89],[77.35,14.13],[77.52,14.18],[77.4,14.34],[77.4,14.2],[77.29,14.34],[77.14,14.34],[77.1,14.22],[76.95,14.24],[76.89,14.4],[76.98,14.48],[76.77,14.6],[76.87,14.94],[76.77,14.97],[76.78,15.08],[77.08,15.01],[77.16,15.13],[77.17,15.26],[76.97,15.5],[77.03,15.64],[77.13,15.64],[77.03,15.84],[77.08,15.91],[78.03,15.91],[78.12,15.83],[78.41,16.09],[78.78,16.03],[78.93,16.21],[79.23,16.25],[79.27,16.57],[79.78,16.74],[79.97,16.65],[80.08,16.82],[80.02,16.91],[80.19,17.05],[80.38,16.82],[80.57,16.77],[80.59,16.93],[80.37,16.98],[80.38,17.06],[80.45,17.02],[80.57,17.15],[80.84,17.03],[80.91,17.21],[81.42,17.37],[81.59,17.73],[81.79,17.84],[81.81,17.94],[82.03,18.07],[82.25,17.99],[82.34,18.06],[82.34,18.33],[82.48,18.54],[82.64,18.24],[82.81,18.45],[83.06,18.39],[83.06,18.62],[83.42,18.86],[83.31,19.0],[83.46,18.95],[83.47,19.08],[83.54,19.01],[83.63,19.16],[83.75,18.93],[83.8,19.02],[83.88,18.83],[84.09,18.75],[84.34,18.8],[84.42,19.02],[84.6,19.02],[84.68,19.17]]]},{"name":"Arunachal Pradesh","name_hi":"अरुणाचल प्रदेश","cells":[[14,17,0.125],[14,18,0.521],[14,19,0.125],[14,20,0.292],[14,21,0.049],[15,17,0.014],[15,18,0.333],[15,19,0.854],[15,20,0.785],[15,21,0.139],[16,19,0.007],[16,20,0.035]],"area_cells":3.28,"centroid_cell":[15,19],"label":[95.0,27.85],"outline":[[[96.16,29.38],[96.25,29.23],[96.4,29.25],[96.12,29.07],[96.17,28.9],[96.53,29.08],[96.48,28.99],[96.62,28.77],[96.27,28.41],[96.4,28.34],[96.67,28.46],[97.4,28.19],[97.31,28.07],[97.42,28.01],[97.39,27.89],[97.26,27.9],[96.9,27.61],[97.14,27.09],[96.87,27.19],[96.8,27.35],[96.62,27.36],[96.1,27.22],[95.73,26.88],[95.42,26.69],[95.24,26.68],[95.2,27.04],[95.46,27.13],[95.52,27.26],[95.89,27.26],[96.02,27.36],[95.85,27.42],[95.88,27.55],[95.76,27.73],[95.98,27.96],[95.61,27.95],[94.46,27.55],[94.25,27.64],[94.26,27.52],[93.81,27.15],[93.83,27.07],[93.49,26.94],[93.02,26.91],[92.66,27.04],[92.11,26.89],[92.03,27.16],[92.12,27.29],[92.02,27.48],[91.66,27.48],[91.57,27.58],[91.65,27.76],[91.56,27.86],[91.92,27.71],[92.22,27.86],[92.32,27.78],[92.57,27.82],[92.74,27.99],[92.69,28.13],[93.22,28.33],[93.19,28.44],[93.34,28.64],[93.93,28.67],[94.22,29.08],[94.56,29.23],[94.63,29.35],[94.8,29.16],[95.41,29.03],[95.78,29.35],[96.09,29.46],[96.16,29.38]]]},{"name":"Assam","name_hi":"असम","cells":[[12,18,0.167],[13,16,0.146],[13,17,0.215],[13,18,0.694],[13,19,0.042],[14,16,0.215],[14,17,0.368],[14,18,0.479],[14,19,0.618],[14,20,0.16],[15,19,0.007],[15,20,0.056]],"area_cells":3.17,"centroid_cell":[13,18],"label":[92.63,25.92],"outline":[[[95.97,27.95],[95.76,27.73],[95.88,27.55],[95.85,27.42],[96.02,27.36],[95.89,27.26],[95.51,27.26],[95.46,27.13],[94.89,26.93],[94.76,26.77],[94.47,26.66],[94.32,26.46],[94.28,26.55],[94.0,26.17],[93.98,25.92],[93.8,25.81],[93.77,25.96],[93.33,25.54],[93.47,25.31],[93.2,24.81],[93.11,24.81],[93.04,24.41],[92.83,24.37],[92.76,24.52],[92.47,24.13],[92.42,24.25],[92.21,24.25],[92.24,24.9],[92.5,24.87],[92.42,24.98],[92.48,25.11],[92.8,25.22],[92.78,25.33],[92.57,25.47],[92.65,25.59],[92.57,25.56],[92.39,25.75],[92.16,25.67],[92.23,25.91],[92.16,25.94],[92.3,26.08],[91.92,26.0],[91.82,26.12],[91.67,25.9],[91.58,26.03],[91.53,25.87],[91.23,25.72],[91.2,25.86],[91.0,25.82],[90.95,25.95],[90.12,25.96],[89.9,25.74],[90.02,25.61],[89.86,25.48],[89.89,25.94],[89.7,26.19],[89.86,26.38],[89.87,26.74],[90.13,26.75],[90.41,26.9],[90.7,26.77],[91.69,26.8],[91.86,26.91],[92.06,26.85],[92.66,27.04],[93.02,26.91],[93.66,26.96],[94.26,27.52],[94.25,27.64],[94.46,27.55],[95.61,27.95],[95.97,27.95]]]},{"name":"Bihar","name_hi":"बिहार","cells":[[12,12,0.146],[12,13,0.118],[12,14,0.069],[13,12,0.583],[13,13,1.0],[13,14,0.868],[13,15,0.083],[14,12,0.333],[14,13,0.354],[14,14,0.153],[14,15,0.042]],"area_cells":3.75,"centroid_cell":[13,13],"label":[85.64,25.89],"outline":[[[84.12,27.51],[84.29,27.38],[84.63,27.34],[84.65,27.05],[84.96,26.96],[85.03,26.85],[85.2,26.87],[85.21,26.76],[85.64,26.87],[85.85,26.57],[86.03,26.67],[86.35,26.62],[86.74,26.42],[87.07,26.59],[87.09,26.45],[87.34,26.35],[87.89,26.49],[88.02,26.35],[88.11,26.53],[88.24,26.55],[88.19,26.49],[88.29,26.34],[87.97,26.15],[87.81,25.92],[88.05,25.69],[88.08,25.48],[87.93,25.54],[87.79,25.45],[87.84,25.2],[87.59,25.35],[87.48,25.2],[87.33,25.22],[87.3,25.09],[87.15,25.02],[87.06,24.61],[86.94,24.64],[86.92,24.54],[86.61,24.61],[86.46,24.37],[86.29,24.46],[86.33,24.58],[86.14,24.6],[86.06,24.78],[85.96,24.73],[85.74,24.82],[85.67,24.58],[85.29,24.53],[85.1,24.38],[85.08,24.44],[84.91,24.37],[84.8,24.53],[84.5,24.29],[84.3,24.45],[84.3,24.57],[84.12,24.48],[84.0,24.64],[83.88,24.53],[83.51,24.53],[83.55,24.62],[83.33,25.02],[83.36,25.2],[83.85,25.44],[84.1,25.72],[84.29,25.66],[84.34,25.74],[84.64,25.73],[84.54,25.88],[84.06,26.1],[84.01,26.23],[84.17,26.24],[84.18,26.37],[83.91,26.45],[84.09,26.64],[84.42,26.62],[84.24,26.74],[84.25,26.86],[84.06,26.89],[83.93,27.31],[83.84,27.32],[83.85,27.45],[84.12,27.51]]]},{"name":"Chandigarh","name_hi":"चंडीगढ़","cells":[[16,7,0.007]],"area_cells":0.01,"centroid_cell":[16,7],"label":[76.77,30.74],"outline":[]},{"name":"Chhattisgarh","name_hi":"छत्तीसगढ़","cells":[[8,10,0.354],[8,11,0.021],[9,10,0.84],[9,11,0.278],[10,10,0.764],[10,11,0.681],[10,12,0.021],[11,10,0.264],[11,11,0.965],[11,12,0.458],[12,10,0.021],[12,11,0.361],[12,12,0.208]],"area_cells":5.24,"centroid_cell":[10,11],"label":[81.96,21.34],"outline":[[[83.34,24.1],[83.7,23.82],[83.78,23.6],[84.01,23.63],[84.04,23.14],[84.16,22.97],[84.38,22.98],[84.38,22.88],[84.23,22.67],[84.01,22.57],[84.01,22.37],[83.63,22.2],[83.54,22.04],[83.59,21.85],[83.34,21.5],[83.41,21.35],[83.28,21.38],[83.2,21.14],[82.64,21.15],[82.47,20.83],[82.35,20.89],[82.4,20.06],[82.72,20.0],[82.72,19.85],[82.59,19.78],[82.6,19.87],[82.35,19.84],[82.24,20.0],[81.95,20.11],[81.88,20.05],[81.86,19.91],[82.07,19.79],[82.03,19.51],[82.19,19.42],[82.25,18.92],[82.09,18.72],[81.89,18.66],[81.96,18.57],[81.75,18.35],[81.54,18.27],[81.39,17.81],[81.17,17.86],[81.05,17.79],[80.98,18.17],[80.87,18.14],[80.84,18.24],[80.74,18.18],[80.73,18.41],[80.5,18.63],[80.35,18.59],[80.25,18.76],[80.36,18.82],[80.27,18.99],[80.39,19.24],[80.58,19.4],[80.76,19.29],[80.9,19.47],[80.66,19.62],[80.55,19.82],[80.4,19.8],[80.55,20.07],[80.39,20.24],[80.62,20.34],[80.63,20.61],[80.49,20.62],[80.59,20.69],[80.55,20.94],[80.43,21.01],[80.46,21.17],[80.68,21.3],[80.73,21.71],[80.82,21.75],[80.91,22.11],[81.01,22.07],[81.12,22.44],[81.62,22.54],[81.77,22.66],[81.78,22.87],[81.95,22.96],[81.95,23.08],[82.16,23.14],[82.19,23.32],[81.92,23.53],[81.61,23.51],[81.58,23.59],[81.69,23.72],[81.62,23.9],[81.79,23.81],[81.92,23.87],[82.52,23.78],[82.81,23.96],[83.14,23.89],[83.34,24.1]]]},{"name":"Dadra & Nagar Haveli","name_hi":"दादरा और नगर हवेली","cells":[[9,5,0.021],[10,5,0.007]],"area_cells":0.03,"centroid_cell":[9,5],"label":[73.08,20.22],"outline":[[[73.21,20.12],[73.04,20.07],[72.91,20.27],[73.1,20.36],[73.17,20.29],[73.06,20.16],[73.17,20.21],[73.21,20.12]]]},{"name":"Daman & Diu","name_hi":"दमन और दीव","cells":[],"area_cells":0.0,"centroid_cell":[10,3],"label":[70.94,20.72],"outline":[]},{"name":"Delhi","name_hi":"दिल्ली","cells":[[15,7,0.056],[15,8,0.007]],"area_cells":0.06,"centroid_cell":[15,7],"label":[77.15,28.64],"outline":[[[77.09,28.87],[77.33,28.71],[77.35,28.5],[77.22,28.41],[76.85,28.55],[76.95,28.82],[77.09,28.87]]]},{"name":"Goa","name_hi":"गोवा","cells":[[6,5,0.125],[6,6,0.014]],"area_cells":0.14,"centroid_cell":[6,5],"label":[73.97,15.36],"outline":[[[73.87,15.78],[73.99,15.61],[74.25,15.66],[74.34,15.3],[74.25,15.26],[74.3,15.04],[74.21,14.92],[74.04,14.92],[73.91,15.08],[73.88,15.35],[73.78,15.41],[73.94,15.43],[73.79,15.46],[73.83,15.51],[73.77,15.49],[73.68,15.73],[73.87,15.78]]]},{"name":"Gujarat","name_hi":"गुजरात","cells":[[9,5,0.007],[10,2,0.021],[10,3,0.556],[10,4,0.347],[10,5,0.646],[11,2,0.34],[11,3,0.896],[11,4,0.938],[11,5,0.938],[11,6,0.035],[12,2,0.549],[12,3,0.715],[12,4,0.896],[12,5,0.368]],"area_cells":7.25,"centroid_cell":[11,3],"label":[70.66,22.17],"outline":[[[68.36,23.81],[68.43,23.79],[68.39,23.65],[68.2,23.6],[68.36,23.81]],[[68.36,23.98],[68.43,23.96],[68.24,23.68],[68.21,23.83],[68.36,23.98]],[[72.66,21.47],[72.74,21.55],[72.64,21.53],[72.63,21.62],[72.84,21.67],[72.52,21.68],[72.64,21.95],[72.51,21.9],[72.55,22.15],[72.92,22.27],[72.54,22.28],[72.49,22.2],[72.38,22.39],[72.42,22.23],[72.36,22.27],[72.34,22.12],[72.29,22.2],[72.28,21.93],[72.3,22.11],[72.17,22.04],[72.22,21.96],[72.15,21.98],[72.25,21.9],[72.27,21.74],[72.18,21.82],[72.31,21.63],[72.11,21.2],[71.07,20.74],[70.82,20.69],[70.44,20.85],[68.94,22.31],[69.07,22.48],[69.07,22.4],[69.19,22.42],[69.16,22.31],[69.23,22.26],[69.49,22.34],[69.5,22.44],[69.58,22.32],[69.73,22.47],[69.8,22.4],[69.98,22.54],[70.16,22.55],[70.49,23.08],[70.35,22.93],[70.14,23.01],[70.13,22.92],[69.8,22.85],[69.71,22.73],[69.19,22.84],[68.59,23.22],[68.69,23.31],[68.5,23.47],[68.49,23.64],[68.76,23.88],[68.53,23.76],[68.66,23.92],[68.55,23.97],[68.75,23.97],[68.82,24.32],[68.87,24.21],[68.94,24.3],[69.01,24.22],[69.59,24.29],[69.73,24.17],[70.02,24.17],[70.11,24.29],[70.57,24.42],[70.58,24.25],[70.83,24.23],[71.12,24.41],[71.0,24.45],[70.99,24.55],[71.1,24.69],[71.85,24.61],[72.05,24.71],[72.35,24.62],[72.25,24.58],[72.44,24.51],[72.46,24.41],[72.54,24.51],[72.92,24.33],[73.09,24.49],[73.08,24.39],[73.23,24.36],[73.08,24.18],[73.24,24.01],[73.37,24.13],[73.36,23.79],[73.51,23.62],[73.66,23.62],[73.63,23.45],[74.1,23.29],[74.12,23.18],[74.24,23.19],[74.36,22.93],[74.46,22.91],[74.38,22.64],[74.04,22.54],[74.12,22.42],[74.19,22.48],[74.29,22.39],[74.07,22.36],[74.14,21.96],[73.8,21.82],[73.89,21.67],[73.78,21.62],[73.86,21.49],[74.33,21.52],[74.06,21.48],[73.82,21.17],[73.58,21.17],[73.9,20.98],[73.94,20.74],[73.66,20.56],[73.45,20.71],[73.42,20.21],[73.21,20.12],[73.17,20.21],[73.06,20.16],[73.17,20.29],[73.1,20.36],[72.73,20.14],[72.76,20.33],[72.9,20.41],[72.78,20.9],[72.85,20.95],[72.76,20.93],[72.72,21.14],[72.62,21.09],[72.66,21.47]]]},{"name":"Haryana","name_hi":"हरियाणा","cells":[[14,7,0.007],[15,6,0.09],[15,7,0.743],[15,8,0.069],[16,6,0.285],[16,7,0.597],[16,8,0.049],[17,7,0.007]],"area_cells":1.85,"centroid_cell":[15,7],"label":[76.45,29.18],"outline":[[[76.85,30.88],[77.17,30.68],[77.12,30.56],[77.22,30.48],[77.61,30.37],[77.13,29.77],[77.13,29.1],[77.23,28.9],[76.95,28.82],[76.94,28.63],[76.84,28.58],[77.18,28.4],[77.34,28.51],[77.48,28.41],[77.55,27.94],[77.24,27.78],[77.05,27.81],[77.09,27.73],[76.98,27.65],[76.89,27.69],[76.97,28.14],[76.87,28.22],[76.55,27.97],[76.48,28.15],[76.3,28.18],[76.35,28.02],[76.16,27.99],[76.23,27.84],[75.97,27.86],[76.04,28.07],[75.94,28.09],[76.1,28.15],[75.56,28.61],[75.52,29.01],[75.37,29.14],[75.41,29.26],[75.09,29.23],[74.85,29.4],[74.6,29.33],[74.54,29.45],[74.62,29.53],[74.61,29.75],[74.47,29.79],[74.53,29.95],[74.66,29.9],[74.81,29.99],[75.0,29.85],[75.1,29.91],[75.1,29.8],[75.19,29.84],[75.24,29.75],[75.17,29.66],[75.23,29.54],[75.45,29.81],[76.05,29.75],[76.25,29.87],[76.18,29.93],[76.22,30.16],[76.33,30.1],[76.42,30.2],[76.55,30.08],[76.65,30.19],[76.56,30.26],[76.74,30.42],[76.94,30.39],[76.78,30.89],[76.85,30.88]]]},{"name":"Himachal Pradesh","name_hi":"हिमाचल प्रदेश","cells":[[16,7,0.014],[16,8,0.069],[17,6,0.007],[17,7,0.667],[17,8,0.799],[17,9,0.014],[18,7,0.493],[18,8,0.285]],"area_cells":2.35,"centroid_cell":[17,8],"label":[77.58,31.81],"outline":[[[76.8,33.25],[76.94,33.03],[77.35,32.82],[77.73,32.97],[78.0,32.58],[78.39,32.76],[78.41,32.62],[78.3,32.5],[78.46,32.5],[78.54,32.41],[78.46,32.24],[78.61,32.21],[78.79,32.0],[78.71,31.79],[78.85,31.61],[78.72,31.51],[79.01,31.11],[78.37,31.29],[77.9,31.15],[77.7,30.76],[77.82,30.53],[77.58,30.38],[77.14,30.54],[77.17,30.68],[76.62,31.0],[76.65,31.21],[76.45,31.28],[76.38,31.44],[76.31,31.32],[76.19,31.3],[75.91,31.95],[75.59,32.08],[75.64,32.23],[75.95,32.42],[75.87,32.51],[75.93,32.76],[75.8,32.89],[76.0,32.9],[76.41,33.19],[76.75,33.18],[76.8,33.25]]]},{"name":"Jammu & Kashmir and Ladakh","name_hi":"जम्मू-कश्मीर और लद्दाख","cells":[[18,5,0.215],[18,6,0.819],[18,7,0.493],[18,8,0.667],[18,9,0.292],[19,5,0.375],[19,6,1.0],[19,7,1.0],[19,8,1.0],[19,9,0.625],[20,4,0.042],[20,5,0.75],[20,6,0.993],[20,7,0.604],[20,8,0.264],[20,9,0.396],[21,5,0.021],[21,6,0.125]],"area_cells":9.68,"centroid_cell":[19,7],"label":[76.17,34.78],"outline":[[[74.73,37.02],[74.92,36.91],[75.34,37.05],[75.47,36.81],[75.77,36.57],[76.64,36.18],[76.8,36.05],[76.72,35.95],[76.81,35.84],[77.36,35.72],[77.49,35.53],[77.32,35.53],[77.44,35.46],[77.73,35.52],[77.98,35.46],[77.95,35.61],[78.14,35.54],[78.42,35.79],[78.96,35.89],[79.13,35.84],[79.22,35.98],[79.38,36.0],[79.42,35.9],[79.74,35.8],[80.0,35.84],[80.29,35.61],[80.33,35.47],[80.07,34.71],[79.78,34.63],[79.79,34.49],[79.51,34.47],[79.59,34.24],[79.43,34.02],[79.17,34.07],[78.91,33.98],[79.11,33.62],[78.91,33.63],[78.99,33.33],[79.45,33.26],[79.33,33.01],[79.63,32.74],[79.45,32.53],[79.32,32.59],[78.98,32.34],[78.83,32.44],[78.76,32.7],[78.33,32.47],[78.39,32.76],[78.0,32.58],[77.73,32.97],[77.35,32.82],[76.94,33.03],[76.8,33.25],[76.75,33.18],[76.41,33.19],[75.96,32.89],[75.82,32.93],[75.94,32.64],[75.51,32.28],[75.03,32.49],[74.69,32.48],[74.7,32.84],[74.63,32.75],[74.37,32.76],[73.63,33.09],[73.59,33.88],[73.39,34.38],[73.45,34.57],[73.65,34.57],[73.75,34.79],[74.03,34.88],[74.13,35.11],[73.72,35.23],[73.78,35.53],[73.27,35.63],[73.14,35.72],[73.1,35.88],[72.6,35.87],[72.55,36.18],[72.99,36.46],[73.09,36.7],[73.88,36.7],[73.69,36.91],[74.06,36.81],[74.43,36.99],[74.58,36.95],[74.59,37.05],[74.73,37.02]]]},{"name":"Jharkhand","name_hi":"झारखंड","cells":[[11,12,0.222],[11,13,0.646],[11,14,0.125],[12,12,0.597],[12,13,0.833],[12,14,0.535],[12,15,0.007],[13,14,0.132],[13,15,0.028]],"area_cells":3.13,"centroid_cell":[12,13],"label":[86.07,23.72],"outline":[[[87.61,25.32],[87.79,25.25],[87.78,25.09],[87.98,24.9],[87.82,24.77],[87.92,24.6],[87.77,24.58],[87.82,24.41],[87.64,24.24],[87.69,24.15],[87.5,24.12],[87.46,23.98],[87.24,24.04],[87.25,23.83],[86.8,23.83],[86.8,23.69],[86.45,23.63],[86.31,23.42],[86.05,23.59],[86.05,23.5],[85.87,23.45],[85.84,23.2],[85.92,23.13],[86.04,23.15],[86.22,22.99],[86.55,22.99],[86.44,22.93],[86.42,22.78],[86.77,22.58],[86.89,22.26],[86.44,22.31],[86.04,22.57],[85.96,22.46],[86.03,22.19],[85.91,21.97],[85.77,21.99],[85.81,22.11],[85.69,22.05],[85.4,22.16],[85.24,22.0],[84.99,22.09],[85.12,22.29],[85.07,22.48],[84.3,22.34],[84.01,22.52],[84.4,22.94],[84.2,23.03],[84.16,22.97],[84.04,23.14],[84.01,23.63],[83.78,23.6],[83.7,23.82],[83.33,24.1],[83.46,24.36],[83.4,24.5],[83.88,24.53],[84.0,24.64],[84.12,24.48],[84.31,24.56],[84.3,24.45],[84.5,24.29],[84.8,24.53],[84.91,24.37],[85.08,24.44],[85.1,24.38],[85.29,24.53],[85.67,24.58],[85.74,24.82],[85.96,24.73],[86.06,24.78],[86.14,24.6],[86.33,24.58],[86.29,24.46],[86.46,24.37],[86.61,24.61],[86.92,24.54],[86.94,24.64],[87.06,24.61],[87.18,25.06],[87.3,25.09],[87.33,25.22],[87.47,25.19],[87.5,25.31],[87.61,25.32]]]},{"name":"Karnataka","name_hi":"कर्नाटक","cells":[[4,6,0.125],[4,7,0.653],[4,8,0.174],[5,6,0.715],[5,7,0.979],[5,8,0.535],[6,5,0.021],[6,6,0.972],[6,7,0.819],[6,8,0.007],[7,6,0.681],[7,7,0.986],[7,8,0.118],[8,6,0.007],[8,7,0.285],[8,8,0.139]],"area_cells":7.22,"centroid_cell":[6,7],"label":[76.08,14.72],"outline":[[[77.34,18.44],[77.41,18.39],[77.37,18.31],[77.61,18.28],[77.55,18.06],[77.66,17.97],[77.44,17.58],[77.69,17.5],[77.51,17.43],[77.38,17.22],[77.5,17.01],[77.47,16.59],[77.24,16.47],[77.6,16.29],[77.49,16.25],[77.51,15.93],[77.18,15.95],[77.03,15.84],[77.13,15.66],[76.97,15.5],[77.17,15.17],[77.08,15.01],[76.78,15.08],[76.77,14.97],[76.87,14.94],[76.77,14.6],[76.98,14.48],[76.89,14.4],[76.95,14.24],[77.11,14.22],[77.16,14.34],[77.29,14.34],[77.39,14.2],[77.39,14.33],[77.51,14.27],[77.51,14.16],[77.35,14.13],[77.4,13.89],[77.32,14.03],[77.15,14.0],[77.03,14.06],[77.03,14.18],[76.9,14.17],[77.04,13.93],[77.0,13.75],[77.17,13.76],[77.18,13.92],[77.43,13.84],[77.48,13.69],[77.72,13.74],[77.83,13.94],[77.99,13.96],[77.95,13.83],[78.12,13.85],[78.09,13.64],[78.4,13.59],[78.38,13.33],[78.59,13.27],[78.41,12.94],[78.47,12.86],[78.36,12.94],[78.23,12.76],[77.84,12.87],[77.74,12.67],[77.6,12.67],[77.63,12.42],[77.48,12.21],[77.74,12.18],[77.68,11.95],[77.5,11.94],[77.43,11.76],[76.91,11.79],[76.85,11.58],[76.42,11.67],[76.42,11.76],[76.11,11.86],[76.11,11.98],[75.87,11.95],[75.42,12.29],[75.42,12.5],[75.34,12.46],[75.27,12.54],[75.33,12.59],[75.05,12.66],[74.99,12.79],[74.86,12.76],[74.69,13.36],[74.75,13.46],[74.66,13.63],[74.76,13.64],[74.67,13.71],[74.67,13.64],[74.52,13.99],[74.43,14.26],[74.53,14.24],[74.43,14.28],[74.36,14.5],[74.44,14.47],[74.31,14.52],[74.29,14.59],[74.43,14.62],[74.28,14.61],[74.25,14.74],[74.09,14.8],[74.25,14.87],[74.09,14.9],[74.26,14.97],[74.32,15.19],[74.25,15.26],[74.34,15.3],[74.25,15.66],[74.09,15.67],[74.22,15.79],[74.36,15.78],[74.46,16.04],[74.36,16.05],[74.49,16.1],[74.5,16.23],[74.32,16.27],[74.36,16.4],[74.27,16.55],[74.38,16.53],[74.47,16.66],[74.57,16.55],[74.69,16.61],[74.69,16.72],[74.92,16.77],[74.93,16.94],[75.21,16.84],[75.29,16.96],[75.67,16.96],[75.58,17.38],[75.63,17.48],[75.8,17.37],[75.89,17.42],[75.93,17.33],[76.38,17.31],[76.33,17.6],[76.52,17.76],[76.69,17.68],[76.79,17.83],[76.74,17.9],[76.92,17.92],[76.96,18.19],[77.11,18.15],[77.34,18.44]]]},{"name":"Kerala","name_hi":"केरल","cells":[[2,7,0.438],[2,8,0.014],[3,7,0.618],[4,6,0.181],[4,7,0.181]],"area_cells":1.43,"centroid_cell":[3,7],"label":[76.2,10.71],"outline":[[[75.0,12.79],[75.05,12.66],[75.33,12.59],[75.34,12.46],[75.42,12.5],[75.42,12.29],[75.58,12.16],[75.8,12.08],[75.88,11.95],[76.11,11.98],[76.12,11.85],[76.42,11.76],[76.44,11.64],[76.23,11.57],[76.25,11.47],[76.55,11.36],[76.46,11.19],[76.74,11.22],[76.8,11.05],[76.66,10.93],[76.91,10.78],[76.82,10.63],[76.83,10.3],[76.98,10.22],[77.24,10.35],[77.29,10.22],[77.2,10.1],[77.28,9.97],[77.17,9.61],[77.36,9.6],[77.41,9.51],[77.15,9.02],[77.26,8.87],[77.17,8.75],[77.28,8.55],[77.18,8.32],[76.98,8.38],[76.55,8.9],[75.82,11.17],[75.54,11.71],[75.2,12.0],[74.86,12.76],[75.0,12.79]]]},{"name":"Lakshadweep","name_hi":"लक्षद्वीप","cells":[[2,5,0.007],[3,4,0.014],[3,5,0.007],[4,4,0.007],[4,5,0.007]],"area_cells":0.04,"centroid_cell":[3,5],"label":[72.78,11.22],"outline":[]},{"name":"Madhya Pradesh","name_hi":"मध्य प्रदेश","cells":[[10,6,0.146],[10,7,0.229],[10,8,0.16],[10,9,0.111],[10,10,0.069],[11,5,0.028],[11,6,0.917],[11,7,1.0],[11,8,1.0],[11,9,1.0],[11,10,0.736],[11,11,0.035],[12,6,0.604],[12,7,0.681],[12,8,0.903],[12,9,0.965],[12,10,0.979],[12,11,0.438],[13,6,0.042],[13,7,0.285],[13,8,0.882],[13,9,0.368],[13,10,0.229],[13,11,0.035],[14,8,0.243],[14,9,0.069]],"area_cells":12.15,"centroid_cell":[12,8],"label":[78.09,23.82],"outline":[[[78.37,26.86],[79.0,26.68],[79.14,26.34],[78.99,26.24],[79.01,26.08],[78.87,25.79],[78.75,25.74],[78.81,25.62],[78.44,25.56],[78.3,25.37],[78.45,25.12],[78.17,24.85],[78.27,24.66],[78.23,24.52],[78.39,24.27],[78.51,24.39],[78.8,24.18],[78.97,24.35],[78.89,24.64],[78.76,24.6],[78.79,24.81],[78.63,24.96],[78.58,25.25],[78.43,25.28],[78.66,25.44],[78.77,25.35],[78.82,25.43],[78.74,25.5],[78.84,25.43],[78.89,25.56],[78.99,25.37],[78.79,25.3],[78.85,25.22],[78.96,25.34],[78.88,25.16],[79.01,25.27],[79.03,25.14],[79.28,25.12],[79.31,25.33],[79.5,25.27],[79.41,25.11],[79.5,25.08],[79.57,25.17],[79.86,25.09],[79.86,25.24],[80.26,25.42],[80.43,25.17],[80.32,25.0],[80.45,25.08],[80.46,24.98],[80.55,25.0],[80.48,25.1],[80.61,25.07],[80.6,25.15],[80.78,25.06],[80.71,25.13],[80.84,25.11],[80.89,25.19],[80.81,24.94],[81.14,24.89],[81.28,25.16],[81.49,25.07],[81.57,25.19],[81.61,25.06],[81.91,25.01],[81.97,24.83],[82.2,24.82],[82.3,24.61],[82.67,24.7],[82.8,24.6],[82.72,24.55],[82.77,24.29],[82.67,24.13],[82.82,23.96],[82.64,23.84],[81.82,23.81],[81.6,23.89],[81.69,23.72],[81.58,23.59],[81.61,23.51],[81.92,23.53],[82.19,23.32],[82.16,23.14],[81.95,23.08],[81.95,22.96],[81.78,22.87],[81.77,22.66],[81.62,22.54],[81.12,22.44],[81.01,22.07],[80.91,22.11],[80.82,21.75],[80.73,21.71],[80.67,21.34],[80.41,21.38],[80.27,21.62],[79.54,21.54],[79.49,21.67],[79.23,21.72],[79.23,21.65],[78.92,21.59],[78.94,21.49],[78.43,21.5],[78.38,21.62],[77.94,21.39],[77.59,21.36],[77.42,21.53],[77.61,21.54],[77.55,21.7],[77.29,21.76],[76.8,21.6],[76.62,21.19],[76.17,21.08],[76.1,21.37],[75.22,21.41],[74.9,21.63],[74.56,21.68],[74.44,22.02],[74.14,21.95],[74.07,22.36],[74.29,22.39],[74.19,22.48],[74.12,22.42],[74.04,22.54],[74.38,22.64],[74.48,22.86],[74.32,23.06],[74.74,23.21],[74.52,23.33],[74.94,23.63],[74.91,23.87],[74.99,24.03],[74.89,24.26],[74.75,24.28],[74.86,24.46],[74.71,24.51],[74.8,24.79],[74.89,24.65],[75.02,24.77],[74.85,24.79],[74.83,24.96],[75.05,24.86],[75.16,25.04],[75.35,25.04],[75.26,24.89],[75.42,24.86],[75.31,24.81],[75.21,24.91],[75.22,24.72],[75.84,24.73],[75.91,24.45],[75.73,24.4],[75.83,24.24],[75.75,24.14],[75.84,24.07],[75.7,23.97],[75.52,24.05],[75.46,23.92],[75.58,23.8],[75.69,23.76],[75.7,23.9],[75.98,23.93],[75.96,24.02],[76.14,24.09],[76.19,24.33],[76.22,24.21],[76.53,24.16],[76.7,24.28],[76.7,24.17],[76.9,24.13],[76.82,24.53],[76.97,24.46],[77.07,24.57],[77.03,24.71],[76.81,24.82],[76.95,24.87],[76.86,25.01],[77.4,25.11],[77.37,25.41],[77.21,25.31],[76.78,25.31],[76.57,25.44],[76.49,25.71],[77.13,26.23],[78.37,26.86]]]},{"name":"Maharashtra","name_hi":"महाराष्ट्र","cells":[[6,5,0.007],[7,5,0.576],[7,6,0.319],[8,5,0.806],[8,6,0.993],[8,7,0.715],[8,8,0.083],[8,9,0.007],[9,4,0.014],[9,5,0.951],[9,6,1.0],[9,7,1.0],[9,8,0.667],[9,9,0.556],[9,10,0.16],[10,5,0.319],[10,6,0.854],[10,7,0.771],[10,8,0.84],[10,9,0.889],[10,10,0.167],[11,5,0.028],[11,6,0.028]],"area_cells":11.75,"centroid_cell":[9,7],"label":[75.83,19.75],"outline":[[[74.45,22.01],[74.59,21.66],[74.9,21.63],[75.3,21.39],[76.1,21.37],[76.14,21.12],[76.28,21.07],[76.62,21.19],[76.8,21.6],[77.29,21.76],[77.55,21.7],[77.61,21.54],[77.42,21.53],[77.59,21.36],[77.94,21.39],[78.38,21.62],[78.43,21.5],[78.94,21.49],[78.92,21.59],[79.23,21.65],[79.23,21.72],[79.49,21.67],[79.54,21.54],[80.27,21.62],[80.41,21.38],[80.68,21.31],[80.44,21.1],[80.59,20.69],[80.49,20.62],[80.63,20.61],[80.62,20.34],[80.39,20.24],[80.55,20.07],[80.4,19.8],[80.55,19.82],[80.66,19.62],[80.9,19.47],[80.76,19.29],[80.58,19.4],[80.48,19.34],[80.27,18.99],[80.35,18.82],[80.12,18.68],[79.9,18.83],[79.94,19.03],[79.86,19.11],[79.98,19.4],[79.79,19.6],[79.48,19.5],[79.25,19.61],[79.18,19.46],[78.96,19.55],[78.85,19.76],[78.5,19.79],[78.31,19.91],[78.31,19.46],[78.19,19.41],[78.17,19.24],[77.86,19.3],[77.85,19.09],[77.76,19.03],[77.95,18.82],[77.74,18.68],[77.74,18.56],[77.6,18.55],[77.57,18.31],[77.37,18.31],[77.41,18.39],[77.32,18.46],[77.11,18.15],[76.96,18.19],[76.92,17.92],[76.74,17.9],[76.79,17.83],[76.69,17.68],[76.52,17.76],[76.33,17.6],[76.38,17.31],[75.93,17.33],[75.89,17.42],[75.8,17.37],[75.63,17.48],[75.58,17.38],[75.67,16.96],[75.29,16.96],[75.21,16.84],[74.93,16.94],[74.92,16.77],[74.69,16.72],[74.69,16.61],[74.57,16.55],[74.47,16.66],[74.38,16.53],[74.26,16.54],[74.36,16.4],[74.33,16.27],[74.51,16.2],[74.48,16.09],[74.36,16.05],[74.46,16.04],[74.36,15.78],[74.22,15.79],[74.02,15.61],[73.86,15.8],[73.68,15.73],[73.46,16.06],[73.37,16.38],[73.47,16.42],[73.37,16.39],[73.31,16.53],[73.4,16.59],[73.3,16.74],[73.33,16.97],[73.19,17.3],[73.13,17.83],[72.93,18.21],[72.65,19.94],[72.77,19.9],[72.7,20.08],[72.86,20.23],[73.17,20.05],[73.3,20.21],[73.42,20.2],[73.45,20.71],[73.66,20.56],[73.94,20.74],[73.9,20.98],[73.58,21.17],[73.82,21.17],[73.95,21.4],[74.33,21.54],[73.86,21.49],[73.78,21.62],[73.89,21.7],[73.8,21.82],[74.45,22.01]]]},{"name":"Manipur","name_hi":"मणिपुर","cells":[[12,18,0.229],[12,19,0.229],[13,18,0.111],[13,19,0.319]],"area_cells":0.89,"centroid_cell":[13,18],"label":[93.75,24.79],"outline":[[[94.58,25.64],[94.56,25.51],[94.68,25.45],[94.58,25.21],[94.74,25.13],[94.74,25.02],[94.32,24.33],[94.16,23.85],[93.75,24.0],[93.51,23.94],[93.35,24.11],[93.25,24.02],[92.98,24.11],[93.11,24.81],[93.2,24.81],[93.4,25.26],[93.47,25.31],[93.61,25.2],[93.84,25.56],[94.31,25.49],[94.58,25.64]]]},{"name":"Meghalaya","name_hi":"मेघालय","cells":[[13,16,0.285],[13,17,0.521],[13,18,0.111]],"area_cells":0.92,"centroid_cell":[13,17],"label":[91.46,25.59],"outline":[[[91.86,26.1],[91.92,26.0],[92.3,26.07],[92.16,25.94],[92.23,25.91],[92.16,25.67],[92.39,25.75],[92.57,25.56],[92.66,25.58],[92.57,25.47],[92.78,25.33],[92.8,25.22],[92.53,25.14],[92.46,25.03],[92.07,25.19],[90.45,25.14],[89.84,25.3],[89.87,25.54],[90.02,25.61],[89.9,25.74],[90.12,25.96],[90.95,25.95],[91.0,25.82],[91.2,25.86],[91.23,25.72],[91.53,25.87],[91.58,26.03],[91.67,25.9],[91.86,26.1]]]},{"name":"Mizoram","name_hi":"मिज़ोरम","cells":[[11,18,0.354],[12,18,0.444]],"area_cells":0.8,"centroid_cell":[12,18],"label":[92.76,23.47],"outline":[[[92.8,24.42],[93.02,24.39],[92.98,24.11],[93.34,24.05],[93.44,23.68],[93.39,23.13],[93.3,23.0],[93.13,23.04],[93.11,22.53],[93.21,22.26],[93.04,22.2],[93.01,21.98],[92.95,22.03],[92.91,21.94],[92.72,22.15],[92.61,21.98],[92.26,23.81],[92.33,23.91],[92.3,24.25],[92.42,24.25],[92.47,24.13],[92.76,24.52],[92.8,24.42]]]},{"name":"Nagaland","name_hi":"नागालैंड","cells":[[13,18,0.062],[13,19,0.368],[14,19,0.236]],"area_cells":0.67,"centroid_cell":[13,19],"label":[94.35,26.04],"outline":[[[95.21,26.93],[95.24,26.68],[95.07,26.45],[95.18,26.07],[95.02,25.9],[95.05,25.76],[94.9,25.56],[94.63,25.46],[94.56,25.51],[94.57,25.69],[94.31,25.49],[93.84,25.56],[93.61,25.2],[93.5,25.24],[93.33,25.54],[93.77,25.96],[93.8,25.81],[93.98,25.92],[94.0,26.17],[94.28,26.55],[94.32,26.46],[94.47,26.66],[94.76,26.77],[94.93,26.95],[95.2,27.04],[95.21,26.93]]]},{"name":"Odisha","name_hi":"ओडिशा","cells":[[8,10,0.049],[8,11,0.292],[9,11,0.722],[9,12,0.882],[9,13,0.438],[9,14,0.028],[10,11,0.319],[10,12,0.979],[10,13,1.0],[10,14,0.486],[11,12,0.319],[11,13,0.326],[11,14,0.181]],"area_cells":6.02,"centroid_cell":[10,12],"label":[84.44,20.28],"outline":[[[86.08,22.53],[86.97,22.08],[87.03,21.87],[87.24,21.96],[87.28,21.81],[87.47,21.73],[87.49,21.6],[87.07,21.46],[86.87,21.22],[86.98,20.82],[86.79,20.75],[87.06,20.72],[86.73,20.48],[86.78,20.33],[86.38,19.95],[85.44,19.63],[84.77,19.08],[84.67,19.17],[84.6,19.02],[84.42,19.02],[84.32,18.79],[83.89,18.81],[83.63,19.16],[83.54,19.01],[83.47,19.08],[83.46,18.95],[83.31,19.0],[83.42,18.86],[83.06,18.62],[83.06,18.38],[82.81,18.45],[82.64,18.24],[82.48,18.54],[82.37,18.42],[82.37,18.14],[82.28,17.99],[82.03,18.07],[81.62,17.82],[81.39,17.81],[81.54,18.27],[81.75,18.35],[81.96,18.57],[81.89,18.66],[82.09,18.72],[82.25,18.92],[82.19,19.42],[82.03,19.51],[82.07,19.79],[81.86,19.91],[81.87,20.04],[81.95,20.11],[82.24,20.0],[82.35,19.84],[82.45,19.91],[82.6,19.87],[82.59,19.78],[82.71,19.84],[82.72,20.0],[82.4,20.06],[82.35,20.89],[82.47,20.83],[82.64,21.15],[83.13,21.1],[83.28,21.38],[83.41,21.35],[83.34,21.5],[83.59,21.85],[83.54,22.04],[83.63,22.21],[84.01,22.37],[84.0,22.53],[84.3,22.34],[85.07,22.48],[85.12,22.29],[84.99,22.08],[85.24,22.0],[85.37,22.16],[85.69,22.05],[85.81,22.11],[85.77,21.99],[85.91,21.97],[86.05,22.31],[85.96,22.48],[86.08,22.53]]]},{"name":"Puducherry","name_hi":"पुडुचेरी","cells":[[3,9,0.007],[4,9,0.007]],"area_cells":0.01,"centroid_cell":[4,9],"label":[79.74,11.94],"outline":[]},{"name":"Punjab","name_hi":"पंजाब","cells":[[16,5,0.076],[16,6,0.59],[16,7,0.347],[17,6,0.729],[17,7,0.326],[18,6,0.021],[18,7,0.014]],"area_cells":2.1,"centroid_cell":[17,6],"label":[75.27,30.98],"outline":[[[75.88,32.49],[75.95,32.42],[75.64,32.23],[75.59,32.08],[75.91,31.95],[76.19,31.3],[76.31,31.32],[76.38,31.44],[76.45,31.28],[76.64,31.22],[76.62,31.0],[76.86,30.79],[76.7,30.74],[76.88,30.68],[76.94,30.38],[76.74,30.42],[76.56,30.26],[76.65,30.19],[76.55,30.08],[76.42,30.2],[76.33,30.1],[76.22,30.16],[76.18,29.93],[76.25,29.87],[76.05,29.75],[75.45,29.81],[75.23,29.54],[75.17,29.66],[75.24,29.75],[75.19,29.84],[75.1,29.8],[75.1,29.91],[75.0,29.85],[74.81,29.99],[74.65,29.9],[73.9,29.97],[73.98,30.12],[73.89,30.36],[73.94,30.49],[74.71,31.1],[74.52,31.14],[74.65,31.46],[74.49,31.72],[74.61,31.89],[74.93,32.07],[75.27,32.1],[75.38,32.24],[75.34,32.34],[75.51,32.28],[75.89,32.58],[75.88,32.49]]]},{"name":"Rajasthan","name_hi":"राजस्थान","cells":[[11,5,0.007],[11,6,0.021],[12,3,0.007],[12,4,0.104],[12,5,0.632],[12,6,0.396],[12,7,0.319],[13,3,0.451],[13,4,1.0],[13,5,1.0],[13,6,0.958],[13,7,0.715],[13,8,0.014],[14,2,0.056],[14,3,0.896],[14,4,1.0],[14,5,1.0],[14,6,1.0],[14,7,0.993],[14,8,0.271],[15,3,0.062],[15,4,0.347],[15,5,0.972],[15,6,0.91],[15,7,0.188],[16,5,0.326],[16,6,0.125]],"area_cells":13.77,"centroid_cell":[13,6],"label":[75.16,25.96],"outline":[[[73.9,29.98],[74.53,29.94],[74.47,29.79],[74.61,29.75],[74.62,29.53],[74.54,29.45],[74.6,29.33],[74.85,29.4],[75.09,29.23],[75.41,29.26],[75.37,29.14],[75.52,29.01],[75.56,28.61],[76.1,28.15],[75.94,28.09],[76.04,28.07],[75.97,27.86],[76.23,27.84],[76.16,27.99],[76.35,28.02],[76.3,28.18],[76.48,28.15],[76.55,27.97],[76.81,28.21],[76.91,28.2],[76.97,28.14],[76.91,27.65],[77.09,27.73],[77.05,27.81],[77.3,27.79],[77.34,27.52],[77.62,27.34],[77.68,27.19],[77.51,27.09],[77.76,27.02],[77.43,26.86],[77.46,26.74],[77.76,26.93],[78.03,26.86],[78.12,26.95],[78.27,26.92],[78.09,26.68],[77.9,26.66],[77.13,26.23],[76.49,25.71],[76.57,25.44],[76.78,25.31],[77.21,25.31],[77.37,25.41],[77.4,25.11],[76.86,25.01],[76.95,24.87],[76.81,24.82],[77.03,24.71],[77.07,24.57],[76.97,24.46],[76.82,24.53],[76.9,24.13],[76.7,24.17],[76.7,24.28],[76.53,24.16],[76.22,24.21],[76.19,24.33],[76.14,24.09],[75.96,24.02],[75.98,23.93],[75.7,23.9],[75.69,23.76],[75.58,23.8],[75.46,23.92],[75.52,24.05],[75.7,23.97],[75.84,24.07],[75.75,24.14],[75.83,24.24],[75.73,24.4],[75.91,24.45],[75.84,24.73],[75.22,24.72],[75.21,24.91],[75.31,24.81],[75.42,24.86],[75.26,24.89],[75.35,25.04],[75.16,25.04],[75.05,24.86],[74.85,24.97],[74.85,24.79],[75.02,24.75],[74.89,24.65],[74.8,24.79],[74.71,24.51],[74.86,24.46],[74.75,24.28],[74.89,24.26],[74.99,24.03],[74.91,23.87],[74.94,23.63],[74.52,23.33],[74.74,23.21],[74.32,23.06],[73.97,23.38],[73.63,23.45],[73.66,23.62],[73.51,23.62],[73.36,23.79],[73.37,24.13],[73.24,24.01],[73.08,24.18],[73.23,24.36],[73.08,24.39],[73.09,24.49],[72.92,24.33],[72.54,24.51],[72.46,24.41],[72.44,24.51],[72.25,24.58],[72.35,24.62],[72.05,24.71],[71.85,24.61],[71.79,24.67],[71.29,24.61],[71.11,24.67],[70.67,25.4],[70.66,25.71],[70.28,25.71],[70.1,25.94],[70.17,26.55],[69.8,26.6],[69.48,26.81],[69.59,27.18],[70.37,28.01],[70.59,28.01],[70.74,27.74],[70.88,27.71],[71.9,27.96],[72.39,28.77],[72.95,29.03],[73.28,29.56],[73.4,29.94],[73.98,30.2],[73.9,29.98]]]},{"name":"Sikkim","name_hi":"सिक्किम","cells":[[14,15,0.194],[15,15,0.097]],"area_cells":0.29,"centroid_cell":[14,15],"label":[88.52,27.62],"outline":[[[88.65,28.1],[88.89,27.89],[88.77,27.56],[88.91,27.28],[88.74,27.14],[88.57,27.19],[88.44,27.08],[88.1,27.14],[88.02,27.22],[88.2,27.79],[88.13,27.95],[88.65,28.1]]]},{"name":"Tamil Nadu","name_hi":"तमिलनाडु","cells":[[1,8,0.028],[2,7,0.007],[2,8,0.75],[2,9,0.056],[3,7,0.188],[3,8,1.0],[3,9,0.576],[4,7,0.167],[4,8,0.812],[4,9,0.778],[5,8,0.035],[5,9,0.34],[5,10,0.021]],"area_cells":4.76,"centroid_cell":[3,8],"label":[78.66,10.99],"outline":[[[79.7,11.88],[79.81,11.84],[79.71,11.79],[79.8,11.78],[79.86,11.01],[79.72,10.96],[79.85,10.83],[79.88,10.29],[79.53,10.36],[79.3,10.26],[79.26,10.04],[78.89,9.48],[79.05,9.3],[79.19,9.28],[78.21,9.05],[78.27,9.0],[78.07,8.37],[77.55,8.08],[77.32,8.12],[77.1,8.29],[77.28,8.55],[77.17,8.75],[77.26,8.87],[77.15,9.02],[77.41,9.51],[77.36,9.6],[77.17,9.61],[77.28,9.97],[77.2,10.1],[77.29,10.22],[77.24,10.35],[76.98,10.22],[76.83,10.3],[76.82,10.63],[76.91,10.78],[76.66,10.93],[76.8,11.05],[76.74,11.22],[76.46,11.19],[76.55,11.36],[76.25,11.47],[76.23,11.57],[76.51,11.71],[76.57,11.62],[76.85,11.58],[76.91,11.79],[77.43,11.76],[77.5,11.94],[77.68,11.95],[77.78,12.12],[77.47,12.25],[77.62,12.37],[77.6,12.67],[77.74,12.67],[77.84,12.87],[78.06,12.85],[78.23,12.76],[78.2,12.69],[78.47,12.62],[78.71,13.07],[79.16,13.02],[79.23,13.15],[79.44,13.2],[79.44,13.34],[79.76,13.21],[79.73,13.28],[79.94,13.35],[80.02,13.55],[80.24,13.47],[80.27,13.56],[80.33,13.44],[80.25,12.77],[79.84,11.95],[79.66,12.01],[79.7,11.88]]]},{"name":"Telangana","name_hi":"तेलंगाना","cells":[[7,8,0.743],[7,9,0.465],[7,10,0.076],[8,8,0.778],[8,9,0.993],[8,10,0.528],[9,8,0.333],[9,9,0.444]],"area_cells":4.36,"centroid_cell":[8,9],"label":[79.04,17.82],"outline":[[[78.34,19.88],[78.84,19.76],[78.96,19.55],[79.18,19.46],[79.25,19.61],[79.48,19.5],[79.79,19.6],[79.98,19.4],[79.86,19.11],[79.94,19.03],[79.92,18.81],[80.64,18.52],[80.8,18.26],[80.74,18.18],[80.84,18.24],[80.87,18.14],[80.98,18.17],[81.04,17.8],[81.8,17.85],[81.59,17.73],[81.44,17.38],[80.91,17.21],[80.84,17.03],[80.57,17.15],[80.45,17.02],[80.38,17.07],[80.37,16.98],[80.59,16.93],[80.57,16.77],[80.38,16.82],[80.19,17.05],[80.02,16.91],[80.08,16.82],[79.97,16.65],[79.78,16.74],[79.27,16.57],[79.23,16.25],[78.93,16.21],[78.78,16.03],[78.41,16.09],[78.12,15.83],[78.04,15.91],[77.66,15.88],[77.51,15.93],[77.5,16.04],[77.49,16.25],[77.6,16.34],[77.24,16.47],[77.47,16.59],[77.5,17.01],[77.38,17.22],[77.51,17.43],[77.69,17.49],[77.44,17.58],[77.66,17.97],[77.55,18.06],[77.61,18.28],[77.53,18.43],[77.6,18.55],[77.74,18.56],[77.84,18.81],[77.95,18.82],[77.76,19.03],[77.85,19.09],[77.86,19.3],[78.17,19.24],[78.19,19.41],[78.31,19.46],[78.34,19.88]]]},{"name":"Tripura","name_hi":"त्रिपुरा","cells":[[11,17,0.028],[12,17,0.368],[12,18,0.014]],"area_cells":0.41,"centroid_cell":[12,17],"label":[91.8,23.75],"outline":[[[92.22,24.5],[92.21,24.25],[92.34,24.14],[92.27,23.72],[92.08,23.65],[91.96,23.73],[91.98,23.48],[91.78,23.28],[91.84,23.1],[91.62,22.94],[91.45,23.26],[91.42,23.07],[91.36,23.1],[91.15,23.73],[91.28,23.98],[91.39,23.98],[91.38,24.1],[91.6,24.08],[91.67,24.23],[91.76,24.14],[91.75,24.24],[91.91,24.14],[91.93,24.34],[92.22,24.5]]]},{"name":"Uttar Pradesh","name_hi":"उत्तर प्रदेश","cells":[[12,8,0.097],[12,9,0.035],[12,11,0.201],[12,12,0.049],[13,8,0.104],[13,9,0.632],[13,10,0.771],[13,11,0.965],[13,12,0.417],[14,8,0.486],[14,9,0.931],[14,10,1.0],[14,11,0.938],[14,12,0.431],[15,7,0.014],[15,8,0.924],[15,9,0.792],[15,10,0.438],[15,11,0.028],[16,7,0.035],[16,8,0.396],[16,9,0.007]],"area_cells":9.69,"centroid_cell":[14,9],"label":[80.25,26.64],"outline":[[[77.6,30.4],[77.94,30.24],[77.71,29.87],[77.8,29.68],[77.96,29.7],[78.0,29.54],[78.43,29.77],[78.62,29.56],[78.94,29.45],[78.73,29.31],[78.91,29.14],[79.14,29.12],[79.42,28.85],[79.79,28.89],[79.98,28.71],[80.12,28.83],[80.52,28.56],[80.57,28.69],[81.22,28.36],[81.32,28.14],[81.43,28.17],[81.89,27.86],[82.07,27.92],[82.46,27.68],[82.71,27.73],[82.74,27.5],[83.18,27.45],[83.31,27.33],[83.39,27.48],[83.61,27.47],[83.93,27.32],[84.06,26.89],[84.25,26.86],[84.24,26.74],[84.42,26.62],[84.09,26.64],[84.06,26.54],[83.91,26.52],[84.18,26.37],[84.17,26.24],[84.01,26.18],[84.17,25.99],[84.54,25.88],[84.64,25.73],[84.34,25.74],[84.29,25.66],[84.1,25.72],[83.85,25.44],[83.34,25.18],[83.36,24.87],[83.55,24.62],[83.4,24.5],[83.46,24.36],[83.2,23.92],[82.95,23.88],[82.67,24.12],[82.77,24.29],[82.77,24.64],[82.44,24.7],[82.42,24.6],[82.3,24.61],[82.2,24.82],[81.97,24.83],[81.91,25.01],[81.61,25.06],[81.57,25.19],[81.49,25.07],[81.28,25.16],[81.14,24.89],[80.81,24.94],[80.89,25.19],[80.84,25.11],[80.71,25.13],[80.78,25.06],[80.6,25.15],[80.61,25.07],[80.48,25.1],[80.55,25.0],[80.46,24.98],[80.45,25.08],[80.29,25.02],[80.43,25.17],[80.26,25.42],[79.86,25.24],[79.86,25.09],[79.57,25.17],[79.5,25.08],[79.41,25.11],[79.5,25.27],[79.3,25.34],[79.31,25.13],[79.14,25.11],[79.09,25.19],[79.03,25.14],[79.01,25.27],[78.88,25.16],[78.96,25.34],[78.85,25.22],[78.79,25.29],[78.99,25.37],[78.94,25.55],[78.84,25.43],[78.74,25.5],[78.82,25.43],[78.77,25.35],[78.66,25.44],[78.43,25.28],[78.58,25.25],[78.63,24.96],[78.79,24.81],[78.76,24.6],[78.89,24.64],[78.97,24.35],[78.8,24.18],[78.51,24.39],[78.35,24.3],[78.17,24.85],[78.45,25.12],[78.3,25.37],[78.44,25.56],[78.81,25.62],[78.75,25.74],[78.87,25.79],[79.14,26.44],[78.99,26.57],[79.0,26.68],[78.36,26.87],[78.22,26.83],[78.22,26.95],[78.03,26.86],[77.76,26.93],[77.44,26.76],[77.43,26.86],[77.76,27.02],[77.52,27.06],[77.68,27.19],[77.32,27.61],[77.28,27.8],[77.55,27.94],[77.48,28.08],[77.55,28.24],[77.31,28.56],[77.33,28.71],[77.2,28.8],[77.1,29.6],[77.2,29.92],[77.6,30.4]]]},{"name":"Uttarakhand","name_hi":"उत्तराखंड","cells":[[15,9,0.188],[16,8,0.486],[16,9,0.993],[16,10,0.188],[17,8,0.194],[17,9,0.215]],"area_cells":2.26,"centroid_cell":[16,9],"label":[79.24,30.09],"outline":[[[79.21,31.35],[79.43,31.03],[79.6,30.94],[79.87,30.97],[80.24,30.76],[80.23,30.57],[81.03,30.25],[80.37,29.75],[80.41,29.6],[80.25,29.44],[80.3,29.2],[80.15,29.1],[80.0,28.71],[79.87,28.84],[79.8,28.8],[79.79,28.89],[79.42,28.85],[79.14,29.12],[78.91,29.14],[78.73,29.31],[78.94,29.45],[78.62,29.56],[78.49,29.74],[78.34,29.79],[78.0,29.54],[77.96,29.7],[77.8,29.68],[77.71,29.87],[77.94,30.24],[77.58,30.41],[77.82,30.53],[77.7,30.76],[77.9,31.15],[78.37,31.29],[78.96,31.1],[78.94,31.32],[79.06,31.46],[79.21,31.35]]]},{"name":"West Bengal","name_hi":"पश्चिम बंगाल","cells":[[10,14,0.014],[10,15,0.056],[11,13,0.028],[11,14,0.694],[11,15,0.757],[12,13,0.049],[12,14,0.396],[12,15,0.528],[13,15,0.333],[13,16,0.042],[14,15,0.375],[14,16,0.153]],"area_cells":3.42,"centroid_cell":[11,15],"label":[88.42,22.97],"outline":[[[88.14,21.88],[88.11,21.63],[88.04,21.68],[88.14,21.88]],[[88.09,27.16],[88.44,27.08],[88.6,27.19],[88.88,27.11],[88.88,26.95],[89.03,26.94],[89.14,26.81],[89.38,26.87],[89.86,26.7],[89.87,26.45],[89.72,26.3],[89.74,26.17],[89.65,26.23],[89.6,26.16],[89.65,26.07],[89.55,25.97],[89.16,26.14],[89.09,26.4],[88.92,26.4],[89.05,26.24],[88.68,26.27],[88.75,26.35],[88.38,26.59],[88.36,26.45],[88.49,26.46],[88.53,26.36],[88.18,26.15],[88.11,25.8],[88.27,25.81],[88.54,25.51],[88.8,25.52],[88.85,25.36],[89.01,25.27],[88.92,25.17],[88.44,25.21],[88.4,24.94],[88.33,24.87],[88.14,24.93],[88.18,24.86],[88.01,24.66],[88.34,24.38],[88.74,24.27],[88.77,23.99],[88.58,23.86],[88.57,23.64],[88.8,23.5],[88.72,23.26],[89.0,23.21],[88.85,23.01],[88.97,22.85],[88.96,22.61],[88.85,22.43],[88.77,22.56],[88.67,22.55],[88.95,22.23],[88.84,22.29],[88.92,22.17],[88.81,22.28],[88.84,22.17],[88.75,22.2],[88.79,22.26],[88.64,22.21],[88.67,22.34],[88.62,22.11],[88.57,22.19],[88.61,21.91],[88.55,21.97],[88.49,21.88],[88.55,22.04],[88.47,21.9],[88.46,22.01],[88.41,21.89],[88.38,21.97],[88.39,21.8],[88.36,21.92],[88.35,21.86],[88.27,21.88],[88.27,21.73],[88.16,21.88],[88.2,22.17],[88.07,22.21],[88.11,22.3],[87.98,22.25],[87.88,22.44],[87.94,22.26],[88.19,22.1],[88.06,22.01],[87.96,22.1],[88.05,22.01],[87.96,21.83],[87.49,21.6],[87.24,21.96],[87.03,21.87],[87.02,22.05],[86.72,22.15],[86.89,22.3],[86.77,22.58],[86.42,22.78],[86.44,22.93],[86.55,22.99],[86.21,23.0],[85.83,23.27],[85.87,23.47],[86.05,23.5],[86.04,23.59],[86.31,23.42],[86.45,23.63],[86.8,23.69],[86.8,23.83],[87.25,23.83],[87.24,24.04],[87.46,23.98],[87.5,24.12],[87.7,24.16],[87.64,24.24],[87.82,24.41],[87.77,24.58],[87.92,24.6],[87.82,24.77],[87.98,24.9],[87.78,25.1],[87.86,25.28],[87.77,25.41],[87.93,25.54],[88.08,25.5],[88.05,25.69],[87.81,25.92],[87.85,26.04],[88.3,26.35],[88.19,26.49],[88.24,26.55],[88.11,26.55],[88.18,26.86],[87.99,27.11],[88.02,27.22],[88.09,27.16]]]}]}'''

# %%
# ---- 2. Build ---------------------------------------------------------------------------
import argparse, json, os, glob, datetime as dt
import numpy as np
import pandas as pd

HERE = os.getcwd()
TYPES = ["rain", "heat", "wind", "z500"]
TYPE_LABELS = {"rain": "Rain", "heat": "Heat (Tmax)", "wind": "Wind", "z500": "500 hPa pattern", "any": "Any"}
SYSTEMS = ["depression", "cyclone", "wd", "heatwave", "active", "break"]
SYSTEM_LABELS = {"depression": "Monsoon depression", "cyclone": "Cyclonic system", "wd": "Western disturbance",
                 "heatwave": "Heat wave", "active": "Active monsoon", "break": "Monsoon break"}
# Hindi labels for the Hindi bulletin
REGION_HI = {"Himalayan WH": "पश्चिमी हिमालय", "NE India": "पूर्वोत्तर भारत", "NW India": "उत्तर-पश्चिम भारत",
             "East India": "पूर्वी भारत", "West Coast": "पश्चिमी तट", "Central India": "मध्य भारत",
             "S. Peninsula": "दक्षिण प्रायद्वीप"}
TYPE_LABELS_HI = {"rain": "वर्षा", "heat": "ताप (अधिकतम तापमान)", "wind": "पवन", "z500": "500 hPa पैटर्न", "any": "कोई भी"}
SYSTEM_LABELS_HI = {"depression": "मानसून अवदाब", "cyclone": "चक्रवाती प्रणाली", "wd": "पश्चिमी विक्षोभ",
                    "heatwave": "लू (हीट वेव)", "active": "सक्रिय मानसून", "break": "मानसून विराम"}
ISLANDS = {"Andaman & Nicobar Islands", "Lakshadweep"}       # outside the 1.5° land regions: drawn, not scored
EVENTS = [
    ("Kerala floods", "West Coast", "2018-08-14", "2018-08-17", "rain"),
    ("Cyclone Fani", "East India", "2019-05-02", "2019-05-04", "any"),
    ("Mumbai extreme rain", "West Coast", "2019-07-01", "2019-07-02", "rain"),
    ("Cyclone Amphan", "East India", "2020-05-19", "2020-05-21", "any"),
    ("Hyderabad floods", "S. Peninsula", "2020-10-13", "2020-10-14", "rain"),
    ("Cyclone Tauktae", "West Coast", "2021-05-15", "2021-05-17", "any"),
    ("Uttarakhand extreme rain", "Himalayan WH", "2021-10-17", "2021-10-19", "rain"),
    ("NW India heat wave", "NW India", "2022-04-26", "2022-04-30", "heat"),
    ("Assam/Meghalaya floods", "NE India", "2022-06-14", "2022-06-17", "rain"),
]


def read_table(folder, stem):
    for ext, fn in ((".parquet", pd.read_parquet), (".csv.gz", pd.read_csv), (".csv", pd.read_csv)):
        p = os.path.join(folder, stem + ext)
        if os.path.exists(p):
            try:
                return fn(p)
            except pd.errors.EmptyDataError:
                return None
    return None


def read_grid(folder):
    p = os.path.join(folder, "grid_meta.nc")
    try:
        import xarray as xr
        g = xr.open_dataset(p).load()
        return (g.lat.values.tolist(), g.lon.values.tolist(), g.region_id.values.astype(int).tolist(),
                g.land.values.astype(int).tolist(), json.loads(g.attrs["regions"]))
    except Exception:
        from scipy.io import netcdf_file
        with netcdf_file(p, "r", mmap=False) as f:
            regions = json.loads(f.regions.decode() if isinstance(f.regions, bytes) else f.regions)
            return (f.variables["lat"][:].tolist(), f.variables["lon"][:].tolist(),
                    f.variables["region_id"][:].astype(int).tolist(), f.variables["land"][:].astype(int).tolist(), regions)


def pct(x):
    return np.where(np.isfinite(x), np.round(100 * x), -1).astype(int)


def read_unet(unet_path, dates, leads, land):
    """Grid-level U-Net probabilities for land cells, packed as base64 uint8 (255 = missing)."""
    import base64
    try:
        import xarray as xr
        u = xr.open_dataset(unet_path).load()
    except Exception as e:
        print("U-Net layer skipped:", e); return None
    land = np.array(land, bool); cells = np.flatnonzero(land.ravel())
    ui = pd.Index(pd.DatetimeIndex(u.init.values).normalize())
    out = np.full((len(dates), len(leads), len(cells)), 255, dtype=np.uint8)
    pv = u["p"].transpose("init", "lead", "lat", "lon").values
    for k, d in enumerate(dates):
        j = ui.get_indexer([pd.Timestamp(d)])[0]
        if j >= 0:
            out[k] = np.clip(pv[j].reshape(len(leads), -1)[:, cells], 0, 100).astype(np.uint8)
    metrics = None
    mp = os.path.join(os.path.dirname(unet_path), "unet_metrics.json")
    if os.path.exists(mp):
        metrics = json.load(open(mp))
    return {"cells": cells.tolist(), "p_b64": base64.b64encode(out.tobytes()).decode(), "metrics": metrics}


def read_states(rid, land):
    """State outlines (DataMeet / Survey of India) + how much of each state lies in each forecast region."""
    S = json.loads(STATES_JSON)
    rid = np.array(rid); nla, nlo = rid.shape
    reg_cells = np.argwhere(rid >= 0)
    out = []
    for st in S["states"]:
        wts, cells, cover, total = {}, [], 0.0, 0.0
        for i, j, w in st["cells"]:
            total += w
            if rid[i][j] >= 0:
                wts[int(rid[i][j])] = wts.get(int(rid[i][j]), 0) + w; cover += w
            if land[i][j]:
                cells.append([i, j, w])
        scored = st["name"] not in ISLANDS
        if scored and not wts:                                  # tiny UT or area outside the region boxes: nearest region
            ci, cj = st["centroid_cell"]
            k = np.argmin(((reg_cells - [ci, cj]) ** 2).sum(1)); wts = {int(rid[tuple(reg_cells[k])]): 1.0}
        tw = sum(wts.values()) or 1
        out.append({"name": st["name"], "name_hi": st["name_hi"], "label": st["label"], "outline": st["outline"],
                    "scored": scored, "regions": [[r, round(w / tw, 3)] for r, w in sorted(wts.items(), key=lambda x: -x[1])],
                    "coverage": round(cover / total, 2) if total else 0, "cells": cells})
    return {"source": S["source"], "india_outline": S["india_outline"], "states": out}


def build(models_dir, years=None, unet_path=None):
    pred = read_table(models_dir, "predictions")
    if pred is None:
        raise FileNotFoundError(f"predictions.parquet not found in {models_dir}")
    pred["init"] = pd.to_datetime(pred["init"]); pred["valid_date"] = pd.to_datetime(pred["valid_date"])
    lat, lon, rid, land, regions = read_grid(models_dir)
    R = len(regions); leads = sorted(pred["lead"].unique().tolist()); NL = len(leads)
    types = [t for t in TYPES if f"p_bust_{t}" in pred]

    # dashboard covers the validation + test years (the honest, not-trained-on period)
    if years is None:
        years = sorted(pred.loc[pred["split"].isin(["val", "test", "live"]), "init"].dt.year.unique().tolist())
    sub = pred[pred["init"].dt.year.isin(years)].copy()
    dates = sorted(sub["init"].dt.normalize().unique())
    full = pd.MultiIndex.from_product([dates, leads, regions], names=["init", "lead", "region"])
    sub = sub.set_index(["init", "lead", "region"]).reindex(full).reset_index()

    reasons_list, reasons_hi, reason_idx = [], [], {}
    def ridx(s, h):
        if not isinstance(s, str) or not s:
            return -1
        h = h if isinstance(h, str) and h else s
        if (s, h) not in reason_idx:
            reason_idx[(s, h)] = len(reasons_list); reasons_list.append(s); reasons_hi.append(h)
        return reason_idx[(s, h)]

    cols = {"p": pct(sub["p_bust"].values)}
    for t in types:
        cols[f"p_{t}"] = pct(sub[f"p_bust_{t}"].values)
    act = np.zeros(len(sub), dtype=int)                     # bitmask of real busts: bit k = TYPES[k]
    for k, t in enumerate(types):
        if f"bust_{t}" in sub:
            act |= (sub[f"bust_{t}"].fillna(0).astype(int).values << k)
    cols["actual"] = np.where(sub["bust"].isna(), -1, act).astype(int)
    sysm = np.zeros(len(sub), dtype=int)
    for k, s in enumerate(SYSTEMS):
        if f"sys_{s}" in sub:
            sysm |= (sub[f"sys_{s}"].fillna(0).astype(int).values << k)
    cols["sys"] = sysm
    en = sub["reasons"] if "reasons" in sub else pd.Series([""] * len(sub))
    hi = sub["reasons_hi"] if "reasons_hi" in sub else en
    cols["reason"] = np.array([ridx(a, b) for a, b in zip(en, hi)], dtype=int)
    for c, scale in [("fc_rain", 10), ("obs_rain", 10), ("rain_lo", 10), ("rain_med", 10), ("rain_hi", 10)]:
        if c in sub:
            cols[c] = np.where(np.isfinite(sub[c]), np.round(sub[c] * scale), -1).astype(int)
    if "fc_tmax_bc" in sub:
        cols["fc_tmax"] = np.where(np.isfinite(sub["fc_tmax_bc"]), np.round((sub["fc_tmax_bc"] - 273.15) * 10), -9999).astype(int)
    if "obs_heat" in sub:
        cols["obs_tmax"] = np.where(np.isfinite(sub["obs_heat"]), np.round((sub["obs_heat"] - 273.15) * 10), -9999).astype(int)
    split_of_date = sub.groupby("init")["split"].first().reindex(dates).fillna("none").tolist()

    # analogue dates (top 3) for the included dates
    analogs = {}
    ap = os.path.join(models_dir, "analog_dates.json")
    if os.path.exists(ap):
        allan = json.load(open(ap))
        keep = {str(pd.Timestamp(d).date()) for d in dates}
        analogs = {k: v for k, v in allan.items() if k.split("|")[0] in keep}
    # outcome of each analogue (did it bust in each region?) from the full predictions
    busted = pred.set_index(["init", "lead", "region"])["bust"]
    analog_outcome = {}
    for k, v in list(analogs.items()):
        L = int(k.split("|")[1])
        for d in v:
            key = f"{d}|{L}"
            if key in analog_outcome:
                continue
            analog_outcome[key] = [int(busted.get((pd.Timestamp(d), L, r), -1)) if pd.notna(busted.get((pd.Timestamp(d), L, r), np.nan)) else -1
                                   for r in regions]

    # event replays from the full predictions (all years)
    events = []
    for name, region, d0, d1, typ in EVENTS:
        pc = "p_bust" if typ == "any" or f"p_bust_{typ}" not in pred else f"p_bust_{typ}"
        ac = "bust" if typ == "any" or f"bust_{typ}" not in pred else f"bust_{typ}"
        s = pred[(pred.region == region) & (pred.valid_date >= d0) & (pred.valid_date <= d1)]
        if s.empty:
            continue
        g = s.groupby("lead").agg(p=(pc, "max"), a=(ac, "max"))
        first_init = {int(L): str((pd.Timestamp(d0) - pd.Timedelta(days=int(L) - 1)).date()) for L in leads}
        sysk = [SYSTEM_LABELS[x] for x in SYSTEMS if f"sys_{x}" in s and s[f"sys_{x}"].max() == 1]
        events.append({"name": name, "region": region, "start": d0, "end": d1, "type": typ,
                       "split": s["split"].iloc[0], "p": [int(round(100 * g.p.get(L, np.nan))) if pd.notna(g.p.get(L, np.nan)) else None for L in leads],
                       "actual": [int(g.a.get(L, 0)) if pd.notna(g.a.get(L, np.nan)) else None for L in leads],
                       "init_for_lead": first_init, "systems": sysk,
                       "obs_rain_max": round(float(s["obs_rain"].max()), 1) if "obs_rain" in s else None})

    def csv(stem):
        t = read_table(models_dir, stem)
        return None if t is None else json.loads(t.to_json(orient="records"))

    auc = read_table(models_dir, "auc_by_lead")
    if unet_path is None:
        cand = (glob.glob(os.path.join(models_dir, "..", "bustradar_unet", "unet_probs.nc"))
                + glob.glob("/kaggle/working/bustradar_unet/unet_probs.nc")
                + glob.glob(os.path.join(HERE, "..", "data", "bustradar_unet", "unet_probs.nc")))
        unet_path = cand[0] if cand else None
    unet = read_unet(unet_path, dates, leads, land) if unet_path else None
    info = {}
    if os.path.exists(os.path.join(models_dir, "run_info.json")):
        info = json.load(open(os.path.join(models_dir, "run_info.json")))
    live_src = None
    for c in glob.glob(os.path.join(models_dir, "..", "bustradar_data", "live_info.json")) + glob.glob("/kaggle/working/bustradar_data/live_info.json") + glob.glob("/kaggle/input/**/live_info.json", recursive=True):
        live_src = json.load(open(c)).get("source"); break
    rr = read_table(models_dir, "rain_range_coverage")
    bundle = {
        "meta": {"generated": dt.datetime.now().strftime("%Y-%m-%d %H:%M"), "regions": regions, "leads": leads,
                 "types": types, "type_labels": TYPE_LABELS, "systems": SYSTEMS, "system_labels": SYSTEM_LABELS,
                 "regions_hi": [REGION_HI.get(r, r) for r in regions], "type_labels_hi": TYPE_LABELS_HI,
                 "system_labels_hi": SYSTEM_LABELS_HI, "alert_threshold": info.get("alert_threshold"),
                 "live_runs": [d for d in info.get("live_runs", []) if d in {str(pd.Timestamp(x).date()) for x in dates}],
                 "live_source": live_src or "ECMWF open data (IFS)",
                 "years": years, "n_rows": int(len(sub))},
        "grid": {"lat": lat, "lon": lon, "region_id": rid, "land": land},
        "dates": [str(pd.Timestamp(d).date()) for d in dates], "date_split": split_of_date,
        "cols": {k: v.tolist() for k, v in cols.items()}, "reasons": reasons_list, "reasons_hi": reasons_hi,
        "states": read_states(rid, land),
        "rain_range_coverage": None if rr is None else json.loads(rr.to_json(orient="records")),
        "analogs": analogs, "analog_outcome": analog_outcome, "events": events,
        "metrics": csv("metrics"), "systems_table": csv("busts_by_system"),
        "auc_by_lead": None if auc is None else json.loads(auc.to_json(orient="records")),
        "unet": unet,
    }
    return bundle


def write(bundle, out):
    os.makedirs(out, exist_ok=True)
    js = json.dumps(bundle, separators=(",", ":"))
    open(os.path.join(out, "bundle.json"), "w").write(js)
    tpl = TEMPLATE
    html = tpl.replace("/*__BUNDLE__*/null", js.replace("</", "<\\/"))
    open(os.path.join(out, "bustradar_dashboard.html"), "w", encoding="utf-8").write(html)
    print(f"wrote {out}/bundle.json ({len(js) / 1e6:.1f} MB) and {out}/bustradar_dashboard.html")



MODELS = globals().get("MODELS") or next((os.path.dirname(p) for p in
          glob.glob("/kaggle/working/bustradar_models/predictions.*")
          + glob.glob("/kaggle/input/**/bustradar_models/predictions.*", recursive=True)
          + glob.glob("../data/bustradar_models/predictions.*") + glob.glob("./data/bustradar_models/predictions.*")
          + glob.glob("./**/bustradar_models/predictions.*", recursive=True)), None)
UNET = globals().get("UNET") or next(iter(glob.glob("/kaggle/working/bustradar_unet/unet_probs.nc")
                                          + glob.glob("/kaggle/input/**/unet_probs.nc", recursive=True)
                                          + glob.glob("../data/bustradar_unet/unet_probs.nc") + glob.glob("./data/bustradar_unet/unet_probs.nc")
                                          + glob.glob("./**/bustradar_unet/unet_probs.nc", recursive=True)), None)
OUT5 = globals().get("OUT5") or ("/kaggle/working/bustradar_dashboard" if os.path.exists("/kaggle") else "./bustradar_dashboard")
bundle = build(MODELS, unet_path=UNET)
write(bundle, OUT5)
print(f"{len(bundle['dates'])} model runs ({len(bundle['meta']['live_runs'])} live), {len(bundle['events'])} event replays, U-Net layer: {bundle['unet'] is not None}")
print(f"Download bustradar_dashboard.html from {OUT5}")
