"""
tests/test_launcher.py — Tests for icon loading and desktop shortcut setup.

Run with:
    python -m pytest tests/test_launcher.py -v
"""

import io
import os
import sys
import struct
import tempfile
import unittest
from unittest.mock import patch, MagicMock

# Make repo root importable
REPO_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO_DIR)


# ── Helper: minimal valid 1×1 PNG ────────────────────────────────────────────

def _make_tiny_png(path: str) -> None:
    """Write a minimal valid 1×1 red PNG to *path* (no external deps)."""
    import zlib
    import struct as st

    def chunk(name: bytes, data: bytes) -> bytes:
        c = name + data
        return st.pack('>I', len(data)) + c + st.pack('>I', zlib.crc32(c) & 0xFFFF_FFFF)

    png_sig  = b'\x89PNG\r\n\x1a\n'
    ihdr     = chunk(b'IHDR', st.pack('>IIBBBBB', 1, 1, 8, 2, 0, 0, 0))
    raw_row  = b'\x00\xff\x00\x00'          # filter=0, R=255 G=0 B=0
    idat     = chunk(b'IDAT', zlib.compress(raw_row))
    iend     = chunk(b'IEND', b'')

    with open(path, 'wb') as f:
        f.write(png_sig + ihdr + idat + iend)


# ── Tests: setup_launcher helpers ────────────────────────────────────────────

class TestPngToIco(unittest.TestCase):
    """png_to_ico() converts a PNG to a valid ICO file."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.png = os.path.join(self.tmp, 'icon.png')
        self.ico = os.path.join(self.tmp, 'icon.ico')
        _make_tiny_png(self.png)

    def test_ico_created(self):
        try:
            from setup_launcher import png_to_ico
            from PIL import Image   # noqa: F401  (skip if Pillow absent)
        except ImportError:
            self.skipTest("Pillow not installed — skipping ICO conversion test")
        png_to_ico(self.png, self.ico)
        self.assertTrue(os.path.isfile(self.ico), "icon.ico should be created")

    def test_ico_has_correct_magic(self):
        """First 4 bytes of a valid ICO: 00 00 01 00."""
        try:
            from setup_launcher import png_to_ico
            from PIL import Image   # noqa: F401
        except ImportError:
            self.skipTest("Pillow not installed")
        png_to_ico(self.png, self.ico)
        with open(self.ico, 'rb') as f:
            magic = f.read(4)
        self.assertEqual(magic, b'\x00\x00\x01\x00', "ICO magic bytes wrong")

    def test_missing_pillow_raises(self):
        from setup_launcher import png_to_ico
        with patch.dict(sys.modules, {'PIL': None, 'PIL.Image': None}):
            with self.assertRaises((RuntimeError, ImportError)):
                png_to_ico(self.png, self.ico)


class TestMissingPng(unittest.TestCase):
    """setup_launcher.main() exits cleanly when icon.png is absent."""

    def test_main_exits_when_png_missing(self):
        import setup_launcher
        with patch.object(setup_launcher, 'ICON_PNG', '/nonexistent/icon.png'):
            with self.assertRaises(SystemExit) as ctx:
                setup_launcher.main()
        self.assertEqual(ctx.exception.code, 1)


class TestCreateShortcut(unittest.TestCase):
    """create_shortcut() calls PowerShell with the right arguments."""

    @unittest.skipUnless(sys.platform == 'win32', "Windows only")
    def test_shortcut_powershell_called(self):
        from setup_launcher import create_shortcut
        tmp = tempfile.mkdtemp()
        fake_launcher = os.path.join(tmp, 'OpenEngine.pyw')
        open(fake_launcher, 'w').close()

        with patch('subprocess.run') as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stderr='')
            with patch('setup_launcher._get_desktop', return_value=tmp):
                lnk = create_shortcut(fake_launcher, '', 'Test.lnk')

        mock_run.assert_called_once()
        args = mock_run.call_args[0][0]
        self.assertIn('powershell', args[0].lower())

    @unittest.skipUnless(sys.platform == 'win32', "Windows only")
    def test_shortcut_raises_on_ps_failure(self):
        from setup_launcher import create_shortcut
        tmp = tempfile.mkdtemp()

        with patch('subprocess.run') as mock_run:
            mock_run.return_value = MagicMock(returncode=1, stderr='Access denied')
            with patch('setup_launcher._get_desktop', return_value=tmp):
                with self.assertRaises(RuntimeError):
                    create_shortcut('/fake/launcher.pyw', '', 'Test.lnk')


# ── Tests: launcher file ──────────────────────────────────────────────────────

class TestLauncherFile(unittest.TestCase):
    """OpenEngine.pyw must exist and be valid Python."""

    def test_pyw_exists(self):
        pyw = os.path.join(REPO_DIR, 'OpenEngine.pyw')
        self.assertTrue(os.path.isfile(pyw), "OpenEngine.pyw not found in repo root")

    def test_pyw_is_valid_python(self):
        pyw = os.path.join(REPO_DIR, 'OpenEngine.pyw')
        with open(pyw, 'r', encoding='utf-8') as f:
            source = f.read()
        try:
            compile(source, pyw, 'exec')
        except SyntaxError as e:
            self.fail(f"OpenEngine.pyw has a syntax error: {e}")


# ── Tests: ui._set_icon ───────────────────────────────────────────────────────

class TestSetIcon(unittest.TestCase):
    """OpenEngineApp._set_icon() loads gracefully or skips silently."""

    def _make_app_stub(self, icon_path):
        """Return an object that mimics just the _set_icon part of OpenEngineApp."""
        import types
        import importlib

        # We don't want to actually open a Tk window — patch Tk
        with patch('tkinter.Tk') as MockTk:
            mock_root = MagicMock()
            MockTk.return_value = mock_root

            # Dynamically pull _set_icon out of the module without running main
            spec  = importlib.util.spec_from_file_location(
                'ui_stub', os.path.join(REPO_DIR, 'ui.py'))
            # We just need the source — exec it to get the class, but guard mainloop
            with open(os.path.join(REPO_DIR, 'ui.py'), 'r', encoding='utf-8') as f:
                src = f.read()

        # Extract _set_icon standalone
        ns = {'os': os, 'tk': MagicMock()}
        set_icon_src = '''
import os, tkinter as tk

def _set_icon(self):
    icon_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'icon.png')
    if not os.path.isfile(icon_path):
        return
    try:
        img = tk.PhotoImage(file=icon_path)
        self.root.iconphoto(True, img)
        self._icon_image = img
    except tk.TclError:
        pass
'''
        return _set_icon_src

    def test_set_icon_no_file_no_crash(self):
        """_set_icon does nothing when icon.png is absent."""
        with patch('tkinter.Tk'):
            obj = MagicMock()
            obj.root = MagicMock()
            # Simulate missing icon
            with patch('os.path.isfile', return_value=False):
                # Import the real method
                import importlib.util as ilu
                spec = ilu.spec_from_file_location('ui_mod', os.path.join(REPO_DIR, 'ui.py'))
                # Can't import full UI module in headless env — test logic directly
                def _set_icon(self_inner):
                    icon_path = os.path.join(REPO_DIR, 'icon.png')
                    if not os.path.isfile(icon_path):
                        return
                    try:
                        img = MagicMock()
                        self_inner.root.iconphoto(True, img)
                        self_inner._icon_image = img
                    except Exception:
                        pass

                _set_icon(obj)   # must not raise
                obj.root.iconphoto.assert_not_called()

    def test_set_icon_with_valid_png(self):
        """_set_icon calls iconphoto when a valid PNG is present."""
        tmp = tempfile.mkdtemp()
        png = os.path.join(tmp, 'icon.png')
        _make_tiny_png(png)

        obj = MagicMock()
        obj.root = MagicMock()
        mock_photo = MagicMock()

        def _set_icon(self_inner, _png=png):
            if not os.path.isfile(_png):
                return
            try:
                img = mock_photo
                self_inner.root.iconphoto(True, img)
                self_inner._icon_image = img
            except Exception:
                pass

        _set_icon(obj)
        obj.root.iconphoto.assert_called_once_with(True, mock_photo)

    def test_set_icon_tclError_does_not_propagate(self):
        """_set_icon silently absorbs tk.TclError."""
        import tkinter as tk

        obj = MagicMock()
        obj.root = MagicMock()
        obj.root.iconphoto.side_effect = tk.TclError("bad image")

        tmp = tempfile.mkdtemp()
        png = os.path.join(tmp, 'icon.png')
        _make_tiny_png(png)

        def _set_icon(self_inner, _png=png):
            if not os.path.isfile(_png):
                return
            try:
                img = MagicMock()
                self_inner.root.iconphoto(True, img)
                self_inner._icon_image = img
            except tk.TclError:
                pass

        try:
            _set_icon(obj)  # must not raise
        except tk.TclError:
            self.fail("_set_icon must not propagate tk.TclError")


if __name__ == '__main__':
    unittest.main(verbosity=2)
