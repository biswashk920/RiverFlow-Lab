"""Command line interface:  python -m hydrofdc run --example   |   python -m hydrofdc animate --example"""
import argparse
import os
from pathlib import Path

import matplotlib
import pandas as pd

matplotlib.use("Agg")                      # draw to files, no window needed

from . import plots                        # noqa: E402
from .animate import make_animation        # noqa: E402
from .data import HydroError, load_csv, build_record, parse_values   # noqa: E402
from .economics import Economics, compute_economics                   # noqa: E402
from .fdc import POSITIONS, percentile_table                          # noqa: E402
from .optimum import cost_optimum, design_range, find_knee, sweep     # noqa: E402
from .plant import Plant, design_from_exceedance, summarize          # noqa: E402
from .report import comparison_table, monthly_frame, save_tables, summary_frame  # noqa: E402
from .turbines import TURBINES                                        # noqa: E402

EXAMPLE_CSV = Path(__file__).resolve().parent.parent / "examples" / "synthetic_daily.csv"


def _add_common(p):
    d = p.add_argument_group("flow record")
    d.add_argument("--flows", help="CSV file with flows in m3/s (optional date column)")
    d.add_argument("--values", help="flows pasted as numbers, e.g. \"1.2 3.4 5.6\" (needs --step)")
    d.add_argument("--example", action="store_true", help="use the SYNTHETIC example record (60 m gross head unless set)")
    d.add_argument("--flow-col"); d.add_argument("--date-col")
    d.add_argument("--step", choices=["daily", "monthly"], help="needed only when there are no dates")
    d.add_argument("--fill", choices=["exclude", "interpolate"], default="exclude", help="what to do with missing values")
    d.add_argument("--position", choices=list(POSITIONS), default="weibull", help="plotting position formula")
    h = p.add_argument_group("head")
    h.add_argument("--gross-head", type=float, help="gross head in m")
    h.add_argument("--head-loss", type=float, default=5.0, help="head loss, %% of gross head (default 5)")
    h.add_argument("--net-head", type=float, help="net head in m (replaces gross head and loss)")
    g = p.add_argument_group("design flow (through the turbine)")
    g.add_argument("--design-pct", type=float, help="pick by exceedance %%, e.g. 40 for Q40 (default 40)")
    g.add_argument("--design-flow", type=float, help="or give a value in m3/s")
    g.add_argument("--env-mode", choices=["percent", "fixed"], default="percent", help="environmental flow type")
    g.add_argument("--env-value", type=float, help="%% of river flow or m3/s (default 10 %% / 0 m3/s)")
    t = p.add_argument_group("turbine and plant")
    t.add_argument("--turbine", choices=list(TURBINES), default="francis")
    t.add_argument("--const-eta", type=float, help="constant turbine efficiency instead of a curve, e.g. 0.88")
    t.add_argument("--min-flow", type=float, help="minimum operating flow in m3/s (default: turbine type default)")
    t.add_argument("--eta-gen", type=float, default=0.97); t.add_argument("--eta-trans", type=float, default=0.99)
    t.add_argument("--availability", type=float, default=95.0, help="%% of year plant is available")
    t.add_argument("--rho", type=float, default=1000.0); t.add_argument("--g", type=float, default=9.81)
    e = p.add_argument_group("economics (optional)")
    e.add_argument("--tariff", type=float, help="price per kWh"); e.add_argument("--capex-per-kw", type=float)
    e.add_argument("--om-pct", type=float, default=2.0); e.add_argument("--rate", type=float, default=10.0)
    e.add_argument("--life", type=float, default=30.0)


def _load(a):
    if a.example:
        return load_csv(EXAMPLE_CSV, step=a.step, fill=a.fill)
    if a.flows:
        return load_csv(a.flows, flow_col=a.flow_col, date_col=a.date_col, step=a.step, fill=a.fill)
    if a.values:
        return build_record(parse_values(a.values), step=a.step, fill=a.fill)
    raise HydroError("Give a flow record: --flows FILE.csv, --values \"...\" or --example.")


def _plant(a):
    gross = a.gross_head if a.gross_head is not None or a.net_head is not None else (60.0 if a.example else None)
    env = a.env_value if a.env_value is not None else (10.0 if a.env_mode == "percent" else 0.0)
    return Plant(gross_head=gross, head_loss_pct=a.head_loss, net_head_value=a.net_head, turbine=a.turbine,
                 const_eta=a.const_eta, min_flow=a.min_flow, eta_gen=a.eta_gen, eta_trans=a.eta_trans,
                 availability_pct=a.availability, rho=a.rho, g=a.g, env_mode=a.env_mode, env_value=env)


def _econ(a):
    if a.tariff is None and a.capex_per_kw is None:
        return None
    if a.tariff is None or a.capex_per_kw is None:
        raise HydroError("For economics give both --tariff and --capex-per-kw.")
    return Economics(a.tariff, a.capex_per_kw, a.om_pct, a.rate, a.life)


def _design(a, rec, plant):
    if a.design_flow is not None:
        if a.design_flow <= 0:
            raise HydroError("Design flow must be greater than zero.")
        return a.design_flow, f"{a.design_flow:g} m3/s"
    pct = 40.0 if a.design_pct is None else a.design_pct
    if not 0 < pct < 100:
        raise HydroError("Exceedance percentage must be between 0 and 100.")
    qd = design_from_exceedance(rec, plant, pct, a.position)
    if qd <= 0:
        raise HydroError("After the environmental flow nothing is left for the turbine at that exceedance.")
    return qd, f"Q{pct:g}"


def _show(df):
    return df.to_string(index=False, float_format=lambda v: f"{v:,.3f}")


def _floats(text):
    try:
        return [float(x) for x in text.replace("Q", "").replace("q", "").split(",") if x.strip()]
    except ValueError:
        raise HydroError("Lists must be numbers separated by commas, e.g. 25,40,60.")


def cmd_run(a):
    rec = _load(a)
    plant = _plant(a)
    econ = _econ(a)
    qd, label = _design(a, rec, plant)
    for m in rec.messages:
        print("Note:", m)
    print("Turbine curves are typical simplified assumptions, not manufacturer data. Economics are a pre-feasibility estimate.\n")
    s = summarize(rec, plant, qd)
    er = compute_economics(s["annual_energy_kwh"], s["installed_kw"], econ) if econ else None
    designs = [(label, qd)]
    if a.compare:
        designs += [(f"Q{p:g}", design_from_exceedance(rec, plant, p, a.position)) for p in _floats(a.compare)]
    if a.compare_flows:
        designs += [(f"{f:g} m3/s", f) for f in _floats(a.compare_flows)]
    tables = {"percentiles": percentile_table(rec, a.position), "summary": summary_frame(s, er),
              "comparison": comparison_table(rec, plant, designs, econ)}
    if rec.has_dates:
        tables["monthly_energy"] = monthly_frame(rec, plant, qd)
    sw = sweep(rec, plant, design_range(rec, plant, a.position))
    k = find_knee(sw["q_design"], sw["annual_energy_gwh"])
    knee = {"Knee design flow (m3/s)": sw["q_design"][k], "Annual energy at knee (GWh)": sw["annual_energy_gwh"][k]}
    tables["energy_vs_design_flow"] = pd.DataFrame({
        "Design flow (m3/s)": sw["q_design"], "Installed capacity (kW)": sw["installed_kw"],
        "Annual energy (GWh)": sw["annual_energy_gwh"], "Capacity factor (%)": 100 * sw["capacity_factor"]})
    print(_show(tables["percentiles"]), "\n")
    print(_show(tables["summary"]), "\n")
    if len(designs) > 1:
        print(_show(tables["comparison"]), "\n")
    print(f"Knee of the energy curve: design flow {knee['Knee design flow (m3/s)']:.2f} m3/s "
          f"({knee['Annual energy at knee (GWh)']:.2f} GWh/year)")
    if econ:
        i = cost_optimum(sw, econ)["index_net_benefit"]
        print(f"Cost-based optimum: design flow {sw['q_design'][i]:.2f} m3/s ({sw['annual_energy_gwh'][i]:.2f} GWh/year)")
    paths = save_tables(a.out, tables)
    if not a.no_figs:
        figs = {"figure1_flow_duration_curve": plots.figure1(rec, plant, qd, a.position, a.log, not a.no_years),
                "figure2_power_duration_curve": plots.figure2(rec, plant, qd, a.position),
                "figure3_energy_vs_design_flow": plots.figure3(rec, plant, qd, a.position, econ, sw)}
        if rec.has_dates:
            figs["figure4_monthly_energy"] = plots.figure4(rec, plant, qd)
            if a.seasonal:
                wm = tuple(int(x) for x in _floats(a.wet_months))
                figs["figure1b_seasonal_fdc"] = plots.figure_seasonal(rec, wm, a.position, a.log)
        elif a.seasonal:
            print("Note: seasonal curves skipped (no dates).")
        for name, fig in figs.items():
            path = os.path.join(a.out, name + ".png")
            fig.savefig(path, dpi=150)
            paths.append(path)
    print(f"\nSaved {len(paths)} files in {os.path.abspath(a.out)}")
    return 0


def cmd_animate(a):
    rec = _load(a)
    plant = _plant(a)
    qd, _ = _design(a, rec, plant)
    path = make_animation(rec, plant, qd, a.out, year=a.year, frame_step=a.frame_step, fps=a.fps)
    print("Saved", os.path.abspath(path))
    return 0


def build_parser():
    ap = argparse.ArgumentParser(prog="hydrofdc", description="Flow duration curve and run-of-river hydropower "
                                 "calculator (pre-feasibility estimate).")
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run", help="calculate and save tables and figures")
    _add_common(r)
    r.add_argument("--out", default="results", help="folder for tables and figures (default: results)")
    r.add_argument("--compare", help="extra design flows as exceedance %%, e.g. 25,60")
    r.add_argument("--compare-flows", help="extra design flows in m3/s, e.g. 2,3.5")
    r.add_argument("--log", action="store_true", help="log scale on the flow axis")
    r.add_argument("--no-figs", action="store_true"); r.add_argument("--no-years", action="store_true")
    r.add_argument("--seasonal", action="store_true", help="also draw wet/dry season curves (needs dates)")
    r.add_argument("--wet-months", default="6,7,8,9", help="months counted as wet season (default 6,7,8,9)")
    r.set_defaults(func=cmd_run)
    n = sub.add_parser("animate", help="save a GIF or MP4 of one year")
    _add_common(n)
    n.add_argument("--out", default="animation.gif", help="file ending in .gif or .mp4")
    n.add_argument("--year", type=int); n.add_argument("--frame-step", type=int)
    n.add_argument("--fps", type=int, default=12)
    n.set_defaults(func=cmd_animate)
    return ap


def main(argv=None):
    a = build_parser().parse_args(argv)
    try:
        return a.func(a)
    except HydroError as exc:
        print("Problem:", exc)
        return 1
