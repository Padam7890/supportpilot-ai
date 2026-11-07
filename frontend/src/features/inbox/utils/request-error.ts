import { ApiError } from "@/lib/api/errors";

export function formatInboxRequestError(error: unknown, fallback: string): string {
  if (error instanceof ApiError) {
    const diagnostic = [
      `HTTP ${error.status}`,
      ...(error.code ? [error.code] : []),
    ].join(" · ");
    const reference = error.correlationId ? ` Reference: ${error.correlationId}` : "";
    return `${error.message} (${diagnostic}).${reference}`;
  }

  if (!(error instanceof Error) || !error.message) return fallback;
  if (/failed to fetch|fetch failed|backend service is unavailable/i.test(error.message)) {
    return "SupportPilot could not reach the backend. Check that the API is running and /health/ready returns ready.";
  }
  return error.message;
}
