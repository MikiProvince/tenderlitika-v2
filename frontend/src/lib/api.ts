import { getApiKey } from "./storage";

const BASE = process.env.NEXT_PUBLIC_API_BASE || "http://127.0.0.1:8000";

type FetchOpts = RequestInit & { auth?: boolean };

export async function apiFetch<T>(path: string, opts: FetchOpts = {}): Promise<T> {
  const headers = new Headers(opts.headers || {});
  headers.set("Accept", "application/json");

  const useAuth = opts.auth !== false; // по умолчанию true
  if (useAuth) {
    const key = getApiKey();
    if (key) headers.set("X-API-Key", key);
  }

  const res = await fetch(`${BASE}${path}`, {
    ...opts,
    headers,
  });

  if (!res.ok) {
    let detail = `${res.status} ${res.statusText}`;
    try {
      const data = await res.json();
      detail = data?.detail ? String(data.detail) : JSON.stringify(data);
    } catch {}
    throw new Error(detail);
  }

  return (await res.json()) as T;
}
