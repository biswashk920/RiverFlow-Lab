"""Tables (pandas DataFrames) that can be printed or saved as CSV."""
import os

import numpy as np
import pandas as pd

from .economics import compute_economics
from .plant import simulate, summarize

MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def monthly_energy(rec, sim):
    """Average energy (MWh) produced in each calendar month, averaged over the years in the record."""
    s = pd.Series(sim.energy_kwh, index=rec.dates)
    per_month = s.groupby([s.index.year, s.index.month]).sum()
    avg = per_month.groupby(level=1).mean().reindex(range(1, 13), fill_value=0.0)
    return avg / 1000.0


def summary_frame(s, econ_result=None):
    rows = [
        ("Net head", s["net_head"], "m"),
        ("Design flow (through turbine)", s["q_design"], "m3/s"),
        ("Minimum operating flow", s["q_min"], "m3/s"),
        ("Installed capacity", s["installed_kw"], "kW"),
        ("Average annual energy", s["annual_energy_gwh"], "GWh/year"),
        ("Capacity factor", 100 * s["capacity_factor"], "%"),
        ("Flow volume used by turbine", s["flow_used_pct"], "% of river volume"),
        ("Time generating", s["running_time_pct"], "% of record"),
        ("Energy compared with 'use all flow up to design flow'", s["energy_vs_ideal_pct"], "%"),
        ("Valid record length", s["years"], "years"),
    ]
    if econ_result:
        e = econ_result
        rows += [
            ("Capital cost", e["capex"], "currency"),
            ("Annual revenue", e["annual_revenue"], "currency/year"),
            ("Annual O&M", e["annual_om"], "currency/year"),
            ("Simple payback (capital / (revenue - O&M))", e["simple_payback_years"], "years"),
            ("LCOE (pre-feasibility estimate)", e["lcoe_per_kwh"], "currency/kWh"),
            ("Net annual benefit (revenue - annualised cost)", e["net_annual_benefit"], "currency/year"),
        ]
    return pd.DataFrame(rows, columns=["Item", "Value", "Unit"])


def comparison_table(rec, plant, designs, econ=None):
    """One row per design flow. `designs` is a list of (label, design flow in m3/s)."""
    rows = []
    for label, qd in designs:
        s = summarize(rec, plant, qd)
        row = {"Design": label, "Design flow (m3/s)": qd, "Installed capacity (kW)": s["installed_kw"],
               "Annual energy (GWh)": s["annual_energy_gwh"], "Capacity factor (%)": 100 * s["capacity_factor"],
               "Flow used (%)": s["flow_used_pct"]}
        if econ:
            e = compute_economics(s["annual_energy_kwh"], s["installed_kw"], econ)
            row.update({"Capital cost": e["capex"], "Annual revenue": e["annual_revenue"],
                        "Simple payback (years)": e["simple_payback_years"], "LCOE (per kWh)": e["lcoe_per_kwh"]})
        rows.append(row)
    return pd.DataFrame(rows)


def monthly_frame(rec, plant, q_design):
    me = monthly_energy(rec, simulate(rec, plant, q_design))
    return pd.DataFrame({"Month": MONTHS,
                         "Average energy (MWh)": me.to_numpy()})


def save_tables(out_dir, tables):
    os.makedirs(out_dir, exist_ok=True)
    paths = []
    for name, df in tables.items():
        path = os.path.join(out_dir, f"table_{name}.csv")
        df.to_csv(path, index=False)
        paths.append(path)
    return paths
