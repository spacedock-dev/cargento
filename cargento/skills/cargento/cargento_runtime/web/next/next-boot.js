const nextQuery = new URLSearchParams(location.search);

const qs = name => nextQuery.get(name);
const esc = value => String(value == null ? "" : value).replace(/[&<>"']/g,
  char => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[char]));

function nextDecodeRoutePart(value){
  try{
    return decodeURIComponent(value);
  }catch(_error){
    return "";
  }
}

function nextRouteFromFragment(fragment){
  const token = String(fragment || "").startsWith("#n=")
    ? String(fragment).slice(3)
    : "overview";
  const parts = token.split(":");
  if(parts.length === 2 && parts[0] === "project"){
    const project = nextDecodeRoutePart(parts[1]);
    if(project) return {view: "project", project, session: null};
  }
  if(parts.length === 3 && parts[0] === "session"){
    const project = nextDecodeRoutePart(parts[1]);
    const session = nextDecodeRoutePart(parts[2]);
    if(project && session) return {view: "session", project, session};
  }
  return {view: "overview", project: null, session: null};
}

function nextFragmentForRoute(route){
  if(route && route.view === "session" && route.project && route.session){
    return `#n=session:${encodeURIComponent(route.project)}:${encodeURIComponent(route.session)}`;
  }
  if(route && route.view === "project" && route.project){
    return `#n=project:${encodeURIComponent(route.project)}`;
  }
  return "#n=overview";
}

let nextRoute = nextRouteFromFragment(location.hash);
const nextInitialFragment = nextFragmentForRoute(nextRoute);
if(location.hash !== nextInitialFragment) location.hash = nextInitialFragment;
