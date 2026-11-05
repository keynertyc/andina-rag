export class ApiError extends Error {
  constructor(
    message: string,
    public code: string,
    public status = 0,
    public details: Record<string, unknown> = {},
    public traceId?: string,
  ) {
    super(message);
  }
  get resourceId() {
    return (this.details.batch_id ?? this.details.document_id) as
      | string
      | undefined;
  }
}

export type Page<T> = { items: T[]; hasMore: boolean };

async function request(path: string, options?: RequestInit) {
  const timeout = AbortSignal.timeout(20000);
  const signal = options?.signal
    ? AbortSignal.any([options.signal, timeout])
    : timeout;
  try {
    const response = await fetch(`/api/v1${path}`, { ...options, signal });
    const traceId = response.headers.get("X-Trace-ID") ?? undefined;
    let body;
    try {
      body = await response.json();
    } catch (error) {
      if (signal.aborted) throw error;
      throw new ApiError(
        response.ok
          ? "La API devolvió una respuesta no válida."
          : `El servicio no pudo responder (HTTP ${response.status}).`,
        response.ok ? "INVALID_RESPONSE" : `HTTP_${response.status}`,
        response.status,
        {},
        traceId,
      );
    }
    if (!response.ok) {
      const error = body?.error;
      throw new ApiError(
        error?.message ?? "No se pudo completar la acción.",
        error?.code ?? `HTTP_${response.status}`,
        response.status,
        error ?? {},
        traceId,
      );
    }
    return { body, hasMore: response.headers.get("X-Has-More") === "true" };
  } catch (error) {
    if (error instanceof ApiError) throw error;
    if (options?.signal?.aborted) throw error;
    if (timeout.aborted)
      throw new ApiError(
        "La solicitud tardó demasiado. Comprueba el estado antes de reenviar.",
        "TIMEOUT",
      );
    throw new ApiError(
      "No hay conexión con la API. Comprueba que Docker esté iniciado.",
      "NETWORK",
    );
  }
}

export async function api<T>(path: string, options?: RequestInit): Promise<T> {
  return (await request(path, options)).body as T;
}
export async function apiPage<T>(
  path: string,
  signal?: AbortSignal,
): Promise<Page<T>> {
  const { body, hasMore } = await request(path, { signal });
  if (!Array.isArray(body))
    throw new ApiError(
      "La API no devolvió una lista válida.",
      "INVALID_RESPONSE",
    );
  return { items: body as T[], hasMore };
}
export function errorMessage(error: unknown) {
  return error instanceof Error
    ? error.message
    : "Ocurrió un error. Vuelve a intentar.";
}
