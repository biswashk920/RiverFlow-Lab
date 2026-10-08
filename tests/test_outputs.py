"""Smoke tests for the command line, figures and animation (they check that files are made, not how they look)."""
import contextlib
import io
import os
import tempfile
import unittest

import matplotlib

matplotlib.use("Agg")
import numpy as np                                    # noqa: E402

import hydrofdc as h                                  # noqa: E402
from hydrofdc import plots                            # noqa: E402
from hydrofdc.animate import make_animation           # noqa: E402
from hydrofdc.cli import main, EXAMPLE_CSV            # noqa: E402
from hydrofdc.data import HydroError                  # noqa: E402


def quiet(argv):
    with contextlib.redirect_stdout(io.StringIO()) as buf:
        code = main(argv)
    return code, buf.getvalue()


class Outputs(unittest.TestCase):
    def test_example_csv_loads(self):
        rec = h.load_csv(EXAMPLE_CSV)
        self.assertEqual(rec.step, "daily")
        self.assertEqual(len(rec.flows), 3652)
        self.assertTrue(rec.has_dates)

    def test_cli_run_makes_tables_and_figures(self):
        with tempfile.TemporaryDirectory() as d:
            code, out = quiet(["run", "--example", "--out", d, "--compare", "25,60", "--seasonal",
                               "--tariff", "0.08", "--capex-per-kw", "2500"])
            self.assertEqual(code, 0)
            names = set(os.listdir(d))
            for f in ("figure1_flow_duration_curve.png", "figure2_power_duration_curve.png",
                      "figure3_energy_vs_design_flow.png", "figure4_monthly_energy.png",
                      "figure1b_seasonal_fdc.png", "table_summary.csv", "table_percentiles.csv",
                      "table_comparison.csv"):
                self.assertIn(f, names)
            self.assertIn("Cost-based optimum", out)

    def test_cli_friendly_errors(self):
        for argv in (["run", "--values", "1 2 3", "--step", "daily", "--net-head", "50"],
                     ["run", "--values", "1 2 3 4 5 6 7 8 9 10 11 12 13 14 15 16 17 18 19 20 21 22 23 24 25 26 27 28 29 30 31",
                      "--step", "daily"],                            # no head given
                     ["run", "--example", "--design-pct", "150"]):
            code, out = quiet(argv)
            self.assertEqual(code, 1)
            self.assertIn("Problem:", out)

    def test_values_without_dates_still_work_but_skip_calendar_figures(self):
        with tempfile.TemporaryDirectory() as d:
            vals = " ".join(f"{v:.2f}" for v in np.linspace(1, 8, 400))
            code, _ = quiet(["run", "--values", vals, "--step", "daily", "--net-head", "30", "--out", d, "--seasonal"])
            self.assertEqual(code, 0)
            self.assertNotIn("figure4_monthly_energy.png", os.listdir(d))
        rec = h.build_record(np.linspace(1, 8, 400), step="daily")
        with self.assertRaises(HydroError):
            plots.figure4(rec, h.Plant(net_head_value=30), 3.0)

    def test_animation_gif_is_written(self):
        rec = h.load_csv(EXAMPLE_CSV)
        plant = h.Plant(gross_head=60)
        with tempfile.TemporaryDirectory() as d:
            path = make_animation(rec, plant, 4.0, os.path.join(d, "a.gif"), year=2003, frame_step=60, fps=5, dpi=40)
            self.assertGreater(os.path.getsize(path), 1000)
            with self.assertRaises(HydroError):
                make_animation(rec, plant, 4.0, os.path.join(d, "a.gif"), year=1990)
            with self.assertRaises(HydroError):
                make_animation(rec, plant, 4.0, os.path.join(d, "a.avi"), year=2003)


if __name__ == "__main__":
    unittest.main()
