const nextQuery = new URLSearchParams(location.search);
const nextRoute = {view: "overview", project: null, session: null};

const qs = name => nextQuery.get(name);
const esc = value => String(value == null ? "" : value).replace(/[&<>"']/g,
  char => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[char]));
