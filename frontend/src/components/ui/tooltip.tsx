"use client";

import * as React from "react";
import { Tooltip as TooltipPrimitive } from "@base-ui/react/tooltip";

import { cn } from "@/lib/utils";

type TooltipTiming = {
  delay?: number;
  closeDelay?: number;
  disableHoverablePopup?: boolean;
};

const TooltipTimingContext = React.createContext<TooltipTiming>({});

const TooltipProvider = ({
  delay,
  delayDuration,
  closeDelay,
  disableHoverableContent,
  ...props
}: TooltipPrimitive.Provider.Props & {
  delayDuration?: number;
  disableHoverableContent?: boolean;
}) => (
  <TooltipTimingContext.Provider
    value={{
      delay: delayDuration ?? delay,
      closeDelay,
      disableHoverablePopup: disableHoverableContent,
    }}
  >
    <TooltipPrimitive.Provider
      delay={delayDuration ?? delay}
      closeDelay={closeDelay}
      {...props}
    />
  </TooltipTimingContext.Provider>
);

type LegacyTooltipProps = TooltipPrimitive.Root.Props<unknown> & {
  openDelay?: number;
  closeDelay?: number;
  delayDuration?: number;
  disableHoverableContent?: boolean;
};

const Tooltip = ({
  openDelay,
  closeDelay,
  delayDuration,
  disableHoverableContent,
  disableHoverablePopup,
  children,
  ...props
}: LegacyTooltipProps) => {
  const timing = React.useContext(TooltipTimingContext);

  return (
    <TooltipTimingContext.Provider
      value={{
        delay: openDelay ?? delayDuration ?? timing.delay,
        closeDelay: closeDelay ?? timing.closeDelay,
        disableHoverablePopup:
          disableHoverablePopup ??
          disableHoverableContent ??
          timing.disableHoverablePopup,
      }}
    >
      <TooltipPrimitive.Root
        disableHoverablePopup={
          disableHoverablePopup ??
          disableHoverableContent ??
          timing.disableHoverablePopup
        }
        {...props}
      >
        {children}
      </TooltipPrimitive.Root>
    </TooltipTimingContext.Provider>
  );
};

type TooltipTriggerProps = Omit<
  TooltipPrimitive.Trigger.Props<unknown>,
  "render"
> & {
  asChild?: boolean;
};

const TooltipTrigger = React.forwardRef<HTMLButtonElement, TooltipTriggerProps>(
  ({ asChild, children, delay, closeDelay, ...props }, ref) => {
    const timing = React.useContext(TooltipTimingContext);

    return (
      <TooltipPrimitive.Trigger
        ref={ref}
        delay={delay ?? timing.delay}
        closeDelay={closeDelay ?? timing.closeDelay}
        render={
          asChild && React.isValidElement(children) ? children : undefined
        }
        {...props}
      >
        {asChild ? undefined : children}
      </TooltipPrimitive.Trigger>
    );
  },
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
          "z-50 overflow-hidden rounded-md bg-primary px-3 py-1.5 text-xs text-primary-foreground transition-[opacity,transform] data-starting-style:opacity-0 data-starting-style:scale-95 data-ending-style:opacity-0 data-ending-style:scale-95 origin-(--transform-origin)",
          className,
        )}
        {...props}
      />
    </TooltipPrimitive.Positioner>
  </TooltipPrimitive.Portal>
));
TooltipContent.displayName = "TooltipContent";

export { Tooltip, TooltipTrigger, TooltipContent, TooltipProvider };
