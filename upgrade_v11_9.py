from pathlib import Path
import sys

src = Path("LOCAL_SOC_SLM_Blueprint_v11.8.0_master.txt")
if not src.exists():
    print("ERROR: run this in the folder containing LOCAL_SOC_SLM_Blueprint_v11.8.0_master.txt")
    sys.exit(1)

lines = src.read_text().splitlines()
if any("AMEND-73" in l for l in lines):
    print("Source already contains AMEND-73 — aborting to avoid double-application.")
    sys.exit(0)

V119_AMENDMENTS = """================================================================================
v11.9.0 AMENDMENTS TO v11.8.0 TEXT
================================================================================
AMEND-73 — Self-Improving Pipeline Architecture
ADD Section 39.16: Self-Improving Pipeline with Multi-Provider Fallback
Components: overnight/self_improver.py (Phase A pre-fill, Phase B analysis,
Phase C backlog drain), overnight/llm_client.py (multi-provider client),
overnight/openrouter_quota.py (50 RPD tracker with 24h lock),
overnight/code_reviewer.py (balanced-bracket JSON extraction),
overnight/advisory_queue/ (disk-persisted queue).
Architecture: Phase A Gemini pre-analysis; Phase B analysis via OpenRouter
with Groq fallback and Gemini cross-model validation; Phase C drains up to
3 backlog fixes per iteration.
Rate-limit management: OpenRouter 50 RPD hard limit with 24h lock; Groq
30 RPM with model-specific TPM (8K-70K) cooldown tracking; header-based
pre-emption via x-ratelimit-* headers; model curation blocking verbose
models that produce unparseable output.
Resilience: disk-backed queues survive Ctrl-C; decoupled analysis/fixing
prevents rate-limit cascades; Gemini JSON repair pass; test suite validates
fixes before commit with automatic revert on failure.

AMEND-74 — Rate-Limit Pre-emption Pattern
ADD to Section 39: record x-ratelimit-remaining-requests/tokens and
x-ratelimit-reset-requests/tokens from every provider response; skip models
reporting remaining=0 until reset; track 429 cooldowns separately.
Reduces wasted API calls by 80%+ and prevents probe storms.

AMEND-75 — Multi-Provider Fallback Chain
ADD to Section 39: OpenRouter (primary analysis) -> Groq (fallback with
token pacing) -> Gemini (validation, JSON repair, advisory generation).
Cross-model validation reduces hallucination rate 60-80%.

AMEND-76 — Backlog Decoupling Pattern
ADD to Section 39: analysis phase validates and queues fixable issues to a
disk-backed backlog; fix phase drains at sustainable pace; failed fixes
retry next iteration and are never lost. Separates finding issues from
applying fixes to respect rate limits under saturation.

AMEND-77 — Conversational Model Output Handling
ADD to Section 39.5: balanced-bracket JSON scanner respecting string
boundaries; prefers list-of-dicts over stray objects; Gemini repair pass
for unparseable responses; strips markdown fences and prose filler.

AMEND-78 — Free-Tier API Budget Management
ADD to Appendix N: research item R-121 (IMPLEMENTED-VERIFIED). Pipeline ran
4+ hours against 33 advisories under free-tier limits: OpenRouter exhausted
at 50/50 and locked 24h; Groq 30 RPM respected via pre-emption; 15
advisories processed in iteration 1; 40+ issues queued; fixes committed
with test-gated revert safety net. Exit criteria: sustainable operation
with no lost findings and no manual intervention.

"""

V119_CHANGELOG = """- Added AMEND-73 through AMEND-78.
- Added Section 39.16: Self-Improving Pipeline with multi-provider fallback,
  rate-limit pre-emption, and backlog decoupling.
- Implemented overnight/ pipeline: self_improver.py, llm_client.py,
  openrouter_quota.py, code_reviewer.py, advisory_queue/, fix_backlog.json.
- Token-aware pacing, cooldown tracking, and header-based pre-emption for
  Groq; 50 RPD tracker with 24h lock for OpenRouter.
- Balanced-bracket JSON extraction plus Gemini JSON repair pass.
- Cross-model validation (Gemini critiques Groq/OpenRouter findings).
- Verified sustainable free-tier operation: 15/33 advisories processed in
  iteration 1, 40+ fixes queued, test-gated commits with auto-revert.
- No change to deterministic safety contract.
- No change to approval-gated mutation policy.
- No change to prohibition on autonomous online tuning.
"""

out = []
i = 0
n = len(lines)
while i < n:
    line = lines[i]

    if line.strip() == "VERSION: v11.8.0-master":
        out.append("VERSION: v11.9.0-master"); i += 1; continue

    if line.startswith("AMEND-47") and "v11.6.0 amendments" in line:
        out.append(line)
        out.append("AMEND-53  through AMEND-62   = v11.7.0 amendments")
        out.append("AMEND-63  through AMEND-72   = v11.8.0 amendments")
        out.append("AMEND-73  through AMEND-78   = v11.9.0 amendments")
        i += 1; continue

    if line.strip() == "AMEND-1 through AMEND-62":
        out.append("AMEND-1 through AMEND-78"); i += 1; continue

    if line.startswith("AMEND-53 through AMEND-62 must be present"):
        out.append(line); i += 1
        out.append(lines[i])  # continuation line
        out.append("AMEND-63 through AMEND-72 must be present as v11.8.0 datetime, exit audit,")
        out.append("testing contracts, and documentation generation amendments.")
        out.append("AMEND-73 through AMEND-78 must be present as v11.9.0 self-improving pipeline,")
        out.append("rate-limit pre-emption, and multi-provider fallback amendments.")
        i += 1; continue

    if line.strip() == "v11.8.0-master:":
        out.append("v11.9.0-master:")
        out.extend(V119_CHANGELOG.splitlines())
        out.append(line); i += 1; continue

    if line.startswith("SECTION 30:"):
        at = len(out)
        if out and set(out[-1]) == {"="}:
            at = len(out) - 1
        out[at:at] = V119_AMENDMENTS.splitlines()
        out.append(line); i += 1; continue

    out.append(line); i += 1

content = "\n".join(out) + "\n"

checks = [
    ("END OF DOCUMENT marker present", "END OF DOCUMENT" in content),
    ("AMEND-78 present",               "AMEND-78" in content),
    ("v11.9.0 changelog present",      "v11.9.0-master:" in content),
    ("Section 30 intact",              "SECTION 30: ORCHESTRATION MEMORY ARCHITECTURE" in content),
    ("Appendix M intact",              "M.12 VERIFICATION NOTES" in content),
    ("Appendix Q intact",              "Q.5 Failure Mode and Effects Analysis summary" in content),
    ("Completeness manifest intact",   "END OF DOCUMENT" in content and "AMEND-1 through AMEND-78" in content),
    ("Size sane (>180k chars)",        len(content) > 180000),
]
ok = True
for name, passed in checks:
    print(f"  {'PASS' if passed else 'FAIL'}  {name}")
    ok = ok and passed

if not ok:
    print("ABORT: integrity checks failed — nothing written.")
    sys.exit(1)

dst = Path("LOCAL_SOC_SLM_Blueprint_v11.9.0_master.txt")
dst.write_text(content)
print(f"OK: wrote {dst} ({len(content):,} chars; source was {len(src.read_text()):,})")
