/**
 * PROTOTYPE Variant B — Control plane + structured table
 * Level dial and retention are a first-class control card; logs are a parsed table.
 * Structure: form-like control plane above, data table below.
 */
import { useMemo, useState } from "react";
import { Copy, RefreshCw } from "lucide-react";
import { Button } from "@/components/ui/button";
import { SettingGroup } from "../SettingGroup";
import {
  LEVEL_LABELS,
  MOCK_PARSED_LOGS,
  SCENARIO_CLEAN,
  SCENARIO_OVERRIDE,
  filterByMinLevel,
  formatRetention,
  levelBadgeStyle,
  type LogLevelName,
  type LogsPrototypeScenario,
} from "./logsMock";

type Props = {
  simulateOverride: boolean;
};

function LevelSegmented({
  value,
  onChange,
  disabled,
}: {
  value: 0 | 1 | 2;
  onChange: (v: 0 | 1 | 2) => void;
  disabled?: boolean;
}) {
  return (
    <div
      className="inline-flex rounded-md border p-0.5"
      style={{ borderColor: "var(--border)", background: "var(--card)" }}
      role="group"
      aria-label="Log level"
    >
      {([0, 1, 2] as const).map((n) => {
        const active = value === n;
        return (
          <button
            key={n}
            type="button"
            disabled={disabled}
            onClick={() => onChange(n)}
            className="min-w-[5.5rem] rounded-[4px] px-3 py-1.5 text-[12.5px] transition-colors disabled:opacity-50"
            style={{
              background: active ? "var(--secondary)" : "transparent",
              color: active ? "var(--foreground)" : "var(--muted-foreground)",
              fontWeight: active ? 600 : 400,
            }}
          >
            <div>{LEVEL_LABELS[n]}</div>
            <div className="text-[10px] font-normal opacity-70">{n}</div>
          </button>
        );
      })}
    </div>
  );
}

function OverrideCard({ scenario }: { scenario: LogsPrototypeScenario }) {
  const overridden = scenario.effectiveSource !== "config";
  return (
    <div
      className="rounded-lg border px-3 py-2.5"
      style={{
        borderColor: overridden
          ? "color-mix(in oklab, var(--status-paused) 45%, transparent)"
          : "var(--border)",
        background: overridden ? "var(--status-paused-bg)" : "var(--card)",
      }}
    >
      <div className="text-[11px] uppercase tracking-[0.05em] text-muted-foreground">
        What is actually running
      </div>
      <div className="mt-1 text-[13px]">
        <strong>
          {LEVEL_LABELS[scenario.effectiveLevel]} ({scenario.effectiveLevel})
        </strong>
        <span className="text-muted-foreground">
          {" "}
          · from {scenario.effectiveSource}
        </span>
      </div>
      {overridden ? (
        <p className="mt-1.5 text-[12px] leading-snug text-muted-foreground">
          A higher-priority source is winning the startup chain. Saving a new
          level applies it <em>now</em>, but the next restart returns to{" "}
          {scenario.effectiveSource} until that pin is removed.
        </p>
      ) : (
        <p className="mt-1.5 text-[12px] leading-snug text-muted-foreground">
          No CLI or environment pin — the config value is what the process uses.
        </p>
      )}
    </div>
  );
}

export function LogsVariantB({ simulateOverride }: Props) {
  const scenario = simulateOverride ? SCENARIO_OVERRIDE : SCENARIO_CLEAN;
  // Host remounts on simulateOverride toggle so initial state tracks the scenario.
  const [savedLevel, setSavedLevel] = useState<0 | 1 | 2>(scenario.savedLevel);
  const [viewFilter, setViewFilter] = useState<"all" | LogLevelName>("INFO");
  const [copied, setCopied] = useState(false);

  const lines = useMemo(
    () => filterByMinLevel(MOCK_PARSED_LOGS, viewFilter),
    [viewFilter],
  );

  const copyFiltered = async () => {
    const text = lines
      .map((l) => `${l.timestamp}\t${l.level}\t${l.message}`)
      .join("\n");
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1500);
    } catch {
      setCopied(false);
    }
  };

  return (
    <div className="space-y-6">
      <SettingGroup
        title="Log level"
        description="One dial. Applies immediately; survives restart only if nothing higher in the chain overrides it."
      >
        <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
          <LevelSegmented value={savedLevel} onChange={setSavedLevel} />
          <div className="text-[12px] text-muted-foreground sm:text-right">
            <div>
              Saved in config:{" "}
              <span className="font-mono text-foreground">
                {savedLevel} ({LEVEL_LABELS[savedLevel]})
              </span>
            </div>
            <div className="mt-0.5">
              Retention{" "}
              <span className="font-mono text-foreground">
                {formatRetention(
                  scenario.maxLogSizeBytes,
                  scenario.maxLogFiles,
                )}
              </span>{" "}
              <span className="text-[10px] uppercase tracking-wide">
                read-only
              </span>
            </div>
            <div className="mt-0.5 font-mono text-[11px]">{scenario.logDir}</div>
          </div>
        </div>
        <OverrideCard
          scenario={{
            ...scenario,
            savedLevel,
          }}
        />
      </SettingGroup>

      <SettingGroup
        title="Recent log"
        description="Parsed from comicarr.log (last N lines). Secrets already redacted on the server."
      >
        <div className="mb-2 flex flex-wrap items-center gap-2">
          {(["all", "DEBUG", "INFO", "WARNING", "ERROR"] as const).map(
            (key) => {
              const active = viewFilter === key;
              const label =
                key === "all" ? "All" : key === "DEBUG" ? "Debug+" : key;
              return (
                <button
                  key={key}
                  type="button"
                  onClick={() => setViewFilter(key)}
                  className="rounded-full border px-2.5 py-0.5 text-[11.5px]"
                  style={{
                    borderColor: active ? "var(--primary)" : "var(--border)",
                    color: active ? "var(--primary)" : "var(--muted-foreground)",
                    background: active
                      ? "color-mix(in oklab, var(--primary) 12%, transparent)"
                      : "transparent",
                  }}
                >
                  {label}
                </button>
              );
            },
          )}
          <div className="ml-auto flex gap-2">
            <Button type="button" variant="outline" size="sm" disabled>
              <RefreshCw className="size-3.5" />
              Refresh
            </Button>
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={copyFiltered}
            >
              <Copy className="size-3.5" />
              {copied ? "Copied" : "Copy filtered"}
            </Button>
          </div>
        </div>

        <div
          className="max-h-[min(52vh,560px)] overflow-auto rounded-[6px] border"
          style={{ borderColor: "var(--border)" }}
        >
          <table className="w-full border-collapse text-left text-[12px]">
            <thead
              className="sticky top-0 z-10 text-[11px] uppercase tracking-[0.04em] text-muted-foreground"
              style={{ background: "var(--card)" }}
            >
              <tr>
                <th className="px-3 py-2 font-medium whitespace-nowrap">Time</th>
                <th className="px-2 py-2 font-medium">Level</th>
                <th className="px-3 py-2 font-medium">Message</th>
              </tr>
            </thead>
            <tbody>
              {lines.map((line, i) => (
                <tr
                  key={`${line.timestamp}-${i}`}
                  className="border-t"
                  style={{ borderColor: "var(--border)" }}
                >
                  <td className="px-3 py-1.5 align-top font-mono text-[11px] whitespace-nowrap text-muted-foreground">
                    {line.timestamp}
                  </td>
                  <td className="px-2 py-1.5 align-top">
                    <span
                      className="inline-flex rounded px-1.5 py-0.5 font-mono text-[10px] font-semibold"
                      style={levelBadgeStyle(line.level)}
                    >
                      {line.level}
                    </span>
                  </td>
                  <td className="px-3 py-1.5 align-top font-mono text-[11.5px] leading-snug break-all">
                    {line.message}
                  </td>
                </tr>
              ))}
              {lines.length === 0 && (
                <tr>
                  <td
                    colSpan={3}
                    className="px-3 py-6 text-center text-muted-foreground"
                  >
                    No lines match this filter.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </SettingGroup>
    </div>
  );
}
