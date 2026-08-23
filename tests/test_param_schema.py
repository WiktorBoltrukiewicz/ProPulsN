"""The parameter vocabulary shim, and the inactive-parameter list.

The inactive list drives what the UI greys out, so it must not drift. The test
below traces which keys the solver actually reads during a real run and
compares that against `INACTIVE_PARAMS` — if regenerative cooling lands and
starts reading `nChannels`, this fails until the list is updated.
"""

import contextlib
import io as _io
import json
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.app.core import PARAMS_DIR  # noqa: E402
from backend.app.core import param_schema as ps  # noqa: E402

LEGACY = {
    "_meta": {"nazwa": "Stary plik", "opis": "opis pliku", "autor": "X",
              "data_utworzenia": "2026-01-01", "wersja": "1.0"},
    "geometria_dyszy": {
        "_opis": "Geometria",
        "R_throat": {"wartosc": 0.02, "jednostka": "m", "opis": "Promien"},
    },
    "warunki_poczatkowe": {
        "N0": {"wartosc": 0.015, "jednostka": "-", "opis": "M^2"},
    },
}


class TestNormaliseRaw(unittest.TestCase):

    def test_translates_sections_fields_and_meta(self):
        out = ps.normalise_raw(LEGACY)
        self.assertIn('nozzle_geometry', out)
        self.assertIn('initial_conditions', out)
        self.assertNotIn('geometria_dyszy', out)
        self.assertEqual(out['nozzle_geometry']['_description'], 'Geometria')
        entry = out['nozzle_geometry']['R_throat']
        self.assertEqual(entry, {'value': 0.02, 'unit': 'm', 'description': 'Promien'})
        self.assertEqual(out['_meta']['name'], 'Stary plik')
        self.assertEqual(out['_meta']['created'], '2026-01-01')

    def test_does_not_mutate_the_input(self):
        before = json.dumps(LEGACY, sort_keys=True)
        ps.normalise_raw(LEGACY)
        self.assertEqual(json.dumps(LEGACY, sort_keys=True), before)

    def test_is_idempotent(self):
        once = ps.normalise_raw(LEGACY)
        self.assertEqual(ps.normalise_raw(once), once)

    def test_unknown_sections_and_keys_survive(self):
        out = ps.normalise_raw({'my_section': {'k': {'wartosc': 1, 'custom': 'x'}}})
        self.assertEqual(out['my_section']['k'], {'value': 1, 'custom': 'x'})

    def test_is_legacy_detects_both_shapes(self):
        self.assertTrue(ps.is_legacy(LEGACY))
        self.assertFalse(ps.is_legacy(ps.normalise_raw(LEGACY)))

    def test_shipped_files_are_already_english(self):
        for name in ('default.json', 'Liquid_Ethanol_N2O.json'):
            with self.subTest(name):
                with open(os.path.join(PARAMS_DIR, name), encoding='utf-8') as fh:
                    raw = json.load(fh)
                self.assertFalse(ps.is_legacy(raw))

    def test_a_legacy_file_still_loads(self):
        """The whole point of the shim."""
        from backend.app.core.param_loader import load_params
        path = os.path.join(PARAMS_DIR, '_test_legacy_vocab.json')
        with open(path, 'w', encoding='utf-8') as fh:
            json.dump(LEGACY, fh, ensure_ascii=False)
        try:
            flat, raw = load_params(path)
            self.assertEqual(flat['R_throat'], 0.02)
            self.assertEqual(flat['N0'], 0.015)
            self.assertIn('nozzle_geometry', raw)
        finally:
            os.unlink(path)


class TestInactiveParams(unittest.TestCase):

    def test_reasons_are_all_defined(self):
        for key, reason in ps.INACTIVE_PARAMS.items():
            with self.subTest(key):
                self.assertIn(reason, ps.INACTIVE_REASONS)

    def test_live_parameters_are_not_listed(self):
        for key in ('R_throat', 'E_r', 'n_grid', 'R_chamber', 'N0', 'P0', 'T0',
                    'epsilon', 'eta', 'c_star', 'max_iterations', 'tol', 'relax',
                    'mdot_gas', 'gamma_chamber'):
            with self.subTest(key):
                self.assertFalse(ps.is_inactive(key))

    def test_cooling_channel_keys_are_listed(self):
        for key in ('nChannels', 'w_throat', 'h_exit', 'fuel_name', 'k_copper'):
            with self.subTest(key):
                self.assertEqual(ps.inactive_reason(key), ps.REASON_COOLING)

    def test_matches_what_the_solver_actually_reads(self):
        """Traces a real run; fails if the list and the solver disagree."""
        import backend.app.core.main as core_main
        import backend.app.core.param_loader as loader

        accessed = set()

        class Tracking(dict):
            def __contains__(self, key):
                accessed.add(key)
                return dict.__contains__(self, key)

            def __getitem__(self, key):
                accessed.add(key)
                return dict.__getitem__(self, key)

        original = loader.load_params

        def tracked(path):
            flat, raw = original(path)
            return Tracking(flat), raw

        core_main.load_params = tracked
        try:
            for name in ('default.json', 'Liquid_Ethanol_N2O.json'):
                path = os.path.join(PARAMS_DIR, name)
                with open(path, encoding='utf-8') as fh:
                    raw = json.load(fh)
                raw['solver']['max_iterations']['value'] = 2
                tmp = os.path.join(PARAMS_DIR, f'_test_schema_{name}')
                with open(tmp, 'w', encoding='utf-8') as fh:
                    json.dump(raw, fh, ensure_ascii=False)
                try:
                    with contextlib.redirect_stdout(_io.StringIO()):
                        core_main.main(tmp)
                finally:
                    os.unlink(tmp)
                    stem = os.path.splitext(os.path.basename(tmp))[0]
                    for f in os.listdir(os.path.join(
                            os.path.dirname(PARAMS_DIR), 'results')):
                        if f.startswith(stem):
                            os.unlink(os.path.join(
                                os.path.dirname(PARAMS_DIR), 'results', f))
        finally:
            core_main.load_params = original

        # Anything the solver read must not be marked inactive.
        wrongly_inactive = sorted(accessed & set(ps.INACTIVE_PARAMS))
        self.assertEqual(wrongly_inactive, [],
                         f"marked inactive but the solver reads them: {wrongly_inactive}")

        # And every key in the shipped files that the solver ignores must be
        # listed, or the UI would present a dead input as live.
        declared = set()
        for name in ('default.json', 'Liquid_Ethanol_N2O.json'):
            with open(os.path.join(PARAMS_DIR, name), encoding='utf-8') as fh:
                raw = json.load(fh)
            for section, body in raw.items():
                if section == '_meta' or not isinstance(body, dict):
                    continue
                declared.update(k for k in body if not k.startswith('_'))

        unlisted = sorted(declared - accessed - set(ps.INACTIVE_PARAMS))
        self.assertEqual(unlisted, [],
                         f"read by nothing but not marked inactive: {unlisted}")


if __name__ == '__main__':
    unittest.main()
