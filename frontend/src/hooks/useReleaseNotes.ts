import { useQuery } from "@tanstack/react-query";
import { apiRequest } from "@/lib/api";
import type { ReleaseNotesResponse } from "@/types/version";

export const releaseNotesQueryKey = (
  after: string | null | undefined,
  through: string | null | undefined,
) => ["system", "release-notes", after ?? "", through ?? ""] as const;

async function fetchReleaseNotes(
  after: string,
  through: string,
): Promise<ReleaseNotesResponse> {
  const params = new URLSearchParams({ after, through });
  return apiRequest<ReleaseNotesResponse>(
    "GET",
    `/api/system/release-notes?${params.toString()}`,
  );
}

/**
 * Release notes for a semver range. Fetch when the popover is open — not on
 * every 10-minute version poll (#473).
 */
export function useReleaseNotes(
  after: string | null | undefined,
  through: string | null | undefined,
  enabled: boolean,
) {
  const ready = Boolean(enabled && after && through);
  return useQuery({
    queryKey: releaseNotesQueryKey(after, through),
    queryFn: () => fetchReleaseNotes(after!, through!),
    enabled: ready,
    staleTime: 5 * 60 * 1000,
    retry: false,
  });
}
