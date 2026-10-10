export function DisclosureChevron() {
  return (
    <svg
      data-slot="disclosure-chevron"
      aria-hidden="true"
      viewBox="2 2 6 6"
      width=".4em"
      height=".4em"
      fill="none"
      className="overflow-visible shrink-0 ms-[.45em] transition-transform duration-[var(--disclose-dur)] ease-[var(--disclose-ease)] in-aria-expanded:rotate-180 motion-reduce:transition-none"
    >
      <path d="m2 3.5 3 3 3-3" stroke="currentColor" strokeWidth="1.5" />
    </svg>
  );
}
