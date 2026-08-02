/**
 * PROTOTYPE — floating variant switcher (#526). Hidden in production builds.
 */

import { useEffect } from "react";
import { useSearchParams } from "react-router-dom";
import { ChevronLeft, ChevronRight } from "lucide-react";

export type VariantKey = "A" | "B" | "C";

export const VARIANT_META: Record<VariantKey, string> = {
  A: "Sentry strip + Attention tab",
  B: "One-line bar + master-detail sheet",
  C: "Issue cards + dedicated route",
};

const ORDER: VariantKey[] = ["A", "B", "C"];

export function parseVariant(raw: string | null): VariantKey | null {
  if (!raw) return null;
  const u = raw.toUpperCase();
  if (u === "A" || u === "B" || u === "C") return u;
  return null;
}

export function PrototypeSwitcher() {
  if (import.meta.env.PROD) return null;

  const [params, setParams] = useSearchParams();
  const current = parseVariant(params.get("variant")) ?? "A";

  const setVariant = (v: VariantKey) => {
    setParams(
      (prev) => {
        const next = new URLSearchParams(prev);
        next.set("variant", v);
        return next;
      },
      { replace: true },
    );
  };

  const cycle = (dir: -1 | 1) => {
    const i = ORDER.indexOf(current);
    const next = ORDER[(i + dir + ORDER.length) % ORDER.length];
    setVariant(next);
  };

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const t = e.target as HTMLElement | null;
      if (
        t &&
        (t.tagName === "INPUT" ||
          t.tagName === "TEXTAREA" ||
          t.isContentEditable)
      ) {
        return;
      }
      if (e.key === "ArrowLeft") {
        e.preventDefault();
        setParams(
          (prev) => {
            const cur = parseVariant(prev.get("variant")) ?? "A";
            const i = ORDER.indexOf(cur);
            const nextV = ORDER[(i - 1 + ORDER.length) % ORDER.length];
            const next = new URLSearchParams(prev);
            next.set("variant", nextV);
            return next;
          },
          { replace: true },
        );
      }
      if (e.key === "ArrowRight") {
        e.preventDefault();
        setParams(
          (prev) => {
            const cur = parseVariant(prev.get("variant")) ?? "A";
            const i = ORDER.indexOf(cur);
            const nextV = ORDER[(i + 1) % ORDER.length];
            const next = new URLSearchParams(prev);
            next.set("variant", nextV);
            return next;
          },
          { replace: true },
        );
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [setParams]);

  return (
    <div
      className="fixed bottom-4 left-1/2 z-[100] flex -translate-x-1/2 items-center gap-2 rounded-full border px-2 py-1.5 shadow-lg"
      style={{
        background: "var(--background)",
        borderColor: "var(--border)",
        boxShadow: "0 8px 30px color-mix(in oklab, black 25%, transparent)",
      }}
      role="group"
      aria-label="Prototype variant switcher"
    >
      <button
        type="button"
        className="rounded-full p-1.5 hover:bg-muted"
        onClick={() => cycle(-1)}
        aria-label="Previous variant"
      >
        <ChevronLeft className="h-4 w-4" />
      </button>
      <div className="min-w-[220px] text-center font-mono text-[11px]">
        <span className="font-semibold">{current}</span>
        <span className="text-muted-foreground"> — {VARIANT_META[current]}</span>
      </div>
      <button
        type="button"
        className="rounded-full p-1.5 hover:bg-muted"
        onClick={() => cycle(1)}
        aria-label="Next variant"
      >
        <ChevronRight className="h-4 w-4" />
      </button>
    </div>
  );
}
