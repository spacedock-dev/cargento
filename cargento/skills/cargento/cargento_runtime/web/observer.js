/* The observer panel: a compact card rendering the derived goal + current
   stage + one open block from the sidecar. Self-contained: it renders from
   the sidecar alone, without the dispatch tree. The operator triggers it by
   clicking "observe" on a session card; observeSession fetches the sidecar
   from /api/observe and renders it into a container. */

function renderObserverPanel(sidecar){
  if(!sidecar) return '<div class="observer-empty">Not yet observed.</div>';
  const goal = sidecar.goal || "";
  const stage = sidecar.stage || "";
  const block = sidecar.block || "";
  const noGoal = goal === "no goal derived";
  const goalHtml = noGoal
    ? '<div class="observer-goal observer-sentinel">no goal derived</div>'
    : '<div class="observer-goal">' + esc(goal) + '</div>';
  const stageHtml = stage
    ? '<span class="observer-stage">' + esc(stage) + '</span>'
    : '';
  const blockHtml = block
    ? '<div class="observer-block">' + esc(block) + '</div>'
    : '';
  return '<div class="observer-panel">' + goalHtml + stageHtml + blockHtml + '</div>';
}

async function observeSession(harness, sid, container){
  if(!container) return;
  container.innerHTML = '<div class="observer-loading">observing…</div>';
  try{
    const r = await fetch("/api/observe?harness=" + encodeURIComponent(harness) +
      "&sid=" + encodeURIComponent(sid));
    if(!r.ok) throw new Error("bad status");
    const sidecar = await r.json();
    container.innerHTML = renderObserverPanel(sidecar);
  }catch(e){
    container.innerHTML = '<div class="observer-error">observe failed</div>';
  }
}
