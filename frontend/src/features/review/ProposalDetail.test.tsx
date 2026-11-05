import {
  fireEvent,
  render as renderComponent,
  screen,
  waitFor,
} from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import type { Proposal } from "../../shared/api/types";
import { QueryClientProvider } from "@tanstack/react-query";
import { createQueryClient } from "../../shared/api/queries";
import { NavigationGuard } from "../../app/NavigationGuard";
import { ProposalForm } from "./ProposalForm";

const proposal: Proposal = {
  id: "p1",
  product_id: "MA-001",
  batch_id: "b1",
  status: "pending_review",
  revision: 1,
  is_stale: false,
  allowed_actions: ["edit", "approve", "reject"],
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

function render(ui: React.ReactNode) {
  return renderComponent(
    <QueryClientProvider client={createQueryClient()}>
      <NavigationGuard>{ui}</NavigationGuard>
    </QueryClientProvider>,
  );
}

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
        proposal={{
          ...proposal,
          is_stale: true,
          allowed_actions: ["reject", "regenerate"],
        }}
        onSaved={vi.fn()}
        onBatch={vi.fn()}
        onReload={vi.fn()}
      />,
    );
    expect(
      screen.queryByRole("button", { name: "Aprobar" }),
    ).not.toBeInTheDocument();
    expect(screen.getByLabelText(/Título/)).toHaveAttribute("readonly");
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

it.each(["approved", "rejected"] as const)(
  "%s es de solo lectura hasta reabrir",
  (status) => {
    render(
      <ProposalForm
        proposal={{ ...proposal, status, allowed_actions: ["reopen"] }}
        onSaved={vi.fn()}
        onBatch={vi.fn()}
        onReload={vi.fn()}
      />,
    );
    expect(screen.getByLabelText(/Título/)).toHaveAttribute("readonly");
    expect(
      screen.queryByRole("button", { name: "Aprobar" }),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "Rechazar" }),
    ).not.toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Reabrir revisión" }),
    ).toBeEnabled();
  },
);

it("deshabilita guardar sin cambios y aprobar con campos inválidos", () => {
  render(
    <ProposalForm
      proposal={proposal}
      onSaved={vi.fn()}
      onBatch={vi.fn()}
      onReload={vi.fn()}
    />,
  );
  expect(
    screen.getByRole("button", { name: "Guardar cambios" }),
  ).toBeDisabled();
  fireEvent.change(screen.getByLabelText(/Título/), {
    target: { value: "  " },
  });
  expect(
    screen.getByRole("button", { name: "Guardar cambios" }),
  ).toBeDisabled();
  expect(screen.getByRole("button", { name: "Aprobar" })).toBeDisabled();
  expect(
    screen.getByText("El título debe tener entre 1 y 160 caracteres."),
  ).toBeVisible();
});

it("conserva el borrador cuando cambia la revisión del servidor", () => {
  const client = createQueryClient();
  const saved = vi.fn();
  const view = (value: Proposal) => (
    <QueryClientProvider client={client}>
      <NavigationGuard>
        <ProposalForm
          proposal={value}
          onSaved={saved}
          onBatch={vi.fn()}
          onReload={vi.fn()}
        />
      </NavigationGuard>
    </QueryClientProvider>
  );
  const { rerender } = renderComponent(view(proposal));
  fireEvent.change(screen.getByLabelText(/Título/), {
    target: { value: "Mi borrador" },
  });
  rerender(
    view({
      ...proposal,
      revision: 2,
      content: { ...proposal.content, title: "Cambio remoto" },
    }),
  );
  expect(screen.getByLabelText(/Título/)).toHaveValue("Mi borrador");
  expect(
    screen.getByText("Hay una revisión más reciente. Tu borrador se conserva."),
  ).toBeVisible();
  expect(
    screen.getByRole("button", { name: "Guardar cambios" }),
  ).toBeDisabled();
});

it("pide confirmar el descarte y rechaza sin enviar el borrador", async () => {
  const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(
    new Response(
      JSON.stringify({
        ...proposal,
        status: "rejected",
        revision: 2,
        allowed_actions: ["reopen"],
      }),
      { status: 200 },
    ),
  );
  render(
    <ProposalForm
      proposal={proposal}
      onSaved={vi.fn()}
      onBatch={vi.fn()}
      onReload={vi.fn()}
    />,
  );
  fireEvent.change(screen.getByLabelText(/Título/), {
    target: { value: "Borrador" },
  });
  fireEvent.click(screen.getByRole("button", { name: "Rechazar" }));
  expect(fetchMock).not.toHaveBeenCalled();
  fireEvent.click(
    screen.getByRole("button", {
      name: "Descartar cambios y rechazar",
    }),
  );
  await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
  expect(JSON.parse(fetchMock.mock.calls[0][1]?.body as string)).toEqual({
    revision: 1,
    status: "rejected",
  });
});

it("reabre con una petición explícita sin campos de contenido", async () => {
  const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(
    new Response(JSON.stringify({ ...proposal, revision: 3 }), {
      status: 200,
    }),
  );
  const saved = vi.fn();
  render(
    <ProposalForm
      proposal={{
        ...proposal,
        revision: 2,
        status: "approved",
        allowed_actions: ["reopen"],
      }}
      onSaved={saved}
      onBatch={vi.fn()}
      onReload={vi.fn()}
    />,
  );
  fireEvent.click(screen.getByRole("button", { name: "Reabrir revisión" }));
  await waitFor(() => expect(saved).toHaveBeenCalled());
  expect(JSON.parse(fetchMock.mock.calls[0][1]?.body as string)).toEqual({
    revision: 2,
    status: "pending_review",
  });
});
