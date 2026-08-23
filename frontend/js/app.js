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
      const owned = ['run_simulation', 'stop_simulation'];
      if (!owned.includes(evt.context)) {
        this.toast(`${evt.context.replace(/_/g, ' ')} failed`, evt.message, 'error');
      }
    });

    this.ws.connect();
    this.ws.send({ type: 'get_settings' });

    this.show(location.hash.replace('#', '') || 'parameters');
    window.addEventListener('hashchange', () =>
      this.show(location.hash.replace('#', '') || 'parameters'));
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
