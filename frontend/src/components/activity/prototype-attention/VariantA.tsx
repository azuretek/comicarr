/**
 * PROTOTYPE Variant A — Sentry strip + fourth "Attention" tab.
 *
 * Band: max 3 groups, volume×newest rank, hard height ~3 rows.
 * Fold: "and K more · open Attention" → fourth tab.
 * Triage: full list + reason/series filters + selection + bulk (cap 25).
 */

import { useMemo, useState } from "react";
import { AlertTriangle } from "lucide-react";
import PageHeader, { Tab, TabRow } from "@/components/layout/PageHeader";
import {
  MOCK_GROUPS,
  TOTAL_GROUPS,
  TOTAL_MEMBERS,
  actionLabel,
  rankByVolumeThenNewest,
  type MockGroup,
} from "./mockData";

const PREVIEW_CAP = 3;

type View = "timeline" | "queue" | "history" | "attention";

export const VARIANT_A_NAME = "Sentry strip + Attention tab";

export function VariantA() {
  const [view, setView] = useState<View>("timeline");
  const ranked = useMemo(() => rankByVolumeThenNewest(MOCK_GROUPS), []);
  const preview = ranked.slice(0, PREVIEW_CAP);
  const more = ranked.length - preview.length;

  return (
    <div className="page-transition flex h-full min-h-0 flex-col">
      <PageHeader
        title="Activity"
        meta="PROTOTYPE A — fourth tab owns the workspace"
      />
      <TabRow>
        {(
          [
            ["timeline", "Timeline"],
            ["queue", "Direct Downloads"],
            ["history", "Download History"],
            ["attention", `Attention · ${TOTAL_GROUPS}`],
          ] as const
        ).map(([id, label]) => (
          <Tab
            key={id}
            active={view === id}
            label={label}
            onClick={() => setView(id)}
          />
        ))}
      </TabRow>

      <div className="flex min-h-0 flex-1 flex-col">
        {view === "timeline" && (
          <>
            <BandPreview
              preview={preview}
              more={more}
              onOpenAttention={() => setView("attention")}
            />
            <FakeTimeline />
          </>
        )}
        {view === "attention" && <TriageTable groups={ranked} />}
        {view === "queue" && <Stub label="Direct Downloads (unchanged)" />}
        {view === "history" && (
          <Stub label="Download History — full ledger, no band actions" />
        )}
      </div>
    </div>
  );
}

function BandPreview({
  preview,
  more,
  onOpenAttention,
}: {
  preview: MockGroup[];
  more: number;
  onOpenAttention: () => void;
}) {
  return (
    <section
      aria-label="Needs attention preview"
      className="shrink-0 border-b"
      style={{
        borderColor: "var(--border)",
        background:
          "var(--status-error-bg, color-mix(in oklab, var(--status-error) 12%, transparent))",
        maxHeight: 148,
      }}
    >
      <div className="flex items-center gap-2 px-5 pt-3 pb-1.5">
        <AlertTriangle
          className="h-3.5 w-3.5"
          style={{ color: "var(--status-error)" }}
        />
        <span
          className="font-mono text-[11px] uppercase tracking-[0.1em]"
          style={{ color: "var(--status-error)" }}
        >
          {TOTAL_GROUPS} need attention
        </span>
        <span className="font-mono text-[10px] text-muted-foreground">
          {TOTAL_MEMBERS} issues · groups, not rows
        </span>
      </div>
      <ul className="px-5 pb-2">
        {preview.map((g) => (
          <li
            key={g.group_key}
            className="flex items-baseline justify-between gap-3 py-1"
          >
            <div className="min-w-0 truncate text-[13px]">
              <span className="font-medium">{g.series_label}</span>
              <span className="text-muted-foreground">
                {" "}
                · {g.reason_phrase}
              </span>
            </div>
            <span className="shrink-0 font-mono text-[11px] text-muted-foreground">
              ×{g.member_count}
            </span>
          </li>
        ))}
      </ul>
      {more > 0 && (
        <button
          type="button"
          onClick={onOpenAttention}
          className="w-full border-t px-5 py-2 text-left font-mono text-[11px] hover:bg-black/5"
          style={{
            borderColor: "var(--border)",
            color: "var(--status-error)",
          }}
        >
          and {more} more · open Attention →
        </button>
      )}
    </section>
  );
}

function TriageTable({ groups }: { groups: MockGroup[] }) {
  const [reasonFilter, setReasonFilter] = useState("");
  const [q, setQ] = useState("");
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [confirmStop, setConfirmStop] = useState(false);
  const [toast, setToast] = useState<string | null>(null);

  const filtered = groups.filter((g) => {
    if (reasonFilter && g.base_reason !== reasonFilter) return false;
    if (q && !g.series_label.toLowerCase().includes(q.toLowerCase())) return false;
    return true;
  });

  const reasons = useMemo(
    () => [...new Set(groups.map((g) => g.base_reason))].sort(),
    [groups],
  );

  const selectedMembers = filtered
    .filter((g) => selected.has(g.group_key))
    .reduce((n, g) => n + g.member_count, 0);

  const toggle = (key: string) => {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  };

  const runBulk = (action: string) => {
    const n = Math.min(25, selectedMembers);
    setToast(
      `${actionLabel(action)}: processed ${n} of ${selectedMembers}` +
        (selectedMembers > 25 ? " (cap 25)" : ""),
    );
    setConfirmStop(false);
    setSelected(new Set());
  };

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <div className="flex shrink-0 flex-wrap items-center gap-2 border-b px-5 py-2.5" style={{ borderColor: "var(--border)" }}>
        <input
          className="max-w-xs flex-1 rounded border bg-transparent px-2 py-1 font-mono text-[11px]"
          style={{ borderColor: "var(--border)" }}
          placeholder="Filter series…"
          value={q}
          onChange={(e) => setQ(e.target.value)}
        />
        <select
          className="rounded border bg-transparent px-2 py-1 font-mono text-[11px]"
          style={{ borderColor: "var(--border)" }}
          value={reasonFilter}
          onChange={(e) => setReasonFilter(e.target.value)}
        >
          <option value="">All reasons</option>
          {reasons.map((r) => (
            <option key={r} value={r}>
              {r}
            </option>
          ))}
        </select>
        <span className="font-mono text-[10px] text-muted-foreground">
          {filtered.length} groups · not Download History (only unresolved + actions)
        </span>
      </div>

      {selected.size > 0 && (
        <div
          className="flex shrink-0 flex-wrap items-center gap-2 border-b px-5 py-2"
          style={{
            borderColor: "var(--border)",
            background: "color-mix(in oklab, var(--primary) 8%, transparent)",
          }}
        >
          <span className="font-mono text-[11px]">
            {selected.size} groups · ~{selectedMembers} issues
            {selectedMembers > 25 ? " · cap 25/click" : ""}
          </span>
          <button
            type="button"
            className="rounded border px-2 py-1 font-mono text-[10px]"
            style={{ borderColor: "var(--border)" }}
            onClick={() => runBulk("search_again")}
          >
            Search again
          </button>
          <button
            type="button"
            className="rounded border px-2 py-1 font-mono text-[10px]"
            style={{ borderColor: "var(--border)" }}
            onClick={() => setConfirmStop(true)}
          >
            Stop wanting…
          </button>
        </div>
      )}

      {confirmStop && (
        <div
          className="shrink-0 border-b px-5 py-3"
          style={{
            borderColor: "var(--border)",
            background:
              "color-mix(in oklab, var(--status-error) 10%, transparent)",
          }}
        >
          <p className="text-[13px] font-medium">
            Stop acquiring ~{Math.min(25, selectedMembers)} issues?
          </p>
          <p className="mt-1 text-[12px] text-muted-foreground">
            They will be marked ignored in your library and leave Needs
            attention. They won’t be searched until you re-want them.
          </p>
          <div className="mt-2 flex gap-2">
            <button
              type="button"
              className="rounded border px-2 py-1 font-mono text-[10px]"
              style={{ borderColor: "var(--border)" }}
              onClick={() => runBulk("stop_wanting")}
            >
              Stop wanting
            </button>
            <button
              type="button"
              className="rounded border px-2 py-1 font-mono text-[10px]"
              style={{ borderColor: "var(--border)" }}
              onClick={() => setConfirmStop(false)}
            >
              Cancel
            </button>
          </div>
        </div>
      )}

      {toast && (
        <div className="shrink-0 px-5 py-1.5 font-mono text-[11px] text-muted-foreground">
          {toast}
        </div>
      )}

      <ul className="min-h-0 flex-1 overflow-auto px-5 py-2">
        {filtered.map((g) => (
          <li
            key={g.group_key}
            className="flex items-start gap-3 border-b py-2.5"
            style={{ borderColor: "var(--border)" }}
          >
            <input
              type="checkbox"
              checked={selected.has(g.group_key)}
              onChange={() => toggle(g.group_key)}
              className="mt-1"
            />
            <div className="min-w-0 flex-1">
              <div className="flex flex-wrap items-baseline gap-x-2">
                <span className="text-[13px] font-medium">{g.series_label}</span>
                <span className="font-mono text-[11px] text-muted-foreground">
                  ×{g.member_count}
                </span>
                <span
                  className="font-mono text-[10px] uppercase"
                  style={{
                    color:
                      g.available_actions.includes("retry")
                        ? "var(--status-error)"
                        : "var(--status-paused)",
                  }}
                >
                  {g.available_actions.includes("retry")
                    ? "failed"
                    : "manual review"}
                </span>
              </div>
              <div className="text-[12px] text-muted-foreground">
                {g.reason_phrase}
              </div>
              <div className="mt-1 flex flex-wrap gap-1.5">
                {g.available_actions.map((a) => (
                  <span
                    key={a}
                    className="rounded border px-1.5 py-0.5 font-mono text-[10px] text-muted-foreground"
                    style={{ borderColor: "var(--border)" }}
                  >
                    {actionLabel(a)}
                  </span>
                ))}
              </div>
            </div>
          </li>
        ))}
      </ul>
    </div>
  );
}

function FakeTimeline() {
  return (
    <div className="min-h-0 flex-1 overflow-auto px-5 py-4">
      <p className="mb-3 font-mono text-[10px] uppercase tracking-wider text-muted-foreground">
        Timeline stays below the fold — position stable (~3 group rows max)
      </p>
      {Array.from({ length: 8 }, (_, i) => (
        <div
          key={i}
          className="border-b py-2 text-[13px] text-muted-foreground"
          style={{ borderColor: "var(--border)" }}
        >
          story row {i + 1} · muted history · no actions
        </div>
      ))}
    </div>
  );
}

function Stub({ label }: { label: string }) {
  return (
    <div className="flex flex-1 items-center justify-center p-8 text-center text-[13px] text-muted-foreground">
      {label}
    </div>
  );
}
