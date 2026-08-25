import argparse
import subprocess
import sys
import os
import datetime
from datetime import timezone
import psycopg2
from psycopg2.extensions import connection as PgConnection
from pathlib import Path

"""
IOC Retention Manager

This module manages the retention and archival of IOC (Indicator of Compromise) 
partitions in a PostgreSQL database. It archives partitions older than 90 days 
to compressed JSONL files and drops the partitioned tables.

Environment Variables:
    ARCHIVE_BASE: Base directory for archived partitions (default: /archive/iocs)
    CMR_MOUNT: Mount point for CMR storage (default: /mnt/cmr)
    PGPASSWORD: PostgreSQL password (alternative to password in connection string)
    RETENTION_DAYS: Retention period in days (default: 90)
"""

ARCHIVE_BASE = os.environ.get('ARCHIVE_BASE', '/archive/iocs')
CMR_MOUNT = os.environ.get('CMR_MOUNT', '/mnt/cmr')


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


def archive_partition(conn: PgConnection, partition_name: str) -> None:
    """
    Archive a partition table to a compressed JSONL file and drop the table.
    
    Args:
        conn: Active PostgreSQL connection.
        partition_name: Name of the partition table to archive (format: iocs_YYYY_MM_DD).
        
    Raises:
        RuntimeError: If the archiving process fails.
        Exception: If any error occurs during archiving.
    """
    try:
        date_part = partition_name.replace('iocs_', '')
        archive_dir = Path(ARCHIVE_BASE) / date_part[:7]
        archive_dir.mkdir(parents=True, exist_ok=True)
        output_file = archive_dir / f"{partition_name}.jsonl.zst"

        query = f"COPY (SELECT * FROM {partition_name}) TO STDOUT WITH (FORMAT JSON);"
        
        with open(output_file, 'wb') as f:
            psql_cmd = ["psql", "-t", "-c", query]
            zstd_cmd = ["zstd", "--rm"]
            
            psql = subprocess.Popen(psql_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            zstd = subprocess.Popen(zstd_cmd, stdin=psql.stdout, stdout=f)
            psql.stdout.close()
            zstd.communicate()

            if psql.returncode != 0 or zstd.returncode != 0:
                raise Exception("Archiving process failed")

        with conn.cursor() as cur:
            cur.execute(f"DROP TABLE {partition_name};")
        conn.commit()
    except Exception as e:
        sys.stderr.write(f"Archive failed for {partition_name}: {e}\n")
        raise RuntimeError(f"Archive failed for {partition_name}: {e}") from e


def run_retention(db_url: str, retention_days: int = None) -> None:
    """
    Execute the retention policy: archive and drop partitions older than the configured retention period.
    
    Args:
        db_url: PostgreSQL connection string.
        retention_days: Number of days to retain partitions. Defaults to RETENTION_DAYS env var or 90.
        
    Raises:
        RuntimeError: If retention logic encounters an error.
    """
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
            
            for part in partitions:
                # Assuming partition naming convention iocs_YYYY_MM_DD
                try:
                    part_date = datetime.datetime.strptime(part.replace('iocs_', ''), '%Y_%m_%d')
                    # Make part_date timezone-aware for comparison
                    part_date = part_date.replace(tzinfo=timezone.utc)
                    if part_date < cutoff:
                        archive_partition(conn, part)
                except ValueError:
                    continue
        conn.close()
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
    parser = argparse.ArgumentParser(description="IOC Retention Manager")
    parser.add_argument("--db-url", required=True, help="Postgres connection string")
    parser.add_argument("--retention-days", type=int, default=90, help="Retention period in days (default: 90). Overrides RETENTION_DAYS env var.")
    args = parser.parse_args()
    
    run_retention(args.db_url, retention_days=args.retention_days)


if __name__ == "__main__":
    main()