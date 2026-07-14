import * as React from "react";
import { PreviewCard as HoverCardPrimitive } from "@base-ui/react/preview-card";

import { cn } from "@/lib/utils";

type HoverCardTiming = {
  delay?: number;
  closeDelay?: number;
};

const HoverCardTimingContext = React.createContext<HoverCardTiming>({});

const HoverCard = ({
  openDelay,
  closeDelay,
  children,
  ...props
}: HoverCardPrimitive.Root.Props & {
  openDelay?: number;
  closeDelay?: number;
}) => (
  <HoverCardTimingContext.Provider value={{ delay: openDelay, closeDelay }}>
    <HoverCardPrimitive.Root {...props}>{children}</HoverCardPrimitive.Root>
  </HoverCardTimingContext.Provider>
);

const HoverCardTrigger = React.forwardRef<
  HTMLAnchorElement,
  Omit<HoverCardPrimitive.Trigger.Props, "render"> & { asChild?: boolean }
>(({ asChild, children, delay, closeDelay, ...props }, ref) => {
  const timing = React.useContext(HoverCardTimingContext);

  return (
    <HoverCardPrimitive.Trigger
      ref={ref}
      delay={delay ?? timing.delay}
      closeDelay={closeDelay ?? timing.closeDelay}
      render={asChild && React.isValidElement(children) ? children : undefined}
      {...props}
    >
      {asChild ? undefined : children}
    </HoverCardPrimitive.Trigger>
  );
});
HoverCardTrigger.displayName = "HoverCardTrigger";

const HoverCardContent = React.forwardRef<
  HTMLDivElement,
  Omit<
    HoverCardPrimitive.Popup.Props,
    "side" | "sideOffset" | "align" | "alignOffset"
  > &
    Pick<
      HoverCardPrimitive.Positioner.Props,
      "side" | "sideOffset" | "align" | "alignOffset"
    >
>(
  (
    {
      className,
      align = "center",
      sideOffset = 4,
      side,
      alignOffset,
      ...props
    },
    ref,
  ) => (
    <HoverCardPrimitive.Portal>
      <HoverCardPrimitive.Positioner
        side={side}
        align={align}
        sideOffset={sideOffset}
        alignOffset={alignOffset}
      >
        <HoverCardPrimitive.Popup
          ref={ref}
          className={cn(
            "z-50 w-64 rounded-md border bg-popover p-4 text-popover-foreground shadow-md outline-none transition-[opacity,transform] data-starting-style:scale-95 data-starting-style:opacity-0 data-ending-style:scale-95 data-ending-style:opacity-0 origin-(--transform-origin)",
            className,
          )}
          {...props}
        />
      </HoverCardPrimitive.Positioner>
    </HoverCardPrimitive.Portal>
  ),
);
HoverCardContent.displayName = "HoverCardContent";

export { HoverCard, HoverCardTrigger, HoverCardContent };
