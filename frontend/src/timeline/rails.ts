import type { CSSProperties } from 'react';

/* How the semantic timeline's rows are joined into lanes: which rail a row sits on, and where a lane's line
   runs between its own consecutive rows. Ported from `projectEventFlows` in the legacy `project.js`, which
   `rails.differential.test.ts` holds it to.

   A lane's line starts below its first row ("out"), runs through every row between and ends above the next
   one of its own ("in"). A row that is both the end of one run and the start of the next is "through". The
   rows are the ones the mode kept, in the order they are drawn, so a filtered-out row leaves no gap in the
   line of a lane that has rows on both sides of it. */
export type Flow = 'out' | 'in' | 'through';

export function eventFlows(
  events: readonly { readonly lane: { readonly key: string } }[],
): ReadonlyMap<string, Flow>[] {
  const flows = events.map(() => new Map<string, Flow>());
  const byLane = new Map<string, number[]>();
  events.forEach((event, index) => {
    const found = byLane.get(event.lane.key);
    if (found) found.push(index);
    else byLane.set(event.lane.key, [index]);
  });
  for (const [laneKey, indices] of byLane) {
    indices.slice(0, -1).forEach((start, offset) => {
      const end = indices[offset + 1] as number;
      for (let index = start; index <= end; index += 1) {
        const next: Flow = index === start ? 'out' : index === end ? 'in' : 'through';
        const row = flows[index] as Map<string, Flow>;
        row.set(laneKey, row.has(laneKey) ? 'through' : next);
      }
    });
  }
  return flows;
}

/* The custom properties a row and the legend size their columns by: one rail column for each lane. */
export const laneStyle = (count: number, index?: number): CSSProperties =>
  ({
    '--lane-count': count,
    ...(index === undefined ? {} : { '--lane-index': index }),
  }) as CSSProperties;
