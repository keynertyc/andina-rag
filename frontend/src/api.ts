export class ApiError extends Error {
  code: string;
  resourceId?: string;
  constructor(message: string, code: string, resourceId?: string) {
    super(message);
    this.code = code;
    this.resourceId = resourceId;
  }
}

export async function api<T>(path: string, options?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`/api/v1${path}`, options);
  } catch (error) {
    if (error instanceof DOMException && error.name === "AbortError")
      throw error;
    throw new ApiError(
      "No hay conexión con la API. Comprueba que Docker esté iniciado.",
      "NETWORK",
    );
  }
  const body = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new ApiError(
      body.error?.message ??
        "No se pudo completar la acción. Vuelve a intentar.",
      body.error?.code ?? `HTTP_${response.status}`,
      body.error?.batch_id ?? body.error?.document_id,
    );
  }
  return body as T;
}

export function errorMessage(error: unknown): string {
  return error instanceof Error
    ? error.message
    : "Ocurrió un error. Vuelve a intentar.";
}
