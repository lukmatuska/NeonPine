#!/usr/bin/env python3
"""Builds a standalone NeonPine Companion with PyInstaller (run it on the OS you build for).

    pip install PySide6 pyinstaller
    python packaging/build.py [--firmware path/to/neonpine_test.bin] [--onedir]

Windows: dist/NeonPine Companion.exe (one file). Linux: dist/NeonPine-Companion/ (a folder, starts faster;
--onefile for a single file). The firmware image is bundled so the app can update trees by itself.
"""
import argparse
import os
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
    a = ap.parse_args()
    onefile = a.onefile or (sys.platform == "win32" and not a.onedir)

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
    print("done: see", os.path.join(ROOT, "dist"))


if __name__ == "__main__":
    main()
