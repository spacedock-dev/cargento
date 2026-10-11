/* shadcn native-select, Base UI flavour. CLI: shadcn@4.21.4.
   Registry: https://ui.shadcn.com/r/styles/base-nova/native-select.json
   Upstream content SHA-256: 17552c2df3b8f5ee44675979c3c29a02f48454e9204f2a02b64f4b7f28bdfc2c
   MIT; the full upstream notice ships in react-licenses.txt.
   The class and ref belong to the real select; the icon cannot intercept a choice.
   docs/design-shadcn-adoption.md#form-controls-layer owns the tuning. */
import type { ComponentProps } from 'react';
import { cn } from '../lib/utils';
import { fieldBase } from './input';

type NativeSelectProps = ComponentProps<'select'> & {
  appearance?: 'prompt' | 'stage' | 'direction' | 'gallery';
};
const surfaces = {
  prompt: 'block w-full py-0 ps-[12px] pe-[28px] font-medium',
  stage: 'inline-block w-full py-[6.4px] ps-[6.4px] pe-[28px] font-medium',
  direction: 'block w-full py-[6px] ps-[8px] pe-[28px]',
  gallery: 'inline-block w-full py-[4px] ps-[8px] pe-[28px] leading-[1.5]',
};

export function NativeSelect({ className, appearance = 'stage', ...props }: NativeSelectProps) {
  return (
    <div
      data-slot="native-select-wrapper"
      className={cn(
        'relative min-w-0 max-w-full',
        appearance === 'prompt' ? 'w-[18rem]' : 'w-full',
      )}
    >
      <select
        data-slot="native-select"
        className={cn(
          fieldBase,
          'appearance-none bg-muted text-foreground leading-[1.55] text-ellipsis',
          surfaces[appearance],
          className,
        )}
        {...props}
      />
      <svg
        data-slot="native-select-icon"
        aria-hidden="true"
        viewBox="0 0 10 10"
        width="10"
        height="10"
        fill="none"
        className="pointer-events-none absolute top-1/2 end-[8px] -translate-y-1/2 text-muted-foreground forced-colors:text-[CanvasText]"
      >
        <path d="m2 3.5 3 3 3-3" stroke="currentColor" strokeWidth="1.5" />
      </svg>
    </div>
  );
}
