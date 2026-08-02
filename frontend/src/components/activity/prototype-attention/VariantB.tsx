/**
 * PROTOTYPE Variant B — one-line band + master-detail sheet (no new tab).
 *
 * Band never grows: single status strip. Timeline always near the top.
 * Triage is a full-height overlay sheet (not Download History).
 * Left: groups. Right: members + selection + bulk.
 */

import { useMemo, useState } from "react";
import { AlertTriangle, X } from "lucide-react";
import PageHeader, { Tab, TabRow } from "@/components/layout/PageHeader";
import {
  MOCK_GROUPS,
  TOTAL_GROUPS,
  TOTAL_MEMBERS,
  actionLabel,
  rankByNewest,
  type MockGroup,
} from "./mockData";

export const VARIANT_B_NAME = "One-line bar + master-detail sheet";

export function VariantB() {
  const [open, setOpen] = useState(false);
  const [activeKey, setActiveKey] = useState(MOCK_GROUPS[0]?.group_key ?? "");
  const [selectedKeys, setSelectedKeys] = useState<Set<string>>(new Set());
  const [confirmStop, setConfirmStop] = useState(false);
  const [toast, setToast] = useState<string | null>(null);

  const ranked = useMemo(() => rankByNewest(MOCK_GROUPS), []);
  const largest = useMemo(
    () => [...MOCK_GROUPS].sort((a, b) => b.member_count - a.member_count)[0],
    [],
  );
  const active = ranked.find((g) => g.group_key === activeKey) ?? ranked[0];

  const selectedMemberCount = ranked
    .filter((g) => selectedKeys.has(g.group_key))
    .reduce((n, g) => n + g.member_count, 0);

  const toggleSelect = (key: string) => {
    setSelectedKeys((prev) => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  };

  const run = (action: string) => {
    const n = Math.min(25, selectedMemberCount || active?.member_count || 0);
    setToast(`${actionLabel(action)} · processed up to ${n} (cap 25)`);
    setConfirmStop(false);
    setSelectedKeys(new Set());
  };

  return (
    <div className="page-transition relative flex h-full min-h-0 flex-col">
      <PageHeader
        title="Activity"
        meta="PROTOTYPE B — no fourth tab; sheet is the workspace"
      />
      <TabRow>
        <Tab active label="Timeline" onClick={() => undefined} />
        <Tab active={false} label="Direct Downloads" onClick={() => undefined} />
        <Tab active={false} label="Download History" onClick={() => undefined} />
      </TabRow>

      {/* One-line band — height ceiling is this strip only */}
      <button
        type="button"
        onClick={() => setOpen(true)}
        className="flex shrink-0 items-center gap-2 border-b px-5 py-2.5 text-left"
        style={{
          borderColor: "var(--border)",
          background:
            "var(--status-error-bg, color-mix(in oklab, var(--status-error) 12%, transparent))",
        }}
      >
        <AlertTriangle
          className="h-3.5 w-3.5 shrink-0"
          style={{ color: "var(--status-error)" }}
        />
        <span
          className="font-mono text-[11px] uppercase tracking-[0.1em]"
          style={{ color: "var(--status-error)" }}
        >
          {TOTAL_GROUPS} need attention
        </span>
        <span className="truncate font-mono text-[11px] text-muted-foreground">
          {TOTAL_MEMBERS} issues · largest {largest?.series_label} ×
          {largest?.member_count}
        </span>
        <span
          className="ml-auto shrink-0 font-mono text-[11px]"
          style={{ color: "var(--status-error)" }}
        >
          Open triage →
        </span>
      </button>

      <div className="min-h-0 flex-1 overflow-auto px-5 py-4">
        <p className="mb-3 font-mono text-[10px] uppercase tracking-wider text-muted-foreground">
          Timeline starts immediately under the one-line band
        </p>
        {Array.from({ length: 12 }, (_, i) => (
          <div
            key={i}
            className="border-b py-2 text-[13px] text-muted-foreground"
            style={{ borderColor: "var(--border)" }}
          >
            story row {i + 1}
          </div>
        ))}
      </div>

      {open && (
        <div
          className="absolute inset-0 z-40 flex flex-col"
          style={{ background: "var(--background)" }}
        >
          <div
            className="flex shrink-0 items-center gap-3 border-b px-5 py-3"
            style={{ borderColor: "var(--border)" }}
          >
            <div>
              <div className="text-[16px] font-semibold">Needs attention</div>
              <div className="font-mono text-[11px] text-muted-foreground">
                Unresolved groups only · actions live here · not Download
                History
              </div>
            </div>
            <button
              type="button"
              className="ml-auto rounded border p-1.5"
              style={{ borderColor: "var(--border)" }}
              onClick={() => setOpen(false)}
              aria-label="Close triage"
            >
              <X className="h-4 w-4" />
            </button>
          </div>

          <div className="flex min-h-0 flex-1">
            {/* Master list */}
            <ul
              className="w-[42%] min-w-[240px] overflow-auto border-r"
              style={{ borderColor: "var(--border)" }}
            >
              {ranked.map((g) => (
                <li key={g.group_key}>
                  <button
                    type="button"
                    onClick={() => setActiveKey(g.group_key)}
                    className="flex w-full items-start gap-2 px-4 py-2.5 text-left hover:bg-muted/40"
                    style={{
                      background:
                        g.group_key === active?.group_key
                          ? "color-mix(in oklab, var(--primary) 8%, transparent)"
                          : undefined,
                    }}
                  >
                    <input
                      type="checkbox"
                      checked={selectedKeys.has(g.group_key)}
                      onChange={(e) => {
                        e.stopPropagation();
                        toggleSelect(g.group_key);
                      }}
                      onClick={(e) => e.stopPropagation()}
                      className="mt-1"
                    />
                    <div className="min-w-0">
                      <div className="truncate text-[13px] font-medium">
                        {g.series_label}{" "}
                        <span className="font-mono text-[11px] text-muted-foreground">
                          ×{g.member_count}
                        </span>
                      </div>
                      <div className="truncate text-[11px] text-muted-foreground">
                        {g.reason_phrase}
                      </div>
                    </div>
                  </button>
                </li>
              ))}
            </ul>

            {/* Detail */}
            <div className="flex min-w-0 flex-1 flex-col">
              {active && <Detail group={active} />}
              <BulkBar
                selectedGroups={selectedKeys.size}
                selectedMembers={selectedMemberCount}
                confirmStop={confirmStop}
                setConfirmStop={setConfirmStop}
                onRun={run}
                toast={toast}
              />
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

function Detail({ group }: { group: MockGroup }) {
  return (
    <div className="min-h-0 flex-1 overflow-auto px-5 py-4">
      <h2 className="text-[15px] font-semibold">{group.series_label}</h2>
      <p className="mt-1 text-[13px] text-muted-foreground">
        {group.reason_phrase}
      </p>
      <p className="mt-1 font-mono text-[10px] text-muted-foreground">
        {group.member_count} issues · newest {group.newest_updated_at} · oldest{" "}
        {group.oldest_updated_at}
      </p>
      <div className="mt-3 flex flex-wrap gap-1.5">
        {group.available_actions.map((a) => (
          <span
            key={a}
            className="rounded border px-2 py-1 font-mono text-[10px]"
            style={{ borderColor: "var(--border)" }}
          >
            {actionLabel(a)} (group)
          </span>
        ))}
      </div>
      <h3 className="mt-5 font-mono text-[10px] uppercase tracking-wider text-muted-foreground">
        Members (sample)
      </h3>
      <ul className="mt-2">
        {group.members.map((m) => (
          <li
            key={m.release_key}
            className="border-b py-1.5 text-[13px]"
            style={{ borderColor: "var(--border)" }}
          >
            {m.issue_label}
            <span className="ml-2 font-mono text-[10px] text-muted-foreground">
              {m.release_key}
            </span>
          </li>
        ))}
        {group.member_count > group.members.length && (
          <li className="py-1.5 text-[12px] text-muted-foreground">
            …and {group.member_count - group.members.length} more
          </li>
        )}
      </ul>
    </div>
  );
}

function BulkBar({
  selectedGroups,
  selectedMembers,
  confirmStop,
  setConfirmStop,
  onRun,
  toast,
}: {
  selectedGroups: number;
  selectedMembers: number;
  confirmStop: boolean;
  setConfirmStop: (v: boolean) => void;
  onRun: (action: string) => void;
  toast: string | null;
}) {
  if (selectedGroups === 0 && !toast && !confirmStop) {
    return (
      <div
        className="shrink-0 border-t px-5 py-2 font-mono text-[10px] text-muted-foreground"
        style={{ borderColor: "var(--border)" }}
      >
        Select groups on the left for bulk · cap 25 issues/click
      </div>
    );
  }
  return (
    <div
      className="shrink-0 border-t px-5 py-3"
      style={{ borderColor: "var(--border)" }}
    >
      {toast && (
        <p className="mb-2 font-mono text-[11px] text-muted-foreground">{toast}</p>
      )}
      {confirmStop ? (
        <div>
          <p className="text-[13px] font-medium">
            Stop acquiring ~{Math.min(25, selectedMembers)} issues across{" "}
            {selectedGroups} groups?
          </p>
          <p className="mt-1 text-[12px] text-muted-foreground">
            Library intent → ignored. Not an alert dismiss.
          </p>
          <div className="mt-2 flex gap-2">
            <button
              type="button"
              className="rounded border px-2 py-1 font-mono text-[10px]"
              style={{ borderColor: "var(--border)" }}
              onClick={() => onRun("stop_wanting")}
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
      ) : (
        selectedGroups > 0 && (
          <div className="flex flex-wrap items-center gap-2">
            <span className="font-mono text-[11px]">
              {selectedGroups} groups · ~{selectedMembers} issues
              {selectedMembers > 25 ? " · will process 25" : ""}
            </span>
            <button
              type="button"
              className="rounded border px-2 py-1 font-mono text-[10px]"
              style={{ borderColor: "var(--border)" }}
              onClick={() => onRun("search_again")}
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
        )
      )}
    </div>
  );
}
