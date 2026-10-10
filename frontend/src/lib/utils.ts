import { type ClassValue, clsx } from 'clsx';
import { extendTailwindMerge } from 'tailwind-merge';

/* Cargento's own type steps and radii are not Tailwind's defaults, so tailwind-merge has to be told about
   them: unconfigured it reads `text-body` as a colour and drops it when a colour class follows. */
const twMerge = extendTailwindMerge({
  extend: {
    classGroups: {
      'font-size': [{ text: ['label', 'body', 'value', 'head', 'hero'] }],
      rounded: [{ rounded: ['control', 'card', 'shell', 'pill'] }],
    },
  },
});

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}
