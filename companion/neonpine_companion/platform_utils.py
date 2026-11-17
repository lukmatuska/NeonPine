"""Linux / Windows specifics: autostart, CPU load, data paths, bundled files."""
import os
import shlex
import sys

APP_NAME = "NeonPine Companion"
APP_ID = "neonpine-companion"


def data_dir():
    if sys.platform == "win32":
        base = os.environ.get("APPDATA") or os.path.expanduser("~")
    else:
        base = os.environ.get("XDG_CONFIG_HOME") or os.path.expanduser("~/.config")
    d = os.path.join(base, APP_ID)
    os.makedirs(d, exist_ok=True)
    return d


def resource_path(*parts):
    """Files shipped with the app (PyInstaller unpacks them to sys._MEIPASS)."""
    base = getattr(sys, "_MEIPASS", None) or os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base, *parts)


def bundled_firmware():
    """The firmware image to offer: shipped with the app, or built in this repository."""
    here = os.path.dirname(os.path.abspath(__file__))
    for p in (resource_path("firmware", "neonpine.bin"),
              os.path.join(here, "firmware", "neonpine.bin"),
              os.path.normpath(os.path.join(here, "..", "..", "firmware", "neonpine", "neonpine.bin"))):
        if os.path.isfile(p):
            return p
    return None


def firmware_version(image):
    """bcdDevice from the USB device descriptor inside the image (usb_config.h), or None."""
    sig = bytes([18, 1, 0x10, 0x01, 0, 0, 0, 0x08, 0x09, 0x12, 0x03, 0xD0])
    k = image.find(sig)
    return image[k + 12] | image[k + 13] << 8 if k >= 0 and k + 14 <= len(image) else None


def launch_command(tray=True):
    if getattr(sys, "frozen", False):
        cmd = [sys.executable]
    else:
        cmd = [sys.executable, "-m", "neonpine_companion"]
    return cmd + (["--tray"] if tray else [])


# ---- autostart ---------------------------------------------------------------------------------

def _desktop_file():
    return os.path.join(os.environ.get("XDG_CONFIG_HOME") or os.path.expanduser("~/.config"), "autostart", APP_ID + ".desktop")


def autostart_enabled():
    if sys.platform == "win32":
        import winreg
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Run") as k:
                winreg.QueryValueEx(k, APP_NAME)
                return True
        except OSError:
            return False
    return os.path.isfile(_desktop_file())


def set_autostart(on):
    cmd = launch_command(tray=True)
    if sys.platform == "win32":
        import subprocess
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Run", 0, winreg.KEY_SET_VALUE) as k:
            if on:
                winreg.SetValueEx(k, APP_NAME, 0, winreg.REG_SZ, subprocess.list2cmdline(cmd))
            else:
                try:
                    winreg.DeleteValue(k, APP_NAME)
                except OSError:
                    pass
        return
    path = _desktop_file()
    if not on:
        if os.path.isfile(path):
            os.remove(path)
        return
    os.makedirs(os.path.dirname(path), exist_ok=True)
    workdir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    with open(path, "w") as f:
        f.write("[Desktop Entry]\nType=Application\nName=%s\nComment=Control your NeonPine tree\n"
                "Exec=%s\nPath=%s\nIcon=%s\nTerminal=false\nX-GNOME-Autostart-enabled=true\n"
                % (APP_NAME, " ".join(shlex.quote(c) for c in cmd), workdir, APP_ID))


# ---- CPU load ----------------------------------------------------------------------------------

class CpuMeter:
    def __init__(self):
        self.last = self._times()

    def _times(self):
        if sys.platform == "win32":
            import ctypes
            from ctypes import wintypes
            idle, kernel, user = wintypes.FILETIME(), wintypes.FILETIME(), wintypes.FILETIME()
            ctypes.windll.kernel32.GetSystemTimes(ctypes.byref(idle), ctypes.byref(kernel), ctypes.byref(user))
            ft = lambda f: f.dwHighDateTime << 32 | f.dwLowDateTime
            return ft(idle), ft(kernel) + ft(user)  # kernel time includes idle
        try:
            with open("/proc/stat") as f:
                v = [int(x) for x in f.readline().split()[1:]]
            return v[3] + (v[4] if len(v) > 4 else 0), sum(v)
        except OSError:
            return 0, 0

    def load(self):
        idle, total = self._times()
        d_idle, d_total = idle - self.last[0], total - self.last[1]
        self.last = (idle, total)
        return 0.0 if d_total <= 0 else max(0.0, min(1.0, 1.0 - d_idle / d_total))
