export function DisclosureChevron() {
  return (
    <svg
      data-slot="disclosure-chevron"
      aria-hidden="true"
      viewBox="0 0 10 10"
      width="10"
      height="10"
      fill="none"
      className="shrink-0 ml-[.45em] transition-transform duration-[var(--disclose-dur)] ease-[var(--disclose-ease)] in-aria-expanded:rotate-180 motion-reduce:transition-none"
    >
      <path d="m2 3.5 3 3 3-3" stroke="currentColor" strokeWidth="1.5" />
    </svg>
  );
}
