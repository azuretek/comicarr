import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiRequest } from "@/lib/api";

export interface WeeklyRefreshResult {
  accepted: boolean;
  state: "queued" | "running" | "paused";
  message?: string;
  error?: string;
}

export interface ScheduledJob {
  id: string;
  name: string;
  next_run_time: string | null;
  trigger: string;
  status?: string | null;
  last_success_timestamp?: number | null;
  last_failure_timestamp?: number | null;
  last_error?: string | null;
}

interface JobsResponse {
  jobs: ScheduledJob[];
}

export function useWeeklyRefresh() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () =>
      apiRequest<WeeklyRefreshResult>("POST", "/api/weekly/refresh"),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["system", "jobs"] });
    },
  });
}

export function useScheduledJobs(enabled: boolean) {
  return useQuery<JobsResponse>({
    queryKey: ["system", "jobs"],
    queryFn: () => apiRequest<JobsResponse>("GET", "/api/system/jobs"),
    enabled,
    staleTime: 0,
    refetchInterval: (query) => {
      const weekly = query.state.data?.jobs.find((job) => job.id === "weekly");
      const status = weekly?.status?.toLowerCase();
      return status === "running" || status === "queued" ? 2_000 : false;
    },
  });
}
