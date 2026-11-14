/**
 * Cliente mínimo del servidor local (web/server). Todas las rutas cuelgan de /api:
 * en desarrollo las reenvía Vite y en la demo las sirve el mismo proceso que la web.
 */

export class ApiError extends Error {
  readonly status: number

  constructor(status: number, message: string) {
    super(message)
    this.name = 'ApiError'
    this.status = status
  }
}

interface RequestOptions {
  method?: 'GET' | 'POST'
  body?: unknown
  signal?: AbortSignal
}

/** Mensaje para la persona que mira la demo cuando el modelo no contesta. */
export const MODEL_OFFLINE =
  'El modelo no responde. Comprueba que el servidor local está arrancado (web\\start.ps1).'

export async function api<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const { method = options.body === undefined ? 'GET' : 'POST', body, signal } = options
  let response: Response
  try {
    response = await fetch(`/api${path}`, {
      method,
      signal,
      headers: body === undefined ? undefined : { 'Content-Type': 'application/json' },
      body: body === undefined ? undefined : JSON.stringify(body),
    })
  } catch (error) {
    if (error instanceof DOMException && error.name === 'AbortError') throw error
    throw new ApiError(0, MODEL_OFFLINE)
  }
  if (!response.ok) {
    let detail = `Error ${response.status}`
    try {
      const data: unknown = await response.json()
      if (data && typeof data === 'object' && 'detail' in data) {
        const d = (data as { detail: unknown }).detail
        detail = typeof d === 'string' ? d : JSON.stringify(d)
      }
    } catch {
      // La respuesta no era JSON (p. ej. el proxy sin servidor detrás): se queda el código.
    }
    throw new ApiError(response.status, response.status >= 500 ? MODEL_OFFLINE : detail)
  }
  return (await response.json()) as T
}

export function isAbort(error: unknown): boolean {
  return error instanceof DOMException && error.name === 'AbortError'
}
