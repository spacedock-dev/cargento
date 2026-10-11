/* shadcn Alert, Base UI flavour. CLI: shadcn@4.21.4.
   Registry: https://ui.shadcn.com/r/styles/base-nova/alert.json
   Upstream content SHA-256: f253568242c1c69b343f12474002fdbe229f603158171c59e21c491ab79f2e6e
   MIT; the full upstream notice ships in react-licenses.txt.
   Sessions recipes preserve the measured cascade; docs/design-shadcn-adoption.md#sessions-layer. */
import type { ComponentProps } from 'react';
import { cva, type VariantProps } from 'class-variance-authority';
import { cn } from '@/lib/utils';

const alertVariants = cva('block', {
  variants: {
    variant: {
      'session-health':
        'px-[16px] py-[14px] [border-left:3px_solid_var(--amber)] bg-card text-muted-foreground text-body leading-[1.5]',
      'answer-failure': 'p-0 text-foreground text-label leading-[normal]',
    },
  },
  defaultVariants: { variant: 'answer-failure' },
});
function Alert({
  className,
  variant,
  as: Tag = 'div',
  role = 'status',
  ...props
}: ComponentProps<'div'> &
  VariantProps<typeof alertVariants> & { readonly as?: 'div' | 'aside' | 'p' }) {
  return (
    <Tag
      data-slot="alert"
      data-variant={variant ?? 'answer-failure'}
      role={role}
      className={cn(alertVariants({ variant }), className)}
      {...props}
    />
  );
}
export { Alert, alertVariants };
