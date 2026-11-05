import { useState } from "react";
import type { Proposal } from "../types";
import { useResource } from "../useResource";
import { ProposalDetail } from "./ProposalDetail";
import { Empty, Status } from "./Status";

export function Review({
  batchId,
  onBatch,
}: {
  batchId: string | null;
  onBatch: (id: string) => void;
}) {
  const [status, setStatus] = useState("pending_review");
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [allBatches, setAllBatches] = useState(!batchId);
  const [offset, setOffset] = useState(0);
  const params = new URLSearchParams();
  params.set("limit", "50");
  params.set("offset", String(offset));
  if (status) params.set("status", status);
  if (batchId && !allBatches) params.set("batch_id", batchId);
  const {
    data: proposals,
    error,
    reload,
  } = useResource<Proposal[]>(`/proposals?${params}`, 5000);
  const activeId = selectedId ?? proposals?.[0]?.id;
  return (
    <>
      <div className="review-toolbar">
        <div>
          <h2>La decisión final es tuya</h2>
          <p className="muted">
            Compara, ajusta y comprueba la evidencia antes de aprobar.
          </p>
        </div>
        <div className="filters">
          <label htmlFor="review-status">Estado</label>
          <select
            id="review-status"
            value={status}
            onChange={(event) => {
              setStatus(event.target.value);
              setSelectedId(null);
              setOffset(0);
            }}
          >
            <option value="pending_review">Por revisar</option>
            <option value="approved">Aprobadas</option>
            <option value="rejected">Rechazadas</option>
            <option value="">Todos</option>
          </select>
          {batchId ? (
            <label className="checkbox">
              <input
                type="checkbox"
                checked={allBatches}
                onChange={(event) => {
                  setAllBatches(event.target.checked);
                  setSelectedId(null);
                  setOffset(0);
                }}
              />
              Todos los lotes
            </label>
          ) : null}
        </div>
      </div>
      {error ? (
        <p className="notice error" role="alert">
          {error}
        </p>
      ) : null}
      <div className="workbench">
        <aside className="item-list" aria-label="Propuestas">
          <p className="list-count">
            {proposals?.length ?? 0} propuestas en esta vista
          </p>
          {!proposals ? (
            <p role="status">Cargando propuestas…</p>
          ) : proposals.length === 0 ? (
            <Empty title="No hay propuestas en este estado">
              Consulta otro filtro o genera un lote desde Productos y lotes.
            </Empty>
          ) : (
            proposals.map((proposal) => (
              <button
                key={proposal.id}
                className={`list-item ${activeId === proposal.id ? "selected" : ""}`}
                onClick={() => setSelectedId(proposal.id)}
              >
                <span className="muted">
                  {proposal.product_id} · {proposal.original.category}
                </span>
                <strong>{proposal.content.title}</strong>
                <Status value={proposal.status} />
                {proposal.is_stale ? (
                  <span className="stale-text">Guías desactualizadas</span>
                ) : null}
              </button>
            ))
          )}
          <div className="pagination">
            <button
              disabled={offset === 0}
              onClick={() => {
                setOffset((value) => Math.max(0, value - 50));
                setSelectedId(null);
              }}
            >
              Anterior
            </button>
            <span className="muted">Página {offset / 50 + 1}</span>
            <button
              disabled={!proposals || proposals.length < 50}
              onClick={() => {
                setOffset((value) => value + 50);
                setSelectedId(null);
              }}
            >
              Siguiente
            </button>
          </div>
        </aside>
        <section className="detail-pane">
          {activeId ? (
            <ProposalDetail
              key={activeId}
              id={activeId}
              onChange={() => {
                setSelectedId(activeId);
                reload();
              }}
              onBatch={onBatch}
            />
          ) : (
            <Empty title="Contenido con fundamento">
              Aquí verás el original, la propuesta editable y los fragmentos que
              la respaldan.
            </Empty>
          )}
        </section>
      </div>
    </>
  );
}
