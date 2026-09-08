import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from snowflake_client import get_connection

CSV_PATH = "data/processed/transactions_with_anomalies.csv"
STAGE_NAME = "transactions_stage"
TABLE_NAME = "transactions"


def load(csv_path: str = CSV_PATH):
    with get_connection() as conn:
        cur = conn.cursor()

        print("Creating file format...")
        cur.execute("""
            CREATE OR REPLACE FILE FORMAT csv_format
            TYPE = 'CSV'
            FIELD_DELIMITER = ','
            SKIP_HEADER = 1
            FIELD_OPTIONALLY_ENCLOSED_BY = '"'
            NULL_IF = ('')
            EMPTY_FIELD_AS_NULL = TRUE
        """)

        print(f"Creating internal stage '{STAGE_NAME}'...")
        cur.execute(f"CREATE OR REPLACE STAGE {STAGE_NAME} FILE_FORMAT = csv_format")

        abs_path = os.path.abspath(csv_path)
     
        uri_path = abs_path.replace("\\", "/")
        print(f"Uploading {abs_path} to stage...")
    
        put_command = f"PUT 'file://{uri_path}' @{STAGE_NAME} AUTO_COMPRESS=TRUE OVERWRITE=TRUE"
        cur.execute(put_command)
        put_result = cur.fetchall()
        print("PUT result:", put_result)

        print(f"Truncating {TABLE_NAME} before load (safe to re-run)...")
        cur.execute(f"TRUNCATE TABLE {TABLE_NAME}")

        print("Running COPY INTO...")
        cur.execute(f"""
            COPY INTO {TABLE_NAME}
            FROM @{STAGE_NAME}
            FILE_FORMAT = (FORMAT_NAME = csv_format)
            ON_ERROR = 'ABORT_STATEMENT'
        """)
        copy_result = cur.fetchall()
        print("COPY INTO result:", copy_result)

        print("Verifying row count...")
        cur.execute(f"SELECT COUNT(*) FROM {TABLE_NAME}")
        count = cur.fetchone()[0]
        print(f"Rows loaded: {count:,}")

        expected = sum(1 for _ in open(csv_path)) - 1  # minus header
        if count != expected:
            print(f"WARNING: expected {expected:,} rows (from CSV line count) but table has {count:,}. "
                  f"Check the COPY INTO result above for row-level errors.")
        else:
            print("Row count matches source CSV exactly.")

        cur.execute(f"SELECT MIN(order_date), MAX(order_date) FROM {TABLE_NAME}")
        min_date, max_date = cur.fetchone()
        print(f"Date range in Snowflake: {min_date} to {max_date}")


if __name__ == "__main__":
    load()