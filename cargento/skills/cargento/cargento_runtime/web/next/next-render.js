function nextOverviewBody(tab){
  if(tab === "sessions") return nextSessionsView();
  if(tab === "projects") return nextProjectsView();
  return "";
}

function nextDetailBody(route){
  if(route.view === "project") return nextProjectView(route.project);
  if(route.view === "session") return nextSessionView(route.project, route.session);
  return "";
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
