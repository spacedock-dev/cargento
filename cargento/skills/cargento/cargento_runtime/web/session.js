/* ── session mode ────────────────────────────────────────────────────────────
   A third display of the same /api/data payload both overviews already consume:
   one session's dispatch tree. No new endpoint, no new collector — the
   `spacedock.workflows` array is already published per session by
   collectors/claude.py → session_spacedock. The view renders each workflow as a
   vertical tree of stage-colored entity nodes along the workflow's ordered
   `stages` spine, with live workers (`live: true`) highlighted, and a one-line
   goal header above the tree when the workflow frontmatter carries a `title`
   scalar (published as `workflow.goal`). When no `title` is present, no goal
   line renders — the view shows the tree alone, never a fabricated objective.

   The session target is routable via the URL hash (`#session=<harness>:<sid>`),
   set by mode.js's hash sync. This lets the view be navigated to directly and
   shared. Distinct empty states cover the four cases a session view can land
   in: loading (session not found in the current data), not-a-Spacedock-session
   (spacedock null), first-officer with no in-flight entities (freshness gate),
   and ensign/worker sessions. */

/* The session picker: rendered when session mode is entered with no target
   session (null key). Each row is a `data-calm="session"` control so the
   existing click channel selects it without a second handler. */
function sessionPicker(d){
  const sessions = (d && d.sessions) || [];
  if(!sessions.length){
    return `<div class="sv-empty">No sessions to view. Switch to regular or calm to see the board.</div>`;
  }
  const rows = sessions.map(s => {
    const key = sessKey(s);
    const title = s.title || s.last_prompt || s.project;
    return `<div class="sv-pick" data-calm="session" data-arg="${esc(key)}" role="button">` +
      badge(s.harness, s.active) +
      `<span class="sv-pick-title">${esc(title)}</span>` +
      `<span class="sv-pick-meta">${esc(s.project)} · ${esc(s.session)}</span></div>`;
  }).join("");
  return `<div class="sv-picker"><div class="sv-picker-h">Select a session to view its dispatch tree</div>${rows}</div>`;
}

function sessionBackBar(){
  return `<div class="sv-back-bar">` +
    `<button type="button" class="sv-back" data-calm="mode" data-arg="regular">← overview</button>` +
    `</div>`;
}

function sessionHeader(sess){
  const title = sess.title || sess.last_prompt || sess.project;
  return `<div class="sv-header"><div class="sv-title">${esc(title)}</div>` +
    `<div class="sv-meta">${badge(sess.harness, sess.active)}` +
    `<span class="sv-meta-text">${esc(sess.project)} · ${esc(sess.session)}</span></div></div>`;
}

/* One workflow's dispatch tree: stages as a vertical spine, entities grouped
   under their current stage. Live workers carry the `sd-live` class, the same
   class the existing Spacedock strip in regular.js uses, so the visual language
   is shared. Stages with no entities still render (the spine is the workflow's
   declared stage order, not a list of occupied stages) so the reader can see
   where the work is not. */
function sessionWorkflow(wf){
  const stages = wf.stages || [];
  const entities = wf.entities || [];
  const goal = wf.goal || "";
  const goalHtml = goal ? `<div class="sv-goal">${esc(goal)}</div>` : "";
  const byStage = {};
  for(const ent of entities){
    const stage = ent.stage || "";
    (byStage[stage] = byStage[stage] || []).push(ent);
  }
  const spine = stages.map(stage => {
    const ents = byStage[stage] || [];
    const entHtml = ents.length ? ents.map(ent => {
      const live = ent.live ? " sd-live" : "";
      const cyc = ent.cycle ? ` <span class="sv-cyc">${esc(ent.cycle)}</span>` : "";
      return `<div class="sv-ent${live}" title="${esc(ent.slug)}">${esc(sdSlug(ent.slug))}${cyc}</div>`;
    }).join("") : `<div class="sv-ent-empty">—</div>`;
    return `<div class="sv-stage"><div class="sv-stage-name">${esc(stage)}</div>` +
      `<div class="sv-ents">${entHtml}</div></div>`;
  }).join("");
  return `<div class="sv-wf"><div class="sv-wf-name">${esc(wf.workflow)}</div>${goalHtml}` +
    `<div class="sv-tree">${spine}</div></div>`;
}

/* Distinct empty states for the four cases the session view can land in when
   the session is found but has no dispatch tree to render. Each gives a
   heading, a one-line explanation, and a back link — never a blank panel that
   reads as "stuck". */
function sessionEmptyState(sess){
  const sd = sess.spacedock;
  if(!sd){
    return sessionHeader(sess) +
      `<div class="sv-empty sv-empty-type">` +
      `<div class="sv-empty-h">Not a Spacedock session</div>` +
      `<div class="sv-empty-p">This session is not driving a Spacedock workflow.</div>` +
      `</div>`;
  }
  if(sd.role === "first-officer"){
    return sessionHeader(sess) +
      `<div class="sv-empty sv-empty-fo">` +
      `<div class="sv-empty-h">First officer with no in-flight entities</div>` +
      `<div class="sv-empty-p">No workflow entities are fresh enough to show. ` +
      `This may be a freshness-gate issue (see fix-spacedock-freshness-gate).</div>` +
      `</div>`;
  }
  const role = sd.role || "worker";
  return sessionHeader(sess) +
    `<div class="sv-empty sv-empty-worker">` +
    `<div class="sv-empty-h">${esc(role)} session</div>` +
    `<div class="sv-empty-p">This Spacedock session has no in-flight workflow entities.</div>` +
    `</div>`;
}

function sessionView(d){
  if(!sessionViewKey){
    return sessionPicker(d);
  }
  const sess = ((d && d.sessions) || []).find(s => sessKey(s) === sessionViewKey);
  if(!sess){
    /* Loading state: the session was requested (via URL hash or picker) but is
       not in the current data. On a fresh page load the first fetch may not
       include it yet; on an established board it may be outside the display
       window. Either way the reader needs to know the page is working, not
       stuck on a blank panel. */
    return sessionBackBar() +
      `<div class="sv-loading">` +
      `<div class="sv-loading-text">Looking for session ${esc(sessionViewKey)}…</div>` +
      `<div class="sv-loading-p">It may be outside the display window. ` +
      `Try <a href="?all=1${location.hash ? "&" + location.hash.slice(1) : ""}">showing all sessions</a>.` +
      `</div></div>`;
  }
  const sd = sess.spacedock;
  if(!sd || !sd.workflows || !sd.workflows.length){
    return sessionBackBar() + sessionEmptyState(sess);
  }
  return sessionBackBar() + sessionHeader(sess) + sd.workflows.map(sessionWorkflow).join("");
}
