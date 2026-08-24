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

/* Owned by other sections, so they are not editable here: the contour is set
   in Geometry (02), and the whole solver box — grid, iteration cap, tolerance,
   relaxation and mode — in Simulation (03). Each value has exactly one field
   in the app; these still round-trip through save, they are hidden, not
   dropped. */
const OWNED_ELSEWHERE = new Set([
  'R_throat', 'E_r', 'R_chamber', 'L_chamber', 'R_conv_arc', 'n_grid',
  'max_iterations', 'tol', 'relax', 'solver_mode',
]);

/* The `_meta` header. Its entries are plain strings, not {value, unit, ...},
   so it is built separately from the parameter cards.

   This is the part of the file that matters once a config is shared: what it
   is, who made it, which revision. `created` / `modified` / `format` are the
   program's own bookkeeping (see param_schema.stamp_meta) and are shown
   read-only — the app fills them in on every save. `author` is never guessed;
   ProPulsN has no idea who you are, so the field is offered and left blank. */
const META_FIELDS = [
  ['name', 'What this configuration is called', false],
  ['description', 'What the engine is, or what it is for', false],
  ['author', 'Who designed it — shown to whoever you share the file with', false],
  ['version', 'Your own revision tag, e.g. 1.2', false],
  ['created', 'First saved', true],
  ['modified', 'Last saved', true],
  ['format', 'File format ProPulsN wrote', true],
];

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
    this.fields = new Map();     // input -> {sectionKey, key, ...}
    this.metaFields = new Map(); // input -> _meta key
    this.pendingUpload = null;   // a parsed file waiting for a free name

    this.root.querySelector('#param-load')
      .addEventListener('click', () => this.load(this.fileSelect.value));
    this.root.querySelector('#param-refresh')
      .addEventListener('click', () => this.listFiles());
    this.root.querySelector('#param-save')
      .addEventListener('click', () => this.save(false));
    this.root.querySelector('#param-saveas')
      .addEventListener('click', () => this.save(true));

    this.uploadInput = this.root.querySelector('#param-upload-file');
    this.root.querySelector('#param-upload')
      .addEventListener('click', () => this.uploadInput.click());
    this.uploadInput.addEventListener('change', () => {
      const [file] = this.uploadInput.files;
      if (file) this.uploadFile(file);
      this.uploadInput.value = '';   // so the same file can be picked twice
    });
    this.root.querySelector('#param-download')
      .addEventListener('click', () => this.download());

    ws.on('params_list', (evt) => this.renderFileList(evt.files));
    ws.on('params_exported', (evt) => this.saveToDisk(evt.filename, evt.content));
    ws.on('params_loaded', (evt) => this.renderParams(evt));
    ws.on('params_saved', (evt) => {
      this.setStatus(`Saved ${evt.filename}`, 'ok');
      this.ui.toast('Parameters saved', evt.filename, 'ok');
      this.listFiles();
      // An upload lands as a save; open it once it is on disk so the user is
      // looking at what they just brought in.
      if (this.pendingUpload === evt.filename) {
        this.pendingUpload = null;
        this.load(evt.filename);
      }
    });
    ws.on('error', (evt) => {
      if (evt.context !== 'save_params_as' || !this.pendingUpload) return;
      const taken = this.pendingUpload;
      this.pendingUpload = null;
      this.setStatus(`Could not upload as ${taken}: ${evt.message}`, 'error');
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

  renderParams({ filename, flat, raw, inactive, inactive_reasons,
                 required, missing, warnings }) {
    this.filename = filename;
    this.flat = flat;
    this.raw = raw;
    this.inactive = inactive || {};
    this.inactiveReasons = inactive_reasons || {};
    this.required = required || {};
    this.fields.clear();
    this.metaFields.clear();

    // Required parameters this file does not carry. They still get a field —
    // an empty one, flagged — because a value the program needs has to be
    // askable for. Nothing is filled in on the user's behalf.
    const gaps = new Map();               // section key -> [param key, ...]
    for (const key of missing || []) {
      const spec = this.required[key];
      if (!spec || OWNED_ELSEWHERE.has(key)) continue;   // asked for elsewhere
      if (!gaps.has(spec.section)) gaps.set(spec.section, []);
      gaps.get(spec.section).push(key);
    }

    const cards = [this.buildMetaCard(raw._meta || {})];
    for (const sectionKey of new Set([...Object.keys(raw), ...gaps.keys()])) {
      if (sectionKey === '_meta') continue;   // built above, by hand
      const section = raw[sectionKey];
      const entries = (section && typeof section === 'object')
        ? Object.entries(section).filter(
          ([key, value]) => key !== '_description' && value && typeof value === 'object'
            && 'value' in value && !OWNED_ELSEWHERE.has(key),
        )
        : [];

      // A section the file omits entirely still appears if the solver needs
      // something from it.
      for (const key of gaps.get(sectionKey) || []) {
        const { unit, description } = this.required[key];
        entries.push([key, { value: '', unit, description }, true]);
      }

      // A section holding nothing but geometry disappears entirely.
      if (!entries.length) continue;
      cards.push(this.buildCard(sectionKey, section || {}, entries));
    }

    // A file from a newer ProPulsN still loads; the note says so, rather
    // than leaving the gaps below looking like the user's own doing.
    for (const text of warnings || []) {
      const note = document.createElement('p');
      note.className = 'note note--warn';
      note.textContent = text;
      cards.unshift(note);
    }

    // Keep the picker pointing at what is actually open — an upload loads a
    // file the dropdown was not showing.
    if ([...this.fileSelect.options].some((o) => o.value === filename)) {
      this.fileSelect.value = filename;
    }

    this.cardsEl.replaceChildren(...cards);
    const gapCount = [...gaps.values()].reduce((n, list) => n + list.length, 0);
    this.setStatus(
      gapCount
        ? `${filename} — ${this.fields.size} parameters, ${gapCount} still to fill in`
        : `${filename} — ${this.fields.size} parameters`,
      gapCount ? 'error' : 'ok',
    );
    this.broadcastChange();
  }

  /** The `_meta` header, as an editable card. */
  buildMetaCard(meta) {
    const card = document.createElement('div');
    card.className = 'panel panel--quiet';

    const head = document.createElement('div');
    head.className = 'panel__head';
    const title = document.createElement('h3');
    title.className = 'panel__title';
    title.textContent = SECTION_TITLES._meta;
    const note = document.createElement('span');
    note.className = 'label-caps';
    note.textContent = 'travels with the file when you share it';
    head.append(title, note);

    const body = document.createElement('div');
    body.className = 'panel__body';
    const grid = document.createElement('div');
    grid.className = 'field-grid';

    for (const [key, description, readOnly] of META_FIELDS) {
      const wrap = document.createElement('label');
      wrap.className = readOnly ? 'field field--inactive' : 'field';

      const labelRow = document.createElement('span');
      labelRow.className = 'field__label';
      const name = document.createElement('span');
      name.className = 'field__name';
      name.textContent = key;
      labelRow.append(name);

      const input = document.createElement('input');
      input.className = 'input';
      input.type = 'text';
      input.spellcheck = false;
      input.value = meta[key] === undefined || meta[key] === null
        ? '' : String(meta[key]);

      if (readOnly) {
        input.disabled = true;
        input.title = 'Filled in by ProPulsN when the file is saved.';
      } else {
        this.metaFields.set(input, key);
      }

      const desc = document.createElement('span');
      desc.className = 'field__desc';
      desc.textContent = description;

      wrap.append(labelRow, input, desc);
      grid.append(wrap);
    }

    body.append(grid);
    card.append(head, body);
    return card;
  }

  /** Ask the server for this config as a file, to keep or to send on.
   *
   *  Download and Save differ only in where the file lands, so they must not
   *  differ in what the file contains. Building the JSON here in the page
   *  would mean a second thing that writes `_meta` — so the assembled config
   *  goes to the server, gets normalised and stamped by exactly the code that
   *  handles a save, and comes back as text. Nothing is written to params/.
   */
  download() {
    const raw = this.ui.currentParams?.() ?? this.collect();
    if (!raw) {
      this.setStatus('Load a parameter file first.', 'error');
      return;
    }
    // The same guard Save uses: collect() keeps the previous value for a field
    // it cannot parse, so downloading past this would hand over a file that
    // quietly disagrees with what is on screen.
    if (this.cardsEl.querySelector('.input--invalid')) {
      this.setStatus('Some values are not valid numbers.', 'error');
      return;
    }
    this.setStatus('Preparing download…');
    this.ws.send({
      type: 'export_params',
      filename: this.filename || 'engine.json',
      raw,
    });
  }

  /** Hand a finished config to the browser as a file. */
  saveToDisk(filename, content) {
    const blob = new Blob([content], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = filename;
    document.body.append(link);
    link.click();
    link.remove();
    setTimeout(() => URL.revokeObjectURL(url), 10000);
    this.setStatus(`Downloaded ${filename}`, 'ok');
    this.ui.toast('Config downloaded', filename, 'ok');
  }

  /** Take a config file from this computer and add it to the app's library.
   *
   *  Parsed here so a plainly wrong file is refused before it reaches the
   *  server, then stored through the ordinary save_params_as command — which
   *  refuses to overwrite, so an upload can never replace a config you have.
   *  The server checks the shape again, and stamps `_meta`, on the way in.
   */
  uploadFile(file) {
    const reader = new FileReader();
    reader.onerror = () => this.setStatus(`Could not read ${file.name}.`, 'error');
    reader.onload = () => {
      let raw;
      try {
        raw = JSON.parse(reader.result);
      } catch (err) {
        this.setStatus(`${file.name} is not valid JSON: ${err.message}`, 'error');
        return;
      }
      if (!raw || typeof raw !== 'object' || Array.isArray(raw)) {
        this.setStatus(`${file.name} is not a ProPulsN parameter file.`, 'error');
        return;
      }
      const name = file.name.toLowerCase().endsWith('.json')
        ? file.name : `${file.name}.json`;
      this.pendingUpload = name;
      this.setStatus(`Uploading ${name}…`);
      this.ws.send({ type: 'save_params_as', filename: name, raw });
    };
    reader.readAsText(file);
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

    for (const [key, entry, isMissing] of entries) {
      grid.append(this.buildField(sectionKey, key, entry, isMissing));
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

  buildField(sectionKey, key, entry, isMissing = false) {
    const reason = this.inactive[key];
    const wrap = document.createElement('label');
    wrap.className = reason ? 'field field--inactive' : 'field';
    if (isMissing) wrap.classList.add('field--required');

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
    if (isMissing) {
      input.classList.add('input--empty');
      input.placeholder = 'required';
      labelRow.append(this.buildRequiredTag());
    }

    this.fields.set(input, {
      sectionKey,
      key,
      original: entry.value,
      // A field standing in for a key the file lacks has no original value to
      // infer a type from; everything the solver requires is a number.
      numeric: isMissing || typeof entry.value === 'number',
      required: this.required?.[key]?.required === true,
    });

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

  buildRequiredTag() {
    const tag = document.createElement('span');
    tag.className = 'tag tag--required';
    tag.textContent = 'required';
    return tag;
  }

  onEdit(input) {
    const meta = this.fields.get(input);
    const text = input.value.trim();
    const invalid = meta.numeric && text !== '' && !Number.isFinite(Number(text));
    input.classList.toggle('input--invalid', invalid);
    // An emptied required field is not "invalid input" — it is a value the
    // program still needs, and it keeps the run blocked until it is supplied.
    input.classList.toggle('input--empty', meta.required && text === '');
    this.refreshGapCount();
    if (!invalid) this.broadcastChange();
  }

  /** Restate how much is still missing, as the user fills it in. */
  refreshGapCount() {
    if (!this.filename) return;
    const remaining = this.issues().length;
    this.setStatus(
      remaining
        ? `${this.filename} — ${this.fields.size} parameters, `
          + `${remaining} still to fill in`
        : `${this.filename} — ${this.fields.size} parameters`,
      remaining ? 'error' : 'ok',
    );
  }

  /** Required parameters with nothing usable in their field, by key. */
  issues() {
    const out = [];
    for (const [input, meta] of this.fields) {
      if (!meta.required) continue;
      const text = input.value.trim();
      if (text === '' || (meta.numeric && !Number.isFinite(Number(text)))) {
        out.push(meta.key);
      }
    }
    return out;
  }

  /** Current edits merged back into the nested structure. */
  collect() {
    if (!this.raw) return null;
    const raw = structuredClone(this.raw);

    // The `_meta` header first — it is what identifies the file to whoever
    // receives it. The read-only fields are not in metaFields; the server
    // stamps those on save.
    if (this.metaFields.size) {
      raw._meta = raw._meta && typeof raw._meta === 'object' ? raw._meta : {};
      for (const [input, key] of this.metaFields) {
        raw._meta[key] = input.value.trim();
      }
    }
    for (const [input, { sectionKey, key, original, numeric }] of this.fields) {
      const text = input.value.trim();
      const target = raw[sectionKey]?.[key];

      if (!target) {
        // A field standing in for a key the file lacks. Once it has a value,
        // write a complete entry so the gap closes for good on save.
        if (text === '') continue;
        const { unit, description } = this.required[key] || {};
        raw[sectionKey] = raw[sectionKey] || {};
        raw[sectionKey][key] = {
          value: numeric ? Number(text) : text,
          unit: unit ?? '',
          description: description ?? '',
        };
        continue;
      }

      if (numeric) {
        const value = Number(text);
        // An emptied field keeps whatever the file had. Number('') is 0, and
        // silently saving a zero is exactly the kind of invented value this
        // whole change is about.
        if (text === '' || !Number.isFinite(value)) continue;
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
    for (const [input, { key, numeric }] of this.fields) {
      const text = input.value.trim();
      if (numeric) {
        const value = Number(text);
        if (text !== '' && Number.isFinite(value)) flat[key] = value;
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
