const API_URL = import.meta.env.VITE_API_URL ?? "http://localhost:8000/api/v1";

function getSessionId(): string | null {
  return sessionStorage.getItem("sessionId");
}

function buildHeaders(extra: Record<string, string> = {}): Record<string, string> {
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...extra,
  };
  const sid = getSessionId();
  if (sid) {
    headers["X-SESSION-ID"] = sid;
  }
  return headers;
}

export async function apiFetch<T = unknown>(
  path: string,
  init: RequestInit = {},
): Promise<T> {
  const resp = await fetch(`${API_URL}${path}`, {
    ...init,
    headers: buildHeaders(init.headers as Record<string, string>),
  });

  if (!resp.ok) {
    const body = await resp.json().catch(() => ({ detail: resp.statusText }));
    throw new Error(body.detail ?? `HTTP ${resp.status}`);
  }

  if (resp.status === 204) return undefined as T;
  return resp.json();
}

export function apiStreamUrl(path: string): string {
  return `${API_URL}${path}`;
}

export { getSessionId, buildHeaders, API_URL };
