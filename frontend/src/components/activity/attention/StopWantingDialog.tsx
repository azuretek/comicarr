/**
 * Consequence confirmation for multi-member stop-wanting (#525).
 *
 * Stop-wanting is the one band exit that changes the library rather than
 * re-driving the pipeline, and a group button can reach dozens of issues at
 * once. The dialog names the series, the count, and what actually happens —
 * there is no timed undo, so the sentence has to carry the weight.
 */

import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import {
  stopWantingConsequence,
  type AttentionGroup,
} from "@/components/activity/timeline";

export function StopWantingDialog({
  groups,
  busy,
  onConfirm,
  onCancel,
}: {
  groups: AttentionGroup[];
  busy: boolean;
  onConfirm: () => void;
  onCancel: () => void;
}) {
  const issues = groups.reduce((sum, group) => sum + group.member_count, 0);
  const seriesLabel = groups.length === 1 ? groups[0].series_label : undefined;

  return (
    <Dialog open onOpenChange={(open) => !open && onCancel()}>
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle>Stop wanting {issues} issues?</DialogTitle>
          <DialogDescription>
            {stopWantingConsequence(issues, seriesLabel)}
          </DialogDescription>
        </DialogHeader>

        {groups.length > 1 && (
          <ul className="max-h-40 space-y-1 overflow-auto text-[12px]">
            {groups.map((group) => (
              <li
                key={group.group_key}
                className="flex items-baseline gap-2 text-muted-foreground"
              >
                <span className="truncate">{group.series_label}</span>
                <span className="ml-auto shrink-0 font-mono tabular-nums">
                  ×{group.member_count}
                </span>
              </li>
            ))}
          </ul>
        )}

        <DialogFooter>
          <Button variant="outline" onClick={onCancel} disabled={busy}>
            Cancel
          </Button>
          <Button onClick={onConfirm} disabled={busy}>
            {busy ? "Stopping…" : "Stop wanting"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
