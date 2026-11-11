# Distinct anonymous storefront visitors

The Shopify storefront widget keeps its existing optional, consent-based name/email collection and first-message ticket creation.

For a visitor who does not provide a consented name, the widget assigns a stable, non-PII display label such as `Visitor #A1B2C3D4` after the customer record is inserted. This uses a prefix of the generated customer UUID, not a visitor's email, IP address, or Shopify identity. It is a human-friendly label, **not** an authentication or verified identity claim. The underlying customer UUID remains the authoritative identifier. Rare prefix collisions are possible; operators should use the ticket/conversation IDs to disambiguate.

The first message continues to supply the ticket subject, now limited to a concise 100-character preview (with an ellipsis if truncated). It is **not** an AI-generated summary or an issue classification; no extra model call is made.

Existing `Store visitor` records are not renamed automatically. Contact collection, order OTP verification, idempotent submissions, and the current conversation/ticket relationship are unchanged.

## Manual review checks

- Start two anonymous widget sessions with distinct idempotency keys; confirm distinct visitor labels appear in the Inbox and customer views.
- Retry the same initial submission with the same key; confirm no extra customer or ticket is created.
- Start a session with consented name/email; confirm the supplied name is retained.
- Confirm an anonymous visitor cannot access order information without the existing verification flow.
- Send a long first message; confirm the ticket subject is shortened while the original message and ticket description are preserved.
- Check old tickets and customer records remain unchanged.

This is a focused usability change. Verified identity capture, returning-visitor linkage, customer merging, and AI-generated issue titles require separate design and implementation.
