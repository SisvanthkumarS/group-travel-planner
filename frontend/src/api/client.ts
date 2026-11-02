// Thin fetch wrapper for the FastAPI backend.
//
// Auth is an HttpOnly JWT cookie set by POST /auth/login, so the browser
// attaches it for us. We never read or store the token in JS; every request
// just has to send credentials.

const baseUrl = (
  import.meta.env.VITE_API_URL || 'http://localhost:8000/api/v1'
).replace(/\/+$/, '');

type Method = 'GET' | 'POST' | 'PUT' | 'PATCH' | 'DELETE';

export type RequestOptions = {
  method?: Method;
  body?: unknown;
  signal?: AbortSignal;
  /**
   * Set to false for public endpoints (register, login, logout). A 401 from
   * those means bad credentials, not an expired session, so it must not
   * trigger the global sign-out handler.
   */
  auth?: boolean;
};

export class ApiError extends Error {
  readonly status: number;
  /** Field name -> message, from FastAPI 422 validation errors. */
  readonly fieldErrors: Record<string, string>;

  constructor(
    status: number,
    message: string,
    fieldErrors: Record<string, string> = {},
  ) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.fieldErrors = fieldErrors;
  }
}

let unauthorizedHandler: (() => void) | null = null;

/**
 * Register a callback for 401s on authenticated requests (expired or missing
 * session). Returns an unsubscribe function.
 */
export function onUnauthorized(handler: () => void): () => void {
  unauthorizedHandler = handler;
  return () => {
    if (unauthorizedHandler === handler) unauthorizedHandler = null;
  };
}

export async function apiRequest<T>(
  path: string,
  { method = 'GET', body, signal, auth = true }: RequestOptions = {},
): Promise<T> {
  const headers: Record<string, string> = {};
  if (body !== undefined) headers['Content-Type'] = 'application/json';
  if (!['GET', 'HEAD', 'OPTIONS'].includes(method)) {
    headers['X-CSRF-Protection'] = '1';
  }
  let response: Response;
  try {
    response = await fetch(`${baseUrl}${path}`, {
      method,
      credentials: 'include',
      headers: Object.keys(headers).length ? headers : undefined,
      body: body === undefined ? undefined : JSON.stringify(body),
      signal,
    });
  } catch (error) {
    if (error instanceof DOMException && error.name === 'AbortError') {
      throw error;
    }
    throw new ApiError(0, 'Could not reach the server. Try again.');
  }

  if (!response.ok) {
    const error = await toApiError(response);
    if (error.status === 401 && auth) unauthorizedHandler?.();
    throw error;
  }

  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

type ValidationIssue = { loc?: (string | number)[]; msg?: string };

async function toApiError(response: Response): Promise<ApiError> {
  const fallback = `Request failed (${response.status})`;
  let payload: unknown;
  try {
    payload = await response.json();
  } catch {
    return new ApiError(response.status, fallback);
  }

  const detail = (payload as { detail?: unknown } | null)?.detail;

  // Most errors: {"detail": "Only the Trip Organizer can ..."}
  if (typeof detail === 'string') {
    return new ApiError(response.status, detail);
  }

  // Pydantic 422: {"detail": [{"loc": ["body", "end_date"], "msg": "..."}]}
  if (Array.isArray(detail)) {
    const fieldErrors: Record<string, string> = {};
    let formMessage: string | undefined;
    for (const issue of detail as ValidationIssue[]) {
      const msg = cleanMessage(issue.msg ?? 'Invalid value.');
      const field = issue.loc?.filter((part) => part !== 'body').at(-1);
      if (field === undefined) {
        formMessage ??= msg;
      } else {
        fieldErrors[String(field)] ??= msg;
      }
    }
    const message =
      formMessage ??
      Object.values(fieldErrors)[0] ??
      'Please check the form and try again.';
    return new ApiError(response.status, message, fieldErrors);
  }

  return new ApiError(response.status, fallback);
}

// Pydantic prefixes custom validator errors with "Value error, ".
function cleanMessage(msg: string): string {
  return msg.replace(/^Value error, /, '');
}
