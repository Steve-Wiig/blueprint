
---

## 🩺 6. Deep Diagnostics (The Truth)
*Understand the exact state of the machine without modifying it.*

**Run the System Doctor** (Full Dashboard: Queues, Budget, Defeat Ledger, NAS):
```bash
python3 tools/system_doctor.py

---

## 🩺 6. Deep Diagnostics (The Truth)
*Understand the exact state of the machine without modifying it.*

**Run the System Doctor** (Full Dashboard: Queues, Budget, Defeat Ledger, NAS):
```bash
python3 tools/system_doctor.py
```
**Manually Quarantine Broken TDD Tests** (If pytest collection crashes):
```bash
python3 tools/sanitize_tests.py
```
**Interrogate the Flight Recorder** (Read what the AI was thinking):
```bash
# See the last 10 raw prompts and responses
python3 tools/audit.py --last 10
```
