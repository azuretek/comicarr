/**
 * PROTOTYPE ONLY — mock payload for the Settings → Logs surface designs.
 * Real shape of file lines matches comicarr/logger.py file formatter.
 */

export type LogLevelName = "DEBUG" | "INFO" | "WARNING" | "ERROR";

export type ParsedLogLine = {
  raw: string;
  timestamp: string;
  level: LogLevelName;
  message: string;
};

/** Matches file formatter: "%(asctime)s - %(levelname)-7s :: …" */
export const MOCK_RAW_LOGS: string[] = [
  "11-Aug-2026 14:28:01 - INFO    :: comicarr.config.read : MainThread : Config file loaded from /config/comicarr/config.ini",
  "11-Aug-2026 14:28:01 - INFO    :: comicarr.app.main : MainThread : Comicarr starting on 0.0.0.0:8090",
  "11-Aug-2026 14:28:02 - DEBUG  :: comicarr.db : MainThread : Opening SQLite connection pool",
  "11-Aug-2026 14:28:03 - INFO    :: comicarr.scheduler : MainThread : Scheduled job rsscheck every 360 min",
  "11-Aug-2026 14:29:11 - INFO    :: comicarr.search.search : Thread-3 : Searching for Batman (2016) #142",
  "11-Aug-2026 14:29:12 - DEBUG  :: comicarr.search.providers : Thread-3 : Querying NZBGeek for Batman 2016 142",
  "11-Aug-2026 14:29:14 - WARNING :: comicarr.search.providers : Thread-3 : Indexer NZBGeek returned 0 results (rate limit header present)",
  "11-Aug-2026 14:29:15 - INFO    :: comicarr.search.search : Thread-3 : No snatch candidate for Batman (2016) #142",
  "11-Aug-2026 14:30:02 - ERROR   :: comicarr.downloaders.qbittorrent : Thread-5 : Failed to connect to qBittorrent at http://qbittorrent:8080 — Connection refused",
  "11-Aug-2026 14:30:02 - WARNING :: comicarr.app.downloads : Thread-5 : Handoff failed; recording fail_reason=client_unreachable",
  "11-Aug-2026 14:31:40 - INFO    :: comicarr.importer : Thread-2 : Scanning library root /comics (3 series)",
  "11-Aug-2026 14:31:41 - DEBUG  :: comicarr.filechecker : Thread-2 : Matched Batman_2016_142.cbz → ComicID 85943 IssueID 991201",
  "11-Aug-2026 14:32:00 - INFO    :: comicarr.postprocessor : Thread-2 : Post-processed Batman (2016) #142",
  "11-Aug-2026 14:32:18 - DEBUG  :: comicarr.cv : Thread-7 : ComicVine volume/85943 cache hit",
  "11-Aug-2026 14:33:01 - INFO    :: comicarr.app.system.service : MainThread : Log level set to 2 by the Settings page",
  "11-Aug-2026 14:33:02 - DEBUG  :: comicarr.logger : MainThread : Rebuilt handlers at threshold DEBUG",
  "11-Aug-2026 14:33:44 - WARNING :: comicarr.rsscheck : Thread-4 : Feed fetch timed out after 30s for https://example.invalid/rss",
  "11-Aug-2026 14:34:10 - ERROR   :: comicarr.app.series.service : Thread-8 : Refresh failed for ComicID 404: upstream 503",
  "11-Aug-2026 14:34:55 - INFO    :: comicarr.app.activity.events : MainThread : activity recorded kind=search_failed",
  "11-Aug-2026 14:35:02 - DEBUG  :: comicarr.helpers : MainThread : redact_sensitive_text scanned 0 provider secrets",
];

const LINE_RE =
  /^(\d{2}-[A-Za-z]{3}-\d{4} \d{2}:\d{2}:\d{2}) - (\w+)\s*::\s*(.*)$/;

export function parseLogLine(raw: string): ParsedLogLine {
  const match = raw.match(LINE_RE);
  if (!match) {
    return {
      raw,
      timestamp: "",
      level: "INFO",
      message: raw,
    };
  }
  const level = (match[2].trim().toUpperCase() || "INFO") as LogLevelName;
  return {
    raw,
    timestamp: match[1],
    level: (["DEBUG", "INFO", "WARNING", "ERROR"] as LogLevelName[]).includes(
      level,
    )
      ? level
      : "INFO",
    message: match[3],
  };
}

export const MOCK_PARSED_LOGS = MOCK_RAW_LOGS.map(parseLogLine);

export type LevelSource =
  "config" | "environment" | "startup argument" | "default";

export type LogsPrototypeScenario = {
  /** Value stored in config.ini / form (what Settings edits). */
  savedLevel: 0 | 1 | 2;
  /** Level the running process is actually using. */
  effectiveLevel: 0 | 1 | 2;
  effectiveSource: LevelSource;
  logDir: string;
  maxLogSizeBytes: number;
  maxLogFiles: number;
};

/** Honest override: CLI pinned quiet, UI still shows saved 1. */
export const SCENARIO_OVERRIDE: LogsPrototypeScenario = {
  savedLevel: 1,
  effectiveLevel: 0,
  effectiveSource: "startup argument",
  logDir: "/config/comicarr/logs",
  maxLogSizeBytes: 10_000_000,
  maxLogFiles: 5,
};

/** No override: Settings is the bottom of the chain and wins at rest. */
export const SCENARIO_CLEAN: LogsPrototypeScenario = {
  savedLevel: 1,
  effectiveLevel: 1,
  effectiveSource: "config",
  logDir: "/config/comicarr/logs",
  maxLogSizeBytes: 10_000_000,
  maxLogFiles: 5,
};

export const LEVEL_LABELS: Record<0 | 1 | 2, string> = {
  0: "Warning",
  1: "Info",
  2: "Debug",
};

export function formatRetention(bytes: number, files: number): string {
  const mb = Math.round(bytes / 1_000_000);
  return `${mb} MB × ${files} files`;
}

export function filterByMinLevel(
  lines: ParsedLogLine[],
  min: "all" | LogLevelName,
): ParsedLogLine[] {
  if (min === "all") return lines;
  const order: LogLevelName[] = ["DEBUG", "INFO", "WARNING", "ERROR"];
  const minIdx = order.indexOf(min);
  return lines.filter((line) => order.indexOf(line.level) >= minIdx);
}

export function levelBadgeStyle(level: LogLevelName): Record<string, string> {
  switch (level) {
    case "ERROR":
      return {
        color: "var(--status-error)",
        background: "var(--status-error-bg)",
      };
    case "WARNING":
      return {
        color: "var(--status-paused)",
        background: "var(--status-paused-bg)",
      };
    case "DEBUG":
      return {
        color: "var(--muted-foreground)",
        background: "var(--secondary)",
      };
    default:
      return {
        color: "var(--status-active)",
        background: "var(--status-active-bg)",
      };
  }
}
