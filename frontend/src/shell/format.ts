/* The page's one duration spelling (`nextFormatDuration`): the two largest units, floored. Null for
   anything that is not a finite non-negative number, so a caller writes an absence rather than a
   figure it cannot support. */
export function formatDuration(seconds: unknown): string | null {
  if (typeof seconds !== 'number' || !Number.isFinite(seconds) || seconds < 0) return null;
  const whole = Math.floor(seconds);
  if (whole < 60) return `${whole}s`;
  if (whole < 3600) return `${Math.floor(whole / 60)}m`;
  if (whole < 86400) return `${Math.floor(whole / 3600)}h ${Math.floor((whole % 3600) / 60)}m`;
  return `${Math.floor(whole / 86400)}d ${Math.floor((whole % 86400) / 3600)}h`;
}
