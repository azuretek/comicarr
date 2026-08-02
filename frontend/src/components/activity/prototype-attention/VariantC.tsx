/**
 * PROTOTYPE Variant C — issue cards on the band + dedicated /attention route.
 *
 * Band: top 5 cards ranked by newest, stage-coloured (failed vs manual_review).
 * Height ceiling: fixed card row (~168px). Fold: "See all N →" deep-links.
 * Triage: own "route" (mock) with age facet + stage split — answers "do stages
 * read differently" and "not Download History".
 */

import { useMemo, useState } from "react";
import { AlertTriangle, ArrowLeft } from "lucide-react";
import PageHeader, { Tab, TabRow } from "@/components/layout/PageHeader";
import {
  MOCK_GROUPS,
  TOTAL_GROUPS,
  actionLabel,
  rankByNewest,
  type MockGroup,
} from "./mockData";

const PREVIEW_CAP = 5;

export const VARIANT_C_NAME = "Issue cards + dedicated route";

export function VariantC() {
  const [route, setRoute] = useState<"activity" | "attention">("activity");
  const ranked = useMemo(() => rankByNewest(MOCK_GROUPS), []);

  if (route === "attention") {
    return <AttentionRoute groups={ranked} onBack={() => setRoute("activity")} />;
  }

  const preview = ranked.slice(0, PREVIEW_CAP);
  const more = ranked.length - preview.length;

  return (
    <div className="page-transition flex h-full min-h-0 flex-col">
      <PageHeader
        title="Activity"
        meta="PROTOTYPE C — dedicated attention route, cards on band"
      />
      <TabRow>
        <Tab active label="Timeline" onClick={() => undefined} />
        <Tab active={false} label="Direct Downloads" onClick={() => undefined} />
        <Tab active={false} label="Download History" onClick={() => undefined} />
      </TabRow>

      <section
        className="shrink-0 border-b"
        style={{
          borderColor: "var(--border)",
          maxHeight: 176,
          overflow: "hidden",
          background:
            "var(--status-error-bg, color-mix(in oklab, var(--status-error) 8%, transparent))",
        }}
      >
        <div className="flex items-center gap-2 px-5 pt-3 pb-2">
          <AlertTriangle
            className="h-3.5 w-3.5"
            style={{ color: "var(--status-error)" }}
          />
          <span
            className="font-mono text-[11px] uppercase tracking-[0.1em]"
            style={{ color: "var(--status-error)" }}
          >
            {TOTAL_GROUPS} problems
          </span>
          <span className="font-mono text-[10px] text-muted-foreground">
            ranked newest · stage colour
          </span>
          <button
            type="button"
            onClick={() => setRoute("attention")}
            className="ml-auto font-mono text-[11px]"
            style={{ color: "var(--status-error)" }}
          >
            See all {TOTAL_GROUPS} →
          </button>
        </div>
        <div className="flex gap-2 overflow-x-auto px-5 pb-3">
          {preview.map((g) => (
            <Card key={g.group_key} group={g} onOpen={() => setRoute("attention")} />
          ))}
          {more > 0 && (
            <button
              type="button"
              onClick={() => setRoute("attention")}
              className="flex h-[104px] w-[120px] shrink-0 flex-col items-center justify-center rounded border border-dashed font-mono text-[11px] text-muted-foreground"
              style={{ borderColor: "var(--border)" }}
            >
              +{more}
              <span className="mt-1">more</span>
            </button>
          )}
        </div>
      </section>

      <div className="min-h-0 flex-1 overflow-auto px-5 py-4">
        <p className="mb-3 font-mono text-[10px] uppercase tracking-wider text-muted-foreground">
          Timeline — band height capped at one card row
        </p>
        {Array.from({ length: 10 }, (_, i) => (
          <div
            key={i}
            className="border-b py-2 text-[13px] text-muted-foreground"
            style={{ borderColor: "var(--border)" }}
          >
            story row {i + 1}
          </div>
        ))}
      </div>
    </div>
  );
}

function stageOf(g: MockGroup): "failed" | "manual_review" {
  return g.available_actions.includes("retry") ? "failed" : "manual_review";
}

function Card({ group, onOpen }: { group: MockGroup; onOpen: () => void }) {
  const stage = stageOf(group);
  const color =
    stage === "failed" ? "var(--status-error)" : "var(--status-paused)";
  return (
    <button
      type="button"
      onClick={onOpen}
      className="flex h-[104px] w-[200px] shrink-0 flex-col rounded border bg-background p-2.5 text-left"
      style={{ borderColor: "var(--border)" }}
    >
      <div className="flex items-center gap-1.5">
        <span
          className="h-1.5 w-1.5 rounded-full"
          style={{ background: color }}
        />
        <span
          className="font-mono text-[9px] uppercase tracking-wider"
          style={{ color }}
        >
          {stage === "failed" ? "failed" : "review"}
        </span>
        <span className="ml-auto font-mono text-[11px] font-semibold">
          ×{group.member_count}
        </span>
      </div>
      <div className="mt-1.5 line-clamp-2 text-[12px] font-medium leading-snug">
        {group.series_label}
      </div>
      <div className="mt-auto line-clamp-2 text-[10px] text-muted-foreground">
        {group.reason_phrase}
      </div>
    </button>
  );
}

function AttentionRoute({
  groups,
  onBack,
}: {
  groups: MockGroup[];
  onBack: () => void;
}) {
  const [stageFilter, setStageFilter] = useState<"all" | "failed" | "manual_review">(
    "all",
  );
  const [age, setAge] = useState<"all" | "7d" | "30d">("all");
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [toast, setToast] = useState<string | null>(null);

  const filtered = groups.filter((g) => {
    const st = stageOf(g);
    if (stageFilter !== "all" && st !== stageFilter) return false;
    if (age === "7d" && g.newest_updated_at < "2026-07-04") return false;
    if (age === "30d" && g.newest_updated_at < "2026-06-11") return false;
    return true;
  });

  const memberN = filtered
    .filter((g) => selected.has(g.group_key))
    .reduce((n, g) => n + g.member_count, 0);

  return (
    <div className="page-transition flex h-full min-h-0 flex-col">
      <PageHeader
        title="Needs attention"
        meta="PROTOTYPE C route · /activity/attention · actionable only"
        actions={
          <button
            type="button"
            onClick={onBack}
            className="inline-flex items-center gap-1 rounded border px-2 py-1 font-mono text-[11px]"
            style={{ borderColor: "var(--border)" }}
          >
            <ArrowLeft className="h-3 w-3" /> Activity
          </button>
        }
      />

      <div
        className="flex shrink-0 flex-wrap items-center gap-2 border-b px-5 py-2.5"
        style={{ borderColor: "var(--border)" }}
      >
        {(
          [
            ["all", "All stages"],
            ["failed", "Failed"],
            ["manual_review", "Manual review"],
          ] as const
        ).map(([id, label]) => (
          <button
            key={id}
            type="button"
            onClick={() => setStageFilter(id)}
            className="rounded border px-2 py-1 font-mono text-[10px]"
            style={{
              borderColor: "var(--border)",
              background:
                stageFilter === id
                  ? "color-mix(in oklab, var(--primary) 12%, transparent)"
                  : undefined,
            }}
          >
            {label}
          </button>
        ))}
        <select
          className="rounded border bg-transparent px-2 py-1 font-mono text-[11px]"
          style={{ borderColor: "var(--border)" }}
          value={age}
          onChange={(e) => setAge(e.target.value as typeof age)}
        >
          <option value="all">Any age</option>
          <option value="7d">Last 7 days</option>
          <option value="30d">Last 30 days</option>
        </select>
        <span className="font-mono text-[10px] text-muted-foreground">
          vs Download History: only unresolved · group actions · no import ledger
        </span>
      </div>

      {selected.size > 0 && (
        <div
          className="flex shrink-0 items-center gap-2 border-b px-5 py-2"
          style={{
            borderColor: "var(--border)",
            background: "color-mix(in oklab, var(--primary) 8%, transparent)",
          }}
        >
          <span className="font-mono text-[11px]">
            {selected.size} groups · ~{memberN} issues
            {memberN > 25 ? " · cap 25" : ""}
          </span>
          <button
            type="button"
            className="rounded border px-2 py-1 font-mono text-[10px]"
            style={{ borderColor: "var(--border)" }}
            onClick={() => {
              setToast(
                `Search again · ${Math.min(25, memberN)} of ${memberN}`,
              );
              setSelected(new Set());
            }}
          >
            Search again
          </button>
          <button
            type="button"
            className="rounded border px-2 py-1 font-mono text-[10px]"
            style={{ borderColor: "var(--border)" }}
            onClick={() => {
              setToast(
                `Stop wanting confirm would open · ${Math.min(25, memberN)} issues`,
              );
            }}
          >
            Stop wanting…
          </button>
        </div>
      )}

      {toast && (
        <div className="px-5 py-1.5 font-mono text-[11px] text-muted-foreground">
          {toast}
        </div>
      )}

      <div className="min-h-0 flex-1 overflow-auto p-5">
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {filtered.map((g) => {
            const stage = stageOf(g);
            const color =
              stage === "failed"
                ? "var(--status-error)"
                : "var(--status-paused)";
            return (
              <div
                key={g.group_key}
                className="rounded border p-3"
                style={{ borderColor: "var(--border)" }}
              >
                <div className="flex items-start gap-2">
                  <input
                    type="checkbox"
                    checked={selected.has(g.group_key)}
                    onChange={() => {
                      setSelected((prev) => {
                        const next = new Set(prev);
                        if (next.has(g.group_key)) next.delete(g.group_key);
                        else next.add(g.group_key);
                        return next;
                      });
                    }}
                    className="mt-1"
                  />
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-2">
                      <span
                        className="font-mono text-[9px] uppercase"
                        style={{ color }}
                      >
                        {stage === "failed" ? "failed" : "manual review"}
                      </span>
                      <span className="ml-auto font-mono text-[12px]">
                        ×{g.member_count}
                      </span>
                    </div>
                    <div className="mt-1 text-[13px] font-medium">
                      {g.series_label}
                    </div>
                    <div className="mt-1 text-[12px] text-muted-foreground">
                      {g.reason_phrase}
                    </div>
                    <div className="mt-2 flex flex-wrap gap-1">
                      {g.available_actions.map((a) => (
                        <span
                          key={a}
                          className="rounded border px-1.5 py-0.5 font-mono text-[10px]"
                          style={{ borderColor: "var(--border)" }}
                        >
                          {actionLabel(a)}
                        </span>
                      ))}
                    </div>
                  </div>
                </div>
              </div>
            );
          })}
        </div>
        {filtered.length === 0 && (
          <p className="text-center text-[13px] text-muted-foreground">
            No groups match these filters — band would hide when empty.
          </p>
        )}
      </div>
    </div>
  );
}
