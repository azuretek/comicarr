/**
 * PROTOTYPE Variant C — Dial in General, viewer in a sheet
 * Level + retention live with other settings; logs open as a tool, not a section.
 * Structure: settings field group + full-height drawer, not a dedicated nav item.
 */
import { useMemo, useState } from "react";
import { Copy, RefreshCw, ScrollText } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet";
import { SettingField } from "../SettingField";
import { SettingGroup } from "../SettingGroup";
import {
  LEVEL_LABELS,
  MOCK_PARSED_LOGS,
  SCENARIO_CLEAN,
  SCENARIO_OVERRIDE,
  filterByMinLevel,
  formatRetention,
  type LogLevelName,
} from "./logsMock";

type Props = {
  simulateOverride: boolean;
};

export function LogsVariantC({ simulateOverride }: Props) {
  const scenario = simulateOverride ? SCENARIO_OVERRIDE : SCENARIO_CLEAN;
  // Host remounts on simulateOverride toggle so initial state tracks the scenario.
  const [savedLevel, setSavedLevel] = useState<0 | 1 | 2>(scenario.savedLevel);
  const [open, setOpen] = useState(false);
  const [viewFilter, setViewFilter] = useState<"all" | LogLevelName>("all");
  const [copied, setCopied] = useState(false);

  const lines = useMemo(
    () => filterByMinLevel(MOCK_PARSED_LOGS, viewFilter),
    [viewFilter],
  );
  const textBlock = lines.map((l) => l.raw).join("\n");
  const overridden = scenario.effectiveSource !== "config";

  const copyAll = async () => {
    try {
      await navigator.clipboard.writeText(textBlock);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1500);
    } catch {
      setCopied(false);
    }
  };

  return (
    <div className="space-y-6">
      <div
        className="rounded-[6px] border border-dashed px-3 py-2 text-[12px] text-muted-foreground"
        style={{ borderColor: "var(--border)" }}
      >
        This variant pretends you are still on{" "}
        <strong className="text-foreground">General</strong> — logging is a
        settings group, not its own nav item. The viewer is a tool you open.
      </div>

      <SettingGroup
        title="Content Sources"
        description="Placeholder — existing General content sits above."
      >
        <SettingField
          label="Comics (Comic Vine)"
          type="checkbox"
          checked
          readOnly
          helpText="Shown only so density matches the real General tab."
        />
      </SettingGroup>

      <SettingGroup
        title="Logging"
        description="Verbosity dial and retention ceiling. Open the viewer when you need to paste lines into an issue."
      >
        <SettingField
          label="Log level"
          type="select"
          value={savedLevel}
          onChange={(v) => setSavedLevel(Number(v) as 0 | 1 | 2)}
          options={[
            { value: 0, label: "0 — Warning (errors and warnings only)" },
            { value: 1, label: "1 — Info (default)" },
            { value: 2, label: "2 — Debug (everything)" },
          ]}
          helpText="Applies immediately. Stored in config.ini as LOG_LEVEL."
        />

        {overridden && (
          <div
            className="rounded-lg border px-3 py-2 text-[12.5px]"
            style={{
              borderColor:
                "color-mix(in oklab, var(--status-paused) 40%, transparent)",
              background: "var(--status-paused-bg)",
              color: "var(--status-paused)",
            }}
          >
            Process is running at{" "}
            <strong>
              {LEVEL_LABELS[scenario.effectiveLevel]} ({scenario.effectiveLevel}
              )
            </strong>{" "}
            via {scenario.effectiveSource}, not the saved config value (
            {savedLevel}). Restart will re-apply the pin.
          </div>
        )}

        <SettingField
          label="Retention"
          value={formatRetention(
            scenario.maxLogSizeBytes,
            scenario.maxLogFiles,
          )}
          type="text"
          readOnly
          helpText={`Rotated files under ${scenario.logDir}. Not editable here.`}
        />

        <div className="pt-1">
          <Button type="button" onClick={() => setOpen(true)}>
            <ScrollText className="size-3.5" />
            Open log viewer
          </Button>
        </div>
      </SettingGroup>

      <SettingGroup
        title="Directories"
        description="Placeholder — rest of General continues below."
      >
        <SettingField
          label="Log Directory"
          value={scenario.logDir}
          type="text"
          readOnly
          helpText="Already on General today; retention above is the new context."
        />
      </SettingGroup>

      <Sheet open={open} onOpenChange={setOpen}>
        <SheetContent
          side="right"
          className="flex w-full flex-col gap-0 p-0 sm:max-w-xl"
        >
          <SheetHeader
            className="border-b px-4 py-3"
            style={{ borderColor: "var(--border)" }}
          >
            <SheetTitle className="text-[15px]">comicarr.log</SheetTitle>
            <SheetDescription className="text-[12px]">
              Last {MOCK_PARSED_LOGS.length} lines · redacted server-side
            </SheetDescription>
          </SheetHeader>

          <div
            className="flex flex-wrap items-center gap-2 border-b px-4 py-2"
            style={{ borderColor: "var(--border)" }}
          >
            <label className="flex items-center gap-1.5 text-[12px] text-muted-foreground">
              Show
              <select
                className="h-8 rounded-md border bg-background px-2 text-[12.5px] text-foreground"
                style={{ borderColor: "var(--border)" }}
                value={viewFilter}
                onChange={(e) =>
                  setViewFilter(e.target.value as "all" | LogLevelName)
                }
              >
                <option value="all">All</option>
                <option value="DEBUG">Debug+</option>
                <option value="INFO">Info+</option>
                <option value="WARNING">Warning+</option>
                <option value="ERROR">Error</option>
              </select>
            </label>
            <div className="ml-auto flex gap-2">
              <Button type="button" variant="outline" size="sm" disabled>
                <RefreshCw className="size-3.5" />
                Refresh
              </Button>
              <Button
                type="button"
                variant="outline"
                size="sm"
                onClick={copyAll}
              >
                <Copy className="size-3.5" />
                {copied ? "Copied" : "Copy"}
              </Button>
            </div>
          </div>

          <pre
            className="min-h-0 flex-1 overflow-auto p-3 font-mono text-[11.5px] leading-[1.45] whitespace-pre"
            style={{
              background: "color-mix(in oklab, var(--card) 70%, black)",
            }}
          >
            {textBlock || "(no lines match this filter)"}
          </pre>
        </SheetContent>
      </Sheet>
    </div>
  );
}
