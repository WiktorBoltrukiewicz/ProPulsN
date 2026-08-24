"""
The parameter file as a thing people share.

A config is the unit users pass around, so it has to say what it is
(`_meta`), say which format it is in (`_meta.format`), and survive a trip out
of one copy of ProPulsN and into another. These tests cover the three
mechanisms that make that work:

  * `stamp_meta()` — the program fills in its own bookkeeping on every save,
    and never invents the fields that belong to the user.
  * `read_format()` / `format_warnings()` — a file from a newer build loads,
    and says so, instead of failing mysteriously.
  * `looks_like_params()` — an unrelated .json dropped into the import button
    is refused before it lands in params/.
"""

import copy
import datetime
import json
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.app.core import PARAMS_DIR, param_schema as ps
from backend.app.services import params as params_service

SHIPPED = ('default.json', 'Liquid_Ethanol_N2O.json')


def _raw(name):
    with open(os.path.join(PARAMS_DIR, name), encoding='utf-8') as fh:
        return json.load(fh)


class TestFormatVersion(unittest.TestCase):

    def test_shipped_files_declare_the_current_format(self):
        for name in SHIPPED:
            with self.subTest(name=name):
                self.assertEqual(ps.read_format(_raw(name)), ps.FORMAT_VERSION)

    def test_an_unmarked_file_reads_as_format_zero(self):
        self.assertEqual(ps.read_format({}), 0)
        self.assertEqual(ps.read_format({'_meta': {}}), 0)
        self.assertEqual(ps.read_format({'_meta': {'format': 'nonsense'}}), 0)

    def test_current_format_is_documented(self):
        self.assertIn(ps.FORMAT_VERSION, ps.FORMAT_HISTORY)

    def test_a_newer_file_warns_but_is_not_refused(self):
        raw = _raw('default.json')
        raw['_meta']['format'] = ps.FORMAT_VERSION + 1
        warnings = ps.format_warnings(raw, 'from_the_future.json')
        self.assertEqual(len(warnings), 1)
        self.assertIn('from_the_future.json', warnings[0])
        self.assertIn('newer version', warnings[0])

    def test_the_current_format_and_older_ones_are_quiet(self):
        """An old file is not nagged about — saving migrates it silently."""
        for value in (0, ps.FORMAT_VERSION):
            with self.subTest(format=value):
                self.assertEqual(ps.format_warnings({'_meta': {'format': value}}), [])


class TestStampMeta(unittest.TestCase):

    def test_fills_in_what_the_program_owns(self):
        raw = {'solver': {'tol': {'value': 1e-6}}}
        ps.stamp_meta(raw, 'my-engine.json', today='2026-01-02')
        meta = raw['_meta']
        self.assertEqual(meta['format'], ps.FORMAT_VERSION)
        self.assertEqual(meta['created'], '2026-01-02')
        self.assertEqual(meta['modified'], '2026-01-02')

    def test_never_overwrites_what_the_user_owns(self):
        raw = {
            '_meta': {'name': 'Mine', 'author': 'Someone', 'version': '3.1',
                      'description': 'A real engine', 'created': '2020-05-05'},
            'solver': {'tol': {'value': 1e-6}},
        }
        ps.stamp_meta(raw, 'other-name.json', today='2026-01-02')
        meta = raw['_meta']
        self.assertEqual(meta['name'], 'Mine')
        self.assertEqual(meta['author'], 'Someone')
        self.assertEqual(meta['version'], '3.1')
        self.assertEqual(meta['description'], 'A real engine')
        # created is the file's birthday, not today's date.
        self.assertEqual(meta['created'], '2020-05-05')
        self.assertEqual(meta['modified'], '2026-01-02')

    def test_names_an_unnamed_file_after_itself(self):
        raw = {'solver': {'tol': {'value': 1e-6}}}
        ps.stamp_meta(raw, 'my_first_engine.json')
        self.assertEqual(raw['_meta']['name'], 'my first engine')

    def test_never_invents_an_author(self):
        """The app has no idea who the user is; the field is offered, not filled."""
        raw = {'solver': {'tol': {'value': 1e-6}}}
        ps.stamp_meta(raw, 'x.json')
        self.assertEqual(raw['_meta']['author'], '')

    def test_offers_every_shareable_field(self):
        raw = {'solver': {'tol': {'value': 1e-6}}}
        ps.stamp_meta(raw, 'x.json')
        for key in ('name', 'description', 'author', 'version'):
            self.assertIn(key, raw['_meta'])


class TestLooksLikeParams(unittest.TestCase):

    def test_accepts_a_real_config(self):
        for name in SHIPPED:
            with self.subTest(name=name):
                self.assertTrue(ps.looks_like_params(_raw(name)))

    def test_accepts_a_legacy_polish_config(self):
        self.assertTrue(ps.looks_like_params(
            {'warunki_poczatkowe': {'P0': {'wartosc': 1}}}))

    def test_refuses_anything_else(self):
        for junk in ({}, {'_meta': {'name': 'x'}}, {'a': 1},
                     {'a': {'b': 'c'}}, {'a': {'b': {'not_a_value': 1}}}):
            with self.subTest(junk=junk):
                self.assertFalse(ps.looks_like_params(junk))


class TestSaveRoundTrip(unittest.TestCase):
    """Through the real service, writing into params/."""

    # No leading underscore: sanitize_name() strips those, which is what keeps
    # a user from writing a file into the runner's `_run_` namespace.
    NAME = 'test_roundtrip_tmp.json'

    def tearDown(self):
        path = os.path.join(PARAMS_DIR, self.NAME)
        if os.path.exists(path):
            os.remove(path)

    def test_save_stamps_the_header(self):
        raw = copy.deepcopy(_raw('default.json'))
        raw['_meta'].pop('modified', None)
        params_service.save(self.NAME, raw)

        written = _raw(self.NAME)
        self.assertEqual(written['_meta']['format'], ps.FORMAT_VERSION)
        self.assertEqual(written['_meta']['modified'],
                         datetime.date.today().isoformat())

    def test_save_refuses_a_file_that_is_not_a_config(self):
        with self.assertRaises(ValueError) as caught:
            params_service.save(self.NAME, {'hello': 'world'})
        self.assertIn('parameter file', str(caught.exception))
        self.assertFalse(os.path.exists(os.path.join(PARAMS_DIR, self.NAME)))

    def test_save_as_refuses_to_clobber_an_existing_config(self):
        """What stops an import from silently replacing someone's work."""
        raw = copy.deepcopy(_raw('default.json'))
        params_service.save(self.NAME, raw, overwrite=False)
        with self.assertRaises(ValueError):
            params_service.save(self.NAME, raw, overwrite=False)

    def test_an_imported_legacy_file_migrates_on_the_way_in(self):
        legacy = {
            '_meta': {'nazwa': 'Stary silnik'},
            'warunki_poczatkowe': {
                'P0': {'wartosc': 6e6, 'jednostka': 'Pa', 'opis': 'Cisnienie'},
            },
        }
        params_service.save(self.NAME, legacy)

        written = _raw(self.NAME)
        self.assertIn('initial_conditions', written)
        self.assertNotIn('warunki_poczatkowe', written)
        self.assertEqual(written['initial_conditions']['P0']['value'], 6e6)
        self.assertEqual(written['_meta']['name'], 'Stary silnik')
        self.assertEqual(written['_meta']['format'], ps.FORMAT_VERSION)

    def test_load_returns_flat_raw_and_warnings(self):
        flat, raw, warnings = params_service.load('default.json')
        self.assertIn('R_throat', flat)
        self.assertIn('_meta', raw)
        self.assertEqual(warnings, [])


class TestImportNamespaceSafety(unittest.TestCase):
    """An imported filename is the user's, so it gets sanitised like any other."""

    def test_cannot_be_written_into_the_runners_temp_namespace(self):
        # `_run_*.json` files are the simulation runner's, and are hidden from
        # the file picker. An import must not be able to land in there.
        self.assertFalse(
            params_service.sanitize_name('_run_evil.json').startswith('_run_'))

    def test_cannot_escape_the_params_directory(self):
        backslash = chr(92)
        for name in ('../escaped.json', backslash + 'escaped.json',
                     '/etc/passwd', 'a/b/c.json'):
            with self.subTest(name=name):
                safe = params_service.sanitize_name(name)
                self.assertNotIn('/', safe)
                self.assertNotIn(backslash, safe)
                self.assertTrue(safe.endswith('.json'))


class TestParamsLoadedCarriesWarnings(unittest.TestCase):

    NAME = '_test_future_format.json'

    @classmethod
    def setUpClass(cls):
        from fastapi.testclient import TestClient
        from backend.app.main import app
        cls.client = TestClient(app)

    def tearDown(self):
        path = os.path.join(PARAMS_DIR, self.NAME)
        if os.path.exists(path):
            os.remove(path)

    def test_a_file_from_the_future_loads_with_a_warning(self):
        raw = copy.deepcopy(_raw('default.json'))
        raw['_meta']['format'] = ps.FORMAT_VERSION + 5
        with open(os.path.join(PARAMS_DIR, self.NAME), 'w', encoding='utf-8') as fh:
            json.dump(raw, fh, ensure_ascii=False)

        with self.client.websocket_connect('/ws') as ws:
            assert ws.receive_json()['type'] == 'server_info'
            ws.send_json({'type': 'load_params', 'filename': self.NAME})
            evt = ws.receive_json()

        self.assertEqual(evt['type'], 'params_loaded')
        self.assertEqual(len(evt['warnings']), 1)
        self.assertIn('newer version', evt['warnings'][0])
        # Still fully usable — a warning is not a refusal.
        self.assertEqual(evt['missing'], [])
        self.assertIn('R_throat', evt['flat'])

    def test_a_normal_file_carries_none(self):
        with self.client.websocket_connect('/ws') as ws:
            assert ws.receive_json()['type'] == 'server_info'
            ws.send_json({'type': 'load_params', 'filename': 'default.json'})
            evt = ws.receive_json()
        self.assertEqual(evt['warnings'], [])



class TestDownloadMatchesSave(unittest.TestCase):
    """Download and Save differ in destination only — never in content.

    They are two buttons producing the same artifact, so the thing worth
    pinning is that they cannot drift apart: both go through `_prepare()`, and
    a file that leaves the app is indistinguishable from one that stays.
    """

    NAME = 'test_download_tmp.json'

    def tearDown(self):
        path = os.path.join(PARAMS_DIR, self.NAME)
        if os.path.exists(path):
            os.remove(path)

    def test_downloaded_bytes_equal_saved_bytes(self):
        raw = copy.deepcopy(_raw('default.json'))
        raw['_meta']['modified'] = '1999-01-01'      # stale, as an edit would be

        _, downloaded = params_service.export(self.NAME, copy.deepcopy(raw))
        params_service.save(self.NAME, copy.deepcopy(raw))
        with open(os.path.join(PARAMS_DIR, self.NAME), encoding='utf-8') as fh:
            saved = fh.read()

        self.assertEqual(json.loads(downloaded), json.loads(saved))

    def test_download_stamps_the_header(self):
        raw = copy.deepcopy(_raw('default.json'))
        raw['_meta']['modified'] = '1999-01-01'
        _, text = params_service.export(self.NAME, raw)
        meta = json.loads(text)['_meta']
        self.assertEqual(meta['format'], ps.FORMAT_VERSION)
        self.assertEqual(meta['modified'], datetime.date.today().isoformat())

    def test_download_writes_nothing(self):
        params_service.export(self.NAME, copy.deepcopy(_raw('default.json')))
        self.assertFalse(os.path.exists(os.path.join(PARAMS_DIR, self.NAME)))

    def test_download_refuses_a_file_that_is_not_a_config(self):
        with self.assertRaises(ValueError):
            params_service.export(self.NAME, {'hello': 'world'})

    def test_download_sanitises_the_name(self):
        name, _ = params_service.export('../my engine', copy.deepcopy(_raw('default.json')))
        self.assertEqual(name, 'my_engine.json')

    def test_a_downloaded_config_loads_straight_back_in(self):
        """The round trip a shared file actually makes."""
        raw = copy.deepcopy(_raw('default.json'))
        _, text = params_service.export(self.NAME, raw)

        # ...as if the file had been sent to someone and uploaded again.
        params_service.save(self.NAME, json.loads(text), overwrite=False)
        flat, _, warnings = params_service.load(self.NAME)

        self.assertEqual(warnings, [])
        self.assertEqual(ps.missing_params(flat), [])


class TestExportParamsCommand(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        from fastapi.testclient import TestClient
        from backend.app.main import app
        cls.client = TestClient(app)

    def _roundtrip(self, message):
        with self.client.websocket_connect('/ws') as ws:
            assert ws.receive_json()['type'] == 'server_info'
            ws.send_json(message)
            return ws.receive_json()

    def test_returns_the_config_as_text(self):
        evt = self._roundtrip({
            'type': 'export_params',
            'filename': 'shared.json',
            'raw': _raw('default.json'),
        })
        self.assertEqual(evt['type'], 'params_exported')
        self.assertEqual(evt['filename'], 'shared.json')
        parsed = json.loads(evt['content'])
        self.assertEqual(parsed['_meta']['format'], ps.FORMAT_VERSION)
        self.assertIn('nozzle_geometry', parsed)

    def test_refuses_something_that_is_not_a_config(self):
        evt = self._roundtrip({
            'type': 'export_params', 'filename': 'x.json', 'raw': {'a': 1},
        })
        self.assertEqual(evt['type'], 'error')
        self.assertEqual(evt['context'], 'export_params')

    def test_does_not_add_a_file_to_the_library(self):
        before = set(params_service.list_param_files())
        self._roundtrip({
            'type': 'export_params',
            'filename': 'not_stored.json',
            'raw': _raw('default.json'),
        })
        self.assertEqual(set(params_service.list_param_files()), before)

if __name__ == '__main__':
    unittest.main()
