import { ConsolePrompt, ConsoleScopeHeader, RawProjectStatus } from './ConsoleParts';
import type { ProjectModel } from './model';

/* What a slot says until the step that owns it supplies it: a stated absence, never a blank, because a blank
   panel would read as an empty healthy one. */

export function Placeholder({ name, what }: { readonly name: string; readonly what: string }) {
  return (
    <p className="next-placeholder" data-next-placeholder={name}>
      {`${what} is not available in the React interface yet. It arrives with a later migration step (the steering and tripwire controls); the Python dashboard still serves it.`}
    </p>
  );
}

export function DefaultDecisions() {
  return <Placeholder name="decisions" what="The Decisions timeline" />;
}

export function DefaultConsole({ model }: { readonly model: ProjectModel }) {
  return (
    <>
      <ConsoleScopeHeader model={model} />
      <ConsolePrompt model={model} />
      <Placeholder name="console" what="The Console operating rail" />
      <RawProjectStatus model={model} />
    </>
  );
}
