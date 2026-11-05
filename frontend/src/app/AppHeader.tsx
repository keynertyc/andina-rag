import { useRef, useState } from "react";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Chip from "@mui/material/Chip";
import IconButton from "@mui/material/IconButton";
import Menu from "@mui/material/Menu";
import MenuItem from "@mui/material/MenuItem";
import Paper from "@mui/material/Paper";
import Stack from "@mui/material/Stack";
import SvgIcon from "@mui/material/SvgIcon";
import Typography from "@mui/material/Typography";
import useMediaQuery from "@mui/material/useMediaQuery";
import { useTheme } from "@mui/material/styles";
import type { Location } from "./useLocation";

type View = Location["view"];
type NavigationProps = { view: View; onNavigate: (view: View) => void };
const sections = [
  ["review", "Mesa de revisión"],
  ["batches", "Productos y lotes"],
  ["guides", "Guías de contenido"],
] as const;

function MobileNavigation({ view, onNavigate }: NavigationProps) {
  const [anchor, setAnchor] = useState<HTMLElement | null>(null);
  const destination = useRef<View | null>(null);
  const open = Boolean(anchor);
  function close() {
    destination.current = null;
    setAnchor(null);
  }
  function finishNavigation() {
    const next = destination.current;
    destination.current = null;
    if (next && next !== view) onNavigate(next);
  }
  return (
    <>
      <IconButton
        id="mobile-navigation-button"
        aria-label="Abrir menú de navegación"
        aria-controls={open ? "mobile-navigation" : undefined}
        aria-haspopup="menu"
        aria-expanded={open}
        color="primary"
        onClick={(event) => setAnchor(event.currentTarget)}
        sx={{ width: 44, height: 44, flexShrink: 0 }}
      >
        <SvgIcon>
          <path d="M3 6h18v2H3zm0 5h18v2H3zm0 5h18v2H3z" />
        </SvgIcon>
      </IconButton>
      <Menu
        id="mobile-navigation"
        anchorEl={anchor}
        open={open}
        onClose={close}
        anchorOrigin={{ vertical: "bottom", horizontal: "left" }}
        transformOrigin={{ vertical: "top", horizontal: "left" }}
        slotProps={{
          list: { "aria-labelledby": "mobile-navigation-button" },
          paper: { sx: { minWidth: 240, maxWidth: "calc(100vw - 32px)" } },
          // Return focus to the trigger before a dirty-draft dialog can open.
          transition: { onExited: finishNavigation },
        }}
      >
        {sections.map(([id, label]) => (
          <MenuItem
            key={id}
            selected={view === id}
            aria-current={view === id ? "page" : undefined}
            onClick={() => {
              destination.current = id;
              setAnchor(null);
            }}
            sx={{ minHeight: 48, px: 2.5 }}
          >
            {label}
          </MenuItem>
        ))}
      </Menu>
    </>
  );
}

export function AppHeader({
  view,
  onNavigate,
  provider,
  offline,
}: NavigationProps & { provider?: string; offline: boolean }) {
  const theme = useTheme();
  const mobile = useMediaQuery(theme.breakpoints.down("sm"));
  const providerName = provider === "gemini" ? "Gemini" : "Simulado";
  const label = offline
    ? "API no disponible"
    : provider
      ? `${providerName} · entorno local`
      : "Conectando…";
  const compactLabel = offline
    ? "Sin conexión"
    : provider
      ? providerName
      : "Conectando…";
  return (
    <Paper
      component="header"
      square
      sx={{
        position: { xs: "sticky", sm: "static" },
        top: 0,
        zIndex: theme.zIndex.appBar,
        bgcolor: "background.paper",
        borderWidth: "0 0 1px",
        px: { xs: 1, sm: 2, md: 4 },
        py: { xs: 1, sm: 2 },
      }}
    >
      <Stack
        direction="row"
        sx={{ alignItems: "center", gap: { xs: 1, sm: 2 } }}
      >
        {mobile && <MobileNavigation view={view} onNavigate={onNavigate} />}
        <Typography component="span" variant="h2" sx={{ whiteSpace: "nowrap" }}>
          AndinaRAG
        </Typography>
        <Chip
          size="small"
          color={offline ? "error" : "default"}
          aria-label={label}
          title={label}
          sx={{ ml: "auto", maxWidth: "100%" }}
          label={
            <>
              <Box
                component="span"
                sx={{ display: { xs: "inline", sm: "none" } }}
              >
                {compactLabel}
              </Box>
              <Box
                component="span"
                sx={{ display: { xs: "none", sm: "inline" } }}
              >
                {label}
              </Box>
            </>
          }
        />
      </Stack>
    </Paper>
  );
}

export function DesktopNavigation({ view, onNavigate }: NavigationProps) {
  return (
    <Stack
      component="nav"
      aria-label="Navegación principal"
      direction="row"
      sx={{
        display: { xs: "none", sm: "flex" },
        flexWrap: "wrap",
        gap: 1,
        mb: 4,
      }}
    >
      {sections.map(([id, label]) => (
        <Button
          key={id}
          variant={view === id ? "contained" : "text"}
          aria-current={view === id ? "page" : undefined}
          onClick={() => onNavigate(id)}
        >
          {label}
        </Button>
      ))}
    </Stack>
  );
}
