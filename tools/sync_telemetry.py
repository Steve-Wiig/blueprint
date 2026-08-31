#!/usr/bin/env python3
"""
LOCAL-SOC-SLM Telemetry Syncer (Stage 2)
Evacuates local telemetry outbox to durable NAS storage using rsync.
Fail-open, bounded, and strictly isolated from the remediation plane.
"""
import os
import sys
import fcntl
import subprocess
from pathlib import Path

# Configuration
PROJECT_ROOT = Path("/home/swiig/Documents/blueprint")
LOCAL_OUTBOX = PROJECT_ROOT / "overnight" / ".telemetry_buffer" / "outbox"
NAS_DEST = Path("/mnt/backup-nas/soc-slm-telemetry")
LOCK_FILE = Path("/tmp/soc-slm-telemetry-sync.lock")

def log(msg):
    print(f"[TELEMETRY SYNC] {msg}", flush=True)

def verify_nas_mount():
    """
    Crucial Guardrail: Prevent writing to root disk if NAS drops.
    Returns True only if NAS is mounted and is NOT the root filesystem.
    """
    try:
        if not NAS_DEST.exists():
            return False
            
        nas_dev = os.stat(str(NAS_DEST)).st_dev
        root_dev = os.stat("/").st_dev
        
        if nas_dev == root_dev:
            log("CRITICAL: NAS mount lost (st_dev matches root). Aborting to protect root disk.")
            return False
            
        return True
    except OSError as e:
        log(f"NAS mount verification failed: {e}")
        return False

def sync():
    # 1. Acquire Lock (Prevent concurrent syncers)
    try:
        lock_fd = os.open(str(LOCK_FILE), os.O_CREAT | os.O_RDWR, 0o600)
        fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        log("Another syncer is already running. Exiting.")
        return
    except Exception as e:
        log(f"Failed to acquire lock: {e}. Exiting.")
        return

    try:
        # 2. Check if outbox exists and has files
        if not LOCAL_OUTBOX.exists() or not any(LOCAL_OUTBOX.iterdir()):
            log("Outbox empty. Nothing to do.")
            return

        # 3. Verify NAS Mount
        if not verify_nas_mount():
            log("NAS unavailable or unmounted. Exiting safely.")
            return

        # 4. Ensure NAS destination directory exists
        try:
            NAS_DEST.mkdir(parents=True, exist_ok=True)
        except OSError as e:
            log(f"Failed to create NAS destination dir: {e}. Exiting.")
            return

        # 5. Execute rsync
        cmd = [
            "rsync", "-a", 
            "--timeout=30", 
            "--remove-source-files",
            "--no-inc-recursive",
            f"{LOCAL_OUTBOX}/", 
            f"{NAS_DEST}/"
        ]
        
        log(f"Executing: {' '.join(cmd)}")
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
            if result.returncode == 0:
                log("Sync successful.")
            elif result.returncode == 24:
                # rsync exit code 24: Partial transfer due to vanished source files
                # This is EXPECTED and SAFE because the Stage 1 writer is allowed 
                # to delete outbox files to enforce the 50MB cap.
                log("Sync completed with vanished source files (writer cap enforcement). Safe.")
            else:
                log(f"rsync failed with code {result.returncode}.")
                if result.stderr:
                    log(f"rsync stderr: {result.stderr.strip()}")
        except subprocess.TimeoutExpired:
            log("rsync timed out. NAS may be stalled. Exiting safely.")
        except Exception as e:
            log(f"rsync execution failed: {e}")

    finally:
        # Lock is released automatically when process exits or fd closes
        try:
            os.close(lock_fd)
        except:
            pass

if __name__ == "__main__":
    sync()
