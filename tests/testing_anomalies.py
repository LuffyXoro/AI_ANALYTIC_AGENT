import pandas as pd

before = pd.read_csv('data/processed/clean_data.csv', parse_dates=['order_date'])
after = pd.read_csv('data/processed/transactions_with_anomalies.csv', parse_dates=['order_date'])

W0, W1 = '2022-06-01', '2022-06-14'

def daily_company(df):
    return df.groupby(df['order_date'])['sales'].sum()

def window_avg(series, start, end):
    return series.loc[start:end].mean()

b_daily = daily_company(before)
a_daily = daily_company(after)

baseline_daily_mean = before[before['order_date'] < W0]['sales'].groupby(before['order_date']).sum().mean() \
    if False else b_daily[(b_daily.index < W0)].mean()

print("=== COMPANY-WIDE ===")
print("Baseline daily avg revenue (pre-window):", round(baseline_daily_mean))
print("Window daily avg revenue BEFORE injection:", round(window_avg(b_daily, W0, W1)))
print("Window daily avg revenue AFTER injection:", round(window_avg(a_daily, W0, W1)))
pct_drop = 100 * (1 - window_avg(a_daily, W0, W1) / window_avg(b_daily, W0, W1))
print(f"Company-wide revenue drop during window: {pct_drop:.1f}%")

print("\n=== SOUTH REGION ===")
south_before = before[before['region']=='South']
south_after = after[after['region']=='South']
sb_daily = daily_company(south_before)
sa_daily = daily_company(south_after)
south_drop = 100 * (1 - window_avg(sa_daily, W0, W1) / window_avg(sb_daily, W0, W1))
print(f"South region revenue drop during window: {south_drop:.1f}%")

print("\n=== ORDERS vs AOV (checking volume-driven story holds) ===")
w_before = before[before['order_date'].between(W0, W1)]
w_after = after[after['order_date'].between(W0, W1)]
print("Orders before:", len(w_before), " after:", len(w_after), f" ({100*(1-len(w_after)/len(w_before)):.1f}% drop)")
print("AOV before: %.0f  after: %.0f  (%.1f%% change)" % (
    w_before['sales'].mean(), w_after['sales'].mean(),
    100*(w_after['sales'].mean()/w_before['sales'].mean()-1)
))

print("ROOT CAUSE: category contribution within South during window ===")
sw_before = south_before[south_before['order_date'].between(W0, W1)].groupby('category')['sales'].sum()
sw_after = south_after[south_after['order_date'].between(W0, W1)].groupby('category')['sales'].sum()
contrib = pd.DataFrame({'before': sw_before, 'after': sw_after})
contrib['drop'] = contrib['before'] - contrib['after']
contrib['pct_of_total_drop'] = 100 * contrib['drop'] / contrib['drop'].sum()
contrib['pct_drop_own'] = 100 * (1 - contrib['after']/contrib['before'])
print(contrib.round(1))


df = pd.read_csv('data/processed/clean_data.csv', parse_dates=['order_date'])

for region, cat in [('North','Furniture'), ('West','Household Items')]:
    sub = df[(df['region']==region) & (df['category']==cat)]
    print(f"{region} + {cat}: {len(sub)} rows, avg discount={sub['discount'].mean():.2f}, avg sales={sub['sales'].mean():.0f}")

# derive implied margin per row (sanity check it's stable ~0.10-0.30)
m = df['profit'] / (df['sales'] * (1 - df['discount']))
print("\nImplied margin overall: mean=%.3f min=%.3f max=%.3f" % (m.mean(), m.min(), m.max()))