"""
param_schema.py — parameter file vocabulary, and which parameters are live.

Two jobs:

1. **Translation shim.** Parameter files used to be written with Polish keys
   (``wartosc``, ``jednostka``, ``opis``, ``geometria_dyszy``, ...). The
   application is English now, but files written before the switch must keep
   loading, so :func:`normalise_raw` rewrites the old vocabulary on the way in.
   Saving always writes the English form, so a file migrates the first time it
   is saved.

2. **Inactive parameters.** The solver models gas flow with friction only.
   Everything to do with regenerative cooling is carried in the parameter files
   from the earlier version of this program, but nothing reads it. Those keys
   are listed here so the UI can grey them out and say why, instead of letting
   a user tune a number that has no effect.

`tests/test_param_schema.py` checks the inactive list against what the solver
actually reads, so it cannot drift as features land.
"""

import datetime as _dt


# ── Translation shim ─────────────────────────────────────────────────────────

#: Old section name → new section name.
SECTION_ALIASES = {
    'warunki_poczatkowe': 'initial_conditions',
    'geometria_dyszy': 'nozzle_geometry',
    'kanaly_chlodzace': 'cooling_channels',
    'wlasciwosci_scianki': 'wall_properties',
    'wlasciwosci_gazu': 'gas_properties',
    'chlodziwo_fuel': 'coolant_fuel',
}

#: Old field name → new field name, inside a parameter entry.
FIELD_ALIASES = {
    'wartosc': 'value',
    'jednostka': 'unit',
    'opis': 'description',
}

#: Old section-level metadata key → new key.
SECTION_META_ALIASES = {
    '_opis': '_description',
}

#: Old `_meta` key → new key.
META_ALIASES = {
    'nazwa': 'name',
    'opis': 'description',
    'autor': 'author',
    'data_utworzenia': 'created',
    'wersja': 'version',
}

VALUE_KEY = 'value'
UNIT_KEY = 'unit'
DESCRIPTION_KEY = 'description'
SECTION_DESCRIPTION_KEY = '_description'


def is_legacy(raw):
    """True if `raw` uses any of the old Polish keys."""
    if not isinstance(raw, dict):
        return False
    for section_key, section in raw.items():
        if section_key in SECTION_ALIASES:
            return True
        if not isinstance(section, dict):
            continue
        if section_key == '_meta':
            if any(k in META_ALIASES for k in section):
                return True
            continue
        if any(k in SECTION_META_ALIASES for k in section):
            return True
        for entry in section.values():
            if isinstance(entry, dict) and any(k in FIELD_ALIASES for k in entry):
                return True
    return False


def normalise_raw(raw):
    """Return `raw` with the English vocabulary, leaving the input untouched.

    Unknown keys pass through unchanged — a file may carry sections this
    program does not know about, and losing them on save would be worse than
    leaving them in their original spelling.
    """
    if not isinstance(raw, dict):
        return raw

    out = {}
    for section_key, section in raw.items():
        new_section_key = SECTION_ALIASES.get(section_key, section_key)

        if not isinstance(section, dict):
            out[new_section_key] = section
            continue

        if section_key == '_meta':
            out[new_section_key] = {
                META_ALIASES.get(k, k): v for k, v in section.items()
            }
            continue

        new_section = {}
        for key, entry in section.items():
            new_key = SECTION_META_ALIASES.get(key, key)
            if isinstance(entry, dict):
                new_section[new_key] = {
                    FIELD_ALIASES.get(k, k): v for k, v in entry.items()
                }
            else:
                new_section[new_key] = entry
        out[new_section_key] = new_section

    return out


def entry_value(entry):
    """Read a parameter entry's value, accepting either vocabulary."""
    if not isinstance(entry, dict):
        return None
    if VALUE_KEY in entry:
        return entry[VALUE_KEY]
    return entry.get('wartosc')


def has_value(entry):
    """True if `entry` looks like a parameter entry in either vocabulary."""
    return isinstance(entry, dict) and (VALUE_KEY in entry or 'wartosc' in entry)


# ── Inactive parameters ──────────────────────────────────────────────────────

#: Reason codes, with the text the UI shows.
REASON_COOLING = 'cooling'
REASON_SUPERSEDED = 'superseded'

INACTIVE_REASONS = {
    REASON_COOLING: (
        "Regenerative cooling is not implemented yet. The solver models gas "
        "flow with wall friction only, so this value has no effect on a run. "
        "It is kept in the file so it survives until cooling lands."
    ),
    REASON_SUPERSEDED: (
        "Computed internally from the gas properties, so the value in the "
        "file is ignored."
    ),
}

#: Parameter key → reason code. Everything listed here is read by nothing.
INACTIVE_PARAMS = {
    # Cooling channel geometry — the whole section.
    'nChannels': REASON_COOLING,
    'w_chamber': REASON_COOLING,
    'h_chamber': REASON_COOLING,
    'w_throat': REASON_COOLING,
    'h_throat': REASON_COOLING,
    'w_exit': REASON_COOLING,
    'h_exit': REASON_COOLING,
    'shift_x': REASON_COOLING,
    'throat_zone_width': REASON_COOLING,
    'smooth_window': REASON_COOLING,

    # Wall properties. `epsilon` (roughness) stays live — the friction model
    # uses it; the rest only matter for conduction through the wall.
    'thickness': REASON_COOLING,
    'k_copper': REASON_COOLING,
    'Thw_init': REASON_COOLING,
    'Tcw_init': REASON_COOLING,
    'sigma_wall': REASON_COOLING,
    'therm_cond_fuel': REASON_COOLING,

    # Coolant — the whole section.
    'fuel_name': REASON_COOLING,
    'mass_flow_fuel': REASON_COOLING,
    'T_fuel_inlet': REASON_COOLING,
    'P_cc_in': REASON_COOLING,

    # Leftovers that the solver now derives for itself.
    'sonvel': REASON_SUPERSEDED,   # compute_qf.py: sqrt(gamma * Rs * T)
    'Ru_bartz': REASON_SUPERSEDED, # compute_bartz_htc() uses the throat radius
}


def is_inactive(param_key):
    """True if nothing in the solver reads `param_key`."""
    return param_key in INACTIVE_PARAMS


def inactive_reason(param_key):
    """Reason code for an inactive parameter, or None if it is live."""
    return INACTIVE_PARAMS.get(param_key)


# ---- Required parameters ----------------------------------------------------
#
# Every key below must carry a value before the solver will start. This table
# holds names, units and labels - deliberately **no values**. Nothing in the
# program invents a number: a parameter comes from the parameter file, as
# edited in the UI, or the run is refused.
#
# The unit/description columns exist so a key missing from a file can be
# rendered as a properly labelled (but empty) field, and so filling it in
# produces a complete JSON entry on save.

#: Parameter key -> (section, unit, description).
REQUIRED_PARAMS = {
    # -- Contour. Owned by the Geometry section of the UI. -------------------
    'R_throat':   ('nozzle_geometry', 'm', 'Throat radius'),
    'E_r':        ('nozzle_geometry', '-', 'Expansion ratio (A_exit / A_throat)'),
    'R_chamber':  ('nozzle_geometry', 'm', 'Combustion chamber radius'),
    'L_chamber':  ('nozzle_geometry', 'm',
                   'Chamber inlet distance upstream of the throat (throat at x = 0)'),
    'R_conv_arc': ('nozzle_geometry', 'm', 'Convergent section large-arc radius'),
    #    Grid resolution. Owned by the Simulation section.
    'n_grid':     ('nozzle_geometry', '-', 'Number of computational grid points'),

    # -- Inlet state. --------------------------------------------------------
    'P0':        ('initial_conditions', 'Pa', 'Static pressure at the inlet'),
    'T0':        ('initial_conditions', 'K',
                  'Static temperature at the inlet (combustion products)'),
    'N0_auto':   ('initial_conditions', '-',
                  'Solve for N0 from the contraction ratio (0 = use the N0 value below)'),
    'N0_margin': ('initial_conditions', '-',
                  'Safety margin above the choking threshold when solving for N0'),

    # -- Gas state at the three interpolation nodes. -------------------------
    'gamma_chamber': ('gas_properties', '-',
                      'Ratio of specific heats (Cp/Cv) - combustion chamber'),
    'gamma_throat':  ('gas_properties', '-',
                      'Ratio of specific heats (Cp/Cv) - throat'),
    'gamma_exit':    ('gas_properties', '-',
                      'Ratio of specific heats (Cp/Cv) - exit'),
    'Cpcg_chamber':  ('gas_properties', 'J/(kg*K)',
                      'Specific heat capacity Cp - combustion chamber'),
    'Cpcg_throat':   ('gas_properties', 'J/(kg*K)',
                      'Specific heat capacity Cp - throat'),
    'Cpcg_exit':     ('gas_properties', 'J/(kg*K)',
                      'Specific heat capacity Cp - exit'),
    'Prcg_chamber':  ('gas_properties', '-',
                      'Prandtl number of the gas - combustion chamber'),
    'Prcg_throat':   ('gas_properties', '-', 'Prandtl number of the gas - throat'),
    'Prcg_exit':     ('gas_properties', '-', 'Prandtl number of the gas - exit'),
    'combustion_molar_mass_chamber': ('gas_properties', 'kg/mol',
                                      'Molar mass of the combustion products - chamber'),
    'combustion_molar_mass_throat':  ('gas_properties', 'kg/mol',
                                      'Molar mass of the combustion products - throat'),
    'combustion_molar_mass_exit':    ('gas_properties', 'kg/mol',
                                      'Molar mass of the combustion products - exit'),
    'eta':    ('gas_properties', 'Pa*s', 'Dynamic viscosity of the gas (constant)'),
    'c_star': ('gas_properties', 'm/s', 'Characteristic velocity'),

    # -- Wall. `epsilon` is the one live wall property: friction reads it. ----
    'epsilon': ('wall_properties', 'm', 'Absolute surface roughness'),

    # -- Convergence loop. Owned by the Simulation section. ------------------
    'max_iterations': ('solver', '-', 'Maximum number of convergence loop iterations'),
    'tol':            ('solver', '-', 'Convergence tolerance'),
    'relax':          ('solver', '-', 'Under-relaxation factor (0-1)'),
    'solver_mode':    ('solver', '-', 'Solver mode: convergence or fixed'),
    'mdot_gas':       ('solver', 'kg/s', 'Gas mass flow rate'),
}

#: `N0` is the one conditional requirement. The solver normally computes it by
#: shooting for the choking threshold (see core/inlet_condition.py) and ignores
#: whatever the file says; it is read only when `N0_auto` is switched off.
CONDITIONAL_PARAMS = {
    'N0': ('initial_conditions', '-',
           'Inlet Mach number squared (M^2) - used only when N0_auto = 0'),
}


class MissingParameters(ValueError):
    """Raised before any computation when the parameters are incomplete.

    Carries the whole list rather than stopping at the first gap, so the user
    fills everything in once instead of meeting them one at a time.
    """

    def __init__(self, keys):
        self.keys = list(keys)
        super().__init__(
            "No value supplied for: " + ", ".join(self.keys) + ". "
            "Every parameter must come from the parameter file - nothing is "
            "assumed. Fill these in and run again."
        )


def _is_off(value):
    """True if a parameter file's flag reads as 'off' (0, false, 'no', '')."""
    if isinstance(value, str):
        return value.strip().lower() in ('0', 'false', 'no', 'off', '')
    return not bool(value)


def missing_params(flat):
    """Required keys that `flat` does not supply, in table order.

    `flat` is the dict returned by `load_params()`. A key that is absent, or
    present but None, counts as missing - None is what an empty UI field sends.
    """
    missing = [key for key in REQUIRED_PARAMS if flat.get(key) is None]

    # N0 matters only when the automatic inlet condition is switched off. If
    # N0_auto is itself missing it is already listed above; don't pile on.
    if 'N0_auto' not in missing and _is_off(flat.get('N0_auto')):
        if flat.get('N0') is None:
            missing.append('N0')

    return missing


def require_params(flat):
    """Raise `MissingParameters` unless every required parameter has a value."""
    missing = missing_params(flat)
    if missing:
        raise MissingParameters(missing)


def param_metadata(key):
    """(section, unit, description) for a required or conditional key."""
    return REQUIRED_PARAMS.get(key) or CONDITIONAL_PARAMS.get(key)


def required_fields():
    """The whole table as JSON-friendly records, for the UI to render fields.

    Conditional keys are included and flagged, so the Parameters section can
    offer `N0` without demanding it.
    """
    out = {}
    for key, (section, unit, description) in REQUIRED_PARAMS.items():
        out[key] = {'section': section, 'unit': unit,
                    'description': description, 'required': True}
    for key, (section, unit, description) in CONDITIONAL_PARAMS.items():
        out[key] = {'section': section, 'unit': unit,
                    'description': description, 'required': False}
    return out


# ---- File format version ----------------------------------------------------
#
# A parameter file is the unit users share, so a file may arrive from a build
# of ProPulsN that is newer than the one reading it. `_meta.format` is how a
# reader finds out, instead of silently loading a file it only half understands.
#
# `_meta.version` is left alone: that one belongs to the user, for their own
# "revision 3 of my engine" tag. `format` belongs to the program.

#: Bump when the shape of a parameter file changes in a way an older build
#: would misread — a renamed section, a new required parameter, a changed
#: entry layout. Adding an optional key does not need a bump.
FORMAT_VERSION = 1

FORMAT_HISTORY = {
    1: "English vocabulary (value/unit/description); every solver parameter "
       "must be present (see REQUIRED_PARAMS).",
    0: "Unmarked — anything written before the format was tracked, including "
       "the Polish-key files.",
}

META_KEY = '_meta'
FORMAT_KEY = 'format'

#: `_meta` entries the program maintains; everything else there is the user's.
STAMPED_META = ('format', 'created', 'modified')


def read_format(raw):
    """The format version `raw` declares. 0 means it predates the marker."""
    meta = raw.get(META_KEY) if isinstance(raw, dict) else None
    if not isinstance(meta, dict):
        return 0
    try:
        return int(meta.get(FORMAT_KEY, 0))
    except (TypeError, ValueError):
        return 0


def format_warnings(raw, filename=None):
    """Non-fatal things worth telling the user about this file, as sentences.

    A warning is not a refusal: the file still loads, and unknown entries are
    still carried through save. It exists so that "some values are missing"
    reads as "this file is from a newer ProPulsN" rather than as a mystery.
    """
    warnings = []
    found = read_format(raw)
    if found > FORMAT_VERSION:
        where = f"{filename} was" if filename else "This file was"
        warnings.append(
            f"{where} written by a newer version of ProPulsN "
            f"(file format {found}; this build reads {FORMAT_VERSION}). "
            "Anything it carries is kept, but a parameter this build needs "
            "may be missing or mean something different."
        )
    return warnings


def stamp_meta(raw, filename=None, today=None):
    """Fill in the `_meta` fields the program owns. Modifies `raw` in place.

    Called on every save, so a shared file carries its own identity instead of
    an empty header: what it is, when it was first written, when it was last
    touched, and which format it is in. `author` is never invented — the app
    has no idea who the user is; the UI offers the field and leaves it blank.
    """
    if today is None:
        today = _dt.date.today().isoformat()

    meta = raw.get(META_KEY)
    if not isinstance(meta, dict):
        meta = {}
        raw[META_KEY] = meta

    meta[FORMAT_KEY] = FORMAT_VERSION
    if not str(meta.get('created') or '').strip():
        meta['created'] = today
    meta['modified'] = today

    if not str(meta.get('name') or '').strip() and filename:
        stem = filename[:-5] if filename.lower().endswith('.json') else filename
        meta['name'] = stem.replace('_', ' ').replace('-', ' ').strip()

    # A `_meta` is not much use without somewhere to write these.
    meta.setdefault('description', '')
    meta.setdefault('author', '')
    meta.setdefault('version', '')

    # `_meta` reads best with the program's own bookkeeping last.
    ordered = {k: v for k, v in meta.items() if k not in STAMPED_META}
    for key in STAMPED_META:
        if key in meta:
            ordered[key] = meta[key]
    raw[META_KEY] = ordered
    return raw


def looks_like_params(raw):
    """True if `raw` could plausibly be a ProPulsN parameter file.

    Imports come from wherever the user got them, so a dropped-in file is
    checked for shape before it is written into params/ — otherwise an
    unrelated .json lands in the picker and fails much later, much less
    clearly.
    """
    if not isinstance(raw, dict) or not raw:
        return False
    for section_key, section in raw.items():
        if section_key == META_KEY or not isinstance(section, dict):
            continue
        if any(has_value(entry) for entry in section.values()):
            return True
    return False
