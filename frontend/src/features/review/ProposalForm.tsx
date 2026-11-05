import { useEffect, useReducer, useRef, useState } from "react";
import { useMutation } from "@tanstack/react-query";
import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Dialog from "@mui/material/Dialog";
import DialogActions from "@mui/material/DialogActions";
import DialogContent from "@mui/material/DialogContent";
import DialogTitle from "@mui/material/DialogTitle";
import Divider from "@mui/material/Divider";
import Paper from "@mui/material/Paper";
import Stack from "@mui/material/Stack";
import TextField from "@mui/material/TextField";
import Typography from "@mui/material/Typography";
import { api, ApiError } from "../../shared/api/client";

import type { Batch, Proposal, ReviewAction } from "../../shared/api/types";
import { Empty, ErrorAlert, Status } from "../../shared/ui/Feedback";
import { useLeaveGuard, useNavigationGuard } from "../../app/NavigationGuard";

type Draft = { title: string; description: string; tags: string };
function draftOf(proposal: Proposal): Draft {
  return { ...proposal.content, tags: proposal.content.tags.join(", ") };
}
function normalized(draft: Draft) {
  return {
    title: draft.title.trim(),
    description: draft.description.trim(),
    tags: draft.tags
      .split(",")
      .map((tag) => tag.trim())
      .filter(Boolean),
  };
}
function isDirty(draft: Draft, proposal: Proposal) {
  return (
    JSON.stringify(normalized(draft)) !==
    JSON.stringify(normalized(draftOf(proposal)))
  );
}
type Editor = { base: Proposal; draft: Draft };
type Event =
  | { type: "reset" | "server"; proposal: Proposal }
  | { type: "edit"; field: keyof Draft; value: string };
function editor(state: Editor, event: Event): Editor {
  if (event.type === "edit")
    return { ...state, draft: { ...state.draft, [event.field]: event.value } };
  if (event.type === "server" && isDirty(state.draft, state.base)) return state;
  return { base: event.proposal, draft: draftOf(event.proposal) };
}

export function ProposalForm({
  proposal,
  onSaved,
  onBatch,
  onReload,
}: {
  proposal: Proposal;
  onSaved: (proposal: Proposal) => void;
  onBatch: (id: string) => void;
  onReload: () => void;
}) {
  const [state, dispatch] = useReducer(editor, proposal, (value) => ({
    base: value,
    draft: draftOf(value),
  }));
  const [notice, setNotice] = useState("");
  const [confirm, setConfirm] = useState<"reject" | "discard" | null>(null);
  const regenerationKey = useRef(crypto.randomUUID());
  const guard = useNavigationGuard();
  const { draft, base } = state;
  const dirty = isDirty(draft, base);
  const values = normalized(draft);
  const tagsValid =
    values.tags.length > 0 &&
    values.tags.length <= 10 &&
    values.tags.every((tag) => tag.length <= 100) &&
    new Set(values.tags).size === values.tags.length;
  const titleValid = values.title.length > 0 && values.title.length <= 160;
  const descriptionValid =
    values.description.length > 0 && values.description.length <= 4000;
  const valid = titleValid && descriptionValid && tagsValid;
  const editable = proposal.allowed_actions.includes("edit");
  const can = (action: ReviewAction) =>
    proposal.allowed_actions.includes(action);
  const changedElsewhere = base.revision !== proposal.revision;
  useEffect(() => {
    dispatch({ type: "server", proposal });
  }, [proposal]);
  const save = useMutation({
    mutationFn: (action: "save" | "approve" | "reject" | "reopen") =>
      api<Proposal>(`/proposals/${proposal.id}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          revision: base.revision,
          ...(["save", "approve"].includes(action) ? values : {}),
          ...(action === "save"
            ? {}
            : {
                status: {
                  approve: "approved",
                  reject: "rejected",
                  reopen: "pending_review",
                }[action as "approve" | "reject" | "reopen"],
              }),
        }),
      }),
    onSuccess: (result, action) => {
      dispatch({ type: "reset", proposal: result });
      setNotice(
        {
          save: "Cambios guardados.",
          approve: "Propuesta aprobada.",
          reject: "Propuesta rechazada.",
          reopen: "Revisión reabierta. Ya puedes editar.",
        }[action],
      );
      onSaved(result);
    },
    onError: (error) => {
      if (error instanceof ApiError && error.status === 409) onReload();
    },
  });
  const regenerate = useMutation({
    mutationFn: () =>
      api<Batch>(`/proposals/${proposal.id}/regenerate`, {
        method: "POST",
        headers: { "Idempotency-Key": regenerationKey.current },
      }),
    onSuccess: (result) => onBatch(result.id),
  });
  const busy = save.isPending || regenerate.isPending;
  useLeaveGuard(dirty, busy);
  function act(action: "save" | "approve" | "reject" | "reopen") {
    if (
      busy ||
      changedElsewhere ||
      ((action === "save" || action === "approve") && !valid)
    )
      return;
    setNotice("");
    save.mutate(action);
  }
  const working = (action: string, label: string) =>
    save.isPending && save.variables === action ? `${label}…` : label;
  return (
    <Stack component="article" spacing={2}>
      <Stack
        direction="row"
        sx={{ alignItems: "center", justifyContent: "space-between", gap: 2 }}
      >
        <Box>
          <Typography variant="overline">
            Producto {proposal.product_id}
          </Typography>
          <Typography variant="h2">Revisar propuesta</Typography>
        </Box>
        <Status value={proposal.status} />
      </Stack>
      {proposal.is_stale && (
        <Alert severity="warning">
          <strong>Las guías cambiaron.</strong> El contenido es de solo lectura.
          Regenera antes de aprobar; el historial se conserva.
        </Alert>
      )}
      {!editable && !proposal.is_stale && (
        <Alert severity="info">
          Esta propuesta es de solo lectura. Para cambiar el contenido o la
          decisión, pulsa Reabrir revisión.
        </Alert>
      )}
      {notice && (
        <Alert severity="success" role="status">
          {notice}
        </Alert>
      )}
      <ErrorAlert error={save.error ?? regenerate.error} />
      {changedElsewhere && (
        <Alert severity="warning">
          <Typography sx={{ fontWeight: 600 }}>
            Hay una revisión más reciente. Tu borrador se conserva.
          </Typography>
          <Typography>Versión actual: {proposal.content.title}</Typography>
          <Typography className="preserve-lines">
            {proposal.content.description}
          </Typography>
          <Typography>Etiquetas: {proposal.content.tags.join(", ")}</Typography>
          <Button color="inherit" onClick={() => setConfirm("discard")}>
            Descartar borrador y cargar versión actual
          </Button>
        </Alert>
      )}
      <Box
        sx={{
          display: "grid",
          gridTemplateColumns: {
            xs: "1fr",
            lg: "minmax(0, 0.8fr) minmax(0, 1.2fr)",
          },
          gap: 2,
        }}
      >
        <Paper
          component="section"
          sx={{ p: 2, bgcolor: "background.default", overflowWrap: "anywhere" }}
        >
          <Typography variant="h3" gutterBottom>
            Ficha original
          </Typography>
          <Typography variant="body2" color="text.secondary">
            {proposal.original.brand} / {proposal.original.category}
          </Typography>
          <Typography sx={{ fontWeight: 600, mt: 2 }}>
            {proposal.original.title}
          </Typography>
          <Typography className="preserve-lines" sx={{ my: 2 }}>
            {proposal.original.description || "Sin descripción."}
          </Typography>
          <Typography variant="body2">
            {proposal.original.tags.join(" · ") || "Sin etiquetas"}
          </Typography>
        </Paper>
        <Stack
          component="form"
          spacing={2}
          onSubmit={(event) => {
            event.preventDefault();
            if (editable && dirty) act("save");
          }}
          noValidate
        >
          <Typography variant="h3">
            {editable ? "Propuesta editable" : "Propuesta guardada"}
          </Typography>
          <TextField
            label="Título"
            value={draft.title}
            onChange={(event) =>
              dispatch({
                type: "edit",
                field: "title",
                value: event.target.value,
              })
            }
            required
            error={editable && !titleValid}
            helperText={
              !titleValid
                ? "El título debe tener entre 1 y 160 caracteres."
                : `${draft.title.length}/160`
            }
            slotProps={{
              htmlInput: {
                maxLength: 160,
                readOnly: !editable,
                "aria-readonly": !editable,
              },
            }}
            disabled={busy}
          />
          <TextField
            label="Descripción"
            value={draft.description}
            onChange={(event) =>
              dispatch({
                type: "edit",
                field: "description",
                value: event.target.value,
              })
            }
            multiline
            minRows={6}
            required
            error={editable && !descriptionValid}
            helperText={
              !descriptionValid
                ? "La descripción debe tener entre 1 y 4.000 caracteres."
                : undefined
            }
            slotProps={{
              htmlInput: {
                maxLength: 4000,
                readOnly: !editable,
                "aria-readonly": !editable,
              },
            }}
            disabled={busy}
          />
          <TextField
            label="Etiquetas"
            value={draft.tags}
            onChange={(event) =>
              dispatch({
                type: "edit",
                field: "tags",
                value: event.target.value,
              })
            }
            required
            error={editable && !tagsValid}
            helperText={
              !tagsValid
                ? "Usa de 1 a 10 etiquetas únicas, de hasta 100 caracteres."
                : "Separadas por comas"
            }
            slotProps={{
              htmlInput: { readOnly: !editable, "aria-readonly": !editable },
            }}
            disabled={busy}
          />
          <Stack direction="row" sx={{ gap: 1, flexWrap: "wrap" }}>
            {editable && (
              <>
                <Button
                  type="submit"
                  variant="outlined"
                  disabled={busy || !dirty || !valid || changedElsewhere}
                >
                  {working("save", "Guardar cambios")}
                </Button>
                <Button
                  disabled={busy || !dirty}
                  onClick={() => setConfirm("discard")}
                >
                  Descartar cambios
                </Button>
              </>
            )}
            {can("approve") && (
              <Button
                variant="contained"
                disabled={busy || !valid || changedElsewhere}
                onClick={() => act("approve")}
              >
                {working("approve", "Aprobar")}
              </Button>
            )}
            {can("reject") && (
              <Button
                color="error"
                variant="outlined"
                disabled={busy || changedElsewhere}
                onClick={() => (dirty ? setConfirm("reject") : act("reject"))}
              >
                {working("reject", "Rechazar")}
              </Button>
            )}
            {can("reopen") && (
              <Button
                variant="contained"
                disabled={busy}
                onClick={() => act("reopen")}
              >
                {working("reopen", "Reabrir revisión")}
              </Button>
            )}
            {can("regenerate") && (
              <Button
                variant="contained"
                disabled={busy}
                onClick={() =>
                  guard(() => {
                    dispatch({ type: "reset", proposal });
                    regenerate.mutate();
                  })
                }
              >
                {regenerate.isPending
                  ? "Regenerando…"
                  : "Regenerar con guías vigentes"}
              </Button>
            )}
          </Stack>
        </Stack>
      </Box>
      <Divider />
      <Box component="section">
        <Typography variant="h3" gutterBottom>
          Evidencia de las guías
        </Typography>
        {proposal.citations?.length ? (
          <Stack spacing={1}>
            {proposal.citations.map((citation) => (
              <Paper key={citation.id} sx={{ p: 2 }}>
                <Typography variant="body2" sx={{ fontWeight: 600 }}>
                  {citation.document_title} · versión {citation.version}
                  {citation.page ? ` · página ${citation.page}` : ""}
                  {citation.heading ? ` · ${citation.heading}` : ""}
                </Typography>
                <Typography
                  component="blockquote"
                  className="preserve-lines"
                  sx={{ mx: 0 }}
                >
                  {citation.text}
                </Typography>
                <Typography variant="caption" color="text.secondary">
                  Fragmento {citation.id}
                </Typography>
              </Paper>
            ))}
          </Stack>
        ) : (
          <Empty title="No hay citas disponibles" />
        )}
      </Box>
      <Dialog
        open={!!confirm}
        onClose={() => setConfirm(null)}
        aria-labelledby="draft-title"
      >
        <DialogTitle id="draft-title">
          {confirm === "reject"
            ? "¿Descartar cambios y rechazar?"
            : "¿Descartar el borrador?"}
        </DialogTitle>
        <DialogContent>
          Los cambios sin guardar se perderán. El contenido persistido y sus
          citas se conservarán.
        </DialogContent>
        <DialogActions>
          <Button autoFocus onClick={() => setConfirm(null)}>
            Seguir editando
          </Button>
          <Button
            color="error"
            onClick={() => {
              const reject = confirm === "reject";
              dispatch({ type: "reset", proposal });
              setConfirm(null);
              if (reject) act("reject");
            }}
          >
            {" "}
            {confirm === "reject"
              ? "Descartar cambios y rechazar"
              : "Descartar borrador"}
          </Button>
        </DialogActions>
      </Dialog>
    </Stack>
  );
}
