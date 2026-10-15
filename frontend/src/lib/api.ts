/**
 * Thin fetch wrapper for the Policy Compass API.
 * The API always returns errors as { error: { code, message, fields?, error_id? } };
 * this turns them into ApiError so screens can show the human-readable message.
 */

export class ApiError extends Error {
  status: number;
  code: string;
  fields: Record<string, string>;
  errorId?: string;

  constructor(
    status: number,
    code: string,
    message: string,
    fields: Record<string, string> = {},
    errorId?: string,
  ) {
    super(message);
    this.status = status;
    this.code = code;
    this.fields = fields;
    this.errorId = errorId;
  }
}

const NETWORK_MESSAGE = "We couldn't reach Policy Compass. Check your connection and try again.";

export async function api<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers);
  if (init.body && !(init.body instanceof FormData)) {
    headers.set("Content-Type", "application/json");
  }

  let response: Response;
  try {
    response = await fetch(`/api${path}`, { ...init, headers, credentials: "include" });
  } catch {
    throw new ApiError(0, "network_error", NETWORK_MESSAGE);
  }

  if (response.status === 204) return undefined as T;
  const body = await response.json().catch(() => null);

  if (!response.ok) {
    const err = body?.error;
    throw new ApiError(
      response.status,
      err?.code ?? "unknown_error",
      err?.message ?? "Something went wrong. Please try again.",
      err?.fields ?? {},
      err?.error_id,
    );
  }
  return body as T;
}
