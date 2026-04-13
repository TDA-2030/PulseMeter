#!/usr/bin/env python3
"""
PulseMeter desktop packaging script.

Bundles the pulsemeter_desktop package into a standalone executable using
PyInstaller.

Usage:
    python scripts/build.py [--onedir] [--debug]
"""

import argparse
import platform
import subprocess
import sys
from pathlib import Path
from typing import List

HERE = Path(__file__).resolve().parent
PROJECT_ROOT = HERE.parent
PACKAGE_ROOT = PROJECT_ROOT / "src" / "pulsemeter_desktop"
SYSTEM = platform.system()


def _sep() -> str:
    return ";" if SYSTEM == "Windows" else ":"


def _check_pyinstaller() -> None:
    try:
        import PyInstaller  # noqa: F401
    except ImportError:
        print("[build] PyInstaller not found, installing...")
        subprocess.run(
            [sys.executable, "-m", "pip", "install", "pyinstaller"],
            check=True,
        )


def _data_args() -> List[str]:
    sep = _sep()
    items: List[str] = []

    icon = PACKAGE_ROOT / "assets" / "icon.ico"
    if icon.exists():
        items += ["--add-data", f"{icon}{sep}assets"]

    fonts = PACKAGE_ROOT / "fonts"
    if fonts.is_dir() and any(fonts.glob("*.[tToO][tTpP][fF]")):
        items += ["--add-data", f"{fonts}{sep}fonts"]

    return items


def _hidden_import_args() -> List[str]:
    imports: List[str] = []

    backend = {
        "Windows": "pystray._win32",
        "Darwin": "pystray._darwin",
        "Linux": "pystray._xorg",
    }.get(SYSTEM)
    if backend:
        imports.append(backend)

    imports += [
        "zeroconf._utils.ipaddress",
        "zeroconf._handlers.incoming",
        "PIL._tkinter_finder",
    ]

    return [arg for hidden in imports for arg in ("--hidden-import", hidden)]


def _collect_args() -> List[str]:
    packages = ["soundcard", "zeroconf"]
    return [arg for package in packages for arg in ("--collect-submodules", package)]


def _exclude_args() -> List[str]:
    excludes = [
        "numpy.testing",
        "numpy.distutils",
        "numpy.f2py",
        "numpy.random",
        "numpy.polynomial",
        "numpy.ma",
        "unittest",
        "_pytest",
        "pytest",
        "doctest",
        "pydoc",
        "pdb",
        "difflib",
        "sqlite3",
        "xmlrpc",
        "ftplib",
        "imaplib",
        "smtplib",
        "telnetlib",
        "turtle",
        "tkinter.test",
    ]
    return [arg for excluded in excludes for arg in ("--exclude-module", excluded)]


def build(onedir: bool = False, debug: bool = False) -> int:
    _check_pyinstaller()

    cmd: List[str] = [sys.executable, "-m", "PyInstaller"]
    cmd.append("--onedir" if onedir else "--onefile")

    if not debug and SYSTEM in ("Windows", "Darwin"):
        cmd.append("--windowed")

    cmd += ["--name", "PulseMeter"]

    if SYSTEM == "Windows":
        ico = PACKAGE_ROOT / "assets" / "icon.ico"
        if ico.exists():
            cmd += ["--icon", str(ico)]
    elif SYSTEM == "Darwin":
        icns = PACKAGE_ROOT / "assets" / "icon.icns"
        if icns.exists():
            cmd += ["--icon", str(icns)]

    cmd += _data_args()
    cmd += _hidden_import_args()
    cmd += _collect_args()
    cmd += _exclude_args()

    cmd += ["--distpath", str(PROJECT_ROOT / "dist")]
    cmd += ["--workpath", str(PROJECT_ROOT / "build")]
    cmd += ["--specpath", str(PROJECT_ROOT)]
    cmd += ["--paths", str(PROJECT_ROOT / "src")]
    cmd += ["--clean", "--noconfirm"]
    cmd.append(str(PACKAGE_ROOT / "__main__.py"))

    print(f"[build] Platform : {SYSTEM} ({platform.machine()})")
    print(f"[build] Mode     : {'onedir' if onedir else 'onefile'}")
    print(f"[build] Console  : {'yes' if debug or SYSTEM == 'Linux' else 'no'}")
    print(f"[build] Command  :\n  {' '.join(cmd)}\n")

    result = subprocess.run(cmd, cwd=PROJECT_ROOT)
    if result.returncode != 0:
        print(f"\n[build] FAILED (exit {result.returncode})")
        return result.returncode

    if onedir:
        out = PROJECT_ROOT / "dist" / "PulseMeter"
    else:
        exe_suffix = ".exe" if SYSTEM == "Windows" else ""
        out = PROJECT_ROOT / "dist" / f"PulseMeter{exe_suffix}"

    print("\n[build] SUCCESS")
    print(f"[build] Output  : {out}")
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Build the PulseMeter desktop app into a standalone binary."
    )
    parser.add_argument(
        "--onedir",
        action="store_true",
        help="Produce a directory bundle instead of a single file.",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Keep the console window for runtime logs.",
    )
    args = parser.parse_args()
    sys.exit(build(onedir=args.onedir, debug=args.debug))
