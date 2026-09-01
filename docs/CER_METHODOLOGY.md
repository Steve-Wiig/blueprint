# Cognitive Escalation & Refeed (CER) Protocol

**Status:** Approved Architectural Methodology
**Phase:** Winter Development
**Objective:** Eliminate the "Local Minimum Trap" (Echo Chamber) in autonomous code repair by utilizing fast, cheap models to generate strategic constraints before refeeding hard problems to large, expensive models.

---

## 1. The Problem: The Local Minimum Trap
When an LLM generates code that fails a safety gate (pytest, AST, or logic error), the naive autonomous response is to feed the error back to the *same* model and say "try again." 

Because LLMs are probabilistic engines operating on the same context window, they frequently fall back into the exact same probability groove. They don't "try harder"; they just "try the same flawed logic louder." This results in infinite retry loops that burn API quotas without solving the root cause.

## 2. The Solution: Cognitive Escalation
Instead of blindly retrying, the pipeline interjects a **Fast-Model Interrogation** step. We use a cheap, low-latency model (e.g., Groq Llama-3, Gemini Flash) to act as a "Meta-Critic." 

The Meta-Critic is strictly forbidden from writing code. Its only job is to analyze the failure and generate a **Strategic Constraint** that forces the heavy model (OpenRouter/Nemotron/Qwen) to adopt a completely different algorithmic approach on the refeed.

## 3. The 4-Step CER Flow

### Step 1: Baseline Generation & Failure
- **Actor:** Heavy Model (OpenRouter)
- **Action:** Generates code. Code fails a deterministic gate (e.g., pytest traceback, AST syntax error, scope violation).
- **State:** `ATTEMPT_1_FAILED`

### Step 2: Fast-Model Interrogation (The Critic)
- **Actor:** Fast Model (Groq / Gemini)
- **Input:** `[Original Prompt] + [Failed Code] + [Gate Error/Traceback]`
- **Prompt Directive:** *"You are a Senior Architect. The previous AI failed. Analyze the error. In exactly ONE sentence, provide a 'Strategic Hint' for the next AI. Tell it what specific approach it MUST take, or what approach it is FORBIDDEN from using. DO NOT WRITE CODE."*
- **Output:** A concise Strategic Constraint.

### Step 3: Strategic Constraint Formulation
The pipeline captures the Meta-Critic's output and formats it into a high-priority system injection. Examples:
- *Anti-Repetition:* "Your previous approach used Regex to parse JSON and failed on nested brackets. You are FORBIDDEN from using Regex. You MUST use `json.loads`."
- *Scope-Down:* "Your previous scope was too wide. You MUST use the SEARCH/REPLACE contract. Do not touch any method other than the one explicitly mentioned."
- *Step-Back:* "You are overcomplicating the edge cases. Write a 2-line comment explaining the simplest happy-path, then implement ONLY that."

### Step 4: Heavy-Model Refeed (The "College Try")
- **Actor:** Heavy Model (OpenRouter)
- **Input:** `[Original Prompt] + [Strategic Constraint Injection]`
- **Action:** Generates code using the new cognitive boundary.
- **State:** `ATTEMPT_2_REFEED`

---

## 4. Tracking the "Journey" (Telemetry Schema)

To prove this methodology works, the JSONL telemetry must track the exact cognitive journey of every repair attempt. The following fields are added to the telemetry schema:

| Field | Type | Description |
| :--- | :--- | :--- |
| `cer_triggered` | boolean | Did the failure trigger the Cognitive Escalation protocol? |
| `critic_model` | string | Which fast model generated the insight? (e.g., `groq/llama3-70b`) |
| `strategic_insight` | string | The exact text of the constraint injected into the refeed. |
| `refeed_outcome` | string | `success`, `failed_same_error`, `failed_new_error`, `truncated` |
| `cognitive_shift` | string | Categorized type of shift (e.g., `algorithm_change`, `scope_reduction`, `anti_repetition`) |

---

## 5. Metrics of Success (The ROI Dashboard)

As the system runs, the Telemetry Reporter (`tools/telemetry_report.py`) will parse the NAS JSONL archive to generate the **CER Efficacy Dashboard**. This allows humans and AI to evaluate the journey:

1. **Escape Velocity:** What percentage of `ATTEMPT_1_FAILED` items successfully pass on `ATTEMPT_2_REFEED`? (Target: >40%)
2. **Critic Accuracy:** Which `critic_model` generates the most successful `strategic_insight` payloads?
3. **Echo Chamber Rate:** How often does `refeed_outcome == failed_same_error`? (If high, the Meta-Critic prompts need tuning).
4. **Token ROI:** Compare the API cost of [1 Heavy Fail + 1 Fast Critic + 1 Heavy Refeed] vs [3 Heavy Blind Retries]. 

---

## 6. Adversarial Failure Modes & Mitigations

| Failure Mode | Description | Mitigation |
| :--- | :--- | :--- |
| **Critic Hallucination** | The fast model suggests a constraint that is factually wrong or breaks the codebase. | The heavy model's output still must pass the deterministic AST/pytest gates. The critic cannot bypass safety. |
| **Constraint Verbosity** | The critic generates a massive paragraph instead of a 1-sentence constraint, bloating the refeed context window. | Hard token limit (max 150 tokens) on the critic's output. Truncate and reject if exceeded. |
| **Infinite Escalation** | The system keeps triggering CER on the same file across multiple nights. | Handled by Pillar 1 (Defeat Ledger). If CER fails 3 times, the item is marked `DEFEATED` and quarantined. |
