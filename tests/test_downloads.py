"""The one REST endpoint: GET /files/{name}.

It is the only route that hands bytes to the browser, so its refusals matter
more than its successes — most of what follows is about what it will *not*
serve.
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.app.api.downloads import SERVABLE_TYPES, download_url  # noqa: E402
from backend.app.core import RESULTS_DIR  # noqa: E402


class DownloadTestCase(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        from fastapi.testclient import TestClient
        from backend.app.main import app
        cls.client = TestClient(app)
        os.makedirs(RESULTS_DIR, exist_ok=True)

    def _write(self, name, text="x_m,r_m\n0,1\n"):
        """Create a file in results/ and remove it when the test finishes.

        newline="" so Windows does not rewrite \n as \r\n on the way to disk —
        the byte-fidelity test below is meaningless otherwise.
        """
        path = os.path.join(RESULTS_DIR, name)
        with open(path, "w", encoding="utf-8", newline="") as fh:
            fh.write(text)
        self.addCleanup(lambda: os.path.exists(path) and os.unlink(path))
        return path


class TestServesFiles(DownloadTestCase):

    def test_serves_the_bytes_unchanged(self):
        body = "x_m,r_m\n0,1\n2,3\n"
        self._write("_test_dl.csv", body)
        r = self.client.get("/files/_test_dl.csv")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.content, body.encode("utf-8"))

    def test_sends_it_as_an_attachment(self):
        """Otherwise the browser renders a CSV instead of saving it."""
        self._write("_test_dl.csv")
        r = self.client.get("/files/_test_dl.csv")
        disposition = r.headers.get("content-disposition", "")
        self.assertIn("attachment", disposition)
        self.assertIn("_test_dl.csv", disposition)

    def test_media_type_matches_the_extension(self):
        for name, expected in (("_test_dl.csv", "text/csv"),
                               ("_test_dl.prof", "text/plain"),
                               ("_test_dl.dxf", "application/dxf")):
            with self.subTest(name):
                self._write(name)
                r = self.client.get(f"/files/{name}")
                self.assertEqual(r.status_code, 200)
                self.assertTrue(r.headers["content-type"].startswith(expected))

    def test_names_with_spaces_round_trip(self):
        self._write("_test dl copy.csv")
        r = self.client.get(download_url("_test dl copy.csv"))
        self.assertEqual(r.status_code, 200)


class TestRefusals(DownloadTestCase):

    def test_missing_file_is_404(self):
        r = self.client.get("/files/_not_here_at_all.csv")
        self.assertEqual(r.status_code, 404)

    def test_unservable_extension_is_refused(self):
        """results/ can hold unrelated files; they stay unreachable."""
        self._write("_test_secret.txt", "not for the web")
        r = self.client.get("/files/_test_secret.txt")
        self.assertEqual(r.status_code, 404)
        self.assertNotIn("not for the web", r.text)

    def test_extensionless_file_is_refused(self):
        self._write("_test_noext", "nope")
        r = self.client.get("/files/_test_noext")
        self.assertEqual(r.status_code, 404)
        self.assertNotIn("nope", r.text)

    def test_traversal_cannot_escape_results(self):
        for attempt in (
            "../CLAUDE.md",
            "..%2FCLAUDE.md",
            "....//CLAUDE.md",
            "subdir/file.csv",
            "..\CLAUDE.md",
        ):
            with self.subTest(attempt):
                r = self.client.get(f"/files/{attempt}")
                self.assertNotEqual(r.status_code, 200, f"{attempt} was served!")
                self.assertNotIn("Migration", r.text)

    def test_absolute_path_is_refused(self):
        r = self.client.get("/files//etc/passwd")
        self.assertNotEqual(r.status_code, 200)

    def test_a_params_file_is_not_reachable(self):
        """Only results/ is served — params/ sits next to it."""
        r = self.client.get("/files/default.json")
        self.assertEqual(r.status_code, 404)

    def test_post_is_not_allowed(self):
        """Read-only: this endpoint must never accept an upload."""
        self._write("_test_dl.csv")
        r = self.client.post("/files/_test_dl.csv", content=b"overwrite")
        self.assertEqual(r.status_code, 405)


class TestUrlHelper(unittest.TestCase):

    def test_percent_encodes_the_name(self):
        self.assertEqual(download_url("a b.csv"), "/files/a%20b.csv")

    def test_covers_every_format_the_app_writes(self):
        self.assertEqual(set(SERVABLE_TYPES), {".csv", ".dxf", ".prof"})


class TestStaticMountStillWorks(DownloadTestCase):
    """The route is registered before the catch-all StaticFiles mount."""

    def test_index_is_still_served(self):
        r = self.client.get("/")
        self.assertEqual(r.status_code, 200)
        self.assertIn("ProPulsN", r.text)

    def test_frontend_assets_still_served(self):
        self.assertEqual(self.client.get("/js/app.js").status_code, 200)


if __name__ == "__main__":
    unittest.main()
