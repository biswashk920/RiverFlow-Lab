"""Figures 1-4 (plus an optional seasonal figure). Colours are always backed up by labels and hatching."""
import matplotlib.pyplot as plt
import numpy as np

from .data import HydroError
from .fdc import annual_fdcs, fdc, seasonal_fdc
from .optimum import cost_optimum, design_range, find_knee, sweep
from .plant import flow_split, installed_kw, power_kw, simulate
from .report import MONTHS, monthly_energy

C_ENV, C_USE, C_SPILL = "#0072B2", "#E69F00", "#BDBDBD"
XLAB = "Exceedance probability (% of time the flow is equalled or exceeded)"


def figure1(rec, plant, qd, method="weibull", log=False, show_years=True):
    P, Q = fdc(rec.flows, method)
    env, turb, spill = flow_split(Q, plant, qd)
    p = P * 100
    pos = Q[Q > 0]
    base = float(pos.min()) * 0.7 if log and len(pos) else 0.0
    b0 = np.full_like(Q, base)
    e, u, top = np.maximum(env, base), np.maximum(env + turb, base), np.maximum(Q, base)
    fig, ax = plt.subplots(figsize=(9, 5.5))
    if show_years and rec.has_dates:
        for i, (_, (py, qy)) in enumerate(annual_fdcs(rec, method).items()):
            ax.plot(py * 100, qy, color="0.6", lw=0.6, alpha=0.6, label="Individual years" if i == 0 else None)
    kw = dict(edgecolor="white", linewidth=0)
    ax.fill_between(p, b0, e, color=C_ENV, alpha=0.8, hatch="..", label="Environmental flow (stays in river)", **kw)
    ax.fill_between(p, e, u, color=C_USE, alpha=0.85, label="Turbine flow (used)", **kw)
    ax.fill_between(p, u, top, color=C_SPILL, alpha=0.7, hatch="//", label="Spill / unused flow", **kw)
    ax.plot(p, Q, color="black", lw=1.6, label=f"Flow duration curve ({method.title()})")
    rq = plant.river_flow_at_design(qd)
    if np.isfinite(rq):
        pct = 100 * float(np.interp(rq, Q[::-1], P[::-1]))
        ax.axhline(rq, color="black", ls="--", lw=1)
        ax.text(99, rq, f" Design flow {qd:.2f} m3/s through turbine\n (river flow {rq:.2f} m3/s, exceeded {pct:.0f}% of time)",
                ha="right", va="bottom", fontsize=8)
    if log:
        ax.set_yscale("log")
        ax.set_ylim(bottom=base)
        ax.text(0.01, 0.02, "Log scale: shaded areas are not proportional to water volume", transform=ax.transAxes,
                fontsize=8, bbox=dict(facecolor="white", alpha=0.8, edgecolor="none"))
    ax.set_xlim(0, 100)
    ax.set_xlabel(XLAB)
    ax.set_ylabel("River flow (m3/s)")
    ax.set_title("Figure 1: Flow duration curve with used and unused flow")
    ax.grid(alpha=0.3)
    ax.legend(loc="upper right", fontsize=8, bbox_to_anchor=(1, 0.86))
    fig.tight_layout()
    return fig


def figure_seasonal(rec, wet_months=(6, 7, 8, 9), method="weibull", log=False):
    curves = seasonal_fdc(rec, wet_months, method)
    names = {"all": ("Whole record", "black", "-"), "wet": ("Wet season", C_USE, "-"), "dry": ("Dry season", C_ENV, "--")}
    fig, ax = plt.subplots(figsize=(9, 5))
    for k, (label, colour, ls) in names.items():
        P, Q = curves[k]
        ax.plot(P * 100, Q, color=colour, ls=ls, lw=1.8, label=label)
    if log:
        ax.set_yscale("log")
    ax.set_xlabel(XLAB)
    ax.set_ylabel("River flow (m3/s)")
    months = ", ".join(str(m) for m in wet_months)
    ax.set_title(f"Seasonal flow duration curves (wet-season months: {months})")
    ax.grid(alpha=0.3)
    ax.legend()
    fig.tight_layout()
    return fig


def figure2(rec, plant, qd, method="weibull"):
    P, Q = fdc(rec.flows, method)
    _, turb, _ = flow_split(Q, plant, qd)
    pw, _ = power_kw(plant, turb, qd)
    cap = installed_kw(plant, qd)
    fig, ax = plt.subplots(figsize=(9, 5))
    ax.fill_between(P * 100, 0, pw, color=C_USE, alpha=0.6, label="Power (before availability reduction)")
    ax.plot(P * 100, pw, color="black", lw=1.5)
    ax.axhline(cap, color="black", ls="--", label=f"Installed capacity {cap:,.0f} kW")
    ax.set_xlim(0, 100)
    ax.set_ylim(bottom=0)
    ax.set_xlabel(XLAB)
    ax.set_ylabel("Power (kW)")
    ax.set_title("Figure 2: Power duration curve")
    ax.grid(alpha=0.3)
    ax.legend(loc="upper right")
    fig.tight_layout()
    return fig


def figure3(rec, plant, qd, method="weibull", econ=None, sw=None):
    sw = sw or sweep(rec, plant, design_range(rec, plant, method))
    q, gwh, cf = sw["q_design"], sw["annual_energy_gwh"], 100 * sw["capacity_factor"]
    fig, ax = plt.subplots(figsize=(9, 5))
    ax2 = ax.twinx()
    l1 = ax.plot(q, gwh, color=C_USE, lw=2, marker=".", label="Annual energy (GWh)")
    l2 = ax2.plot(q, cf, color=C_ENV, lw=2, ls="--", label="Capacity factor (%)")
    ax.axvline(qd, color="black", ls=":", label=f"Chosen design flow {qd:.2f} m3/s")
    k = find_knee(q, gwh)
    ax.plot(q[k], gwh[k], "D", color="black", ms=9, label=f"Knee: {q[k]:.2f} m3/s")
    if econ:
        i = cost_optimum(sw, econ)["index_net_benefit"]
        ax.plot(q[i], gwh[i], "s", color="red", ms=9, label=f"Cost-based optimum: {q[i]:.2f} m3/s")
    ax.set_xlabel("Design flow through turbine (m3/s)")
    ax.set_ylabel("Average annual energy (GWh)")
    ax2.set_ylabel("Capacity factor (%)")
    ax.set_title("Figure 3: Energy and capacity factor vs design flow")
    ax.grid(alpha=0.3)
    handles, labels = ax.get_legend_handles_labels()
    ax.legend(handles + l2, labels + [l.get_label() for l in l2], loc="lower right", fontsize=8)
    fig.tight_layout()
    return fig


def figure4(rec, plant, qd):
    if not rec.has_dates:
        raise HydroError("The monthly energy chart needs dates in the record.")
    me = monthly_energy(rec, simulate(rec, plant, qd))
    fig, ax = plt.subplots(figsize=(9, 5))
    bars = ax.bar(MONTHS, me.to_numpy(), color=C_USE, edgecolor="black", hatch="//")
    ax.bar_label(bars, fmt="%.0f", fontsize=8)
    ax.set_ylabel("Average energy (MWh per month)")
    ax.set_title("Figure 4: Average energy by calendar month")
    ax.grid(axis="y", alpha=0.3)
    fig.tight_layout()
    return fig
