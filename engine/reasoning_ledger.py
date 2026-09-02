"""
engine/reasoning_ledger.py
--------------------------
The Black Box Flight Recorder. Records every LLM prompt and raw response.
Writes to local buffer (fail-safe) AND directly to NAS if mounted.
"""
import json
import time
import os
from pathlib import Path

ROOT = Path(__file__).parent.parent
NAS_DIR = Path("/mnt/backup-nas/soc-slm-telemetry/reasoning")
BUFFER_DIR = ROOT / "overnight" / ".reasoning_buffer"

def record_interaction(stage: str, prompt: str, raw_response: str, model: str = "unknown"):
    """Appends an LLM interaction to the flight recorder."""
    BUFFER_DIR.mkdir(parents=True, exist_ok=True)
    local_file = BUFFER_DIR / "current.jsonl"
    
    event = {
        "ts": time.time(),
        "stage": stage,
        "model": model,
        "prompt_chars": len(prompt),
        "response_chars": len(raw_response) if raw_response else 0,
        "prompt_preview": prompt[:500] + "..." if len(prompt) > 500 else prompt,
        "response_preview": raw_response[:500] + "..." if raw_response and len(raw_response) > 500 else raw_response
    }
    
    # 1. Always write to local buffer (fail-safe)
    try:
        with open(local_file, "a") as f:
            f.write(json.dumps(event) + "\n")
    except Exception:
        pass

    # 2. NAS Guardrail: Check st_dev to ensure NAS is actually mounted
    try:
        nas_stat = os.stat("/mnt/backup-nas")
        root_stat = os.stat("/")
        if nas_stat.st_dev != root_stat.st_dev:
            # NAS is mounted! Write directly to the NAS for real-time observability
            NAS_DIR.mkdir(parents=True, exist_ok=True)
            nas_file = NAS_DIR / "reasoning.jsonl"
            with open(nas_file, "a") as f:
                f.write(json.dumps(event) + "\n")
    except Exception:
        pass # Fail-open: NAS is asleep/unmounted, data is safe in local buffer
