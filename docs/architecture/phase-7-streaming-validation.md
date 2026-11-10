# Phase 7 — widget streaming integration checks

The backend already emits SSE `message.delta` events from the Redis stream and the
Next.js widget proxy forwards the response body without buffering. The browser
consumes those events and progressively paints the assistant bubble.

## Fixes in this branch

- Repeated `execution.status` and `execution.started` frames for the same
  execution attempt no longer clear already-received text.
- A status frame cannot rewind the last received Redis delta cursor.
- A terminal event is not discarded just because it shares an older
  sequence offset than the latest text delta.
- A different execution attempt still clears provisional text.

## Validation before merge

1. Run `node --check frontend/public/supportpilot-widget.js`.
2. In a Shopify development store, submit a question with a long, grounded
   answer. Confirm the DOM updates before `message.completed` arrives.
3. Replay an `execution.status` frame after a `message.delta`; the bubble
   must keep the previous text and accept subsequent deltas.
4. Reconnect with `?after=<last-delta-sequence>`; ensure no duplicated text.
5. Retry an execution with a new attempt; the previous provisional answer
   must disappear.
6. Check cancellation, handoff, expired visitor tokens, and source revocation.
7. Confirm committed history replaces the provisional bubble without
   duplicating the assistant message.
8. Compare provider first-token, Redis publish, SSE arrival, browser delta,
   and first DOM update timestamps. If deltas only arrive at the end, debug
   provider/worker/proxy buffering rather than adding a fake typewriter delay.

These checks have **not** been executed by this change.
