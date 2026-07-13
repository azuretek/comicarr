"use client";

import * as React from "react";
import { Popover as PopoverPrimitive } from "@base-ui/react/popover";

import { cn } from "@/lib/utils";

const Popover = PopoverPrimitive.Root;

const PopoverTrigger = PopoverPrimitive.Trigger;

const PopoverAnchor = React.Fragment;

const PopoverContent = React.forwardRef<
  HTMLDivElement,
  Omit<
    PopoverPrimitive.Popup.Props,
    "side" | "sideOffset" | "align" | "alignOffset"
  > &
    Pick<
      PopoverPrimitive.Positioner.Props,
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
    <PopoverPrimitive.Portal>
      <PopoverPrimitive.Positioner
        side={side}
        align={align}
        sideOffset={sideOffset}
        alignOffset={alignOffset}
      >
        <PopoverPrimitive.Popup
          ref={ref}
          className={cn(
            "z-50 w-72 rounded-md border bg-popover p-4 text-popover-foreground shadow-md outline-none transition-[opacity,transform] data-starting-style:scale-95 data-starting-style:opacity-0 data-ending-style:scale-95 data-ending-style:opacity-0 origin-[--transform-origin]",
            className,
          )}
          {...props}
        />
      </PopoverPrimitive.Positioner>
    </PopoverPrimitive.Portal>
  ),
);
PopoverContent.displayName = "PopoverContent";

export { Popover, PopoverTrigger, PopoverContent, PopoverAnchor };
