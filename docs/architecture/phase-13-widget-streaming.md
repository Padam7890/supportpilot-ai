# Phase 13 — widget streaming reliability

Tracking: [Production hardening roadmap #10](https://github.com/Padam7890/supportpilot-ai/issues/10)

## Runtime change
The widget already consumes SSE deltas, but its reveal loop accelerated in proportion to the backlog (`ceil(remainingWords / 70)`). When many deltas arrived together due to upstream buffering or rapid generation, this could paint most of the response at once and make the stream appear non-incremental.

The widget now reveals at most two word groups per 30ms tick, regardless of how much text has arrived. This changes only the **visual reveal**, not backend provider latency or the time to first SSE delta. CRLF event framing is normalized for compatibility.

## Validation
The existing Playwright widget stream test exercises disconnect/resume, final message deduplication, HTML safety, and multiple DOM paints from a burst. The test now explicitly checks observed intermediate paints.

Run:
```bash
cd frontend
node --check public/supportpilot-widget.js
npm run lint
npm run typecheck
npx playwright test tests/e2e/widget-reply-stream.spec.ts
```

## Next required work
- Run the Playwright test and record timing from first provider token, Redis publish, SSE browser receipt, and first DOM update.
- Diagnose server/proxy buffering separately; this UI change cannot fix network-level delayed first bytes.
- Add tests for CRLF split across chunks, provider outage, retry exhaustion, handoff and accessibility.
- Ensure visual reveal and final history reconciliation do not indefinitely delay the final answer.

**Status:** Implemented in a draft PR; checks have not been executed.
