import { useQuery } from "@tanstack/react-query";
import { apiPage } from "../../shared/api/client";
import { indexing } from "../../shared/api/queries";
import type { Guide } from "../../shared/api/types";

async function guideOptions(signal: AbortSignal) {
  const guides: Guide[] = [];
  for (let offset = 0; ; offset += 200) {
    const page = await apiPage<Guide>(
      `/documents?latest_only=true&limit=200&offset=${offset}`,
      signal,
    );
    guides.push(...page.items);
    if (!page.hasMore) return guides;
  }
}
export function useGuideCatalog() {
  return useQuery({
    queryKey: ["guide-options"],
    queryFn: ({ signal }) => guideOptions(signal),
    refetchInterval: (query) =>
      query.state.data && indexing(query.state.data) ? 2000 : false,
  });
}
