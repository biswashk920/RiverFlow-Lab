"""Search for a good design flow: energy vs design flow, its 'knee', and an optional cost-based optimum."""
import numpy as np

from .data import HydroError
from .economics import compute_economics
from .plant import design_from_exceedance, simulate, summarize


def design_range(rec, plant, method="weibull", n=60):
    """Design flows to try: from the turbine flow available at Q95 up to the flow available at Q5."""
    hi = design_from_exceedance(rec, plant, 5, method)
    lo = design_from_exceedance(rec, plant, 95, method)
    if hi <= 0:
        raise HydroError("After the environmental flow nothing is left for the turbine. Reduce the environmental flow.")
    if lo <= 0:
        lo = hi / n
    if hi <= lo:
        return np.array([hi])
    return np.linspace(lo, hi, n)


def sweep(rec, plant, q_grid):
    keys = ("installed_kw", "annual_energy_gwh", "capacity_factor", "flow_used_pct")
    out = {k: [] for k in keys}
    out["annual_energy_kwh"] = []
    for qd in q_grid:
        s = summarize(rec, plant, float(qd))
        for k in keys:
            out[k].append(s[k])
        out["annual_energy_kwh"].append(s["annual_energy_kwh"])
    res = {k: np.array(v) for k, v in out.items()}
    res["q_design"] = np.asarray(q_grid, float)
    return res


def find_knee(x, y):
    """Index of the knee: scale both axes to 0-1 and take the point farthest above the straight line
    joining the first and last points (where extra capacity starts to give little extra energy)."""
    x, y = np.asarray(x, float), np.asarray(y, float)
    if len(x) < 3 or x[-1] == x[0] or y[-1] == y[0]:
        return len(x) - 1
    xn = (x - x[0]) / (x[-1] - x[0])
    yn = (y - y[0]) / (y[-1] - y[0])
    return int(np.argmax(yn - xn))


def cost_optimum(sw, econ):
    """Design flow with the largest net annual benefit (revenue minus annualised cost); also min LCOE."""
    rows = [compute_economics(e, kw, econ) for e, kw in zip(sw["annual_energy_kwh"], sw["installed_kw"])]
    net = np.array([r["net_annual_benefit"] for r in rows])
    lcoe = np.array([r["lcoe_per_kwh"] for r in rows])
    return {"index_net_benefit": int(np.argmax(net)), "index_lcoe": int(np.argmin(lcoe)),
            "net_annual_benefit": net, "lcoe_per_kwh": lcoe}
