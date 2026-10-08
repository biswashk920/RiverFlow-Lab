"""Core calculation tests. Run from the project root:  python -m unittest discover -v
All flow series used here are SYNTHETIC (made-up or random with a fixed seed)."""
import unittest

import numpy as np

import hydrofdc as h
from hydrofdc.data import HydroError
from hydrofdc.economics import crf
from hydrofdc.fdc import annual_fdcs, seasonal_fdc
from hydrofdc.optimum import design_range
from hydrofdc.plant import power_kw, installed_kw, flow_split, simulate


def flat_plant(**kw):
    """Plant with efficiency exactly 0.85 in total and no environmental flow, always available."""
    base = dict(net_head_value=50, const_eta=0.85, eta_gen=1.0, eta_trans=1.0, availability_pct=100,
                env_mode="fixed", env_value=0.0)
    base.update(kw)
    return h.Plant(**base)


def random_record(seed, n=1500):
    rng = np.random.default_rng(seed)
    return h.build_record(np.exp(rng.normal(1.0, 0.8, n)), step="daily")


class HandCalculations(unittest.TestCase):
    def test_power_833_9_kw(self):
        # P = 0.85 * 1000 * 9.81 * 2 * 50 / 1000 = 833.85 kW
        p, _ = power_kw(flat_plant(), np.array([2.0]), 2.0)
        self.assertAlmostEqual(float(p[0]), 833.85, places=6)
        self.assertAlmostEqual(installed_kw(flat_plant(), 2.0), 833.85, places=6)

    def test_energy_over_8760_hours_is_7_30_gwh(self):
        rec = h.build_record(np.full(365, 2.0), step="daily")          # 365 days = 8760 h
        s = h.summarize(rec, flat_plant(), 2.0)
        self.assertAlmostEqual(s["total_energy_kwh"], 833.85 * 8760, delta=1e-3)
        self.assertEqual(round(s["total_energy_kwh"] / 1e6, 2), 7.30)
        # the 'average annual' value uses a 365.25-day year (8766 h), so it is 7.31 GWh
        self.assertAlmostEqual(s["annual_energy_gwh"], 833.85 * 8766 / 1e6, places=9)

    def test_constant_flow_gives_flat_fdc_and_capacity_factor_one(self):
        rec = h.build_record(np.full(400, 3.0), step="daily")
        P, Q = h.fdc(rec.flows)
        self.assertTrue(np.all(Q == 3.0))
        for plant in [flat_plant()] + [flat_plant(const_eta=None, turbine=t) for t in h.TURBINES]:
            s = h.summarize(rec, plant, 3.0)
            self.assertAlmostEqual(s["capacity_factor"], 1.0, places=12)

    def test_weibull_exceedance_of_max_and_min(self):
        for n in (30, 100, 1234):
            P = h.plotting_positions(n, "weibull")
            self.assertAlmostEqual(P[0], 1 / (n + 1), places=14)
            self.assertAlmostEqual(P[-1], n / (n + 1), places=14)

    def test_energy_never_exceeds_use_all_flow_up_to_design_flow(self):
        for seed in (1, 2, 3):
            rec = random_record(seed)
            for kind in list(h.TURBINES) + ["const"]:
                for env_mode, env_val in (("percent", 10), ("percent", 0), ("fixed", 0.5)):
                    for avail in (100, 90):
                        plant = h.Plant(net_head_value=40, turbine=kind if kind != "const" else "francis",
                                        const_eta=0.9 if kind == "const" else None, env_mode=env_mode,
                                        env_value=env_val, availability_pct=avail)
                        for qd in (0.5, 2.0, 5.0, 20.0):
                            s = h.summarize(rec, plant, qd)
                            self.assertLessEqual(s["total_energy_kwh"], s["ideal_energy_kwh"] * (1 + 1e-12))


class DataHandling(unittest.TestCase):
    def test_parse_values_handles_text(self):
        v = h.parse_values("1.5, 2 ;3\n x 4")
        self.assertEqual(len(v), 5)
        self.assertTrue(np.isnan(v[3]))

    def test_negative_missing_zero_messages(self):
        vals = list(np.full(60, 2.0))
        vals[3], vals[4], vals[5] = -1.0, np.nan, 0.0
        rec = h.build_record(vals, step="daily")
        self.assertEqual(rec.valid.sum(), 58)
        text = " ".join(rec.messages)
        for word in ("negative", "zero", "missing"):
            self.assertIn(word, text)

    def test_too_short_records_are_refused(self):
        with self.assertRaises(HydroError):
            h.build_record(np.ones(10), step="daily")
        with self.assertRaises(HydroError):
            h.build_record(np.ones(6), step="monthly")

    def test_need_step_without_dates(self):
        with self.assertRaises(HydroError):
            h.build_record(np.ones(100))

    def test_missing_dates_become_missing_values(self):
        import pandas as pd
        d = pd.date_range("2005-01-01", periods=100, freq="D").delete([10, 11])
        rec = h.build_record(np.ones(98), dates=d)
        self.assertEqual(len(rec.flows), 100)
        self.assertEqual(int(np.isnan(rec.flows).sum()), 2)
        self.assertEqual(rec.step, "daily")

    def test_interpolation_fills_gaps(self):
        vals = list(np.arange(1.0, 61.0))
        vals[9] = np.nan
        rec = h.build_record(vals, step="daily", fill="interpolate")
        self.assertAlmostEqual(rec.flows[9], 10.0)
        self.assertEqual(int(np.isnan(rec.flows).sum()), 0)

    def test_monthly_hours_use_real_month_lengths(self):
        import pandas as pd
        d = pd.date_range("2001-01-01", periods=24, freq="MS")
        rec = h.build_record(np.full(24, 5.0), dates=d)
        self.assertEqual(rec.step, "monthly")
        self.assertEqual(rec.hours[1], 28 * 24)          # February 2001
        self.assertEqual(rec.hours[0], 31 * 24)


class FlowDurationCurves(unittest.TestCase):
    def test_percentiles_decrease_with_exceedance(self):
        t = h.percentile_table(random_record(7))
        self.assertTrue(np.all(np.diff(t["Flow (m3/s)"]) <= 0))
        self.assertEqual(list(t["Name"]), ["Q5", "Q10", "Q25", "Q40", "Q50", "Q75", "Q90", "Q95"])

    def test_all_plotting_positions_are_valid(self):
        for m in h.POSITIONS:
            P = h.plotting_positions(50, m)
            self.assertTrue(np.all(np.diff(P) > 0) and P[0] > 0 and P[-1] < 1)
        with self.assertRaises(HydroError):
            h.plotting_positions(10, "nonsense")

    def test_annual_and_seasonal_curves(self):
        import pandas as pd
        d = pd.date_range("2001-01-01", "2003-12-31", freq="D")
        rec = h.build_record(np.linspace(1, 10, len(d)), dates=d)
        self.assertEqual(sorted(annual_fdcs(rec)), [2001, 2002, 2003])
        sf = seasonal_fdc(rec)
        self.assertEqual(len(sf["wet"][1]) + len(sf["dry"][1]), len(d))
        with self.assertRaises(HydroError):
            seasonal_fdc(h.build_record(np.ones(100), step="daily"))


class PlantModel(unittest.TestCase):
    def test_net_head_and_validation(self):
        self.assertAlmostEqual(h.Plant(gross_head=60, head_loss_pct=5).net_head, 57.0)
        self.assertEqual(h.Plant(gross_head=60, net_head_value=50).net_head, 50.0)
        for bad in (dict(), dict(gross_head=60, eta_gen=1.2), dict(gross_head=60, availability_pct=120),
                    dict(gross_head=60, turbine="steam"), dict(gross_head=60, env_value=-1)):
            with self.assertRaises(HydroError):
                h.Plant(**bad)

    def test_flow_split_adds_up_and_respects_minimum_flow(self):
        plant = h.Plant(gross_head=50, turbine="francis", env_mode="percent", env_value=10)
        q = np.array([0.5, 1.0, 2.0, 4.0, 10.0])
        env, turb, spill = flow_split(q, plant, 4.0)         # Francis minimum = 40 % of 4 = 1.6 m3/s
        self.assertTrue(np.allclose(env + turb + spill, q))
        self.assertEqual(list(turb[:3] > 0), [False, False, True])      # 0.45, 0.9 below minimum; 1.8 above
        self.assertAlmostEqual(turb[-1], 4.0)                           # capped at design flow

    def test_fixed_environmental_flow_larger_than_river(self):
        plant = flat_plant(env_value=5.0)
        env, turb, spill = flow_split(np.array([3.0]), plant, 2.0)
        self.assertEqual((env[0], turb[0], spill[0]), (3.0, 0.0, 0.0))

    def test_design_flow_from_exceedance_removes_environmental_flow(self):
        rec = random_record(5)
        plant = h.Plant(net_head_value=40, env_mode="percent", env_value=10)
        P, Q = h.fdc(rec.flows)
        self.assertAlmostEqual(h.design_from_exceedance(rec, plant, 40), 0.9 * h.flow_at(P, Q, 40))

    def test_cumulative_energy_ends_at_total(self):
        rec = random_record(9)
        plant = h.Plant(net_head_value=40)
        sim = simulate(rec, plant, 3.0)
        s = h.summarize(rec, plant, 3.0, sim)
        self.assertEqual(sim.cum_energy_kwh[-1], s["total_energy_kwh"])

    def test_missing_steps_do_not_generate_or_count(self):
        vals = np.full(100, 2.0)
        vals[10:20] = np.nan
        rec = h.build_record(vals, step="daily")
        s = h.summarize(rec, flat_plant(), 2.0)
        self.assertAlmostEqual(s["valid_hours"], 90 * 24)
        self.assertAlmostEqual(s["capacity_factor"], 1.0, places=12)


class Economics(unittest.TestCase):
    def test_capital_recovery_factor(self):
        self.assertAlmostEqual(crf(10, 30), 0.1060792, places=6)
        self.assertAlmostEqual(crf(0, 25), 0.04)

    def test_simple_numbers(self):
        e = h.Economics(tariff=0.1, capex_per_kw=2000, om_pct=2, rate_pct=0, life_years=20)
        r = h.compute_economics(5e6, 1000, e)
        self.assertAlmostEqual(r["capex"], 2e6)
        self.assertAlmostEqual(r["annual_revenue"], 5e5)
        self.assertAlmostEqual(r["annual_om"], 4e4)
        self.assertAlmostEqual(r["simple_payback_years"], 2e6 / 4.6e5)
        self.assertAlmostEqual(r["lcoe_per_kwh"], (2e6 / 20 + 4e4) / 5e6)

    def test_payback_infinite_when_no_profit(self):
        r = h.compute_economics(1e5, 1000, h.Economics(0.01, 5000))
        self.assertEqual(r["simple_payback_years"], float("inf"))


class DesignFlowSearch(unittest.TestCase):
    def test_energy_increases_with_design_flow_for_constant_efficiency(self):
        rec = random_record(11)
        plant = flat_plant()
        sw = h.sweep(rec, plant, np.linspace(0.5, 12, 25))
        self.assertTrue(np.all(np.diff(sw["annual_energy_gwh"]) >= -1e-12))
        self.assertTrue(np.all(np.diff(sw["installed_kw"]) > 0))

    def test_knee_of_a_known_curve(self):
        x = np.linspace(0, 1, 101)
        k = h.find_knee(x, np.sqrt(x))                  # sqrt(x) - x is largest at x = 0.25
        self.assertAlmostEqual(x[k], 0.25, delta=0.011)

    def test_range_and_cost_optimum_run(self):
        rec = random_record(12)
        plant = h.Plant(net_head_value=40)
        grid = design_range(rec, plant)
        sw = h.sweep(rec, plant, grid)
        co = h.cost_optimum(sw, h.Economics(0.1, 2500))
        self.assertTrue(0 <= co["index_net_benefit"] < len(grid))
        self.assertTrue(0 <= h.find_knee(sw["q_design"], sw["annual_energy_gwh"]) < len(grid))


if __name__ == "__main__":
    unittest.main()
