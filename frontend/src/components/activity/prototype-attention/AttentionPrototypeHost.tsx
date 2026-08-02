/**
 * PROTOTYPE host for #526 — bounded band preview + triage surface.
 *
 * Question: What do the bounded band preview and dedicated triage surface look like?
 * Three structural variants on /activity?variant=A|B|C (dev only entry from ActivityPage).
 */

import { VariantA } from "./VariantA";
import { VariantB } from "./VariantB";
import { VariantC } from "./VariantC";
import { PrototypeSwitcher, type VariantKey } from "./PrototypeSwitcher";

export function AttentionPrototypeHost({ variant }: { variant: VariantKey }) {
  return (
    <>
      {variant === "A" && <VariantA />}
      {variant === "B" && <VariantB />}
      {variant === "C" && <VariantC />}
      <PrototypeSwitcher />
      <div
        className="pointer-events-none fixed bottom-16 left-1/2 z-[99] -translate-x-1/2 rounded-full border px-3 py-1 font-mono text-[10px] text-muted-foreground"
        style={{
          borderColor: "var(--border)",
          background: "var(--background)",
        }}
      >
        PROTOTYPE · mock data · ← → switch · not production
      </div>
    </>
  );
}
