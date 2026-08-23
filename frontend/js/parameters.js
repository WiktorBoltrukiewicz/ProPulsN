/* parameters.js — Parameters section.
 *
 * Replaces the old Parameters tab. Fields are generated from the file's own
 * nested structure, so a config with extra sections still renders: each entry
 * carries its label, unit and description, which the desktop app showed and
 * several non-obvious keys genuinely need.
 *
 * Parameters the solver does not read (everything to do with regenerative
 * cooling) arrive in `params_loaded` as an `inactive` map. They are rendered
 * dimmed and read-only, with a note per card saying why — editing them would
 * change nothing, and silently hiding them would lose data the file carries.
 */

const SECTION_TITLES = {
  _meta: 'File info',
  initial_conditions: 'Initial conditions',
  nozzle_geometry: 'Nozzle geometry',
  cooling_channels: 'Cooling channels',
  wall_properties: 'Wall properties',
  gas_properties: 'Gas properties',
  coolant_fuel: 'Coolant',
  solver: 'Solver',
};

/* Owned by other sections, so they are not editable here:
   R_throat / E_r are set in Geometry (02), n_grid in Simulation (03).
   Their values still round-trip through save — they are hidden, not dropped. */
const OWNED_ELSEWHERE = new Set([
  'R_throat', 'E_r', 'R_chamber', 'L_chamber', 'R_conv_arc', 'n_grid',
]);

const prettify = (key) =>
  key.replace(/^_/, '').replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase());

/** Format a number for an input without losing precision. */
const toField = (value) => {
  if (typeof value !== 'number') return String(value ?? '');
  const abs = Math.abs(value);
  if (value !== 0 && (abs >= 1e6 || abs < 1e-4)) return value.toExponential(6);
  return String(value);
};

export class ParametersSection {
  constructor(ws, ui) {
    this.ws = ws;
    this.ui = ui;
    this.root = document.getElementById('section-parameters');
    this.cardsEl = this.root.querySelector('#param-cards');
    this.fileSelect = this.root.querySelector('#param-file');
    this.statusEl = this.root.querySelector('#param-status');

    this.raw = null;
    this.flat = null;
    this.filename = null;
    this.inactive = {};          // param key -> reason code, from the server
    this.inactiveReasons = {};   // reason code -> sentence to show
    this.fields = new Map();   // input -> {section, key}

    this.root.querySelector('#param-load')
      .addEventListener('click', () => this.load(this.fileSelect.value));
    this.root.querySelector('#param-refresh')
      .addEventListener('click', () => this.listFiles());
    this.root.querySelector('#param-save')
      .addEventListener('click', () => this.save(false));
    this.root.querySelector('#param-saveas')
      .addEventListener('click', () => this.save(true));

    ws.on('params_list', (evt) => this.renderFileList(evt.files));
    ws.on('params_loaded', (evt) => this.renderParams(evt));
    ws.on('params_saved', (evt) => {
      this.setStatus(`Saved ${evt.filename}`, 'ok');
      this.ui.toast('Parameters saved', evt.filename, 'ok');
      this.listFiles();
    });
    ws.on('connection', ({ state }) => {
      if (state === 'open') this.listFiles();
    });
  }

  activate() {
    if (!this.raw) this.listFiles();
  }

  listFiles() {
    this.ws.send({ type: 'list_params' });
  }

  load(filename) {
    if (!filename) return;
    this.setStatus(`Loading ${filename}…`);
    this.ws.send({ type: 'load_params', filename });
  }

  renderFileList(files) {
    const previous = this.fileSelect.value || this.filename;
    this.fileSelect.replaceChildren(...files.map((name) => {
      const option = document.createElement('option');
      option.value = name;
      option.textContent = name;
      return option;
    }));
    if (previous && files.includes(previous)) this.fileSelect.value = previous;

    // First visit: open something so the section isn't an empty shell.
    if (!this.raw && files.length) this.load(this.fileSelect.value);
  }

  renderParams({ filename, flat, raw, inactive, inactive_reasons }) {
    this.filename = filename;
    this.flat = flat;
    this.raw = raw;
    this.inactive = inactive || {};
    this.inactiveReasons = inactive_reasons || {};
    this.fields.clear();

    const cards = [];
    for (const [sectionKey, section] of Object.entries(raw)) {
      if (!section || typeof section !== 'object') continue;

      const entries = Object.entries(section).filter(
        ([key, value]) => key !== '_description' && value && typeof value === 'object'
          && 'value' in value && !OWNED_ELSEWHERE.has(key),
      );
      // A section holding nothing but geometry disappears entirely.
      if (!entries.length) continue;

      cards.push(this.buildCard(sectionKey, section, entries));
    }

    this.cardsEl.replaceChildren(...cards);
    this.setStatus(`${filename} — ${this.fields.size} parameters`, 'ok');
    this.broadcastChange();
  }

  buildCard(sectionKey, section, entries) {
    const card = document.createElement('div');
    card.className = 'panel panel--quiet';

    const head = document.createElement('div');
    head.className = 'panel__head';
    const title = document.createElement('h3');
    title.className = 'panel__title';
    title.textContent = SECTION_TITLES[sectionKey] || prettify(sectionKey);
    head.append(title);

    if (section._description) {
      const note = document.createElement('span');
      note.className = 'label-caps';
      note.textContent = section._description;
      head.append(note);
    }

    const reasonsHere = [...new Set(
      entries.map(([key]) => this.inactive[key]).filter(Boolean),
    )];
    const allInactive = reasonsHere.length
      && entries.every(([key]) => this.inactive[key]);
    if (allInactive) card.classList.add('panel--inactive');

    const body = document.createElement('div');
    body.className = 'panel__body';
    const grid = document.createElement('div');
    grid.className = 'field-grid';

    for (const [key, entry] of entries) {
      grid.append(this.buildField(sectionKey, key, entry));
    }
    body.append(grid);

    // One note per distinct reason, rather than repeating a sentence under
    // every greyed field.
    for (const reason of reasonsHere) {
      const note = document.createElement('p');
      note.className = 'note note--inactive';
      note.textContent = this.inactiveReasons[reason]
        || 'Not used by the current solver.';
      body.append(note);
    }

    card.append(head, body);
    return card;
  }

  buildField(sectionKey, key, entry) {
    const reason = this.inactive[key];
    const wrap = document.createElement('label');
    wrap.className = reason ? 'field field--inactive' : 'field';

    const labelRow = document.createElement('span');
    labelRow.className = 'field__label';
    const name = document.createElement('span');
    name.className = 'field__name';
    name.textContent = key;
    labelRow.append(name);

    if (entry.unit) {
      const unit = document.createElement('span');
      unit.className = 'field__unit';
      unit.textContent = entry.unit;
      labelRow.append(unit);
    }

    const input = document.createElement('input');
    input.className = 'input';
    input.value = toField(entry.value);
    input.spellcheck = false;
    // Text, not number: values span 1e-5 to 1e7 and several are exponential.
    input.type = 'text';

    if (reason) {
      // Read-only, not removed: the value still round-trips through save.
      input.disabled = true;
      input.title = this.inactiveReasons[reason]
        || 'Not used by the current solver.';
      labelRow.append(this.buildInactiveTag());
    } else {
      input.addEventListener('input', () => this.onEdit(input));
    }

    this.fields.set(input, { sectionKey, key, original: entry.value });

    wrap.append(labelRow, input);

    if (entry.description) {
      const desc = document.createElement('span');
      desc.className = 'field__desc';
      desc.textContent = entry.description;
      wrap.append(desc);
    }
    return wrap;
  }

  buildInactiveTag() {
    const tag = document.createElement('span');
    tag.className = 'tag tag--inactive';
    tag.textContent = 'not used';
    return tag;
  }

  onEdit(input) {
    const meta = this.fields.get(input);
    const isNumeric = typeof meta.original === 'number';
    const invalid = isNumeric && input.value.trim() !== ''
      && !Number.isFinite(Number(input.value));
    input.classList.toggle('input--invalid', invalid);
    if (!invalid) this.broadcastChange();
  }

  /** Current edits merged back into the nested structure. */
  collect() {
    if (!this.raw) return null;
    const raw = structuredClone(this.raw);
    for (const [input, { sectionKey, key, original }] of this.fields) {
      const target = raw[sectionKey]?.[key];
      if (!target) continue;
      const text = input.value.trim();
      if (typeof original === 'number') {
        const value = Number(text);
        if (!Number.isFinite(value)) continue;
        // Preserve int-ness, as the desktop app did.
        target.value = Number.isInteger(original) && Number.isInteger(value)
          ? value : value;
      } else {
        target.value = text;
      }
    }
    return raw;
  }

  /** Flat view of the current edits, for other sections to consume. */
  flatValues() {
    const flat = { ...(this.flat || {}) };
    for (const [input, { key, original }] of this.fields) {
      if (typeof original === 'number') {
        const value = Number(input.value);
        if (Number.isFinite(value)) flat[key] = value;
      } else {
        flat[key] = input.value;
      }
    }
    return flat;
  }

  broadcastChange() {
    // Geometry and Simulation listen for this instead of reaching in here.
    window.dispatchEvent(new CustomEvent('openengine:params-changed', {
      detail: this.flatValues(),
    }));
  }

  save(asNew) {
    // Save what would actually be solved: these fields plus the nozzle
    // designed in Geometry, which is hidden here but still lives in the file.
    const raw = this.ui.currentParams?.() ?? this.collect();
    if (!raw) {
      this.setStatus('Load a parameter file first.', 'error');
      return;
    }
    if (this.cardsEl.querySelector('.input--invalid')) {
      this.setStatus('Some values are not valid numbers.', 'error');
      return;
    }

    let filename = this.filename;
    if (asNew) {
      filename = window.prompt('Save parameters as', this.filename || 'my-engine.json');
      if (!filename) return;
    }
    this.ws.send({
      type: asNew ? 'save_params_as' : 'save_params',
      filename,
      raw,
    });
  }

  setStatus(text, kind = '') {
    this.statusEl.textContent = text;
    this.statusEl.className = `status${kind ? ` status--${kind}` : ''}`;
  }
}
