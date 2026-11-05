import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import type { Proposal } from "../types";
import { ProposalForm } from "./ProposalDetail";

const proposal: Proposal = {
  id: "p1",
  product_id: "MA-001",
  batch_id: "b1",
  status: "pending_review",
  revision: 1,
  is_stale: false,
  original: {
    id: "MA-001",
    title: "BUFANDA",
    description: "Lana azul",
    brand: "Puna",
    category: "textiles",
    tags: [],
  },
  content: {
    title: "Puna Bufanda",
    description: "Bufanda de lana azul.",
    tags: ["puna"],
    citations: ["c1"],
  },
  citations: [
    {
      id: "c1",
      text: "El título empieza por la marca.",
      document_title: "Guía Puna",
      version: 1,
      page: 2,
      heading: null,
    },
  ],
};

describe("Revisión de propuestas", () => {
  it("muestra original y citas y persiste edición con aprobación", async () => {
    const updated = { ...proposal, status: "approved", revision: 2 };
    const fetchMock = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValue(
        new Response(JSON.stringify(updated), { status: 200 }),
      );
    const onSaved = vi.fn();
    render(
      <ProposalForm
        proposal={proposal}
        onSaved={onSaved}
        onBatch={vi.fn()}
        onReload={vi.fn()}
      />,
    );
    expect(screen.getByText("BUFANDA")).toBeVisible();
    expect(screen.getByText("El título empieza por la marca.")).toBeVisible();
    fireEvent.change(screen.getByLabelText(/Título/), {
      target: { value: "Puna Bufanda azul" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Aprobar" }));
    await waitFor(() => expect(onSaved).toHaveBeenCalledWith(updated));
    const options = fetchMock.mock.calls[0][1];
    expect(JSON.parse(options?.body as string)).toMatchObject({
      title: "Puna Bufanda azul",
      status: "approved",
      revision: 1,
    });
  });

  it("bloquea aprobación desactualizada y mantiene citas visibles", () => {
    render(
      <ProposalForm
        proposal={{ ...proposal, is_stale: true }}
        onSaved={vi.fn()}
        onBatch={vi.fn()}
        onReload={vi.fn()}
      />,
    );
    expect(screen.getByRole("button", { name: "Aprobar" })).toBeDisabled();
    expect(screen.getByText("Las guías cambiaron.")).toBeVisible();
    expect(screen.getByText("El título empieza por la marca.")).toBeVisible();
  });

  it("explica un conflicto y no confirma una escritura fallida", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(
        JSON.stringify({
          error: {
            code: "REVISION_CONFLICT",
            message: "La propuesta cambió; recarga antes de guardar",
          },
        }),
        { status: 409 },
      ),
    );
    const saved = vi.fn();
    render(
      <ProposalForm
        proposal={proposal}
        onSaved={saved}
        onBatch={vi.fn()}
        onReload={vi.fn()}
      />,
    );
    fireEvent.click(screen.getByRole("button", { name: "Rechazar" }));
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "La propuesta cambió",
    );
    expect(saved).not.toHaveBeenCalled();
  });
});
