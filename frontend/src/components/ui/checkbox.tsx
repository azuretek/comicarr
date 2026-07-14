import * as React from "react";
import { Checkbox as CheckboxPrimitive } from "@base-ui/react/checkbox";
import { Check } from "lucide-react";

import { cn } from "@/lib/utils";

type CheckboxProps = Omit<
  CheckboxPrimitive.Root.Props,
  "checked" | "onCheckedChange"
> & {
  checked?: boolean | "indeterminate";
  onCheckedChange?: (checked: boolean) => void;
  onChange?: () => void;
};

const Checkbox = React.forwardRef<HTMLButtonElement, CheckboxProps>(
  ({ className, checked, onCheckedChange, onChange, ...props }, ref) => (
    <CheckboxPrimitive.Root
      ref={ref}
      checked={checked === "indeterminate" ? false : checked}
      onCheckedChange={(value) => onCheckedChange?.(value === true)}
      onClick={onChange}
      className={cn(
        "grid place-content-center peer h-4 w-4 shrink-0 rounded-sm border border-border shadow focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring data-disabled:cursor-not-allowed data-disabled:opacity-50 data-checked:bg-primary data-checked:text-primary-foreground data-checked:border-primary",
        className,
      )}
      {...props}
    >
      <CheckboxPrimitive.Indicator
        className={cn("grid place-content-center text-current")}
      >
        <Check className="h-4 w-4" />
      </CheckboxPrimitive.Indicator>
    </CheckboxPrimitive.Root>
  ),
);
Checkbox.displayName = "Checkbox";

export { Checkbox };
