# LOCAL-SOC-SLM: Winter Engineering Roadmap

**Phase:** Winter Development (Pre-Hardware / Pre-Live-Traffic)
**Objective:** Evolve the bounded self-healing pipeline into a measurable, deterministic autonomous engineering system before Spring hardware and live SOC traffic arrive.

## The Storage Invariant (Non-Negotiable)
- **No Databases / Vector Stores / RAG** for telemetry or memory. Flat-file JSONL only.
- **50MB Local Cap** on `/dev/sda` (temporary outbox).
- **200GB NAS** (`/dev/sdc`) is the permanent, flat-file JSONL archive.
- Telemetry stores **lightweight metadata only** (~400 bytes/record). Raw prompts/code are banned.

## The 4 Architectural Pillars

### Pillar 1: The Memory Layer (Canonical Defeat Ledger)
- **Concept:** The pipeline must remember what it has tried and failed to fix across nights.
- **Mechanism:** Hash the file's AST (stripping comments/formatting) and the normalized pytest traceback. If `(file_state, failure_signature)` fails 3 times, mark as `DEFEATED` and move to human-review quarantine.
- **Value:** Prevents infinite retry loops that bleed API quotas dry on unfixable bugs.

### Pillar 2: The Output Contract (Search/Replace Patching)
- **Concept:** Stop asking the LLM to rewrite 2,000 lines of code to fix a 3-line bug (the root cause of truncation).
- **Mechanism:** Enforce an Aider-style `<<<<<<< SEARCH ... ======= ... >>>>>>> REPLACE` contract. A deterministic Python parser validates blocks *before* AST/pytest gates run. Pair with a Scope Budget to prevent "replace-all" laziness.
- **Value:** Reduces output token consumption by 50x-100x. Makes truncation mathematically impossible for small fixes.

### Pillar 3: The Hermetic Replay Harness (Pipeline CI/CD)
- **Concept:** A "unit test suite for the autonomous loop."
- **Mechanism:** Turn the NAS JSONL telemetry into a Golden Regression Corpus. Replay historical `raw_response` fixtures through *new* gates/prompts offline to ensure we didn't introduce regressions, without burning live API tokens.
- **Value:** Allows safe, offline A/B testing of new prompt templates and gate logic.

### Pillar 4: Telemetry-Driven Routing & Backpressure
- **Concept:** Move from static fallback chains to dynamic, budget-aware routing.
- **Mechanism:** A nightly cron parses JSONL to build a Provider Efficacy Matrix (e.g., "Groq truncates 40% of files > 1000 lines"). Implement Token-Bucket Pacing so the system gracefully sheds low-priority items under heavy load instead of hitting 429 cliffs.
- **Value:** Maximizes free/low-tier API quotas by sending the right task to the right provider based on empirical evidence.

## Execution Sequence (Strict Dependencies)

### Phase 1: The Foundation
1. **Hermetic Replay Harness (Pillar 3):** Build the tool that turns NAS JSONL into replayable fixtures. (Safety net for all future changes).
2. **Canonical Defeat Ledger (Pillar 1):** Add AST hashing and `DEFEATED` state tracking.

### Phase 2: The Token Economics Revolution
3. **Patch-Diff Contract (Pillar 2):** Rewrite prompts to demand Search/Replace blocks. Build the deterministic block parser with `difflib.SequenceMatcher` fuzzy fallback.
4. **Scope Contract (Pillar 2):** Add AST-diff mapper to ensure the LLM didn't modify functions outside the `SEARCH` block.

### Phase 3: The Intelligence Layer
5. **Telemetry-Driven Router (Pillar 4):** Write the nightly taxonomy job that generates `routing_policy.json`.
6. **Token-Bucket Pacing (Pillar 4):** Upgrade `budget_manager` to a continuous refill bucket with priority shedding.
