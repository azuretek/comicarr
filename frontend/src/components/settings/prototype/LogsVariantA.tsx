/**
 * PROTOTYPE Variant A — Console first
 * Monospace block is the primary surface; dial + retention live in a slim toolbar.
 * Structure: terminal pane, not a form.
 */
import { useMemo, useState } from "react";
import { Copy, RefreshCw } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  LEVEL_LABELS,
  MOCK_PARSED_LOGS,
  SCENARIO_CLEAN,
  SCENARIO_OVERRIDE,
  filterByMinLevel,
  formatRetention,
  type LogLevelName,
  type LogsPrototypeScenario,
} from "./logsMock";

type Props = {
  simulateOverride: boolean;
};

function OverrideStrip({ scenario }: { scenario: LogsPrototypeScenario }) {
  if (scenario.effectiveSource === "config") return null;
  return (
    <div
      className="rounded-[5px] border px-3 py-2 text-[12.5px]"
      style={{
        borderColor: "color-mix(in oklab, var(--status-paused) 40%, transparent)",
        background: "var(--status-paused-bg)",
        color: "var(--status-paused)",
      }}
    >
      Running at{" "}
      <strong>
        {LEVEL_LABELS[scenario.effectiveLevel]} ({scenario.effectiveLevel})
      </strong>{" "}
      from {scenario.effectiveSource}. Changing the dial below saves to config
      and applies live, but a restart will snap back to the higher-priority
      source until you remove it.
    </div>
  );
}

export function LogsVariantA({ simulateOverride }: Props) {
  const scenario = simulateOverride ? SCENARIO_OVERRIDE : SCENARIO_CLEAN;
  // Host remounts on simulateOverride toggle so initial state tracks the scenario.
  const [savedLevel, setSavedLevel] = useState<0 | 1 | 2>(scenario.savedLevel);
  const [viewFilter, setViewFilter] = useState<"all" | LogLevelName>("all");
  const [copied, setCopied] = useState(false);

  const lines = useMemo(
    () => filterByMinLevel(MOCK_PARSED_LOGS, viewFilter),
    [viewFilter],
  );
  const textBlock = lines.map((l) => l.raw).join("\n");

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
    <div className="space-y-3">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <div className="text-base font-medium tracking-wide">Logs</div>
          <div className="text-[13px] text-muted-foreground">
            Last {MOCK_PARSED_LOGS.length} lines from comicarr.log ·{" "}
            {formatRetention(scenario.maxLogSizeBytes, scenario.maxLogFiles)} ·{" "}
            <span className="font-mono text-[12px]">{scenario.logDir}</span>
          </div>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <label className="flex items-center gap-1.5 text-[12px] text-muted-foreground">
            Level
            <select
              className="h-8 rounded-md border bg-background px-2 text-[12.5px] text-foreground"
              style={{ borderColor: "var(--border)" }}
              value={savedLevel}
              onChange={(e) =>
                setSavedLevel(Number(e.target.value) as 0 | 1 | 2)
              }
            >
              {([0, 1, 2] as const).map((n) => (
                <option key={n} value={n}>
                  {n} — {LEVEL_LABELS[n]}
                </option>
              ))}
            </select>
          </label>
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
              <option value="all">All lines</option>
              <option value="DEBUG">Debug+</option>
              <option value="INFO">Info+</option>
              <option value="WARNING">Warning+</option>
              <option value="ERROR">Error only</option>
            </select>
          </label>
          <Button type="button" variant="outline" size="sm" disabled>
            <RefreshCw className="size-3.5" />
            Refresh
          </Button>
          <Button type="button" variant="outline" size="sm" onClick={copyAll}>
            <Copy className="size-3.5" />
            {copied ? "Copied" : "Copy"}
          </Button>
        </div>
      </div>

      <OverrideStrip scenario={{ ...scenario, savedLevel }} />

      <pre
        className="max-h-[min(62vh,640px)] overflow-auto rounded-[6px] border p-3 font-mono text-[11.5px] leading-[1.45] whitespace-pre"
        style={{
          borderColor: "var(--border)",
          background: "color-mix(in oklab, var(--card) 70%, black)",
        }}
      >
        {textBlock || "(no lines match this filter)"}
      </pre>

      <p className="text-[11px] text-muted-foreground">
        Prototype note: copy grabs the filtered view only. Level change is local
        state — no API write.
      </p>
    </div>
  );
}
