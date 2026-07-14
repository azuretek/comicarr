import { useQuery } from "@tanstack/react-query";
import { useDownloadQueue } from "@/hooks/useActivity";
import { useDashboard } from "@/hooks/useDashboard";
import { apiRequest } from "@/lib/api";

const STATUS_POLL_MS = 30 * 1000;
const STATUS_QUEUE_QUERY = {
  limit: 1,
  offset: 0,
  sort: "updated",
  order: "desc" as const,
};

interface HealthResponse {
  status: string;
}

function countLabel(count: number, singular: string, plural = `${singular}s`) {
  return `${count} ${count === 1 ? singular : plural}`;
}

/**
 * A compact, independently refreshed summary of the application's live state.
 * Dashboard data shares React Query's cache with the dashboard page, avoiding
 * duplicate requests when both are visible.
 */
export default function AppStatusBar() {
  const dashboard = useDashboard();
  const queue = useDownloadQueue(STATUS_QUEUE_QUERY);
  const health = useQuery<HealthResponse>({
    queryKey: ["app", "health"],
    queryFn: () => apiRequest<HealthResponse>("GET", "/api/health"),
    staleTime: 15 * 1000,
    refetchInterval: STATUS_POLL_MS,
  });

  const libraryStatus = dashboard.isPending
    ? "loading…"
    : dashboard.data
      ? countLabel(dashboard.data.stats.total_series ?? 0, "series", "series")
      : "unavailable";
  const queueStatus = queue.isPending
    ? "loading…"
    : queue.data
      ? `${queue.data.pagination.total} active`
      : "unavailable";
  const apiStatus = health.isPending
    ? "checking…"
    : health.data?.status === "ok"
      ? "online"
      : "unavailable";
  const apiStatusColor =
    apiStatus === "online"
      ? "var(--status-active)"
      : apiStatus === "unavailable"
        ? "var(--status-error)"
        : undefined;

  return (
    <div
      className="flex min-w-0 items-center gap-3 font-mono text-[11px] text-muted-foreground"
      aria-label="Application status"
      aria-live="polite"
    >
      <span title="Active series in your library">
        library: <span className="text-foreground">{libraryStatus}</span>
      </span>
      <span aria-hidden="true">·</span>
      <span title="Connection to the Comicarr API">
        api:{" "}
        <span className="text-foreground" style={{ color: apiStatusColor }}>
          {apiStatus}
        </span>
      </span>
      <span aria-hidden="true">·</span>
      <span title="Active direct downloads">
        queue: <span className="text-foreground">{queueStatus}</span>
      </span>
    </div>
  );
}
