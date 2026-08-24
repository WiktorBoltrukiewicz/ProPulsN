"""
Every solver parameter comes from the parameter file — nothing is assumed.

The program used to carry a fallback next to each read (`p('tol', 1e-6)`), so
the same number lived in the JSON, in the Python and in the HTML, and the
three had already drifted: `default.json` said `relax = 0.3` while the code
and the page said `0.5`. Those fallbacks are gone. `param_schema` now holds
one table of *names* — never values — and an incomplete file is refused before
any computation runs.

These tests guard both halves of that:
  * the table stays free of values, and stays in step with what the solver
    actually reads;
  * an incomplete file is refused, by name, at every entry point.
"""

import contextlib
import io as _io
import json
import os
import subprocess
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.app.core import PARAMS_DIR, REPO_ROOT, param_schema as ps
from backend.app.core.param_loader import load_params

SHIPPED = ('default.json', 'Liquid_Ethanol_N2O.json')


def _flat(name):
    flat, _ = load_params(os.path.join(PARAMS_DIR, name))
    return flat


class TestTableHoldsNoValues(unittest.TestCase):
    """The whole point: names and labels, never a number."""

    def test_every_entry_is_section_unit_description(self):
        table = dict(ps.REQUIRED_PARAMS)
        table.update(ps.CONDITIONAL_PARAMS)
        for key, spec in table.items():
            with self.subTest(key=key):
                self.assertEqual(len(spec), 3, f"{key}: expected (section, unit, description)")
                for part in spec:
                    self.assertIsInstance(part, str, f"{key}: {part!r} is not a label")

    def test_no_key_is_both_required_and_inactive(self):
        overlap = sorted(set(ps.REQUIRED_PARAMS) & set(ps.INACTIVE_PARAMS))
        self.assertEqual(overlap, [],
                         f"required but marked as read by nothing: {overlap}")

    def test_required_fields_is_json_friendly(self):
        fields = ps.required_fields()
        json.dumps(fields)  # would raise on anything the WS cannot ship
        self.assertTrue(fields['tol']['required'])
        # N0 is offered but not demanded — the solver normally computes it.
        self.assertFalse(fields['N0']['required'])


class TestShippedFilesAreComplete(unittest.TestCase):
    """A file that ships with the program must not need filling in."""

    def test_nothing_missing(self):
        for name in SHIPPED:
            with self.subTest(name=name):
                self.assertEqual(ps.missing_params(_flat(name)), [])


class TestMissingParams(unittest.TestCase):

    def test_reports_every_gap_at_once(self):
        flat = _flat('default.json')
        for key in ('tol', 'P0', 'gamma_throat'):
            del flat[key]
        missing = ps.missing_params(flat)
        self.assertEqual(sorted(missing), ['P0', 'gamma_throat', 'tol'])

    def test_a_present_but_null_value_counts_as_missing(self):
        flat = _flat('default.json')
        flat['relax'] = None
        self.assertIn('relax', ps.missing_params(flat))

    def test_N0_is_only_required_when_N0_auto_is_off(self):
        flat = _flat('default.json')
        del flat['N0']

        flat['N0_auto'] = 1
        self.assertNotIn('N0', ps.missing_params(flat),
                         "N0 is computed when N0_auto is on")

        flat['N0_auto'] = 0
        self.assertIn('N0', ps.missing_params(flat),
                      "N0 is read verbatim when N0_auto is off")

    def test_error_names_every_gap(self):
        flat = _flat('default.json')
        del flat['tol']
        del flat['epsilon']
        with self.assertRaises(ps.MissingParameters) as caught:
            ps.require_params(flat)
        message = str(caught.exception)
        self.assertIn('tol', message)
        self.assertIn('epsilon', message)
        self.assertEqual(sorted(caught.exception.keys), ['epsilon', 'tol'])


class TestMatchesWhatTheSolverReads(unittest.TestCase):
    """Drift guard, the mirror of the INACTIVE_PARAMS one.

    A parameter the solver reads must be one the UI knows to ask for. Add a
    `p('something')` to core/main.py without an entry here and this fails —
    which is the point, because otherwise the run would die on a KeyError
    instead of the user being offered a field.
    """

    def test_every_live_parameter_is_declared(self):
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
        results_dir = os.path.join(REPO_ROOT, 'results')
        try:
            for name in SHIPPED:
                with open(os.path.join(PARAMS_DIR, name), encoding='utf-8') as fh:
                    raw = json.load(fh)
                # Cap the iteration count rather than shrinking n_grid: a coarse
                # grid fails near the sonic point (see CLAUDE.md, testing notes).
                raw['solver']['max_iterations']['value'] = 2
                tmp = os.path.join(PARAMS_DIR, f'_test_required_{name}')
                with open(tmp, 'w', encoding='utf-8') as fh:
                    json.dump(raw, fh, ensure_ascii=False)
                try:
                    with contextlib.redirect_stdout(_io.StringIO()):
                        core_main.main(tmp)
                finally:
                    os.unlink(tmp)
                    stem = os.path.splitext(os.path.basename(tmp))[0]
                    for produced in os.listdir(results_dir):
                        if produced.startswith(stem):
                            os.unlink(os.path.join(results_dir, produced))
        finally:
            core_main.load_params = original

        declared = set()
        for name in SHIPPED:
            declared.update(_flat(name))

        known = set(ps.REQUIRED_PARAMS) | set(ps.CONDITIONAL_PARAMS)
        undeclared = sorted((accessed & declared) - known - set(ps.INACTIVE_PARAMS))
        self.assertEqual(undeclared, [],
                         f"the solver reads these but the UI never asks: {undeclared}")


class TestCliRefusesIncompleteFiles(unittest.TestCase):
    """End-to-end through the real CLI, the same entry point the web app spawns."""

    TMP = os.path.join(PARAMS_DIR, '_test_incomplete.json')

    def tearDown(self):
        if os.path.exists(self.TMP):
            os.remove(self.TMP)

    def _run(self, argv):
        return subprocess.run(
            [sys.executable, '-u', 'main.py', *argv],
            cwd=REPO_ROOT, capture_output=True, text=True,
            env={**os.environ, 'PYTHONIOENCODING': 'utf-8'},
        )

    def test_refuses_and_names_the_gaps(self):
        with open(os.path.join(PARAMS_DIR, 'default.json'), encoding='utf-8') as fh:
            raw = json.load(fh)
        del raw['solver']['tol']
        del raw['gas_properties']['gamma_throat']
        with open(self.TMP, 'w', encoding='utf-8') as fh:
            json.dump(raw, fh, ensure_ascii=False)

        proc = self._run([self.TMP])
        self.assertNotEqual(proc.returncode, 0)
        output = proc.stdout + proc.stderr
        self.assertIn('tol', output)
        self.assertIn('gamma_throat', output)

    def test_refuses_before_computing_anything(self):
        """No geometry, no ODE — the gate runs first."""
        with open(os.path.join(PARAMS_DIR, 'default.json'), encoding='utf-8') as fh:
            raw = json.load(fh)
        del raw['nozzle_geometry']['R_throat']
        with open(self.TMP, 'w', encoding='utf-8') as fh:
            json.dump(raw, fh, ensure_ascii=False)

        proc = self._run([self.TMP])
        self.assertNotEqual(proc.returncode, 0)
        self.assertNotIn('Stage 1', proc.stdout)

    def test_default_mode_is_gone(self):
        """`--default` was the built-in fallback values; it cannot survive."""
        proc = self._run(['--default'])
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn('--default', proc.stdout + proc.stderr)


class TestWebSocketRefusesIncompleteRuns(unittest.TestCase):
    """The browser is told, rather than the subprocess dying on a traceback."""

    @classmethod
    def setUpClass(cls):
        from fastapi.testclient import TestClient
        from backend.app.main import app
        cls.client = TestClient(app)

    def _connect(self, ws):
        greeting = ws.receive_json()
        assert greeting['type'] == 'server_info', greeting

    def test_run_with_a_gap_is_refused(self):
        _, raw = load_params(os.path.join(PARAMS_DIR, 'default.json'))
        del raw['gas_properties']['Cpcg_throat']

        with self.client.websocket_connect('/ws') as ws:
            self._connect(ws)
            ws.send_json({
                'type': 'run_simulation',
                'raw_params': raw,
                'solver_overrides': {'max_iterations': 1},
                'solver_mode': 'fixed',
            })
            evt = ws.receive_json()

        self.assertEqual(evt['type'], 'error')
        self.assertEqual(evt['context'], 'run_simulation')
        self.assertIn('Cpcg_throat', evt['message'])

    def test_a_typed_value_closes_a_gap_the_file_has(self):
        """A solver override lands even when the file carries no such key.

        This is what lets the user fill an empty field in and press Run: the
        entry is created rather than dropped.
        """
        _, raw = load_params(os.path.join(PARAMS_DIR, 'default.json'))
        del raw['solver']['tol']

        from backend.app.services.simulation_runner import SimulationRun
        run = SimulationRun(
            raw_params=raw,
            solver_overrides={'tol': 1e-5},
            solver_mode='convergence',
        )
        self.assertEqual(run.missing_parameters(), [])

    def test_params_loaded_ships_the_table_and_the_gaps(self):
        with self.client.websocket_connect('/ws') as ws:
            self._connect(ws)
            ws.send_json({'type': 'load_params', 'filename': 'default.json'})
            evt = ws.receive_json()

        self.assertEqual(evt['type'], 'params_loaded')
        self.assertIn('tol', evt['required'])
        self.assertEqual(evt['missing'], [])
        # Labels only — a value here would be a default by another name.
        self.assertNotIn('value', evt['required']['tol'])


if __name__ == '__main__':
    unittest.main()
