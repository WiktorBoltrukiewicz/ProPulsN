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
