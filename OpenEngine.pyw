"""
OpenEngine.pyw — Silent launcher for the OpenEngine GUI.

On Windows, .pyw files are run by pythonw.exe, which suppresses the console
window. Double-click this file (or a shortcut to it) to start the app with no
terminal visible. Run setup_launcher.py once to create a desktop shortcut.
"""
import runpy, os, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
runpy.run_path(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'ui.py'),
               run_name='__main__')
