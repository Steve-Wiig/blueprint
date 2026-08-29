# 🛠️ LOCAL-SOC-SLM Operator Cheatsheet

Quick reference for daily operations, safe manual interventions, and session management.

---

## 1. Daily Monitoring & Health Checks

| Command | Purpose |
| :--- | :--- |
| `dashboard` | **The ultimate status check.** Shows drain PID, queue sizes (Active/Deferred/Manual), disk health (Root/Docker/Backup), recent git commits, and pytest status. |
| `cat overnight/morning_report.md` | Review the summary of the last autonomous overnight run. |
| `tail -f overnight/drain.log` | Watch the live output of the currently running drain loop. |
| `git log --oneline -10` | See the last 10 actions (look for "Auto-fix" vs manual commits). |

---

## 2. Safe Manual Backlog Editing (CRITICAL)

**⚠️ NEVER edit `fix_backlog.json` or `fix_backlog_deferred.json` while the drain is running.** The drain holds the file in memory and will overwrite your changes on its next save.

**The Safe Workflow:**
1. **Lock the backlog:**  
   `lock_backlog`  
   *(Creates `overnight/backlog.lock`. The drain will see this, print a warning, and gracefully skip processing.)*
2. **Edit the file:**  
   `nano overnight/fix_backlog.json` (or your preferred editor)
3. **Commit your changes:**  
   `git add overnight/fix_backlog.json`  
   `git commit -m "manual: triage and clear deferred items"`
4. **Unlock the backlog:**  
   `unlock_backlog`  
   *(Removes the lock file. The drain will resume processing on its next pass.)*

---

## 3. Session Management & LLM Handoff

When you are running low on tokens, need to switch models, or just want to pause and resume later:

| Command | Purpose |
| :--- | :--- |
| `handoff` | **Generates a complete, LLM-ready Markdown brief.** It auto-collects: current git commit, queue sizes, disk health, recent commits, and your last 12 bash commands. |

**How to use `handoff`:**
1. Type `handoff` in the terminal.
2. Highlight and copy the entire output (from `# 🚨 LLM HANDOFF DOCUMENT` to the end).
3. Paste it into a new chat with your LLM of choice.
4. *(Optional)* Quickly edit Section 6 ("USER'S ACTIVE TASK") to add one sentence about what you were literally just doing before you switch.

---

## 4. Maintenance & Utilities

| Command | Purpose |
| :--- | :--- |
| `~/bin/backup_blueprint.sh` | Manually trigger the automated backup script. (Also runs automatically daily at 2:00 AM via cron). |
| `crontab -l` | Verify that the daily backup cron job is still scheduled. |
| `df -h` | Quick check of local and NAS disk space usage. |
| `pgrep -af "self_improver.py"` | Verify the drain process is actually running and see its exact launch arguments. |

---

## 5. Emergency Recovery

| Scenario | Action |
| :--- | :--- |
| **VM crashes into emergency mode** | Boot, comment out `/dev/sdb` in `/etc/fstab`, reboot. Once up, run `sudo mount /dev/sdb /mnt/docker-data`. |
| **Git says "empty object" or "bad object HEAD"** | Run: `find .git/objects -type f -empty -delete` then `git update-ref HEAD <last_good_commit>`. |
| **Drain is stuck or misbehaving** | Run `pkill -f "self_improver.py"`, then restart with: `nohup python3 overnight/self_improver.py --drain-backlog --fixes-per-pass 4 > overnight/drain.log 2>&1 &` |

---
*Last Updated: 2026-08-29 (v11.10 Hardened State)*
