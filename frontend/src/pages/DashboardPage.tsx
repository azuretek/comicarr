import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { RefreshCw } from "lucide-react";
import ErrorDisplay from "@/components/ui/ErrorDisplay";
import RelativeTime from "@/components/ui/RelativeTime";
import { useToast } from "@/components/ui/toast";
import { useDashboard, type DashboardQueueItem } from "@/hooks/useDashboard";
import {
  useComicScan,
  useComicScanProgress,
  useMangaScan,
  useMangaScanProgress,
} from "@/hooks/useImport";

function Kpi({
  label,
  value,
  borderLeft,
}: {
  label: string;
  value: string;
  borderLeft?: boolean;
}) {
  return (
    <div className={`px-5 py-4 ${borderLeft ? "border-l border-border" : ""}`}>
      <div className="mono-label">{label}</div>
      <div className="flex items-end gap-2 mt-1.5">
        <div className="text-[26px] font-semibold tracking-tight leading-none">
          {value}
        </div>
      </div>
    </div>
  );
}

function QueueStatus({ status }: { status: DashboardQueueItem["status"] }) {
  const normalized = (status || "queued").toLowerCase();
  const color = normalized.includes("fail")
    ? "var(--status-error)"
    : normalized.includes("download")
      ? "var(--status-active)"
      : "var(--status-paused)";

  return (
    <span className="uppercase truncate" style={{ color }}>
      {status || "Queued"}
    </span>
  );
}

export default function DashboardPage() {
  const { data, isLoading, error } = useDashboard();
  const comicScan = useComicScan();
  const mangaScan = useMangaScan();
  const [comicScanning, setComicScanning] = useState(false);
  const [mangaScanning, setMangaScanning] = useState(false);
  const { data: comicScanProgress, error: comicProgressError } =
    useComicScanProgress(comicScanning);
  const { data: mangaScanProgress, error: mangaProgressError } =
    useMangaScanProgress(mangaScanning);
  const { addToast } = useToast();

  useEffect(() => {
    if (
      !comicScanning ||
      !["completed", "error"].includes(comicScanProgress?.status || "")
    )
      return;
    // eslint-disable-next-line react-hooks/set-state-in-effect -- Sync the dashboard action with server scan state
    setComicScanning(false);
    if (comicScanProgress?.status === "error") {
      addToast({ type: "error", message: "Comic library scan failed." });
    }
  }, [comicScanning, comicScanProgress?.status, addToast]);

  useEffect(() => {
    if (
      !mangaScanning ||
      !["completed", "error"].includes(mangaScanProgress?.status || "")
    )
      return;
    // eslint-disable-next-line react-hooks/set-state-in-effect -- Sync the dashboard action with server scan state
    setMangaScanning(false);
    if (mangaScanProgress?.status === "error") {
      addToast({ type: "error", message: "Manga library scan failed." });
    }
  }, [mangaScanning, mangaScanProgress?.status, addToast]);

  useEffect(() => {
    if (!comicScanning || !comicProgressError) return;
    // eslint-disable-next-line react-hooks/set-state-in-effect -- Release a dashboard action whose progress request failed
    setComicScanning(false);
    addToast({
      type: "error",
      message: "Unable to monitor comic library scan.",
    });
  }, [comicScanning, comicProgressError, addToast]);

  useEffect(() => {
    if (!mangaScanning || !mangaProgressError) return;
    // eslint-disable-next-line react-hooks/set-state-in-effect -- Release a dashboard action whose progress request failed
    setMangaScanning(false);
    addToast({
      type: "error",
      message: "Unable to monitor manga library scan.",
    });
  }, [mangaScanning, mangaProgressError, addToast]);

  if (error) {
    return (
      <div className="p-8">
        <ErrorDisplay
          error={error}
          title="Unable to load dashboard"
          onRetry={() => window.location.reload()}
        />
      </div>
    );
  }

  const stats = data?.stats;
  const downloads = data?.recently_downloaded || [];
  const activeQueue = data?.active_queue || [];
  const upcoming = data?.upcoming_releases || [];

  const activeSeries = stats?.total_series ?? 0;
  const totalIssues = stats?.total_issues ?? 0;
  const completion = stats?.completion_pct ?? 0;
  const queueCount = stats?.queue_count ?? 0;
  const scanPending =
    comicScan.isPending ||
    mangaScan.isPending ||
    comicScanning ||
    mangaScanning;
  const canScan = Boolean(
    data?.scan_targets?.comic || data?.scan_targets?.manga,
  );

  const handleLibraryScan = async () => {
    const scans: { type: "comic" | "manga"; request: Promise<unknown> }[] = [];
    if (data?.scan_targets?.comic) {
      scans.push({ type: "comic", request: comicScan.mutateAsync() });
    }
    if (data?.scan_targets?.manga) {
      scans.push({ type: "manga", request: mangaScan.mutateAsync() });
    }

    if (scans.length === 0) {
      addToast({
        type: "error",
        message:
          "Configure a comic or manga library directory before scanning.",
      });
      return;
    }

    const results = await Promise.allSettled(scans.map((scan) => scan.request));
    results.forEach((result, index) => {
      if (result.status !== "fulfilled") return;
      if (scans[index].type === "comic") setComicScanning(true);
      else setMangaScanning(true);
    });
    const started = results.filter(
      (result) => result.status === "fulfilled",
    ).length;
    if (started === scans.length) {
      addToast({
        type: "success",
        message: `${started === 2 ? "Comic and manga library scans" : "Library scan"} started.`,
      });
    } else if (started > 0) {
      addToast({
        type: "error",
        message: "One library scan started, but another failed to start.",
      });
    } else {
      addToast({ type: "error", message: "Failed to start library scans." });
    }
  };

  return (
    <div className="h-full flex flex-col page-transition">
      {/* Page header */}
      <div className="px-5 py-4 border-b border-border flex items-center justify-between gap-3">
        <div>
          <div className="text-[18px] font-semibold tracking-tight">
            Dashboard
          </div>
          <div className="font-mono text-[11px] text-muted-foreground mt-0.5">
            {isLoading
              ? "loading…"
              : `${activeSeries} series · ${totalIssues} issues · ${queueCount} in queue`}
          </div>
        </div>
        <button
          type="button"
          onClick={() => void handleLibraryScan()}
          disabled={!canScan || scanPending}
          title={
            canScan
              ? "Scan configured comic and manga libraries"
              : "Configure a library directory first"
          }
          className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-[5px] border text-[12px] font-medium disabled:opacity-50"
          style={{ borderColor: "var(--border)" }}
        >
          <RefreshCw
            className={`w-3.5 h-3.5 ${scanPending ? "animate-spin" : ""}`}
          />
          {scanPending ? "Scanning…" : "Scan libraries"}
        </button>
      </div>

      {/* KPI strip */}
      <div className="grid grid-cols-2 lg:grid-cols-4 border-b border-border">
        <Kpi
          label="Active series"
          value={isLoading ? "—" : String(activeSeries)}
        />
        <Kpi
          label="Issues"
          value={isLoading ? "—" : String(totalIssues)}
          borderLeft
        />
        <Kpi
          label="Completion"
          value={isLoading ? "—" : `${completion.toFixed(1)}%`}
          borderLeft
        />
        <Kpi label="Queue" value={String(queueCount)} borderLeft />
      </div>

      {/* Operational summaries */}
      <div className="grid grid-cols-1 lg:grid-cols-[2fr_1fr] border-b border-border min-h-[320px]">
        {/* Active queue and recent history */}
        <section className="px-5 py-4 lg:border-r lg:border-border">
          <div className="flex items-center justify-between gap-3 mb-3">
            <div className="flex items-center gap-2.5">
              <div className="text-[13px] font-semibold">Active queue</div>
              <div className="font-mono text-[10px] text-[var(--text-muted)] tracking-wider uppercase">
                {queueCount} item{queueCount === 1 ? "" : "s"}
              </div>
            </div>
            <Link
              to="/activity"
              className="font-mono text-[10px] text-muted-foreground hover:text-foreground"
            >
              open queue →
            </Link>
          </div>

          {isLoading && (
            <div className="font-mono text-[11px] text-muted-foreground py-3">
              loading queue…
            </div>
          )}

          {!isLoading && activeQueue.length === 0 && (
            <div className="font-mono text-[11px] text-muted-foreground py-3">
              queue is clear
            </div>
          )}

          <div className="font-mono text-[11px]">
            {activeQueue.map((item, index) => (
              <div
                key={item.ID}
                className="grid items-center gap-2 py-1.5"
                style={{
                  gridTemplateColumns: "minmax(140px, 1fr) 100px 120px",
                  borderTop:
                    index > 0
                      ? "1px solid var(--border-soft, var(--border))"
                      : "none",
                }}
              >
                <div className="min-w-0">
                  <div className="font-sans text-foreground truncate">
                    {item.series || item.filename || "Unnamed download"}
                  </div>
                  {item.filename && item.filename !== item.series && (
                    <div className="text-muted-foreground truncate">
                      {item.filename}
                    </div>
                  )}
                </div>
                <QueueStatus status={item.status} />
                <span className="text-muted-foreground truncate text-right">
                  {item.updated_date ? (
                    <RelativeTime value={item.updated_date} />
                  ) : (
                    "—"
                  )}
                </span>
              </div>
            ))}
          </div>

          <div className="mt-5 pt-4 border-t border-border">
            <div className="flex items-center justify-between gap-3 mb-3">
              <div className="flex items-center gap-2.5">
                <div className="text-[13px] font-semibold">Recent activity</div>
                <div className="font-mono text-[10px] text-[var(--text-muted)] tracking-wider uppercase">
                  {downloads.length} event{downloads.length === 1 ? "" : "s"} ·
                  30 days
                </div>
              </div>
              <Link
                to="/activity?view=history"
                className="font-mono text-[10px] text-muted-foreground hover:text-foreground"
              >
                open history →
              </Link>
            </div>

            {isLoading && (
              <div className="font-mono text-[11px] text-muted-foreground py-4">
                loading recent activity…
              </div>
            )}

            {!isLoading && downloads.length === 0 && (
              <div className="font-mono text-[11px] text-muted-foreground py-4">
                no activity in the last 30 days —{" "}
                <Link
                  to="/activity?view=history"
                  className="hover:text-foreground"
                >
                  open full history
                </Link>
              </div>
            )}

            <div className="font-mono text-[11px]">
              {downloads.slice(0, 5).map((d, i) => {
                const action = d.Status?.toLowerCase() || "—";
                const color = action.includes("down")
                  ? "var(--chart-4)"
                  : action.includes("post") || action.includes("import")
                    ? "var(--status-active)"
                    : action.includes("snatch") || action.includes("queue")
                      ? "var(--status-paused)"
                      : "var(--muted-foreground)";
                return (
                  <div
                    key={`${d.ComicID}-${d.IssueID}-${i}`}
                    className="grid items-center gap-2 py-1.5"
                    style={{
                      gridTemplateColumns:
                        "120px 90px minmax(180px, 1fr) 140px",
                      borderTop:
                        i > 0
                          ? "1px solid var(--border-soft, var(--border))"
                          : "none",
                    }}
                  >
                    <RelativeTime value={d.DateAdded} />
                    <span className="uppercase truncate" style={{ color }}>
                      {action}
                    </span>
                    <div className="flex items-center gap-2 min-w-0">
                      {d.ComicID && (
                        <img
                          src={`/api/metadata/art/${d.ComicID}`}
                          alt=""
                          className="w-4 h-6 object-cover rounded-[1px] shrink-0"
                          onError={(e) => {
                            e.currentTarget.style.visibility = "hidden";
                          }}
                        />
                      )}
                      <Link
                        to={`/library/${d.ComicID}`}
                        className="font-sans text-foreground truncate hover:text-[var(--primary)]"
                      >
                        {d.ComicName} #{d.Issue_Number}
                      </Link>
                    </div>
                    <span className="text-muted-foreground truncate">
                      {d.Provider || "—"}
                    </span>
                  </div>
                );
              })}
            </div>
          </div>
        </section>

        {/* This week */}
        <section className="px-5 py-4">
          <div className="flex items-center justify-between gap-3 mb-3">
            <div className="flex items-center gap-2.5">
              <div className="text-[13px] font-semibold">This week</div>
              <div className="font-mono text-[10px] text-[var(--text-muted)] tracking-wider uppercase">
                {upcoming.length} releases
              </div>
            </div>
            <Link
              to="/releases?view=mine"
              className="font-mono text-[10px] text-muted-foreground hover:text-foreground"
            >
              view mine →
            </Link>
          </div>

          {isLoading && (
            <div className="font-mono text-[11px] text-muted-foreground py-4">
              loading releases…
            </div>
          )}

          {!isLoading && upcoming.length === 0 && (
            <div className="font-mono text-[11px] text-muted-foreground py-4">
              nothing upcoming this week
            </div>
          )}

          {upcoming.slice(0, 6).map((u, i) => (
            <div
              key={`${u.ComicID}-${u.IssueNumber}-${i}`}
              className="flex items-center gap-2.5 py-2.5"
              style={{
                borderTop:
                  i > 0
                    ? "1px solid var(--border-soft, var(--border))"
                    : "none",
              }}
            >
              <div className="font-mono text-[10px] text-muted-foreground w-12 shrink-0">
                {u.IssueDate?.slice(5) || "—"}
              </div>
              <div className="flex-1 min-w-0">
                <Link
                  to={`/library/${u.ComicID}`}
                  className="text-[12px] truncate block hover:text-[var(--primary)]"
                >
                  {u.ComicName}
                </Link>
                <div className="font-mono text-[10px] text-[var(--text-muted)]">
                  #{u.IssueNumber}
                </div>
              </div>
              <div className="font-mono text-[10px] text-[var(--text-muted)]">
                {u.Status || "auto"}
              </div>
            </div>
          ))}

          <div className="mt-4 p-3 rounded-[6px] border border-border bg-card">
            <div
              className="font-mono text-[10px] mb-1.5"
              style={{ color: "var(--primary)" }}
            >
              ⌘K · COMMAND HINT
            </div>
            <div className="text-[12px] text-muted-foreground leading-relaxed">
              Try <span className="text-foreground">"search wolverine"</span>,{" "}
              <span className="text-foreground">"queue pause"</span>, or{" "}
              <span className="text-foreground">"import /downloads/new"</span>.
            </div>
          </div>
        </section>
      </div>
    </div>
  );
}
