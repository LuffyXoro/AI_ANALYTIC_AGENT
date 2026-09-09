# Snowflake connection helper.

import os
from contextlib import contextmanager

try:
    import snowflake.connector
except ImportError as e:
    raise ImportError(
        "snowflake-connector-python not installed. Run: "
        "pip install snowflake-connector-python --break-system-packages"
    ) from e

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass  


REQUIRED_VARS = [
    "SNOWFLAKE_ACCOUNT", "SNOWFLAKE_USER", "SNOWFLAKE_PASSWORD",
    "SNOWFLAKE_WAREHOUSE", "SNOWFLAKE_DATABASE", "SNOWFLAKE_SCHEMA",
]


def _check_env():
    missing = [v for v in REQUIRED_VARS if not os.environ.get(v)]
    if missing:
        raise EnvironmentError(
            f"Missing required environment variables: {missing}. "
            f"Copy .env.example to .env and fill in your credentials."
        )


@contextmanager
def get_connection():
    _check_env()
    conn = snowflake.connector.connect(
        account=os.environ["SNOWFLAKE_ACCOUNT"],
        user=os.environ["SNOWFLAKE_USER"],
        password=os.environ["SNOWFLAKE_PASSWORD"],
        warehouse=os.environ["SNOWFLAKE_WAREHOUSE"],
        database=os.environ["SNOWFLAKE_DATABASE"],
        schema=os.environ["SNOWFLAKE_SCHEMA"],
        role=os.environ.get("SNOWFLAKE_ROLE"),
    )
    try:
        yield conn
    finally:
        conn.close()


def test_connection():
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute("SELECT CURRENT_VERSION(), CURRENT_WAREHOUSE(), CURRENT_DATABASE(), CURRENT_SCHEMA()")
        version, wh, db, schema = cur.fetchone()
        print(f"Connected. Snowflake version={version}, warehouse={wh}, database={db}, schema={schema}")


if __name__ == "__main__":
    test_connection()