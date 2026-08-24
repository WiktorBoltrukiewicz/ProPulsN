"""
Smoke-test a running ProPulsN container.

    python scripts/smoke_container.py [base_url]

Checks the things a container can break that a unit test cannot:

  * the page is served at all (the static mount resolved inside the image);
  * the WebSocket accepts a connection and greets with `server_info`;
  * a real solve runs — which means the server successfully spawned
    `python main.py` as a *subprocess inside the container*, the single most
    likely thing to work on a developer's machine and fail in an image;
  * output lands in the mounted results directory and is downloadable through
    `GET /files/`, so the volume is writable by the container's user.

Exits non-zero with a readable reason on the first failure.
"""

import json
import sys
import urllib.request

try:
    from websockets.sync.client import connect
except ImportError:                                   # pragma: no cover
    sys.exit("This needs the `websockets` package: pip install websockets")

BASE = (sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8000").rstrip("/")
WS = BASE.replace("https://", "wss://").replace("http://", "ws://") + "/ws"

# Two iterations: enough to prove the loop streams and completes, fast enough
# that a slow CI runner does not turn this into a timeout.
ITERATIONS = 2


def step(message):
    print(f"  {message}", flush=True)


def fail(message):
    sys.exit(f"FAIL: {message}")


def main():
    step(f"GET {BASE}/")
    with urllib.request.urlopen(BASE + "/", timeout=15) as response:
        page = response.read().decode("utf-8", "replace")
    if response.status != 200:
        fail(f"the page returned {response.status}")
    if "ProPulsN" not in page:
        fail("the page does not look like ProPulsN — is the frontend in the image?")
    if 'id="app-version"' not in page:
        fail("the page is missing the version slot; stale frontend in the image?")

    step(f"connect {WS}")
    with connect(WS, open_timeout=20, max_size=None) as ws:
        greeting = json.loads(ws.recv(timeout=20))
        if greeting.get("type") != "server_info":
            fail(f"expected server_info, got {greeting.get('type')!r}")
        step(f"server_info: protocol v{greeting['protocol_version']}, "
             f"app v{greeting.get('app_version')}")

        step("load_params default.json")
        ws.send(json.dumps({"type": "load_params", "filename": "default.json"}))
        loaded = json.loads(ws.recv(timeout=30))
        if loaded.get("type") != "params_loaded":
            fail(f"load_params returned {loaded.get('type')!r}: "
                 f"{loaded.get('message', '')}")
        if loaded.get("missing"):
            fail(f"the shipped config is incomplete in the image: {loaded['missing']}")

        step(f"run_simulation ({ITERATIONS} iterations, fixed)")
        ws.send(json.dumps({
            "type": "run_simulation",
            "raw_params": loaded["raw"],
            "solver_overrides": {"max_iterations": ITERATIONS},
            "solver_mode": "fixed",
        }))

        saw_log = saw_convergence = False
        results_file = None
        for _ in range(20000):
            event = json.loads(ws.recv(timeout=300))
            kind = event.get("type")
            if kind == "log_line":
                saw_log = True
            elif kind == "convergence_update":
                saw_convergence = True
            elif kind == "error":
                fail(f"the server reported: {event.get('message')}")
            elif kind == "simulation_complete":
                if event.get("returncode") != 0:
                    fail(f"the solver exited {event.get('returncode')} — the "
                         f"subprocess could not run inside the container")
                results_file = event.get("results_file")
                break
        else:
            fail("the run never completed")

    if not saw_log:
        fail("no output streamed — stdout is buffered (PYTHONUNBUFFERED?)")
    if not saw_convergence:
        fail("no convergence updates — the live chart would stay empty")
    if not results_file:
        fail("the run completed but named no results file")
    step(f"solved, wrote {results_file}")

    step(f"GET /files/{results_file}")
    with urllib.request.urlopen(f"{BASE}/files/{results_file}", timeout=30) as response:
        body = response.read()
    if response.status != 200 or not body:
        fail(f"the results file is not downloadable ({response.status})")
    if b"x_m" not in body.split(b"\n", 60)[-1] and b"x_m" not in body[:4000]:
        fail("the downloaded file does not look like a results CSV")
    step(f"downloaded {len(body)} bytes")

    print("OK — the container serves, solves and hands the file back.")


if __name__ == "__main__":
    main()
