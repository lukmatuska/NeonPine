#!/usr/bin/env python3
"""Builds the A5 customer pamphlet (one sheet, printed both sides): QR codes + PDF.

    pip install segno
    python docs/pamphlet/build.py

Writes qr-download.svg and qr-repo.svg next to this file, then prints pamphlet.html to NeonPine-pamphlet.pdf with
headless Chrome / Edge / Chromium.
"""
import os
import shutil
import subprocess
import sys
import tempfile

import segno

HERE = os.path.dirname(os.path.abspath(__file__))
QR = {
    "qr-download.svg": "https://github.com/lukmatuska/NeonPine/releases/latest",
    "qr-repo.svg": "https://github.com/lukmatuska/NeonPine",
}


def find_browser():
    names = ["chrome", "msedge", "chromium", "chromium-browser", "google-chrome"]
    for n in names:
        p = shutil.which(n)
        if p:
            return p
    for env in ("ProgramFiles", "ProgramFiles(x86)", "LOCALAPPDATA"):
        base = os.environ.get(env)
        for sub in (r"Google\Chrome\Application\chrome.exe", r"Microsoft\Edge\Application\msedge.exe"):
            p = os.path.join(base, sub) if base else ""
            if p and os.path.isfile(p):
                return p
    sys.exit("no Chrome / Edge / Chromium found for printing the PDF")


def main():
    for name, url in QR.items():
        segno.make(url, error="m").save(os.path.join(HERE, name), kind="svg", border=2, scale=10, dark="#1b1b1f",
                                        xmldecl=False, svgns=True, nl=False)
    out = os.path.join(HERE, "NeonPine-pamphlet.pdf")
    with tempfile.TemporaryDirectory() as prof:
        subprocess.run([find_browser(), "--headless", "--disable-gpu", "--no-sandbox", "--user-data-dir=" + prof,
                        "--no-pdf-header-footer", "--print-to-pdf=" + out,
                        "file:///" + os.path.join(HERE, "pamphlet.html").replace("\\", "/")], check=True,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    print("wrote", out)


if __name__ == "__main__":
    main()
