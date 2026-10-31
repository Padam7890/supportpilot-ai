import { ApiError } from "./errors";

export async function api<T>(path: string, init: RequestInit = {}): Promise<T> {
  const response = await fetch(`/api${path.startsWith("/") ? path : `/${path}`}`, {
    ...init,
    credentials: "same-origin",
    cache: "no-store",
    headers: {
      accept: "application/json",
      ...(init.body ? { "content-type": "application/json" } : {}),
      ...init.headers,
    },
  });
  if (!response.ok) {
    const payload = (await response.json().catch(() => null)) as {
      detail?: string;
      title?: string;
      code?: string;
      type?: string;
      instance?: string;
    } | null;
    throw new ApiError(
      payload?.detail ?? payload?.title ?? "The request could not be completed.",
      response.status,
      payload ?? {},
    );
  }
  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

export function jsonBody(value: unknown): string {
  return JSON.stringify(value);
}
