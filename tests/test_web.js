// Tests the browser calculation and animation-state logic with Node (no browser, no npm).  Run: node tests/test_web.js
const fs = require('fs'), assert = require('assert');
const html = fs.readFileSync('docs/index.html', 'utf8');
const core = html.split('/*CORE*/')[1].split('/*ENDCORE*/')[0];
const C = new Function(core + ';return{parseCSV,fdc,flowAt,designFromExc,simulate,summarize,state,split}')();
const near = (a, b, tol = 1e-9) => assert(Math.abs(a - b) <= tol * Math.max(1, Math.abs(b)), `${a} vs ${b}`);
const rec = C.parseCSV(fs.readFileSync('examples/synthetic_daily.csv', 'utf8'));
let n = 0;
for (const c of JSON.parse(fs.readFileSync('tests/fixtures/web_cases.json'))) {          // browser == Python
  const F = C.fdc(rec.q, c.pos), e = c.expected;
  for (const p in e.q_percentiles) near(C.flowAt(F, +p), e.q_percentiles[p]);
  const qd = c.qd || C.designFromExc(c, F, c.pct); near(qd, e.qd);
  const sim = C.simulate(rec.q, c, qd, 24, rec.yr), s = C.summarize(sim);
  for (const k of ['installed_kw', 'total_energy_kwh', 'annual_energy_gwh', 'capacity_factor', 'flow_used_pct']) near(s[k], e[k]);
  // animation logic: end-of-playback total is EXACTLY the calculated total; scrubbing == playing
  assert.strictEqual(C.state(sim, sim.n - 1).cum, s.total_energy_kwh);
  let run = 0, ytd = 0;
  for (let i = 0; i < sim.n; i++) {
    run += sim.en[i]; ytd = (i > 0 && rec.yr[i] !== rec.yr[i - 1]) ? sim.en[i] : ytd + sim.en[i];
    if (i % 97 === 0 || i === sim.n - 1) { const st = C.state(sim, i); assert.strictEqual(st.cum, run); assert.strictEqual(st.ytd, ytd); }
  }
  for (let i = 0; i < sim.n; i++) { const [a, b, d] = [sim.env[i], sim.turb[i], sim.spill[i]]; near(a + b + d, sim.q[i], 1e-12); }
  n++;
}
// hand checks
const flat = { turbine: 'constant', constEta: .85, etaGen: 1, etaTrans: 1, avail: 100, rho: 1000, g: 9.81, envMode: 'fixed', envValue: 0, netHead: 50 };
const r2 = C.parseCSV(Array(365).fill('2').join('\n')), s2 = C.summarize(C.simulate(r2.q, flat, 2, 24, r2.yr));
near(s2.installed_kw, 833.85); near(s2.total_energy_kwh, 833.85 * 8760); near(s2.capacity_factor, 1, 1e-12);
const Fc = C.fdc(r2.q, 'weibull'); assert(Fc.Q.every(v => v === 2));
const Fw = C.fdc(rec.q, 'weibull'), m = Fw.Q.length; near(Fw.P[0], 1 / (m + 1)); near(Fw.P[m - 1], m / (m + 1));
console.log(`OK: ${n} browser-vs-Python cases, animation state checks, hand calculations`);
