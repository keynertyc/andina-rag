const labels: Record<string, string> = {
  pending: "Pendiente",
  indexing: "Indexando",
  ready: "Lista",
  error: "Error",
  running: "En curso",
  completed: "Completado",
  with_errors: "Con incidencias",
  pending_review: "Por revisar",
  approved: "Aprobada",
  rejected: "Rechazada",
  blocked: "Sin evidencia",
  failed: "Fallido",
  succeeded: "Generada",
};

export function Status({ value }: { value: string }) {
  return (
    <span className={`status status-${value}`}>
      <span aria-hidden="true">●</span> {labels[value] ?? value}
    </span>
  );
}

export function Empty({
  title,
  children,
}: {
  title: string;
  children: React.ReactNode;
}) {
  return (
    <div className="empty">
      <span className="empty-mark" aria-hidden="true">
        ↗
      </span>
      <h2>{title}</h2>
      <p>{children}</p>
    </div>
  );
}
