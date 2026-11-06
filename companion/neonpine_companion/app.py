"""NeonPine Companion: main window, tray icon, shared state."""
import json
import os
import sys

from PySide6.QtCore import QObject, QSize, Qt, QTime, QTimer, Signal
from PySide6.QtGui import QActionGroup, QCloseEvent, QGuiApplication
from PySide6.QtNetwork import QLocalServer, QLocalSocket
from PySide6.QtWidgets import (QApplication, QButtonGroup, QFrame, QHBoxLayout, QLabel, QMainWindow, QMenu,
                               QPushButton, QStackedWidget, QSystemTrayIcon, QVBoxLayout, QWidget)

from . import __version__, device, platform_utils
from .device import SHOW_CUSTOM0, SHOW_LIVE, Config
from .mirror import Mirror
from .widgets import QSS, Dot, app_icon, dark_palette, label, line_icon
from .worker import DeviceClient


class Prefs:
    DEFAULTS = dict(start_minimized=False, close_to_tray=True, notifications=True, schedule=False,
                    on_time="16:00", off_time="23:30", live_fps=25, page=0, tray_hint_shown=False)

    def __init__(self):
        self.path = os.path.join(platform_utils.data_dir(), "prefs.json")
        self.d = dict(self.DEFAULTS)
        try:
            with open(self.path) as f:
                self.d.update(json.load(f))
        except (OSError, ValueError):
            pass

    def __getitem__(self, k):
        return self.d.get(k, self.DEFAULTS.get(k))

    def __setitem__(self, k, v):
        self.d[k] = v
        try:
            with open(self.path, "w") as f:
                json.dump(self.d, f, indent=1)
        except OSError:
            pass


class AppContext(QObject):
    connectionChanged = Signal(bool)
    statusChanged = Signal(object)
    configChanged = Signal(object)
    customsChanged = Signal(list)
    message = Signal(str, str)          # text, kind (info / ok / error)
    liveChanged = Signal(object)        # owner or None

    def __init__(self):
        super().__init__()
        self.prefs = Prefs()
        self.client = DeviceClient(self)
        self.mirror = Mirror()
        self.info = None
        self.status = None
        self.config = None
        self.customs = []
        self.last_error = ""
        self.live_owner = None
        self.live_return = None
        self.client.worker.live_fps = int(self.prefs["live_fps"])
        w = self.client.worker
        w.connected.connect(self._on_connected)
        w.disconnected.connect(self._on_disconnected)
        w.statusUpdated.connect(self._on_status)

    @property
    def connected(self):
        return self.info is not None

    @property
    def tree_name(self):
        return (self.config.name if self.config and self.config.name else "") or "NeonPine"

    def custom_names(self):
        return [a.name for a in self.customs]

    def show_name(self, n):
        return device.show_name(n, self.custom_names())

    # -- device events

    def _on_connected(self, info):
        self.info = info
        self.status = info.status
        self.config = info.config
        self.customs = info.customs
        self.last_error = ""
        self.mirror.reset()
        self.mirror.cfg = info.config or Config()
        self.mirror.customs = info.customs
        self.mirror.update_status(info.status)
        self.connectionChanged.emit(True)
        self.statusChanged.emit(info.status)
        self.configChanged.emit(self.config)
        self.customsChanged.emit(self.customs)
        if info.status.fw_version < 3:
            self.message.emit("This tree runs firmware v%d: update it on the Firmware page to edit animations."
                              % info.status.fw_version, "info")

    def _on_disconnected(self, reason):
        was = self.info is not None
        self.info = None
        self.status = None
        self.mirror.reset()
        self.last_error = reason
        if self.live_owner:
            self.client.set_live(None)
        if was or reason:
            self.connectionChanged.emit(False)

    def _on_status(self, st):
        self.status = st
        self.mirror.update_status(st)
        self.statusChanged.emit(st)

    # -- actions

    def call(self, fn, ok=None, err=None, quiet=False):
        def on_err(e):
            if err:
                err(e)
            if not quiet:
                self.message.emit(str(e), "error")
        self.client.call(fn, ok, on_err)

    def cmd(self, fn):
        """Fire a command, then refresh the status right away."""
        self.call(lambda t: (fn(t), t.read_status())[1], self._on_status)

    def write_config(self, cfg, persist=True, ok=None):
        def done(r):
            self.config = r
            self.mirror.cfg = r
            self.configChanged.emit(r)
            if ok:
                ok(r)
        self.call(lambda t: t.write_config(cfg, persist), done)

    def upload_customs(self, anims, ok=None, err=None):
        from .custom import pack_blob
        blob = pack_blob(anims)
        snapshot = [a.copy() for a in anims]

        def done(_):
            self.customs = snapshot
            self.mirror.customs = snapshot
            self.customsChanged.emit(snapshot)
            if ok:
                ok()
        self.call(lambda t: (t.write_blob(blob), t.read_status())[1], lambda st: (self._on_status(st), done(None)), err)

    # -- live streaming (one owner at a time)

    def start_live(self, owner):
        if self.live_owner == owner:
            return
        if self.live_owner is None and self.status is not None and self.status.show != SHOW_LIVE:
            self.live_return = self.status.show
        self.live_owner = owner
        self.liveChanged.emit(owner)

    def stop_live(self, owner):
        if self.live_owner != owner:
            return
        self.live_owner = None
        self.client.set_live(None)
        self.mirror.live = None
        if self.live_return is not None and self.connected:
            back = self.live_return
            self.cmd(lambda t: t.set_show(back))
        self.live_return = None
        self.liveChanged.emit(None)

    def push_live(self, owner, left, right):
        if self.live_owner != owner:
            return
        frame = ([max(0, min(255, round(v * 255))) for v in left], [max(0, min(255, round(v * 255))) for v in right])
        self.mirror.live = frame
        if self.connected:
            self.client.set_live(frame)


class MainWindow(QMainWindow):
    def __init__(self, ctx):
        super().__init__()
        self.ctx = ctx
        self.setWindowTitle("NeonPine Companion")
        self.setWindowIcon(app_icon())
        self.resize(1180, 780)
        self.setMinimumSize(QSize(960, 640))
        self.quitting = False

        from .pages_animations import AnimationsPage
        from .pages_home import HomePage
        from .pages_live import LivePage
        from .pages_system import DiagnosticsPage, FirmwarePage, PreferencesPage
        from .pages_tree_settings import TreeSettingsPage

        root = QWidget()
        lay = QHBoxLayout(root)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        self.setCentralWidget(root)

        side = QFrame()
        side.setObjectName("sidebar")
        side.setFixedWidth(214)
        sl = QVBoxLayout(side)
        sl.setContentsMargins(12, 16, 12, 14)
        sl.setSpacing(4)
        logo = QLabel()
        logo.setPixmap(app_icon().pixmap(34, 34))
        title = label("NeonPine", h2=True)
        sub = label("Companion", muted=True)
        tl = QVBoxLayout()
        tl.setSpacing(0)
        tl.addWidget(title)
        tl.addWidget(sub)
        head = QHBoxLayout()
        head.addWidget(logo)
        head.addLayout(tl)
        head.addStretch(1)
        sl.addLayout(head)
        sl.addSpacing(18)

        self.stack = QStackedWidget()
        self.pages = [
            ("Tree", "tree", HomePage(ctx)),
            ("Animations", "edit", AnimationsPage(ctx)),
            ("Live", "live", LivePage(ctx)),
            ("Tree settings", "tune", TreeSettingsPage(ctx)),
            ("Diagnostics", "pulse", DiagnosticsPage(ctx)),
            ("Firmware", "chip", FirmwarePage(ctx)),
            ("App", "app", PreferencesPage(ctx)),
        ]
        self.nav = QButtonGroup(self)
        self.nav.setExclusive(True)
        for i, (name, icon, page) in enumerate(self.pages):
            b = QPushButton("  " + name)
            b.setProperty("nav", True)
            b.setCheckable(True)
            b.setIcon(line_icon(icon))
            b.setIconSize(QSize(18, 18))
            self.nav.addButton(b, i)
            sl.addWidget(b)
            self.stack.addWidget(page)
        self.nav.idClicked.connect(self.go)
        sl.addStretch(1)

        conn = QHBoxLayout()
        self.dot = Dot("#555")
        self.conn_text = label("Looking for the tree…", muted=True, wrap=True)
        conn.addWidget(self.dot)
        conn.addWidget(self.conn_text, 1)
        sl.addLayout(conn)
        lay.addWidget(side)

        right = QVBoxLayout()
        right.setContentsMargins(0, 0, 0, 0)
        right.setSpacing(0)
        right.addWidget(self.stack, 1)
        self.toast = QLabel()
        self.toast.setWordWrap(True)
        self.toast.hide()
        self.toast_timer = QTimer(self)
        self.toast_timer.setSingleShot(True)
        self.toast_timer.timeout.connect(self.toast.hide)
        right.addWidget(self.toast)
        lay.addLayout(right, 1)

        ctx.connectionChanged.connect(self._conn)
        ctx.statusChanged.connect(self._status)
        ctx.configChanged.connect(lambda c: self._status(ctx.status))
        ctx.message.connect(self.show_message)
        self.go(min(int(ctx.prefs["page"] or 0), len(self.pages) - 1))

    def go(self, i):
        self.nav.button(i).setChecked(True)
        self.stack.setCurrentIndex(i)
        self.ctx.prefs["page"] = i
        page = self.pages[i][2]
        if hasattr(page, "activated"):
            page.activated()

    def show_message(self, text, kind="info"):
        color = {"error": "#ff8a8a", "ok": "#7ee0a8"}.get(kind, "#ffd2b8")
        border = {"error": "#6b2b2b", "ok": "#245c3c"}.get(kind, "#5a3a24")
        self.toast.setStyleSheet("background:#16191c; color:%s; border-top:1px solid %s; padding:9px 16px;" % (color, border))
        self.toast.setText(text)
        self.toast.show()
        self.toast_timer.start(6000 if kind == "error" else 3500)

    def _conn(self, ok):
        if ok:
            self.dot.set_color("#3ccf7e")
        else:
            self.dot.set_color("#555" if not self.ctx.last_error else "#ffb347")
            err = self.ctx.last_error
            self.conn_text.setText("Not connected" + (" – " + err if err and err not in ("unplugged", "closing") else ""))

    def _status(self, st):
        if st is None or not self.ctx.connected:
            return
        on = "off" if not st.is_on else ("daylight off" if st.daylight_off else self.ctx.show_name(st.show))
        self.conn_text.setText("%s\nfw v%d · %s" % (self.ctx.tree_name, st.fw_version, on))
        self.dot.set_color("#ff5c5c" if st.fault else "#3ccf7e")

    def closeEvent(self, e: QCloseEvent):
        tray = getattr(self, "tray", None)
        if not self.quitting and tray and tray.isVisible() and self.ctx.prefs["close_to_tray"]:
            e.ignore()
            self.hide()
            if not self.ctx.prefs["tray_hint_shown"]:
                tray.showMessage("NeonPine", "Still running in the tray. Right-click the icon for quick controls.", app_icon(), 4000)
                self.ctx.prefs["tray_hint_shown"] = True
            return
        e.accept()
        QApplication.quit()


class Tray(QObject):
    def __init__(self, ctx, win):
        super().__init__()
        self.ctx, self.win = ctx, win
        self.icon = QSystemTrayIcon(app_icon("idle"))
        self.icon.setToolTip("NeonPine – not connected")
        self.menu = QMenu()
        self.menu.aboutToShow.connect(self._rebuild)
        self.icon.setContextMenu(self.menu)
        self.icon.activated.connect(self._activated)
        self.icon.show()
        win.tray = self.icon
        ctx.statusChanged.connect(self._status)
        ctx.connectionChanged.connect(self._conn)
        self._last_fault = 0
        self._rebuild()

    def _activated(self, reason):
        if reason in (QSystemTrayIcon.Trigger, QSystemTrayIcon.DoubleClick):
            if self.win.isVisible() and not self.win.isMinimized() and self.win.isActiveWindow():
                self.win.hide()
            else:
                show_window(self.win)

    def _conn(self, ok):
        self.icon.setIcon(app_icon("on" if ok else "idle"))
        if not ok:
            self.icon.setToolTip("NeonPine – not connected")
        if self.ctx.prefs["notifications"] and not self.win.isVisible():
            if ok:
                self.icon.showMessage("NeonPine", "%s connected" % self.ctx.tree_name, app_icon(), 2500)

    def _status(self, st):
        state = "on" if st.is_on and not st.daylight_off else "off"
        self.icon.setIcon(app_icon(state))
        self.icon.setToolTip("%s – %s, %d %%" % (self.ctx.tree_name, self.ctx.show_name(st.show) if st.is_on else "off",
                                                 round(st.user_level * 100 / 255)))
        if st.fault and st.fault != self._last_fault and self.ctx.prefs["notifications"]:
            self.icon.showMessage("NeonPine fault", device.FAULTS[st.fault] if st.fault < len(device.FAULTS) else str(st.fault),
                                  QSystemTrayIcon.Warning, 6000)
        self._last_fault = st.fault

    def _rebuild(self):
        m = self.menu
        m.clear()
        ctx = self.ctx
        m.addAction(app_icon(), "Open NeonPine", lambda: show_window(self.win))
        m.addSeparator()
        st = ctx.status
        if not ctx.connected or st is None:
            a = m.addAction("No tree connected")
            a.setEnabled(False)
        else:
            a = m.addAction("Tree on")
            a.setCheckable(True)
            a.setChecked(st.is_on)
            a.toggled.connect(lambda on: ctx.cmd(lambda t: t.set_power(on)))
            anims = m.addMenu("Animation")
            grp = QActionGroup(anims)
            shows = list(range(8)) + [SHOW_CUSTOM0 + k for k in range(len(ctx.customs))]
            for n in shows:
                if n == SHOW_CUSTOM0:
                    anims.addSeparator()
                act = anims.addAction(ctx.show_name(n))
                act.setCheckable(True)
                act.setChecked(st.show == n)
                act.setActionGroup(grp)
                act.triggered.connect(lambda _=False, n=n: ctx.cmd(lambda t: t.set_show(n)))
            br = m.addMenu("Brightness")
            for pct in (10, 25, 50, 75, 100):
                act = br.addAction("%d %%" % pct)
                act.triggered.connect(lambda _=False, p=pct: ctx.cmd(lambda t: t.set_brightness(round(p * 255 / 100))))
            a = m.addAction("Sleep timer (%s)" % ("%d min left" % st.sleep_min if st.sleep_on else "%d min" % (ctx.config.sleep_min if ctx.config else 20)))
            a.setCheckable(True)
            a.setChecked(st.sleep_on)
            a.toggled.connect(lambda on: ctx.cmd(lambda t: t.set_sleep(on)))
            a = m.addAction("Retro flicker")
            a.setCheckable(True)
            a.setChecked(st.style == 1)
            a.toggled.connect(lambda on: ctx.cmd(lambda t: t.set_style(on)))
        m.addSeparator()
        m.addAction("Quit", self.win_quit)

    def win_quit(self):
        self.win.quitting = True
        QApplication.quit()


def show_window(win):
    win.show()
    win.setWindowState((win.windowState() & ~Qt.WindowMinimized) | Qt.WindowActive)
    win.raise_()
    win.activateWindow()


class Scheduler(QObject):
    """Turns the tree on / off at set times while the app runs."""

    def __init__(self, ctx):
        super().__init__()
        self.ctx = ctx
        self.last = None
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.tick)
        self.timer.start(20000)

    def tick(self):
        p = self.ctx.prefs
        if not p["schedule"] or not self.ctx.connected:
            return
        now = QTime.currentTime()
        minute = now.hour() * 60 + now.minute()
        for key, on in (("on_time", True), ("off_time", False)):
            t = QTime.fromString(p[key], "HH:mm")
            if t.isValid() and t.hour() * 60 + t.minute() == minute and self.last != (key, minute):
                self.last = (key, minute)
                self.ctx.cmd(lambda tr, on=on: tr.set_power(on))
                self.ctx.message.emit("Schedule: tree %s" % ("on" if on else "off"), "info")


def main():
    QGuiApplication.setHighDpiScaleFactorRoundingPolicy(Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
    app = QApplication(sys.argv)
    app.setApplicationName(platform_utils.APP_NAME)
    app.setApplicationVersion(__version__)
    app.setDesktopFileName(platform_utils.APP_ID)
    app.setWindowIcon(app_icon())
    app.setQuitOnLastWindowClosed(False)
    app.setStyle("Fusion")
    app.setPalette(dark_palette())
    app.setStyleSheet(QSS)

    # one instance: a second start just brings the first one up
    key = "%s-%s" % (platform_utils.APP_ID, os.environ.get("USER") or os.environ.get("USERNAME") or "user")
    sock = QLocalSocket()
    sock.connectToServer(key)
    if sock.waitForConnected(300):
        sock.write(b"show")
        sock.waitForBytesWritten(300)
        return 0
    QLocalServer.removeServer(key)
    server = QLocalServer()
    server.listen(key)

    ctx = AppContext()
    win = MainWindow(ctx)
    tray = Tray(ctx, win) if QSystemTrayIcon.isSystemTrayAvailable() else None
    server.newConnection.connect(lambda: (server.nextPendingConnection(), show_window(win)))
    sched = Scheduler(ctx)  # noqa: F841 - kept alive

    start_hidden = ("--tray" in sys.argv or ctx.prefs["start_minimized"]) and tray is not None
    if not start_hidden:
        win.show()
    ctx.client.start()
    app.aboutToQuit.connect(ctx.client.shutdown)
    rc = app.exec()
    del tray
    return rc
