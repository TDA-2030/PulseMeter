#!/usr/bin/env python3
"""
PulseMeter client packaging script.

Bundles pulsemeter.py into a standalone executable using PyInstaller.
Run this script from any platform — it detects the host OS and applies
the appropriate options automatically.

Usage:
    python build.py [--onedir] [--debug]

Options:
    --onedir   Produce a directory bundle instead of a single file.
               Starts faster; useful for debugging packaging issues.
    --debug    Keep the console window visible (shows print/traceback output).
"""

import argparse
import platform
import subprocess
import sys
from pathlib import Path
from typing import List

HERE = Path(__file__).parent.resolve()
SYSTEM = platform.system()  # 'Windows' | 'Linux' | 'Darwin'


def _sep() -> str:
    """PyInstaller data separator: ';' on Windows, ':' everywhere else."""
    return ';' if SYSTEM == 'Windows' else ':'


def _check_pyinstaller() -> None:
    try:
        import PyInstaller  # noqa: F401
    except ImportError:
        print("[build] PyInstaller not found — installing...")
        subprocess.run(
            [sys.executable, '-m', 'pip', 'install', 'pyinstaller'],
            check=True,
        )


def _data_args() -> List[str]:
    """
    Return --add-data flags for all runtime resources that PyInstaller
    cannot discover via static import analysis.
    """
    sep   = _sep()
    items = []

    # assets/icon.ico — loaded at runtime by pystray for the system tray icon
    icon = HERE / 'assets' / 'icon.ico'
    if icon.exists():
        items += ['--add-data', f'{icon}{sep}assets']

    # fonts/ — bundled TTF/OTF files registered at startup
    fonts = HERE / 'fonts'
    if fonts.is_dir() and any(fonts.glob('*.[tToO][tTpP][fF]')):
        items += ['--add-data', f'{fonts}{sep}fonts']

    return items


def _hidden_import_args() -> List[str]:
    """
    Return --hidden-import flags for packages that use lazy / dynamic loading
    and are therefore invisible to PyInstaller's static analyser.
    """
    imports = []

    # pystray loads its platform backend at import time via a conditional,
    # which PyInstaller cannot trace.  Only include the current platform's
    # module so the binary doesn't carry dead code.
    backend = {
        'Windows': 'pystray._win32',
        'Darwin':  'pystray._darwin',
        'Linux':   'pystray._xorg',
    }.get(SYSTEM)
    if backend:
        imports.append(backend)

    # zeroconf uses lazy service-type registration
    imports += [
        'zeroconf._utils.ipaddress',
        'zeroconf._handlers.incoming',
    ]

    # Pillow's tkinter integration helper
    imports.append('PIL._tkinter_finder')

    return [arg for h in imports for arg in ('--hidden-import', h)]


def _collect_args() -> List[str]:
    """
    Return --collect-submodules flags for packages whose sub-modules are loaded
    dynamically.  --collect-submodules includes only Python modules (no extra
    data/test files), unlike --collect-all which bundles everything.
    """
    # soundcard and zeroconf use dynamic imports; collect Python modules only.
    packages = ['soundcard', 'zeroconf']
    return [arg for p in packages for arg in ('--collect-submodules', p)]


def _exclude_args() -> List[str]:
    """
    Return --exclude-module flags for packages that are definitely unused.

    numpy ships a large amount of test/build infrastructure that PyInstaller
    cannot prune on its own.  Standard-library modules like unittest, pydoc,
    and sqlite3 are never imported by this application.
    """
    excludes = [
        # numpy internals not needed at runtime
        'numpy.testing',
        'numpy.distutils',
        'numpy.f2py',
        'numpy.random',
        'numpy.polynomial',
        'numpy.ma',
        'numpy.matrixlib',
        # test frameworks
        'unittest',
        '_pytest',
        'pytest',
        'doctest',
        # dev / documentation tools
        'pydoc',
        'pdb',
        'difflib',
        # unused stdlib
        'sqlite3',
        'xmlrpc',
        'ftplib',
        'imaplib',
        'smtplib',
        'telnetlib',
        'turtle',
        'tkinter.test',
    ]
    return [arg for e in excludes for arg in ('--exclude-module', e)]


def build(onedir: bool = False, debug: bool = False) -> int:
    _check_pyinstaller()

    cmd: List[str] = [sys.executable, '-m', 'PyInstaller']

    # --- Output mode ---
    cmd.append('--onedir' if onedir else '--onefile')

    # --- Console window ---
    # Keep console on Linux (there is no windowed concept there).
    # On Windows / macOS hide it unless --debug is requested.
    if not debug and SYSTEM in ('Windows', 'Darwin'):
        cmd.append('--windowed')

    # --- App name ---
    cmd += ['--name', 'PulseMeter']

    # --- Icon ---
    if SYSTEM == 'Windows':
        ico = HERE / 'assets' / 'icon.ico'
        if ico.exists():
            cmd += ['--icon', str(ico)]
    elif SYSTEM == 'Darwin':
        icns = HERE / 'assets' / 'icon.icns'
        if icns.exists():
            cmd += ['--icon', str(icns)]

    # --- Data files ---
    cmd += _data_args()

    # --- Hidden imports ---
    cmd += _hidden_import_args()

    # --- Full package collection ---
    cmd += _collect_args()

    # --- Exclude unused modules ---
    cmd += _exclude_args()

    # --- Output / work paths ---
    cmd += ['--distpath', str(HERE / 'dist')]
    cmd += ['--workpath', str(HERE / 'build')]
    cmd += ['--specpath', str(HERE)]

    # --- Build hygiene ---
    cmd += ['--clean', '--noconfirm']

    # --- Entry point ---
    cmd.append(str(HERE / 'pulsemeter.py'))

    print(f"[build] Platform : {SYSTEM} ({platform.machine()})")
    print(f"[build] Mode     : {'onedir' if onedir else 'onefile'}")
    print(f"[build] Console  : {'yes' if debug or SYSTEM == 'Linux' else 'no'}")
    print(f"[build] Command  :\n  {' '.join(cmd)}\n")

    result = subprocess.run(cmd, cwd=HERE)

    if result.returncode != 0:
        print(f"\n[build] FAILED (exit {result.returncode})")
        return result.returncode

    # Report output location
    if onedir:
        out = HERE / 'dist' / 'PulseMeter'
    else:
        exe_suffix = '.exe' if SYSTEM == 'Windows' else ''
        out = HERE / 'dist' / f'PulseMeter{exe_suffix}'

    print(f"\n[build] SUCCESS")
    print(f"[build] Output  : {out}")
    return 0


if __name__ == '__main__':
    parser = argparse.ArgumentParser(
        description='Build the PulseMeter client into a standalone binary.'
    )
    parser.add_argument(
        '--onedir',
        action='store_true',
        help='Produce a directory bundle instead of a single file.',
    )
    parser.add_argument(
        '--debug',
        action='store_true',
        help='Keep the console window (shows stdout/stderr at runtime).',
    )
    args = parser.parse_args()
    sys.exit(build(onedir=args.onedir, debug=args.debug))
