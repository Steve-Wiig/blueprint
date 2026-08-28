# Blueprint Drain Cheat Sheet

## Monitor: tail -f $(ls -t overnight/run_*.log | head -1)

## Dashboard: bash overnight/dashboard.sh

## Stop: pkill -f "self_improver.py"

## Start: set -a && source .env && set +a && PYTHONUNBUFFERED=1 nohup python3 overnight/self_improver.py --drain-backlog --fixes-per-pass 4 > overnight/run_$(date +%Y%m%d_%H%M%S).log 2>&1 & echo PID $!

## Escalate deferred: python3 -c "import json; from pathlib import Path; d=json.loads(Path('overnight/fix_backlog_deferred.json').read_text()); m=json.loads(Path('overnight/needs_manual_review.json').read_text()); m.extend(d); Path('overnight/needs_manual_review.json').write_text(json.dumps(m,indent=2)); Path('overnight/fix_backlog_deferred.json').write_text('[]')"

## Retry deferred: python3 -c "import json; from pathlib import Path; d=json.loads(Path('overnight/fix_backlog_deferred.json').read_text()); b=json.loads(Path('overnight/fix_backlog.json').read_text()); b.extend(d); Path('overnight/fix_backlog.json').write_text(json.dumps(b,indent=2)); Path('overnight/fix_backlog_deferred.json').write_text('[]')"
