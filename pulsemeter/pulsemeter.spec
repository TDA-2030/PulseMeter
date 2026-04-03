# -*- mode: python ; coding: utf-8 -*-
# This spec is kept as a reference / manual override entry point.
# Prefer using  build.py  which auto-detects the platform and passes
# the correct arguments to PyInstaller without editing this file.

import platform
_SYSTEM = platform.system()
_SEP    = ';' if _SYSTEM == 'Windows' else ':'

# Runtime data: icon for pystray, fonts bundled at startup
_datas = [('assets/icon.ico', 'assets')]
import os
if os.path.isdir('fonts'):
    _datas.append(('fonts', 'fonts'))

# Platform-specific pystray backend
_hidden = {
    'Windows': ['pystray._win32'],
    'Darwin':  ['pystray._darwin'],
    'Linux':   ['pystray._xorg'],
}.get(_SYSTEM, [])
_hidden += [
    'zeroconf._utils.ipaddress',
    'zeroconf._handlers.incoming',
    'PIL._tkinter_finder',
]

_excludes = [
    # numpy internals not needed at runtime
    'numpy.testing', 'numpy.distutils', 'numpy.f2py',
    'numpy.random', 'numpy.polynomial', 'numpy.ma', 'numpy.matrixlib',
    # test frameworks
    'unittest', '_pytest', 'pytest', 'doctest',
    # dev / documentation tools
    'pydoc', 'pdb', 'difflib',
    # unused stdlib
    'sqlite3', 'xmlrpc', 'ftplib', 'imaplib', 'smtplib',
    'telnetlib', 'turtle', 'tkinter.test',
]

a = Analysis(
    ['pulsemeter.py'],
    pathex=[],
    binaries=[],
    datas=_datas,
    hiddenimports=_hidden,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=_excludes,
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='PulseMeter',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=(_SYSTEM == 'Linux'),   # console visible only on Linux
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='assets/icon.ico',
)
