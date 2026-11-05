import { describe, expect, it, vi } from "vitest";
import { api, apiPage, ApiError } from "./client";

describe("Contrato HTTP", () => {
  it("rechaza JSON inválido en vez de entregar un objeto vacío a la vista", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response("<html>nginx</html>", { status: 200 }),
    );
    await expect(api("/proposals")).rejects.toMatchObject({
      code: "INVALID_RESPONSE",
      status: 200,
    });
  });
  it("conserva estado, filas y trace ID para errores accionables", async () => {
    const rows = [{ row: 3, fields: ["brand"] }];
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(
        JSON.stringify({
          error: {
            code: "INVALID_PRODUCTS",
            message: "Corrige las filas",
            rows,
          },
        }),
        { status: 422, headers: { "X-Trace-ID": "abc123" } },
      ),
    );
    await expect(api("/batches")).rejects.toMatchObject({
      status: 422,
      details: { rows },
      traceId: "abc123",
    });
  });
  it("lee la paginación del servidor y conserva cancelación", async () => {
    const signal = new AbortController().signal;
    const fetchMock = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValue(
        new Response("[]", { headers: { "X-Has-More": "true" } }),
      );
    expect(await apiPage("/batches?limit=50", signal)).toEqual({
      items: [],
      hasMore: true,
    });
    expect(fetchMock.mock.calls[0][1]?.signal).toBeInstanceOf(AbortSignal);
  });
  it("explica una caída del proxy aunque su respuesta no sea JSON", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response("Bad Gateway", { status: 502 }),
    );
    await expect(api("/batches")).rejects.toBeInstanceOf(ApiError);
  });
});
