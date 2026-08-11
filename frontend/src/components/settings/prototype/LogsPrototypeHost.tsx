/**
 * PROTOTYPE HOST — Settings → Logs surface variants for wayfinder #616.
 *
 * Question: What should the Settings → Logs surface look and behave like?
 * Three structurally different answers, switchable via ?variant=A|B|C.
 *
 * Throwaway: not production. DEV-only entry from SettingsPage.
 */
import { useSearchParams } from "react-router-dom";
import { PrototypeSwitcher } from "@/components/prototype/PrototypeSwitcher";
import { usePrototypeVariant } from "@/components/prototype/usePrototypeVariant";
import { LogsVariantA } from "./LogsVariantA";
import { LogsVariantB } from "./LogsVariantB";
import { LogsVariantC } from "./LogsVariantC";
import { LOGS_PROTOTYPE_VARIANTS } from "./logsMeta";

export function LogsPrototypeHost() {
  const variant = usePrototypeVariant([...LOGS_PROTOTYPE_VARIANTS]);
  const [searchParams, setSearchParams] = useSearchParams();
  const simulateOverride = searchParams.get("override") !== "0";

  const setSimulateOverride = (on: boolean) => {
    setSearchParams(
      (prev) => {
        const next = new URLSearchParams(prev);
        if (on) {
          next.delete("override");
        } else {
          next.set("override", "0");
        }
        return next;
      },
      { replace: true },
    );
  };

  return (
    <>
      <div
        className="mb-4 flex flex-wrap items-center justify-between gap-2 rounded-[6px] border border-dashed px-3 py-2"
        style={{ borderColor: "var(--border)" }}
      >
        <div className="text-[12px] text-muted-foreground">
          <strong className="text-foreground">PROTOTYPE</strong> — mock data,
          no API writes. Use ← → or the bar below to compare variants.
        </div>
        <label className="flex cursor-pointer items-center gap-2 text-[12.5px]">
          <input
            type="checkbox"
            checked={simulateOverride}
            onChange={(e) => setSimulateOverride(e.target.checked)}
            className="size-3.5 accent-[var(--primary)]"
          />
          Simulate CLI/env override
        </label>
      </div>

      {variant === "A" && (
        <LogsVariantA
          key={`A-${simulateOverride}`}
          simulateOverride={simulateOverride}
        />
      )}
      {variant === "B" && (
        <LogsVariantB
          key={`B-${simulateOverride}`}
          simulateOverride={simulateOverride}
        />
      )}
      {variant === "C" && (
        <LogsVariantC
          key={`C-${simulateOverride}`}
          simulateOverride={simulateOverride}
        />
      )}

      <PrototypeSwitcher variants={[...LOGS_PROTOTYPE_VARIANTS]} />
    </>
  );
}
