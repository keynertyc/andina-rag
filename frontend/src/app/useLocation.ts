import { useCallback, useEffect, useState } from "react";
export type Location = {
  view: "review" | "batches" | "guides";
  batch: string | null;
  proposal: string | null;
  document: string | null;
  status: string;
  offset: number;
  listOffset: number;
  historyOffset: number;
};
const defaults = {
  view: "review",
  status: "pending_review",
  offset: 0,
  listOffset: 0,
  historyOffset: 0,
};
function read(): Location {
  const params = new URLSearchParams(window.location.search);
  const view = params.get("view");
  const status = params.get("status") ?? "pending_review";
  function offset(key: string) {
    const value = Number(params.get(key));
    return Number.isSafeInteger(value) && value >= 0 && value % 50 === 0
      ? value
      : 0;
  }
  return {
    view: view === "batches" || view === "guides" ? view : "review",
    batch: params.get("batch"),
    proposal: params.get("proposal"),
    document: params.get("document"),
    status: ["", "pending_review", "approved", "rejected"].includes(status)
      ? status
      : "pending_review",
    offset: offset("offset"),
    listOffset: offset("listOffset"),
    historyOffset: offset("historyOffset"),
  };
}
export function useLocation() {
  const [location, setLocation] = useState(read);
  const navigate = useCallback(
    (patch: Partial<Location>) =>
      setLocation((current) => ({ ...current, ...patch })),
    [],
  );
  useEffect(() => {
    const params = new URLSearchParams();
    for (const [key, value] of Object.entries(location)) {
      if (value !== null && value !== defaults[key as keyof typeof defaults])
        params.set(key, String(value));
    }
    const query = params.toString();
    window.history.replaceState(
      null,
      "",
      `${window.location.pathname}${query ? `?${query}` : ""}${window.location.hash}`,
    );
  }, [location]);
  return [location, navigate] as const;
}
