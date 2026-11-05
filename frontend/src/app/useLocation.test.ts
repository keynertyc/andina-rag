import { act, renderHook } from "@testing-library/react";
import { beforeEach, expect, it } from "vitest";
import { useLocation } from "./useLocation";
beforeEach(() => window.history.replaceState(null, "", "/"));
it("restaura el documento y la paginación desde un enlace", () => {
  window.history.replaceState(
    null,
    "",
    "/?view=guides&document=guide-1&offset=50&historyOffset=100",
  );
  const { result } = renderHook(useLocation);
  expect(result.current[0]).toMatchObject({
    view: "guides",
    document: "guide-1",
    offset: 50,
    historyOffset: 100,
  });
});
it("combina navegaciones en el mismo evento y conserva el filtro Todos", () => {
  const { result } = renderHook(useLocation);
  act(() => {
    result.current[1]({ view: "guides", document: "guide-2" });
    result.current[1]({ historyOffset: 50, status: "" });
  });
  expect(result.current[0]).toMatchObject({
    view: "guides",
    document: "guide-2",
    historyOffset: 50,
    status: "",
  });
  expect(new URLSearchParams(window.location.search).get("document")).toBe(
    "guide-2",
  );
  expect(new URLSearchParams(window.location.search).get("status")).toBe("");
});
