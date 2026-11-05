import { Component, type ReactNode } from "react";
import { CacheProvider } from "@emotion/react";
import createCache from "@emotion/cache";
import { QueryClientProvider } from "@tanstack/react-query";
import { createTheme, ThemeProvider } from "@mui/material/styles";
import CssBaseline from "@mui/material/CssBaseline";
import Alert from "@mui/material/Alert";
import Button from "@mui/material/Button";
import { createQueryClient } from "../shared/api/queries";
import { NavigationGuard } from "./NavigationGuard";

const nonce = document.querySelector<HTMLMetaElement>(
  'meta[name="csp-nonce"]',
)?.content;
const cache = createCache({
  key: "andina",
  nonce: nonce && nonce !== "CSP_NONCE_PLACEHOLDER" ? nonce : undefined,
  prepend: true,
});
const client = createQueryClient();
const theme = createTheme({
  palette: {
    primary: { main: "#126b60" },
    secondary: { main: "#243c5a" },
    background: { default: "#f5f7f8", paper: "#fff" },
    text: { primary: "#182c3b", secondary: "#526371" },
  },
  typography: {
    fontFamily: "Inter, ui-sans-serif, system-ui, -apple-system, sans-serif",
    h1: { fontSize: "clamp(1.65rem, 3vw, 2.3rem)", fontWeight: 700 },
    h2: { fontSize: "1.25rem", fontWeight: 700 },
    h3: { fontSize: "1.05rem", fontWeight: 650 },
    button: { textTransform: "none", fontWeight: 600 },
  },
  shape: { borderRadius: 8 },
  components: {
    MuiButton: { defaultProps: { disableElevation: true } },
    MuiTextField: { defaultProps: { size: "small", fullWidth: true } },
    MuiPaper: { defaultProps: { elevation: 0, variant: "outlined" } },
  },
});
class ErrorBoundary extends Component<
  { children: ReactNode },
  { failed: boolean }
> {
  state = { failed: false };
  static getDerivedStateFromError() {
    return { failed: true };
  }
  render() {
    return this.state.failed ? (
      <Alert
        severity="error"
        sx={{ m: 3 }}
        action={
          <Button color="inherit" onClick={() => window.location.reload()}>
            Recargar
          </Button>
        }
      >
        La vista no pudo mostrarse. Recarga para recuperar los datos guardados.
      </Alert>
    ) : (
      this.props.children
    );
  }
}
export function Providers({ children }: { children: ReactNode }) {
  return (
    <CacheProvider value={cache}>
      <ThemeProvider theme={theme}>
        <CssBaseline />
        <ErrorBoundary>
          <QueryClientProvider client={client}>
            <NavigationGuard>{children}</NavigationGuard>
          </QueryClientProvider>
        </ErrorBoundary>
      </ThemeProvider>
    </CacheProvider>
  );
}
