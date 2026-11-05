import { useQueryClient } from "@tanstack/react-query";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";
import {
  invalidateResources,
  resourceKey,
  useResource,
} from "../../shared/api/queries";
import type { Proposal } from "../../shared/api/types";
import { ErrorAlert } from "../../shared/ui/Feedback";
import { ProposalForm } from "./ProposalForm";

export function ProposalDetail({
  id,
  onBatch,
  onSaved,
}: {
  id: string;
  onBatch: (id: string) => void;
  onSaved: (proposal: Proposal) => void;
}) {
  const client = useQueryClient();
  const path = `/proposals/${id}`;
  const query = useResource<Proposal>(path);
  if (!query.data)
    return query.error ? (
      <ErrorAlert error={query.error} retry={() => void query.refetch()} />
    ) : (
      <Typography role="status">Cargando propuesta…</Typography>
    );
  return (
    <Stack spacing={2}>
      <ErrorAlert error={query.error} retry={() => void query.refetch()} />
      <ProposalForm
        key={id}
        proposal={query.data}
        onReload={() => void query.refetch()}
        onBatch={onBatch}
        onSaved={(proposal) => {
          client.setQueryData(resourceKey(path), proposal);
          void invalidateResources(client, "/proposals?");
          onSaved(proposal);
        }}
      />
    </Stack>
  );
}
