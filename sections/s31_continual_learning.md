SOURCE: LOCAL_SOC_SLM_Blueprint_v11.6.0_master.txt
BLOCK:  SECTION 31: CONTINUAL LEARNING
SHA256: 04caa6cda7fdd85f
────────────────────────────────────────────────────────────────────────

31.0 Thesis
The system becomes more effective with curated experience without ever
performing autonomous online tuning.
Model weights are frozen during operation.
The system learns through four distinct loops.
Only the third loop changes weights, and it is fully gated, signed, reversible,
and audited.
The fourth loop, autonomous online tuning, is explicitly prohibited for safety
reasons.
31.1 The four adaptation loops
Loop 1 — Retrieval / memory:
Changes:
Prompt context.
Latency:
Next alert.
Gating:
Inert context.
Loop 2 — Deterministic adaptation:
Changes:
Non-ML config.
Latency:
Hours to days.
Gating:
Deterministic gates.
Loop 3 — Gated retraining:
Changes:
Weights via new adapter.
Latency:
Days to weeks.
Gating:
CI + replay-mix + canary + approval.
Loop 4 — Autonomous online tuning:
Changes:
Weights.
Latency:
Continuous.
Gating:
PROHIBITED.
31.2 Loop 1 — Retrieval / memory
Loop 1 is safe and immediate.
pgvector top-k injection, defined in Section 30.5, places past accepted cases
and corrections into every relevant prompt.
The retrieved content is wrapped as inert <memory_context>.
The effect is genuine and immediate:
A corrected alert from yesterday can bias today's similar alert.
Safety posture:
Retrieved content is untrusted context.
Retrieved content is subject to the same <untrusted_log_payload> discipline
as everything else.
The verifier still gates every output.
31.3 Loop 2 — Deterministic adaptation
Loop 2 is safe and medium-term.
It changes non-ML configuration and statistics.
Examples:
Cache TTLs.
Routing priorities.
Quota statistics.
Playbook growth.
Action-budget tuning.
Queue thresholds.
Sanitizer allowlists.
VRAM budget overrides.
Changes are deterministic and auditable.
Anything state-changing remains approval-gated per Section 24.5.
31.4 Loop 3 — Gated retraining
Loop 3 is safe, slow, and fully controlled.
Trigger:
Accumulation of corrections with decision = accept or fix since the last
promotion.
Scheduled cadence, weekly by default.
Data:
Corrections-derived examples only.
Raw operational telemetry never enters training.
Process:
1. QLoRA training on GPU 0.
2. Merge to safetensors or produce signed adapter artifact according to the
approved training pipeline.
3. Sign adapter.
4. Run CI gates from Section 20.7.
5. Run replay-mix evaluation from Section 31.5.
6. Deploy to canary from Section 31.6.
7. Atomic swap if canary passes.
8. Instant rollback if SLO regression occurs.
31.5 Replay-mix evaluation [v11.4]
Adapter promotion requires replay-mix evaluation.
The replay-mix evaluation set must contain:
1. Held-out test examples derived only from approved corrections or
approved curated training data.
2. A replay sample from the golden evaluation set used for the currently
active adapter.
Purpose:
Detect regression on newly learned corrections.
Detect catastrophic forgetting of previously accepted behavior.
Ensure the candidate adapter remains safe for SOC use.
Required metrics:
verifier_pass_rate
schema_validity_rate
prohibited_action_rate
hallucinated_tool_call_rate
IOC extraction accuracy
triage summary sanity score
regression delta against active adapter
forgetting delta against golden replay sample
CI must record:
candidate adapter sha256
active adapter sha256
evaluation dataset hashes
replay sample hashes
metric results
pass/fail verdict
evaluator version
A candidate adapter must not be promoted if replay-mix evaluation fails or if
any safety-critical metric regresses beyond the approved threshold.
31.6 Canary and rollback [v11.4]
Canary deployment is mandatory for promoted adapters.
Canary modes:
Shadow canary:
Candidate adapter receives the same prompt/context as the active
adapter, but its output is not used for operational action.
Limited live canary:
Candidate adapter handles a small, explicitly routed subset of eligible
task_type traffic.
Canary SLOs include:
verifier_pass_rate
schema_validity_rate
prohibited_action_rate
hallucinated_tool_call_rate
analyst correction rate
latency percentile
VRAM stability
recurrence of known failure classes
Promotion:
Promotion is atomic.
Promotion swaps the active adapter pointer or serving endpoint.
The previous signed adapter remains immediately restorable.
Rollback:
Rollback is immediate.
Rollback does not require retraining.
Rollback restores the previous signed adapter pointer or endpoint.
Rollback is recorded in the handoff ledger and model registry history.
31.7 Prohibited autonomous online tuning
Loop 4 is prohibited.
The system must not:
Update model weights from operational traffic.
Perform online fine-tuning from alerts.
Perform reinforcement learning from live SOC events.
Autonomously promote adapters without CI, replay-mix, canary, and approval.
Modify active model weights during inference.
Use raw telemetry directly as training data.
All weight changes occur only through Loop 3.
31.8 Acceptance criteria
Retrieval memory injection is visible in handoff metadata.
Deterministic configuration changes are auditable.
Corrections are the only operational source for retraining examples.
Replay-mix evaluation is mandatory for adapter promotion.
Canary evaluation is mandatory before active promotion.
Rollback is immediate and tested.
No online weight tuning path exists in code or config.

