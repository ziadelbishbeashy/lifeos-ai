export class ApiError extends Error {
  status: number;
  code?: string;

  constructor(message: string, status: number, code?: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
  }
}

type ApiErrorPayload = {
  error?: string;
  message?: string;
};

let csrfToken: string | null = null;

async function readJson<T>(response: Response): Promise<T> {
  const contentType = response.headers.get("content-type") ?? "";
  if (!contentType.includes("application/json")) {
    if (!response.ok) {
      throw new ApiError(`API request failed (${response.status})`, response.status);
    }
    return undefined as T;
  }

  const payload = (await response.json()) as T | ApiErrorPayload;
  if (!response.ok) {
    const errorPayload = payload as ApiErrorPayload;
    throw new ApiError(
      errorPayload.message ?? `API request failed (${response.status})`,
      response.status,
      errorPayload.error,
    );
  }

  return payload as T;
}

async function fetchCsrfToken(force = false): Promise<string> {
  if (csrfToken && !force) {
    return csrfToken;
  }

  const response = await fetch("/api/v1/csrf", {
    method: "GET",
    credentials: "include",
    headers: { Accept: "application/json" },
  });

  const payload = await readJson<{ csrf_token: string }>(response);
  csrfToken = payload.csrf_token;
  return csrfToken;
}

export function resetCsrfToken() {
  csrfToken = null;
}

export async function apiGet<T>(path: string): Promise<T> {
  const response = await fetch(path, {
    method: "GET",
    credentials: "include",
    headers: { Accept: "application/json" },
  });

  return readJson<T>(response);
}

async function apiUnsafe<T>(
  path: string,
  method: "POST" | "PUT" | "PATCH" | "DELETE",
  body?: unknown,
  retryCsrf = true,
): Promise<T> {
  const token = await fetchCsrfToken();

  const response = await fetch(path, {
    method,
    credentials: "include",
    headers: {
      Accept: "application/json",
      "Content-Type": "application/json",
      "X-CSRFToken": token,
    },
    body: body === undefined ? undefined : JSON.stringify(body),
  });

  // Flask-WTF returns a JSON 400 titled "Your form expired" when the
  // token/session is stale. Refresh exactly that case once; ordinary domain
  // validation errors must never be submitted twice.
  if (response.status === 400 && retryCsrf) {
    const probe = response.clone();
    const contentType = probe.headers.get("content-type") ?? "";
    if (contentType.includes("application/json")) {
      const payload = (await probe.json()) as ApiErrorPayload;
      if (payload.error === "Your form expired") {
        resetCsrfToken();
        await fetchCsrfToken(true);
        return apiUnsafe<T>(path, method, body, false);
      }
    }
  }

  return readJson<T>(response);
}

export function apiPost<T>(path: string, body?: unknown): Promise<T> {
  return apiUnsafe<T>(path, "POST", body);
}

export function apiPatch<T>(path: string, body?: unknown): Promise<T> {
  return apiUnsafe<T>(path, "PATCH", body);
}

export function apiDelete<T>(path: string, body?: unknown): Promise<T> {
  return apiUnsafe<T>(path, "DELETE", body);
}

export async function apiPostForm<T>(path: string, form: FormData): Promise<T> {
  const token = await fetchCsrfToken();
  const response = await fetch(path, {
    method: "POST",
    credentials: "include",
    headers: {
      Accept: "application/json",
      "X-CSRFToken": token,
    },
    body: form,
  });
  return readJson<T>(response);
}
