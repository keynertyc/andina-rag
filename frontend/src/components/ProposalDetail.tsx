import { useEffect, useRef, useState } from "react";
import { api, errorMessage } from "../api";
import type { Batch, Proposal } from "../types";
import { Status } from "./Status";

export function ProposalDetail({
  id,
  onChange,
  onBatch,
}: {
  id: string;
  onChange: () => void;
  onBatch: (id: string) => void;
}) {
  const [proposal, setProposal] = useState<Proposal | null>(null);
  const [error, setError] = useState("");
  const [reload, setReload] = useState(0);
  const [notice, setNotice] = useState("");
  useEffect(() => {
    const controller = new AbortController();
    api<Proposal>(`/proposals/${id}`, { signal: controller.signal })
      .then((result) => {
        setProposal(result);
        setError("");
      })
      .catch((error) => {
        if (!controller.signal.aborted) setError(errorMessage(error));
      });
    return () => controller.abort();
  }, [id, reload]);
  if (error)
    return (
      <div className="notice error" role="alert">
        {error}{" "}
        <button onClick={() => setReload((value) => value + 1)}>
          Reintentar
        </button>
      </div>
    );
  if (!proposal || proposal.id !== id)
    return <p role="status">Cargando propuesta…</p>;
  return (
    <>
      {notice ? (
        <p role="status" className="success-message">
          {notice}
        </p>
      ) : null}
      <ProposalForm
        key={`${proposal.id}-${proposal.revision}`}
        proposal={proposal}
        onSaved={(result) => {
          setProposal(result);
          setNotice(
            result.status === "approved"
              ? "Propuesta aprobada."
              : result.status === "rejected"
                ? "Propuesta rechazada."
                : "Cambios guardados.",
          );
          onChange();
        }}
        onBatch={onBatch}
        onReload={() => setReload((value) => value + 1)}
      />
    </>
  );
}

export function ProposalForm({
  proposal,
  onSaved,
  onBatch,
  onReload,
}: {
  proposal: Proposal;
  onSaved: (result: Proposal) => void;
  onBatch: (id: string) => void;
  onReload: () => void;
}) {
  const [title, setTitle] = useState(proposal.content.title);
  const [description, setDescription] = useState(proposal.content.description);
  const [tags, setTags] = useState(proposal.content.tags.join(", "));
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const regenerationKey = useRef(crypto.randomUUID());

  async function save(status?: string) {
    setBusy(true);
    setError("");
    setMessage("");
    try {
      const updated = await api<Proposal>(`/proposals/${proposal.id}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          revision: proposal.revision,
          title: title.trim(),
          description: description.trim(),
          tags: tags
            .split(",")
            .map((tag) => tag.trim())
            .filter(Boolean),
          ...(status ? { status } : {}),
        }),
      });
      setMessage(
        status === "approved"
          ? "Propuesta aprobada."
          : status === "rejected"
            ? "Propuesta rechazada."
            : "Cambios guardados.",
      );
      onSaved(updated);
    } catch (error) {
      setError(errorMessage(error));
    } finally {
      setBusy(false);
    }
  }

  async function regenerate() {
    setBusy(true);
    setError("");
    try {
      const batch = await api<Batch>(`/proposals/${proposal.id}/regenerate`, {
        method: "POST",
        headers: { "Idempotency-Key": regenerationKey.current },
      });
      onBatch(batch.id);
    } catch (error) {
      setError(errorMessage(error));
    } finally {
      setBusy(false);
    }
  }

  return (
    <article className="proposal-detail">
      <header className="detail-heading">
        <div>
          <p className="muted">Producto {proposal.product_id}</p>
          <h2>Revisar propuesta</h2>
        </div>
        <Status value={proposal.status} />
      </header>
      {proposal.is_stale ? (
        <div className="notice warning">
          <strong>Las guías cambiaron.</strong> Regenera esta propuesta antes de
          aprobarla. El historial se conserva.
          <button className="text-button" onClick={regenerate} disabled={busy}>
            Regenerar con guías vigentes ↗
          </button>
        </div>
      ) : null}
      <div className="comparison">
        <section className="original">
          <h3>Ficha original</h3>
          <p className="product-context">
            {proposal.original.brand} / {proposal.original.category}
          </p>
          <h4>{proposal.original.title}</h4>
          <p className="preserve-lines">
            {proposal.original.description || "Sin descripción."}
          </p>
          <p className="muted">
            {proposal.original.tags.join(" · ") || "Sin etiquetas"}
          </p>
        </section>
        <form
          className="editor"
          onSubmit={(event) => {
            event.preventDefault();
            void save();
          }}
        >
          <h3>Propuesta editable</h3>
          <label htmlFor="proposal-title">
            Título <span className="muted">{title.length}/160</span>
          </label>
          <input
            id="proposal-title"
            required
            maxLength={160}
            value={title}
            onChange={(event) => setTitle(event.target.value)}
          />
          <label htmlFor="proposal-description">Descripción</label>
          <textarea
            id="proposal-description"
            required
            maxLength={4000}
            rows={7}
            value={description}
            onChange={(event) => setDescription(event.target.value)}
          />
          <label htmlFor="proposal-tags">
            Etiquetas <span className="muted">separadas por comas</span>
          </label>
          <input
            id="proposal-tags"
            required
            value={tags}
            onChange={(event) => setTags(event.target.value)}
          />
          <div className="review-actions">
            <button type="submit" disabled={busy}>
              {busy ? "Guardando…" : "Guardar cambios"}
            </button>
            <button
              type="button"
              className="primary"
              disabled={busy || proposal.is_stale}
              onClick={() => void save("approved")}
            >
              Aprobar
            </button>
            <button
              type="button"
              className="danger"
              disabled={busy}
              onClick={() => void save("rejected")}
            >
              Rechazar
            </button>
          </div>
          {message ? (
            <p role="status" className="success-message">
              {message}
            </p>
          ) : null}
          {error ? (
            <div role="alert" className="notice error">
              {error}{" "}
              <button type="button" onClick={onReload}>
                Recargar propuesta
              </button>
            </div>
          ) : null}
        </form>
      </div>
      <section className="evidence">
        <div className="section-heading">
          <h3>Evidencia de las guías</h3>
          <span className="muted">
            {proposal.citations?.length ?? 0} fragmentos citados
          </span>
        </div>
        <p className="muted">
          Comprueba que las citas también fundamentan tus ediciones.
        </p>
        {proposal.citations?.map((citation, index) => (
          <details key={citation.id} open>
            <summary>
              <span className="citation-number">{index + 1}</span>{" "}
              {citation.document_title}{" "}
              <span className="muted">
                · v{citation.version}
                {citation.page ? ` · página ${citation.page}` : ""}
              </span>
            </summary>
            {citation.heading ? (
              <p className="citation-heading">{citation.heading}</p>
            ) : null}
            <blockquote>{citation.text}</blockquote>
          </details>
        ))}
      </section>
    </article>
  );
}
