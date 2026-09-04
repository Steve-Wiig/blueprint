SOURCE: soc-autopilot (historical)
BLOCK:  SECTION 33: INFERENCE, EMBEDDING, AND VRAM
SHA256: a80b1a8447a6dec9
────────────────────────────────────────────────────────────────────────

33.0 Purpose
Section 33 governs how local SLM inference, embedding generation, adapter
serving, and VRAM limits are managed on consumer hardware.
This section does not mandate a specific serving backend. It mandates that the
chosen backend be proven against the project's safety, memory, and rollback
requirements.
33.1 Hardware contexts
Single-GPU baseline:
One NVIDIA GPU with 16GB VRAM.
Training, inference, embedding, and SOC workloads must be serialized or
tightly bounded.
Future dual-GPU path:
GPU 0:
Development bench: training, merge, heavy eval.
GPU 1:
Analyst-on-shift inference worker and embedding worker.
A second GPU increases operational availability, not autonomy.
33.2 Serving stack decision record
The deployment must record:
serving_backend
serving_backend_version
model_name
model_hash
quantization_format
context_length_limit
parallel_request_limit
vram_budget_limit
embedding_worker_location
adapter_loading_mechanism
rollback_mechanism
Candidate serving approaches include, but are not limited to:
Local OpenAI-compatible inference server.
Ollama-style local model runner.
vLLM-style serving backend.
llama.cpp-style lightweight server.
No candidate is mandatory until validated in the lab.
33.3 Dynamic VRAM budget [v11.5]
The VRAM budget must not be hardcoded to a single GPU SKU.
The VRAM smoke check must dynamically detect installed GPU memory and enforce
a safety ceiling.
Default policy:
maximum_allowed_vram = total_gpu_vram * 0.90
The 10% reserve is reserved for:
CUDA context overhead,
driver overhead,
embedding co-residency spikes,
KV-cache fragmentation,
unexpected concurrent requests.
The check must still run a representative workload:
maximum configured context length,
concurrent embedding batch,
at least one inference request or simulated inference allocation.
Idle VRAM polling alone is insufficient.
If nvidia-smi or NVML is unavailable on a GPU-required runner, the check must
fail closed.
If the VRAM budget is exceeded, the deployment must reduce at least one of:
model size,
quantization footprint,
context length,
parallelism,
embedding co-residency,
concurrent service load,
or move to serialized operation.
33.4 Adapter promotion mechanisms
Adapter promotion must use one or more of the following mechanisms:
active adapter pointer swap,
model registry status change,
serving endpoint swap,
container swap,
reverse proxy switch,
serving backend reload.
The chosen mechanism must satisfy:
signed adapter verification,
health check before promotion,
immediate rollback,
audit ledger recording,
no requirement to retrain during rollback.
If the serving backend does not support hot adapter swapping, promotion may be
implemented by starting a new verified serving instance and switching the local
routing endpoint after health checks pass.
33.5 Embedding service contract
The embedding service must:
pin model artifact and hash,
enforce dimension 768 for orchestration memory,
enforce normalization policy,
enforce prefix policy if required,
enforce idempotent prefix normalization,
record embedding model metadata in handoff or ledger metadata,
fail closed if prefix or dimension contract cannot be satisfied.
Embedding generation may co-reside with the inference worker only if the VRAM
budget smoke check passes.
33.6 Acceptance criteria
Serving backend is documented and version-pinned.
VRAM budget smoke check passes.
Context length and concurrency limits are configured and tested.
Adapter promotion mechanism is documented.
Rollback drill passes.
Embedding prefix and dimension checks pass.
Embedding prefix idempotency check passes.
No unbounded model loading or unbounded context expansion is possible.
Dynamic VRAM detection fails closed when GPU metrics are unavailable.

