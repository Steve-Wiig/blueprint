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

    # 1b. IMPROVEMENT LEDGER (Decision Provenance)
    h1("📊 IMPROVEMENT LEDGER")
    ledger_path = ROOT / "overnight" / "improvement_ledger.jsonl"
    if ledger_path.exists():
        import json
        from collections import Counter
        statuses = Counter()
        for line in ledger_path.read_text().strip().split("\n"):
            if line.strip():
                try:
                    entry = json.loads(line)
                    statuses[entry.get("status", "UNKNOWN")] += 1
                except:
                    pass
        total = sum(statuses.values())
        print(f"   Total decisions: {total}")
        for status in ["APPLIED", "STALE", "ESCALATED", "REJECTED"]:
            count = statuses.get(status, 0)
            icon = {"APPLIED": "🟢", "STALE": "⚪", "ESCALATED": "🟡", "REJECTED": "🔴"}.get(status, "❓")
            print(f"   {icon} {status:10s}: {count}")
    else:
        print("   No ledger entries yet.")

    # 1c. SELF-IMPROVEMENT SCORECARD
    h1("📈 SELF-IMPROVEMENT SCORECARD")
    if ledger_path.exists():
        import json
        from collections import Counter, defaultdict
        entries = []
        for line in ledger_path.read_text().strip().split("\n"):
            if line.strip():
                try:
                    entries.append(json.loads(line))
                except Exception:
                    pass
        total = len(entries)
        applied = sum(1 for e in entries if e.get("status") == "APPLIED")
        rejected = sum(1 for e in entries if e.get("status") == "REJECTED")
        rate = (applied / total) if total else 0.0
        print(f"   Total decisions: {total}")
        print(f"   Success rate:    {rate*100:.1f}% ({applied} applied / {total} actionable)")
        proven_path = ROOT / "overnight" / "proven_fixes.jsonl"
        proven_count = 0
        if proven_path.exists():
            proven_count = sum(1 for l in proven_path.read_text().strip().split("\n") if l.strip())
        print(f"   Proven patterns: {proven_count} stored")
        trend = "⏳ insufficient data"
        if total >= 10:
            half = total // 2
            def _succ(es):
                ap = sum(1 for e in es if e.get("status") == "APPLIED")
                return (ap / len(es)) if es else 0.0
            r_old = _succ(entries[:half])
            r_new = _succ(entries[half:])
            if r_new > r_old + 0.02:
                trend = "📈 improving"
            elif r_new < r_old - 0.02:
                trend = "📉 degrading"
            else:
                trend = "➡️ stable"
        print(f"   Trend:           {trend}")
        cat_stats = defaultdict(Counter)
        for e in entries:
            cat_stats[e.get("category", "unknown")][e.get("status", "?")] += 1
        print("   By category:")
        for cat in sorted(cat_stats):
            sc = cat_stats[cat]
            ap = sc.get("APPLIED", 0); rj = sc.get("REJECTED", 0)
            esc = sc.get("ESCALATED", 0)
            tot = ap + rj + esc + sc.get("STALE", 0)
            print(f"     {cat:20s}: {ap}✅ {rj}❌ {esc}🟡 ({tot} total)")
    else:
        print("   No scorecard data yet.")

    # 2. DRAIN PROCESS
    h1("🔄 DRAIN PROCESS")
    pids = run("pgrep -f 'self_improver.py'").split('\n')
    pids = [p for p in pids if p]
    if pids: print(f"   🟢 RUNNING (PIDs: {', '.join(pids)})")
    else: print("   🔴 STOPPED")
    
    # 3. QUEUE STATUS
    # 🍓 EDGE WORKER STATUS
    h1("🍓 EDGE WORKER STATUS")
    try:
        gen_status = subprocess.run(["systemctl", "is-active", "pi-generator"], capture_output=True, text=True).stdout.strip()
        gen_icon = "🟢" if gen_status == "active" else "🔴"
        print(f"   {gen_icon} Generator: {gen_status}")
        
        crit_status = subprocess.run(["systemctl", "is-active", "pi-worker"], capture_output=True, text=True).stdout.strip()
        crit_icon = "🟢" if crit_status == "active" else "🔴"
        print(f"   {crit_icon} Critic:    {crit_status}")
        
        pi_patches = ROOT / "overnight" / "pi_patches.jsonl"
        if pi_patches.exists():
            count = sum(1 for l in pi_patches.read_text().strip().split('\n') if l.strip())
            print(f"   📦 Pending Pi Patches: {count}")
        else:
            print("   📦 Pending Pi Patches: 0")
    except Exception as e:
        print(f"   ⚠️ Could not check Pi status: {e}")
    

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
