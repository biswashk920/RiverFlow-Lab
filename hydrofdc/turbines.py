"""Simplified turbine efficiency curves.

IMPORTANT: these are TYPICAL, SIMPLIFIED ASSUMPTIONS chosen for pre-feasibility teaching, NOT manufacturer
or published data. Replace them with real curves from a supplier before any real design decision.
Efficiency is given against the fraction of design flow (flow through the turbine / design flow).
"""
from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class Turbine:
    name: str
    fracs: tuple
    etas: tuple
    min_frac: float          # minimum operating flow as a fraction of design flow

    def efficiency(self, frac):
        return np.interp(frac, self.fracs, self.etas)

    @property
    def eta_max(self):
        return max(self.etas)


TURBINES = {
    "pelton":    Turbine("Pelton",     (0.10, 0.20, 0.40, 0.70, 1.00), (0.78, 0.85, 0.89, 0.90, 0.89), 0.10),
    "francis":   Turbine("Francis",    (0.40, 0.60, 0.80, 1.00),       (0.75, 0.87, 0.92, 0.91),       0.40),
    "kaplan":    Turbine("Kaplan",     (0.20, 0.40, 0.60, 0.80, 1.00), (0.78, 0.88, 0.91, 0.92, 0.91), 0.20),
    "crossflow": Turbine("Cross-flow", (0.15, 0.30, 0.50, 0.75, 1.00), (0.65, 0.76, 0.82, 0.84, 0.83), 0.15),
}


def constant_turbine(eta, min_frac=0.0):
    return Turbine("Constant efficiency", (0.0, 1.0), (eta, eta), min_frac)
