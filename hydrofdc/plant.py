"""Plant model: head, environmental flow, flow split, power and energy for every time step.

Fixed head (no tailwater or head change with flow), no storage: water not used is spilled.
"""
from dataclasses import dataclass

import numpy as np

from .data import HydroError, HOURS_PER_YEAR
from .fdc import fdc, flow_at
from .turbines import TURBINES, constant_turbine


@dataclass
class Plant:
    gross_head: float = None          # m
    head_loss_pct: float = 5.0        # % of gross head
    net_head_value: float = None      # m; if given it replaces gross head minus losses
    turbine: str = "francis"          # pelton, francis, kaplan, crossflow
    const_eta: float = None           # if given: constant turbine efficiency instead of a curve
    min_flow: float = None            # m3/s; if None: turbine default fraction of design flow
    eta_gen: float = 0.97
    eta_trans: float = 0.99
    availability_pct: float = 95.0    # % of the year the plant is available
    rho: float = 1000.0               # kg/m3
    g: float = 9.81                   # m/s2
    env_mode: str = "percent"         # "percent" of river flow or "fixed" m3/s
    env_value: float = 10.0

    def __post_init__(self):
        if self.net_head_value is None and self.gross_head is None:
            raise HydroError("Please give a gross head or a net head (in metres).")
        if self.net_head <= 0:
            raise HydroError("Net head must be greater than zero. Check gross head and head loss.")
        if not 0 <= self.head_loss_pct < 100:
            raise HydroError("Head loss must be between 0 and 100 % of gross head.")
        for name, val in (("Generator", self.eta_gen), ("Transformer", self.eta_trans)):
            if not 0 < val <= 1:
                raise HydroError(f"{name} efficiency must be between 0 and 1 (for example 0.97).")
        if self.const_eta is not None and not 0 < self.const_eta <= 1:
            raise HydroError("Constant turbine efficiency must be between 0 and 1.")
        if not 0 <= self.availability_pct <= 100:
            raise HydroError("Availability must be between 0 and 100 %.")
        if self.env_mode not in ("percent", "fixed"):
            raise HydroError("Environmental flow mode must be 'percent' or 'fixed'.")
        if self.env_value < 0 or (self.env_mode == "percent" and self.env_value > 100):
            raise HydroError("Environmental flow must be 0 or more (and at most 100 % if given as a percentage).")
        if self.const_eta is None and self.turbine not in TURBINES:
            raise HydroError(f"Unknown turbine '{self.turbine}'. Choose from: {', '.join(TURBINES)}.")
        if self.min_flow is not None and self.min_flow < 0:
            raise HydroError("Minimum operating flow cannot be negative.")
        if self.rho <= 0 or self.g <= 0:
            raise HydroError("Water density and gravity must be positive.")

    @property
    def net_head(self):
        if self.net_head_value is not None:
            return float(self.net_head_value)
        return float(self.gross_head) * (1 - self.head_loss_pct / 100.0)

    @property
    def turbine_model(self):
        return constant_turbine(self.const_eta) if self.const_eta is not None else TURBINES[self.turbine]

    @property
    def availability(self):
        return self.availability_pct / 100.0

    def env_request(self, q):
        q = np.asarray(q, float)
        if self.env_mode == "percent":
            return q * self.env_value / 100.0
        return np.full_like(q, self.env_value)

    def min_flow_for(self, q_design):
        if self.min_flow is not None:
            return float(self.min_flow)
        return self.turbine_model.min_frac * q_design

    def river_flow_at_design(self, q_design):
        """River flow at which the turbine just reaches its design flow."""
        if self.env_mode == "percent":
            return float("inf") if self.env_value >= 100 else q_design / (1 - self.env_value / 100.0)
        return q_design + self.env_value


def flow_split(q, plant, q_design):
    """Split river flow into environmental, turbine and spill flows (m3/s). They add up to the river flow.
    NaN (missing) stays NaN."""
    q = np.asarray(q, float)
    env = np.minimum(q, plant.env_request(q))
    avail = q - env
    turb = np.minimum(avail, q_design)
    turb = np.where(turb < plant.min_flow_for(q_design), 0.0, turb)
    return env, turb, avail - turb


def power_kw(plant, q_turb, q_design):
    """Electrical power (kW) and total efficiency for turbine flow q_turb. P = eta * rho * g * Q * H."""
    q_turb = np.asarray(q_turb, float)
    frac = q_turb / q_design if q_design > 0 else np.zeros_like(q_turb)
    eta = plant.turbine_model.efficiency(frac) * plant.eta_gen * plant.eta_trans
    eta = np.where(q_turb > 0, eta, 0.0)
    return eta * plant.rho * plant.g * q_turb * plant.net_head / 1000.0, eta


def installed_kw(plant, q_design):
    eta = float(plant.turbine_model.efficiency(1.0)) * plant.eta_gen * plant.eta_trans
    return eta * plant.rho * plant.g * q_design * plant.net_head / 1000.0


@dataclass
class Sim:
    q: np.ndarray
    env: np.ndarray
    turb: np.ndarray
    spill: np.ndarray
    eta: np.ndarray
    power_kw: np.ndarray
    energy_kwh: np.ndarray            # per step, includes availability
    cum_energy_kwh: np.ndarray
    valid: np.ndarray
    installed_kw: float
    q_design: float
    q_min: float


def simulate(rec, plant, q_design):
    """State of the plant at every time step (this is what the browser animation replays)."""
    q = rec.flows
    env, turb, spill = flow_split(q, plant, q_design)
    p, eta = power_kw(plant, turb, q_design)
    energy = np.nan_to_num(p * rec.hours * plant.availability, nan=0.0)
    return Sim(q=q, env=env, turb=turb, spill=spill, eta=eta, power_kw=p, energy_kwh=energy,
               cum_energy_kwh=np.cumsum(energy), valid=rec.valid,
               installed_kw=installed_kw(plant, q_design), q_design=float(q_design),
               q_min=plant.min_flow_for(q_design))


def summarize(rec, plant, q_design, sim=None):
    sim = sim or simulate(rec, plant, q_design)
    hours = rec.hours[rec.valid]
    total = float(sim.cum_energy_kwh[-1]) if len(sim.cum_energy_kwh) else 0.0   # running sum, same as the animation
    vh = float(hours.sum())
    years = vh / HOURS_PER_YEAR
    river_vol = float(np.sum(sim.q[rec.valid] * hours))
    turb_vol = float(np.sum(sim.turb[rec.valid] * hours))
    q_ideal = np.minimum(sim.q[rec.valid], q_design)
    ideal = (float(np.sum(q_ideal * hours)) * plant.rho * plant.g * plant.net_head / 1000.0
             * plant.turbine_model.eta_max * plant.eta_gen * plant.eta_trans * plant.availability)
    cap = sim.installed_kw
    return {
        "q_design": float(q_design), "q_min": sim.q_min, "net_head": plant.net_head,
        "installed_kw": cap, "total_energy_kwh": total, "valid_hours": vh, "years": years,
        "annual_energy_kwh": total / years if years > 0 else 0.0,
        "annual_energy_gwh": total / years / 1e6 if years > 0 else 0.0,
        "capacity_factor": total / (cap * vh) if cap > 0 and vh > 0 else 0.0,
        "flow_used_pct": 100.0 * turb_vol / river_vol if river_vol > 0 else 0.0,
        "running_time_pct": 100.0 * float(np.sum(hours[sim.turb[rec.valid] > 0])) / vh if vh > 0 else 0.0,
        "ideal_energy_kwh": ideal,
        "energy_vs_ideal_pct": 100.0 * total / ideal if ideal > 0 else 0.0,
    }


def design_from_exceedance(rec, plant, percent, method="weibull"):
    """Turbine design flow when you pick Qxx: river flow at that exceedance minus the environmental flow
    that must stay in the river at that flow."""
    P, Q = fdc(rec.flows, method)
    q = flow_at(P, Q, percent)
    env = float(np.minimum(q, plant.env_request(q)))
    return max(q - env, 0.0)
