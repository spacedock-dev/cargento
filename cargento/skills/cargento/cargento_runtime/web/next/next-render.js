function nextDetailBody(route){
  if(route.view === "project") return nextProjectView(route.project);
  if(route.view === "session") return nextSessionView(route.project, route.session);
  return "";
}

function nextViewBody(){
  if(nextRoute.view === "attention") return nextAttentionView(nextAttentionModel(nextData || {}));
  if(nextRoute.view === "projects"){
    return `<section class="next-projects" data-next-view-body="projects"><h1>Projects</h1>${nextProjectsView(nextAttentionModel(nextData || {}))}</section>`;
  }
  if(nextRoute.view === "sessions"){
    return `<section class="next-sessions" data-next-view-body="sessions"><h1>Sessions</h1>${nextSessionsView()}</section>`;
  }
  return `<section data-next-view-body="${esc(nextRoute.view)}">${nextDetailBody(nextRoute)}</section>`;
}

function nextDataUrl(){
  return nextQuery.get("all") === "1" ? "/api/data?all=1" : "/api/data";
}

function nextRefreshRetryMs(){
  return NEXT_LIVE_SUPPORTED ? NEXT_FALLBACK_POLL_MS : NEXT_LEGACY_POLL_MS;
}

async function refreshNext(manual = false){
  if(manual && nextRefreshInFlight) return;
  if(manual){
    nextRefreshInFlight = true;
    renderNext();
  }
  try{
    const response = await fetch(nextDataUrl());
    if(!response.ok) throw new Error(`HTTP ${response.status}`);
    const fresh = await response.json();
    nextObserveWorkstream(fresh);
    nextData = fresh;
    nextRefreshFailures = 0;
    nextLastRefreshSuccessAt = Date.now();
  }catch(_error){
    nextRefreshFailures += 1;
  }finally{
    if(manual) nextRefreshInFlight = false;
    renderNext();
  }
}
