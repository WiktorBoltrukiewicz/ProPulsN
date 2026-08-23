/* results.js — Results section.
 *
 * Replaces the old Results tab: file list, Plot Creator, Results Table and
 * Wall Export (with the 3D point-cloud preview and Fluent .prof export).
 *
 * Refreshes itself when a run finishes by listening for `simulation_complete`
 * — the Simulation section never calls in here directly.
 */

import { drawPlot } from './svg-plot.js';

const COORD_COLS = new Set(['x_m', 'r_m']);
const FLUENT_FIELDS = {
  T_K: 'temperature',
  T_aw_K: 'temperature',
  P_Pa: 'pressure',
  M: 'mach-number',
  h_gas_W_m2K: 'heat-transfer-coefficient',
};
const TABLE_PAGE = 100;

export class ResultsSection {
  constructor(ws, ui) {
    this.ws = ws;
    this.ui = ui;
    this.root = document.getElementById('section-results');

    this.fileSelect = this.root.querySelector('#res-file');
    this.statusEl = this.root.querySelector('#res-status');
    this.plotSvg = this.root.querySelector('#res-plot');
    this.xSelect = this.root.querySelector('#res-x');
    this.ySelect = this.root.querySelector('#res-y');
    this.tableWrap = this.root.querySelector('#res-table');
    this.pageLabel = this.root.querySelector('#res-page-label');
    this.fieldsEl = this.root.querySelector('#wall-fields');
    this.colorSelect = this.root.querySelector('#wall-color');
    this.previewHost = this.root.querySelector('#wall-canvas');
    this.previewMeta = this.root.querySelector('#wall-meta');
    this.dirEl = this.root.querySelector('#res-dir');

    this.revolve = {
      enabled: this.root.querySelector('#wall-revolve'),
      start: this.root.querySelector('#wall-start'),
      end: this.root.querySelector('#wall-end'),
      planes: this.root.querySelector('#wall-planes'),
    };
    this.opPressure = this.root.querySelector('#wall-op');

    this.columns = [];
    this.rows = [];
    this.page = 0;
    this.filename = null;
    this.preview = null;

    this.bindSubviews();
    this.bindControls();

    ws.on('results_list', (evt) => {
      this.renderFileList(evt.files);
      this.showDirectory(evt.directory);
    });
    ws.on('results_table', (evt) => this.renderTable(evt));
    ws.on('plot_data', (evt) => this.renderPlot(evt));
    ws.on('wall_preview_ready', (evt) => this.renderPreview(evt));
    ws.on('wall_export_ready', (evt) => {
      this.setStatus(`Wrote ${evt.filename} (${evt.n_points.toLocaleString()} points)`, 'ok');
      this.showDirectory(evt.directory);
      const note = evt.temperature_field_resolved
        ? `Fields: ${evt.fields_exported.join(', ')} — temperature taken from ${evt.temperature_field_resolved}`
        : `Fields: ${evt.fields_exported.join(', ')}`;
      this.ui.toast('Fluent profile exported', `${evt.filename} · ${note}`, 'ok');
    });

    // Section communication happens only through events on the shared socket.
    ws.on('simulation_complete', (evt) => {
      if (evt.returncode === 0 && !evt.stopped_by_user) {
        this.pendingSelect = evt.results_file;
        this.list();
      }
    });
    ws.on('connection', ({ state }) => { if (state === 'open') this.list(); });

    let pending;
    window.addEventListener('resize', () => {
      clearTimeout(pending);
      pending = setTimeout(() => {
        this.preview?.resize();
        if (this.lastPlot) this.renderPlot(this.lastPlot);
      }, 150);
    });
  }

  activate() {
    if (!this.fileSelect.options.length) this.list();
    this.preview?.resize();
  }

  bindSubviews() {
    const pills = [...this.root.querySelectorAll('.pill[data-subview]')];
    const views = [...this.root.querySelectorAll('.subview')];
    pills.forEach((pill) => {
      pill.addEventListener('click', () => {
        pills.forEach((p) => p.setAttribute('aria-selected', String(p === pill)));
        const target = pill.dataset.subview;
        views.forEach((v) => {
          if (v.dataset.subview === target) v.setAttribute('data-active', '');
          else v.removeAttribute('data-active');
        });
        if (target === 'wall') this.preview?.resize();
      });
    });
  }

  bindControls() {
    this.root.querySelector('#res-load')
      .addEventListener('click', () => this.load(this.fileSelect.value));
    this.root.querySelector('#res-refresh')
      .addEventListener('click', () => this.list());
    this.root.querySelector('#res-draw')
      .addEventListener('click', () => this.requestPlot());
    this.root.querySelector('#res-clear')
      .addEventListener('click', () => this.clearPlot());
    this.root.querySelector('#res-prev')
      .addEventListener('click', () => this.turnPage(-1));
    this.root.querySelector('#res-next')
      .addEventListener('click', () => this.turnPage(1));
    this.root.querySelector('#wall-all')
      .addEventListener('click', () => this.toggleAll(true));
    this.root.querySelector('#wall-none')
      .addEventListener('click', () => this.toggleAll(false));
    this.root.querySelector('#wall-preview')
      .addEventListener('click', () => this.requestPreview());
    this.root.querySelector('#wall-export')
      .addEventListener('click', () => this.exportWall());

    this.revolve.enabled.addEventListener('change', () => this.syncRevolve());
    this.syncRevolve();
  }

  syncRevolve() {
    const on = this.revolve.enabled.checked;
    for (const key of ['start', 'end', 'planes']) {
      this.revolve[key].disabled = !on;
    }
  }

  list() { this.ws.send({ type: 'list_results' }); }

  load(filename) {
    if (!filename) return;
    this.filename = filename;
    this.page = 0;
    this.setStatus(`Loading ${filename}…`);
    this.ws.send({ type: 'get_results_table', filename });
  }

  renderFileList(files) {
    const keep = this.pendingSelect || this.fileSelect.value || this.filename;
    this.pendingSelect = null;

    this.fileSelect.replaceChildren(...files.map((name) => {
      const option = document.createElement('option');
      option.value = name;
      option.textContent = name;
      return option;
    }));

    if (!files.length) {
      this.setStatus('No results yet — run a simulation.');
      return;
    }
    if (keep && files.includes(keep)) this.fileSelect.value = keep;
    this.load(this.fileSelect.value);
  }

  renderTable({ filename, columns, rows }) {
    this.filename = filename;
    this.columns = columns;
    this.rows = rows;
    this.page = 0;

    this.fillColumnPickers();
    this.buildFluentCheckboxes();
    this.drawTablePage();
    this.setStatus(`${filename} — ${rows.length} rows × ${columns.length} columns`, 'ok');

    if (this.xSelect.value && this.ySelect.value) this.requestPlot();
  }

  fillColumnPickers() {
    const fill = (select, preferred) => {
      const previous = select.value;
      select.replaceChildren(...this.columns.map((col) => {
        const option = document.createElement('option');
        option.value = col;
        option.textContent = col;
        return option;
      }));
      if (previous && this.columns.includes(previous)) select.value = previous;
      else if (preferred && this.columns.includes(preferred)) select.value = preferred;
    };
    fill(this.xSelect, 'x_m');
    fill(this.ySelect, 'M');

    const props = this.columns.filter((c) => !COORD_COLS.has(c));
    const previous = this.colorSelect.value;
    this.colorSelect.replaceChildren(
      new Option('(none)', ''),
      ...props.map((c) => new Option(c, c)),
    );
    if (previous && props.includes(previous)) this.colorSelect.value = previous;
  }

  buildFluentCheckboxes() {
    const available = this.columns.filter((c) => c in FLUENT_FIELDS);
    if (!available.length) {
      const empty = document.createElement('p');
      empty.className = 'empty';
      empty.textContent = 'This file has no Fluent-recognised properties.';
      this.fieldsEl.replaceChildren(empty);
      return;
    }
    this.fieldsEl.replaceChildren(...available.map((col) => {
      const label = document.createElement('label');
      label.className = 'checkbox';
      const box = document.createElement('input');
      box.type = 'checkbox';
      box.value = col;
      box.checked = true;
      const text = document.createElement('span');
      text.textContent = `${col} → ${FLUENT_FIELDS[col]}`;
      label.append(box, text);
      return label;
    }));
  }

  toggleAll(checked) {
    this.fieldsEl.querySelectorAll('input[type=checkbox]')
      .forEach((box) => { box.checked = checked; });
  }

  selectedFields() {
    return [...this.fieldsEl.querySelectorAll('input[type=checkbox]:checked')]
      .map((box) => box.value);
  }

  /* ── Table ─────────────────────────────────────────────────────────── */

  turnPage(delta) {
    const pages = Math.max(Math.ceil(this.rows.length / TABLE_PAGE), 1);
    this.page = Math.min(Math.max(this.page + delta, 0), pages - 1);
    this.drawTablePage();
  }

  drawTablePage() {
    if (!this.columns.length) return;
    const start = this.page * TABLE_PAGE;
    const slice = this.rows.slice(start, start + TABLE_PAGE);

    const table = document.createElement('table');
    table.className = 'table';

    const thead = document.createElement('thead');
    const headRow = document.createElement('tr');
    headRow.append(...['#', ...this.columns].map((col) => {
      const th = document.createElement('th');
      th.textContent = col;
      return th;
    }));
    thead.append(headRow);

    const tbody = document.createElement('tbody');
    slice.forEach((row, i) => {
      const tr = document.createElement('tr');
      const index = document.createElement('td');
      index.textContent = String(start + i + 1);
      tr.append(index);
      row.forEach((value) => {
        const td = document.createElement('td');
        td.textContent = value == null ? '—' : formatCell(value);
        tr.append(td);
      });
      tbody.append(tr);
    });

    table.append(thead, tbody);
    this.tableWrap.replaceChildren(table);

    const pages = Math.max(Math.ceil(this.rows.length / TABLE_PAGE), 1);
    this.pageLabel.textContent =
      `${this.rows.length} rows · page ${this.page + 1} / ${pages}`;
  }

  /* ── Plot ──────────────────────────────────────────────────────────── */

  requestPlot() {
    if (!this.filename) return;
    this.ws.send({
      type: 'get_plot_data',
      filename: this.filename,
      x_col: this.xSelect.value,
      y_col: this.ySelect.value,
    });
  }

  /* The desktop app had an "Open Results Folder" button. A browser cannot open
     a folder, so show where the server actually wrote the files instead. */
  showDirectory(directory) {
    if (!this.dirEl || !directory) return;
    this.dirEl.textContent = directory;
  }

  /** Empty the chart, as the desktop Plot Creator's Clear button did. */
  clearPlot() {
    this.lastPlot = null;
    drawPlot(this.plotSvg, [], { xLabel: '', yLabel: '' });
    this.setStatus('Plot cleared.');
  }

  renderPlot(evt) {
    this.lastPlot = evt;
    const accent = getComputedStyle(document.documentElement)
      .getPropertyValue('--accent').trim();
    const points = evt.x.map((x, i) => [x, evt.y[i]])
      .filter(([x, y]) => x != null && y != null);
    drawPlot(this.plotSvg, [{ name: evt.y_col, color: accent, points }], {
      xLabel: evt.x_col,
      yLabel: evt.y_col,
    });
  }

  /* ── Wall export ───────────────────────────────────────────────────── */

  revolveConfig() {
    return {
      enabled: this.revolve.enabled.checked,
      start_deg: Number(this.revolve.start.value) || 0,
      end_deg: Number(this.revolve.end.value) || 360,
      n_planes: parseInt(this.revolve.planes.value, 10) || 36,
    };
  }

  requestPreview() {
    if (!this.filename) {
      this.setStatus('Load a results file first.', 'error');
      return;
    }
    this.setStatus('Building point cloud…');
    this.ws.send({
      type: 'preview_wall',
      filename: this.filename,
      color_by: this.colorSelect.value || null,
      revolve: this.revolveConfig(),
    });
  }

  async renderPreview(evt) {
    if (!this.preview) {
      // Loaded on demand: three.js is 670KB and most sessions never open this.
      const { WallPreview3D } = await import('./wall-preview-3d.js');
      this.preview = new WallPreview3D(this.previewHost);
    }
    this.preview.setPoints(evt.x, evt.y, evt.z, evt.color_values, evt.color_label);

    const bits = [`${evt.n_points.toLocaleString()} points`, `${evt.n_planes} planes`];
    if (evt.color_label && this.preview.range) {
      const { lo, hi } = this.preview.range;
      bits.push(`${evt.color_label}: ${formatCell(lo)} … ${formatCell(hi)}`);
    }
    this.previewMeta.textContent = bits.join('  ·  ');
    this.setStatus(`Preview ready — ${evt.n_points.toLocaleString()} points`, 'ok');
  }

  exportWall() {
    if (!this.filename) {
      this.setStatus('Load a results file first.', 'error');
      return;
    }
    const selected = this.selectedFields();
    if (!selected.length) {
      this.setStatus('Select at least one field to export.', 'error');
      return;
    }
    this.setStatus('Writing Fluent profile…');
    this.ws.send({
      type: 'export_wall',
      filename: this.filename,
      selected_cols: selected,
      revolve: this.revolveConfig(),
      operating_pressure_pa: Number(this.opPressure.value) || 101325,
      output_name: 'nozzle-wall',
    });
  }

  setStatus(text, kind = '') {
    this.statusEl.textContent = text;
    this.statusEl.className = `status${kind ? ` status--${kind}` : ''}`;
  }
}

function formatCell(value) {
  const abs = Math.abs(value);
  if (value === 0) return '0';
  if (abs >= 1e5 || abs < 1e-3) return value.toExponential(3);
  return String(Number(value.toPrecision(6)));
}
