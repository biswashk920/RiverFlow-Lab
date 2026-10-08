"""Very simple economics. PRE-FEASIBILITY ESTIMATE ONLY: no construction period, degradation, tax,
inflation, financing structure or penstock/civil cost scaling."""
from dataclasses import dataclass

from .data import HydroError


@dataclass
class Economics:
    tariff: float                 # price per kWh
    capex_per_kw: float           # capital cost per kW installed
    om_pct: float = 2.0           # yearly O&M as % of capital cost
    rate_pct: float = 10.0        # discount rate, %
    life_years: float = 30.0

    def __post_init__(self):
        if self.tariff < 0 or self.capex_per_kw < 0 or self.om_pct < 0 or self.rate_pct < 0:
            raise HydroError("Tariff, costs and discount rate cannot be negative.")
        if self.life_years <= 0:
            raise HydroError("Project life must be greater than zero.")


def crf(rate_pct, life):
    """Capital recovery factor: share of capital cost paid back each year."""
    r = rate_pct / 100.0
    if r == 0:
        return 1.0 / life
    return r * (1 + r) ** life / ((1 + r) ** life - 1)


def compute_economics(annual_kwh, installed_kw, econ):
    capex = installed_kw * econ.capex_per_kw
    revenue = annual_kwh * econ.tariff
    om = capex * econ.om_pct / 100.0
    net = revenue - om
    ann_cost = capex * crf(econ.rate_pct, econ.life_years) + om
    return {
        "capex": capex,
        "annual_revenue": revenue,
        "annual_om": om,
        "annual_net_revenue": net,
        "simple_payback_years": capex / net if net > 0 else float("inf"),
        "crf": crf(econ.rate_pct, econ.life_years),
        "annualised_cost": ann_cost,
        "lcoe_per_kwh": ann_cost / annual_kwh if annual_kwh > 0 else float("inf"),
        "net_annual_benefit": revenue - ann_cost,
    }
