/* simulation.js — Simulation section.
 *
 * Replaces the old Simulation tab: solver settings, Run/Stop, the streaming
 * console, and the live L1 residual chart. Convergence data arrives as
 * `convergence_update` events; nothing is polled.
 */

import { drawPlot } from './svg-plot.js';
import { setParam } from './param-write.js';

const CURVES = [
  { key: 'r_n', name: 'R_N', varName: '--curve-n' },
  { key: 'r_p', name: 'R_P', varName: '--curve-p' },
  { key: 'r_t', name: 'R_T', varName: '--curve-t' },
  { key: 'r_f', name: 'R_F', varName: '--curve-f' },
];

const MAX_CONSOLE_LINES = 2000;

export class SimulationSection {
  constructor(ws, ui) {
    this.ws = ws;
    this.ui = ui;
    this.root = document.getElementById('section-simulation');
    this.consoleEl = this.root.querySelector('#sim-console');
    this.chartEl = this.root.querySelector('#sim-chart');
    this.legendEl = this.root.querySelector('#sim-legend');
    this.chipEl = this.root.querySelector('#sim-chip');
    this.runBtn = this.root.querySelector('#sim-run');
    this.stopBtn = this.root.querySelector('#sim-stop');
    this.iterEl = this.root.querySelector('#sim-iteration');

    this.fields = {
      n_grid: this.root.querySelector('#sim-ngrid'),
      max_iterations: this.root.querySelector('#sim-maxiter'),
      tol: this.root.querySelector('#sim-tol'),
      relax: this.root.querySelector('#sim-relax'),
    };
    this.modeSelect = this.root.querySelector('#sim-mode');

    this.history = [];
    this.params = null;
    this.running = false;
    this.converged = null;   // null = unknown, until the solver says

    this.runBtn.addEventListener('click', () => this.run());
    this.stopBtn.addEventListener('click', () => this.stop());
    this.modeSelect.addEventListener('change', () => this.syncMode());
    for (const input of Object.values(this.fields)) {
      input.addEventListener('input', () => input.classList.toggle(
        'input--empty', input.value.trim() === ''));
    }
    this.root.querySelector('#sim-clear')
      .addEventListener('click', () => this.clear());

    this.geoEl = this.root.querySelector('#sim-geometry');

    ws.on('params_loaded', (evt) => this.adoptParams(evt));
    // Geometry (02) owns the nozzle; show what this run will actually solve.
    window.addEventListener('openengine:geometry-changed',
      (e) => this.renderGeometry(e.detail));

    ws.on('log_line', (evt) => this.appendLine(evt.text));
    ws.on('convergence_update', (evt) => this.addPoint(evt));
    ws.on('simulation_complete', (evt) => this.onComplete(evt));
    ws.on('error', (evt) => {
      if (evt.context !== 'run_simulation' && evt.context !== 'stop_simulation') return;
      this.appendLine(`\n[error] ${evt.message}\n`);
      this.setState('error');
      this.running = false;
      this.syncButtons();
    });

    this.syncMode();
    this.renderChart();

    let pending;
    window.addEventListener('resize', () => {
      clearTimeout(pending);
      pending = setTimeout(() => this.renderChart(), 150);
    });
  }

  activate() { this.renderChart(); }

  adoptParams({ flat, raw }) {
    this.params = raw;
    // Seed the solver box from the file, as the desktop tab did. A key the
    // file does not carry leaves its field empty and blocks Run — better than
    // solving with a number nobody chose.
    for (const [key, input] of Object.entries(this.fields)) {
      input.value = Number.isFinite(flat?.[key]) ? flat[key] : '';
      input.classList.toggle('input--empty', input.value === '');
    }
    if (flat?.solver_mode === 'fixed' || flat?.solver_mode === 'convergence') {
      this.modeSelect.value = flat.solver_mode;
    }
    this.syncMode();
  }

  /** Solver settings with nothing usable in them, by key. */
  issues() {
    const out = [];
    for (const [key, input] of Object.entries(this.fields)) {
      // Fixed-iteration mode ignores the tolerance, so an empty one is fine.
      if (key === 'tol' && this.modeSelect.value === 'fixed') continue;
      const text = input.value.trim();
      if (text === '' || !Number.isFinite(Number(text))) out.push(key);
    }
    return out;
  }

  /** Write this section's values into the nested structure, for Run and Save.
   *
   *  Simulation owns the whole solver box, so these are the values that must
   *  reach the file — otherwise Save would persist the copy the Parameters
   *  section no longer shows.
   */
  applyTo(raw) {
    if (!raw) return raw;
    const solver = 'solver';
    const specs = {
      n_grid: { section: 'nozzle_geometry', unit: '-',
                description: 'Number of computational grid points' },
      max_iterations: { section: solver, unit: '-',
                        description: 'Maximum number of convergence loop iterations' },
      tol: { section: solver, unit: '-', description: 'Convergence tolerance' },
      relax: { section: solver, unit: '-',
               description: 'Under-relaxation factor (0-1)' },
    };
    for (const [key, input] of Object.entries(this.fields)) {
      const text = input.value.trim();
      if (text === '') continue;
      const value = Number(text);
      if (!Number.isFinite(value)) continue;
      setParam(raw, key,
        key === 'n_grid' || key === 'max_iterations' ? Math.round(value) : value,
        specs[key]);
    }
    setParam(raw, 'solver_mode', this.modeSelect.value,
      { section: solver, unit: '-', description: 'Solver mode: convergence or fixed' });
    return raw;
  }

  renderGeometry({ R_throat, E_r, stats }) {
    this.geometryReady = true;
    const rows = [
      ['Throat radius', `${stats.throat_radius_mm.toFixed(3)} mm`],
      ['Exit radius', `${stats.exit_radius_mm.toFixed(3)} mm`],
      ['Expansion ratio', stats.E_r_actual.toFixed(3)],
      ['Total length', `${stats.total_length_mm.toFixed(2)} mm`],
      ['Contraction ratio', stats.contraction_ratio.toFixed(3)],
      // The solver derives N0 from the contraction ratio at run time; this is
      // the isentropic value it starts that search from.
      ['Inlet Mach (isentropic)',
        `${stats.inlet_mach.toFixed(4)} (N0 ${stats.N0_isentropic.toFixed(5)})`],
    ];
    this.geoEl.replaceChildren(...rows.map(([name, value]) => {
      const row = document.createElement('div');
      row.className = 'stat';
      const label = document.createElement('span');
      label.className = 'label-caps';
      label.textContent = name;
      const val = document.createElement('span');
      val.className = 'stat__value';
      val.textContent = value;
      row.append(label, val);
      return row;
    }));
  }

  /** Fixed-iteration mode ignores the tolerance, so grey it out. */
  syncMode() {
    const fixed = this.modeSelect.value === 'fixed';
    this.fields.tol.disabled = fixed;
    this.fields.tol.parentElement.style.opacity = fixed ? '.5' : '1';
    this.fields.tol.classList.toggle(
      'input--empty', !fixed && this.fields.tol.value.trim() === '');
  }

  overrides() {
    const out = {};
    for (const [key, input] of Object.entries(this.fields)) {
      const value = Number(input.value);
      if (input.value.trim() !== '' && Number.isFinite(value)) {
        out[key] = key === 'n_grid' || key === 'max_iterations'
          ? Math.round(value) : value;
      }
    }
    return out;
  }

  run() {
    if (this.running) return;
    if (!this.params) {
      this.ui.toast('Load a parameter file first', 'Open the Parameters section.', 'error');
      return;
    }

    // Nothing is assumed on the user's behalf, so nothing starts until every
    // value the solver reads has actually been supplied. The backend checks
    // this again before spawning; this is what keeps it from getting there.
    const missing = [
      ...(this.ui.geometryIssues?.() ?? []),
      ...this.issues(),
      ...(this.ui.parameterIssues?.() ?? []),
    ];
    if (missing.length) {
      const names = [...new Set(missing)];
      this.setState('error');
      this.appendLine(`
[not started] No value for: ${names.join(', ')}.
Fill these in — the Geometry section for the contour, the solver box
above, and the Parameters section for the rest.
`);
      this.ui.toast('Nothing to solve yet',
        `${names.length} parameter(s) still need a value`, 'error');
      return;
    }

    this.clear();
    this.running = true;
    this.setState('running');
    this.syncButtons();
    this.ui.setSolving(true);

    this.ws.send({
      type: 'run_simulation',
      raw_params: this.ui.currentParams() || this.params,
      solver_overrides: this.overrides(),
      solver_mode: this.modeSelect.value,
    });
  }

  stop() {
    if (!this.running) return;
    this.stopBtn.disabled = true;
    this.appendLine('\n[stopping…]\n');
    this.ws.send({ type: 'stop_simulation' });
  }

  onComplete(evt) {
    this.running = false;
    this.ui.setSolving(false);
    this.syncButtons();

    if (evt.stopped_by_user) {
      this.setState('idle', 'stopped');
      this.appendLine('\n[stopped]\n');
      return;
    }
    if (evt.returncode === 0) {
      if (this.converged === false) {
        this.setState('warn', 'Not converged');
        this.ui.toast('Finished without converging',
          'The iteration cap was reached first.', 'warn');
      } else {
        this.setState('done', this.converged ? 'Converged' : undefined);
        this.ui.toast('Simulation complete', evt.results_file || '', 'ok');
      }
    } else {
      this.setState('error');
      this.ui.toast('Simulation failed', `Exit code ${evt.returncode}`, 'error');
    }
  }

  syncButtons() {
    this.runBtn.disabled = this.running;
    this.stopBtn.disabled = !this.running;
  }

  setState(state, labelOverride) {
    const labels = {
      idle: 'Idle', running: 'Running', done: 'Finished', error: 'Failed',
    };
    this.chipEl.className = `chip chip--${state}`;
    this.chipEl.querySelector('.chip__label').textContent =
      labelOverride || labels[state];
  }

  clear() {
    this.history = [];
    this.converged = null;
    this.consoleEl.replaceChildren();
    this.iterEl.textContent = '—';
    this.setState('idle');
    this.renderChart();
  }

  /** Did the solver actually converge? Read off its own summary line.
   *
   *  Exit code 0 only means the process finished; hitting the iteration cap
   *  is a successful exit and an unconverged answer. Reporting that as
   *  "Converged" is the one thing this chip must not do.
   */
  noteConvergence(text) {
    if (text.includes('CONVERGENCE ACHIEVED')) this.converged = true;
    else if (text.includes('without convergence')) this.converged = false;
  }

  appendLine(text) {
    this.noteConvergence(text);
    // Stick to the bottom only if the user hasn't scrolled up to read.
    const atBottom = this.consoleEl.scrollTop + this.consoleEl.clientHeight
      >= this.consoleEl.scrollHeight - 24;

    const span = document.createElement('span');
    const lower = text.toLowerCase();
    if (lower.includes('error') || lower.includes('traceback')) {
      span.className = 'console__line--error';
    } else if (lower.includes('warning')) {
      span.className = 'console__line--warn';
    }
    span.textContent = text;
    this.consoleEl.append(span);

    while (this.consoleEl.childNodes.length > MAX_CONSOLE_LINES) {
      this.consoleEl.firstChild.remove();
    }
    if (atBottom) this.consoleEl.scrollTop = this.consoleEl.scrollHeight;
  }

  addPoint(evt) {
    this.history.push(evt);
    this.iterEl.textContent = String(evt.iteration);
    this.renderChart();
  }

  renderChart() {
    const styles = getComputedStyle(document.documentElement);
    const series = CURVES.map(({ key, name, varName }) => ({
      name,
      color: styles.getPropertyValue(varName).trim(),
      points: this.history
        .filter((h) => typeof h[key] === 'number' && h[key] > 0)
        .map((h) => [h.iteration, h[key]]),
    }));

    const tol = Number(this.fields.tol.value);
    drawPlot(this.chartEl, series, {
      yScale: 'log',
      xLabel: 'iteration',
      yLabel: 'L1 residual',
      threshold: this.modeSelect.value === 'fixed' || !Number.isFinite(tol)
        ? null : tol,
      thresholdLabel: 'tolerance',
    });

    this.legendEl.replaceChildren(...series.map((s) => {
      const item = document.createElement('span');
      item.className = 'chart-legend__item';
      const swatch = document.createElement('span');
      swatch.className = 'chart-legend__swatch';
      swatch.style.background = s.color;
      const label = document.createElement('span');
      const last = s.points.at(-1);
      label.textContent = last ? `${s.name} ${last[1].toExponential(2)}` : s.name;
      item.append(swatch, label);
      return item;
    }));
  }
}
