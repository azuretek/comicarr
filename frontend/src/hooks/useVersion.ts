import {
  useMutation,
  useQuery,
  useQueryClient,
  type UseMutationResult,
  type UseQueryResult,
} from "@tanstack/react-query";
import { apiRequest } from "@/lib/api";
import type { VersionInfo } from "@/lib/updateStatus";

export const VERSION_QUERY_KEY = ["system", "version"] as const;

export function useVersionInfo(): UseQueryResult<VersionInfo> {
  return useQuery({
    queryKey: VERSION_QUERY_KEY,
    queryFn: () => apiRequest<VersionInfo>("GET", "/api/system/version"),
    staleTime: 10 * 60 * 1000,
    retry: 1,
  });
}

export function useForceVersionCheck(): UseMutationResult<
  VersionInfo,
  Error,
  void
> {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: () =>
      apiRequest<VersionInfo>("POST", "/api/system/version/check"),
    onSuccess: (data) => {
      queryClient.setQueryData(VERSION_QUERY_KEY, data);
    },
  });
}
