import type { SVGProps } from 'react';

/* The two chevrons the accordion and the native select draw. shadcn's own files import them from lucide-react,
   which is a package for hundreds of icons; Cargento draws two, so they are inline. */
const base = {
  viewBox: '0 0 24 24',
  width: 16,
  height: 16,
  fill: 'none',
  stroke: 'currentColor',
  strokeWidth: 2,
  strokeLinecap: 'round',
  strokeLinejoin: 'round',
} as const;

export function ChevronDownIcon(props: SVGProps<SVGSVGElement>) {
  return (
    <svg {...base} {...props}>
      <path d="m6 9 6 6 6-6" />
    </svg>
  );
}

export function ChevronUpIcon(props: SVGProps<SVGSVGElement>) {
  return (
    <svg {...base} {...props}>
      <path d="m18 15-6-6-6 6" />
    </svg>
  );
}
