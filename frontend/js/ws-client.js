/* ws-client.js — the only channel to the server.
 *
 * Sections never call into each other; they send commands and listen for
 * events on this shared connection. Reconnects automatically so a restarted
 * backend (uvicorn --reload) doesn't leave a dead page.
 */

export class WSClient {
  constructor(path = '/ws') {
    const scheme = location.protocol === 'https:' ? 'wss:' : 'ws:';
    this.url = `${scheme}//${location.host}${path}`;
    this.socket = null;
    this.listeners = new Map();   // type -> Set<fn>
    this.queue = [];              // commands sent before the socket opened
    this.retryDelay = 500;
  }

  connect() {
    this.emitLocal('connection', { state: 'connecting' });
    this.socket = new WebSocket(this.url);

    this.socket.onopen = () => {
      this.retryDelay = 500;
      this.emitLocal('connection', { state: 'open' });
      const pending = this.queue.splice(0);
      pending.forEach((cmd) => this.send(cmd));
    };

    this.socket.onmessage = (event) => {
      let message;
      try {
        message = JSON.parse(event.data);
      } catch {
        return;
      }
      this.emitLocal(message.type, message);
    };

    this.socket.onclose = () => {
      this.emitLocal('connection', { state: 'closed' });
      // Back off up to 8s so a stopped server doesn't spin the tab.
      setTimeout(() => this.connect(), this.retryDelay);
      this.retryDelay = Math.min(this.retryDelay * 2, 8000);
    };

    // 'error' is always followed by 'close'; let close drive the retry.
    this.socket.onerror = () => {};
  }

  get isOpen() {
    return this.socket && this.socket.readyState === WebSocket.OPEN;
  }

  send(command) {
    if (!this.isOpen) {
      this.queue.push(command);
      return;
    }
    this.socket.send(JSON.stringify(command));
  }

  on(type, callback) {
    if (!this.listeners.has(type)) this.listeners.set(type, new Set());
    this.listeners.get(type).add(callback);
    return () => this.off(type, callback);
  }

  off(type, callback) {
    this.listeners.get(type)?.delete(callback);
  }

  emitLocal(type, message) {
    this.listeners.get(type)?.forEach((fn) => {
      try {
        fn(message);
      } catch (err) {
        console.error(`listener for "${type}" failed`, err);
      }
    });
  }
}
