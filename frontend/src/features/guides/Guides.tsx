import { useRef, useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import MenuItem from "@mui/material/MenuItem";
import Paper from "@mui/material/Paper";
import Stack from "@mui/material/Stack";
import TextField from "@mui/material/TextField";
import Typography from "@mui/material/Typography";
import { api, ApiError } from "../../shared/api/client";
import {
  indexing,
  invalidateResources,
  usePage,
} from "../../shared/api/queries";
import type { Guide } from "../../shared/api/types";
import {
  Empty,
  ErrorAlert,
  Pagination,
  Status,
} from "../../shared/ui/Feedback";
import { useLeaveGuard } from "../../app/NavigationGuard";

import { useGuideCatalog } from "./queries";

import type { Location } from "../../app/useLocation";

export function Guides({
  location,
  navigate,
}: {
  location: Location;
  navigate: (patch: Partial<Location>) => void;
}) {
  const client = useQueryClient();
  const [destination, setDestination] = useState("");
  const [dirty, setDirty] = useState(false);
  const { offset, document: history, historyOffset } = location;
  const setOffset = (offset: number) => navigate({ offset });
  const setHistory = (document: string) =>
    navigate({ document, historyOffset: 0 });
  const setHistoryOffset = (historyOffset: number) =>
    navigate({ historyOffset });
  const form = useRef<HTMLFormElement>(null);
  const options = useGuideCatalog();
  const guides = usePage<Guide>(
    `/documents?latest_only=true&limit=50&offset=${offset}`,
    indexing,
  );
  const versions = usePage<Guide>(
    history
      ? `/documents?document_id=${history}&limit=50&offset=${historyOffset}`
      : null,
    indexing,
  );
  const upload = useMutation({
    mutationFn: async (body: FormData) => {
      const file = body.get("file") as File;
      if (!file.size || file.size > 10 * 1024 * 1024)
        throw new ApiError(
          "Usa un documento de hasta 10 MiB con contenido.",
          "INVALID_FILE_SIZE",
        );
      if (!/\.(pdf|md)$/i.test(file.name))
        throw new ApiError(
          "Usa PDF con texto o Markdown UTF-8.",
          "INVALID_FILE_TYPE",
        );
      if (!destination && !String(body.get("title") ?? "").trim())
        throw new ApiError("Indica un título para la guía.", "INVALID_TITLE");
      return api<{ document_id: string; version_id: string; status: string }>(
        destination ? `/documents/${destination}/versions` : "/documents",
        { method: "POST", body },
      );
    },
    onSuccess: (result) => {
      form.current?.reset();
      setDirty(false);
      setDestination("");
      setHistory(result.document_id);
      setHistoryOffset(0);
      void invalidateResources(client, "/documents");
      void client.invalidateQueries({ queryKey: ["guide-options"] });
    },
    onError: (error) => {
      if (error instanceof ApiError && error.resourceId) {
        setDestination(error.resourceId);
        setHistory(error.resourceId);
        setHistoryOffset(0);
      }
      void invalidateResources(client, "/documents");
      void client.invalidateQueries({ queryKey: ["guide-options"] });
    },
  });
  useLeaveGuard(dirty, upload.isPending);
  return (
    <Box
      sx={{
        display: "grid",
        gridTemplateColumns: {
          xs: "minmax(0, 1fr)",
          md: "minmax(280px, 0.9fr) minmax(0, 1.6fr)",
        },
        gap: 3,
        alignItems: "start",
      }}
    >
      <Paper component="section" sx={{ p: 3 }}>
        <Stack spacing={2}>
          <Typography variant="h2">Incorporar una guía</Typography>
          <Typography color="text.secondary">
            Las propuestas usan las versiones activas. Una versión fallida
            conserva la anterior.
          </Typography>
          <Stack
            component="form"
            ref={form}
            onChange={() => setDirty(true)}
            spacing={2}
            onSubmit={(event) => {
              event.preventDefault();
              if (!upload.isPending)
                upload.mutate(new FormData(event.currentTarget));
            }}
          >
            <TextField
              select
              label="Destino"
              slotProps={{
                select: { displayEmpty: true },
                inputLabel: { shrink: true },
              }}
              value={destination}
              disabled={upload.isPending || options.isPending}
              onChange={(event) => {
                setDestination(event.target.value);
                upload.reset();
              }}
            >
              <MenuItem value="">Nueva guía</MenuItem>
              {options.data?.map((guide) => (
                <MenuItem key={guide.id} value={guide.id}>
                  Nueva versión: {guide.title}
                </MenuItem>
              ))}
            </TextField>
            {!destination && (
              <>
                <TextField
                  label="Nombre de la guía"
                  name="title"
                  required
                  disabled={upload.isPending}
                  slotProps={{ htmlInput: { maxLength: 200 } }}
                />
                <TextField
                  label="Marca (opcional)"
                  name="brand"
                  disabled={upload.isPending}
                  helperText="Vacío: aplica a todas las marcas"
                  slotProps={{ htmlInput: { maxLength: 100 } }}
                />
                <TextField
                  label="Categoría (opcional)"
                  name="category"
                  disabled={upload.isPending}
                  helperText="Vacío: aplica a todas las categorías"
                  slotProps={{ htmlInput: { maxLength: 100 } }}
                />
              </>
            )}
            <Box>
              <label htmlFor="guide-file">Documento</label>
              <Box
                component="input"
                id="guide-file"
                name="file"
                type="file"
                accept=".pdf,.md"
                required
                disabled={upload.isPending}
                sx={{ display: "block", mt: 1, maxWidth: "100%" }}
              />
              <Typography variant="caption" color="text.secondary">
                PDF con texto o Markdown UTF-8. Hasta 10 MiB y 100 páginas.
              </Typography>
            </Box>
            <Button
              variant="contained"
              type="submit"
              disabled={upload.isPending}
            >
              {upload.isPending ? "Subiendo…" : "Subir e indexar guía"}
            </Button>
          </Stack>
          <ErrorAlert error={upload.error ?? options.error} />
          {upload.isSuccess && (
            <Alert severity="success" role="status">
              Guía recibida. Consulta la indexación en el historial.
            </Alert>
          )}
        </Stack>
      </Paper>
      <Stack spacing={2}>
        <Paper component="section" sx={{ p: 3 }}>
          <Stack spacing={2}>
            <Typography variant="h2">Biblioteca de guías</Typography>
            <ErrorAlert
              error={guides.error}
              retry={() => void guides.refetch()}
            />
            {guides.isPending ? (
              <Typography role="status">Cargando guías…</Typography>
            ) : !guides.data?.items.length ? (
              <Empty
                title={
                  guides.error
                    ? "Biblioteca no disponible"
                    : "Empieza por la evidencia"
                }
              >
                Sube una guía y después importa tus productos.
              </Empty>
            ) : (
              guides.data.items.map((guide) => (
                <Paper key={guide.id} sx={{ p: 2 }}>
                  <Stack spacing={1}>
                    <Stack
                      direction="row"
                      sx={{ justifyContent: "space-between", gap: 2 }}
                    >
                      <Typography variant="h3">{guide.title}</Typography>
                      <Status value={guide.status} />
                    </Stack>
                    <Typography variant="body2" color="text.secondary">
                      {guide.brand ?? "Todas las marcas"} ·{" "}
                      {guide.category ?? "Todas las categorías"}
                    </Typography>
                    <Typography variant="body2">
                      Última versión: {guide.version}
                      {guide.is_active
                        ? " · activa"
                        : " · consulta la versión activa en el historial"}
                    </Typography>
                    {guide.error && (
                      <Alert severity="error">
                        {guide.error.message} ({guide.error.code})
                      </Alert>
                    )}
                    <Button
                      sx={{ alignSelf: "flex-start" }}
                      onClick={() => {
                        setHistory(guide.id);
                        setHistoryOffset(0);
                      }}
                    >
                      Ver historial
                    </Button>
                  </Stack>
                </Paper>
              ))
            )}
            <Pagination
              offset={offset}
              hasMore={guides.data?.hasMore ?? false}
              busy={guides.isFetching}
              onChange={setOffset}
            />
          </Stack>
        </Paper>
        {history && (
          <Paper component="section" sx={{ p: 3 }}>
            <Typography variant="h2" gutterBottom>
              Historial de versiones
            </Typography>
            <ErrorAlert
              error={versions.error}
              retry={() => void versions.refetch()}
            />
            <Stack spacing={1}>
              {versions.data?.items.map((version) => (
                <Paper key={version.version_id} sx={{ p: 2 }}>
                  <Stack
                    direction="row"
                    sx={{ justifyContent: "space-between", gap: 1 }}
                  >
                    <Typography>
                      {version.title} · versión {version.version}
                      {version.is_active ? " · activa" : ""}
                    </Typography>
                    <Status value={version.status} />
                  </Stack>
                  {version.error && (
                    <Alert severity="error" sx={{ mt: 1 }}>
                      {version.error.message} ({version.error.code})
                    </Alert>
                  )}
                </Paper>
              ))}
            </Stack>
            <Pagination
              offset={historyOffset}
              hasMore={versions.data?.hasMore ?? false}
              busy={versions.isFetching}
              onChange={setHistoryOffset}
            />
          </Paper>
        )}
      </Stack>
    </Box>
  );
}
