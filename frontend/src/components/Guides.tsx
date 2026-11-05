import { useState } from "react";
import { api, errorMessage } from "../api";
import type { Guide } from "../types";
import { useResource } from "../useResource";
import { Empty, Status } from "./Status";

export function Guides() {
  const {
    data: guides,
    error,
    reload,
  } = useResource<Guide[]>("/documents", 2000);
  const [documentId, setDocumentId] = useState("");
  const [busy, setBusy] = useState(false);
  const [feedback, setFeedback] = useState("");
  const [uploadError, setUploadError] = useState("");

  async function upload(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = event.currentTarget;
    const body = new FormData(form);
    setBusy(true);
    setUploadError("");
    setFeedback("");
    try {
      await api(
        documentId ? `/documents/${documentId}/versions` : "/documents",
        { method: "POST", body },
      );
      setFeedback("Guía recibida. La indexación continuará en segundo plano.");
      form.reset();
      reload();
    } catch (error) {
      setUploadError(errorMessage(error));
      reload();
    } finally {
      setBusy(false);
    }
  }
  const uniqueGuides = Array.from(
    new Map(guides?.map((guide) => [guide.id, guide])).values(),
  );
  return (
    <div className="setup-layout">
      <section className="upload-panel">
        <h2>Incorporar una guía</h2>
        <p className="muted">
          Las propuestas se fundamentan en las versiones activas de tus
          documentos.
        </p>
        <form onSubmit={(event) => void upload(event)}>
          <label htmlFor="guide-version">Destino</label>
          <select
            id="guide-version"
            value={documentId}
            onChange={(event) => setDocumentId(event.target.value)}
          >
            <option value="">Nueva guía</option>
            {uniqueGuides.map((guide) => (
              <option key={guide.id} value={guide.id}>
                Nueva versión: {guide.title}
              </option>
            ))}
          </select>
          {!documentId ? (
            <>
              <label htmlFor="guide-title">Nombre de la guía</label>
              <input
                id="guide-title"
                name="title"
                required
                maxLength={200}
                placeholder="Ej. Guía editorial de textiles"
              />
              <label htmlFor="guide-brand">
                Marca <span className="muted">opcional</span>
              </label>
              <input
                id="guide-brand"
                name="brand"
                maxLength={100}
                placeholder="Vacío: todas las marcas"
              />
              <label htmlFor="guide-category">
                Categoría <span className="muted">opcional</span>
              </label>
              <input
                id="guide-category"
                name="category"
                maxLength={100}
                placeholder="Vacío: todas las categorías"
              />
            </>
          ) : null}
          <label htmlFor="guide-file">Documento</label>
          <input
            id="guide-file"
            name="file"
            type="file"
            accept=".pdf,.md"
            required
          />
          <p className="field-help">
            PDF con texto o Markdown UTF-8. Hasta 10 MiB y 100 páginas.
          </p>
          <button className="primary" disabled={busy}>
            {busy ? "Subiendo…" : "Subir e indexar guía"}
          </button>
        </form>
        {feedback ? (
          <p className="success-message" role="status">
            {feedback}
          </p>
        ) : null}
        {uploadError ? (
          <p className="notice error" role="alert">
            {uploadError}
          </p>
        ) : null}
      </section>
      <section className="guide-list">
        <div className="section-heading">
          <h2>Biblioteca de guías</h2>
          <button onClick={reload}>Actualizar</button>
        </div>
        {error ? (
          <p className="notice error" role="alert">
            {error}
          </p>
        ) : null}
        {!guides ? (
          <p role="status">Cargando guías…</p>
        ) : guides.length === 0 ? (
          <Empty title="Empieza por la evidencia">
            Sube una guía de ejemplo desde samples/guides. Después podrás
            importar los productos.
          </Empty>
        ) : (
          guides.map((guide) => (
            <article className="guide-row" key={guide.version_id}>
              <div className="section-heading">
                <h3>{guide.title}</h3>
                <Status value={guide.status} />
              </div>
              <p className="muted">
                {guide.brand ?? "Todas las marcas"} ·{" "}
                {guide.category ?? "Todas las categorías"} · versión{" "}
                {guide.version}
                {guide.is_active ? " · activa" : ""}
              </p>
              {guide.error ? (
                <p className="error-text">
                  {guide.error.message} ({guide.error.code})
                </p>
              ) : null}
            </article>
          ))
        )}
      </section>
    </div>
  );
}
