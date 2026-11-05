/* THESIS: una mesa de revisión con evidencia junto al contenido.
   OWN-WORLD: superficies claras, azul profundo, acento petróleo, controles nativos.
   STORY: incorporar guías, generar un lote y decidir con citas visibles.
   FIRST VIEWPORT: cabecera y navegación; lista izquierda, comparación derecha.
   FORM: consola operativa fijada en el plan aprobado; sin selección visual pendiente. */
import { useState } from "react";
import { Batches } from "./components/Batches";
import { Guides } from "./components/Guides";
import { Review } from "./components/Review";
import { useResource } from "./useResource";

type Tab = "review" | "batches" | "guides";

export default function App() {
  const [tab, setTab] = useState<Tab>("review");
  const [batchId, setBatchId] = useState<string | null>(null);
  const health = useResource<{ llm_provider: string }>("/health/ready", 15000);
  function openBatch(id: string) {
    setBatchId(id);
    setTab("batches");
  }
  return (
    <>
      <a className="skip-link" href="#main">
        Ir al contenido
      </a>
      <header className="app-header">
        <a
          className="brand"
          href="#"
          onClick={() => setTab("review")}
          aria-label="AndinaRAG, inicio"
        >
          <svg aria-hidden="true" viewBox="0 0 40 40">
            <path d="m6 30 12-21 7 12 4-6 7 15H6Z" />
          </svg>
          <span>
            Andina<span className="brand-light">RAG</span>
          </span>
        </a>
        <span className="header-caption">Catálogo con fundamento</span>
        <span className={`environment ${health.error ? "offline" : ""}`}>
          {health.error
            ? "API no disponible"
            : health.data?.llm_provider === "gemini"
              ? "Gemini · entorno local"
              : health.data
                ? "Simulado · entorno local"
                : "Conectando…"}
        </span>
      </header>
      <nav className="app-nav" aria-label="Navegación principal">
        <div>
          {(
            [
              ["review", "Mesa de revisión"],
              ["batches", "Productos y lotes"],
              ["guides", "Guías de contenido"],
            ] as const
          ).map(([id, label]) => (
            <button
              key={id}
              aria-current={tab === id ? "page" : undefined}
              onClick={() => setTab(id)}
            >
              {label}
            </button>
          ))}
        </div>
        <span className="nav-note">Mercadia Andina / datos sintéticos</span>
      </nav>
      <main id="main">
        <div className="page-heading">
          <div>
            <p className="section-label">Merchandising</p>
            <h1>
              {tab === "review"
                ? "Revisar, con evidencia."
                : tab === "batches"
                  ? "Del catálogo a la propuesta."
                  : "Las reglas, en un solo lugar."}
            </h1>
          </div>
          <a
            className="docs-link"
            href="http://localhost:8000/docs"
            target="_blank"
            rel="noreferrer"
          >
            Explorar API ↗
          </a>
        </div>
        {tab === "review" ? (
          <Review
            key={batchId ?? "all"}
            batchId={batchId}
            onBatch={openBatch}
          />
        ) : tab === "batches" ? (
          <Batches
            selectedId={batchId}
            onSelect={setBatchId}
            onReview={(id) => {
              setBatchId(id);
              setTab("review");
            }}
          />
        ) : (
          <Guides />
        )}
      </main>
      <footer className="app-footer">
        <span>AndinaRAG · Revisión humana, evidencia trazable.</span>
        <a href="http://localhost:16686" target="_blank" rel="noreferrer">
          Abrir trazas en Jaeger ↗
        </a>
      </footer>
    </>
  );
}
