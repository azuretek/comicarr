"use client";

import * as React from "react";
import { Tooltip as TooltipPrimitive } from "@base-ui/react/tooltip";

import { cn } from "@/lib/utils";

const TooltipProvider = ({
  delayDuration,
  ...props
}: TooltipPrimitive.Provider.Props & { delayDuration?: number }) => (
  <TooltipPrimitive.Provider delay={delayDuration} {...props} />
);

type LegacyTooltipProps = TooltipPrimitive.Root.Props<unknown> & {
  openDelay?: number;
  closeDelay?: number;
};

const Tooltip = ({
  openDelay: _openDelay,
  closeDelay: _closeDelay,
  ...props
}: LegacyTooltipProps) => <TooltipPrimitive.Root {...props} />;

type TooltipTriggerProps = TooltipPrimitive.Trigger.Props<unknown> & {
  asChild?: boolean;
};

const TooltipTrigger = React.forwardRef<HTMLElement, TooltipTriggerProps>(
  ({ asChild, children, ...props }, ref) => (
    <TooltipPrimitive.Trigger
      ref={ref}
      render={asChild ? children : undefined}
      {...props}
    >
      {asChild ? undefined : children}
    </TooltipPrimitive.Trigger>
  ),
);

const TooltipContent = React.forwardRef<
  HTMLDivElement,
  TooltipPrimitive.Popup.Props &
    Pick<
      TooltipPrimitive.Positioner.Props,
      "side" | "sideOffset" | "align" | "alignOffset"
    >
>(({ className, sideOffset = 4, side, align, alignOffset, ...props }, ref) => (
  <TooltipPrimitive.Portal>
    <TooltipPrimitive.Positioner
      className="isolate z-50"
      side={side}
      sideOffset={sideOffset}
      align={align}
      alignOffset={alignOffset}
    >
      <TooltipPrimitive.Popup
        ref={ref}
        className={cn(
          "z-50 overflow-hidden rounded-md bg-primary px-3 py-1.5 text-xs text-primary-foreground transition-[opacity,transform] data-starting-style:opacity-0 data-starting-style:scale-95 data-ending-style:opacity-0 data-ending-style:scale-95 origin-[--transform-origin]",
          className,
        )}
        {...props}
      />
    </TooltipPrimitive.Positioner>
  </TooltipPrimitive.Portal>
));
TooltipContent.displayName = "TooltipContent";

export { Tooltip, TooltipTrigger, TooltipContent, TooltipProvider };
