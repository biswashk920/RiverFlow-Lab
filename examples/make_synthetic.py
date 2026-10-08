"""Make the SYNTHETIC example flow record (NOT a real river). Fixed random seed, so it is always identical.

Run from the project root:  python examples/make_synthetic.py
Shape: low dry-season flow, a monsoon-like wet season (June-September), day-to-day persistence and storm peaks.
"""
import numpy as np
import pandas as pd

rng = np.random.default_rng(42)
dates = pd.date_range("2001-01-01", "2010-12-31", freq="D")
doy = dates.dayofyear.to_numpy()
season = np.log(3.0) + 2.0 * np.exp(-((doy - 215) / 45.0) ** 2)      # log of typical flow for each day of year
x = np.zeros(len(dates))        # slowly varying noise
storm = np.zeros(len(dates))    # storm peaks that fade over a few days
wet = np.isin(dates.month, [6, 7, 8, 9])
for t in range(1, len(dates)):
    x[t] = 0.93 * x[t - 1] + rng.normal(0, 0.12)
    storm[t] = 0.80 * storm[t - 1] + (rng.exponential(0.5) if wet[t] and rng.random() < 0.03 else 0.0)
flow = np.maximum(np.exp(season + x + storm), 0.5).round(2)
out = pd.DataFrame({"date": dates.strftime("%Y-%m-%d"), "flow_m3s": flow})
with open("examples/synthetic_daily.csv", "w", newline="") as f:
    f.write("# SYNTHETIC DATA made by examples/make_synthetic.py (seed 42). Not a real river record.\n")
    out.to_csv(f, index=False)
print(f"Wrote {len(out)} rows; mean {flow.mean():.1f}, min {flow.min():.2f}, max {flow.max():.1f} m3/s")
