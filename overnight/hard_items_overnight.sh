#!/usr/bin/env bash
# Hard Items Overnight — retry deferred items with standard drain logic
set -euo pipefail

cd "$(dirname "$0")/.."
mkdir -p overnight
LOG_FILE="overnight/hard_items_$(date +%Y%m%d_%H%M%S).log"
exec > >(tee -a "$LOG_FILE") 2>&1

echo "Hard Items Overnight started: $(date)"
echo "Starting deferred count: $(python3 -c 'import json;print(len(json.load(open("overnight/fix_backlog_deferred.json"))))')"

# Step 1: Move deferred items back to main backlog for retry
echo ""
echo "========== Moving deferred items to backlog =========="
python3 << 'PYEOF'
import json
from pathlib import Path

deferred_path = Path("overnight/fix_backlog_deferred.json")
backlog_path = Path("overnight/fix_backlog.json")

deferred = json.loads(deferred_path.read_text())
backlog = json.loads(backlog_path.read_text())

print(f"Moving {len(deferred)} deferred items back to backlog for retry")
backlog.extend(deferred)
backlog_path.write_text(json.dumps(backlog, indent=2))
deferred_path.write_text("[]")
print(f"Backlog now: {len(backlog)}, Deferred cleared: 0")
PYEOF

# Step 2: Run drain using the real API
echo ""
echo "========== Hard Items Drain =========="
python3 << 'PYEOF'
import sys
import os
sys.path.insert(0, ".")

# Load API keys
from overnight.self_improver import load_state, drain_backlog_loop
from overnight.budget_manager import APIBudgetManager

state = load_state()
budget = APIBudgetManager()

# Load API keys from environment or config
api_keys = {
    "openrouter": os.getenv("OPENROUTER_API_KEY", ""),
    "gemini": os.getenv("GEMINI_API_KEY", ""),
    "groq": os.getenv("GROQ_API_KEY", ""),
}

print("Starting hard items drain (standard model selection with fallback)")
print("This will use the same model discovery/fallback logic as the overnight drain")
print("")

# Run the drain loop with 4 fixes per pass, up to 200 passes
drain_backlog_loop(api_keys, budget, state, fixes_per_pass=4, max_passes=200)

print("")
print("=" * 60)
print("Hard Items Drain Complete")
print("=" * 60)
PYEOF

echo ""
echo "Hard Items Overnight finished: $(date)"
