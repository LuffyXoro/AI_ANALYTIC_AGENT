# kpi_engine.py, trend_engine.py, statistical.py, and
# contribution.py were all built and tested against a local pandas DataFrame
# (from transactions_with_anomalies.csv). Rather than rewriting each of them
# to speak SQL directly, this module lets you pull a DataFrame FROM Snowflake
 
import sys
import os
import pandas as pd
 
sys.path.insert(0, os.path.dirname(__file__))
from snowflake_client import get_connection
 
 
def fetch_transactions_df() -> pd.DataFrame:
   
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute("""
            SELECT order_id, order_date, sales, quantity, discount, profit,
                   region, state, city_type, outlet_type, category, sub_category,
                   segment, ship_mode
            FROM transactions
        """)
        cols = [c[0].lower() for c in cur.description]
        rows = cur.fetchall()
 
    df = pd.DataFrame(rows, columns=cols)
    df["order_date"] = pd.to_datetime(df["order_date"]).dt.date
 
    
    numeric_float_cols = ["sales", "discount", "profit"]
    for col in numeric_float_cols:
        df[col] = df[col].astype(float)
    df["quantity"] = df["quantity"].astype(int)
 
    return df
 
 
def run_query(sql: str) -> pd.DataFrame:
   
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute(sql)
        cols = [c[0].lower() for c in cur.description]
        rows = cur.fetchall()
    return pd.DataFrame(rows, columns=cols)
 
 
if __name__ == "__main__":
    print("Fetching full transactions table from Snowflake...")
    df = fetch_transactions_df()
    print(f"Fetched {len(df):,} rows, {len(df.columns)} columns")
    print(df.dtypes)
 
    expected_numeric = {"sales": "float64", "quantity": "int64", "discount": "float64", "profit": "float64"}
    for col, expected_dtype in expected_numeric.items():
        actual_dtype = str(df[col].dtype)
        status = "OK" if actual_dtype == expected_dtype else "MISMATCH"
        print(f"  dtype check: {col} = {actual_dtype} (expected {expected_dtype}) [{status}]")
 
    print(df.head(3))
 
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "analytics"))
    from analytics.kpi_engine import compute_kpis
 
    kpis = compute_kpis(df)
    print("\nKPIs computed from Snowflake-sourced DataFrame:")
    for k, v in kpis.as_dict().items():
        print(f"  {k}: {v}")
    print("Compare to  DuckDB self-test "
          "(revenue=2505921167.3, orders=99916, profit_margin=0.1497, etc.)")
 