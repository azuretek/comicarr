import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiRequest } from "@/lib/api";
import type { PaginationMeta } from "@/types";

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
