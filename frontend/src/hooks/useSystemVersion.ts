import { useQuery } from "@tanstack/react-query";
import { apiRequest } from "@/lib/api";
import type { SystemVersionInfo } from "@/types/version";

/** Poll cadence for the update chip (#473 / #460). */
export const SYSTEM_VERSION_POLL_MS = 10 * 60 * 1000;

export const systemVersionQueryKey = ["system", "version"] as const;

async function fetchSystemVersion(): Promise<SystemVersionInfo> {
  return apiRequest<SystemVersionInfo>("GET", "/api/system/version");
}

/**
 * Live update state for the sidebar chip.
 *
 * Only a successful poll with `update_state === "behind"` lights the cue.
 * Transport / 5xx / parse failure → no sticky last-good behind (status leaves
 * success). No SSE path for update availability.
 */
export function useSystemVersion(enabled = true) {
  return useQuery({
    queryKey: systemVersionQueryKey,
    queryFn: fetchSystemVersion,
    enabled,
    refetchInterval: enabled ? SYSTEM_VERSION_POLL_MS : false,
    // Defaults elsewhere turn focus refetch off; this surface needs it (#460).
    refetchOnWindowFocus: true,
    refetchOnMount: true,
    staleTime: 0,
    retry: false,
  });
}

/** True only when the last successful poll says behind. */
export function isUpdateBehind(
  status: "pending" | "error" | "success",
  data: SystemVersionInfo | undefined,
): boolean {
  if (status !== "success" || !data) return false;
  return data.update_state === "behind" && Boolean(data.latest_version);
}
