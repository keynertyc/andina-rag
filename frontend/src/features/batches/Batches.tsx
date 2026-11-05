import { useEffect, useRef, useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Dialog from "@mui/material/Dialog";
import DialogActions from "@mui/material/DialogActions";
import DialogContent from "@mui/material/DialogContent";
import DialogTitle from "@mui/material/DialogTitle";
import LinearProgress from "@mui/material/LinearProgress";
import Paper from "@mui/material/Paper";
import Stack from "@mui/material/Stack";
import Table from "@mui/material/Table";
import TableBody from "@mui/material/TableBody";
import TableCell from "@mui/material/TableCell";
import TableContainer from "@mui/material/TableContainer";
import TableHead from "@mui/material/TableHead";
import TableRow from "@mui/material/TableRow";
import Typography from "@mui/material/Typography";
import { api, ApiError } from "../../shared/api/client";
import {
  hasActiveWork,
  invalidateResources,
  resourceKey,
  usePage,
  useResource,
} from "../../shared/api/queries";
import type { Batch, BatchItem } from "../../shared/api/types";
import {
  Empty,
  ErrorAlert,
  Pagination,
  Status,
} from "../../shared/ui/Feedback";
import { useLeaveGuard, useNavigationGuard } from "../../app/NavigationGuard";

const intentKey = "andina:pending-import";
async function importKey(file: File) {
  const digest = await crypto.subtle.digest(
    "SHA-256",
    await file.arrayBuffer(),
  );
  const fingerprint = Array.from(new Uint8Array(digest), (value) =>
    value.toString(16).padStart(2, "0"),
  ).join("");
  let previous;
  try {
    previous = JSON.parse(sessionStorage.getItem(intentKey) ?? "null");
  } catch {
    /* A damaged optional browser cache is safe to replace. */
  }
  const key =
    previous?.fingerprint === fingerprint && typeof previous?.key === "string"
      ? previous.key
      : crypto.randomUUID();
  try {
    sessionStorage.setItem(intentKey, JSON.stringify({ fingerprint, key }));
  } catch {
    /* The in-memory intent still protects retries in this view. */
  }
  return key;
}
export function Batches({
  selectedId,
  offset,
  onSelect,
  onPage,
  onReview,
  listOffset,
  onListPage,
}: {
  selectedId: string | null;
  offset: number;
  onSelect: (id: string) => void;
  onPage: (value: number) => void;
  onReview: (id: string) => void;
  listOffset: number;
  onListPage: (offset: number) => void;
}) {
  const client = useQueryClient();
  const guard = useNavigationGuard();
  const [file, setFile] = useState<File | null>(null);
  const input = useRef<HTMLInputElement>(null);
  const key = useRef<{ file: File; key: string } | null>(null);
  const [recover, setRecover] = useState(false);
  const batches = usePage<Batch>(
    `/batches?limit=50&offset=${listOffset}`,
    hasActiveWork,
  );
  const selected = useResource<Batch>(
    selectedId ? `/batches/${selectedId}` : null,
    (value) => !value.terminal,
  );
  const items = usePage<BatchItem>(
    selectedId
      ? `/batches/${selectedId}/items?limit=50&offset=${offset}`
      : null,
    () => !!selected.data && !selected.data.terminal,
  );
  const upload = useMutation({
    mutationFn: async () => {
      if (!file)
        throw new ApiError("Selecciona un CSV o JSON.", "FILE_REQUIRED");
      if (file.size > 5 * 1024 * 1024)
        throw new ApiError("El archivo supera 5 MiB.", "FILE_TOO_LARGE");
      if (!/\.(csv|json)$/i.test(file.name))
        throw new ApiError("Usa un archivo CSV o JSON.", "INVALID_FILE_TYPE");
      if (key.current?.file !== file)
        key.current = { file, key: await importKey(file) };
      const body = new FormData();
      body.append("file", file);
      return api<Batch>("/batches", {
        method: "POST",
        body,
        headers: { "Idempotency-Key": key.current.key },
      });
    },
    onSuccess: (result) => {
      client.setQueryData(resourceKey(`/batches/${result.id}`), result);
      onSelect(result.id);
      setFile(null);
      key.current = null;
      try {
        sessionStorage.removeItem(intentKey);
      } catch {
        /* Optional browser cache. */
      }
      if (input.current) input.current.value = "";
      void invalidateResources(client, "/batches");
    },
    onError: (error) => {
      if (error instanceof ApiError && error.resourceId) {
        onSelect(error.resourceId);
      }
      void invalidateResources(client, "/batches");
    },
  });
  const retry = useMutation({
    mutationFn: (mode: "failed" | "unfinished") =>
      api<Batch>(`/batches/${selectedId}/retry?mode=${mode}`, {
        method: "POST",
      }),
    onSuccess: (result) => {
      client.setQueryData(resourceKey(`/batches/${result.id}`), result);
      void invalidateResources(client, "/batches");
    },
  });
  const resetRetry = retry.reset;
  useEffect(() => resetRetry(), [selectedId, resetRetry]);
  const busy = upload.isPending || retry.isPending;
  useLeaveGuard(false, busy);
  const batch = selected.data;
  useEffect(() => {
    if (batch?.terminal && selectedId)
      void invalidateResources(client, `/batches/${selectedId}/items`);
  }, [batch?.terminal, selectedId, client]);
  return (
    <Stack spacing={3}>
      <Paper component="section" sx={{ p: 3 }}>
        <Stack spacing={2}>
          <Typography variant="h2">Crear un lote</Typography>
          <Typography color="text.secondary">
            Importa hasta 1.000 productos. CSV o JSON, hasta 5 MiB. Las fichas
            originales se conservan.
          </Typography>
          <Stack
            component="form"
            direction={{ xs: "column", sm: "row" }}
            onSubmit={(event) => {
              event.preventDefault();
              if (!busy) upload.mutate();
            }}
            sx={{ gap: 2, alignItems: { sm: "center" } }}
          >
            <Box sx={{ flex: 1 }}>
              <label htmlFor="products-file">Archivo de productos</label>
              <Box
                component="input"
                id="products-file"
                ref={input}
                type="file"
                accept=".csv,.json"
                required
                disabled={busy}
                sx={{ display: "block", mt: 1, maxWidth: "100%" }}
                onChange={(event) => {
                  setFile(event.target.files?.[0] ?? null);
                  upload.reset();
                }}
              />
            </Box>
            <Button type="submit" variant="contained" disabled={busy || !file}>
              {upload.isPending ? "Enviando…" : "Crear lote"}
            </Button>
          </Stack>
          <ErrorAlert error={upload.error} />
          {upload.isSuccess && (
            <Alert severity="success" role="status">
              Lote recibido. El procesamiento continúa en segundo plano.
            </Alert>
          )}
        </Stack>
      </Paper>
      <Box
        sx={{
          display: "grid",
          gridTemplateColumns: {
            xs: "1fr",
            md: "minmax(240px, 0.8fr) minmax(0, 2.2fr)",
          },
          gap: 2,
          alignItems: "start",
        }}
      >
        <Paper component="aside" sx={{ p: 2 }}>
          <Typography variant="h2" gutterBottom>
            Lotes
          </Typography>
          <ErrorAlert
            error={batches.error}
            retry={() => void batches.refetch()}
          />
          {batches.isPending ? (
            <Typography role="status">Cargando lotes…</Typography>
          ) : !batches.data?.items.length ? (
            <Empty
              title={
                batches.error ? "Lista no disponible" : "Todavía no hay lotes"
              }
            />
          ) : (
            <Stack spacing={1}>
              {batches.data.items.map((row) => (
                <Button
                  key={row.id}
                  variant={row.id === selectedId ? "outlined" : "text"}
                  onClick={() => guard(() => onSelect(row.id))}
                  sx={{ justifyContent: "flex-start", textAlign: "left" }}
                >
                  <Stack
                    sx={{
                      alignItems: "flex-start",
                      gap: 0.5,
                      minWidth: 0,
                    }}
                  >
                    <Typography sx={{ overflowWrap: "anywhere" }}>
                      {row.filename}
                    </Typography>
                    <Typography variant="caption">
                      {row.id.slice(0, 8)} · {row.finished}/{row.total}{" "}
                      productos
                    </Typography>
                    <Status value={row.status} />
                  </Stack>
                </Button>
              ))}
            </Stack>
          )}
          <Pagination
            offset={listOffset}
            hasMore={batches.data?.hasMore ?? false}
            busy={batches.isFetching || busy}
            onChange={onListPage}
          />
        </Paper>
        <Paper component="section" sx={{ p: { xs: 2, sm: 3 }, minWidth: 0 }}>
          <Stack spacing={2}>
            <ErrorAlert
              error={selected.error}
              retry={() => void selected.refetch()}
            />
            {!selectedId ? (
              <Empty title="Selecciona un lote">
                Aquí verás el progreso y el resultado de cada producto.
              </Empty>
            ) : !batch ? (
              <Typography role="status">Cargando lote…</Typography>
            ) : (
              <>
                <Stack
                  direction="row"
                  sx={{ justifyContent: "space-between", gap: 2 }}
                >
                  <Box>
                    <Typography variant="h2">{batch.filename}</Typography>
                    <Typography variant="caption">
                      Lote {batch.id} · proveedor{" "}
                      {batch.configuration.llm_provider}
                    </Typography>
                  </Box>
                  <Status value={batch.status} />
                </Stack>
                <LinearProgress
                  variant="determinate"
                  value={batch.total ? (100 * batch.finished) / batch.total : 0}
                  aria-label="Productos procesados"
                />
                <Typography>
                  {batch.finished} de {batch.total} ·{" "}
                  {batch.counts.succeeded ?? 0} propuestas ·{" "}
                  {batch.counts.blocked ?? 0} sin evidencia ·{" "}
                  {batch.counts.failed ?? 0} fallidos
                </Typography>
                {batch.terminal && (
                  <Alert severity={batch.counts.failed ? "warning" : "info"}>
                    Procesamiento finalizado.
                    {batch.counts.blocked
                      ? " Los productos sin evidencia necesitan guías adecuadas y un lote nuevo."
                      : ""}
                  </Alert>
                )}
                {batch.dispatch_error && (
                  <Alert severity="error">
                    {batch.dispatch_error.message} El lote está guardado;
                    recupera los pendientes.
                  </Alert>
                )}
                <Stack direction="row" sx={{ flexWrap: "wrap", gap: 1 }}>
                  <Button
                    variant="contained"
                    disabled={busy || !batch.counts.succeeded}
                    onClick={() => onReview(batch.id)}
                  >
                    Revisar propuestas
                  </Button>
                  <Button
                    variant="outlined"
                    disabled={busy || !batch.counts.failed}
                    onClick={() => retry.mutate("failed")}
                  >
                    {retry.isPending && retry.variables === "failed"
                      ? "Reintentando…"
                      : "Reintentar fallidos"}
                  </Button>
                  <Button
                    disabled={busy || batch.terminal}
                    onClick={() => setRecover(true)}
                  >
                    Recuperar pendientes
                  </Button>
                </Stack>
                <ErrorAlert error={retry.error} />
                <ErrorAlert
                  error={items.error}
                  retry={() => void items.refetch()}
                />
                <TableContainer>
                  <Table size="small" aria-label="Resultado de productos">
                    <TableHead>
                      <TableRow>
                        <TableCell>Producto</TableCell>
                        <TableCell>Estado</TableCell>
                        <TableCell>Detalle</TableCell>
                      </TableRow>
                    </TableHead>
                    <TableBody>
                      {items.data?.items.map((item) => (
                        <TableRow key={item.id}>
                          <TableCell
                            sx={{
                              minWidth: 150,
                              maxWidth: 280,
                              overflowWrap: "anywhere",
                            }}
                          >
                            <Typography variant="body2">
                              {item.original.title}
                            </Typography>
                            <Typography
                              variant="caption"
                              color="text.secondary"
                            >
                              {item.product_id}
                            </Typography>
                          </TableCell>
                          <TableCell>
                            <Status value={item.status} />
                          </TableCell>
                          <TableCell sx={{ minWidth: 180 }}>
                            {item.error ? (
                              <>
                                <Typography variant="body2">
                                  {item.error.message}
                                </Typography>
                                <Typography
                                  variant="caption"
                                  color="text.secondary"
                                >
                                  {item.error.code}
                                </Typography>
                              </>
                            ) : (
                              "—"
                            )}
                          </TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                </TableContainer>
                {items.isPending && (
                  <Typography role="status">Cargando productos…</Typography>
                )}
                <Pagination
                  offset={offset}
                  hasMore={items.data?.hasMore ?? false}
                  busy={items.isFetching || busy}
                  onChange={onPage}
                />
              </>
            )}
          </Stack>
        </Paper>
      </Box>
      <Dialog
        open={recover}
        onClose={() => setRecover(false)}
        aria-labelledby="recover-title"
      >
        <DialogTitle id="recover-title">
          Recuperar trabajo pendiente
        </DialogTitle>
        <DialogContent>
          Úsalo tras un error de Redis o una interrupción del worker. Los
          productos que estén siendo procesados se omiten y los resultados
          terminados se conservan.
        </DialogContent>
        <DialogActions>
          <Button autoFocus onClick={() => setRecover(false)}>
            Cancelar
          </Button>
          <Button
            onClick={() => {
              setRecover(false);
              retry.mutate("unfinished");
            }}
          >
            Recuperar pendientes
          </Button>
        </DialogActions>
      </Dialog>
    </Stack>
  );
}
