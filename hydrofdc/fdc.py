"""Flow duration curves (FDC): sorting, plotting positions, percentiles, annual and seasonal curves."""
import numpy as np
import pandas as pd

from .data import HydroError

# P = (m - a) / (n + 1 - 2a); Weibull is a = 0, which gives P = m / (n + 1)
POSITIONS = {"weibull": 0.0, "cunnane": 0.4, "gringorten": 0.44, "hazen": 0.5, "blom": 0.375}
Q_LEVELS = (5, 10, 25, 40, 50, 75, 90, 95)


def plotting_positions(n, method="weibull"):
    """Exceedance probability (fraction 0-1) of the m-th largest of n values."""
    try:
        a = POSITIONS[str(method).lower()]
    except KeyError:
        raise HydroError(f"Unknown plotting position '{method}'. Choose from: {', '.join(POSITIONS)}.")
    m = np.arange(1, n + 1)
    return (m - a) / (n + 1 - 2 * a)


def fdc(flows, method="weibull"):
    """Return (P, Q): exceedance fraction (ascending) and flows sorted largest to smallest. NaN ignored."""
    flows = np.asarray(flows, float)
    q = np.sort(flows[~np.isnan(flows)])[::-1]
    return plotting_positions(len(q), method), q


def flow_at(P, Q, percent):
    """Flow equalled or exceeded `percent` % of the time (linear interpolation; ends are held flat)."""
    return float(np.interp(percent / 100.0, P, Q))


def percentile_table(rec, method="weibull", levels=Q_LEVELS):
    P, Q = fdc(rec.flows, method)
    return pd.DataFrame({"Name": [f"Q{p}" for p in levels],
                         "Exceedance (%)": list(levels),
                         "Flow (m3/s)": [flow_at(P, Q, p) for p in levels]})


def annual_fdcs(rec, method="weibull", min_fraction=0.8):
    """One FDC per calendar year (years with too many missing steps are skipped)."""
    s = pd.Series(rec.flows, index=rec.dates)
    out = {}
    for year, grp in s.groupby(s.index.year):
        expected = 365 if rec.step == "daily" else 12
        if grp.notna().sum() >= min_fraction * expected:
            out[int(year)] = fdc(grp.to_numpy(), method)
    return out


def seasonal_fdc(rec, wet_months=(6, 7, 8, 9), method="weibull"):
    """FDCs for the wet season, the dry season and the whole record. Needs real dates."""
    if not rec.has_dates:
        raise HydroError("Seasonal curves need dates in the record.")
    month = rec.dates.month.to_numpy()
    wet = np.isin(month, list(wet_months))
    return {"wet": fdc(rec.flows[wet], method), "dry": fdc(rec.flows[~wet], method), "all": fdc(rec.flows, method)}
