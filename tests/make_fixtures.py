"""Write expected results from the PYTHON code so the Node test can check the browser code against them.
Run from the project root:  python -m tests.make_fixtures"""
import json
import hydrofdc as h

rec = h.load_csv("examples/synthetic_daily.csv")
J = dict(turbine="francis", constEta=0.88, minFlow=None, etaGen=0.97, etaTrans=0.99, avail=95, rho=1000, g=9.81,
         envMode="percent", envValue=10, gross=60, loss=5, netHead=None)
cases = [dict(J, pct=40),
         dict(J, turbine="pelton", envMode="fixed", envValue=0.5, avail=90, pct=25, pos="cunnane"),
         dict(J, turbine="constant", netHead=50, envValue=0, pct=60, pos="hazen"),
         dict(J, turbine="kaplan", minFlow=1.2, qd=5.0, rho=998, g=9.80, pos="blom")]
for c in cases:
    m = c.get("pos", "weibull"); c["pos"] = m
    pl = h.Plant(gross_head=c["gross"], head_loss_pct=c["loss"], net_head_value=c["netHead"],
                 turbine="francis" if c["turbine"] == "constant" else c["turbine"],
                 const_eta=c["constEta"] if c["turbine"] == "constant" else None, min_flow=c["minFlow"],
                 eta_gen=c["etaGen"], eta_trans=c["etaTrans"], availability_pct=c["avail"], rho=c["rho"], g=c["g"],
                 env_mode=c["envMode"], env_value=c["envValue"])
    qd = c.get("qd") or h.design_from_exceedance(rec, pl, c["pct"], m)
    s = h.summarize(rec, pl, qd)
    P, Q = h.fdc(rec.flows, m)
    c["expected"] = dict(qd=qd, installed_kw=s["installed_kw"], total_energy_kwh=s["total_energy_kwh"],
                         annual_energy_gwh=s["annual_energy_gwh"], capacity_factor=s["capacity_factor"],
                         flow_used_pct=s["flow_used_pct"], q_percentiles={str(p): h.flow_at(P, Q, p) for p in (5, 25, 50, 95)})
json.dump(cases, open("tests/fixtures/web_cases.json", "w"), indent=1)
print("wrote", len(cases), "cases")
