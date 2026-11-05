import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Chip from "@mui/material/Chip";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";
import { ApiError, errorMessage } from "../api/client";

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
  const color = ["approved", "succeeded", "ready", "completed"].includes(value)
    ? "success"
    : ["failed", "error"].includes(value)
      ? "error"
      : ["rejected", "blocked", "with_errors"].includes(value)
        ? "warning"
        : "default";
  return (
    <Chip
      size="small"
      label={labels[value] ?? value}
      color={color}
      variant="outlined"
    />
  );
}
export function ErrorAlert({
  error,
  retry,
}: {
  error: unknown;
  retry?: () => void;
}) {
  if (!error) return null;
  const details = error instanceof ApiError ? error.details : {};
  const rows = Array.isArray(details.rows)
    ? (details.rows as {
        row?: number;
        code?: string;
        fields?: string[];
        message?: string;
      }[])
    : [];
  const fields = Array.isArray(details.fields)
    ? (details.fields as (string | number)[][])
    : [];
  return (
    <Alert
      severity="error"
      action={
        retry ? (
          <Button color="inherit" onClick={retry}>
            Reintentar
          </Button>
        ) : undefined
      }
    >
      {errorMessage(error)}
      {rows.length > 0 && (
        <Box component="ul" sx={{ pl: 2, my: 1 }}>
          {rows.map((row, i) => (
            <li key={i}>
              Fila {row.row ?? i + 1}:{" "}
              {row.message ?? row.code ?? "Datos inválidos"}
              {row.fields?.length ? ` · ${row.fields.join(", ")}` : ""}
            </li>
          ))}
        </Box>
      )}
      {fields.length > 0 && (
        <Typography variant="body2">
          Campos: {fields.map((field) => field.join(".")).join(", ")}
        </Typography>
      )}
      {error instanceof ApiError && (
        <Typography variant="caption" component="p">
          {error.code}
          {error.traceId ? ` · Traza ${error.traceId}` : ""}
        </Typography>
      )}
    </Alert>
  );
}
export function Empty({
  title,
  children,
}: {
  title: string;
  children?: React.ReactNode;
}) {
  return (
    <Box sx={{ p: 3, textAlign: "center", color: "text.secondary" }}>
      <Typography component="h2" variant="h6" color="text.primary">
        {title}
      </Typography>
      <Typography sx={{ mt: 1 }}>{children}</Typography>
    </Box>
  );
}
export function Pagination({
  offset,
  hasMore,
  busy,
  onChange,
}: {
  offset: number;
  hasMore: boolean;
  busy?: boolean;
  onChange: (offset: number) => void;
}) {
  return (
    <Stack
      direction="row"
      sx={{
        alignItems: "center",
        justifyContent: "space-between",
        gap: 1,
        py: 2,
        flexShrink: 0,
      }}
    >
      <Button
        disabled={offset === 0 || busy}
        onClick={() => onChange(Math.max(0, offset - 50))}
      >
        Anterior
      </Button>
      <Typography variant="body2">Página {offset / 50 + 1}</Typography>
      <Button disabled={!hasMore || busy} onClick={() => onChange(offset + 50)}>
        Siguiente
      </Button>
    </Stack>
  );
}
