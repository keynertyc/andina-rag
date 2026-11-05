import { useCallback, useEffect, useState } from "react";
import { api, errorMessage } from "./api";

export function useResource<T>(path: string | null, interval = 0) {
  const [data, setData] = useState<{ path: string; value: T } | null>(null);
  const [error, setError] = useState<{ path: string; message: string } | null>(
    null,
  );
  const [version, setVersion] = useState(0);
  const reload = useCallback(() => setVersion((value) => value + 1), []);

  useEffect(() => {
    if (!path) return;
    const controller = new AbortController();
    let timer: ReturnType<typeof setTimeout>;
    const load = async () => {
      try {
        const result = await api<T>(path, { signal: controller.signal });
        if (!controller.signal.aborted) {
          setData({ path, value: result });
          setError(null);
        }
      } catch (error) {
        if (!controller.signal.aborted)
          setError({ path, message: errorMessage(error) });
      } finally {
        if (interval && !controller.signal.aborted)
          timer = setTimeout(load, interval);
      }
    };
    void load();
    return () => {
      controller.abort();
      clearTimeout(timer);
    };
  }, [path, interval, version]);

  return {
    data: data?.path === path ? data.value : null,
    error: error?.path === path ? error.message : "",
    reload,
  };
}
