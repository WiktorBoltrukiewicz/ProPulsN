"""
The assumptions the container image is built on.

A Dockerfile fails loudly when a COPY path is wrong, but it fails *silently*
when the layout drifts underneath it: `core/__init__.py` finds REPO_ROOT by
walking four directories up from itself, so moving `backend/` one level would
leave an image that builds, starts, serves an empty page and writes results
into a directory nobody mounted.

These tests need no Docker. They pin the handful of facts the image depends
on, so the breakage shows up here rather than in a container someone is trying
to use.
"""

import io
import os
import re
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.app.core import PARAMS_DIR, REPO_ROOT, RESULTS_DIR  # noqa: E402

DOCKERFILE = os.path.join(REPO_ROOT, 'Dockerfile')
COMPOSE = os.path.join(REPO_ROOT, 'docker-compose.yml')
DOCKERIGNORE = os.path.join(REPO_ROOT, '.dockerignore')


def _read(path):
    with io.open(path, encoding='utf-8') as fh:
        return fh.read()


def _directives(path):
    """The file with its comments stripped.

    Both these files explain themselves at length, and several comments name
    the very things these tests assert are absent — searching the prose finds
    "matplotlib" in the note saying matplotlib is excluded.
    """
    lines = []
    for line in _read(path).splitlines():
        stripped = line.strip()
        if stripped and not stripped.startswith('#'):
            lines.append(line)
    return chr(10).join(lines)


class TestFilesExist(unittest.TestCase):

    def test_the_three_files_are_present(self):
        for path in (DOCKERFILE, COMPOSE, DOCKERIGNORE):
            with self.subTest(path=os.path.basename(path)):
                self.assertTrue(os.path.isfile(path))


class TestCopiedPathsExist(unittest.TestCase):
    """Every COPY source must be a real path in the repository."""

    def test_each_copy_source_exists(self):
        for line in _read(DOCKERFILE).splitlines():
            match = re.match(r'^COPY\s+(.+)$', line.strip())
            if not match:
                continue
            parts = match.group(1).split()
            for source in parts[:-1]:            # last token is the destination
                with self.subTest(source=source):
                    self.assertTrue(
                        os.path.exists(os.path.join(REPO_ROOT, source.rstrip('/'))),
                        f"Dockerfile copies {source!r}, which does not exist",
                    )

    def test_it_copies_everything_the_app_serves(self):
        dockerfile = _read(DOCKERFILE)
        for needed in ('backend/', 'frontend/', 'params/', 'main.py'):
            with self.subTest(needed=needed):
                self.assertIn(needed, dockerfile)


class TestLayoutAssumption(unittest.TestCase):
    """REPO_ROOT is derived from the source tree's shape, so pin the shape."""

    def test_core_sits_four_levels_below_the_root(self):
        from backend.app.core import __file__ as core_init
        relative = os.path.relpath(os.path.dirname(core_init), REPO_ROOT)
        self.assertEqual(relative.replace(os.sep, '/'), 'backend/app/core')

    def test_the_writable_directories_are_directly_under_the_root(self):
        for path, name in ((PARAMS_DIR, 'params'), (RESULTS_DIR, 'results')):
            with self.subTest(name=name):
                self.assertEqual(os.path.dirname(path), REPO_ROOT)
                self.assertEqual(os.path.basename(path), name)

    def test_the_frontend_sits_where_the_app_mounts_it(self):
        from backend.app.main import FRONTEND_DIR
        self.assertEqual(os.path.dirname(FRONTEND_DIR), REPO_ROOT)
        self.assertTrue(os.path.isfile(os.path.join(FRONTEND_DIR, 'index.html')))

    def test_the_cli_the_runner_spawns_is_at_the_root(self):
        from backend.app.services.simulation_runner import MAIN_PY
        self.assertEqual(os.path.dirname(MAIN_PY), REPO_ROOT)
        self.assertTrue(os.path.isfile(MAIN_PY))


class TestComposeMountsMatchTheApp(unittest.TestCase):
    """The mounts have to land on the directories the app actually writes."""

    def setUp(self):
        self.compose = _read(COMPOSE)

    def test_mounts_the_two_writable_directories(self):
        for name in ('params', 'results'):
            with self.subTest(name=name):
                self.assertIn(f'./{name}:/app/{name}', self.compose)

    def test_container_paths_agree_with_the_image_workdir(self):
        # WORKDIR /app in the Dockerfile is what makes /app/params correct.
        self.assertIn('WORKDIR /app', _read(DOCKERFILE))

    def test_stays_on_loopback(self):
        """An app with no auth must not be published by default."""
        self.assertIn('127.0.0.1:8000:8000', self.compose)


class TestImageStaysSmall(unittest.TestCase):

    def test_matplotlib_is_not_in_the_backend_requirements(self):
        """The single largest thing the web app can do without."""
        reqs = _directives(os.path.join(REPO_ROOT, 'backend', 'requirements.txt'))
        self.assertNotIn('matplotlib', reqs.lower())

    def test_the_build_context_excludes_the_heavy_directories(self):
        ignored = _read(DOCKERIGNORE)
        for path in ('.git/', 'tests/', 'google_stich/', 'icon.png'):
            with self.subTest(path=path):
                self.assertIn(path, ignored)

    def test_results_are_not_baked_into_the_image(self):
        self.assertIn('results/*', _read(DOCKERIGNORE))


class TestStreamingSurvivesTheContainer(unittest.TestCase):
    """The live console is the one thing a container can quietly break."""

    def test_python_output_is_unbuffered(self):
        """A buffered pipe stalls the convergence chart until the run ends."""
        self.assertIn('PYTHONUNBUFFERED=1', _read(DOCKERFILE))

    def test_uvicorn_listens_on_all_interfaces(self):
        """Without this the published port reaches nothing."""
        self.assertIn('--host', _read(DOCKERFILE))
        self.assertIn('0.0.0.0', _read(DOCKERFILE))

    def test_no_reload_flag_in_the_image(self):
        self.assertNotIn('--reload', _directives(DOCKERFILE))


class TestStaticFilesRevalidate(unittest.TestCase):
    """Upgrading means pulling an image and reloading a long-open tab.

    Chrome will reuse a cached ES module across an ordinary reload, which would
    leave new Python serving an old page — the mirror of the stale-backend trap
    in version.py, with none of its warning.
    """

    @classmethod
    def setUpClass(cls):
        from fastapi.testclient import TestClient
        from backend.app.main import app
        cls.client = TestClient(app)

    def test_the_page_and_its_modules_must_be_revalidated(self):
        for path in ('/', '/js/app.js', '/js/simulation.js', '/css/theme.css'):
            with self.subTest(path=path):
                response = self.client.get(path)
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.headers.get('cache-control'), 'no-cache')

    def test_revalidation_is_cheap(self):
        """`no-cache` still means "keep it" — an unchanged file costs a 304."""
        first = self.client.get('/js/app.js')
        etag = first.headers.get('etag')
        self.assertTrue(etag)
        again = self.client.get('/js/app.js', headers={'If-None-Match': etag})
        self.assertEqual(again.status_code, 304)



class TestWorkflowIsValid(unittest.TestCase):
    """A malformed workflow fails in 0s with no log, which reads like nothing
    ran at all. It has happened once: an unquoted `image size: ` inside a
    `run:` scalar turned into a YAML mapping. Parsing it here costs nothing.
    """

    WORKFLOW = os.path.join(REPO_ROOT, '.github', 'workflows', 'tests.yml')

    def setUp(self):
        try:
            import yaml
        except ImportError:                       # pragma: no cover
            self.skipTest('PyYAML not installed')
        self.yaml = yaml
        with io.open(self.WORKFLOW, encoding='utf-8') as fh:
            self.parsed = yaml.safe_load(fh)

    def test_it_parses(self):
        self.assertIsInstance(self.parsed, dict)

    def test_both_jobs_are_defined(self):
        self.assertEqual(sorted(self.parsed['jobs']), ['docker', 'test'])

    def test_the_docker_job_builds_and_exercises_the_image(self):
        """Building alone would not catch a container that cannot subprocess."""
        steps = self.parsed['jobs']['docker']['steps']
        script = chr(10).join(str(step.get('run', '')) for step in steps)
        self.assertIn('docker build', script)
        self.assertIn('scripts/smoke_container.py', script)

    def test_the_test_job_installs_both_requirements_files(self):
        steps = self.parsed['jobs']['test']['steps']
        script = chr(10).join(str(step.get('run', '')) for step in steps)
        self.assertIn('backend/requirements.txt', script)
        self.assertIn('-r requirements.txt', script)


class TestSmokeScript(unittest.TestCase):

    SCRIPT = os.path.join(REPO_ROOT, 'scripts', 'smoke_container.py')

    def test_it_exists_and_compiles(self):
        self.assertTrue(os.path.isfile(self.SCRIPT))
        with io.open(self.SCRIPT, encoding='utf-8') as fh:
            compile(fh.read(), self.SCRIPT, 'exec')

    def test_it_checks_what_only_a_container_can_break(self):
        source = _read(self.SCRIPT)
        for probe in ('server_info', 'run_simulation', 'simulation_complete',
                      '/files/'):
            with self.subTest(probe=probe):
                self.assertIn(probe, source)

if __name__ == '__main__':
    unittest.main()
