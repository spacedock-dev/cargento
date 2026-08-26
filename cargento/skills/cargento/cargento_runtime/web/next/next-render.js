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

async function refreshNext(){
  try{
    const response = await fetch(nextDataUrl());
    if(!response.ok) throw new Error(`HTTP ${response.status}`);
    const fresh = await response.json();
    nextObserveWorkstream(fresh);
    nextData = fresh;
    nextRefreshFailures = 0;
  }catch(_error){
    nextRefreshFailures += 1;
  }
  renderNext();
}
