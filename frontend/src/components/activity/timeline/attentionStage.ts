/**
 * Stage display for needs-attention groups.
 *
 * `failed` and `manual_review` are the same band with a different obligation:
 * one went wrong, the other is waiting on a decision. Colour carries that so
 * the operator can tell them apart without opening triage — the same band, not
 * a second one (#526).
 */

import type { BandAction } from "./types";

export function stageAccent(stage: string): string {
  if (stage === "failed") return "var(--status-error)";
  if (stage === "manual_review") return "var(--status-paused)";
  return "var(--muted-foreground)";
}

export function stageLabel(stage: string): string {
  if (stage === "failed") return "failed";
  if (stage === "manual_review") return "review";
  return "mixed";
}

export function stageDescription(stage: string): string {
  if (stage === "failed") return "Comicarr couldn't finish this.";
  if (stage === "manual_review") return "Waiting on your decision.";
  return "Members are at different stages — select the rows you mean.";
}

const ACTION_LABELS: Record<BandAction, string> = {
  retry: "Retry",
  search_again: "Search again",
  import: "Import",
  stop_wanting: "Stop wanting",
};

export function actionLabel(action: BandAction): string {
  return ACTION_LABELS[action] ?? action;
}

/**
 * Consequence sentence for stop-wanting. Shared by the single-row path and the
 * multi-member confirmation so the two can never describe the same act
 * differently (#525).
 */
export function stopWantingConsequence(count: number, seriesLabel?: string) {
  const subject = count === 1 ? "This issue" : `These ${count} issues`;
  const where = seriesLabel ? ` in ${seriesLabel}` : "";
  return `${subject}${where} will be marked ignored in your library, leave Needs attention, and will not be searched again until you want them back.`;
}
