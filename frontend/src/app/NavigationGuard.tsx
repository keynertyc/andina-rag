/* eslint-disable react-refresh/only-export-components -- Guard hooks share a private context. */
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useState,
} from "react";
import Button from "@mui/material/Button";
import Dialog from "@mui/material/Dialog";
import DialogActions from "@mui/material/DialogActions";
import DialogContent from "@mui/material/DialogContent";
import DialogContentText from "@mui/material/DialogContentText";
import DialogTitle from "@mui/material/DialogTitle";

type State = { dirty: boolean; busy: boolean };
const clean = { dirty: false, busy: false };
const Context = createContext({
  run: (action: () => void) => action(),
  setGuard: (state: State) => {
    void state;
  },
});
export function NavigationGuard({ children }: { children: React.ReactNode }) {
  const [state, setGuard] = useState(clean);
  const [pending, setPending] = useState<{
    action: () => void;
    busy: boolean;
  } | null>(null);
  const updateGuard = useCallback((next: State) => {
    setGuard(next);
    if (!next.busy) setPending((current) => (current?.busy ? null : current));
  }, []);
  const run = useCallback(
    (action: () => void) => {
      if (state.dirty || state.busy) setPending({ action, busy: state.busy });
      else action();
    },
    [state],
  );
  useEffect(() => {
    if (!state.dirty && !state.busy) return;
    const beforeUnload = (event: BeforeUnloadEvent) => {
      event.preventDefault();
      event.returnValue = "";
    };
    window.addEventListener("beforeunload", beforeUnload);
    return () => window.removeEventListener("beforeunload", beforeUnload);
  }, [state]);
  return (
    <Context.Provider value={{ run, setGuard: updateGuard }}>
      {children}
      <Dialog
        open={!!pending}
        onClose={() => setPending(null)}
        aria-labelledby="leave-title"
      >
        <DialogTitle id="leave-title">
          {pending?.busy
            ? "Hay una solicitud en curso"
            : "Hay cambios sin guardar"}
        </DialogTitle>
        <DialogContent>
          <DialogContentText>
            {pending?.busy
              ? "Espera el resultado antes de cambiar de vista. Si falla la conexión, podrás recuperar el recurso creado."
              : "Si continúas, se perderán los cambios sin guardar de esta vista."}
          </DialogContentText>
        </DialogContent>
        <DialogActions>
          <Button autoFocus onClick={() => setPending(null)}>
            Volver
          </Button>
          {!pending?.busy && (
            <Button
              color="error"
              onClick={() => {
                const action = pending?.action;
                setPending(null);
                setGuard(clean);
                action?.();
              }}
            >
              Descartar y continuar
            </Button>
          )}
        </DialogActions>
      </Dialog>
    </Context.Provider>
  );
}
export function useNavigationGuard() {
  return useContext(Context).run;
}
export function useLeaveGuard(dirty: boolean, busy: boolean) {
  const { setGuard } = useContext(Context);
  useEffect(() => {
    setGuard({ dirty, busy });
    return () => setGuard(clean);
  }, [setGuard, dirty, busy]);
}
