/**
 * Pinned needs-attention band above the chronological feed.
 *
 * Red + actions live only here (Activity Center ADR §2 / #432). Stream rows
 * for the same trouble are muted history with no actions.
 */

import { useState } from "react";
import { Link } from "react-router-dom";
import { AlertTriangle } from "lucide-react";
import RelativeTime from "@/components/ui/RelativeTime";
import { useToast } from "@/components/ui/toast";
import {
  useBandResolution,
  type BandResolutionAction,
} from "@/hooks/useActivity";
import { bandLabel, bandSentence, reasonDetailLine } from "./sentences";
import type { BandItem } from "./types";

const ACTIONS: Record<"failed" | "manual_review", BandResolutionAction[]> = {
  failed: ["retry", "ignore"],
  manual_review: ["import", "search-again", "ignore"],
};

const ACTION_LABEL: Record<BandResolutionAction, string> = {
  retry: "retry",
  ignore: "ignore",
  import: "import",
  "search-again": "search again",
};

function stageKey(stage: string): "failed" | "manual_review" | null {
  if (stage === "failed") return "failed";
  if (stage === "manual_review") return "manual_review";
  return null;
}

function BandAction({
  label,
  busy,
  disabled,
  onClick,
}: {
  label: string;
  busy: boolean;
  disabled: boolean;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      className="rounded-[4px] border px-2 py-1 font-mono text-[10px] text-muted-foreground hover:text-foreground disabled:opacity-60"
      style={{ borderColor: "var(--border)" }}
    >
      {busy ? `${label}…` : label}
    </button>
  );
}

export function AttentionBand({ items }: { items: BandItem[] }) {
  const { mutateAsync, isPending, variables } = useBandResolution();
  const { addToast } = useToast();
  const [pendingKey, setPendingKey] = useState<string | null>(null);

  if (items.length === 0) return null;

  const handleAction = async (item: BandItem, action: BandResolutionAction) => {
    const key = `${item.release_key}:${action}`;
    setPendingKey(key);
    try {
      await mutateAsync({ releaseKey: item.release_key, action });
      addToast({
        type: "success",
        message:
          action === "ignore"
            ? "Ignored — cleared from needs attention."
            : action === "import"
              ? "Import queued."
              : action === "search-again"
                ? "Search started again."
                : "Retry started.",
      });
    } catch (err) {
      addToast({
        type: "error",
        message:
          err instanceof Error
            ? err.message
            : `Unable to ${ACTION_LABEL[action]}.`,
      });
    } finally {
      setPendingKey(null);
    }
  };

  return (
    <section
      aria-label="Needs attention"
      className="border-b"
      style={{
        borderColor: "var(--border)",
        background:
          "var(--status-error-bg, color-mix(in oklab, var(--status-error) 12%, transparent))",
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
          {items.length} need{items.length === 1 ? "s" : ""} attention
        </span>
        <span className="font-mono text-[10px] text-muted-foreground">
          clears only by action
        </span>
      </div>

      <ul className="px-5 pb-3">
        {items.map((item) => {
          const label = bandLabel(item);
          const stage = stageKey(String(item.stage));
          const actions = stage ? ACTIONS[stage] : [];
          const reason = reasonDetailLine(item.fail_reason);
          const issueHref = item.issueid
            ? `/activity?scope_type=issue&scope_id=${encodeURIComponent(item.issueid)}`
            : null;

          return (
            <li
              key={item.release_key}
              className="flex flex-wrap items-baseline gap-x-3 gap-y-1 py-1.5"
            >
              <span className="text-[13px] font-medium">
                {issueHref ? (
                  <Link to={issueHref} className="hover:text-[var(--primary)]">
                    {bandSentence(String(item.stage), label)}
                  </Link>
                ) : (
                  bandSentence(String(item.stage), label)
                )}
              </span>
              {reason.phrase && (
                <span className="text-[12px] text-muted-foreground">
                  {reason.phrase}
                  {reason.rawCode && (
                    <span className="ml-1.5 font-mono text-[10px] opacity-70">
                      {reason.rawCode}
                    </span>
                  )}
                </span>
              )}
              <RelativeTime value={item.updated_date} />
              <span className="ml-auto flex items-center gap-1.5">
                {actions.map((action) => {
                  const key = `${item.release_key}:${action}`;
                  const busy =
                    isPending &&
                    variables?.releaseKey === item.release_key &&
                    variables?.action === action;
                  return (
                    <BandAction
                      key={action}
                      label={ACTION_LABEL[action]}
                      busy={busy || pendingKey === key}
                      disabled={isPending}
                      onClick={() => void handleAction(item, action)}
                    />
                  );
                })}
              </span>
            </li>
          );
        })}
      </ul>
    </section>
  );
}
