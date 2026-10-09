import { Disclosure, disclosureKey } from '../controls';
import { ScopeCue } from '../timeline/ScopeCue';
import { ProjectAnchor } from './parts';
import type { ProjectModel } from './model';
import { sessionScope, PROJECT_SCOPE } from './scope';
import { sessKey } from './group';

/* The pieces of the Console tab that are the project page's and not the operating rail's: which scope the
   console is for, the sentence that asks for one exact session, and the raw state of every session. The
   rail, the terminal and the setup disclosure are the steering step's; it places these among them. */

export function ConsoleScopeHeader({ model }: { readonly model: ProjectModel }) {
  const scope = model.focus ? sessionScope(model.focus, model.harnesses) : PROJECT_SCOPE;
  return (
    <header className="next-cockpit-scope next-cockpit-scope--evidence">
      <ScopeCue scope={scope} detail={scope.detail} />
      <strong>CONSOLE</strong>
    </header>
  );
}

/* A console is one exact session's, so a project with none selected asks for one, and a project with only
   one session offers it. */
export function ConsolePrompt({ model }: { readonly model: ProjectModel }) {
  if (model.focus) return null;
  const only = model.group.sessions.length === 1 ? model.group.sessions[0] : undefined;
  return (
    <p className="next-cockpit-empty">
      {'Select one exact session to open its read-only console.'}
      {only ? (
        <>
          {' '}
          <ProjectAnchor
            route={{
              view: 'project',
              project: model.group.label,
              focus: sessKey(only),
              tab: 'console',
            }}
          >
            Open this session’s console
          </ProjectAnchor>
        </>
      ) : null}
    </p>
  );
}

/** Every session of the project and the state it published, raw, behind a disclosure. */
export function RawProjectStatus({ model }: { readonly model: ProjectModel }) {
  const rows = model.group.sessions;
  if (!rows.length) return null;
  return (
    <Disclosure
      disclosureKey={disclosureKey({
        project: model.route.project,
        scope: model.route.focus ?? '',
        name: 'status',
      })}
      className="next-cockpit-console-status"
      focusKey="cockpit-disclosure:status"
      summary="Raw project status"
    >
      <ul>
        {rows.map((session, index) => (
          // The same pair twice is a malformed board, and the list still needs two keys.
          <li key={`${sessKey(session)}#${String(index)}`}>
            {`${sessKey(session)} · ${String(session['state'] || 'unknown')}`}
          </li>
        ))}
      </ul>
    </Disclosure>
  );
}
