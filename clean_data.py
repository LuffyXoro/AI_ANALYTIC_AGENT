import pandas as pd

RAW_DATA_PATH = "data/raw/store_sales_data.csv"
CLEAN_DATA_PATH = "data/processed/clean_data.csv"

df = pd.read_csv(RAW_DATA_PATH)
print(df.columns.tolist())

COLUMN_MAP = {
    "Order ID": "order_id",
    "Order Date": "order_date",
    "Sales": "sales",
    "Quantity": "quantity",
    "Discount": "discount",
    "Profit": "profit",
    "Region": "region",
    "State": "state",
    "City Type": "city_type",
    "Outlet Type": "outlet_type",
    "Category of Goods": "category",
    "Sub-Category": "sub_category",
    "Segment": "segment",
    "Ship Mode": "ship_mode",
}

def clean(raw_path: str = RAW_DATA_PATH, out_path: str = CLEAN_DATA_PATH) -> pd.DataFrame:
    df = pd.read_csv(raw_path)
    df = df[list(COLUMN_MAP.keys())].rename(columns=COLUMN_MAP)
 
    df["order_date"] = pd.to_datetime(df["order_date"]).dt.date
 
    # sanity assertions -- fail loudly in case of unexpected data issues

    assert df["order_id"].is_unique, "order_id is no longer unique after load"
    assert df.isnull().sum().sum() == 0, "unexpected nulls after column selection"
 
    df.to_csv(out_path, index=False)
    print(f"Cleaned {len(df):,} rows -> {out_path}")
    return df
 
 
if __name__ == "__main__":
    clean()

 