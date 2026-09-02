#!/usr/bin/env python3
import subprocess, json, sys, os
from pathlib import Path

ROOT = Path(__file__).parent.parent
NAS_BASE = Path("/mnt/backup-nas/soc-slm-telemetry/oracle_queue")

def h1(text): print(f"\n=== {text} ===")
def run(cmd): return subprocess.run(cmd, shell=True, capture_output=True, text=True).stdout.strip()

def count_dir(path): return len(list(path.glob("*.json"))) if path.exists() else 0
def get_size_mb(path): return sum(f.stat().st_size for f in path.rglob("*") if f.is_file()) // (1024*1024) if path.exists() else 0

def main():
    print("=== 📊 UNIFIED SYSTEM DASHBOARD ===")
    
    # 1. ORACLE SWARM
    h1("🧠 ORACLE SWARM CONSENSUS GATE")
    local_p = count_dir(ROOT / "overnight/oracle_queue/pending")
    nas_p = count_dir(NAS_BASE / "pending")
    local_a = count_dir(ROOT / "overnight/oracle_queue/approved")
    local_r = count_dir(ROOT / "overnight/oracle_queue/rejected")
    local_size = get_size_mb(ROOT / "overnight/oracle_queue/pending")
    
    print(f"⏳ Pending 2-LLM Vote: {local_p + nas_p} (Local: {local_p} [{local_size}MB], NAS: {nas_p})")
    print(f"✅ Unanimously Approved: {local_a + count_dir(NAS_BASE / 'approved')}")
    print(f"❌ Rejected by Supreme Court: {local_r + count_dir(NAS_BASE / 'rejected')}")

    if (local_p + nas_p) > 0:
        print("\n⚖️  Running Consensus Gate...")
        subprocess.run([sys.executable, str(ROOT / "tools/process_oracle.py")])

    # 2. DRAIN PROCESS
    h1("🔄 DRAIN PROCESS")
    pids = run("pgrep -f 'self_improver.py'").split('\n')
    pids = [p for p in pids if p]
    if pids: print(f"   🟢 RUNNING (PIDs: {', '.join(pids)})")
    else: print("   🔴 STOPPED")
    
    # 3. QUEUE STATUS
    h1("📥 QUEUE STATUS")
    backlog = json.loads((ROOT / "overnight/fix_backlog.json").read_text()) if (ROOT / "overnight/fix_backlog.json").exists() else []
    deferred = json.loads((ROOT / "overnight/fix_backlog_deferred.json").read_text()) if (ROOT / "overnight/fix_backlog_deferred.json").exists() else []
    print(f"   Active    : {len(backlog)}")
    print(f"   Deferred  : {len(deferred)}")

    # 4. LIVE ACTIVITY
    h1("📈 LIVE ACTIVITY (Last 10 lines)")
    print(run("tail -n 10 overnight/drun_continuous.log 2>/dev/null"))
    
    # 5. DISK HEALTH
    h1("💾 DISK HEALTH (NAS Check)")
    print(run("df -h / /mnt/docker-data /mnt/backup-nas 2>/dev/null | grep -v tmpfs"))
    
    # 6. RECENT FIXES
    h1("🛠️ RECENT FIXES")
    print(run("git log -5 --oneline"))
    
    # 7. TEST SUITE
    h1("🧪 TEST SUITE (Post-Consensus)")
    res = subprocess.run([sys.executable, "-m", "pytest", "-q", "--tb=line", "tests/"], cwd=ROOT, capture_output=True, text=True)
    lines = res.stdout.strip().split('\n')
    print('\n'.join(lines[-3:]) if len(lines) >= 3 else res.stdout)

if __name__ == "__main__":
    main()
