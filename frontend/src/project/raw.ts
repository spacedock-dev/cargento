import { isRecord, type Row } from '../observed/values';

/* The legacy page reads a payload with JavaScript's own coercions, and the project views stand on
   payloads a collector or an older server wrote, so the port keeps the coercions rather than replacing
   them with a stricter reading that would draw a different page for the same board. These are the
   idioms, named once. */

export type { Row };
export { isRecord };

/** `String(value || "")`: every falsy value is the empty string, `0` included. */
export function text(value: unknown): string {
  return String(value || '');
}

/** `String(value == null ? "" : value)`: only null and undefined are absent. */
export function textOrEmpty(value: unknown): string {
  return String(value == null ? '' : value);
}

/** `Array.isArray(value) ? value : []`, with no filter: the legacy loops tolerate a non-record member. */
export function list(value: unknown): readonly unknown[] {
  return Array.isArray(value) ? value : [];
}

/** A record's own field, or undefined for a non-record: `value && value.field` without the throw. */
export function field(value: unknown, name: string): unknown {
  return isRecord(value) ? value[name] : undefined;
}

/** `value && value.field || ""` as a string: the legacy `String(row && row.field || "")`. */
export function fieldText(value: unknown, name: string): string {
  return text(field(value, name));
}

/** `Number(value)`, as written in the legacy sorts: NaN for a non-number. */
export function numeric(value: unknown): number {
  return Number(value);
}

/** `Number(value || 0)`. */
export function numericOr0(value: unknown): number {
  return Number(value || 0);
}

export function record(value: unknown): Row {
  return isRecord(value) ? value : {};
}

/** The rows of a list that are records, in order. */
export function recordsOf(value: unknown): Row[] {
  return Array.isArray(value) ? value.filter(isRecord) : [];
}

/** `localeCompare` as the legacy sorts call it, so two machines order one board the same way. */
export function localeCompare(left: string, right: string): number {
  return left.localeCompare(right);
}

/** A quiet live session has no fresh evidence after one complete token-rate window (ten minutes). */
export const PROJECT_STALLED_SEC = 600;
