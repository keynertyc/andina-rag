import { lazy, Suspense, useEffect } from "react";
import { useQueryClient } from "@tanstack/react-query";
import Box from "@mui/material/Box";
import Container from "@mui/material/Container";
import Link from "@mui/material/Link";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";
import { invalidateResources, useResource } from "../shared/api/queries";
import { useGuideCatalog } from "../features/guides/queries";
import { useNavigationGuard } from "./NavigationGuard";
import { useLocation, type Location } from "./useLocation";
import { AppHeader, DesktopNavigation } from "./AppHeader";

const Batches = lazy(() =>
  import("../features/batches/Batches").then((module) => ({
    default: module.Batches,
  })),
);
const Guides = lazy(() =>
  import("../features/guides/Guides").then((module) => ({
    default: module.Guides,
  })),
);
const Review = lazy(() =>
  import("../features/review/Review").then((module) => ({
    default: module.Review,
  })),
);

export default function App() {
  const [location, navigate] = useLocation();
  const guard = useNavigationGuard();
  const client = useQueryClient();
  const health = useResource<{ llm_provider: string }>("/health/ready", 15000);
  const guides = useGuideCatalog();
  const activeVersions = guides.data
    ?.map((guide) => `${guide.version_id}:${guide.is_active}:${guide.status}`)
    .join("|");
  useEffect(() => {
    void invalidateResources(client, "/proposals");
  }, [activeVersions, client]);
  function switchView(view: Location["view"]) {
    if (view !== location.view)
      guard(() => {
        navigate({ view, offset: 0, proposal: null });
        window.scrollTo({ top: 0, left: 0, behavior: "instant" });
      });
  }
  function openBatch(id: string) {
    navigate({ batch: id, view: "batches", offset: 0, proposal: null });
  }
  return (
    <>
      <a className="skip-link" href="#main">
        Ir al contenido
      </a>
      <AppHeader
        view={location.view}
        onNavigate={switchView}
        provider={health.data?.llm_provider}
        offline={health.isError}
      />
      <Container
        maxWidth={false}
        sx={{
          maxWidth: 1680,
          pt: { xs: 2, sm: 3 },
          pb: 3,
          px: { xs: 2, md: 4 },
        }}
      >
        <DesktopNavigation view={location.view} onNavigate={switchView} />
        <Box component="main" id="main">
          <Stack
            direction="row"
            sx={{
              justifyContent: "space-between",
              alignItems: "center",
              gap: 2,
              mb: 3,
            }}
          >
            <Box>
              <Typography variant="overline" color="text.secondary">
                Mercadia Andina · Merchandising
              </Typography>
              <Typography variant="h1">
                {location.view === "review"
                  ? "Revisar, con evidencia."
                  : location.view === "batches"
                    ? "Del catálogo a la propuesta."
                    : "Las reglas, en un solo lugar."}
              </Typography>
            </Box>
            <Link
              href="http://localhost:8000/docs"
              target="_blank"
              rel="noreferrer"
              sx={{
                display: { xs: "none", sm: "block" },
                whiteSpace: "nowrap",
              }}
            >
              Explorar API ↗
            </Link>
          </Stack>
          <Suspense
            fallback={<Typography role="status">Cargando vista…</Typography>}
          >
            {location.view === "review" ? (
              <Review
                location={location}
                navigate={navigate}
                onBatch={openBatch}
              />
            ) : location.view === "batches" ? (
              <Batches
                selectedId={location.batch}
                offset={location.offset}
                listOffset={location.listOffset}
                onListPage={(listOffset) => navigate({ listOffset })}
                onSelect={(id) => navigate({ batch: id, offset: 0 })}
                onPage={(offset) => navigate({ offset })}
                onReview={(id) =>
                  navigate({
                    view: "review",
                    batch: id,
                    status: "pending_review",
                    proposal: null,
                    offset: 0,
                  })
                }
              />
            ) : (
              <Guides location={location} navigate={navigate} />
            )}
          </Suspense>
        </Box>
        <Stack
          component="footer"
          direction={{ xs: "column", sm: "row" }}
          sx={{
            justifyContent: "space-between",
            gap: 1,
            pt: 5,
            color: "text.secondary",
          }}
        >
          <Typography variant="caption">
            AndinaRAG · Revisión humana, evidencia trazable.
          </Typography>
          <Link
            href="http://localhost:16686"
            target="_blank"
            rel="noreferrer"
            variant="caption"
          >
            Abrir trazas en Jaeger ↗
          </Link>
        </Stack>
      </Container>
    </>
  );
}
