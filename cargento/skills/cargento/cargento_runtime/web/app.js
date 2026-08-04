const qs = new URLSearchParams(location.search);
const showAll = qs.get("all") === "1";
let idleExpanded = false;
let lastData = null;
let refreshSequence = 0;
let latestSettledRefresh = 0;

const esc = s => String(s == null ? "" : s).replace(/[&<>"']/g,
  c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));

function fmtDur(sec){
  if(sec == null || sec < 0) return "–";
  sec = Math.floor(sec);
  if(sec < 60) return sec + "s";
  if(sec < 3600) return Math.floor(sec/60) + "m";
  if(sec < 86400) return Math.floor(sec/3600) + "h " + Math.floor((sec%3600)/60) + "m";
  return Math.floor(sec/86400) + "d " + Math.floor((sec%86400)/3600) + "h";
}

// One wording for the long-turn signal: the regular view's ⚠️ tooltip and the
// calm ledger's flag explanation must not drift apart.
const LONG_TURN_NOTE = "This request is running long (or estimated to). " +
  "Double-check what the agent is doing matches your expectations.";

// MCP tools reach the payload under their wire name — a mangled
// `mcp` + server + tool triple joined by double underscores. Rendering that raw
// puts the transport's naming convention on screen where the reader wants to
// know which service is being called. Rewrite it to "server · tool name" and
// leave every other tool name exactly as the harness reported it.
const MCP_TOOL = /\bmcp__([A-Za-z0-9-]+(?:_[A-Za-z0-9-]+)*?)__([A-Za-z0-9_-]+)/g;
// Host prefixes that identify the connection, not the service behind it.
const MCP_HOST_PREFIX = /^(?:claude_ai_|claude_code_|plugin_)/;
function humanTool(text){
  return String(text == null ? "" : text).replace(MCP_TOOL, (whole, server, tool) => {
    const service = server.replace(MCP_HOST_PREFIX, "").replace(/_+/g, " ").trim();
    const action = tool.replace(/_+/g, " ").trim();
    if(!action) return whole;              // nothing left to show — keep the original
    return (service ? service + " · " : "") + action;
  });
}

// Trailing output-rate sparklines: client-side ring buffers that start when
// the page opens and drop points once they age out of the visual window.
// Points are stamped with the VIEWER's clock at receipt — the axis and the
// tooltip timestamps must agree with the user's watch, and the server's
// `generated` value can lag (2.5s response memoization) or skew. `generated`
// is used only to drop replayed/memoized payloads.
const SPARK_WINDOW_SEC = 300;
const nowSec = () => Date.now() / 1000;
const rateHistory = [];               // overall: [{t, v}]
const sessRateHistory = new Map();    // "harness:sid" -> [{t, v}]
const sessKey = x => x.harness + ":" + (x.sid || x.session);
let lastGenerated = 0;

function pushPoint(arr, t, v){
  if(arr.length && arr[arr.length-1].t >= t) return; // non-advancing clock
  arr.push({t, v});
  const cutoff = t - SPARK_WINDOW_SEC;
  while(arr.length && arr[0].t < cutoff) arr.shift();
}

function recordRates(d){
  if(typeof d.generated !== 'number' || !isFinite(d.generated)) return;
  if(d.generated <= lastGenerated) return; // memoized/replayed payload
  lastGenerated = d.generated;
  const t = nowSec();
  pushPoint(rateHistory, t, d.summary.rate_per_min || 0);
  const seen = new Set();
  for(const x of d.sessions){
    const key = sessKey(x);
    seen.add(key);
    let arr = sessRateHistory.get(key);
    if(!arr) sessRateHistory.set(key, arr = []);
    pushPoint(arr, t, x.rate_per_min || 0);
  }
  // Remove entries for departed sessions AND aged-out orphaned buffers (no updates in 600s).
  // This ensures memory doesn't leak if a session disappears before the next recordRates() call.
  for(const [k, arr] of sessRateHistory){
    if(!seen.has(k) || (arr.length && arr[arr.length-1].t < t - 600)){
      sessRateHistory.delete(k);
    }
  }
}

const SPARK_PAD = 3;
const sparkX = (t, now, w) => {
  if(!isFinite(t) || !isFinite(now) || !isFinite(w) || SPARK_WINDOW_SEC <= 0) return 0;
  return w - SPARK_PAD - (now - t) * (w - 2*SPARK_PAD) / SPARK_WINDOW_SEC;
};
const sparkY = (v, max, h) => {
  if(!isFinite(v) || !isFinite(max) || !isFinite(h) || max <= 0) return h - SPARK_PAD;
  return h - SPARK_PAD - (v / max) * (h - 2*SPARK_PAD);
};

function sparkSVG(pts, now, w, h, stretch){
  if(!isFinite(w) || !isFinite(h) || !isFinite(now) || w <= 0 || h <= 0) return "";
  const base = h - SPARK_PAD;
  let marks = "";
  if(pts && pts.length > 1){
    const max = Math.max(1, ...pts.map(p => p.v));
    if(!isFinite(max)) return ""; // Guard against NaN from points
    const xy = pts.map(p => {
      const x = sparkX(p.t, now, w);
      const y = sparkY(p.v, max, h);
      return [isFinite(x) ? x : 0, isFinite(y) ? y : h/2]; // Default to safe values if NaN
    });
    const pathPts = xy.map(c => c[0].toFixed(2) + "," + c[1].toFixed(2));
    const area = "M" + xy[0][0].toFixed(2) + "," + base + " L" + pathPts.join(" L") +
      " L" + xy[xy.length-1][0].toFixed(2) + "," + base + " Z";
    marks = `<path d="${area}" fill="var(--accent)" fill-opacity=".12"/>` +
      `<polyline points="${pathPts.join(" ")}" fill="none"` +
      ` stroke="color-mix(in oklab,var(--accent) 72%,var(--ink3))" stroke-width="2"` +
      ` stroke-linejoin="round" stroke-linecap="round" vector-effect="non-scaling-stroke"/>`;
    if(!stretch){
      const e = xy[xy.length-1];
      marks += `<circle cx="${e[0].toFixed(2)}" cy="${e[1].toFixed(2)}" r="3.5"` +
        ` fill="var(--accent)" stroke="var(--panel)" stroke-width="2"/>`;
    }
  }
  return `<svg viewBox="0 0 ${w} ${h}"${stretch ? ' preserveAspectRatio="none"' : ""} aria-hidden="true">` +
    `<line x1="0" y1="${base}" x2="${w}" y2="${base}" stroke="var(--line)" stroke-width="1"` +
    ` vector-effect="non-scaling-stroke"/>${marks}</svg>`;
}

function heroSpark(){
  // Stretched viewBox (0..100 units) so the HTML end-dot and crosshair can
  // share the same coordinates as percentages of the wrap's width and height.
  // The axis anchors to the viewer's clock — the same clock the points are
  // stamped with — so hover timestamps never drift from wall time.
  const axisNow = nowSec();
  let dot = "";
  if(rateHistory.length > 1){
    const max = Math.max(1, ...rateHistory.map(p => p.v));
    const last = rateHistory[rateHistory.length-1];
    const dotX = sparkX(last.t, axisNow, 100);
    const dotY = sparkY(last.v, max, 100); // Use 100 to get percentage coordinates (0-100%)
    dot = `<span class="spark-dot" style="left:${dotX.toFixed(2)}%;` +
      `top:${dotY.toFixed(2)}%"></span>`;
  }
  const lastV = rateHistory.length ? rateHistory[rateHistory.length-1].v : null;
  const nowLabel = lastV == null ? "" :
    `, now ${lastV.toLocaleString()} tokens per minute`;
  return `<div class="spark-wrap" id="spark-main" tabindex="0" data-now="${axisNow}"` +
    ` role="img" aria-label="output rate, trailing 5 minutes${nowLabel}">` +
    sparkSVG(rateHistory, axisNow, 100, 46, true) + dot +
    `<span class="spark-x" id="spark-x"></span><span class="spark-tip" id="spark-tip"></span></div>`;
}

function hideSparkHover(){
  if(sparkHoverCache && sparkHoverCache.xline) sparkHoverCache.xline.style.opacity = 0;
  if(sparkHoverCache && sparkHoverCache.tip) sparkHoverCache.tip.style.opacity = 0;
}

// Cache DOM nodes and child elements for efficient hover updates.
let sparkHoverCache = null;
function initSparkHoverCache(){
  sparkHoverCache = {
    xline: document.getElementById("spark-x"),
    tip: document.getElementById("spark-tip"),
    tipVal: null,
    tipTime: null
  };
  if(sparkHoverCache.tip){
    // Create tip children once and reuse them.
    sparkHoverCache.tipVal = document.createElement("b");
    sparkHoverCache.tipTime = document.createTextNode("");
    sparkHoverCache.tip.appendChild(sparkHoverCache.tipVal);
    sparkHoverCache.tip.appendChild(sparkHoverCache.tipTime);
  }
  return sparkHoverCache;
}

function showSparkHover(frac){
  const wrap = document.getElementById("spark-main");
  if(!wrap || rateHistory.length < 2) return;
  const now = parseFloat(wrap.dataset.now);
  if(typeof now !== 'number' || !isFinite(now)) return;
  const t = now - (1 - Math.min(1, Math.max(0, frac))) * SPARK_WINDOW_SEC;
  let best = rateHistory[0];
  for(const p of rateHistory) if(Math.abs(p.t - t) < Math.abs(best.t - t)) best = p;
  if(!isFinite(best.v) || !isFinite(best.t)) return;
  const x = sparkX(best.t, now, 100);
  if(!isFinite(x)) return;

  // Use cached DOM nodes instead of recreating on every move event.
  let cache = sparkHoverCache;
  if(!cache || !cache.xline || !cache.xline.parentElement){
    cache = initSparkHoverCache();
  }
  if(!cache.xline || !cache.tip || !cache.tipVal || !cache.tipTime) return;

  cache.xline.style.left = x.toFixed(2) + "%";
  cache.xline.style.opacity = 1;
  cache.tip.style.left = Math.min(88, Math.max(12, x)).toFixed(2) + "%";
  // Update cached tip content instead of recreating DOM.
  cache.tipVal.textContent = best.v.toLocaleString();
  cache.tipTime.textContent = " tok/min · " + new Date(best.t * 1000).toLocaleTimeString();
  cache.tip.style.opacity = 1;
}

let sparkPointer = null; // last pointer position while over the sparkline
let renderInProgress = false; // prevent race between DOM updates and event handlers

document.addEventListener("pointermove", e => {
  if(renderInProgress) return; // Skip updates during render
  const wrap = e.target.closest ? e.target.closest("#spark-main") : null;
  if(!wrap){ sparkPointer = null; hideSparkHover(); return; }
  sparkPointer = {x: e.clientX, y: e.clientY};
  const r = wrap.getBoundingClientRect();
  showSparkHover((e.clientX - r.left) / Math.max(1, r.width));
});
document.addEventListener("focusin", e => {
  if(e.target && e.target.id === "spark-main") showSparkHover(1);
});
document.addEventListener("focusout", e => {
  if(e.target && e.target.id === "spark-main") hideSparkHover();
});

// The pointer can leave the page without a final in-document pointermove
// (window-edge exit, alt-tab, tab switch). Clear the saved position on those
// paths, or restoreSparkState() resurrects the tooltip for a pointer that is
// gone on every subsequent poll.
function clearSparkPointer(){ sparkPointer = null; hideSparkHover(); }
document.addEventListener("mouseout", e => { if(!e.relatedTarget) clearSparkPointer(); });
window.addEventListener("blur", clearSparkPointer);
document.addEventListener("visibilitychange", () => { if(document.hidden) clearSparkPointer(); });

// render() replaces #app wholesale, which kills the sparkline's focus and
// resets its hover layer; re-apply both against the freshly built DOM.
function restoreSparkState(hadFocus, savedPointer){
  // Invalidate the hover cache since the DOM was replaced.
  sparkHoverCache = null;

  const wrap = document.getElementById("spark-main");
  if(!wrap) return;
  if(hadFocus){ wrap.focus({preventScroll: true}); return; } // focusin re-shows tip

  // Restore hover state based on saved pointer position (captured before render).
  if(!savedPointer) return;
  const r = wrap.getBoundingClientRect();
  if(savedPointer.x >= r.left && savedPointer.x <= r.right &&
     savedPointer.y >= r.top && savedPointer.y <= r.bottom){
    showSparkHover((savedPointer.x - r.left) / Math.max(1, r.width));
  }
}

const ICON_PATH = {
  claude: "M4.709 15.955l4.72-2.647.08-.23-.08-.128H9.2l-.79-.048-2.698-.073-2.339-.097-2.266-.122-.571-.121L0 11.784l.055-.352.48-.321.686.06 1.52.103 2.278.158 1.652.097 2.449.255h.389l.055-.157-.134-.098-.103-.097-2.358-1.596-2.552-1.688-1.336-.972-.724-.491-.364-.462-.158-1.008.656-.722.881.06.225.061.893.686 1.908 1.476 2.491 1.833.365.304.145-.103.019-.073-.164-.274-1.355-2.446-1.446-2.49-.644-1.032-.17-.619a2.97 2.97 0 01-.104-.729L6.283.134 6.696 0l.996.134.42.364.62 1.414 1.002 2.229 1.555 3.03.456.898.243.832.091.255h.158V9.01l.128-1.706.237-2.095.23-2.695.08-.76.376-.91.747-.492.584.28.48.685-.067.444-.286 1.851-.559 2.903-.364 1.942h.212l.243-.242.985-1.306 1.652-2.064.73-.82.85-.904.547-.431h1.033l.76 1.129-.34 1.166-1.064 1.347-.881 1.142-1.264 1.7-.79 1.36.073.11.188-.02 2.856-.606 1.543-.28 1.841-.315.833.388.091.395-.328.807-1.969.486-2.309.462-3.439.813-.042.03.049.061 1.549.146.662.036h1.622l3.02.225.79.522.474.638-.079.485-1.215.62-1.64-.389-3.829-.91-1.312-.329h-.182v.11l1.093 1.068 2.006 1.81 2.509 2.33.127.578-.322.455-.34-.049-2.205-1.657-.851-.747-1.926-1.62h-.128v.17l.444.649 2.345 3.521.122 1.08-.17.353-.608.213-.668-.122-1.374-1.925-1.415-2.167-1.143-1.943-.14.08-.674 7.254-.316.37-.729.28-.607-.461-.322-.747.322-1.476.389-1.924.315-1.53.286-1.9.17-.632-.012-.042-.14.018-1.434 1.967-2.18 2.945-1.726 1.845-.414.164-.717-.37.067-.662.401-.589 2.388-3.036 1.44-1.882.93-1.086-.006-.158h-.055L4.132 18.56l-1.13.146-.487-.456.061-.746.231-.243 1.908-1.312-.006.006z",
  codex: "M8.086.457a6.105 6.105 0 013.046-.415c1.333.153 2.521.72 3.564 1.7a.117.117 0 00.107.029c1.408-.346 2.762-.224 4.061.366l.063.03.154.076c1.357.703 2.33 1.77 2.918 3.198.278.679.418 1.388.421 2.126a5.655 5.655 0 01-.18 1.631.167.167 0 00.04.155 5.982 5.982 0 011.578 2.891c.385 1.901-.01 3.615-1.183 5.14l-.182.22a6.063 6.063 0 01-2.934 1.851.162.162 0 00-.108.102c-.255.736-.511 1.364-.987 1.992-1.199 1.582-2.962 2.462-4.948 2.451-1.583-.008-2.986-.587-4.21-1.736a.145.145 0 00-.14-.032c-.518.167-1.04.191-1.604.185a5.924 5.924 0 01-2.595-.622 6.058 6.058 0 01-2.146-1.781c-.203-.269-.404-.522-.551-.821a7.74 7.74 0 01-.495-1.283 6.11 6.11 0 01-.017-3.064.166.166 0 00.008-.074.115.115 0 00-.037-.064 5.958 5.958 0 01-1.38-2.202 5.196 5.196 0 01-.333-1.589 6.915 6.915 0 01.188-2.132c.45-1.484 1.309-2.648 2.577-3.493.282-.188.55-.334.802-.438.286-.12.573-.22.861-.304a.129.129 0 00.087-.087A6.016 6.016 0 015.635 2.31C6.315 1.464 7.132.846 8.086.457zm-.804 7.85a.848.848 0 00-1.473.842l1.694 2.965-1.688 2.848a.849.849 0 001.46.864l1.94-3.272a.849.849 0 00.007-.854l-1.94-3.393zm5.446 6.24a.849.849 0 000 1.695h4.848a.849.849 0 000-1.696h-4.848z",
  gemini: "M20.616 10.835a14.147 14.147 0 01-4.45-3.001 14.111 14.111 0 01-3.678-6.452.503.503 0 00-.975 0 14.134 14.134 0 01-3.679 6.452 14.155 14.155 0 01-4.45 3.001c-.65.28-1.318.505-2.002.678a.502.502 0 000 .975c.684.172 1.35.397 2.002.677a14.147 14.147 0 014.45 3.001 14.112 14.112 0 013.679 6.453.502.502 0 00.975 0c.172-.685.397-1.351.677-2.003a14.145 14.145 0 013.001-4.45 14.113 14.113 0 016.453-3.678.503.503 0 000-.975 13.245 13.245 0 01-2.003-.678z",
  copilot: "M19.245 5.364c1.322 1.36 1.877 3.216 2.11 5.817.622 0 1.2.135 1.592.654l.73.964c.21.278.323.61.323.955v2.62c0 .339-.173.669-.453.868C20.239 19.602 16.157 21.5 12 21.5c-4.6 0-9.205-2.583-11.547-4.258-.28-.2-.452-.53-.453-.868v-2.62c0-.345.113-.679.321-.956l.73-.963c.392-.517.974-.654 1.593-.654l.029-.297c.25-2.446.81-4.213 2.082-5.52 2.461-2.54 5.71-2.851 7.146-2.864h.198c1.436.013 4.685.323 7.146 2.864zm-7.244 4.328c-.284 0-.613.016-.962.05-.123.447-.305.85-.57 1.108-1.05 1.023-2.316 1.18-2.994 1.18-.638 0-1.306-.13-1.851-.464-.516.165-1.012.403-1.044.996a65.882 65.882 0 00-.063 2.884l-.002.48c-.002.563-.005 1.126-.013 1.69.002.326.204.63.51.765 2.482 1.102 4.83 1.657 6.99 1.657 2.156 0 4.504-.555 6.985-1.657a.854.854 0 00.51-.766c.03-1.682.006-3.372-.076-5.053-.031-.596-.528-.83-1.046-.996-.546.333-1.212.464-1.85.464-.677 0-1.942-.157-2.993-1.18-.266-.258-.447-.661-.57-1.108-.32-.032-.64-.049-.96-.05zm-2.525 4.013c.539 0 .976.426.976.95v1.753c0 .525-.437.95-.976.95a.964.964 0 01-.976-.95v-1.752c0-.525.437-.951.976-.951zm5 0c.539 0 .976.426.976.95v1.753c0 .525-.437.95-.976.95a.964.964 0 01-.976-.95v-1.752c0-.525.437-.951.976-.951zM7.635 5.087c-1.05.102-1.935.438-2.385.906-.975 1.037-.765 3.668-.21 4.224.405.394 1.17.657 1.995.657h.09c.649-.013 1.785-.176 2.73-1.11.435-.41.705-1.433.675-2.47-.03-.834-.27-1.52-.63-1.813-.39-.336-1.275-.482-2.265-.394zm6.465.394c-.36.292-.6.98-.63 1.813-.03 1.037.24 2.06.675 2.47.968.957 2.136 1.104 2.776 1.11h.044c.825 0 1.59-.263 1.995-.657.555-.556.765-3.187-.21-4.224-.45-.468-1.335-.804-2.385-.906-.99-.088-1.875.058-2.265.394zM12 7.615c-.24 0-.525.015-.84.044.03.16.045.336.06.526l-.001.159a2.94 2.94 0 01-.014.25c.225-.022.425-.027.612-.028h.366c.187 0 .387.006.612.028-.015-.146-.015-.277-.015-.409.015-.19.03-.365.06-.526a9.29 9.29 0 00-.84-.044z",
  opencode: "M16 6H8v12h8V6zm4 16H4V2h16v20z",
  cursor: "M22.106 5.68L12.5.135a.998.998 0 00-.998 0L1.893 5.68a.84.84 0 00-.419.726v11.186c0 .3.16.577.42.727l9.607 5.547a.999.999 0 00.998 0l9.608-5.547a.84.84 0 00.42-.727V6.407a.84.84 0 00-.42-.726zm-.603 1.176L12.228 22.92c-.063.108-.228.064-.228-.061V12.34a.59.59 0 00-.295-.51l-9.11-5.26c-.107-.062-.063-.228.062-.228h18.55c.264 0 .428.286.296.514z",
  goose: "M21.595 23.61c1.167-.254 2.405-.944 2.405-.944l-2.167-1.784a12.124 12.124 0 01-2.695-3.131 12.127 12.127 0 00-3.97-4.049l-.794-.462a1.115 1.115 0 01-.488-.815.844.844 0 01.154-.575c.413-.582 2.548-3.115 2.94-3.44.503-.416 1.065-.762 1.586-1.159.074-.056.148-.112.221-.17.003-.002.007-.004.009-.007.167-.131.325-.272.45-.438.453-.524.563-.988.59-1.193-.061-.197-.244-.639-.753-1.148.319.02.705.272 1.056.569.235-.376.481-.773.727-1.171.165-.266-.08-.465-.086-.471h-.001V3.22c-.007-.007-.206-.25-.471-.086-.567.35-1.134.702-1.639 1.021 0 0-.597-.012-1.305.599a2.464 2.464 0 00-.438.45l-.007.009c-.058.072-.114.147-.17.221-.397.521-.743 1.083-1.16 1.587-.323.391-2.857 2.526-3.44 2.94a.842.842 0 01-.574.153 1.115 1.115 0 01-.815-.488l-.462-.794a12.123 12.123 0 00-4.049-3.97 12.133 12.133 0 01-3.13-2.695L1.332 0S.643 1.238.39 2.405c.352.428 1.27 1.49 2.34 2.302C1.58 4.167.73 3.75.06 3.4c-.103.765-.063 1.92.043 2.816.726.317 1.961.806 3.219 1.066-1.006.236-2.11.278-2.961.262.15.554.358 1.119.64 1.688.119.263.25.52.39.77.452.125 2.222.383 3.164.171l-2.51.897a27.776 27.776 0 002.544 2.726c2.031-1.092 2.494-1.241 4.018-2.238-2.467 2.008-3.108 2.828-3.8 3.67l-.483.678c-.25.351-.469.725-.65 1.117-.61 1.31-1.47 4.1-1.47 4.1-.154.486.202.842.674.674 0 0 2.79-.861 4.1-1.47.392-.182.766-.4 1.118-.65l.677-.483c.227-.187.453-.37.701-.586 0 0 1.705 2.02 3.458 3.349l.896-2.511c-.211.942.046 2.712.17 3.163.252.142.509.272.772.392.569.28 1.134.49 1.688.64-.016-.853.026-1.956.261-2.962.26 1.258.75 2.493 1.067 3.219.895.106 2.051.146 2.816.043a73.87 73.87 0 01-1.308-2.67c.811 1.07 1.874 1.988 2.302 2.34h-.001z"
};
const iconURI = d => "data:image/svg+xml," + encodeURIComponent(
  '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="#000"><path d="' + d + '"/></svg>');
const HARNESS = {
  claude:{code:"CL",name:"Claude"}, codex:{code:"CX",name:"Codex"},
  pi:{code:"PI",name:"Pi"},
  gemini:{code:"GE",name:"Gemini"}, copilot:{code:"CP",name:"Copilot"},
  opencode:{code:"OC",name:"OpenCode"}, cursor:{code:"CU",name:"Cursor"},
  goose:{code:"GO",name:"Goose"}, droid:{code:"DR",name:"Droid"}
};
for(const k in HARNESS){ if(ICON_PATH[k]) HARNESS[k].icon = iconURI(ICON_PATH[k]); }

/* One badge encoding for both states, and the difference is not carried by
   colour alone: "has data" is a tinted tile behind a solid edge, "no data" is a
   dashed edge over nothing. A filled-vs-outlined pair at this size read as the
   same weight, which is how a strip of nine badges became unreadable. */
function badge(key, active, name, tipSuffix){
  const h = own(HARNESS, key, null) ||
    {code:String(key||"?").slice(0,2).toUpperCase(), name:key};
  const label = name || h.name;
  const tileStyle = active
    ? "background:color-mix(in oklab,var(--accent) 22%,transparent);" +
      "border:1px solid color-mix(in oklab,var(--accent) 48%,transparent)"
    : "border:1px dashed var(--line2)";
  const on = active ? "var(--ink)" : "var(--ink3)";
  const inner = h.icon
    ? `<span class="bico" style="background:${on};-webkit-mask:url('${h.icon}') center/contain no-repeat;mask:url('${h.icon}') center/contain no-repeat"></span>`
    : `<span class="bmono" style="color:${on}">${esc(h.code)}</span>`;
  return `<span class="hbadge"><span class="btile" style="${tileStyle}">${inner}</span>` +
         `<span class="htip">${esc(label)}${esc(tipSuffix || "")}</span></span>`;
}

function harnessStrip(harnesses){
  if(!harnesses || !harnesses.length) return "";
  const chips = harnesses.map(h => {
    const healthy = h.discovered && !h.error;
    const suffix = h.error ? " — collector error" : (h.discovered ? "" : " — no data");
    return badge(h.key, healthy, h.label, suffix);
  }).join("");
  return `<span class="hstrip-k">harnesses</span>${chips}`;
}

function rateTile(d){
  const rate = d.summary.rate_per_min || 0;
  const total = (isFinite(rate) ? rate : 0).toLocaleString();
  const byH = {};
  for(const x of d.sessions){
    if(x.active && x.rate_per_min && isFinite(x.rate_per_min)){
      byH[x.harness] = (byH[x.harness]||0) + x.rate_per_min;
    }
  }
  const shown = (d.harnesses || []).filter(h => h.discovered)
    .map(h => ({key:h.key, v:byH[h.key] || 0}))
    .sort((a,b) => b.v - a.v).slice(0,5);
  const max = Math.max(1, ...shown.map(r => r.v));
  const rows = shown.length ? `<div class="rate-rows">` + shown.map(r => {
    const v = isFinite(r.v) ? r.v : 0;
    const pct = Math.max(v ? 4 : 0, Math.round(v * 100 / max));
    return `<div class="rrow"><span class="rrow-badge">${badge(r.key, true)}</span>` +
      `<span class="rrow-bar"><span class="rrow-fill" style="width:${pct}%"></span></span>` +
      `<span class="rrow-v">${v.toLocaleString()}</span></div>`;
  }).join("") + `</div>` : "";
  return `<div class="tile"><div class="tile-top"><span class="tile-label">Output rate</span>` +
    `<span class="tile-cap">tok / min · 10 min</span></div>` +
    `<div class="tile-val">${total}</div>${heroSpark()}${rows}</div>`;
}

/* The grid height-matches the two count tiles to the rate tile beside them,
   which left each with a big empty box under a single numeral. Spend it on the
   per-harness split of the very sessions the numeral counted — derived from the
   same list, so the breakdown can never disagree with the total. */
function countTile(label, sub, sessions, alert){
  const byH = new Map();
  for(const x of sessions) byH.set(x.harness, (byH.get(x.harness) || 0) + 1);
  const rows = Array.from(byH.entries())
    .sort((a, b) => b[1] - a[1] || (a[0] < b[0] ? -1 : 1))
    .slice(0, 4)
    .map(([key, n]) => {
      const name = own(HARNESS, key, {}).name || key;
      return `<div class="tile-brow">${badge(key, true)}` +
        `<span class="tile-bname">${esc(name)}</span>` +
        `<span class="tile-bnum">${n}</span></div>`;
    }).join("");
  const body = rows
    ? `<div class="tile-break">${rows}</div>`
    : `<div class="tile-none">${esc(sub.empty)}</div>`;
  const val = sessions.length && alert
    ? `<div class="tile-val alert">${sessions.length}</div>`
    : `<div class="tile-val">${sessions.length}</div>`;
  return `<div class="tile"><div class="tile-label">${esc(label)}</div>${val}` +
    `<div class="tile-sub">${esc(sub.line)}</div>${body}</div>`;
}

function sdWindow(stages, idx){
  if(stages.length <= 6 || idx < 0) return stages.slice(0, 6);
  const lo = Math.max(0, idx - 2), hi = Math.min(stages.length, idx + 3);
  const out = [];
  if(lo > 0){ out.push(stages[0]); if(lo > 1) out.push(null); }
  for(let k = lo; k < hi; k++) out.push(stages[k]);
  if(hi < stages.length){ if(hi < stages.length - 1) out.push(null); out.push(stages[stages.length - 1]); }
  return out;
}

const SD_SLUG_MAX = 22;   // matches the .sd-ent column width, in mono ch
const SD_SLUG_HEAD = 8;   // enough to tell one workflow's entities from another's

// Elide the MIDDLE of an over-long entity slug, never the tail. Entity slugs
// within a workflow share a long prefix and differ only at the end
// (`datarecce-recce-cloud-infra-pr-1573` vs `…-pr-1587`), so tail truncation
// renders two different entities as the same string.
function sdSlug(slug){
  if(slug.length <= SD_SLUG_MAX) return slug;
  const tail = SD_SLUG_MAX - SD_SLUG_HEAD - 1;
  return slug.slice(0, SD_SLUG_HEAD) + "…" + slug.slice(slug.length - tail);
}

function sdBlock(sess){
  const sd = sess.spacedock;
  if(!sd) return "";
  const wfs = sd.workflows || [];
  const role = sd.role === "first-officer" ? "first officer" : sd.role;
  if(!wfs.length){
    return `<div class="sd"><div><span class="sd-k">spacedock</span>` +
      `<span class="sd-role">${esc(role)}</span></div></div>`;
  }
  let rows = "";
  for(const wf of wfs){
    const stages = wf.stages || [];
    for(const ent of (wf.entities || [])){
      const idx = stages.indexOf(ent.stage);
      const spine = sdWindow(stages, idx).map(s => s === null
        ? `<span class="sd-gap">…</span>`
        : `<span class="${s === ent.stage && idx >= 0 ? "sd-cur" : "sd-st"}">${esc(s)}</span>`
      ).join(`<span class="sd-arr">→</span>`);
      rows += `<div class="sd-row"><span class="sd-ent${ent.live ? " sd-live" : ""}"` +
        ` title="${esc(ent.slug)}">${esc(sdSlug(ent.slug))}</span>` +
        (ent.cycle ? `<span class="sd-cyc">${esc(ent.cycle)}</span>` : "") +
        `<span class="sd-spine">${spine}</span></div>`;
    }
  }
  const names = wfs.map(w => w.workflow).join(" · ");
  return `<div class="sd"><div><span class="sd-k">spacedock ${esc(names)}</span>` +
    `<span class="sd-role">${esc(role)}</span></div>${rows}</div>`;
}

function turnBlock(t){
  if(!t) return "";
  const warn = t.long ? `<span class="lwarn" tabindex="0" role="note"` +
    ` aria-label="${LONG_TURN_NOTE}">!` +
    `<span class="ltip">${LONG_TURN_NOTE}</span></span>` : "";
  const pct = (t.pct != null) ? `<span class="pct">${t.pct}%</span>` : "";
  /* Both shapes draw a track. A turn with no estimate used to drop the bar
     entirely, so two cards stacked in the same column had different anatomy and
     the reader had to work out which part was missing rather than reading it. */
  const bar = (t.pct != null)
    ? `<div class="turnbar"><span class="turnfill" style="width:${t.pct}%"></span></div>`
    : `<div class="turnbar" title="No past turn ran this long, so there is nothing` +
      ` to estimate against."><span class="turnfill indeterminate"></span></div>`;
  const eta = t.eta_h ? `~${esc(t.eta_h)} left (est)` : "running longer than recent turns";
  return `<div class="turn"><div class="turn-row">` +
    `<span class="turn-txt">this request · ${esc(t.elapsed_h)} elapsed · ${eta}</span>` +
    `<span class="turn-right">${warn}${pct}</span></div>${bar}</div>`;
}

/* Silent when the session tracks no tasks. The board already states once, above
   the fold, that nothing on it uses tracked tasks; repeating the negative on
   every card was a line of chrome per card that told the reader nothing. */
function taskBlock(sess){
  if(!sess.tasks || !sess.tasks.length) return "";
  const order = {in_progress:0, pending:1, completed:2};
  const STATUS = {in_progress:"In progress", pending:"Pending", completed:"Completed"};
  const tasks = [...sess.tasks].sort((a,b) => (order[a.status] ?? 3) - (order[b.status] ?? 3));
  const rows = tasks.map(t => {
    const af = (t.status === "in_progress" && t.activeForm) ? `<div class="task-af">${esc(t.activeForm)}…</div>` : "";
    return `<div class="task"><span class="tstatus st-${esc(t.status)}">${STATUS[t.status] || esc(t.status)}</span>` +
      `<div class="task-body"><div class="task-subj">${esc(t.subject)}</div>${af}</div>` +
      `<div class="task-when">${esc(t.elapsed_h || "")}<br>${esc(t.updated_ago || "")}</div></div>`;
  }).join("");
  return `<div class="tasks">${rows}</div>`;
}

function workingCard(d, sess){
  const hist = sessRateHistory.get(sessKey(sess));
  const spark = (hist && hist.length > 1)
    ? `<span class="rate-spark" title="${(sess.rate_per_min || 0).toLocaleString()}` +
      ` tok/min · trailing 5 min">` +
      sparkSVG(hist, nowSec(), 84, 26, false) + `</span>`
    : "";
  const rateMeter = (sess.active && sess.rate_per_min)
    ? `<div class="rate-meter"><div class="rate-flex">${spark}` +
      `<div><div class="rate-num">${sess.rate_per_min.toLocaleString()}</div>` +
      `<div class="rate-lab">tok / min</div></div></div>` +
      `<div class="rate-track"><span class="rate-live"></span></div></div>`
    : "";
  const bits = [];
  if(sess.total) bits.push(`${sess.done}/${sess.total} done · ${sess.progress_pct}%`);
  if(sess.eta_h) bits.push(`~${sess.eta_h} left`);
  const bitsLine = bits.length ? `<div class="card-bits">${esc(bits.join(" · "))}</div>` : "";
  const subs = (sess.subagents && sess.subagents.length)
    ? `<div class="subs"><span class="subs-k">subagents</span>` +
      sess.subagents.slice(0,6).map(a => `<span class="subpill"><span class="subdot"></span>${esc(a)}</span>`).join("") +
      (sess.subagents.length > 6 ? `<span class="subs-k">+${sess.subagents.length-6} more</span>` : "") +
      `</div>`
    : "";
  return `<div class="card"><div class="card-top"><div class="card-main">` +
    `<div class="card-headrow"><span class="pill pill-work"><span class="pill-dot"></span>Working</span>` +
    badge(sess.harness, true) + `</div>` +
    `<div class="card-title">${esc(sess.title || sess.project)}</div>` +
    `<div class="card-meta">${esc(sess.project)} · ${esc(sess.session)}</div>${bitsLine}` +
    `</div>${rateMeter}</div>` +
    `<div class="now"><span class="now-k">now</span>` +
    `<span title="${esc(sess.state_detail)}">${esc(humanTool(sess.state_detail))}</span></div>` +
    turnBlock(sess.turn) + subs + sdBlock(sess) + taskBlock(sess) + `</div>`;
}

function needRow(d, sess){
  const blocked = fmtDur(d.generated - (sess.blocked_since || sess.last_activity));
  return `<div class="need"><div style="min-width:0">` +
    `<div class="need-meta">${badge(sess.harness, true)}${esc(sess.project)} · ${esc(sess.session)}</div>` +
    `<div class="need-title">${esc(sess.title || sess.last_prompt || sess.project)}</div>` +
    `<div class="need-detail" title="${esc(sess.state_detail)}">` +
    `${esc(humanTool(sess.state_detail))}</div></div>` +
    `<div style="flex:none"><div class="blocked-k">blocked</div><div class="blocked-v">${esc(blocked)}</div></div></div>`;
}

function idleRow(d, sess){
  const age = fmtDur(d.generated - sess.last_activity);
  const t = sess.total ? ` · ${sess.done}/${sess.total}` : "";
  return `<div class="idle-row"><span class="idle-dot"></span>${badge(sess.harness, false)}` +
    `<span class="idle-title">${esc(sess.title || sess.last_prompt || sess.project)}</span>` +
    `<span class="idle-proj">${esc(sess.project)} · ${esc(sess.session)}${t}</span>` +
    `<span class="idle-age">idle ${esc(age)}</span></div>`;
}

function toggleIdle(){ idleExpanded = !idleExpanded; if(lastData) render(lastData); }

/* ── calm mode ─────────────────────────────────────────────────────────────
   A second display of the same payload: one dense ledger row per session
   instead of a stack of cards. Every value it shows is derived from
   /api/data, so the two modes cannot disagree about what a session is
   doing. The switch is remembered in localStorage and bound to `c`. */
const DISPLAY_MODE_KEY = "cargento.displayMode";
const CALM_STALE_SEC = 7200;   // an idle session quiet this long is flagged "stale"

let displayMode = "regular";
try{
  const saved = localStorage.getItem(DISPLAY_MODE_KEY);
  if(saved === "calm" || saved === "regular") displayMode = saved;
}catch(e){ /* private mode, or a context with no storage — regular it is */ }

let calmSort = "attention";   /* attention | recent | repo */
let calmStateOnly = null;     /* needs | work | idle */
let calmFlagOnly = false;
/* Rows are identified by sessKey(), the same (harness, sid) pair the rate
   buffers and the notification map use — dedupe_sessions keys on that pair, so
   a bare sid is not unique across harnesses. */
let calmOpenKey = null;       /* the one expanded row */
let calmCursorKey = null;     /* keyboard cursor */
let calmCopyNote = null;      /* {key, text} — transient label after copy id */
let calmScrollTop = 0;        /* ledger scroll survives the 5s re-render */
let calmRevealFocus = false;  /* scroll the cursor into view after this render */
let calmResetScroll = false;  /* re-filtered: the next render starts at the top */

function setDisplayMode(mode){
  if(mode !== "calm" && mode !== "regular" || mode === displayMode) return;
  displayMode = mode;
  try{ localStorage.setItem(DISPLAY_MODE_KEY, mode); }catch(e){ /* nothing to persist to */ }
  calmResetScroll = true;
  if(lastData) render(lastData);
}

/* ── usage band ────────────────────────────────────────────────────────────
   Quota per harness, in both display modes. Everything here renders only when
   the payload carries a `usage` array — no server sends one yet, so the whole
   surface stays dormant until the collectors publish it (Codex from disk
   first, then the Claude fetcher). One entry per harness:
     {harness,                       // key into HARNESS, like a session's
      state,                        // "ok" | "expired"
      asOf,                         // epoch seconds of the snapshot or fetch
      fiveH: {pct, reset},          // integer percent, short reset text
      week:  {pct, reset},
      burn, today, cost}            // optional extras, preformatted strings
   The disclosure modal is likewise gated: it opens once, the first time a
   payload carries `usage_fetch` — the quota fetcher's capability flag, which
   ships with the fetcher itself. */
const USAGE_OPEN_KEY = "cargento.usageOpen";        /* calm band visibility */
const USAGE_CFG_KEY = "cargento.usageCfg";          /* which stats are shown */
const USAGE_ENABLED_KEY = "cargento.usageEnabled";  /* the feature switch */
const USAGE_MODAL_KEY = "cargento.usageModalSeen";
const USAGE_STATS = [
  ["fiveH", "5h window"], ["week", "weekly window"], ["burn", "burn rate"],
  ["today", "tokens today"], ["cost", "cost today"]];

let usageOpen = true;
let usageEnabled = true;
let usageModalSeen = false;
let usageCfgOpen = false;   /* the popover is transient, never persisted */
let usageCfg = {fiveH: true, week: true, burn: false, today: false, cost: false};
try{
  if(localStorage.getItem(USAGE_OPEN_KEY) === "0") usageOpen = false;
  if(localStorage.getItem(USAGE_ENABLED_KEY) === "0") usageEnabled = false;
  if(localStorage.getItem(USAGE_MODAL_KEY) === "1") usageModalSeen = true;
  const savedCfg = JSON.parse(localStorage.getItem(USAGE_CFG_KEY));
  /* A torn or all-false value would blank every window; only adopt a saved
     config that still shows at least one stat. */
  if(savedCfg && typeof savedCfg === "object" &&
     USAGE_STATS.some(([k]) => savedCfg[k] === true)){
    for(const [k] of USAGE_STATS) usageCfg[k] = savedCfg[k] === true;
  }
}catch(e){ /* private mode, or a context with no storage — defaults hold */ }

function usagePresent(d){ return !!d && Array.isArray(d.usage); }

function usageStore(key, val){
  try{ localStorage.setItem(key, val); }catch(e){ /* nothing to persist to */ }
}

/* The same thresholds both design comps use: 90 is "act now", 70 is "worth a
   look", mapped onto the board's existing flag tones. */
function usageTone(pct){
  if(pct >= 90) return {ink: "var(--alert)", bar: "var(--alert)"};
  if(pct >= 70) return {ink: "var(--warnink)", bar: "var(--warn)"};
  return {ink: "var(--ink2)", bar: "var(--line2)"};
}

/* Every figure carries the moment it was true. A Codex snapshot is only as
   fresh as the last active turn, and a cached fetch is older than the page —
   a percentage with no timestamp would claim to be live. A bare time only
   says "today", so any older snapshot names its day, and past a week the
   date: "as of 05:29 PM" from four days ago is a lie of omission. */
function usageAsOf(u){
  const t = Number(u.asOf);
  if(!isFinite(t) || t <= 0) return "";
  const then = new Date(t*1000);
  const ref = new Date();
  const time = then.toLocaleTimeString([], {hour: "2-digit", minute: "2-digit"});
  if(then.toDateString() === ref.toDateString()) return "as of " + time;
  if(ref - then < 6*86400*1000){
    return "as of " + then.toLocaleDateString([], {weekday: "short"}) + " " + time;
  }
  return "as of " + then.toLocaleDateString([], {month: "short", day: "numeric"});
}

function usageEntry(u){
  const h = own(HARNESS, u.harness, null) ||
    {code: String(u.harness || "?").slice(0, 2).toUpperCase(), name: u.harness};
  const ico = h.icon
    ? `<span class="cm-ico" style="-webkit-mask:url('${h.icon}') center/contain no-repeat;` +
      `mask:url('${h.icon}') center/contain no-repeat"></span>`
    : `<span class="cm-icot">${esc(h.code)}</span>`;
  const head = `<div class="u-hrow"><span class="cm-hcell">${ico}</span>` +
    `<span class="u-hname" title="${esc(h.name || u.harness)}">${esc(h.name || u.harness)}</span></div>`;
  /* An expired token shows no numbers at all: stale figures presented next to
     live ones read as live. The remedy belongs to the harness, so the note
     points there — Cargento never refreshes a token. */
  if(u.state === "expired"){
    return `<div class="u-entry">${head}` +
      `<div class="u-expired"><span class="u-excl" role="img" aria-label="attention">!</span>` +
      `<span>token expired — sign in again in ${esc(h.name || u.harness)}</span></div></div>`;
  }
  const win = (label, w) => {
    if(!w || w.pct == null) return "";
    const pct = Math.max(0, Math.min(100, Math.round(Number(w.pct) || 0)));
    const tone = usageTone(pct);
    return `<div class="u-wrow"><span class="u-wlab">${label}</span>` +
      `<span class="cm-track"><span class="cm-fill" style="width:${pct}%;` +
      `background:${tone.bar}"></span></span>` +
      `<span class="u-pct" style="color:${tone.ink}">${pct}%</span>` +
      `<span class="u-reset" title="${esc(String(w.reset || ""))}">↺ ${esc(String(w.reset || "—"))}</span></div>`;
  };
  const wins = (usageCfg.fiveH ? win("5h", u.fiveH) : "") +
    (usageCfg.week ? win("wk", u.week) : "");
  const extras = [];
  if(usageCfg.burn && u.burn != null) extras.push(["burn", u.burn]);
  if(usageCfg.today && u.today != null) extras.push(["today", u.today]);
  if(usageCfg.cost && u.cost != null) extras.push(["cost", u.cost]);
  const asOf = usageAsOf(u);
  const tail = (extras.length || asOf)
    ? `<div class="u-extras">` +
      extras.map(([k, v]) => `<span>${k} <b>${esc(String(v))}</b></span>`).join("") +
      (asOf ? `<span class="u-asof">${esc(asOf)}</span>` : "") + `</div>`
    : "";
  return `<div class="u-entry">${head}${wins}${tail}</div>`;
}

function usageCfgPop(){
  if(!usageCfgOpen) return "";
  const shown = USAGE_STATS.filter(([k]) => usageCfg[k]).length;
  /* The master switch is the modal's off switch, reachable again later — the
     way back the disclosure promises. It is not part of the stats group and
     never locks. */
  const master = `<button type="button" class="u-cfg-row" data-calm="uon"` +
    ` aria-pressed="${usageEnabled}">` +
    `<span class="u-cfg-box${usageEnabled ? " on" : ""}">${usageEnabled ? "✓" : ""}</span>` +
    `usage on</button>`;
  const rows = USAGE_STATS.map(([k, label]) => {
    /* The last shown stat cannot be unchecked: a band with every stat hidden
       is indistinguishable from a broken one. */
    const locked = usageCfg[k] && shown <= 1;
    return `<button type="button" class="u-cfg-row${locked ? " locked" : ""}"` +
      ` data-calm="ustat" data-arg="${k}" aria-pressed="${!!usageCfg[k]}"` +
      `${locked ? ' aria-disabled="true"' : ""}>` +
      `<span class="u-cfg-box${usageCfg[k] ? " on" : ""}${locked ? " locked" : ""}">` +
      `${usageCfg[k] ? "✓" : ""}</span>${esc(label)}</button>`;
  }).join("");
  return `<div class="u-cfg"><span class="u-cfg-k">usage</span>${master}` +
    `<span class="u-cfg-k">show stats</span>${rows}</div>`;
}

function usageBody(d){
  if(!usageEnabled){
    return `<div class="u-note">usage is off — turn it back on under configure</div>`;
  }
  if(!d.usage.length){
    return `<div class="u-note">No quota data yet. Harnesses that publish usage will appear here.</div>`;
  }
  return `<div class="u-grid">${d.usage.map(usageEntry).join("")}</div>`;
}

function usageSectionRegular(d){
  if(!usagePresent(d)) return "";
  return `<div class="usec"><div class="sec"><span class="sec-k">Usage · rate limits</span>` +
    `<span class="sec-rule"></span>` +
    `<button type="button" class="u-link${usageCfgOpen ? " on" : ""}" data-calm="ucfg"` +
    ` aria-expanded="${usageCfgOpen}">configure ▾</button></div>` +
    `<div class="u-panel">${usageBody(d)}</div>${usageCfgPop()}</div>`;
}

function usageBandCalm(d){
  if(!usagePresent(d) || !usageOpen) return "";
  return `<div class="u-band"><div class="u-band-head">` +
    `<span class="cm-k">usage · rate limits per harness</span><span class="cm-sp"></span>` +
    `<button type="button" class="u-link${usageCfgOpen ? " on" : ""}" data-calm="ucfg"` +
    ` aria-expanded="${usageCfgOpen}">configure ▾</button></div>` +
    usageBody(d) + usageCfgPop() + `</div>`;
}

/* First-run disclosure. The copy quotes the security contract
   (docs/plans/quota-fetch-security-scope.md, promoted to SECURITY.md with the
   fetcher) — it must not promise anything the contract does not say. */
function usageModal(d){
  if(!usagePresent(d) || !d.usage_fetch || usageModalSeen) return "";
  return `<div class="u-overlay" role="dialog" aria-modal="true"` +
    ` aria-label="usage disclosure"><div class="u-modal">` +
    `<div class="u-modal-h">Show usage and rate limits?</div>` +
    `<p class="u-modal-p">Cargento can fetch each vendor's quota so the dashboard` +
    ` shows how much of the 5-hour and weekly windows is used, and when they reset.</p>` +
    `<p class="u-modal-p">What is sent: the vendor's own OAuth access token, and` +
    ` nothing else. No transcript content, no prompts, no paths, no project names,` +
    ` no machine identifiers. What comes back is quota numbers. Session data never` +
    ` appears in either direction. The token is never refreshed, never written,` +
    ` never logged, and never served.</p>` +
    `<p class="u-modal-p">Usage is on by default. Turn it off here and nothing is` +
    ` fetched; turn it back on any time under configure.</p>` +
    `<div class="u-modal-acts">` +
    `<button type="button" class="u-primary" data-calm="umodal" data-arg="on">Keep usage on</button>` +
    `<button type="button" class="u-act" data-calm="umodal" data-arg="off">Turn it off</button>` +
    `</div></div></div>`;
}

function usageAction(act, arg){
  if(act === "usage"){
    usageOpen = !usageOpen; usageCfgOpen = false;
    usageStore(USAGE_OPEN_KEY, usageOpen ? "1" : "0");
  } else if(act === "ucfg"){
    usageCfgOpen = !usageCfgOpen;
  } else if(act === "uon"){
    usageEnabled = !usageEnabled;
    usageStore(USAGE_ENABLED_KEY, usageEnabled ? "1" : "0");
  } else if(act === "ustat"){
    if(!Object.prototype.hasOwnProperty.call(usageCfg, arg)) return true;
    const shown = USAGE_STATS.filter(([k]) => usageCfg[k]).length;
    if(usageCfg[arg] && shown <= 1) return true;  /* the last stat stays */
    usageCfg[arg] = !usageCfg[arg];
    usageStore(USAGE_CFG_KEY, JSON.stringify(usageCfg));
  } else if(act === "umodal"){
    usageModalSeen = true;
    usageStore(USAGE_MODAL_KEY, "1");
    if(arg === "off"){
      usageEnabled = false;
      usageStore(USAGE_ENABLED_KEY, "0");
    }
  } else return false;
  if(lastData) render(lastData);
  return true;
}

/* ── stopping the server from the page ─────────────────────────────────────
   Two clicks, because the page cannot undo a stop and the header is a place
   people click. `stopArmed` is a module variable for the documented reason:
   #app is rebuilt every five seconds, so state that is not reapplied after
   the swap is state the refresh eats — and a button that disarmed itself on
   the next poll would flicker under the reader's cursor. */
let stopArmed = false;
let stopError = "";
let serverStopped = false;
let stopFocusPending = false;

function stopControl(){
  const note = stopError ? `<span class="stopnote">${esc(stopError)}</span>` : "";
  return `<button type="button" id="stop-control"` +
    ` class="stopbtn${stopArmed ? " armed" : ""}"` +
    ` data-calm="stop" aria-pressed="${stopArmed}"` +
    ` title="Stop the Cargento server. Two clicks — this cannot be undone from the page.">` +
    (stopArmed ? "stop — sure?" : "stop") + `</button>` + note;
}

function restoreStopFocus(){
  if(!stopFocusPending) return;
  stopFocusPending = false;
  const button = document.getElementById("stop-control");
  if(button && button.focus) button.focus();
}

function disarmStop(){
  if(!stopArmed && !stopError) return false;
  stopArmed = false; stopError = ""; stopFocusPending = false;
  return true;
}

async function requestStop(){
  stopArmed = false; stopFocusPending = false;
  try{
    const r = await fetch("/api/shutdown", {method: "POST"});
    if(!r.ok) throw new Error("status " + r.status);
  }catch(e){
    /* Still running, so the page must not claim otherwise. */
    stopError = "stop failed";
    if(lastData) render(lastData);
    return;
  }
  /* Clearing the error matters even though the panel replaces the note: a
     lingering stopError keeps disarmStop() answering true forever, so every
     later click reports a disarm that disarmed nothing. */
  stopError = "";
  serverStopped = true;
  renderStopped();
}

function renderStopped(){
  /* Not the "stalled" banner: nothing is retrying, nothing is coming back,
     and the reader is the one who ended it. */
  if(refreshTimer !== null){ clearInterval(refreshTimer); refreshTimer = null; }
  document.title = "Cargento — stopped";
  const app = document.getElementById("app");
  if(!app) return;
  app.className = "wrap";
  app.innerHTML = `<div class="stopped"><div class="stopped-h">Cargento stopped.</div>` +
    `<div class="stopped-p">The server is no longer running, so this page will not ` +
    `update. Ask your agent to open Cargento again to restart it.</div></div>`;
}

function modeBar(){
  const btn = k => `<button type="button" class="modebtn${displayMode === k ? " on" : ""}"` +
    ` data-calm="mode" data-arg="${k}" aria-pressed="${displayMode === k}">${k}</button>`;
  /* `stop` is past a divider on purpose. Two of these three buttons swap a view
     and the third ends the server, and sitting them in one undifferentiated
     group put an irreversible action one slip away from a display toggle. */
  return `<div class="modebar"><span class="modebar-k">display</span>` +
    `<div class="modeseg" role="group" aria-label="display mode">` +
    btn("regular") + btn("calm") + `</div>` +
    `<span class="modebar-split" aria-hidden="true"></span>` + stopControl() + `</div>`;
}

/* Two flag tones, and only signals the payload actually carries: --alert for
   "you are the blocker", --warn for "worth a look", neither for "gone quiet".
   The fixture's stalled/failed flags have no server-side detector, so calm
   mode does not invent them. */
const CALM_TONE = {
  attn: {rank:0, ink:"var(--alert)",
         bg:"color-mix(in oklab,var(--alert) 13%,transparent)",
         bd:"color-mix(in oklab,var(--alert) 34%,transparent)"},
  warn: {rank:1, ink:"var(--warnink)",
         bg:"color-mix(in oklab,var(--warn) 26%,transparent)",
         bd:"color-mix(in oklab,var(--warn) 42%,transparent)"},
  /* A real chip, not grey text on a grey row. `stale` is the quietest of the
     three flags but it is still a flag, and rendering it at --ink3 with a
     hairline border made it disappear into the column it sits in. */
  quiet:{rank:3, ink:"var(--ink2)",
         bg:"color-mix(in oklab,var(--ink3) 14%,transparent)",
         bd:"var(--line2)"}
};
/* The footer legend is generated from the same table the row chips use, and its
   labels are the chip labels verbatim. It used to paraphrase them — "you are the
   blocker" for a chip that reads `your call` — so the legend described flags the
   reader could not find on any row. */
const CALM_FLAG_LEGEND = [
  {label:"your call", tone:"attn"},
  {label:"long turn", tone:"warn"},
  {label:"stale", tone:"quiet"}
];
const CALM_RAIL = {needs:"var(--alert)", work:"var(--accent)", idle:"var(--line2)"};
const CALM_TASK = {
  in_progress:{glyph:"▸", ink:"var(--accent-ink)", text:"var(--ink)"},
  pending:    {glyph:"·", ink:"var(--ink3)",       text:"var(--ink3)"},
  completed:  {glyph:"✓", ink:"var(--accent-ink)", text:"var(--ink3)"}
};
const CALM_TASK_ORDER = {in_progress:0, pending:1, completed:2};

/* These tables are indexed by strings that come out of the payload, and every
   plain object inherits truthy `constructor`, `toString` and friends from
   Object.prototype — enough to sail straight past an `||` or `??` fallback and
   render `undefined` as a glyph and as a colour. Ask for own properties only. */
function own(table, key, fallback){
  return Object.prototype.hasOwnProperty.call(table, key) ? table[key] : fallback;
}

/* One ledger row per session. Every session lands in exactly one of the three
   buckets — a ledger that silently drops a row is worse than useless. */
function calmRow(d, x){
  const st = x.state === "needs_input" ? "needs" : (x.state === "working" ? "work" : "idle");
  const ageSec = Math.max(0, d.generated - (x.last_activity || 0));
  const waitSec = Math.max(0, d.generated - (x.blocked_since || x.last_activity || 0));
  const turn = x.turn || null;
  let flag = null, tone = "quiet", why = "";
  if(st === "needs"){
    flag = "your call"; tone = "attn";
    why = "Blocked on you for " + fmtDur(waitSec) +
      " — nothing in this session moves until you answer.";
  } else if(st === "work" && turn && turn.long){
    flag = "long turn"; tone = "warn"; why = LONG_TURN_NOTE;
  } else if(st === "idle" && ageSec >= CALM_STALE_SEC){
    flag = "stale"; tone = "quiet";
    why = "No activity for " + fmtDur(ageSec) + ". Either it finished quietly and " +
      "nobody read the result, or it is waiting on a reply that never came.";
  }
  const title = x.title || x.last_prompt || x.project;
  const prompt = String(x.last_prompt || "").trim();
  const tasks = (x.tasks || []).slice().sort(
    (a, b) => own(CALM_TASK_ORDER, a.status, 3) - own(CALM_TASK_ORDER, b.status, 3));
  const taskDone = tasks.filter(t => t.status === "completed").length;
  const rate = x.rate_per_min || 0;
  return {
    key: sessKey(x), sid: x.sid,
    harness: x.harness, project: x.project, session: x.session,
    st, title, doing: humanTool(x.state_detail), doingRaw: x.state_detail,
    ageSec, waitSec, turn, flag, tone, why,
    sortAge: st === "work" ? 0 : ageSec,   /* see byAge — a working row's age is noise */
    rail: CALM_RAIL[st] || CALM_RAIL.idle,
    /* The prompt is only worth quoting when the title is not already it. */
    excerpt: (prompt && prompt !== String(title).trim()) ? prompt : "",
    tasks, taskNote: tasks.length ? taskDone + " of " + tasks.length + " done" : "",
    subagents: x.subagents || [], spacedock: x.spacedock || null,
    rank: flag ? CALM_TONE[tone].rank : (st === "work" ? 2 : 4),
    /* One column used to carry all three buckets' headline numbers under the
       single heading `signal` — tokens per minute on one row, hours idle on the
       next. A column whose unit changes per row cannot be compared down its own
       length, which is the only thing a ledger column is for. Two columns now,
       each with one unit: what this request is producing, and how long the
       session has been sitting still. Both are empty where they do not apply,
       and an empty cell reads as "not applicable" where a wrong unit does not. */
    rate: st === "work" ? (rate ? rate.toLocaleString() + " /m" : "—") : "",
    rateTip: st === "work"
      ? (rate ? rate.toLocaleString() + " tokens per minute" : "this harness reports no token rate")
      : "",
    quiet: st === "needs" ? fmtDur(waitSec) : (st === "idle" ? fmtDur(ageSec) : ""),
    quietTip: st === "needs" ? "blocked on you for " + fmtDur(waitSec)
      : (st === "idle" ? "no activity for " + fmtDur(ageSec) : ""),
    quietInk: st === "needs" ? "var(--alert)" : "var(--ink3)",
    titleInk: st === "idle" ? "var(--ink2)" : "var(--ink)",
    detailAge: st === "needs" ? "blocked " + fmtDur(waitSec)
      : (st === "work" ? "last event " + fmtDur(ageSec) + " ago" : "idle " + fmtDur(ageSec)),
    turnLine: turn ? turn.elapsed_h + " elapsed · " +
      (turn.eta_h ? "~" + turn.eta_h + " left (est)" : "running longer than recent turns") : ""
  };
}

function calmFilter(all){
  return all.filter(r => (!calmFlagOnly || !!r.flag) &&
                         (!calmStateOnly || r.st === calmStateOnly));
}

/* Ordering has to be STABLE across the 5s poll — a row that swaps places under
   the reader's cursor is worse than a row in the wrong place. Age is stable by
   construction everywhere it means something: it is a fixed per-session
   timestamp subtracted from one clock shared by the whole payload, so two idle
   rows keep their relative order forever. The exception is a WORKING row,
   whose last activity is always within WORKING_THRESHOLD_SEC of now — ordering
   those by age sorts on nothing but which one wrote most recently, which flips
   every poll. `sortAge` pins them level (see calmRow) and the session id, which
   never changes, breaks every remaining tie. This is the same call collect()
   makes server-side for the same reason. */
const bySid = (a, b) => (a.sid < b.sid ? -1 : (a.sid > b.sid ? 1 : 0));
const byAge = (a, b) => a.sortAge - b.sortAge || bySid(a, b);
const byRank = (a, b) => a.rank - b.rank || byAge(a, b);

/* Returns display entries: {row} for a session, {divider} for a repo heading. */
function calmEntries(shown){
  if(calmSort === "recent"){
    return shown.slice().sort(byAge).map(r => ({row: r}));
  }
  if(calmSort === "repo"){
    const by = new Map();
    for(const r of shown){
      if(!by.has(r.project)) by.set(r.project, []);
      by.get(r.project).push(r);
    }
    const out = [];
    for(const key of Array.from(by.keys()).sort()){
      const g = by.get(key).sort(byRank);
      out.push({divider: {label: key, count: g.length,
                          flagged: g.filter(r => r.flag).length}});
      for(const r of g) out.push({row: r});
    }
    return out;
  }
  return shown.slice().sort(byRank).map(r => ({row: r}));
}

/* The cursor falls back to the first row rather than being written back into
   calmCursorKey, so a re-sort moves the highlight without stranding state. */
function calmEffectiveFocus(order){
  if(calmCursorKey && order.some(r => r.key === calmCursorKey)) return calmCursorKey;
  return order.length ? order[0].key : null;
}

function calmOrder(d){
  return calmEntries(calmFilter(d.sessions.map(x => calmRow(d, x))))
    .filter(e => e.row).map(e => e.row);
}

function calmMove(step){
  if(!lastData) return;
  const order = calmOrder(lastData);
  if(!order.length) return;
  const i = order.findIndex(r => r.key === calmEffectiveFocus(order));
  calmCursorKey = order[Math.max(0, Math.min(order.length - 1, (i < 0 ? 0 : i + step)))].key;
  calmRevealFocus = true;
  render(lastData);
}

function calmCopyId(key){
  /* The row key identifies the row; the session id is what goes on the
     clipboard. Resolve one to the other rather than carrying both around. */
  const row = lastData ? lastData.sessions.find(x => sessKey(x) === key) : null;
  const sid = row ? row.sid : null;
  if(!sid) return;
  const note = text => {
    calmCopyNote = {key, text};
    if(lastData) render(lastData);
    setTimeout(() => {
      if(!calmCopyNote || calmCopyNote.key !== key) return;
      calmCopyNote = null;
      if(lastData) render(lastData);
    }, 1400);
  };
  const clip = (typeof navigator !== "undefined" && navigator.clipboard &&
                navigator.clipboard.writeText) ? navigator.clipboard.writeText(sid) : null;
  /* Never claim "copied" for a write the browser refused — an unfocused or
     non-secure context rejects, and a silent lie here costs a lost session id. */
  if(clip && typeof clip.then === "function") clip.then(() => note("copied"), () => note("blocked"));
  else note("blocked");
}

function calmAction(act, arg){
  if(act === "mode"){ setDisplayMode(arg); return; }
  if(usageAction(act, arg)) return;
  if(act === "stop"){
    if(!stopArmed){
      stopArmed = true; stopError = ""; stopFocusPending = true;
      if(lastData) render(lastData);
      return;
    }
    requestStop();
    return;
  }
  if(act === "copy"){ calmCopyId(arg); return; }
  if(act === "sort"){
    if(calmSort === arg) return;
    calmSort = arg; calmResetScroll = true;
  } else if(act === "state"){
    calmStateOnly = calmStateOnly === arg ? null : arg;
    calmOpenKey = null; calmCursorKey = null; calmResetScroll = true;
  } else if(act === "flag"){
    calmFlagOnly = !calmFlagOnly;
    calmOpenKey = null; calmCursorKey = null; calmResetScroll = true;
  } else if(act === "clear"){
    calmFlagOnly = false; calmStateOnly = null; calmResetScroll = true;
  } else if(act === "open"){
    calmOpenKey = calmOpenKey === arg ? null : arg;
    calmCursorKey = arg;
  } else return;
  if(lastData) render(lastData);
}

document.addEventListener("click", e => {
  const el = (e.target && e.target.closest) ? e.target.closest("[data-calm]") : null;
  if(!el){
    /* A click anywhere else is an answer: not that one. The configure popover
       reads the same answer — it floats over content, so a click on that
       content is a dismissal, not a miss. */
    let dirty = disarmStop();
    if(usageCfgOpen){ usageCfgOpen = false; dirty = true; }
    if(dirty && lastData) render(lastData);
    return;
  }
  /* So is a click on a different control. Otherwise the armed state outlives
     the moment the reader was answering for — sort the ledger, toggle a mode,
     come back later, and one click would stop the server with no confirmation
     at all, which is the whole thing the second click is here to prevent. */
  const act = el.getAttribute("data-calm");
  if(act !== "stop" && disarmStop() && lastData) render(lastData);
  calmAction(act, el.getAttribute("data-arg"));
});

document.addEventListener("keydown", e => {
  /* The stopped panel is terminal, and a shortcut must not act on it, swallow
     the key, or outlive it. The render() guard stops the paint but not the side
     effects on the way there: setDisplayMode writes localStorage *before* it
     paints, so `c` on the terminal panel appeared to do nothing while durably
     flipping the saved display mode for the next run. */
  if(serverStopped) return;
  if(e.metaKey || e.ctrlKey || e.altKey) return;
  const tag = e.target && e.target.tagName;
  if(tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT") return;
  const k = e.key;
  const stop = () => { if(e.preventDefault) e.preventDefault(); };
  /* The first activation rebuilds #app to show the armed label. Keep focus on
     its replacement and let Enter/Space reach the button's native click;
     disarming on keydown makes that generated click arm it all over again. */
  if(stopArmed && (k === "Enter" || k === " ") && e.target && e.target.closest &&
     e.target.closest('[data-calm="stop"]')) return;
  if(k === "Escape" && (stopArmed || stopError)){
    /* While armed, Escape answers the stop and does nothing else. */
    stop(); disarmStop(); if(lastData) render(lastData); return;
  }
  /* Every other keystroke answers it too. The keyboard drives the same controls
     the mouse does — `c` is the mode button, `f` the flag, Enter opens a row —
     so disarming only on click left exactly the staleness the second click
     exists to prevent reachable with one hand on the keyboard. */
  if(disarmStop() && lastData) render(lastData);
  /* `c` works in both modes — it is the way back out of calm. */
  if(k === "c"){ stop(); setDisplayMode(displayMode === "calm" ? "regular" : "calm"); return; }
  if(displayMode !== "calm" || !lastData) return;
  /* A focused button already answers Enter and Space itself. */
  if((k === "Enter" || k === " ") && e.target && e.target.closest &&
     e.target.closest("a[href],button,select,textarea,input,[tabindex]")) return;
  if(k === "j" || k === "ArrowDown"){ stop(); calmMove(1); }
  else if(k === "k" || k === "ArrowUp"){ stop(); calmMove(-1); }
  else if(k === "Enter" || k === " "){
    stop();
    const sid = calmEffectiveFocus(calmOrder(lastData));
    if(sid) calmAction("open", sid);
  }
  else if(k === "f"){ stop(); calmAction("flag", null); }
  else if(k === "u" && usagePresent(lastData)){ stop(); usageAction("usage", null); }
  else if(k === "Escape"){
    stop();
    calmOpenKey = null; calmFlagOnly = false; calmStateOnly = null;
    usageCfgOpen = false;
    calmResetScroll = true;
    render(lastData);
  }
});

function calmHarnessCell(r){
  const h = own(HARNESS, r.harness, null) ||
    {code:String(r.harness || "?").slice(0, 2).toUpperCase(), name:r.harness};
  const inner = h.icon
    ? `<span class="cm-ico" style="-webkit-mask:url('${h.icon}') center/contain no-repeat;` +
      `mask:url('${h.icon}') center/contain no-repeat"></span>`
    : `<span class="cm-icot">${esc(h.code)}</span>`;
  return `<span class="cm-hcell" title="${esc(h.name || r.harness)}">${inner}</span>`;
}

function calmExpansion(r){
  const tone = CALM_TONE[r.tone] || CALM_TONE.quiet;
  const why = r.flag
    ? `<div class="cm-why"><span class="cm-why-g" style="color:${tone.ink}">◆</span>` +
      `<span class="cm-why-t"><b style="color:${tone.ink}">${esc(r.flag)}</b>` +
      ` — ${esc(r.why)}</span></div>`
    : "";
  const quote = r.excerpt
    ? `<div class="cm-quote"><span class="cm-subk">last prompt</span>` +
      `<div class="cm-quote-t">${esc(r.excerpt)}</div></div>`
    : "";
  const tasks = r.tasks.length
    ? `<div class="cm-tasks"><span class="cm-subk">tasks · ${esc(r.taskNote)}</span>` +
      r.tasks.map(t => {
        const s = own(CALM_TASK, t.status, CALM_TASK.pending);
        const line = (t.status === "in_progress" && t.activeForm)
          ? t.activeForm + "…" : t.subject;
        return `<div class="cm-task"><span class="cm-task-g" style="color:${s.ink}">` +
          `${s.glyph}</span><span class="cm-task-t" style="color:${s.text}"` +
          ` title="${esc(t.subject)}">${esc(line)}</span></div>`;
      }).join("") + `</div>`
    : "";
  const meta = `<div class="cm-meta">` +
    `<span>${esc(own(HARNESS, r.harness, {}).name || r.harness)}</span>` +
    `<span>${esc(r.project)}</span><span>session ${esc(r.session)}</span>` +
    `<span>${esc(r.detailAge)}</span>` +
    (r.tasks.length ? `<span>${esc(r.taskNote)}</span>` : "") + `</div>`;
  const hasPct = !!(r.turn && r.turn.pct != null);
  const turn = r.turn
    ? `<div class="cm-turn"><div class="cm-turn-top"><span class="cm-k">this request</span>` +
      (hasPct ? `<span class="cm-turn-pct">${r.turn.pct}%</span>` : "") + `</div>` +
      (hasPct ? `<div class="cm-turn-track"><span class="cm-fill"` +
        ` style="width:${r.turn.pct}%;background:${r.rail}"></span></div>` : "") +
      `<div class="cm-turn-line">${esc(r.turnLine)}</div></div>`
    : "";
  const subs = r.subagents.length
    ? `<div class="cm-subs"><span class="cm-subk">subagents</span>` +
      r.subagents.slice(0, 8).map(a => `<div class="cm-sub"><span class="cm-sub-dot"></span>` +
        `<span class="cm-sub-n" title="${esc(a)}">${esc(a)}</span></div>`).join("") +
      (r.subagents.length > 8
        ? `<div class="cm-sub"><span class="cm-sub-n">+${r.subagents.length - 8} more</span></div>`
        : "") + `</div>`
    : "";
  const copied = calmCopyNote && calmCopyNote.key === r.key;
  const acts = `<div class="cm-acts"><button type="button" class="cm-act" data-calm="copy"` +
    ` data-arg="${esc(r.key)}">${copied ? esc(calmCopyNote.text) : "copy id"}</button>` +
    `<button type="button" class="cm-act" data-calm="open"` +
    ` data-arg="${esc(r.key)}">collapse</button></div>`;
  return `<div class="cm-exp"><div class="cm-exp-main">${why}${quote}${tasks}` +
    sdBlock({spacedock: r.spacedock}) + meta + `</div>` +
    `<div class="cm-exp-side">${turn}${subs}${acts}</div></div>`;
}

function calmRowHTML(r, focusSid){
  const open = calmOpenKey === r.key;
  const focus = r.key === focusSid;
  const tone = CALM_TONE[r.tone] || CALM_TONE.quiet;
  const pct = (r.turn && r.turn.pct != null) ? r.turn.pct : null;
  /* The progress bar lives under the rate, not in a column of its own. As a
     separate track it was 46px wide and empty on every row that was not both
     working and estimable — which on a real board is nearly all of them. */
  const bar = (r.st === "work" && pct != null)
    ? `<span class="cm-track" role="img" aria-label="request ${pct} percent complete">` +
      `<span class="cm-fill" style="width:${pct}%;background:${r.rail}"></span></span>`
    : "";
  const flag = r.flag
    ? `<span class="cm-flag" style="background:${tone.bg};color:${tone.ink};` +
      `border-color:${tone.bd}">${esc(r.flag)}</span>`
    : "";
  const copied = calmCopyNote && calmCopyNote.key === r.key;
  return `<div class="cm-item"><div class="cm-row${focus ? " focus" : ""}${open ? " open" : ""}"` +
    ` data-calm="open" data-arg="${esc(r.key)}" role="button" aria-expanded="${open}">` +
    (focus ? `<span class="cm-cursor"></span>` : "") +
    `<span class="cm-rail" style="background:${r.rail}"></span>` +
    calmHarnessCell(r) +
    `<span class="cm-title" style="color:${r.titleInk}"` +
    ` title="${esc(r.title)}">${esc(r.title)}</span>` +
    /* Real project names fill the whole cell, and tail truncation would eat the
       session id — the part that identifies the row. Only the project gives way. */
    `<span class="cm-where" title="${esc(r.project + " · " + r.session)}">` +
    `<span class="cm-proj">${esc(r.project)}</span>` +
    `<span class="cm-sess">· ${esc(r.session)}</span></span>` +
    `<span class="cm-doing" title="${esc(r.doingRaw)}">${esc(r.doing)}</span>` +
    `<span>${flag}</span>` +
    `<span class="cm-rate"><span class="cm-metric" style="color:var(--ink2)"` +
    ` title="${esc(r.rateTip)}">${esc(r.rate)}</span>${bar}</span>` +
    `<span class="cm-metric" style="color:${r.quietInk}"` +
    ` title="${esc(r.quietTip)}">${esc(r.quiet)}</span>` +
    `<span class="cm-q"><button type="button" class="cm-qb" data-calm="copy"` +
    ` data-arg="${esc(r.key)}" title="copy this session's id">` +
    `${copied ? esc(calmCopyNote.text) : "copy id"}</button></span>` +
    `<span class="cm-caret">${open ? "–" : "+"}</span></div>` +
    (open ? calmExpansion(r) : "") + `</div>`;
}

function calmLedger(d){
  const all = d.sessions.map(x => calmRow(d, x));
  const shown = calmFilter(all);
  const entries = calmEntries(shown);
  const focusSid = calmEffectiveFocus(entries.filter(e => e.row).map(e => e.row));
  const count = st => all.filter(r => r.st === st).length;
  const chip = (st, label, dot) =>
    `<button type="button" class="cm-chip${calmStateOnly === st ? " on" : ""}"` +
    ` data-calm="state" data-arg="${st}" aria-pressed="${calmStateOnly === st}">` +
    dot + count(st) + " " + label + `</button>`;
  const legend =
    chip("needs", "needs you", `<span class="cm-dot" style="background:var(--alert)"></span>`) +
    chip("work", "working", `<span class="cm-dot" style="background:var(--accent)"></span>`) +
    chip("idle", "idle", `<span class="cm-dot hollow"></span>`);
  const sorts = ["attention", "recent", "repo"].map(k =>
    `<button type="button" class="cm-segb${calmSort === k ? " on" : ""}" data-calm="sort"` +
    ` data-arg="${k}" aria-pressed="${calmSort === k}">${k}</button>`).join("");
  const flagged = all.filter(r => r.flag).length;
  const clear = (calmFlagOnly || calmStateOnly)
    ? `<button type="button" class="cm-clear" data-calm="clear">clear</button>` : "";
  const note = shown.length === all.length
    ? "showing all " + all.length
    : "showing " + shown.length + " of " + all.length;

  let body;
  if(!shown.length && !all.length){
    body = `<div class="cm-empty"><span class="cm-subk">all quiet</span>` +
      `<div class="cm-empty-t">No session activity in the last ${esc(d.window_hours)}h.` +
      (d.show_all ? "" : ` <a href="?all=1">Show all sessions</a>`) + `</div></div>`;
  } else if(!shown.length){
    body = `<div class="cm-empty"><span class="cm-subk">all quiet</span>` +
      `<div class="cm-empty-t">Nothing matches this filter. ` +
      `<button type="button" class="cm-link" data-calm="clear">Show all ${all.length}` +
      `</button></div></div>`;
  } else {
    body = entries.map(e => e.row ? calmRowHTML(e.row, focusSid)
      : `<div class="cm-div"><span class="cm-div-k">${esc(e.divider.label)}</span>` +
        `<span class="cm-div-n">${e.divider.count}</span>` +
        `<span class="cm-div-rule"></span>` +
        (e.divider.flagged ? `<span class="cm-div-f">◆ ${e.divider.flagged}</span>` : "") +
        `</div>`).join("");
  }

  const found = (d.harnesses || []).filter(h => h.discovered);
  const strip = (d.harnesses || []).map(h => badge(h.key, h.discovered && !h.error, h.label,
    h.error ? " — collector error" : (h.discovered ? "" : " — no data"))).join("");
  return `<div class="cm-frame">` +
    `<div class="cm-bar"><span class="cm-brand">Cargento</span>` +
    `<div class="cm-legend">${legend}</div><span class="cm-sp"></span>` +
    `<span class="cm-live"><span class="live" id="live-dot"></span>` +
    `<span id="live-status">auto-refresh 5s · ` +
    `${new Date(d.generated*1000).toLocaleTimeString()}</span>` +
    (d.show_all ? `<span>· showing all</span>` : "") + notifyControl(d) + `</span></div>` +
    `<div class="cm-ctl"><span class="cm-k">order</span><div class="cm-seg">${sorts}</div>` +
    `<span class="cm-vr"></span>` +
    `<button type="button" class="cm-flagchip${calmFlagOnly ? " on" : ""}" data-calm="flag"` +
    ` aria-pressed="${calmFlagOnly}">◆ ${flagged} flagged</button>${clear}` +
    (usagePresent(d)
      ? `<span class="cm-vr"></span><button type="button"` +
        ` class="cm-flagchip${usageOpen ? " on" : ""}" data-calm="usage"` +
        ` aria-pressed="${usageOpen}">usage</button>`
      : "") +
    `<span class="cm-sp"></span><span class="cm-note">${esc(note)}</span></div>` +
    usageBandCalm(d) +
    `<div class="cm-body" id="cm-body">` +
    `<div class="cm-head"><span></span><span></span><span>session</span><span>where</span>` +
    `<span>doing</span><span>flag</span><span class="r">rate</span>` +
    `<span class="r">idle / wait</span>` +
    `<span></span><span></span></div>${body}</div>` +
    /* The session count belongs to the control bar's `showing …` note, which is
       filter-aware. Repeating it down here was a second number for one fact. */
    `<div class="cm-foot"><span>${found.length} ` +
    `${found.length === 1 ? "harness" : "harnesses"} · ` +
    `${(d.summary.rate_per_min || 0).toLocaleString()} tok/min</span>` +
    `<span class="cm-fstrip">${strip}</span><span class="cm-sp"></span>` +
    `<span class="cm-keys">` +
    CALM_FLAG_LEGEND.map(f => `<span><span class="cm-legend-f"` +
      ` style="color:${CALM_TONE[f.tone].ink}">◆</span>${esc(f.label)}</span>`).join("") +
    `</span><span class="cm-sp"></span>` +
    `<span class="cm-keys"><span>j k move</span><span>⏎ expand</span><span>f flagged</span>` +
    (usagePresent(d) ? `<span>u usage</span>` : "") +
    `<span>c mode</span><span>esc clear</span></span></div></div>`;
}

/* Every control the ledger emits is identified by its (data-calm, data-arg)
   pair, which survives the DOM swap even though the element does not. Capture
   the focused one before the swap and hand focus back to its replacement, the
   way restoreSparkState does for the sparkline — otherwise tabbing into the
   ledger is undone by the next poll, five seconds later at most. */
function calmFocusKey(){
  const el = document.activeElement;
  if(!el || !el.getAttribute) return null;
  const act = el.getAttribute("data-calm");
  return act ? {act, arg: el.getAttribute("data-arg")} : null;
}

function calmRestoreFocus(key){
  if(!key) return;
  const root = document.getElementById("app");
  /* Matched by attribute in JS rather than through a built selector: `arg` is a
     session id, and a selector string would need escaping the DOM does not. */
  if(!root || !root.querySelectorAll) return;
  for(const el of root.querySelectorAll("[data-calm]")){
    if(el.getAttribute("data-calm") !== key.act) continue;
    if(el.getAttribute("data-arg") !== key.arg) continue;
    if(el.focus) el.focus({preventScroll: true});
    return;
  }
}

/* render() replaces #app wholesale every poll, which resets the ledger's own
   scroll offset. Put it back, then bring the keyboard cursor into view if the
   last action moved it. */
function calmRestoreScroll(){
  const body = document.getElementById("cm-body");
  if(!body) return;
  body.scrollTop = calmScrollTop;
  if(calmRevealFocus){
    calmRevealFocus = false;
    const row = body.querySelector ? body.querySelector(".cm-row.focus") : null;
    if(row && row.scrollIntoView) row.scrollIntoView({block: "nearest"});
  }
  calmScrollTop = body.scrollTop;
}

/* Desktop notifications.
   Exactly one layer notifies for a given transition. The server fires an
   OS-level popup where it has a backend and reports that as `native_notify`;
   the page raises its own only when the server cannot. Without that split,
   macOS would pop twice for every blocked session. */
let notifyState = new Map();  /* harness:sid -> last state seen */
let notifyPrimed = false;     /* first payload only records: nothing is "new" yet */

function notifySupported(){ return typeof Notification !== "undefined"; }

function notifyPermission(){
  return notifySupported() ? (Notification.permission || "default") : "unsupported";
}

function browserNotifyOwns(d){ return !(d && d.native_notify) && notifySupported(); }

function requestNotifyPermission(){
  if(!notifySupported() || !Notification.requestPermission) return;
  /* Re-render so the control reflects the new permission. Both the callback
     and promise forms are handled; Safari still uses the callback. */
  const done = () => { if(lastData) render(lastData); };
  let result;
  try{ result = Notification.requestPermission(done); }catch(e){ return; }
  if(result && typeof result.then === "function") result.then(done, done);
}

function syncNotifications(d){
  const seen = new Map();
  const fire = browserNotifyOwns(d) && notifyPermission() === "granted";
  for(const s of d.sessions){
    const key = s.harness + ":" + s.sid;
    seen.set(key, s.state);
    if(!fire || !notifyPrimed) continue;
    /* Same rule the server uses: notify on the transition into needs_input,
       not for every refresh a session spends blocked. */
    if(!s.active || s.state !== "needs_input") continue;
    if(notifyState.get(key) === "needs_input") continue;
    try{
      new Notification("Claude is waiting on you",
        {body: "[" + s.project + "] " + (s.state_detail || "needs your input"),
         tag: key});  /* tag replaces a stale popup instead of stacking */
    }catch(e){ /* permission revoked mid-session, or a headless browser */ }
  }
  notifyState = seen;  /* sessions that disappeared stop being tracked */
  notifyPrimed = true;
}

function notifyControl(d){
  if(!browserNotifyOwns(d)) return "";
  const p = notifyPermission();
  if(p === "granted" || p === "unsupported") return "";
  if(p === "denied"){
    return ` · <span class="notify-note" title="Re-enable notifications for this ` +
      `site in your browser's settings to be alerted when a session needs you.">` +
      `notifications blocked</span>`;
  }
  return ` · <button type="button" class="notify-btn" onclick="requestNotifyPermission()">` +
    `Enable notifications</button>`;
}

function render(d){
  /* The stopped panel is terminal, and this is the sink that would undo it.
     Guarding refresh() alone was not enough: fourteen other call sites end in
     render(lastData) — setDisplayMode, toggleIdle, calmAction, calmCopyId, the
     keyboard — and the keydown listener is on `document`, so nothing in #app
     gates it. One `c` was enough to repaint a live-looking board, stale
     needs-input count back in the title, for a server that is gone.

     This covers every DOM write below it, which is all of them except two
     places that need their own check and have one: renderStopped(), which is
     the panel, and refresh()'s catch arm, which writes #app and the live-status
     text without going through here. */
  if(serverStopped) return;
  lastData = d;
  syncNotifications(d);
  const app = document.getElementById("app");
  const needs = d.sessions.filter(x => x.active && x.state === "needs_input");
  if(!app){
    document.title = (needs.length > 0 ? `(${needs.length}!) ` : "") + "Cargento";
    return;
  }
  if(displayMode === "calm"){
    // Carry the outgoing ledger's scroll offset across the DOM swap — unless
    // the last action re-filtered the list, where the old offset is meaningless.
    const outgoing = document.getElementById("cm-body");
    if(calmResetScroll){ calmScrollTop = 0; calmResetScroll = false; }
    else if(outgoing) calmScrollTop = outgoing.scrollTop;
    const focusKey = calmFocusKey();
    renderInProgress = true;
    app.className = "wrap calm";
    app.innerHTML = modeBar() + calmLedger(d) + usageModal(d);
    renderInProgress = false;
    calmRestoreScroll();
    calmRestoreFocus(focusKey);
    restoreStopFocus();
    document.title = (needs.length > 0 ? `(${needs.length}!) ` : "") + "Cargento";
    return;
  }
  const sparkFocused = !!(document.activeElement && document.activeElement.id === "spark-main");
  // Capture pointer position before render so we can restore it afterward, even if
  // pointermove fires during the render operation.
  const savedPointer = sparkPointer ? {x: sparkPointer.x, y: sparkPointer.y} : null;
  const s = d.summary;
  const working = d.sessions.filter(x => x.state === "working");
  const idle = d.sessions.filter(x => x.state === "idle");

  const tiles =
    countTile("Needs you", {line: "sessions blocked on you",
      empty: "Nothing is waiting on you."}, needs, true) +
    countTile("Working now", {line: "sessions generating",
      empty: "No agent is generating right now."}, working, false) +
    rateTile(d);

  /* Three em-dashes and a sentence saying the same thing is not a summary. When
     nothing tracks tasks, say that once and stop. */
  const subnote = s.total_tasks
    ? `<span>open tasks <b>${s.open_tasks}</b></span><span class="div"></span>` +
      `<span>progress <b>${s.progress_pct}%</b></span><span class="div"></span>` +
      `<span>${s.total_done}/${s.total_tasks} tracked tasks done</span>`
    : `<span>no active session uses tracked tasks</span>`;

  const bandHtml = needs.length
    ? `<div class="band"><div class="band-head"><span class="band-dot"></span>` +
      `<span class="band-k">Needs your input</span></div>` +
      needs.map(n => needRow(d, n)).join("") + `</div>`
    : "";

  let workingHtml = "";
  if(working.length){
    workingHtml = `<div class="stack"><div class="sec"><span class="sec-k">Working now</span>` +
      `<span class="sec-count">${working.length}</span><span class="sec-rule"></span></div>` +
      working.map(s => workingCard(d, s)).join("") + `</div>`;
  } else if(d.sessions.length){
    workingHtml = `<div class="stack"><div class="sec"><span class="sec-k">Working now</span>` +
      `<span class="sec-count">0</span><span class="sec-rule"></span></div>` +
      `<div class="empty">No sessions generating right now — every agent is idle or waiting.</div></div>`;
  }

  let idleHtml = "";
  if(idle.length){
    const maxh = idleExpanded ? "3000px" : "184px";
    const fade = idleExpanded ? "" : `<div class="idle-fade"></div>`;
    const rows = idle.map(x => idleRow(d, x)).join("");
    idleHtml = `<div class="stack"><div class="sec"><span class="sec-k">Idle</span>` +
      `<span class="sec-count">${idle.length}</span><span class="sec-rule"></span></div>` +
      `<div class="idle-wrap"><div class="idle-clip" style="max-height:${maxh}">${rows}${fade}</div>` +
      `<div class="idle-toggle-wrap"><button class="idle-toggle" onclick="toggleIdle()">` +
      `${idleExpanded ? "Show less" : "Show all " + idle.length + " idle"}</button></div></div></div>`;
  }

  let body;
  if(!d.sessions.length){
    body = `<div class="empty">No session activity in the last ${esc(d.window_hours)}h.` +
      (d.show_all ? "" : ` <a href="?all=1">Show all sessions</a>`) + `</div>`;
  } else {
    body = `<div class="hero">${tiles}</div><div class="subnote">${subnote}</div>` +
      usageSectionRegular(d) + bandHtml + workingHtml + idleHtml;
  }

  renderInProgress = true;
  app.className = "wrap";
  app.innerHTML = modeBar() +
    `<div class="top"><div><div class="brand">Cargento</div>` +
    `<div class="sub"><span class="live" id="live-dot"></span>` +
    `<span id="live-status">live · updated ${new Date(d.generated*1000).toLocaleTimeString()} · auto-refresh 5s</span>` +
    (d.show_all ? " · showing all" : "") + notifyControl(d) + `</div></div>` +
    `<div class="hstrip">${harnessStrip(d.harnesses)}</div></div>` + body + usageModal(d);
  renderInProgress = false;

  restoreSparkState(sparkFocused, savedPointer);
  restoreStopFocus();
  document.title = (needs.length > 0 ? `(${needs.length}!) ` : "") + "Cargento";
}

async function refresh(){
  /* Checked twice, and both are load-bearing: this one skips a poll that would
     start after the stop, and the ones below drop a poll that was already in
     flight when the stop landed. Without those, the reply settles after
     renderStopped() and repaints a live-looking dashboard over the terminal
     panel — with the interval already cleared, so not even the stalled banner
     would contradict it. /api/data is the slow request here; the shutdown POST
     is a loopback round trip. */
  if(serverStopped) return;
  const sequence = ++refreshSequence;
  try{
    const r = await fetch("/api/data" + (showAll ? "?all=1" : ""));
    if(!r.ok) throw new Error("bad status");
    const data = await r.json();
    if(serverStopped) return;
    if(sequence < latestSettledRefresh) return;
    latestSettledRefresh = sequence;
    recordRates(data);
    render(data);
    window.__refreshFailures = 0;
  }catch(e){
    if(serverStopped) return;
    if(window.__SAMPLE){ recordRates(window.__SAMPLE); render(window.__SAMPLE); return; }
    if(sequence < latestSettledRefresh) return;
    latestSettledRefresh = sequence;
    console.error("dashboard refresh failed", e);
    window.__refreshFailures = (window.__refreshFailures || 0) + 1;
    const app = document.getElementById("app");
    if(app && !lastData){
      app.innerHTML = `<div class="empty">refresh failed — is the server running?</div>`;
      return;
    }
    if(window.__refreshFailures < 2) return;
    const dot = document.getElementById("live-dot");
    const status = document.getElementById("live-status");
    if(dot) dot.classList.add("stalled");
    if(status){
      const updated = new Date(lastData.generated*1000).toLocaleTimeString();
      status.textContent = `stalled · last update ${updated} · retrying every 5s`;
    }
  }
}
refresh();
let refreshTimer = setInterval(refresh, 5000);
