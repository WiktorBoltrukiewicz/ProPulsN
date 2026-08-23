"""
setup_launcher.py - One-time setup: convert icon.png to icon.ico and create a
Windows desktop shortcut that opens OpenEngine without a console window.

Usage:
    python setup_launcher.py

Requirements:
    - Pillow (pip install Pillow) for PNG -> ICO conversion.
    - Windows only (shortcut creation uses PowerShell/WScript.Shell).
"""

import os
import sys
import subprocess

REPO_DIR      = os.path.dirname(os.path.abspath(__file__))
ICON_PNG      = os.path.join(REPO_DIR, 'icon.png')
ICON_ICO      = os.path.join(REPO_DIR, 'icon.ico')
LAUNCHER      = os.path.join(REPO_DIR, 'OpenEngine.pyw')
SHORTCUT_NAME = 'OpenEngine.lnk'


# -- ICO conversion -----------------------------------------------------------

def png_to_ico(src_png: str, dst_ico: str) -> None:
    """Convert a PNG file to a multi-size ICO using Pillow."""
    try:
        from PIL import Image
    except ImportError:
        raise RuntimeError(
            "Pillow is required for PNG->ICO conversion.\n"
            "Install it with:  pip install Pillow"
        )

    img = Image.open(src_png).convert('RGBA')

    # Sizes ordered LARGEST first — the first frame becomes the ICO's
    # "main" image.  Passing sizes= and append_images= together caused
    # Pillow to rescale every entry from the 16×16 thumbnail instead of
    # the original, producing heavily blurred results.
    sizes = [256, 128, 64, 48, 32, 16]
    frames = [img.resize((s, s), Image.LANCZOS) for s in sizes]

    # Save: main frame = 256×256, rest appended.  No sizes= kwarg so
    # Pillow uses the pre-rendered frames as-is.
    frames[0].save(dst_ico, format='ICO', append_images=frames[1:])
    print(f"  icon.ico created -> {dst_ico}")


# -- Desktop shortcut (Windows) -----------------------------------------------

def _get_desktop() -> str:
    """Return the current user's Desktop path."""
    import ctypes
    import ctypes.wintypes
    buf = ctypes.create_unicode_buffer(ctypes.wintypes.MAX_PATH)
    ctypes.windll.shell32.SHGetFolderPathW(None, 0x0000, None, 0, buf)  # CSIDL_DESKTOP
    desktop = buf.value
    if os.path.isdir(desktop):
        return desktop
    return os.path.join(os.path.expanduser('~'), 'Desktop')


def create_shortcut(launcher: str, icon_ico: str, shortcut_name: str) -> str:
    """Create a .lnk shortcut on the Windows Desktop via PowerShell."""
    desktop  = _get_desktop()
    lnk_path = os.path.join(desktop, shortcut_name)
    pythonw  = os.path.join(os.path.dirname(sys.executable), 'pythonw.exe')
    if not os.path.isfile(pythonw):
        pythonw = sys.executable   # fallback: console window may appear

    icon_location = f'{icon_ico}, 0' if (icon_ico and os.path.isfile(icon_ico)) else ''

    ps_script = (
        "$ws  = New-Object -ComObject WScript.Shell\n"
        f"$lnk = $ws.CreateShortcut('{lnk_path}')\n"
        f"$lnk.TargetPath       = '{pythonw}'\n"
        f"$lnk.Arguments        = '\"{launcher}\"'\n"
        f"$lnk.WorkingDirectory = '{REPO_DIR}'\n"
        "$lnk.Description      = 'OpenEngine Rocket Nozzle Simulator'\n"
    )
    if icon_location:
        ps_script += f"$lnk.IconLocation = '{icon_location}'\n"
    ps_script += "$lnk.Save()"

    result = subprocess.run(
        ['powershell', '-NoProfile', '-ExecutionPolicy', 'Bypass', '-Command', ps_script],
        capture_output=True, text=True
    )
    if result.returncode != 0:
        raise RuntimeError(f"PowerShell shortcut creation failed:\n{result.stderr}")

    print(f"  Desktop shortcut created -> {lnk_path}")
    return lnk_path


# -- Main ---------------------------------------------------------------------

def main():
    print("OpenEngine - Launcher Setup")
    print("=" * 40)

    # 1. Check PNG exists
    if not os.path.isfile(ICON_PNG):
        print(f"\n[!] icon.png not found in:\n    {REPO_DIR}")
        print("    Place your PNG icon there and re-run this script.")
        sys.exit(1)
    print("[+] icon.png found")

    # 2. Convert PNG -> ICO
    print("[+] Converting icon.png -> icon.ico ...")
    try:
        png_to_ico(ICON_PNG, ICON_ICO)
        icon_ico_use = ICON_ICO
    except RuntimeError as e:
        print(f"\n[!] {e}")
        print("    Shortcut will be created without a custom icon.")
        icon_ico_use = ''

    # 3. Create desktop shortcut (Windows only)
    if sys.platform != 'win32':
        print("[!] Desktop shortcut creation is Windows-only.")
        print("    On Linux/macOS create a launcher manually pointing to OpenEngine.pyw")
        return

    print("[+] Creating desktop shortcut ...")
    try:
        create_shortcut(LAUNCHER, icon_ico_use, SHORTCUT_NAME)
        print(f"\nDone! Double-click '{SHORTCUT_NAME}' on your Desktop to start OpenEngine.")
    except RuntimeError as e:
        print(f"\n[!] {e}")
        sys.exit(1)


if __name__ == '__main__':
    main()
