import { act, render, screen, waitFor } from "@testing-library/react";
import { QueryClientProvider } from "@tanstack/react-query";
import { expect, it, vi } from "vitest";
import { createQueryClient, resourceKey } from "../../shared/api/queries";
import { Review } from "./Review";

vi.mock("./ProposalDetail", () => ({
  ProposalDetail: ({ id }: { id: string }) => <div>Detalle {id}</div>,
}));

it("actualiza propuestas de un lote activo fuera de los 50 más recientes", async () => {
  let completed = false;
  const proposal = {
    id: "p-old",
    product_id: "P-1",
    original: { category: "textiles" },
    content: { title: "Propuesta recuperada" },
    status: "pending_review",
    is_stale: false,
  };
  const fetchMock = vi
    .spyOn(globalThis, "fetch")
    .mockImplementation(async (input) => {
      const path = String(input);
      const body = path.endsWith("/batches/old-batch")
        ? {
            id: "old-batch",
            terminal: completed,
            status: completed ? "completed" : "running",
          }
        : path.includes("/proposals?") && completed
          ? [proposal]
          : [];
      return new Response(JSON.stringify(body), {
        headers: { "X-Has-More": "false" },
      });
    });
  const client = createQueryClient();
  const location = {
    view: "review" as const,
    batch: "old-batch",
    proposal: null,
    document: null,
    status: "pending_review",
    offset: 0,
    listOffset: 0,
    historyOffset: 0,
  };
  render(
    <QueryClientProvider client={client}>
      <Review location={location} navigate={vi.fn()} onBatch={vi.fn()} />
    </QueryClientProvider>,
  );
  await waitFor(() =>
    expect(
      fetchMock.mock.calls.some(([url]) =>
        String(url).endsWith("/batches/old-batch"),
      ),
    ).toBe(true),
  );
  completed = true;
  await act(async () => {
    await client.refetchQueries({
      queryKey: resourceKey("/batches/old-batch"),
    });
  });
  expect(await screen.findByText("Propuesta recuperada")).toBeVisible();
  client.clear();
});
