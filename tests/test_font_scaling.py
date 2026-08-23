"""
tests/test_font_scaling.py — Visual settings font-scaling tests.

Tests:
  1.  _apply_fonts changes QApplication default font
  2.  Main window font updates after _apply_fonts
  3.  All tab widget fonts update (no pinned widgets left at old size)
  4.  Proportional offsets are preserved (title = BASE+2, mono = BASE-1)
  5.  _apply_visual in SettingsWindow triggers a real font update
  6.  Font scaling is idempotent (calling twice with no change is safe)
  7.  Minimum floor: fonts never go below 6 pt regardless of negative offsets
  8.  allWidgets traversal covers widgets inside nested layouts
  9.  Saving persists the new base_font in settings dict
  10. Scaling down then up returns to original sizes
"""

import os
import sys
import tempfile
import unittest

_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO not in sys.path:
    sys.path.insert(0, _REPO)

from PySide6.QtWidgets import QApplication, QLabel, QWidget
from PySide6.QtGui import QFont

_qapp = QApplication.instance() or QApplication(sys.argv)

# We need the real settings path so we can restore the class attr afterwards.
from app import OpenEngineApp as _OEApp, _REPO_DIR as _APP_REPO_DIR
_REAL_SETTINGS = _OEApp._SETTINGS_FILE


def _fresh_app(start_size: int = 10):
    """Return a new OpenEngineApp normalised to *start_size* pt, fully
    isolated from the on-disk settings.json so tests don't contaminate
    each other through persisted base_font values."""
    import constants

    # ── 1. Point the class at an empty temp file BEFORE __init__ is called,
    #       so _load_settings() reads {} and never overwrites BASE_FONT.
    tf = tempfile.NamedTemporaryFile(
        mode='w', suffix='.json', delete=False, encoding='utf-8'
    )
    tf.write('{}')
    tf.close()

    _OEApp._SETTINGS_FILE = tf.name      # class-level patch
    constants.BASE_FONT = start_size

    app = _OEApp()                        # __init__ now reads the empty temp file

    # ── 2. Restore the class default; give the instance its own pointer so
    #       save_settings() still writes to the temp file (not the real one).
    _OEApp._SETTINGS_FILE = _REAL_SETTINGS
    app._SETTINGS_FILE = tf.name          # instance attribute shadows class attr

    # ── 3. Because allWidgets() may still contain widgets from previous test
    #       instances, re-normalise everything to start_size right now.
    constants.BASE_FONT = start_size
    app._apply_fonts(old_base=start_size) # no-op for new widgets; irons out
                                          # any stale sizes from old instances

    return app, tf.name


class TestFontScaling(unittest.TestCase):

    def setUp(self):
        import constants
        self.app, self._tmp_settings = _fresh_app(start_size=10)
        # Sanity-check: the app default font really is 10
        self.assertEqual(QApplication.instance().font().pointSize(), 10,
                         "setUp: app default font not at expected start_size=10")

    def tearDown(self):
        try:
            os.unlink(self._tmp_settings)
        except OSError:
            pass

    # ── 1. QApplication default font updates ─────────────────────────────────

    def test_qapp_font_updates(self):
        import constants
        constants.BASE_FONT = 14
        self.app._apply_fonts(old_base=10)
        self.assertEqual(QApplication.instance().font().pointSize(), 14)

    # ── 2. Main window font updates ───────────────────────────────────────────

    def test_main_window_font_updates(self):
        import constants
        constants.BASE_FONT = 12
        self.app._apply_fonts(old_base=10)
        self.assertEqual(self.app._win.font().pointSize(), 12)

    # ── 3. Tab widgets all reflect new size ───────────────────────────────────

    def test_tab_widgets_update(self):
        """No widget from *this* app should still show the old base size."""
        import constants
        old_base = 10
        new_base = 14
        constants.BASE_FONT = new_base
        self.app._apply_fonts(old_base=old_base)

        # Collect widgets that belong to this app's window tree
        stale = []
        for w in self.app._win.findChildren(QWidget):
            if w.font().pointSize() == old_base:
                stale.append(type(w).__name__)
        # Also check the window itself
        if self.app._win.font().pointSize() == old_base:
            stale.append('QMainWindow')
        self.assertEqual(stale, [],
                         f"Widgets still at old size {old_base}: {stale[:5]}")

    # ── 4. Proportional offsets preserved ─────────────────────────────────────

    def test_proportional_offsets_preserved(self):
        """A widget set to BASE+2 at construction must stay at BASE+2 after scale."""
        import constants

        parent = QWidget()
        lbl = QLabel("Title", parent)
        lbl.setFont(QFont("Segoe UI", 12))   # 10 + 2
        parent.show()

        constants.BASE_FONT = 14
        self.app._apply_fonts(old_base=10)

        self.assertEqual(lbl.font().pointSize(), 16)   # 14 + 2
        parent.close()

    # ── 5. SettingsWindow _apply_visual triggers real update ──────────────────

    def test_apply_visual_updates_fonts(self):
        import constants
        from settings_window import SettingsWindow

        sw = SettingsWindow(self.app._win, self.app)
        sw._font_spin.setText('14')
        sw._apply_visual()

        self.assertEqual(constants.BASE_FONT, 14)
        self.assertEqual(QApplication.instance().font().pointSize(), 14)

    # ── 6. Idempotent — calling with same value is safe ───────────────────────

    def test_idempotent_call(self):
        import constants
        try:
            self.app._apply_fonts(old_base=10)
            self.app._apply_fonts(old_base=10)
        except Exception as exc:
            self.fail(f"Idempotent _apply_fonts raised: {exc}")

    # ── 7. Floor at 6 pt ──────────────────────────────────────────────────────

    def test_floor_at_six_pt(self):
        """An extreme negative offset must not produce a font below 6 pt."""
        import constants

        parent = QWidget()
        lbl = QLabel("tiny", parent)
        lbl.setFont(QFont("Segoe UI", 7))   # 10 - 3
        parent.show()

        # Scale from 10 → 8: offset = -3, naive result = 5 → floor to 6
        constants.BASE_FONT = 8
        self.app._apply_fonts(old_base=10)

        self.assertGreaterEqual(lbl.font().pointSize(), 6)
        parent.close()

    # ── 8. Nested layout widgets are reached ──────────────────────────────────

    def test_nested_widgets_updated(self):
        import constants

        outer = QWidget()
        inner = QWidget(outer)
        deep  = QLabel("deep", inner)
        deep.setFont(QFont("Segoe UI", 10))
        outer.show()

        constants.BASE_FONT = 13
        self.app._apply_fonts(old_base=10)

        self.assertEqual(deep.font().pointSize(), 13)
        outer.close()

    # ── 9. Settings dict updated ──────────────────────────────────────────────

    def test_settings_dict_updated(self):
        from settings_window import SettingsWindow

        sw = SettingsWindow(self.app._win, self.app)
        sw._font_spin.setText('16')
        sw._apply_visual()

        self.assertEqual(self.app.settings['base_font'], 16)

    # ── 10. Scale down then up returns to original ────────────────────────────

    def test_roundtrip_scale(self):
        import constants

        parent = QWidget()
        lbl = QLabel("round-trip", parent)
        lbl.setFont(QFont("Segoe UI", 10))
        parent.show()

        # Scale up 10 → 14
        constants.BASE_FONT = 14
        self.app._apply_fonts(old_base=10)
        self.assertEqual(lbl.font().pointSize(), 14)

        # Scale back down 14 → 10
        constants.BASE_FONT = 10
        self.app._apply_fonts(old_base=14)
        self.assertEqual(lbl.font().pointSize(), 10)

        parent.close()


if __name__ == '__main__':
    unittest.main()
