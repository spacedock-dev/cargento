import assert from 'node:assert/strict';
import { goldenFor, jsonSafe, normalise } from './golden.mjs';

/* DEC-27's retracted controls and relocated explanation change only the recorded
   side. React observations retain every control and word, so regressions fail. */
export function sessionDeviations(proof) {
  const golden = goldenFor(proof);
  const seen = new Map();
  const retract = (value, key = '') => {
    if (typeof value === 'string') {
      value = value.replaceAll('ASSIGNMENT', 'Current task');
      if (key === 'header' || key === 'text')
        return value
          .replace(/Copy ID|Copy link|Copy command/g, '')
          .replaceAll('COMMAND SURFACE', '')
          .replaceAll('How rows are split', '')
          .replaceAll('Goal sources', '')
          .replace(
            /No resume commandWhy(?:This session published no usable id this run|[^.]* publishes no re-entry command), so (?:there is no re-entry command to copy|there is none to copy)\./g,
            '',
          )
          .replace(/No resume command · | · No resume command|No resume command/g, '')
          .replace(
            /(?:This session published no usable id this run|(?<=Why)[^.]* publishes no re-entry command), so (?:there is no re-entry command to copy|there is none to copy)\./g,
            '',
          )
          .replace(
            /What analysis does(?:When you analyze drift, Cargento lists where this session departed from your saved goal\. |Choose a goal or use your prompt, then analyze drift: Cargento lists where this session departed from it\. )It never writes into the session, so steering stays yours\./g,
            '',
          );
      return value;
    }
    if (Array.isArray(value))
      return value
        .filter(
          (item) =>
            !(
              typeof item === 'string' &&
              /^Copy (session ID |a link to this session|re-entry command )/.test(item)
            ),
        )
        .filter(
          (item) =>
            !(Array.isArray(item) && ['Copy ID', 'Copy link', 'Copy command'].includes(item[0])),
        )
        .map((item) => retract(item, key));
    if (value && typeof value === 'object')
      return Object.fromEntries(
        Object.entries(value).map(([name, item]) => [
          name,
          retract(name === 'fleet' ? item.slice(0, 2) : item, name),
        ]),
      );
    return value;
  };
  return {
    ...golden,
    recorded: (key) => retract(golden.recorded(key)),
    observe(key) {
      const value = retract(golden.observe(key));
      seen.set(key, value);
      return value;
    },
    verify(key, value) {
      assert.ok(seen.has(key));
      assert.deepEqual(jsonSafe(normalise(value)), seen.get(key), `${proof}: ${key}`);
    },
  };
}
