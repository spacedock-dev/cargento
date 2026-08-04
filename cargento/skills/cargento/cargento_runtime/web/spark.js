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
