import { useRef, useState } from "react";
import { api, ApiError, errorMessage } from "../api";
import type { Batch, BatchItem } from "../types";
import { useResource } from "../useResource";
import { Empty, Status } from "./Status";

export function Batches({
  selectedId,
  onSelect,
  onReview,
}: {
  selectedId: string | null;
  onSelect: (id: string) => void;
  onReview: (id: string) => void;
}) {
  const {
    data: batches,
    error,
    reload,
  } = useResource<Batch[]>("/batches", 2000);
  const { data: items, error: itemError } = useResource<BatchItem[]>(
    selectedId ? `/batches/${selectedId}/items?limit=1000` : null,
    2000,
  );
  const [busy, setBusy] = useState(false);
  const [feedback, setFeedback] = useState("");
  const key = useRef(crypto.randomUUID());
  const selected = batches?.find((batch) => batch.id === selectedId);

  async function upload(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = event.currentTarget;
    setBusy(true);
    setFeedback("");
    try {
      const batch = await api<Batch>("/batches", {
        method: "POST",
        body: new FormData(form),
        headers: { "Idempotency-Key": key.current },
      });
      onSelect(batch.id);
      key.current = crypto.randomUUID();
      form.reset();
      reload();
    } catch (error) {
      setFeedback(errorMessage(error));
      if (error instanceof ApiError && error.resourceId)
        onSelect(error.resourceId);
      reload();
    } finally {
      setBusy(false);
    }
  }
  async function retry() {
    if (!selectedId) return;
    setBusy(true);
    setFeedback("");
    try {
      await api(`/batches/${selectedId}/retry`, { method: "POST" });
      reload();
    } catch (error) {
      setFeedback(errorMessage(error));
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <section className="batch-upload">
        <div>
          <h2>Un archivo, un lote de propuestas</h2>
          <p className="muted">
            Importa hasta 1.000 productos. Las fichas originales se conservan.
          </p>
        </div>
        <form onSubmit={(event) => void upload(event)}>
          <label className="sr-only" htmlFor="products-file">
            Archivo de productos
          </label>
          <input
            id="products-file"
            name="file"
            type="file"
            accept=".csv,.json"
            required
            onChange={() => {
              key.current = crypto.randomUUID();
            }}
          />
          <button className="primary" disabled={busy}>
            {busy ? "Enviando…" : "Generar propuestas ↗"}
          </button>
        </form>
      </section>
      {error || feedback ? (
        <p className="notice error" role="alert">
          {error || feedback}
        </p>
      ) : null}
      <div className="workbench">
        <aside className="item-list">
          <h2>Lotes recientes</h2>
          {!batches ? (
            <p role="status">Cargando lotes…</p>
          ) : batches.length === 0 ? (
            <Empty title="Todavía no hay lotes">
              Importa samples/products/productos.csv después de indexar las
              guías.
            </Empty>
          ) : (
            batches.map((batch) => (
              <button
                className={`list-item ${batch.id === selectedId ? "selected" : ""}`}
                key={batch.id}
                onClick={() => onSelect(batch.id)}
              >
                <strong>{batch.filename}</strong>
                <Status value={batch.status} />
                <span className="muted">
                  {batch.finished} de {batch.total} procesados
                </span>
              </button>
            ))
          )}
        </aside>
        <section className="batch-detail">
          {selected ? (
            <>
              <div className="detail-heading">
                <div>
                  <p className="muted">
                    {selected.configuration.llm_provider === "mock"
                      ? "Generación simulada"
                      : "Generación con Gemini"}
                  </p>
                  <h2>{selected.filename}</h2>
                </div>
                <Status value={selected.status} />
              </div>
              <progress
                max={selected.total}
                value={selected.finished}
                aria-label="Productos procesados"
              />
              <p>
                {selected.finished} de {selected.total} productos ·{" "}
                {selected.counts.succeeded ?? 0} propuestas ·{" "}
                {selected.counts.blocked ?? 0} sin evidencia ·{" "}
                {selected.counts.failed ?? 0} fallidos
              </p>
              <div className="review-actions">
                <button
                  className="primary"
                  onClick={() => onReview(selected.id)}
                >
                  Revisar propuestas
                </button>
                <button disabled={busy} onClick={() => void retry()}>
                  Reenviar pendientes y fallidos
                </button>
              </div>
              {selected.dispatch_error ? (
                <p className="notice error">
                  {selected.dispatch_error.message}
                </p>
              ) : null}
              {itemError ? (
                <p className="notice error" role="alert">
                  {itemError}
                </p>
              ) : null}
              <div className="table-wrap">
                <table>
                  <thead>
                    <tr>
                      <th>Producto</th>
                      <th>Estado</th>
                      <th>Detalle</th>
                    </tr>
                  </thead>
                  <tbody>
                    {items?.map((item) => (
                      <tr key={item.id}>
                        <td>
                          {item.original.title}
                          <small>{item.product_id}</small>
                        </td>
                        <td>
                          <Status value={item.status} />
                        </td>
                        <td>{item.error?.message ?? "—"}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </>
          ) : (
            <Empty title="Sigue el progreso de cada lote">
              Selecciona un lote para ver sus productos, propuestas e
              incidencias.
            </Empty>
          )}
        </section>
      </div>
    </>
  );
}
