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
"""

ARCHIVE_BASE = os.environ.get('ARCHIVE_BASE', '/archive/iocs')
CMR_MOUNT = os.environ.get('CMR_MOUNT', '/mnt/cmr')


def check_cmr_mount() -> None:
    """
    Verify that the CMR mount point is available.
    
    Raises:
        RuntimeError: If the CMR mount point is not mounted.
    """
    if not os.path.ismount(CMR_MOUNT):
        sys.stderr.write(f"Error: CMR mount point {CMR_MOUNT} not available.\n")
        raise RuntimeError("CMR mount point not available")


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

        query = f"SELECT row_to_json(t) FROM {partition_name} t;"
        
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


def run_retention(db_url: str) -> None:
    """
    Execute the retention policy: archive and drop partitions older than 90 days.
    
    Args:
        db_url: PostgreSQL connection string.
        
    Raises:
        RuntimeError: If retention logic encounters an error.
    """
    check_cmr_mount()
    try:
        conn = psycopg2.connect(db_url)
        cutoff = datetime.datetime.now(timezone.utc) - datetime.timedelta(days=90)
        
        with conn.cursor() as cur:
            cur.execute("""
                SELECT relname FROM pg_class 
                WHERE relname LIKE 'iocs_%' 
                AND relkind = 'r';
            """)
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
    
    Parses command-line arguments, validates database credentials,
    and executes the retention policy.
    
    Raises:
        RuntimeError: If required database password is missing or other errors occur.
    """
    parser = argparse.ArgumentParser(description="IOC Retention Manager")
    parser.add_argument("--db-url", required=True, help="Postgres connection string")
    args = parser.parse_args()
    
    if not os.environ.get("PGPASSWORD") and "password=" not in args.db_url:
        raise RuntimeError("Database password not provided via PGPASSWORD or connection string")
        
    run_retention(args.db_url)


if __name__ == "__main__":
    main()