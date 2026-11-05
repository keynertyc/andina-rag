import { useEffect } from "react";
import { useQueryClient } from "@tanstack/react-query";
import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Link from "@mui/material/Link";
import MenuItem from "@mui/material/MenuItem";
import Paper from "@mui/material/Paper";
import Stack from "@mui/material/Stack";
import TextField from "@mui/material/TextField";
import Typography from "@mui/material/Typography";
import type { Batch, Proposal } from "../../shared/api/types";
import {
  hasActiveWork,
  usePage,
  invalidateResources,
} from "../../shared/api/queries";
import {
  Empty,
  ErrorAlert,
  Pagination,
  Status,
} from "../../shared/ui/Feedback";
import { useNavigationGuard } from "../../app/NavigationGuard";
import type { Location } from "../../app/useLocation";
import { ProposalDetail } from "./ProposalDetail";

export function Review({
  location,
  navigate,
  onBatch,
}: {
  location: Location;
  navigate: (patch: Partial<Location>) => void;
  onBatch: (id: string) => void;
}) {
  const { batch, status, offset, proposal: selected } = location;
  const guard = useNavigationGuard();
  const client = useQueryClient();
  const params = new URLSearchParams({ limit: "50", offset: String(offset) });
  if (status) params.set("status", status);
  if (batch) params.set("batch_id", batch);
  const query = usePage<Proposal>(`/proposals?${params}`);
  const batches = usePage<Batch>("/batches?limit=50", hasActiveWork);
  useEffect(() => {
    void invalidateResources(client, "/proposals");
  }, [client, batches.dataUpdatedAt]);
  const rows = query.data?.items ?? [];
  const firstId = query.data?.items[0]?.id;
  const activeId = selected ?? firstId;
  // Pin automatic selection so a background list update cannot replace an open editor.
  useEffect(() => {
    if (!selected && firstId) navigate({ proposal: firstId });
  }, [selected, firstId, navigate]);
  return (
    <Stack spacing={2}>
      <Stack
        direction={{ xs: "column", sm: "row" }}
        sx={{
          alignItems: { sm: "center" },
          justifyContent: "space-between",
          gap: 2,
        }}
      >
        <Typography variant="body2" color="text.secondary">
          Compara el original, ajusta el contenido y comprueba la evidencia.
        </Typography>
        <TextField
          select
          label="Estado"
          slotProps={{
            select: { displayEmpty: true },
            inputLabel: { shrink: true },
          }}
          value={status}
          sx={{ maxWidth: 220 }}
          onChange={(event) =>
            guard(() =>
              navigate({
                status: event.target.value,
                proposal: null,
                offset: 0,
              }),
            )
          }
        >
          {[
            ["pending_review", "Por revisar"],
            ["approved", "Aprobadas"],
            ["rejected", "Rechazadas"],
            ["", "Todos"],
          ].map(([value, label]) => (
            <MenuItem key={value} value={value}>
              {label}
            </MenuItem>
          ))}
        </TextField>
      </Stack>
      {batch && (
        <Alert
          severity="info"
          action={
            <Button
              color="inherit"
              onClick={() =>
                guard(() =>
                  navigate({ batch: null, proposal: null, offset: 0 }),
                )
              }
            >
              Todos los lotes
            </Button>
          }
        >
          Mostrando el lote {batch.slice(0, 8)}.
        </Alert>
      )}
      <ErrorAlert error={query.error} retry={() => void query.refetch()} />
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
        <Paper
          component="aside"
          aria-label="Propuestas"
          sx={{
            p: 1,
            display: "flex",
            flexDirection: "column",
            maxHeight: { xs: 320, md: "calc(100vh - 32px)" },
            position: { md: "sticky" },
            top: 16,
          }}
        >
          <Typography variant="body2" color="text.secondary" sx={{ p: 1 }}>
            {query.data ? rows.length : "—"} propuestas en esta página
          </Typography>
          {activeId && (
            <Link href="#proposal-detail" sx={{ px: 1, pb: 1, fontSize: 14 }}>
              Ir a la propuesta seleccionada
            </Link>
          )}
          {query.isPending ? (
            <Typography role="status" sx={{ p: 2 }}>
              Cargando propuestas…
            </Typography>
          ) : rows.length === 0 ? (
            <Empty
              title={
                query.error
                  ? "Lista no disponible"
                  : "No hay propuestas en este estado"
              }
            >
              Cambia el filtro o genera un lote.
            </Empty>
          ) : (
            <Stack sx={{ overflowY: "auto", minHeight: 0 }}>
              {rows.map((row) => (
                <Button
                  key={row.id}
                  aria-current={activeId === row.id ? "true" : undefined}
                  onClick={() => guard(() => navigate({ proposal: row.id }))}
                  sx={{
                    textAlign: "left",
                    justifyContent: "flex-start",
                    borderLeft: 3,
                    borderColor:
                      activeId === row.id ? "primary.main" : "transparent",
                    bgcolor:
                      activeId === row.id ? "action.selected" : "transparent",
                    borderRadius: 0,
                    py: 1.5,
                  }}
                >
                  <Stack
                    spacing={0.7}
                    sx={{ alignItems: "flex-start", minWidth: 0 }}
                  >
                    <Typography variant="caption" color="text.secondary">
                      {row.product_id} · {row.original.category}
                    </Typography>
                    <Typography
                      sx={{ fontWeight: 600, overflowWrap: "anywhere" }}
                    >
                      {row.content.title}
                    </Typography>
                    <Status value={row.status} />
                    {row.is_stale && (
                      <Typography variant="caption" color="warning.main">
                        Guías desactualizadas
                      </Typography>
                    )}
                  </Stack>
                </Button>
              ))}
            </Stack>
          )}
          <Pagination
            offset={offset}
            hasMore={query.data?.hasMore ?? false}
            busy={query.isFetching}
            onChange={(value) =>
              guard(() => navigate({ offset: value, proposal: null }))
            }
          />
        </Paper>
        <Paper
          component="section"
          id="proposal-detail"
          tabIndex={-1}
          aria-label="Detalle de propuesta"
          sx={{ p: { xs: 2, sm: 3 }, minWidth: 0 }}
        >
          <Stack spacing={2}>
            {selected &&
              !query.isPending &&
              !rows.some((row) => row.id === selected) && (
                <Alert severity="info">
                  La propuesta seleccionada no está en esta página o ya no
                  pertenece al filtro actual. Puedes consultar su decisión aquí.
                </Alert>
              )}
            {activeId ? (
              <ProposalDetail
                key={activeId}
                id={activeId}
                onBatch={onBatch}
                onSaved={(result) => navigate({ proposal: result.id })}
              />
            ) : (
              <Empty title="Contenido con fundamento">
                Aquí verás el original, la propuesta y sus citas.
              </Empty>
            )}
          </Stack>
        </Paper>
      </Box>
    </Stack>
  );
}
