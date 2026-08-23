"""
connection.py — the single `/ws` WebSocket endpoint.

Every client-server interaction goes through here as a JSON message with a
`type` field (see the WebSocket Protocol section of CLAUDE.md). Commands flow
client -> server, events flow server -> client.

Phase 4 (current): `run_simulation` / `stop_simulation` are wired up. The
remaining commands land in the next phase; until then they get an `error`
event back.
"""

import asyncio
import json
import logging
import os
from typing import Any, Awaitable, Callable, Dict, Optional

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from pydantic import ValidationError

from ..core import PARAMS_DIR, RESULTS_DIR, param_schema
from ..version import PROTOCOL_VERSION
from ..services import dxf as dxf_service
from ..services import geometry as geometry_service
from ..services import params as params_service
from ..services import results as results_service
from ..services import settings as settings_service
from ..services.simulation_runner import SimulationRun
from . import protocol as p
from .protocol import sanitize_floats

logger = logging.getLogger(__name__)

router = APIRouter()

# type string -> handler(connection, message) -> None
# Populated in later phases; empty by design right now.
Handler = Callable[["Connection", dict], Awaitable[None]]
HANDLERS: Dict[str, Handler] = {}


def command(type_name: str):
    """Register a coroutine as the handler for one command `type`."""

    def decorator(fn: Handler) -> Handler:
        HANDLERS[type_name] = fn
        return fn

    return decorator


class Connection:
    """One connected client. Owns whatever per-connection state handlers need."""

    def __init__(self, socket: WebSocket):
        self._socket = socket
        self.simulation: Optional[SimulationRun] = None
        self._sim_task: Optional[asyncio.Task] = None
        # One event at a time: the streaming task and the receive loop can both
        # send, and interleaved send_text() calls would corrupt the stream.
        self._send_lock = asyncio.Lock()

    async def send_event(self, event: Any) -> None:
        """Send one event to this client. Accepts a dict or a Pydantic model.

        NaN/Infinity are stripped first: they are not valid JSON and would make
        the browser's JSON.parse throw. `allow_nan=False` then guarantees we
        fail loudly here rather than shipping a broken frame.
        """
        if hasattr(event, "model_dump"):
            event = event.model_dump()
        payload = json.dumps(sanitize_floats(event), allow_nan=False)
        async with self._send_lock:
            await self._socket.send_text(payload)

    async def send_error(self, context: str, message: str) -> None:
        await self.send_event({"type": "error", "context": context, "message": message})


def _validate(model, message: dict):
    """Parse a command payload, raising a readable error for the client."""
    try:
        return model.model_validate(message)
    except ValidationError as exc:
        raise ValueError(f"Invalid payload: {exc}") from exc


# ─────────────────────────────────────────────────────────────────────────────
# Parameters
# ─────────────────────────────────────────────────────────────────────────────

@command("list_params")
async def handle_list_params(conn: "Connection", message: dict) -> None:
    await conn.send_event(p.ParamsListEvt(files=params_service.list_param_files()))


@command("load_params")
async def handle_load_params(conn: "Connection", message: dict) -> None:
    cmd = _validate(p.LoadParamsCmd, message)
    flat, raw = params_service.load(cmd.filename)
    await conn.send_event(
        p.ParamsLoadedEvt(
            filename=cmd.filename,
            flat=flat,
            raw=raw,
            inactive=param_schema.INACTIVE_PARAMS,
            inactive_reasons=param_schema.INACTIVE_REASONS,
        )
    )


@command("save_params")
async def handle_save_params(conn: "Connection", message: dict) -> None:
    cmd = _validate(p.SaveParamsCmd, message)
    name = params_service.save(cmd.filename, cmd.raw, overwrite=True)
    await conn.send_event(p.ParamsSavedEvt(filename=name))


@command("save_params_as")
async def handle_save_params_as(conn: "Connection", message: dict) -> None:
    cmd = _validate(p.SaveParamsAsCmd, message)
    name = params_service.save(cmd.filename, cmd.raw, overwrite=False)
    await conn.send_event(p.ParamsSavedEvt(filename=name))


@command("client_hello")
async def handle_client_hello(conn: "Connection", message: dict) -> None:
    """The page reports its protocol version; warn if it does not match ours.

    A stale uvicorn keeps serving fresh static files with old Python behind
    them, so the page can look current while the backend is not. This is how
    the page finds out. See backend/app/version.py.
    """
    client_version = message.get("protocol_version")
    if client_version == PROTOCOL_VERSION:
        return
    await conn.send_event(p.VersionMismatchEvt(
        server_version=PROTOCOL_VERSION,
        client_version=client_version if isinstance(client_version, int) else -1,
        message=(
            f"This page expects protocol v{client_version}, but the backend "
            f"serving it is v{PROTOCOL_VERSION}. Restart the backend — on "
            f"Windows a second uvicorn can bind the same port while a stale "
            f"one keeps answering."
        ),
    ))


# ─────────────────────────────────────────────────────────────────────────────
# Geometry
# ─────────────────────────────────────────────────────────────────────────────

@command("preview_geometry")
async def handle_preview_geometry(conn: "Connection", message: dict) -> None:
    cmd = _validate(p.PreviewGeometryCmd, message)
    preview = geometry_service.preview_geometry(
        cmd.R_throat, cmd.E_r, cmd.n_grid,
        R_chamber=cmd.R_chamber,
        L_chamber=cmd.L_chamber,
        R_conv_arc=cmd.R_conv_arc,
    )
    await conn.send_event(p.GeometryPreviewEvt(**preview))


@command("export_dxf")
async def handle_export_dxf(conn: "Connection", message: dict) -> None:
    cmd = _validate(p.ExportDxfCmd, message)
    filename = dxf_service.export_dxf(
        R_throat=cmd.R_throat,
        E_r=cmd.E_r,
        n_grid=cmd.n_grid,
        mirror=cmd.mirror,
        spline=cmd.spline,
        labels=cmd.labels,
        filename=cmd.filename,
        R_chamber=cmd.R_chamber,
        L_chamber=cmd.L_chamber,
        R_conv_arc=cmd.R_conv_arc,
    )
    await conn.send_event(p.DxfExportReadyEvt(
        filename=filename, directory=RESULTS_DIR,
    ))


# ─────────────────────────────────────────────────────────────────────────────
# Results
# ─────────────────────────────────────────────────────────────────────────────

@command("list_results")
async def handle_list_results(conn: "Connection", message: dict) -> None:
    await conn.send_event(p.ResultsListEvt(
        files=results_service.list_result_files(), directory=RESULTS_DIR,
    ))


@command("get_results_table")
async def handle_get_results_table(conn: "Connection", message: dict) -> None:
    cmd = _validate(p.GetResultsTableCmd, message)
    path = results_service.safe_results_path(cmd.filename)
    data, headers = results_service.read_results_csv(path)

    n_rows = len(data[headers[0]]) if headers else 0
    rows = [[float(data[col][i]) for col in headers] for i in range(n_rows)]

    await conn.send_event(
        p.ResultsTableEvt(filename=cmd.filename, columns=headers, rows=rows)
    )


@command("get_plot_data")
async def handle_get_plot_data(conn: "Connection", message: dict) -> None:
    cmd = _validate(p.GetPlotDataCmd, message)
    path = results_service.safe_results_path(cmd.filename)
    data, _ = results_service.read_results_csv(path)

    for col in (cmd.x_col, cmd.y_col):
        if col not in data:
            raise ValueError(f"Column not found in file: {col}")

    await conn.send_event(p.PlotDataEvt(
        filename=cmd.filename,
        x_col=cmd.x_col,
        y_col=cmd.y_col,
        x=data[cmd.x_col].tolist(),
        y=data[cmd.y_col].tolist(),
    ))


@command("preview_wall")
async def handle_preview_wall(conn: "Connection", message: dict) -> None:
    cmd = _validate(p.PreviewWallCmd, message)
    path = results_service.safe_results_path(cmd.filename)
    data, _ = results_service.read_results_csv(path)

    color_cols = [cmd.color_by] if cmd.color_by else []
    points = results_service.generate_wall_points(
        data, color_cols,
        enabled=cmd.revolve.enabled,
        start_deg=cmd.revolve.start_deg,
        end_deg=cmd.revolve.end_deg,
        n_planes=cmd.revolve.n_planes,
    )

    color_values = (
        points["props"][cmd.color_by].tolist() if cmd.color_by else None
    )

    await conn.send_event(p.WallPreviewReadyEvt(
        x=points["X"].tolist(),
        y=points["Y"].tolist(),
        z=points["Z"].tolist(),
        color_values=color_values,
        color_label=cmd.color_by,
        n_points=points["n_pts"] * points["n_planes"],
        n_planes=points["n_planes"],
    ))


@command("export_wall")
async def handle_export_wall(conn: "Connection", message: dict) -> None:
    cmd = _validate(p.ExportWallCmd, message)
    path = results_service.safe_results_path(cmd.filename)
    data, _ = results_service.read_results_csv(path)

    selected, resolved = results_service.resolve_fluent_fields(cmd.selected_cols)
    points = results_service.generate_wall_points(
        data, list(selected.keys()),
        enabled=cmd.revolve.enabled,
        start_deg=cmd.revolve.start_deg,
        end_deg=cmd.revolve.end_deg,
        n_planes=cmd.revolve.n_planes,
    )

    stem = cmd.output_name or "nozzle-wall"
    out_path = results_service.unique_results_path(
        params_service.sanitize_name(stem)[:-5], "prof"
    )
    n_total = results_service.write_fluent_profile(
        out_path, points, selected, cmd.operating_pressure_pa
    )

    await conn.send_event(p.WallExportReadyEvt(
        filename=os.path.basename(out_path),
        directory=RESULTS_DIR,
        n_points=n_total,
        fields_exported=list(dict.fromkeys(selected.values())),
        temperature_field_resolved=resolved,
    ))


# ─────────────────────────────────────────────────────────────────────────────
# Settings
# ─────────────────────────────────────────────────────────────────────────────

@command("get_settings")
async def handle_get_settings(conn: "Connection", message: dict) -> None:
    await conn.send_event(p.SettingsEvt(**settings_service.load_settings()))


@command("save_settings")
async def handle_save_settings(conn: "Connection", message: dict) -> None:
    cmd = _validate(p.SaveSettingsCmd, message)
    saved = settings_service.save_settings(cmd.model_dump(exclude={"type"}))
    await conn.send_event(p.SettingsEvt(**saved))


# ─────────────────────────────────────────────────────────────────────────────
# Simulation (Phase 4)
# ─────────────────────────────────────────────────────────────────────────────

@command("run_simulation")
async def handle_run_simulation(conn: "Connection", message: dict) -> None:
    cmd = _validate(p.RunSimulationCmd, message)

    # The old UI prevented this by disabling the Run button while a solve was
    # in flight; nothing stops a stray double-click here, so enforce it.
    if conn.simulation is not None and conn.simulation.is_running:
        await conn.send_error(
            "run_simulation", "A simulation is already running on this connection."
        )
        return

    run = SimulationRun(
        raw_params=cmd.raw_params,
        solver_overrides=cmd.solver_overrides.model_dump(),
        solver_mode=cmd.solver_mode,
    )
    conn.simulation = run

    async def _stream() -> None:
        try:
            await run.run(conn.send_event)
        except Exception as exc:  # noqa: BLE001
            logger.exception("Simulation failed")
            # Some exceptions (a bare `raise NotImplementedError`) stringify to
            # nothing, which makes for a useless error event.
            detail = str(exc) or exc.__class__.__name__
            await conn.send_error("run_simulation", detail)
            await conn.send_event({
                "type": "simulation_complete",
                "returncode": -1,
                "results_file": None,
                "stopped_by_user": False,
            })

    # Run in the background so the receive loop stays responsive to
    # stop_simulation while the solver streams.
    conn._sim_task = asyncio.create_task(_stream())


@command("stop_simulation")
async def handle_stop_simulation(conn: "Connection", message: dict) -> None:
    if conn.simulation is None or not conn.simulation.is_running:
        await conn.send_error("stop_simulation", "No simulation is running.")
        return
    # The final simulation_complete comes from the streaming task once the
    # terminated subprocess closes its stdout.
    conn.simulation.stop()


@router.websocket("/ws")
async def websocket_endpoint(socket: WebSocket) -> None:
    await socket.accept()
    conn = Connection(socket)

    # Announce what we are before the page asks for anything.
    await conn.send_event(p.ServerInfoEvt(
        protocol_version=PROTOCOL_VERSION,
        results_dir=RESULTS_DIR,
        params_dir=PARAMS_DIR,
    ))

    try:
        while True:
            raw = await socket.receive_text()

            try:
                message = json.loads(raw)
            except json.JSONDecodeError as exc:
                await conn.send_error("parse", f"Invalid JSON: {exc}")
                continue

            if not isinstance(message, dict):
                await conn.send_error("parse", "Expected a JSON object")
                continue

            msg_type = message.get("type")
            if not msg_type:
                await conn.send_error("parse", "Message is missing a 'type' field")
                continue

            handler = HANDLERS.get(msg_type)
            if handler is None:
                await conn.send_error(msg_type, f"Unknown command: {msg_type}")
                continue

            try:
                await handler(conn, message)
            except Exception as exc:  # noqa: BLE001 - report, don't drop the connection
                logger.exception("Handler for %s failed", msg_type)
                await conn.send_error(msg_type, str(exc))

    except WebSocketDisconnect:
        logger.info("Client disconnected")
    finally:
        # Don't let a solver subprocess outlive the connection that started it
        # (the old app._on_close() called sim_tab.terminate() for this reason).
        if conn.simulation is not None:
            conn.simulation.stop()
        if conn._sim_task is not None:
            conn._sim_task.cancel()
