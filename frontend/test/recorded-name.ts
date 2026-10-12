// The retired page's recordings precede the owner's Compass rename. Project only
// those three spellings on the recorded side; keep the live side and fixtures exact.
const names = [
  ['Cargento', 'Compass'],
  ['CARGENTO', 'COMPASS'],
  ['cargento', 'compass'],
] as const;

export function recordedName(value: unknown, original = false): unknown {
  if (typeof value === 'string') {
    for (const [before, after] of names)
      value = (value as string).replaceAll(original ? after : before, original ? before : after);
    return value;
  }
  if (Array.isArray(value)) return value.map((item) => recordedName(item, original));
  if (value && typeof value === 'object')
    return Object.fromEntries(
      Object.entries(value).map(([key, item]) => [
        recordedName(key, original),
        recordedName(item, original),
      ]),
    );
  return value;
}
