#!/usr/bin/env python3
import subprocess, json, sys, os
from pathlib import Path

ROOT = Path(__file__).parent.parent
NAS_BASE = Path("/mnt/backup-nas/soc-slm-telemetry/oracle_queue")

def h1(text): print(f"\n{'='*60}\n🔍 {text}\n{'='*60}")
def count_dir(path): return len(list(path.glob("*.json"))) if path.exists() else 0
def get_size_mb(path): return sum(f.stat().st_size for f in path.rglob("*") if f.is_file()) // (1024*1024) if path.exists() else 0

def main():
    h1("🧠 ORACLE SWARM CONSENSUS GATE")
    
    local_p = count_dir(ROOT / "overnight/oracle_queue/pending")
    nas_p = count_dir(NAS_BASE / "pending")
    local_a = count_dir(ROOT / "overnight/oracle_queue/approved")
    nas_a = count_dir(NAS_BASE / "approved")
    local_r = count_dir(ROOT / "overnight/oracle_queue/rejected")
    nas_r = count_dir(NAS_BASE / "rejected")
    local_size = get_size_mb(ROOT / "overnight/oracle_queue/pending")
    
    print(f"⏳ Pending 2-LLM Vote: {local_p + nas_p} (Local: {local_p} [{local_size}MB], NAS: {nas_p})")
    print(f"✅ Unanimously Approved: {local_a + nas_a} (Local: {local_a}, NAS: {nas_a})")
    print(f"❌ Rejected by Supreme Court: {local_r + nas_r} (Local: {local_r}, NAS: {nas_r})")

    if (local_p + nas_p) > 0:
        print("\n⚖️  Running Consensus Gate...")
        subprocess.run([sys.executable, str(ROOT / "tools/process_oracle.py")])

    h1("🧪 TEST SUITE (Post-Consensus)")
    res = subprocess.run([sys.executable, "-m", "pytest", "-q", "--tb=line", "tests/"], cwd=ROOT, capture_output=True, text=True)
    print(res.stdout)

if __name__ == "__main__":
    main()
