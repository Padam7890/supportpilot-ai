# Analytics metric definitions

Dashboard aggregates use records scoped to the signed-in workspace. Date filters include both endpoints in UTC. Outcome counts reflect the current state of records in the selected period and can change after a later retry, review, or delivery.

| Metric | Source and date | Counting rule |
| --- | --- | --- |
| AI requests and tokens | AI executions, grouped by creation date | Count one execution record. Sum recorded input and output tokens. A reused execution record stays one request. |
| AI bot latency | Successful bot executions grouped by creation date | Measure start to completion for records with ordered timestamps. The 95th percentile is calculated over those timed runs, alongside the average and sample size. |
| Estimated AI cost | Recorded AI execution tokens | Multiply input and output tokens by their respective configured USD rates per million tokens. Both rates are required. The displayed rates apply to the full selected period and the estimate can differ from a provider invoice. |
| Document citation coverage | Successful playground answers, reply drafts, and widget replies with a recorded model, grouped by execution creation date | Divide executions with at least one citation by eligible executions. With no eligible executions, coverage is unavailable. Citation presence measures source use. |
| First response | Conversations grouped by their first customer message | Measure time to the first eligible teammate or AI reply. Exclude internal notes and failed deliveries. For outbound delivery jobs, use successful completion time. For replies without a delivery job, use message creation time. Provider acceptance can precede customer receipt. |
| Inbox first-response SLA | Ticket and its conversations | Apply the same reply eligibility rule at ticket level. The ticket priority selects the SLA target. |
| Channel delivery | Outbound integration delivery jobs grouped by creation date | Count each persisted job once and report its current state. Attempt averages use the persisted attempt counter. |
| Workflow health | Automation executions grouped by creation date | Count each persisted execution once by current state. Average duration uses successful executions with start and completion timestamps. |
| Human commerce review | Commerce requests grouped by creation date | Measure from creation to approval or rejection. Exclude pending, expired, and cancelled requests from timing. Show average, median, and sample size. |
| Commerce execution completion | Approved commerce requests in the same creation-date cohort | Measure from approval to terminal execution completion for successes and failures with ordered timestamps. Includes queue time and retries. |
| Recommendation events | Tenant-scoped recommendation event records grouped by event creation date | Count each persisted idempotent event once. Impression, product click, comparison, rejection, no-result, and human-handoff events are supported. No raw customer message is retained in the analytics response. |
| Recommendation performance by bot | Recommendation events joined through the tenant-owned message and its widget AI execution | Attribute the event to the bot recorded on the execution that handled the source message. Events without a resolvable widget execution remain in workspace totals but are omitted from the per-bot table. The table is bounded to 50 bots. |
| Recommendation conversion | Trusted cart or commerce provider events | Cart adds and purchases are unavailable until a trusted event source is configured. Do not interpret clicks as cart activity or purchases. A 7-day attribution window is a planned contract default, not a measured conversion report. |
| Inbox SLA status | Earliest customer message and first eligible reply across a ticket's conversations | `met` means reply at or before the ticket's priority deadline; `breached` means reply after it. Awaiting replies become `overdue` at the deadline, `at_risk` within `min(60, max(5, 25% of target))` minutes of it, and otherwise `on_track`. Inbox SLA filters use these same categories before cursor pagination. |

Operations uses a rolling window for recent failures and shows live state for queue and approval alerts. The [Operations runbook](operations-runbook.md) describes those windows, recovery steps, and trace references.
