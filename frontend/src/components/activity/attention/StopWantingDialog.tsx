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
import { stopWantingConsequence } from "@/components/activity/timeline";

export function StopWantingDialog({
  count,
  seriesLabel,
  busy,
  onConfirm,
  onCancel,
}: {
  count: number;
  seriesLabel?: string;
  busy: boolean;
  onConfirm: () => void;
  onCancel: () => void;
}) {
  return (
    <Dialog open onOpenChange={(open) => !open && onCancel()}>
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle>Stop wanting {count} issues?</DialogTitle>
          <DialogDescription>
            {stopWantingConsequence(count, seriesLabel)}
          </DialogDescription>
        </DialogHeader>

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
