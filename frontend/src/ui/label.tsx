/* shadcn label, Base UI flavour. CLI: shadcn@4.21.4.
   Registry: https://ui.shadcn.com/r/styles/base-nova/label.json
   Upstream content SHA-256: b3b7b21d2877838fc73713df48a47248392de04a3b3fafa8961369f33ab14530
   MIT; the full upstream notice ships in react-licenses.txt.
   Surface labels keep their inherited typography and layout, and gain native associations.
   docs/design-shadcn-adoption.md#form-controls-layer owns the tuning. */
import type { ComponentProps } from 'react';
import { cn } from '../lib/utils';

export function Label({ className, ...props }: ComponentProps<'label'>) {
  return <label data-slot="label" className={cn('cursor-default', className)} {...props} />;
}
