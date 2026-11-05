import { QueryClient, useQuery } from "@tanstack/react-query";
import { api, apiPage, ApiError, type Page } from "./client";

export function createQueryClient() {
  return new QueryClient({
    defaultOptions: {
      queries: {
        staleTime: 10000,
        gcTime: 300000,
        refetchOnWindowFocus: true,
        refetchIntervalInBackground: false,
        networkMode: "always",
        retry: (count, error) =>
          count < 2 &&
          error instanceof ApiError &&
          (error.status >= 500 || ["NETWORK", "TIMEOUT"].includes(error.code)),
      },
      mutations: { retry: false, networkMode: "always" },
    },
  });
}
export const resourceKey = (path: string) => ["api", path] as const;
export function useResource<T>(
  path: string | null,
  interval: number | ((value: T) => boolean) = 0,
) {
  return useQuery({
    queryKey: resourceKey(path ?? "disabled"),
    enabled: !!path,
    queryFn: ({ signal }) => api<T>(path!, { signal }),
    refetchInterval: (query) =>
      typeof interval === "number"
        ? interval || false
        : query.state.data && interval(query.state.data)
          ? 2000
          : false,
  });
}
export function usePage<T>(
  path: string | null,
  active?: (rows: T[]) => boolean,
) {
  return useQuery({
    queryKey: resourceKey(path ?? "disabled-page"),
    enabled: !!path,
    queryFn: ({ signal }) => apiPage<T>(path!, signal),
    refetchInterval: (query) =>
      active && query.state.data && active(query.state.data.items)
        ? 2000
        : false,
  });
}
export function invalidateResources(client: QueryClient, prefix: string) {
  return client.invalidateQueries({
    predicate: (query) =>
      typeof query.queryKey[1] === "string" &&
      query.queryKey[1].startsWith(prefix),
  });
}
export function hasActiveWork(rows: { terminal: boolean }[]) {
  return rows.some((row) => !row.terminal);
}
export function indexing(rows: { status: string }[]) {
  return rows.some((row) => ["pending", "indexing"].includes(row.status));
}
export type { Page };
