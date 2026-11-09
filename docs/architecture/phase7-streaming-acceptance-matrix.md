# Phase 7 — Widget streaming acceptance matrix

## Security invariant

Do not expose raw LLM tokens before full-answer grounding and tenant-source authorization. Redis deltas are provisional and must never override the persisted message or bypass human takeover.

## Covered by code changes in this PR

- CRLF boundaries split across network chunks and bare-CR SSE separators.
- Bounded SSE reconnect attempts with exponential delay.
- Malformed Redis cursor fails closed in browser without throwing.
- Oversized SSE frames abort parsing.
- Redis transport errors fall back to polling durable execution status.
- Typed SSE events reject text on terminal events and reject malformed completed events.
- Customer action retractions such as "don't cancel" are recognized by the follow-up module.

## Required end-to-end scenarios before release

1. Actual streaming: observe multiple message.delta frames arriving at different times before message.completed; not merely an animation after generation.
2. Grounding: unsupported numeric policy answer is never streamed; authorized and cited knowledge survives to final message.
3. Shopify: no unverified order details leak in SSE or replay.
4. Redis: outage before first delta, mid-stream, reconnect, and expired replay key.
5. Race conditions: human takeover, bot switch, disabled widget, new customer message, and revoked knowledge source mid-generation.
6. Attempts: worker retry must not replay stale attempt deltas; duplicate cursor frames must not duplicate words.
7. Browser: split UTF-8 bytes, split CRLF, bare CR, malformed JSON, empty events, oversized frames, mobile Safari, background/resume.
8. Follow-ups: yes/no, topic switch, order verification, OTP interruption, cancellation retraction, multiple turns and expired pending state.
9. Persistence: terminal event references the committed message, and history polling replaces the provisional row exactly once.
10. Performance: time-to-first-delta, sustained cadence, slow network and long answers.

## Test commands

`cd backend && pytest -q tests/test_widget_reply_stream.py tests/test_follow_up_retractions.py`

Run the full backend suite, frontend checks, and browser E2E suite in CI. These have not been executed by the GitHub connector.

## Known blocker

The AI worker currently generates a full draft before grounding validation and does not publish model deltas. True low-latency streaming therefore remains **not implemented**. Do not mark Phase 7 complete or merge as production-ready until a safe progressive delivery design and end-to-end verification are in place.
