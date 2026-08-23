"""
protocol.py — every message that can cross the `/ws` WebSocket.

Commands flow client -> server, events flow server -> client. Each message is
a JSON object whose `type` field selects the model. There is no REST API; this
module is the complete client-server contract (see CLAUDE.md).

Phase 3: schema only. Handlers are registered in later phases.

Note on floats: the solver produces NaN in places (e.g. `T_aw` is pre-filled
with NaN before Stage 1 fills it in). NaN/Infinity are not valid JSON and
`JSON.parse` rejects them, so any field that can carry solver output is typed
`Optional[float]` and NaN/Inf must be sanitised to `None` on the way out —
see `sanitize_floats()` below.
"""

import math
from typing import Annotated, Any, Literal, Optional, Union

from pydantic import BaseModel, Field

from ..core import geometry as geo


# ─────────────────────────────────────────────────────────────────────────────
# Commands (client -> server)
# ─────────────────────────────────────────────────────────────────────────────

class ListParamsCmd(BaseModel):
    type: Literal["list_params"] = "list_params"


class LoadParamsCmd(BaseModel):
    type: Literal["load_params"] = "load_params"
    filename: str                      # basename inside params/, e.g. "default.json"


class SaveParamsCmd(BaseModel):
    type: Literal["save_params"] = "save_params"
    filename: str                      # existing file to overwrite
    raw: dict                          # full nested JSON, round-tripped from params_loaded


class SaveParamsAsCmd(BaseModel):
    type: Literal["save_params_as"] = "save_params_as"
    filename: str                      # new name; sanitised server-side
    raw: dict


class ChamberGeometry(BaseModel):
    """Convergent-section shape. Defaults reproduce the original MATLAB contour."""
    R_chamber: float = geo.R_CHAMBER_DEFAULT
    L_chamber: float = geo.L_CHAMBER_DEFAULT
    R_conv_arc: float = geo.R_CONV_ARC_DEFAULT


class PreviewGeometryCmd(ChamberGeometry):
    type: Literal["preview_geometry"] = "preview_geometry"
    R_throat: float
    E_r: float
    n_grid: int = 100                  # preview resolution, independent of the solver grid


class ExportDxfCmd(ChamberGeometry):
    type: Literal["export_dxf"] = "export_dxf"
    R_throat: float
    E_r: float
    # DXF options, mirroring settings.json (see SettingsEvt)
    n_grid: int = 500
    mirror: bool = False
    spline: bool = True
    labels: bool = False
    filename: Optional[str] = None     # None -> server auto-names via generate_output_filename()


class SolverOverrides(BaseModel):
    """The old Simulation tab's Solver Settings box."""
    n_grid: Optional[int] = None
    max_iterations: Optional[int] = None
    tol: Optional[float] = None
    relax: Optional[float] = None


class RunSimulationCmd(BaseModel):
    type: Literal["run_simulation"] = "run_simulation"
    # Fully assembled client-side (raw nested params + edits), exactly as the
    # old _build_temp_json() did. The server only writes it out and runs it.
    raw_params: dict
    solver_overrides: SolverOverrides = Field(default_factory=SolverOverrides)
    solver_mode: Literal["convergence", "fixed"] = "convergence"


class StopSimulationCmd(BaseModel):
    type: Literal["stop_simulation"] = "stop_simulation"


class ListResultsCmd(BaseModel):
    type: Literal["list_results"] = "list_results"


class GetResultsTableCmd(BaseModel):
    type: Literal["get_results_table"] = "get_results_table"
    filename: str


class GetPlotDataCmd(BaseModel):
    type: Literal["get_plot_data"] = "get_plot_data"
    filename: str
    x_col: str
    y_col: str


class RevolveConfig(BaseModel):
    """Defaults match the old Wall Export tab's fields."""
    enabled: bool = True
    start_deg: float = 0.0
    end_deg: float = 360.0
    n_planes: int = 36


class PreviewWallCmd(BaseModel):
    type: Literal["preview_wall"] = "preview_wall"
    filename: str
    color_by: Optional[str] = None     # column to colour the point cloud by
    revolve: RevolveConfig = Field(default_factory=RevolveConfig)


class ExportWallCmd(BaseModel):
    type: Literal["export_wall"] = "export_wall"
    filename: str
    selected_cols: list[str]           # OpenEngine column names, e.g. ["T_aw_K", "P_Pa"]
    revolve: RevolveConfig = Field(default_factory=RevolveConfig)
    operating_pressure_pa: float = 101325.0   # Fluent gauge offset, subtracted from P_Pa
    output_name: Optional[str] = None


class GetSettingsCmd(BaseModel):
    type: Literal["get_settings"] = "get_settings"


class SaveSettingsCmd(BaseModel):
    type: Literal["save_settings"] = "save_settings"
    dxf_n_grid: int = 500
    dxf_mirror: bool = False
    dxf_spline: bool = True
    dxf_labels: bool = False
    # base_font is intentionally absent: the Qt font-scaling concept does not
    # map to a browser (use browser zoom). See CLAUDE.md.


Command = Annotated[
    Union[
        ListParamsCmd,
        LoadParamsCmd,
        SaveParamsCmd,
        SaveParamsAsCmd,
        PreviewGeometryCmd,
        ExportDxfCmd,
        RunSimulationCmd,
        StopSimulationCmd,
        ListResultsCmd,
        GetResultsTableCmd,
        GetPlotDataCmd,
        PreviewWallCmd,
        ExportWallCmd,
        GetSettingsCmd,
        SaveSettingsCmd,
    ],
    Field(discriminator="type"),
]


# ─────────────────────────────────────────────────────────────────────────────
# Events (server -> client)
# ─────────────────────────────────────────────────────────────────────────────

class ParamsListEvt(BaseModel):
    type: Literal["params_list"] = "params_list"
    files: list[str]                   # basenames


class ParamsLoadedEvt(BaseModel):
    type: Literal["params_loaded"] = "params_loaded"
    filename: str
    flat: dict                         # key -> value, from load_params()
    raw: dict                          # nested structure, for round-trip saving
    # Parameters nothing in the solver reads, so the UI can grey them out and
    # say why instead of letting someone tune a number with no effect.
    # param key -> reason code; reason code -> explanatory sentence.
    inactive: dict = Field(default_factory=dict)
    inactive_reasons: dict = Field(default_factory=dict)


class ServerInfoEvt(BaseModel):
    """Sent unprompted the moment a client connects.

    Lets the page notice it is talking to a stale backend — see
    `backend/app/version.py` for why that happens and why it matters.
    """
    type: Literal["server_info"] = "server_info"
    protocol_version: int
    results_dir: str = ""
    params_dir: str = ""


class VersionMismatchEvt(BaseModel):
    """The page and the server disagree about the protocol version."""
    type: Literal["version_mismatch"] = "version_mismatch"
    server_version: int
    client_version: int
    message: str


class ParamsSavedEvt(BaseModel):
    type: Literal["params_saved"] = "params_saved"
    filename: str


class GeometryStats(BaseModel):
    """The old Geometry tab's stats box. Lengths in mm, matching its display."""
    total_length_mm: float
    throat_radius_mm: float
    exit_radius_mm: float
    E_r_actual: float
    throat_position_mm: float
    chamber_radius_mm: float
    # Inlet/throat area ratio and the inlet condition it implies. Shown so the
    # user can see at a glance that a geometry is solvable before running it.
    contraction_ratio: float
    # Isentropic inlet condition. The solver shoots for a slightly higher N0
    # (see core/inlet_condition.py); this is the value it brackets from.
    inlet_mach: float
    N0_isentropic: float


class GeometryPreviewEvt(BaseModel):
    type: Literal["geometry_preview"] = "geometry_preview"
    x_mm: list[float]
    r_mm: list[float]
    throat_index: int
    stats: GeometryStats


class DxfExportReadyEvt(BaseModel):
    type: Literal["dxf_export_ready"] = "dxf_export_ready"
    filename: str                      # basename inside `directory`
    # Absolute server-side directory. The desktop app had an "Open Results
    # Folder" button; a browser cannot open a folder, so the next best thing
    # is telling the user exactly where the file landed.
    directory: str = ""


class LogLineEvt(BaseModel):
    type: Literal["log_line"] = "log_line"
    text: str


class ConvergenceUpdateEvt(BaseModel):
    """One parsed `[Iteration n] R_N=... R_P=... R_T=... R_F=...` line."""
    type: Literal["convergence_update"] = "convergence_update"
    iteration: int
    r_n: float
    r_p: float
    r_t: float
    r_f: Optional[float] = None        # absent in older/frictionless output


class SimulationCompleteEvt(BaseModel):
    type: Literal["simulation_complete"] = "simulation_complete"
    returncode: int
    results_file: Optional[str] = None  # basename in results/, None on failure/stop
    stopped_by_user: bool = False


class ResultsListEvt(BaseModel):
    type: Literal["results_list"] = "results_list"
    files: list[str]
    directory: str = ""                # where these files live on the server


class ResultsTableEvt(BaseModel):
    type: Literal["results_table"] = "results_table"
    filename: str
    columns: list[str]
    rows: list[list[Optional[float]]]   # None where the CSV held NaN


class PlotDataEvt(BaseModel):
    type: Literal["plot_data"] = "plot_data"
    filename: str
    x_col: str
    y_col: str
    x: list[Optional[float]]
    y: list[Optional[float]]


class WallPreviewReadyEvt(BaseModel):
    type: Literal["wall_preview_ready"] = "wall_preview_ready"
    x: list[float]
    y: list[float]
    z: list[float]
    color_values: Optional[list[Optional[float]]] = None
    color_label: Optional[str] = None
    n_points: int
    n_planes: int


class WallExportReadyEvt(BaseModel):
    type: Literal["wall_export_ready"] = "wall_export_ready"
    filename: str
    directory: str = ""                # see DxfExportReadyEvt
    n_points: int
    fields_exported: list[str]
    # Set when both T_K and T_aw_K were selected; they map to the same Fluent
    # field, so one wins (T_aw_K), matching the old export's behaviour.
    temperature_field_resolved: Optional[str] = None


class SettingsEvt(BaseModel):
    type: Literal["settings"] = "settings"
    dxf_n_grid: int
    dxf_mirror: bool
    dxf_spline: bool
    dxf_labels: bool


class ErrorEvt(BaseModel):
    type: Literal["error"] = "error"
    context: str                       # the command that failed, or "parse"
    message: str


Event = Annotated[
    Union[
        ServerInfoEvt,
        VersionMismatchEvt,
        ParamsListEvt,
        ParamsLoadedEvt,
        ParamsSavedEvt,
        GeometryPreviewEvt,
        DxfExportReadyEvt,
        LogLineEvt,
        ConvergenceUpdateEvt,
        SimulationCompleteEvt,
        ResultsListEvt,
        ResultsTableEvt,
        PlotDataEvt,
        WallPreviewReadyEvt,
        WallExportReadyEvt,
        SettingsEvt,
        ErrorEvt,
    ],
    Field(discriminator="type"),
]


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def sanitize_floats(value: Any) -> Any:
    """Recursively replace NaN/Infinity with None so the result is valid JSON.

    Python's `json.dumps` happily emits bare `NaN`/`Infinity`, which every
    browser's `JSON.parse` rejects. Solver output contains NaN, so every event
    is passed through this before being sent.
    """
    if isinstance(value, float):
        return None if (math.isnan(value) or math.isinf(value)) else value
    if isinstance(value, dict):
        return {k: sanitize_floats(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [sanitize_floats(v) for v in value]
    return value
