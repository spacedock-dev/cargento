import type { EvidenceRow } from './level';
import { Why } from './Why';

/* The cited entries' own rows: what each is, who recorded it, and when, with the source one click away. The
   scope names the list a row belongs to, so one entry cited in two places keeps two independent disclosures. */
export function EvidenceList({
  rows,
  scope,
}: {
  readonly rows: readonly EvidenceRow[];
  readonly scope: string;
}) {
  if (!rows.length) return null;
  return (
    <ul className="next-cockpit-assessment-evidence">
      {rows.map((row) => (
        <li key={row.id}>
          <p className="next-cockpit-assessment-entry">{row.label}</p>
          <span className="next-cockpit-reading-evidence">{`${row.kind} · ${row.who}`}</span>
          <span className="next-cockpit-reading-evidence">{`${row.eventLabel} ${row.at}`}</span>
          {row.result ? <span className="next-cockpit-reading-evidence">{row.result}</span> : null}
          <Why name={`assessment-source:${scope}:${row.id}`} summary="Source">
            <p className="next-cockpit-reading-evidence">{row.source}</p>
          </Why>
        </li>
      ))}
    </ul>
  );
}
