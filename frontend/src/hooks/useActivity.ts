import {
  useInfiniteQuery,
  useMutation,
  useQuery,
  useQueryClient,
} from "@tanstack/react-query";
import { apiRequest } from "@/lib/api";
import type {
  BandPage,
  TimelinePage,
} from "@/components/activity/timeline/types";
import type { PaginationMeta } from "@/types";

/** Permanent 30s poll for open timeline/band surfaces (Activity Center ADR §8). */
export const ACTIVITY_POLL_MS = 30_000;

/** Event page size for infinite timeline fetches (story page of 25 is client-side). */
export const TIMELINE_EVENT_PAGE_SIZE = 100;

export type ActivityScope = {
  scope_type?: string | null;
  scope_id?: string | null;
};

export type BandResolutionAction =
  "retry" | "search-again" | "ignore" | "import";

interface BandResolutionResult {
  success: boolean;
  error?: string;
  message?: string;
  status?: string;
  action?: string;
  release_key?: string;
}

export interface HistoryItem {
  IssueID: string;
  ComicName: string;
  Issue_Number: string;
  Size: number;
  DateAdded: string;
  Status: string;
  FolderName: string;
  ComicID: string;
  Provider: string;
}

interface HistoryResponse {
  history: HistoryItem[];
  pagination: PaginationMeta;
}

export interface QueueItem {
  ID: string;
  series: string;
  year: string;
  filename: string;
  size: string;
  issueid: string;
  comicid: string;
  link: string;
  status: string;
  remote_filesize: string;
  updated_date: string;
  site: string;
  submit_date: string;
}

interface QueueResponse {
  queue: QueueItem[];
  pagination: PaginationMeta;
}

interface RequeueDownloadResult {
  success: boolean;
  error?: string;
}

interface ActivityQuery {
  limit: number;
  offset: number;
  q?: string;
  status?: string;
  sort: string;
  order: "asc" | "desc";
}

function activityUrl(path: string, query: ActivityQuery): string {
  const params = new URLSearchParams({
    limit: String(query.limit),
    offset: String(query.offset),
    sort: query.sort,
    order: query.order,
  });
  if (query.q?.trim()) params.set("q", query.q.trim());
  if (query.status?.trim()) params.set("status", query.status.trim());
  return `${path}?${params.toString()}`;
}

export function useDownloadHistory(query: ActivityQuery) {
  return useQuery<HistoryResponse>({
    queryKey: ["downloads", "history", query],
    queryFn: () =>
      apiRequest<HistoryResponse>(
        "GET",
        activityUrl("/api/downloads/history", query),
      ),
    staleTime: 30 * 1000, // 30 seconds
  });
}

export function useDownloadQueue(query: ActivityQuery) {
  return useQuery<QueueResponse>({
    queryKey: ["downloads", "queue", query],
    queryFn: () =>
      apiRequest<QueueResponse>(
        "GET",
        activityUrl("/api/downloads/queue", query),
      ),
    staleTime: 10 * 1000, // 10 seconds — queue data is transient
    refetchInterval: 15 * 1000, // Poll every 15 seconds
  });
}

/**
 * Requeue only a failed DDL queue item through the server's validated retry
 * endpoint. Other downloader states deliberately have no client-side retry.
 */
export function useRequeueDownload() {
  const queryClient = useQueryClient();
  return useMutation<RequeueDownloadResult, Error, string>({
    mutationFn: async (itemId) => {
      const result = await apiRequest<RequeueDownloadResult>(
        "POST",
        `/api/downloads/${encodeURIComponent(itemId)}/requeue`,
      );
      if (!result.success) {
        throw new Error(
          result.error || "Unable to requeue the direct download.",
        );
      }
      return result;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["downloads", "queue"] });
    },
  });
}

function scopeParams(scope?: ActivityScope): URLSearchParams {
  const params = new URLSearchParams();
  const type = scope?.scope_type?.trim();
  const id = scope?.scope_id?.trim();
  if (type && id) {
    params.set("scope_type", type);
    params.set("scope_id", id);
  }
  return params;
}

/**
 * Narrative timeline events (newest first). Pages *events* via infinite query;
 * story grouping of 25 is a client concern. Polls every 30s while mounted.
 */
export function useActivityTimeline(options: ActivityScope = {}) {
  const scope_type = options.scope_type?.trim() || undefined;
  const scope_id = options.scope_id?.trim() || undefined;
  const limit = TIMELINE_EVENT_PAGE_SIZE;

  return useInfiniteQuery({
    queryKey: ["activity", "timeline", { limit, scope_type, scope_id }],
    queryFn: ({ pageParam }) => {
      const params = scopeParams({ scope_type, scope_id });
      params.set("limit", String(limit));
      params.set("offset", String(pageParam));
      return apiRequest<TimelinePage>(
        "GET",
        `/api/activity/timeline?${params.toString()}`,
      );
    },
    initialPageParam: 0,
    getNextPageParam: (lastPage) =>
      lastPage.has_more ? lastPage.offset + lastPage.limit : undefined,
    staleTime: ACTIVITY_POLL_MS,
    refetchInterval: ACTIVITY_POLL_MS,
  });
}

/**
 * Needs-attention band from pipeline_journal (derived, never narrative).
 * Polls every 30s while mounted.
 */
export function useActivityBand(scope: ActivityScope = {}) {
  const scope_type = scope.scope_type?.trim() || undefined;
  const scope_id = scope.scope_id?.trim() || undefined;

  return useQuery<BandPage>({
    queryKey: ["activity", "band", { scope_type, scope_id }],
    queryFn: () => {
      const params = scopeParams({ scope_type, scope_id });
      const qs = params.toString();
      return apiRequest<BandPage>(
        "GET",
        qs ? `/api/activity/band?${qs}` : "/api/activity/band",
      );
    },
    staleTime: ACTIVITY_POLL_MS,
    refetchInterval: ACTIVITY_POLL_MS,
  });
}

/**
 * Operator exits for band rows via POST /api/downloads/needs-attention/...
 * Invalidates band + timeline on success.
 */
export function useBandResolution() {
  const queryClient = useQueryClient();
  return useMutation<
    BandResolutionResult,
    Error,
    { releaseKey: string; action: BandResolutionAction }
  >({
    mutationFn: async ({ releaseKey, action }) => {
      const result = await apiRequest<BandResolutionResult>(
        "POST",
        `/api/downloads/needs-attention/${encodeURIComponent(releaseKey)}/${action}`,
      );
      if (!result.success) {
        throw new Error(
          result.error || result.message || `Unable to ${action} this item.`,
        );
      }
      return result;
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["activity", "band"] });
      void queryClient.invalidateQueries({
        queryKey: ["activity", "timeline"],
      });
    },
  });
}
