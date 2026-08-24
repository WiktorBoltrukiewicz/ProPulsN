/* geometry.js — Geometry section.
 *
 * Replaces the old Geometry tab: the nozzle profile, the stats box, and DXF
 * export. The diagram is drawn from real solver geometry (preview_geometry),
 * not a decorative curve — the annotations are the actual computed stations.
 */

import { setParam } from './param-write.js';

const NS = 'http://www.w3.org/2000/svg';

const svgEl = (name, attrs = {}) => {
  const node = document.createElementNS(NS, name);
  for (const [k, v] of Object.entries(attrs)) node.setAttribute(k, v);
  return node;
};

const fmt = (value, digits = 2) =>
  Number.isFinite(value) ? value.toFixed(digits) : '—';

export class GeometrySection {
  constructor(ws, ui) {
    this.ws = ws;
    this.ui = ui;
    this.root = document.getElementById('section-geometry');
    this.diagram = this.root.querySelector('#geo-diagram');
    this.svg = this.root.querySelector('#geo-svg');
    this.statsEl = this.root.querySelector('#geo-stats');
    this.statusEl = this.root.querySelector('#geo-status');
    this.latest = null;

    this.inputs = {
      R_throat: this.root.querySelector('#geo-rthroat'),
      E_r: this.root.querySelector('#geo-er'),
      n_grid: this.root.querySelector('#geo-ngrid'),
      R_chamber: this.root.querySelector('#geo-rchamber'),
      L_chamber: this.root.querySelector('#geo-lchamber'),
      R_conv_arc: this.root.querySelector('#geo-rconvarc'),
    };
    this.dxf = {
      n_grid: this.root.querySelector('#dxf-ngrid'),
      mirror: this.root.querySelector('#dxf-mirror'),
      spline: this.root.querySelector('#dxf-spline'),
      labels: this.root.querySelector('#dxf-labels'),
    };

    this.downloadLink = this.root.querySelector('#geo-download');

    this.root.querySelector('#geo-refresh')
      .addEventListener('click', () => this.refresh());
    this.root.querySelector('#geo-export')
      .addEventListener('click', () => this.exportDxf());
    this.root.querySelector('#dxf-save')
      .addEventListener('click', () => this.saveSettings());

    for (const input of Object.values(this.inputs)) {
      input.addEventListener('change', () => this.refresh());
    }

    ws.on('geometry_preview', (evt) => this.render(evt));
    ws.on('dxf_export_ready', (evt) => {
      this.setStatus(`Saved ${evt.filename}`, 'ok');
      this.ui.toast('DXF exported', evt.filename, 'ok');
      this.offerDownload(evt);
    });
    ws.on('settings', (evt) => this.applySettings(evt));

    // This section owns R_throat / E_r. A newly loaded file seeds them, but
    // nothing else overwrites them — otherwise an unrelated edit in
    // Parameters would silently discard the nozzle the user just designed.
    ws.on('params_loaded', (evt) => this.adoptParams(evt.flat));

    // Redraw on resize so the SVG stays crisp at any width.
    let pending;
    window.addEventListener('resize', () => {
      clearTimeout(pending);
      pending = setTimeout(() => this.latest && this.render(this.latest), 150);
    });
  }

  activate() {
    // The profile is built as soon as a file loads, while this section is
    // still hidden and has no width — redraw now that it can be measured.
    if (this.latest) this.render(this.latest);
    else this.refresh();
  }

  adoptParams(flat) {
    if (!flat) return;
    // n_grid is deliberately absent: this section's grid is the preview
    // resolution, not the solver's. Simulation (03) owns that one.
    for (const key of ['R_throat', 'E_r', 'R_chamber', 'L_chamber', 'R_conv_arc']) {
      // Blank when the file has no value: carrying one over from whatever was
      // loaded before would be a number nobody chose for this engine.
      this.inputs[key].value = Number.isFinite(flat[key]) ? flat[key] : '';
    }
    this.refresh();
  }

  /** Contour inputs with nothing usable in them, by key. */
  issues() {
    const out = [];
    for (const [key, input] of Object.entries(this.inputs)) {
      const text = input.value.trim();
      if (text === '' || !Number.isFinite(Number(text))) out.push(key);
    }
    return out;
  }

  values() {
    return {
      R_throat: parseFloat(this.inputs.R_throat.value),
      E_r: parseFloat(this.inputs.E_r.value),
      n_grid: parseInt(this.inputs.n_grid.value, 10),
      R_chamber: parseFloat(this.inputs.R_chamber.value),
      L_chamber: parseFloat(this.inputs.L_chamber.value),
      R_conv_arc: parseFloat(this.inputs.R_conv_arc.value),
    };
  }

  refresh() {
    const values = this.values();
    const { R_throat, E_r, n_grid, R_chamber, R_conv_arc } = values;
    if (!(R_throat > 0) || !(E_r > 1) || !(n_grid >= 2)) {
      this.setStatus('Throat radius must be above 0 and expansion ratio above 1.', 'error');
      return;
    }
    if (!(R_chamber > R_throat)) {
      this.setStatus('Chamber radius must be larger than the throat radius.', 'error');
      return;
    }
    if (!(R_conv_arc > 0)) {
      this.setStatus('Convergent arc radius must be above 0.', 'error');
      return;
    }
    this.setStatus('Building profile…');
    this.ws.send({ type: 'preview_geometry', ...values });
  }

  exportDxf() {
    const { R_throat, E_r, R_chamber, L_chamber, R_conv_arc } = this.values();
    if (!(R_throat > 0) || !(E_r > 1) || !(R_chamber > R_throat)) {
      this.setStatus('Fix the geometry values before exporting.', 'error');
      return;
    }
    this.setStatus('Writing DXF…');
    this.ws.send({
      type: 'export_dxf',
      R_throat,
      E_r,
      R_chamber,
      L_chamber,
      R_conv_arc,
      n_grid: parseInt(this.dxf.n_grid.value, 10) || 500,
      mirror: this.dxf.mirror.checked,
      spline: this.dxf.spline.checked,
      labels: this.dxf.labels.checked,
    });
  }

  /** Reveal the download link for a freshly written DXF. */
  offerDownload({ filename, download_url: url }) {
    if (!this.downloadLink) return;
    if (!url) { this.downloadLink.hidden = true; return; }
    this.downloadLink.href = url;
    this.downloadLink.setAttribute('download', filename);
    this.downloadLink.hidden = false;
  }

  saveSettings() {
    this.ws.send({
      type: 'save_settings',
      dxf_n_grid: parseInt(this.dxf.n_grid.value, 10) || 500,
      dxf_mirror: this.dxf.mirror.checked,
      dxf_spline: this.dxf.spline.checked,
      dxf_labels: this.dxf.labels.checked,
    });
    this.ui.toast('Export options saved', '', 'ok');
  }

  applySettings(settings) {
    this.dxf.n_grid.value = settings.dxf_n_grid;
    this.dxf.mirror.checked = settings.dxf_mirror;
    this.dxf.spline.checked = settings.dxf_spline;
    this.dxf.labels.checked = settings.dxf_labels;
  }

  setSolving(isSolving) {
    this.diagram.dataset.solving = isSolving ? 'true' : 'false';
  }

  setStatus(text, kind = '') {
    this.statusEl.textContent = text;
    this.statusEl.className = `status${kind ? ` status--${kind}` : ''}`;
  }

  render(evt) {
    this.latest = evt;
    this.renderStats(evt.stats);
    this.renderDiagram(evt);
    this.setStatus(`${evt.x_mm.length} profile points`, 'ok');

    // Publish the nozzle so Simulation can show (and solve) what was designed
    // here. Sections talk through events, never by reaching into each other.
    window.dispatchEvent(new CustomEvent('openengine:geometry-changed', {
      detail: { ...this.values(), stats: evt.stats },
    }));
  }

  /** Write this section's geometry into a raw params structure. */
  applyTo(raw) {
    if (!raw) return raw;
    const { R_throat, E_r, R_chamber, L_chamber, R_conv_arc } = this.values();
    if (!(R_throat > 0) || !(E_r > 1) || !(R_chamber > R_throat)) return raw;

    // Files written before the chamber became parametric carry no entry for
    // it, so setParam() creates one rather than discarding what the user drew.
    const section = 'nozzle_geometry';
    setParam(raw, 'R_throat', R_throat,
             { section, unit: 'm', description: 'Throat radius' });
    setParam(raw, 'E_r', E_r,
             { section, unit: '-', description: 'Expansion ratio (A_exit / A_throat)' });
    setParam(raw, 'R_chamber', R_chamber,
             { section, unit: 'm', description: 'Combustion chamber radius' });
    setParam(raw, 'L_chamber', L_chamber,
             { section, unit: 'm',
               description: 'Chamber inlet distance upstream of the throat (throat at x = 0)' });
    setParam(raw, 'R_conv_arc', R_conv_arc,
             { section, unit: 'm', description: 'Convergent section large-arc radius' });
    return raw;
  }

  renderStats(stats) {
    const rows = [
      ['Total length', `${fmt(stats.total_length_mm)} mm`, false],
      ['Throat radius', `${fmt(stats.throat_radius_mm, 3)} mm`, true],
      ['Exit radius', `${fmt(stats.exit_radius_mm, 3)} mm`, false],
      ['Expansion ratio', fmt(stats.E_r_actual, 3), false],
      ['Throat position', `${fmt(stats.throat_position_mm)} mm`, false],
      ['Chamber radius', `${fmt(stats.chamber_radius_mm, 3)} mm`, false],
      ['Contraction ratio', fmt(stats.contraction_ratio, 3), false],
      // The isentropic inlet condition this contour implies — the check that
      // the engine can choke at all. The solver shoots for a slightly higher
      // N0 at run time; see core/inlet_condition.py.
      ['Inlet Mach (isentropic)', fmt(stats.inlet_mach, 4), true],
    ];
    this.statsEl.replaceChildren(...rows.map(([name, value, accent]) => {
      const row = document.createElement('div');
      row.className = 'stat';
      const label = document.createElement('span');
      label.className = 'label-caps';
      label.textContent = name;
      const val = document.createElement('span');
      val.className = `stat__value${accent ? ' stat__value--accent' : ''}`;
      val.textContent = value;
      row.append(label, val);
      return row;
    }));
  }

  /* The signature view: the real contour, mirrored about the engine axis,
     with the throat station and exit plane called out like a drawing. */
  renderDiagram({ x_mm, r_mm, throat_index, stats }) {
    const width = Math.max(this.diagram.clientWidth || 720, 320);
    const height = Math.round(Math.min(Math.max(width * 0.42, 240), 380));
    const pad = { top: 30, right: 74, bottom: 34, left: 40 };

    const svg = this.svg;
    svg.setAttribute('viewBox', `0 0 ${width} ${height}`);
    svg.setAttribute('height', height);
    svg.replaceChildren();

    const xMin = Math.min(...x_mm);
    const xMax = Math.max(...x_mm);
    const rMax = Math.max(...r_mm);
    const plotW = width - pad.left - pad.right;
    const plotH = height - pad.top - pad.bottom;
    // One shared scale keeps the drawing proportionally honest.
    const scale = Math.min(plotW / (xMax - xMin || 1), plotH / (2 * rMax || 1));

    const cx = pad.left;
    const cy = pad.top + plotH / 2;
    const X = (x) => cx + (x - xMin) * scale;
    const Y = (r) => cy - r * scale;

    const upper = x_mm.map((x, i) => `${X(x)},${Y(r_mm[i])}`).join(' ');
    const lower = x_mm.map((x, i) => `${X(x)},${Y(-r_mm[i])}`).join(' ');

    svg.append(svgEl('polygon', {
      class: 'contour-fill',
      points: `${upper} ${x_mm.map((x, i) => `${X(x)},${Y(-r_mm[i])}`).reverse().join(' ')}`,
    }));
    svg.append(svgEl('line', {
      class: 'axis-line',
      x1: X(xMin), x2: X(xMax) + 26, y1: cy, y2: cy,
    }));
    svg.append(svgEl('polyline', { class: 'contour', points: upper }));
    svg.append(svgEl('polyline', { class: 'contour contour--ghost', points: lower }));

    // Throat station
    const tx = X(x_mm[throat_index]);
    const tr = r_mm[throat_index];
    svg.append(svgEl('line', {
      class: 'station-line', x1: tx, x2: tx, y1: Y(tr) - 14, y2: Y(-tr) + 14,
    }));
    svg.append(svgEl('circle', { class: 'marker', cx: tx, cy: Y(tr), r: 3.5 }));
    const throatLabel = svgEl('text', {
      class: 'svg-label svg-label--station',
      x: tx, y: Y(tr) - 20, 'text-anchor': 'middle',
    });
    throatLabel.textContent = `throat r=${fmt(stats.throat_radius_mm, 2)}`;
    svg.append(throatLabel);

    // Exit plane
    const ex = X(x_mm[x_mm.length - 1]);
    const er = r_mm[r_mm.length - 1];
    svg.append(svgEl('line', {
      class: 'dim-line', x1: ex, x2: ex + 20, y1: Y(er), y2: Y(er),
    }));
    const exitLabel = svgEl('text', {
      class: 'svg-label svg-label--accent', x: ex + 24, y: Y(er) + 3,
    });
    exitLabel.textContent = `exit r=${fmt(stats.exit_radius_mm, 2)}`;
    svg.append(exitLabel);

    const erLabel = svgEl('text', {
      class: 'svg-label svg-label--accent', x: ex + 24, y: Y(er) + 17,
    });
    erLabel.textContent = `E_r=${fmt(stats.E_r_actual, 2)}`;
    svg.append(erLabel);

    // Overall length dimension
    const dimY = height - pad.bottom + 14;
    svg.append(svgEl('line', {
      class: 'dim-line', x1: X(xMin), x2: X(xMax), y1: dimY, y2: dimY,
    }));
    for (const x of [X(xMin), X(xMax)]) {
      svg.append(svgEl('line', {
        class: 'dim-line', x1: x, x2: x, y1: dimY - 4, y2: dimY + 4,
      }));
    }
    const lenLabel = svgEl('text', {
      class: 'svg-label', x: (X(xMin) + X(xMax)) / 2, y: dimY - 6,
      'text-anchor': 'middle',
    });
    lenLabel.textContent = `L = ${fmt(stats.total_length_mm)} mm`;
    svg.append(lenLabel);
  }
}
