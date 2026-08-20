import argparse
import subprocess
import sys
import os
import datetime
import psycopg2
from pathlib import Path

ARCHIVE_BASE = "/archive/iocs"
CMR_MOUNT = "/mnt/cmr"

def check_cmr_mount():
    if not os.path.ismount(CMR_MOUNT):
        sys.stderr.write(f"Error: CMR mount point {CMR_MOUNT} not available.\n")
        raise RuntimeError(f"Library code called exit(3)")

def archive_partition(conn, partition_name):
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
        raise RuntimeError(f"Library code called exit(1)")

def run_retention(db_url):
    check_cmr_mount()
    try:
        conn = psycopg2.connect(db_url)
        cutoff = datetime.datetime.now() - datetime.timedelta(days=90)
        
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
                    if part_date < cutoff:
                        archive_partition(conn, part)
                except ValueError:
                    continue
        conn.close()
    except Exception as e:
        sys.stderr.write(f"Retention logic error: {e}\n")
        raise RuntimeError(f"Library code called exit(2)")

def main():
    parser = argparse.ArgumentParser(description="IOC Retention Manager")
    parser.add_argument("--db-url", required=True, help="Postgres connection string")
    args = parser.parse_args()
    
    if not os.environ.get("PGPASSWORD") and "password=" not in args.db_url:
        raise RuntimeError(f"Library code called exit(2)")
        
    run_retention(args.db_url)
    raise RuntimeError(f"Library code called exit(0)")

if __name__ == "__main__":
    main()