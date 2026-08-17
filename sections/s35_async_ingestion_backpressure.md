SOURCE: LOCAL_SOC_SLM_Blueprint_v11.6.0_master.txt
BLOCK:  SECTION 35: ASYNCHRONOUS INGESTION
SHA256: 62394cd1819fe758
────────────────────────────────────────────────────────────────────────

35.0 Purpose
Alert ingestion must be decoupled from SLM inference.
The intake path must not block on model inference.
This section defines the backpressure and queueing contract required to
prevent alert bursts from saturating GPU KV-cache context windows, timing out
intake endpoints, or crashing the enrichment pipeline.
35.1 Queue implementation policy
Preferred v1 queue implementation:
Use PostgreSQL or SQLite as the durable local queue.
Do not introduce Redis, RabbitMQ, Kafka, or another external queue
service unless lab evidence proves the local queue is insufficient.
This preserves the blueprint principle:
No new heavy services.
If Redis or another queue is later introduced, it must be recorded as a
LAB-VERIFY dependency in Appendix N and must not become a hidden source of
raw telemetry.
35.2 Intake flow
The intake flow must be:
1. Webhook, filebeat, EVE intake, or API adapter receives alert.
2. Alert is sanitized or quarantined.
3. Sanitized alert reference is written to the triage queue.
4. Intake returns HTTP 202 Accepted or equivalent local acknowledgment.
5. Worker pool claims queued jobs using bounded concurrency.
The intake adapter must not directly invoke the SLM for every alert.
35.3 Queue states
Queue items must have at least the following states:
pending
processing
completed
failed
quarantined
shed
State transitions must be recorded.
35.4 Severity prioritization
Queue workers must prioritize alerts by severity and enqueue time.
Recommended priority order:
critical
high
medium
low
informational
Within the same severity, older items must be processed first.
35.5 Backpressure thresholds
The deployment must define:
warning_queue_depth
emergency_queue_depth
max_worker_concurrency
max_inflight_inference_requests
max_embedding_batch_size
max_attempts
queue_lease_interval
If queue depth exceeds warning_queue_depth:
Low-severity enrichment may be delayed.
Metrics must record queue pressure.
If queue depth exceeds emergency_queue_depth:
Low-severity alerts may be shed from SLM triage.
Medium-severity alerts may be delayed or shed only if policy allows.
High-severity and critical alerts must not be silently dropped.
Shedding must be auditable.
Wiki generation tasks are low-priority background work and may be delayed or
shed before operational alert triage [v11.6].
35.6 Shedding policy
When shedding occurs:
The queue item state must become shed.
The shed_reason must be recorded.
The alert must remain visible in the SOC dashboard or OpenSearch.
The event must be written to the handoff ledger or an equivalent audit
table.
Shedding is not deletion.
35.7 Dead-letter and retry behavior
Jobs that fail repeatedly must not be silently discarded.
Required behavior:
attempts counter must be incremented.
after max_attempts, the job must move to failed or quarantined.
failure_reason must be recorded.
payload_ref must remain available for investigation.
35.8 Worker concurrency and VRAM coupling
Worker concurrency must be bounded by the VRAM budget in Section 33.
If VRAM pressure is detected:
reduce worker concurrency,
reduce embedding batch size,
reduce context length,
or shed low-severity work.
Worker autoscaling must never override the approval-gated mutation contract.
35.9 Stale job recovery [v11.5.1]
Workers that crash, time out, or OOM must not leave queue rows permanently
stuck in status = 'processing'.
The queue must implement lease-based recovery.
Recommended columns:
lease_expires_at TIMESTAMPTZ
last_heartbeat_at TIMESTAMPTZ
When a worker claims a job, it must set:
status = 'processing'
started_at = now()
attempts = attempts + 1
lease_expires_at = now() + queue_lease_interval
Default queue_lease_interval:
15 minutes
Long-running SLM jobs must extend the lease with periodic heartbeats:
UPDATE triage_queue
SET last_heartbeat_at = now(),
lease_expires_at = now() + interval '15 minutes'
WHERE id = :job_id
AND status = 'processing';
A reaper process must periodically recover stale jobs:
UPDATE triage_queue
SET status = 'pending',
started_at = NULL,
lease_expires_at = NULL
WHERE status = 'processing'
AND lease_expires_at < now()
AND attempts < :max_attempts;
Jobs that exceed max_attempts must move to failed or quarantined:
UPDATE triage_queue
SET status = 'failed',
finished_at = now(),
failure_reason = 'max_attempts_exceeded_after_stale_recovery'
WHERE status = 'processing'
AND lease_expires_at < now()
AND attempts >= :max_attempts;
Stale recovery events must be auditable.
Stale recovery is not silent deletion.
35.10 Acceptance criteria
Intake does not block on SLM inference.
Queue state transitions are recorded.
Severity prioritization works.
Backpressure thresholds are tested.
Shedding is auditable and does not delete alerts.
Failed jobs enter dead-letter or quarantine state.
Worker concurrency is bounded by VRAM budget.
Crashed workers do not leave jobs stuck in processing.
Lease expiration recovers jobs safely.
Jobs exceeding max_attempts are failed or quarantined.

