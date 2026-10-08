"""Reading and cleaning a river flow record (daily or monthly, m3/s)."""
import re
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

HOURS_PER_YEAR = 8766.0            # average year (365.25 days)
MONTH_HOURS_NO_DATES = HOURS_PER_YEAR / 12.0
MIN_STEPS = {"daily": 30, "monthly": 12}


class HydroError(ValueError):
    """A problem the user can fix (bad data or bad input). Messages are written in plain language."""


@dataclass
class Record:
    flows: np.ndarray            # m3/s; NaN where missing or invalid
    dates: pd.DatetimeIndex
    step: str                    # "daily" or "monthly"
    hours: np.ndarray            # hours covered by each step
    has_dates: bool              # False -> dates are placeholders, so no seasons/calendar months
    messages: list = field(default_factory=list)

    @property
    def valid(self):
        return ~np.isnan(self.flows)

    @property
    def valid_hours(self):
        return float(self.hours[self.valid].sum())

    @property
    def years(self):
        return self.valid_hours / HOURS_PER_YEAR


def parse_values(text):
    """Turn pasted text (spaces, commas, semicolons or new lines) into a float array; bad tokens become NaN."""
    out = []
    for tok in re.split(r"[\s,;]+", str(text).strip()):
        if not tok:
            continue
        try:
            out.append(float(tok))
        except ValueError:
            out.append(np.nan)
    return np.array(out, dtype=float)


def detect_step(index):
    gap = pd.Series(index).diff().dt.total_seconds().median() / 86400.0
    if gap <= 1.5:
        return "daily"
    if 27 <= gap <= 32:
        return "monthly"
    raise HydroError(f"The dates are about {gap:.1f} days apart, so I cannot tell if the data are daily or "
                     "monthly. Please choose the time step yourself.")


def build_record(values, dates=None, step=None, fill="exclude"):
    """Clean the series and return a Record.

    fill="exclude": missing steps are left out of every calculation.
    fill="interpolate": gaps inside the record are filled by straight-line interpolation.
    """
    msgs = []
    vals = np.array(pd.to_numeric(pd.Series(list(values)), errors="coerce"), dtype=float)
    vals[~np.isfinite(vals)] = np.nan
    if step is not None and step not in MIN_STEPS:
        raise HydroError("Time step must be 'daily' or 'monthly'.")

    if dates is not None:
        idx = pd.DatetimeIndex(pd.to_datetime(pd.Series(list(dates)), errors="coerce"))
        if len(idx) != len(vals):
            raise HydroError(f"There are {len(vals)} flow values but {len(idx)} dates; they must match.")
        if idx.isna().any():
            row = int(np.argmax(idx.isna())) + 1
            raise HydroError(f"The date in row {row} could not be read. Use a format like 2005-07-31.")
        if step is None:
            step = detect_step(idx.sort_values())
        idx = idx.normalize()
        if step == "monthly":
            idx = idx.to_period("M").to_timestamp()
        s = pd.Series(vals, index=idx).sort_index()
        if s.index.has_duplicates:
            raise HydroError("Some dates appear more than once. Each date must appear once.")
        full = pd.date_range(s.index[0], s.index[-1], freq="D" if step == "daily" else "MS")
        if len(full) > len(s):
            msgs.append(f"{len(full) - len(s)} dates were missing from the record and are treated as missing data.")
            s = s.reindex(full)
        has_dates = True
    else:
        if step is None:
            raise HydroError("Without dates I need to know whether the values are daily or monthly.")
        idx = pd.date_range("2001-01-01", periods=len(vals), freq="D" if step == "daily" else "MS")
        s = pd.Series(vals, index=idx)
        has_dates = False
        msgs.append("No dates given: seasonal curves and calendar-month charts are not available.")

    neg = int((s < 0).sum())
    if neg:
        s[s < 0] = np.nan
        msgs.append(f"{neg} negative flow value(s) are not physical and were treated as missing.")
    zeros = int((s == 0).sum())
    if zeros:
        msgs.append(f"{zeros} zero-flow step(s) kept (the river may really run dry). Check they are not missing data.")
    n_missing = int(s.isna().sum())
    if fill == "interpolate" and n_missing:
        s = s.interpolate(method="linear", limit_area="inside")
        filled = n_missing - int(s.isna().sum())
        msgs.append(f"{filled} missing step(s) filled by straight-line interpolation.")
        n_missing = int(s.isna().sum())
    if n_missing:
        msgs.append(f"{n_missing} step(s) are missing and are excluded; annual energy is scaled to the valid record length.")

    flows = np.array(s, dtype=float)
    n_valid = int(np.sum(~np.isnan(flows)))
    if n_valid < MIN_STEPS[step]:
        raise HydroError(f"Only {n_valid} valid {step} values. I need at least {MIN_STEPS[step]} to build a "
                         "meaningful flow duration curve.")
    if np.nanmax(flows) <= 0:
        raise HydroError("All flows are zero, so there is no water to use.")

    if step == "daily":
        hours = np.full(len(s), 24.0)
    elif has_dates:
        hours = s.index.days_in_month.to_numpy(dtype=float) * 24.0
    else:
        hours = np.full(len(s), MONTH_HOURS_NO_DATES)

    rec = Record(flows=flows, dates=s.index, step=step, hours=hours, has_dates=has_dates, messages=msgs)
    if rec.years < 1:
        msgs.append("The record is shorter than one year, so seasonal effects are not captured. Treat results with great care.")
    elif rec.years < 9.9:
        msgs.append(f"The record is only {rec.years:.1f} years long. Longer records (commonly 10+ years) give more reliable estimates.")
    if step == "monthly":
        msgs.append("Monthly averages smooth out flood peaks, so energy at high design flows is likely underestimated.")
    return rec


def load_csv(path, flow_col=None, date_col=None, step=None, fill="exclude"):
    """Read a CSV. Lines starting with # are ignored. A date column is optional."""
    try:
        df = pd.read_csv(path, comment="#", skip_blank_lines=True)
    except Exception as exc:
        raise HydroError(f"I could not read the file: {exc}") from exc
    if df.empty:
        raise HydroError("The file has no data rows.")
    try:                                  # no header row: the first 'column name' is really a number
        float(str(df.columns[0]))
        df = pd.read_csv(path, comment="#", header=None)
        df.columns = [f"col{i}" for i in range(df.shape[1])]
    except ValueError:
        pass

    def pick(name, label):
        if name is None:
            return None
        if name in df.columns:
            return name
        low = {str(c).lower(): c for c in df.columns}
        if str(name).lower() in low:
            return low[str(name).lower()]
        raise HydroError(f"There is no {label} column called '{name}'. Columns found: {', '.join(map(str, df.columns))}.")

    date_col = pick(date_col, "date")
    flow_col = pick(flow_col, "flow")
    if date_col is None:
        first = df.columns[0]
        if str(first).lower() in {"date", "dates", "time", "datetime", "day", "timestamp"}:
            date_col = first
        elif df[first].dtype == object or str(df[first].dtype).startswith("str"):
            parsed = pd.to_datetime(df[first], errors="coerce")
            if parsed.notna().mean() > 0.9:
                date_col = first
    if flow_col is None:
        others = [c for c in df.columns if c != date_col]
        if not others:
            raise HydroError("I could not find a flow column.")
        flow_col = others[0]
    dates = df[date_col] if date_col is not None else None
    return build_record(df[flow_col].to_numpy(), dates=dates, step=step, fill=fill)
