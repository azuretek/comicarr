import {
  useMutation,
  useQuery,
  useQueryClient,
  type UseMutationResult,
  type UseQueryResult,
} from "@tanstack/react-query";
import { apiRequest } from "@/lib/api";
import { VERSION_QUERY_KEY } from "@/hooks/useVersion";
import type {
  WhatsNewArchiveResponse,
  WhatsNewDismissResponse,
} from "@/types/version";

export const WHATS_NEW_ARCHIVE_QUERY_KEY = [
  "system",
  "whats-new",
  "archive",
] as const;

async function fetchArchive(): Promise<WhatsNewArchiveResponse> {
  return apiRequest<WhatsNewArchiveResponse>(
    "GET",
    "/api/system/whats-new/archive",
  );
}

async function postDismiss(): Promise<WhatsNewDismissResponse> {
  return apiRequest<WhatsNewDismissResponse>(
    "POST",
    "/api/system/whats-new/dismiss",
  );
}

/** Permanent Settings → About archive (server floor/pad). */
export function useWhatsNewArchive(options?: {
  enabled?: boolean;
}): UseQueryResult<WhatsNewArchiveResponse> {
  const enabled = options?.enabled ?? true;
  return useQuery({
    queryKey: WHATS_NEW_ARCHIVE_QUERY_KEY,
    queryFn: fetchArchive,
    enabled,
    staleTime: 60 * 1000,
    retry: false,
  });
}

/**
 * Got it / Mark as read — writes LAST_SEEN_VERSION = current on the server.
 * Invalidates version (pending clears) and the archive list.
 */
export function useDismissWhatsNew(): UseMutationResult<
  WhatsNewDismissResponse,
  Error,
  void
> {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: postDismiss,
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: VERSION_QUERY_KEY });
      void queryClient.invalidateQueries({
        queryKey: WHATS_NEW_ARCHIVE_QUERY_KEY,
      });
    },
  });
}
