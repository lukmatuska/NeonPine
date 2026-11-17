#!/usr/bin/env python3
"""Builds a standalone NeonPine Companion with PyInstaller (run it on the OS you build for).

    pip install PySide6 pyinstaller
    python packaging/build.py [--firmware path/to/neonpine_test.bin] [--onedir] [--installer]

Windows: dist/NeonPine Companion.exe (one file). Linux: dist/NeonPine-Companion/ (a folder, starts faster;
--onefile for a single file). The firmware image is bundled so the app can update trees by itself.
Windows --installer: builds the folder version and wraps it with Inno Setup 6 (ISCC on PATH or in its default
location) into dist/NeonPine-Companion-Setup-<version>.exe.
"""
import argparse
import os
import re
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(HERE, ".."))
BUILD = os.path.join(ROOT, "build")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--firmware", default=os.path.join(ROOT, "..", "firmware", "neonpine_test", "neonpine_test.bin"))
    ap.add_argument("--onefile", action="store_true", help="single file (default on Windows)")
    ap.add_argument("--onedir", action="store_true", help="folder (default on Linux)")
    ap.add_argument("--installer", action="store_true", help="Windows: folder build + Inno Setup installer")
    a = ap.parse_args()
    if a.installer and sys.platform != "win32":
        ap.error("--installer needs Windows (Inno Setup)")
    iscc = find_iscc() if a.installer else None
    onefile = not a.installer and (a.onefile or (sys.platform == "win32" and not a.onedir))

    os.makedirs(os.path.join(BUILD, "firmware"), exist_ok=True)
    subprocess.check_call([sys.executable, os.path.join(HERE, "make_icons.py"), BUILD])
    add = []
    if os.path.isfile(a.firmware):
        shutil.copyfile(a.firmware, os.path.join(BUILD, "firmware", "neonpine.bin"))
        add = ["--add-data", os.path.join(BUILD, "firmware", "neonpine.bin") + os.pathsep + "firmware"]
        print("bundling firmware", os.path.abspath(a.firmware))
    else:
        print("no firmware image at %s - the app will offer 'Flash a file...' only" % a.firmware)

    name = "NeonPine Companion" if sys.platform == "win32" else "NeonPine-Companion"
    cmd = [sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", "--windowed", "--name", name,
           "--distpath", os.path.join(ROOT, "dist"), "--workpath", os.path.join(BUILD, "pyinstaller"),
           "--specpath", BUILD, "--onefile" if onefile else "--onedir",
           "--icon", os.path.join(BUILD, "neonpine-companion.ico" if sys.platform == "win32" else "neonpine-companion.png"),
           "--add-data", os.path.join(BUILD, "neonpine-companion.png") + os.pathsep + ".",
           "--hidden-import", "PySide6.QtMultimedia", "--hidden-import", "PySide6.QtNetwork",
           "--exclude-module", "tkinter"] + add + [os.path.join(ROOT, "neonpine-companion.py")]
    print(" ".join(cmd))
    subprocess.check_call(cmd, cwd=ROOT)
    if a.installer:
        dist = os.path.join(ROOT, "dist")
        subprocess.check_call([iscc, "/Q", "/DAppVersion=" + app_version(), "/DSourceDir=" + os.path.join(dist, name),
                               "/DOutputDir=" + dist, "/DIconFile=" + os.path.join(BUILD, "neonpine-companion.ico"),
                               os.path.join(HERE, "windows", "neonpine-companion.iss")])
    print("done: see", os.path.join(ROOT, "dist"))


def app_version():
    with open(os.path.join(ROOT, "neonpine_companion", "__init__.py")) as f:
        return re.search(r'__version__\s*=\s*"([^"]+)"', f.read()).group(1)


def find_iscc():
    found = shutil.which("iscc")
    if found:
        return found
    for env in ("ProgramFiles(x86)", "ProgramFiles", "LOCALAPPDATA"):
        base = os.environ.get(env)
        for sub in ("Inno Setup 6", os.path.join("Programs", "Inno Setup 6")):
            p = os.path.join(base, sub, "ISCC.exe") if base else ""
            if p and os.path.isfile(p):
                return p
    sys.exit("Inno Setup 6 not found: install it (winget install JRSoftware.InnoSetup) or put ISCC.exe on PATH")


if __name__ == "__main__":
    main()
