import { ApiError } from "@/lib/api/errors";

const MAX_TRANSIENT_RETRIES = 2;
const MAX_RETRY_DELAY_MS = 4000;
const NETWORK_FAILURE = /failed to fetch|fetch failed|networkerror|network request failed|load failed/i;

export function shouldRetryInboxQuery(failureCount: number, error: unknown): boolean {
  if (failureCount >= MAX_TRANSIENT_RETRIES) return false;
  if (error instanceof ApiError) {
    return error.status === 408 || error.status === 429 || error.status >= 500;
  }
  return error instanceof TypeError && NETWORK_FAILURE.test(error.message);
}

export function inboxQueryRetryDelay(attemptIndex: number): number {
  return Math.min(500 * 2 ** attemptIndex, MAX_RETRY_DELAY_MS);
}
