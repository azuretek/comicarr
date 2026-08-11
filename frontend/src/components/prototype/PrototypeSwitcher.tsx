/**
 * PROTOTYPE ONLY — floating bar to flip ?variant= on a throwaway surface.
 * Hidden outside Vite DEV builds. Do not ship as product UI.
 */
import { useCallback, useEffect } from "react";
import { useSearchParams } from "react-router-dom";
import { ChevronLeft, ChevronRight } from "lucide-react";

export type PrototypeVariantMeta = {
  key: string;
  name: string;
};

type PrototypeSwitcherProps = {
  variants: PrototypeVariantMeta[];
  /** search-param name; defaults to "variant" */
  param?: string;
};

export function PrototypeSwitcher({
  variants,
  param = "variant",
}: PrototypeSwitcherProps) {
  const [searchParams, setSearchParams] = useSearchParams();

  const keys = variants.map((v) => v.key);
  const currentKey = searchParams.get(param) ?? keys[0] ?? "A";
  const index = Math.max(0, keys.indexOf(currentKey));
  const current = variants[index] ?? variants[0];

  const go = useCallback(
    (nextIndex: number) => {
      if (variants.length === 0) return;
      const wrapped = (nextIndex + variants.length) % variants.length;
      const next = variants[wrapped];
      setSearchParams(
        (prev) => {
          const nextParams = new URLSearchParams(prev);
          nextParams.set(param, next.key);
          return nextParams;
        },
        { replace: true },
      );
    },
    [variants, param, setSearchParams],
  );

  useEffect(() => {
    if (!import.meta.env.DEV || variants.length === 0) return;
    const onKey = (event: KeyboardEvent) => {
      const target = event.target as HTMLElement | null;
      if (
        target &&
        (target.tagName === "INPUT" ||
          target.tagName === "TEXTAREA" ||
          target.isContentEditable)
      ) {
        return;
      }
      if (event.key === "ArrowLeft") {
        event.preventDefault();
        go(index - 1);
      } else if (event.key === "ArrowRight") {
        event.preventDefault();
        go(index + 1);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [go, index, variants.length]);

  if (!import.meta.env.DEV || variants.length === 0 || !current) return null;

  return (
    <div
      className="fixed bottom-4 left-1/2 z-[100] flex -translate-x-1/2 items-center gap-1 rounded-full border px-1.5 py-1 shadow-lg"
      style={{
        borderColor: "var(--border)",
        background: "color-mix(in oklab, var(--card) 92%, black)",
        boxShadow: "0 8px 28px color-mix(in oklab, black 35%, transparent)",
      }}
      role="group"
      aria-label="Prototype variant switcher"
    >
      <button
        type="button"
        onClick={() => go(index - 1)}
        className="grid size-8 place-items-center rounded-full hover:bg-secondary"
        aria-label="Previous variant"
      >
        <ChevronLeft className="size-4" />
      </button>
      <div className="min-w-[11rem] px-2 text-center">
        <div className="text-[10px] uppercase tracking-[0.08em] text-muted-foreground">
          prototype
        </div>
        <div className="text-[12.5px] font-medium leading-tight">
          {current.key} — {current.name}
        </div>
      </div>
      <button
        type="button"
        onClick={() => go(index + 1)}
        className="grid size-8 place-items-center rounded-full hover:bg-secondary"
        aria-label="Next variant"
      >
        <ChevronRight className="size-4" />
      </button>
    </div>
  );
}

