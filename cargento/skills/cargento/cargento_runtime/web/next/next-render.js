// This is the old bundle's named cadence, not a fresh polling policy. The
// collector memo is keyed by show_all, so an all=1 tab costs a second real
// filesystem pass when it runs beside a tab without that flag.
const NEXT_POLL_MS = 5000;

function nextOverviewBody(tab){
  if(tab === "sessions") return nextSessionsView();
  if(tab === "projects") return nextProjectsView();
  return "";
}

function nextDataUrl(){
  return nextQuery.get("all") === "1" ? "/api/data?all=1" : "/api/data";
}

async function refreshNext(){
  try{
    const response = await fetch(nextDataUrl());
    if(!response.ok) throw new Error(`HTTP ${response.status}`);
    nextData = await response.json();
    nextRefreshFailures = 0;
  }catch(_error){
    nextRefreshFailures += 1;
  }
  renderNext();
}

renderNext();
refreshNext();
setInterval(refreshNext, NEXT_POLL_MS);
