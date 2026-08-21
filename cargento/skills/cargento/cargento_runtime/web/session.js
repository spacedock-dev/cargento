/* ── session mode ────────────────────────────────────────────────────────────
   A third display of the same /api/data payload both overviews already consume:
   one session's dispatch tree. No new endpoint, no new collector — the
   `spacedock.workflows` array is already published per session by
   collectors/claude.py → session_spacedock. The view renders each workflow as a
   vertical tree of stage-colored entity nodes along the workflow's ordered
   `stages` spine, with live workers (`live: true`) highlighted, and a one-line
   goal header above the tree when the workflow frontmatter carries a `title`
   scalar (published as `workflow.goal`). When no `title` is present, no goal
   line renders — the view shows the tree alone, never a fabricated objective. */

/* The session picker: rendered when session mode is entered with no target
   session (null key, or a key that no longer matches a live session). Each row
   is a `data-calm="session"` control so the existing click channel selects it
   without a second handler. */
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

function sessionView(d){
  if(!sessionViewKey){
    return sessionPicker(d);
  }
  const sess = ((d && d.sessions) || []).find(s => sessKey(s) === sessionViewKey);
  if(!sess){
    return sessionPicker(d);
  }
  const sd = sess.spacedock;
  if(!sd || !sd.workflows || !sd.workflows.length){
    return sessionHeader(sess) +
      `<div class="sv-empty">This session has no Spacedock workflows.</div>`;
  }
  return sessionHeader(sess) + sd.workflows.map(sessionWorkflow).join("");
}
