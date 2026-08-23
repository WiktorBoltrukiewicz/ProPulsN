"""The page and the backend must agree on the protocol version.

A stale uvicorn can keep answering on a port while serving fresh static files
from disk, so the page looks current while the Python behind it is not. New
fields then go missing and the UI renders the wrong thing without saying so.
The handshake exists to make that loud; these tests keep it honest.
"""

import os
import re
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.app.version import PROTOCOL_HISTORY, PROTOCOL_VERSION  # noqa: E402
from backend.app.ws import protocol as p  # noqa: E402

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP_JS = os.path.join(REPO, 'frontend', 'js', 'app.js')


def _frontend_version():
    with open(APP_JS, encoding='utf-8') as fh:
        source = fh.read()
    match = re.search(r'^const PROTOCOL_VERSION = (\d+);', source, re.M)
    if not match:
        raise AssertionError(f"No PROTOCOL_VERSION constant found in {APP_JS}")
    return int(match.group(1))


class TestVersionsAgree(unittest.TestCase):

    def test_frontend_matches_backend(self):
        """If this fails you bumped one constant and forgot the other."""
        self.assertEqual(
            _frontend_version(), PROTOCOL_VERSION,
            "frontend/js/app.js and backend/app/version.py disagree about "
            "PROTOCOL_VERSION — bump both together.",
        )

    def test_history_documents_the_current_version(self):
        self.assertIn(PROTOCOL_VERSION, PROTOCOL_HISTORY)

    def test_history_has_no_gaps(self):
        self.assertEqual(
            sorted(PROTOCOL_HISTORY), list(range(1, PROTOCOL_VERSION + 1)))


class TestHandshakeMessages(unittest.TestCase):

    def test_server_info_is_a_known_event(self):
        evt = p.ServerInfoEvt(protocol_version=PROTOCOL_VERSION)
        self.assertEqual(evt.type, 'server_info')
        self.assertEqual(evt.protocol_version, PROTOCOL_VERSION)

    def test_version_mismatch_carries_both_sides(self):
        evt = p.VersionMismatchEvt(
            server_version=3, client_version=2, message='x')
        self.assertEqual((evt.server_version, evt.client_version), (3, 2))


class TestHandshakeOverTheSocket(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        from fastapi.testclient import TestClient
        from backend.app.main import app
        cls.client = TestClient(app)

    def test_server_info_arrives_unprompted(self):
        with self.client.websocket_connect('/ws') as ws:
            first = ws.receive_json()
        self.assertEqual(first['type'], 'server_info')
        self.assertEqual(first['protocol_version'], PROTOCOL_VERSION)
        self.assertTrue(first['results_dir'])

    def test_matching_hello_is_silent(self):
        with self.client.websocket_connect('/ws') as ws:
            ws.receive_json()                      # server_info
            ws.send_json({'type': 'client_hello',
                          'protocol_version': PROTOCOL_VERSION})
            ws.send_json({'type': 'list_params'})
            reply = ws.receive_json()
        self.assertEqual(reply['type'], 'params_list')

    def test_stale_page_is_told(self):
        with self.client.websocket_connect('/ws') as ws:
            ws.receive_json()
            ws.send_json({'type': 'client_hello', 'protocol_version': 1})
            reply = ws.receive_json()
        self.assertEqual(reply['type'], 'version_mismatch')
        self.assertEqual(reply['server_version'], PROTOCOL_VERSION)
        self.assertEqual(reply['client_version'], 1)
        self.assertIn('Restart the backend', reply['message'])

    def test_missing_version_is_treated_as_a_mismatch(self):
        with self.client.websocket_connect('/ws') as ws:
            ws.receive_json()
            ws.send_json({'type': 'client_hello'})
            reply = ws.receive_json()
        self.assertEqual(reply['type'], 'version_mismatch')
        self.assertEqual(reply['client_version'], -1)


if __name__ == '__main__':
    unittest.main()
