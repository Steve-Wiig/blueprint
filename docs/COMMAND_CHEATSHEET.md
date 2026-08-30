# 🛠️ Blueprint Drain Cheat Sheet

## 📊 MONITORING
**Quick Dashboard:** 
```bash
dashboard
```

**Live Log (Standard Run):** 
```bash
tail -f overnight/drun_latest.log
```

**Live Log (Large Models Run):** 
```bash
tail -f overnight/large_model_drain.log
```
*(Press Ctrl+C to exit live tail)*

## 🔄 DRAIN LOOP CONTROL
**Start (Standard):**
```bash
cd /home/swiig/Documents/blueprint
PYTHONUNBUFFERED=1 nohup python3 overnight/self_improver.py --drain-backlog --fixes-per-pass 4 > overnight/drun_latest.log 2>&1 &
echo "Loop started with PID: $!"
```

**Start (Large Models Only — Nemotron 340B, Qwen 32B/72B):**
```bash
cd /home/swiig/Documents/blueprint
PYTHONUNBUFFERED=1 nohup ~/bin/drain_large_models > overnight/large_model_drain.log 2>&1 &
echo "Large model drain started with PID: $!"
```
*(Note: Uses in-memory override only; source files remain untouched. 5 retries, 10s rate limit sleep.)*

**Stop (Kills any running drain process):**
```bash
pkill -f "drain_large_models|self_improver"
```

**Pause/Resume:**
- Lock backlog (pause autonomous fixes): `lock_backlog`
- Unlock backlog (resume autonomous fixes): `unlock_backlog`

## 📥 QUEUE MANAGEMENT
**Requeue deferred items (give them another whack):**
```bash
requeue_deferred
```

**Escalate all deferred → manual review:**
```bash
python3 -c "import json; from pathlib import Path; d=json.loads(Path('overnight/fix_backlog_deferred.json').read_text()); m=json.loads(Path('overnight/needs_manual_review.json').read_text()); m.extend(d); Path('overnight/needs_manual_review.json').write_text(json.dumps(m,indent=2)); Path('overnight/fix_backlog_deferred.json').write_text('[]')"
```

## 📝 CONTEXT & HANDOFF
**Generate LLM handoff document:**
```bash
handoff
```

## 🧪 TESTING & REVIEW
**Full test suite:** 
```bash
python3 -m pytest tests/ -q --tb=no
```

**Check what the AI changed (before committing):**
```bash
git status --short
git diff
```

## 💾 BACKUP & INFRASTRUCTURE
**Manual backup:** 
```bash
~/bin/backup_blueprint.sh
```

**Check disk health:** 
```bash
df -h | grep -E "/$|docker-data|backup-nas"
```

## 🔧 TROUBLESHOOTING
**Git corruption fix (after power/network crash):**
```bash
find .git/objects -type f -empty -delete
git update-ref HEAD <last_good_commit>
```

**NAS mount check:** 
```bash
mount | grep -E "docker-data|backup-nas"
```
