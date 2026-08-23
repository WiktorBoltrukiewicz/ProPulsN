/* app.js — boots the shell.
 *
 * Owns the single WSClient and one instance of each section. Sections never
 * reference each other; anything shared goes through this object or an event
 * on the socket.
 */

import { WSClient } from './ws-client.js';
import { GeometrySection } from './geometry.js';
import { ParametersSection } from './parameters.js';
import { SimulationSection } from './simulation.js';
import { ResultsSection } from './results.js';

/* Bump together with PROTOCOL_VERSION in backend/app/version.py.
   tests/test_version_handshake.py fails if these two ever drift apart. */
const PROTOCOL_VERSION = 4;

const TITLES = {
  geometry: 'Geometry',
  parameters: 'Parameters',
  simulation: 'Simulation',
  results: 'Results',
};

class App {
  constructor() {
    this.ws = new WSClient('/ws');
    this.sections = {};
    this.current = null;
    this.sawServerInfo = false;

    this.titleEl = document.getElementById('header-title');
    this.connEl = document.getElementById('conn');
    this.connLabel = document.getElementById('conn-label');
    this.toastsEl = document.getElementById('toasts');

    const ui = {
      toast: (title, detail, kind) => this.toast(title, detail, kind),
      setSolving: (on) => this.sections.geometry?.setSolving(on),
      // The params file supplies everything except the nozzle itself, which
      // Geometry (02) owns and overlays here before a run.
      currentParams: () => {
        const raw = this.sections.parameters?.collect();
        if (!raw) return null;
        return this.sections.geometry?.applyTo(raw) ?? raw;
      },
    };

    this.sections.parameters = new ParametersSection(this.ws, ui);
    this.sections.geometry = new GeometrySection(this.ws, ui);
    this.sections.simulation = new SimulationSection(this.ws, ui);
    this.sections.results = new ResultsSection(this.ws, ui);

    this.bindNav();
    this.bindConnection();

    this.ws.on('error', (evt) => {
      // Section-owned errors are surfaced inline by that section.
      // client_hello failures are reported by the stale-server banner.
      const owned = ['run_simulation', 'stop_simulation', 'client_hello'];
      if (!owned.includes(evt.context)) {
        this.toast(`${evt.context.replace(/_/g, ' ')} failed`, evt.message, 'error');
      }
    });

    // Announce ourselves first: if a stale backend is answering, the reply
    // tells us before the user spends time wondering why a change "did not
    // take". See backend/app/version.py.
    this.ws.on('version_mismatch', (evt) => this.showStaleServerBanner(evt));
    this.ws.on('server_info', (evt) => {
      this.sawServerInfo = true;
      if (evt.protocol_version !== PROTOCOL_VERSION) {
        this.showStaleServerBanner({
          server_version: evt.protocol_version,
          client_version: PROTOCOL_VERSION,
          message: `This page expects protocol v${PROTOCOL_VERSION}, but the `
            + `backend serving it is v${evt.protocol_version}.`,
        });
      }
    });
    // A backend old enough to predate the handshake answers neither — it just
    // rejects the command it has never heard of, or says nothing at all. Both
    // are conclusive.
    this.ws.on('error', (evt) => {
      if (evt.context === 'client_hello') {
        this.showStaleServerBanner({
          server_version: 'older than the handshake',
          client_version: PROTOCOL_VERSION,
          message: 'The backend does not recognise the version handshake, so '
            + 'it predates this page by some margin.',
        });
      }
    });
    this.ws.on('connection', ({ state }) => {
      if (state !== 'open' || this.sawServerInfo) return;
      clearTimeout(this.helloTimer);
      this.helloTimer = setTimeout(() => {
        if (!this.sawServerInfo) {
          this.showStaleServerBanner({
            server_version: 'unknown',
            client_version: PROTOCOL_VERSION,
            message: 'The backend never identified itself on connect, which '
              + 'means it predates this page.',
          });
        }
      }, 3000);
    });

    this.ws.connect();
    this.ws.send({ type: 'client_hello', protocol_version: PROTOCOL_VERSION });
    this.ws.send({ type: 'get_settings' });

    this.show(location.hash.replace('#', '') || 'parameters');
    window.addEventListener('hashchange', () =>
      this.show(location.hash.replace('#', '') || 'parameters'));
  }

  /* A backend older than this page. Deliberately loud and not dismissible:
     every symptom downstream of it is misleading. */
  showStaleServerBanner({ server_version, client_version, message }) {
    if (document.getElementById('stale-server')) return;
    const bar = document.createElement('div');
    bar.className = 'banner banner--error';
    bar.id = 'stale-server';
    bar.setAttribute('role', 'alert');

    const strong = document.createElement('strong');
    strong.textContent = 'Backend is out of date — restart it';
    const text = document.createElement('span');
    text.textContent = ` ${message} Stop every process listening on this port `
      + `and start one again; on Windows a second uvicorn can bind a port a `
      + `stale one is still answering on.`;
    const detail = document.createElement('code');
    detail.textContent = `page v${client_version} · server v${server_version}`;

    bar.append(strong, text, detail);
    document.querySelector('.main')?.prepend(bar);
  }

  bindNav() {
    this.navItems = [...document.querySelectorAll('.nav__item')];
    this.navItems.forEach((item) => {
      item.addEventListener('click', () => { location.hash = item.dataset.section; });
    });
  }

  bindConnection() {
    this.ws.on('connection', ({ state }) => {
      this.connEl.dataset.state = state;
      this.connLabel.textContent = {
        connecting: 'Connecting…',
        open: 'Connected',
        closed: 'Reconnecting…',
      }[state] || state;
    });
  }

  show(name) {
    if (!this.sections[name]) name = 'parameters';
    this.current = name;

    document.querySelectorAll('.section').forEach((section) => {
      if (section.id === `section-${name}`) section.setAttribute('data-active', '');
      else section.removeAttribute('data-active');
    });
    this.navItems.forEach((item) => {
      if (item.dataset.section === name) item.setAttribute('aria-current', 'page');
      else item.removeAttribute('aria-current');
    });

    this.titleEl.textContent = TITLES[name];
    this.sections[name].activate?.();
  }

  toast(title, detail = '', kind = '') {
    const toast = document.createElement('div');
    toast.className = `toast${kind ? ` toast--${kind}` : ''}`;
    toast.setAttribute('role', 'status');

    const heading = document.createElement('strong');
    heading.textContent = title;
    toast.append(heading);

    if (detail) {
      const path = document.createElement('span');
      path.className = 'toast__path';
      path.textContent = detail;
      toast.append(path);
    }

    this.toastsEl.append(toast);
    setTimeout(() => toast.remove(), 6000);
  }
}

new App();
