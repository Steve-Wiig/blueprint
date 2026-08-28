from typing import Tuple
import argparse
import subprocess
import sys
import os
import shutil
import datetime
from datetime import timezone
import psycopg2
from psycopg2.extensions import connection as PgConnection
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading

"""
IOC Retention Manager

This module manages the retention and archival of IOC (Indicator of Compromise) 
partitions in a PostgreSQL database. It archives partitions older than 90 days 
to compressed JSONL files and drops the partitioned tables.

Environment Variables:
    ARCHIVE_BASE: Base directory for archived partitions (default: /archive/iocs)
    CMR_MOUNT: Mount point for CMR storage (default: /mnt/cmr)
    ZSTD_COMMAND: Path to zstd binary (default: zstd)
    PGPASSWORD: PostgreSQL password (alternative to password in connection string)
    RETENTION_DAYS: Retention period in days (default: 90)
"""
# Module-level defaults (no I/O at import time, per blueprint v11.7).
# Production use: call _load_config() from main() to read env vars.
# Test use: monkeypatch ARCHIVE_BASE/CMR_MOUNT/ZSTD_COMMAND on the module.
ARCHIVE_BASE = '/archive/iocs'
CMR_MOUNT = '/mnt/cmr'
ZSTD_COMMAND = 'zstd'


def _load_config() -> None:
    """Read environment variables and update module-level config globals."""
    global ARCHIVE_BASE, CMR_MOUNT, ZSTD_COMMAND
    ARCHIVE_BASE = os.environ.get('ARCHIVE_BASE', '/archive/iocs')
    CMR_MOUNT = os.environ.get('CMR_MOUNT', '/mnt/cmr')
    ZSTD_COMMAND = os.environ.get('ZSTD_COMMAND', 'zstd')


def validate_commands() -> None:
    """
    Verify that required external commands are available in PATH.
    
    Raises:
        RuntimeError: If any required command is not found.
    """
    if not shutil.which(ZSTD_COMMAND):
        raise RuntimeError(
            f"Required command '{ZSTD_COMMAND}' not found in PATH. "
            f"Set ZSTD_COMMAND environment variable to override."
        )


def check_cmr_mount() -> None:
    """
    Verify that the CMR mount point is available.
    
    Uses multiple detection methods for reliability across different mount types
    (network mounts, bind mounts, etc.).
    
    Raises:
        RuntimeError: If the CMR mount point is not mounted or accessible.
    """
    if not os.path.exists(CMR_MOUNT):
        sys.stderr.write(f"Error: CMR mount point {CMR_MOUNT} does not exist.\n")
        raise RuntimeError("CMR mount point not available")
    
    if not os.access(CMR_MOUNT, os.R_OK):
        sys.stderr.write(f"Error: CMR mount point {CMR_MOUNT} is not readable.\n")
        raise RuntimeError("CMR mount point not accessible")
    
    try:
        with open('/proc/mounts', 'r') as f:
            mounts = f.read()
            if CMR_MOUNT not in mounts:
                sys.stderr.write(f"Error: CMR mount point {CMR_MOUNT} not found in /proc/mounts.\n")
                raise RuntimeError("CMR mount point not mounted")
    except (OSError, IOError):
        pass



def _get_archive_paths(partition_name: str) -> Tuple[Path, Path]:
    """Calculate the archive directory and output file path for a partition."""
    date_part = partition_name.replace('iocs_', '')
    archive_dir = Path(ARCHIVE_BASE) / date_part[:7]
    output_file = archive_dir / f"{partition_name}.jsonl.zst"
    return archive_dir, output_file

def _stream_and_compress(conn: PgConnection, partition_name: str, output_file: Path) -> None:
    """Stream partition data from Postgres and compress it with zstd."""
    query = f"COPY (SELECT * FROM {partition_name}) TO STDOUT WITH (FORMAT JSON);"
    with open(output_file, 'wb') as f:
        zstd = subprocess.Popen([ZSTD_COMMAND, "--rm"], stdin=subprocess.PIPE, stdout=f)
        try:
            with conn.cursor() as cur:
                cur.copy_expert(query, zstd.stdin)
        finally:
            zstd.stdin.close()
            zstd.wait()
            if zstd.returncode != 0:
                raise Exception("zstd compression failed")

def _drop_partition_table(conn: PgConnection, partition_name: str) -> None:
    """Drop the partition table from the database."""
    with conn.cursor() as cur:
        cur.execute(f"DROP TABLE {partition_name};")
    conn.commit()

def archive_partition(conn: PgConnection, partition_name: str, dry_run: bool = False) -> None:
    """
    Archive a partition table to a compressed JSONL file and drop the table.

    Uses psycopg2.copy_expert for efficient streaming without subprocess overhead.

    Args:
        conn: Active PostgreSQL connection.
        partition_name: Name of the partition table to archive (format: iocs_YYYY_MM_DD).
        dry_run: If True, log actions without executing them.

    Raises:
        RuntimeError: If the archiving process fails.
        Exception: If any error occurs during archiving.
    """
    try:
        archive_dir, output_file = _get_archive_paths(partition_name)

        if dry_run:
            sys.stdout.write(f"[DRY-RUN] Would archive {partition_name} to {output_file}\n")
            sys.stdout.write(f"[DRY-RUN] Would execute: DROP TABLE {partition_name};\n")
            return

        archive_dir.mkdir(parents=True, exist_ok=True)
        _stream_and_compress(conn, partition_name, output_file)
        _drop_partition_table(conn, partition_name)
    except Exception as e:
        sys.stderr.write(f"Archive failed for {partition_name}: {e}\n")
        raise RuntimeError(f"Archive failed for {partition_name}: {e}") from e


def archive_partition_with_connection(db_url: str, partition_name: str, dry_run: bool = False) -> None:
    """
    Archive a partition using a dedicated connection (for parallel processing).
    
    Args:
        db_url: PostgreSQL connection string.
        partition_name: Name of the partition table to archive.
        dry_run: If True, log actions without executing them.
        
    Raises:
        RuntimeError: If the archiving process fails.
    """
    if dry_run:
        date_part = partition_name.replace('iocs_', '')
        archive_dir = Path(ARCHIVE_BASE) / date_part[:7]
        output_file = archive_dir / f"{partition_name}.jsonl.zst"
        sys.stdout.write(f"[DRY-RUN] Would archive {partition_name} to {output_file}\n")
        sys.stdout.write(f"[DRY-RUN] Would execute: DROP TABLE {partition_name};\n")
        return

    conn = psycopg2.connect(db_url)
    try:
        archive_partition(conn, partition_name, dry_run=False)
    finally:
        conn.close()


def run_retention(db_url: str, retention_days: int = None, max_workers: int = 4, dry_run: bool = False) -> None:
    """
    Execute the retention policy: archive and drop partitions older than the configured retention period.
    
    Uses parallel processing with a connection pool for improved performance.
    
    Args:
        db_url: PostgreSQL connection string.
        retention_days: Number of days to retain partitions. Defaults to RETENTION_DAYS env var or 90.
        max_workers: Maximum number of parallel workers for archiving (default: 4).
        dry_run: If True, log actions without executing archive or DROP TABLE
        
    Raises:
        RuntimeError: If retention logic encounters an error.
    """
    validate_commands()
    check_cmr_mount()
    try:
        conn = psycopg2.connect(db_url)
        if retention_days is None:
            retention_days = int(os.environ.get('RETENTION_DAYS', '90'))
        cutoff = datetime.datetime.now(timezone.utc) - datetime.timedelta(days=retention_days)
        
        with conn.cursor() as cur:
            cutoff_date = cutoff.date()
            cur.execute("""
                SELECT relname FROM pg_class 
                WHERE relname LIKE 'iocs_%' 
                AND relkind = 'r'
                AND relnamespace = 'public'::regnamespace
                AND to_date(substring(relname from 6), 'YYYY_MM_DD') < %s;
            """, (cutoff_date,))
            partitions = [row[0] for row in cur.fetchall()]
            
            partitions_to_archive = []
            for part in partitions:
                try:
                    part_date = datetime.datetime.strptime(part.replace('iocs_', ''), '%Y_%m_%d')
                    part_date = part_date.replace(tzinfo=timezone.utc)
                    if part_date < cutoff:
                        partitions_to_archive.append(part)
                except ValueError:
                    continue
        
        conn.close()
        
        if not partitions_to_archive:
            if dry_run:
                sys.stdout.write("[DRY-RUN] No partitions to archive.\n")
            return
        
        if dry_run:
            sys.stdout.write(f"[DRY-RUN] Would archive {len(partitions_to_archive)} partition(s): {', '.join(partitions_to_archive)}\n")
            for part in partitions_to_archive:
                date_part = part.replace('iocs_', '')
                archive_dir = Path(ARCHIVE_BASE) / date_part[:7]
                output_file = archive_dir / f"{part}.jsonl.zst"
                sys.stdout.write(f"[DRY-RUN] Would archive {part} to {output_file}\n")
                sys.stdout.write(f"[DRY-RUN] Would execute: DROP TABLE {part};\n")
            return
        
        if len(partitions_to_archive) == 1:
            archive_partition_with_connection(db_url, partitions_to_archive[0])
        else:
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                futures = {
                    executor.submit(archive_partition_with_connection, db_url, part): part
                    for part in partitions_to_archive
                }
                for future in as_completed(futures):
                    part = futures[future]
                    try:
                        future.result()
                    except Exception as e:
                        sys.stderr.write(f"Failed to archive {part}: {e}\n")
                        raise
    except Exception as e:
        sys.stderr.write(f"Retention logic error: {e}\n")
        raise RuntimeError(f"Retention logic error: {e}") from e


def main() -> None:
    """
    Main entry point for the IOC Retention Manager CLI.
    
    Parses command-line arguments and executes the retention policy.
    
    Raises:
        RuntimeError: If required database password is missing or other errors occur.
    """
    _load_config()
    parser = argparse.ArgumentParser(description="IOC Retention Manager")
    parser.add_argument("--db-url", required=True, help="Postgres connection string")
    parser.add_argument("--retention-days", type=int, default=90, help="Retention period in days (default: 90). Overrides RETENTION_DAYS env var.")
    parser.add_argument("--max-workers", type=int, default=4, help="Maximum parallel workers for archiving (default: 4)")
    parser.add_argument("--dry-run", action="store_true", help="Log actions without executing archive or DROP TABLE")
    args = parser.parse_args()
    
    run_retention(args.db_url, retention_days=args.retention_days, max_workers=args.max_workers, dry_run=args.dry_run)


if __name__ == "__main__":
    main()