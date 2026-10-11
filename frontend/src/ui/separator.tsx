/* shadcn Separator, Base UI flavour. CLI: shadcn@4.21.4.
   Registry: https://ui.shadcn.com/r/styles/base-nova/separator.json
   Upstream content SHA-256: 9a80ff8c110e0c55489509f4f82ebcc929c0174b59544047147b7134f86a54e7
   MIT; the full upstream notice ships in react-licenses.txt.
   Sessions recipes preserve the measured cascade; docs/design-shadcn-adoption.md#sessions-layer. */
import { Separator as SeparatorPrimitive } from '@base-ui/react/separator';
import { cn } from '@/lib/utils';

function Separator({ className, orientation = 'horizontal', ...props }: SeparatorPrimitive.Props) {
  return (
    <SeparatorPrimitive
      data-slot="separator"
      orientation={orientation}
      className={cn(
        'block shrink-0 bg-[var(--rule)] data-[orientation=horizontal]:h-px data-[orientation=horizontal]:w-full data-[orientation=vertical]:w-px data-[orientation=vertical]:self-stretch',
        className,
      )}
      {...props}
    />
  );
}
export { Separator };
