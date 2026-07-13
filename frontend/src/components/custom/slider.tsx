"use client";

import { cn } from "@/lib/utils";
import { Slider as SliderPrimitive } from "@base-ui/react/slider";
import * as React from "react";

function Slider({
  className,
  ...props
}: SliderPrimitive.Root.Props) {
  const value = props.value ?? props.defaultValue ?? props.min ?? 0;
  const thumbCount = Array.isArray(value) ? value.length : 1;

  return (
    <SliderPrimitive.Root
      data-slot="slider"
      className={cn(
        "relative flex w-full touch-none items-center select-none",
        className,
      )}
      {...props}
    >
      <SliderPrimitive.Control className="relative flex w-full touch-none items-center select-none">
      <SliderPrimitive.Track className="bg-secondary relative h-2 w-full grow overflow-hidden rounded-full">
        <SliderPrimitive.Indicator className="bg-primary absolute h-full" />
      {Array.from({ length: thumbCount }, (_, index) => (
        <React.Fragment key={index}>
          <SliderPrimitive.Thumb index={index} className="border-primary bg-background focus-visible:border-ring focus-visible:ring-ring/50 block h-4 w-4 rounded-full border-2 transition-all outline-none focus-visible:ring-[3px] disabled:pointer-events-none disabled:opacity-50" />
        </React.Fragment>
      ))}</SliderPrimitive.Track></SliderPrimitive.Control>
    </SliderPrimitive.Root>
  );
}

export { Slider };
