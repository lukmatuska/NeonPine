"""Diagnostics, firmware updates, app preferences."""
import os
import sys

from PySide6.QtCore import QTime
from PySide6.QtWidgets import (QCheckBox, QFileDialog, QGridLayout, QGroupBox, QHBoxLayout, QMessageBox, QPlainTextEdit,
                               QProgressBar, QPushButton, QScrollArea, QSpinBox, QTimeEdit, QVBoxLayout, QWidget)

from . import __version__, device, platform_utils
from .widgets import ACCENT, GOOD, WARN, Sparkline, card, hstretch, label


# ---- diagnostics -------------------------------------------------------------------------------

class Stat(QWidget):
    def __init__(self, title):
        super().__init__()
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        lay.addWidget(label(title, muted=True))
        self.value = label("–")
        self.value.setStyleSheet("font-size: 15pt; font-weight: 600;")
        lay.addWidget(self.value)
        self.sub = label("", muted=True)
        lay.addWidget(self.sub)

    def set(self, value, sub=""):
        self.value.setText(value)
        self.sub.setText(sub)


class DiagnosticsPage(QWidget):
    def __init__(self, ctx):
        super().__init__()
        self.ctx = ctx
        outer = QVBoxLayout(self)
        outer.setContentsMargins(24, 20, 24, 16)
        head = QHBoxLayout()
        head.addWidget(label("Diagnostics", h1=True))
        head.addStretch(1)
        self.clear_btn = QPushButton("Clear fault")
        self.clear_btn.setProperty("danger", True)
        self.clear_btn.clicked.connect(lambda: ctx.cmd(lambda t: t.command("clear")))
        head.addWidget(self.clear_btn)
        outer.addLayout(head)
        self.fault = label("", wrap=True)
        outer.addWidget(self.fault)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        body = QWidget()
        g = QGridLayout(body)
        g.setContentsMargins(0, 8, 8, 8)
        g.setSpacing(14)
        scroll.setWidget(body)
        outer.addWidget(scroll, 1)

        c, l = card()
        l.addWidget(label("High voltage", h2=True))
        row = QHBoxLayout()
        self.hv = Stat("HV rail")
        self.boost = Stat("Boost")
        self.budget = Stat("Power budget")
        for w in (self.hv, self.boost, self.budget):
            row.addWidget(w)
        l.addLayout(row)
        self.hv_graph = Sparkline(ACCENT, lo=None, hi=None)
        self.hv_graph.setMinimumHeight(110)
        l.addWidget(self.hv_graph)
        g.addWidget(c, 0, 0, 1, 2)

        c, l = card()
        l.addWidget(label("Touch pad", h2=True))
        row = QHBoxLayout()
        self.touch = Stat("Raw / baseline")
        self.gesture = Stat("Last gesture")
        row.addWidget(self.touch)
        row.addWidget(self.gesture)
        l.addLayout(row)
        self.touch_graph = Sparkline(GOOD)
        l.addWidget(self.touch_graph)
        g.addWidget(c, 1, 0)

        c, l = card()
        l.addWidget(label("Light sensor", h2=True))
        row = QHBoxLayout()
        self.light = Stat("Room")
        self.adapt = Stat("Adaptive brightness")
        row.addWidget(self.light)
        row.addWidget(self.adapt)
        l.addLayout(row)
        self.light_graph = Sparkline(WARN)
        l.addWidget(self.light_graph)
        g.addWidget(c, 1, 1)

        c, l = card()
        l.addWidget(label("Lamps and timing", h2=True))
        row = QHBoxLayout()
        self.pwm = Stat("PWM")
        self.late = Stat("Edges late")
        self.lamps = Stat("Lit electrodes")
        for w in (self.pwm, self.late, self.lamps):
            row.addWidget(w)
        l.addLayout(row)
        g.addWidget(c, 2, 0)

        c, l = card()
        l.addWidget(label("System", h2=True))
        row = QHBoxLayout()
        self.supply = Stat("USB supply")
        self.uptime = Stat("Up")
        self.mem = Stat("Free stack")
        for w in (self.supply, self.uptime, self.mem):
            row.addWidget(w)
        l.addLayout(row)
        self.ident = label("", muted=True)
        l.addWidget(self.ident)
        g.addWidget(c, 2, 1)

        adv = QGroupBox("Advanced (bring-up and tuning – the tree carries up to 105 V on its back)")
        al = QGridLayout(adv)
        self.hv_set = QSpinBox()
        self.hv_set.setRange(0, 105)
        self.hv_set.setValue(100)
        self.hv_set.setSuffix(" V")
        b = QPushButton("Set HV")
        b.clicked.connect(lambda: ctx.cmd(lambda t, v=None: t.command("hv", self.hv_set.value())))
        al.addWidget(label("HV setpoint (0 = boost off)", muted=True), 0, 0)
        al.addWidget(self.hv_set, 0, 1)
        al.addWidget(b, 0, 2)
        self.touch_thr = QSpinBox()
        self.touch_thr.setRange(0, 5000)
        self.touch_thr.setValue(500)
        b = QPushButton("Set threshold")
        b.clicked.connect(lambda: ctx.cmd(lambda t: t.command16("touch", self.touch_thr.value())))
        al.addWidget(label("Touch threshold above baseline (0 = default 500)", muted=True), 1, 0)
        al.addWidget(self.touch_thr, 1, 1)
        al.addWidget(b, 1, 2)
        self.budget_cb = QCheckBox("Power budget limiter")
        self.budget_cb.setChecked(True)
        self.budget_cb.toggled.connect(lambda on: ctx.cmd(lambda t: t.command("budget", 1 if on else 0)))
        al.addWidget(self.budget_cb, 2, 0)
        shows = QHBoxLayout()
        for name, n in (("Test sequence", 8), ("Brightness sweep", 9), ("Steady glow", 10)):
            bb = QPushButton(name)
            bb.clicked.connect(lambda _=False, n=n: ctx.cmd(lambda t: t.set_show(n)))
            shows.addWidget(bb)
        wave = QPushButton("Simulate a wave")
        wave.clicked.connect(lambda: ctx.cmd(lambda t: t.command("wave")))
        shows.addWidget(wave)
        shows.addStretch(1)
        al.addWidget(label("Bring-up shows", muted=True), 3, 0)
        al.addLayout(shows, 3, 1, 1, 2)
        g.addWidget(adv, 3, 0, 1, 2)
        g.setColumnStretch(0, 1)
        g.setColumnStretch(1, 1)
        g.setRowStretch(4, 1)

        ctx.statusChanged.connect(self._status)
        ctx.connectionChanged.connect(self._conn)
        self._conn(False)

    def _conn(self, ok):
        self.setEnabled(True)
        if not ok:
            self.fault.setText("No tree connected.")
            self.clear_btn.hide()

    def _status(self, s):
        if not self.ctx.connected:
            return
        self.hv.set("%.1f V" % s.hv, "target %d V · boost %s" % (s.hv_set, "on" if s.boost_on else "off"))
        self.hv_graph.marks = [(s.hv_set, "#5a3a24")]
        self.hv_graph.add(s.hv)
        self.boost.set("%.1f %%" % (s.duty_pm / 10), "pulsing · %.1f µs at %.1f kHz" % (s.ton / 48, 1000 / s.period_us if s.period_us else 0))
        self.budget.set("%d / 255" % s.budget, "limiting" if s.budget < 255 else "no limit")
        thr = self.touch_thr.value() or 500
        self.touch.set("%d / %d" % (s.touch, s.touch_base), "TOUCHED" if s.touched else "threshold +%d" % thr)
        self.touch_graph.marks = [(s.touch_base + thr, "#245c3c")]
        self.touch_graph.add(s.touch)
        g = s.gesture & 15
        self.gesture.set(device.GESTURES[g] if g < len(device.GESTURES) else "?", "event #%d" % (s.gesture >> 4))
        self.light.set("%d lx" % s.lux, "ambient %d · own light %d%s" % (s.ambient, s.reflection, " · OFF FOR DAYLIGHT" if s.daylight_off else ""))
        self.light_graph.add(s.ambient)
        self.adapt.set("%.2f" % (s.adapt / 255), "sensor features %s" % ("on" if s.autolight else "off"))
        self.pwm.set("%d ms / %d µs" % (s.pwm_ms, s.pwm_min_10us * 10), "frame / strike minimum · level %d" % s.level)
        self.late.set("≤ %d µs" % s.late_us, "peak %d µs (USB traffic adds)" % s.late_peak_us)
        lit = sum(bin(s.lamp_bits(i)).count("1") for i in range(10))
        self.lamps.set("%d of 20" % lit, "")
        self.supply.set("%.2f V" % (s.vdd_mv / 1000), "")
        up = s.uptime_ms // 1000
        self.uptime.set("%d:%02d:%02d" % (up // 3600, up // 60 % 60, up % 60), "")
        self.mem.set("%d B" % s.stack_free if s.caps else "–", "of 2 kB RAM, worst case so far")
        self.ident.setText("Firmware v%d · chip %08X · %d custom animations · settings %s" %
                           (s.fw_version, s.uid, s.n_custom, "not saved yet" if s.unsaved else "saved"))
        if s.fault:
            self.fault.setText("FAULT: %s – the boost is off until the fault is cleared (or the tree is replugged)."
                               % (device.FAULTS[s.fault] if s.fault < len(device.FAULTS) else s.fault))
            self.fault.setStyleSheet("color: #ff8a8a;")
            self.clear_btn.show()
        else:
            self.fault.setText("")
            self.clear_btn.hide()


# ---- firmware ----------------------------------------------------------------------------------

class FirmwarePage(QWidget):
    def __init__(self, ctx):
        super().__init__()
        self.ctx = ctx
        self.busy = False
        lay = QVBoxLayout(self)
        lay.setContentsMargins(24, 20, 24, 16)
        lay.setSpacing(14)
        lay.addWidget(label("Firmware", h1=True))

        c, l = card()
        self.on_tree = label("", h2=True)
        l.addWidget(self.on_tree)
        self.bundled = label("", muted=True, wrap=True)
        l.addWidget(self.bundled)
        self.update_btn = QPushButton("Update the tree")
        self.update_btn.setProperty("primary", True)
        self.update_btn.clicked.connect(self._update_bundled)
        file_btn = QPushButton("Flash a file…")
        file_btn.clicked.connect(self._flash_file)
        rec_btn = QPushButton("Recovery…")
        rec_btn.setToolTip("For a tree that doesn't show up any more: catches the bootloader when you plug it in")
        rec_btn.clicked.connect(self._recovery)
        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.clicked.connect(self._cancel)
        self.cancel_btn.hide()
        l.addWidget(hstretch(self.update_btn, file_btn, rec_btn, None, self.cancel_btn))
        self.progress = QProgressBar()
        self.progress.setRange(0, 1000)
        self.progress.setValue(0)
        l.addWidget(self.progress)
        self.step = label("", muted=True)
        l.addWidget(self.step)
        lay.addWidget(c)

        c, l = card()
        l.addWidget(label("How it works", h2=True))
        l.addWidget(label(
            "The tree restarts into its USB bootloader, the app erases and writes the new firmware, reads it back to verify it, "
            "and starts it – about 10 seconds. The settings and your custom animations live in a separate part of the flash and "
            "survive the update. The bootloader itself is never touched, so a failed update can always be repeated: if the tree "
            "doesn't come back, use Recovery and plug it in – the bootloader waits 5 seconds after power-up.", muted=True, wrap=True))
        if sys.platform.startswith("linux"):
            l.addWidget(label("Linux: the udev rule firmware/tools/99-neonpine.rules must cover the bootloader (1209:B003) too.",
                              muted=True, wrap=True))
        lay.addWidget(c)
        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setMaximumBlockCount(500)
        self.log.setPlaceholderText("Update log")
        lay.addWidget(self.log, 1)

        w = ctx.client.worker
        w.flashProgress.connect(self._progress)
        w.flashDone.connect(self._done)
        ctx.connectionChanged.connect(lambda ok: self._refresh())
        ctx.statusChanged.connect(lambda s: self._refresh())
        self._refresh()

    def _image(self):
        p = platform_utils.bundled_firmware()
        if not p:
            return None, None
        with open(p, "rb") as f:
            return p, f.read()

    def _refresh(self):
        st = self.ctx.status
        self.on_tree.setText("On the tree: firmware v%d" % st.fw_version if st and self.ctx.connected else "No tree connected")
        p, img = self._image()
        if img:
            v = platform_utils.firmware_version(img)
            self.bundled.setText("Included with the app: firmware v%s · %.1f kB\n%s" % (v if v is not None else "?", len(img) / 1024, p))
        else:
            self.bundled.setText("No firmware image is included with this copy of the app – use “Flash a file…”.")
        self.update_btn.setEnabled(bool(img) and not self.busy)

    def _confirm(self, what):
        return QMessageBox.question(self, "Update firmware", "%s\n\nKeep the tree plugged in until it's done. Continue?" % what) == QMessageBox.Yes

    def _start(self, image, what, allow=False):
        if self.busy:
            return
        if not self._confirm(what):
            return
        self.busy = True
        self.ctx.stop_live(self.ctx.live_owner) if self.ctx.live_owner else None
        self.cancel_btn.show()
        self.update_btn.setEnabled(False)
        self.log.appendPlainText("— %s (%d bytes)" % (what, len(image)))
        self.ctx.client.flash(image, allow)

    def _update_bundled(self):
        p, img = self._image()
        if img:
            v = platform_utils.firmware_version(img)
            self._start(img, "Write firmware v%s (%s) to the tree." % (v if v is not None else "?", os.path.basename(p)))

    def _flash_file(self):
        path, _ = QFileDialog.getOpenFileName(self, "Firmware image", "", "Firmware (*.bin);;All files (*)")
        if not path:
            return
        with open(path, "rb") as f:
            img = f.read()
        allow = False
        if len(img) > 15360:
            if QMessageBox.warning(self, "Large image", "This image is bigger than 15 kB and will overwrite the settings and the "
                                   "custom animations stored on the tree. Flash it anyway?",
                                   QMessageBox.Yes | QMessageBox.No) != QMessageBox.Yes:
                return
            allow = True
        if platform_utils.firmware_version(img) is None and QMessageBox.warning(
                self, "Unknown image", "This doesn't look like NeonPine firmware (no NeonPine USB descriptor). Flash it anyway?",
                QMessageBox.Yes | QMessageBox.No) != QMessageBox.Yes:
            return
        self._start(img, "Write %s to the tree." % os.path.basename(path), allow)

    def _recovery(self):
        p, img = self._image()
        if not img:
            path, _ = QFileDialog.getOpenFileName(self, "Firmware image", "", "Firmware (*.bin)")
            if not path:
                return
            with open(path, "rb") as f:
                img = f.read()
        QMessageBox.information(self, "Recovery", "Unplug the tree now, then press OK and plug it back in within 12 seconds.")
        self.busy = True
        self.cancel_btn.show()
        self.update_btn.setEnabled(False)
        self.log.appendPlainText("— Recovery: waiting for the bootloader")
        self.ctx.client.flash(img, False)

    def _cancel(self):
        self.ctx.client.worker.cancel_flash = True

    def _progress(self, text, frac):
        self.progress.setValue(int(frac * 1000))
        self.step.setText(text)
        if not text.startswith("Writing "):
            self.log.appendPlainText(text)

    def _done(self, ok, msg):
        self.busy = False
        self.cancel_btn.hide()
        self.step.setText(msg)
        self.log.appendPlainText(("OK: " if ok else "FAILED: ") + msg)
        if not ok:
            self.progress.setValue(0)
        self.ctx.message.emit(msg, "ok" if ok else "error")
        self._refresh()


# ---- preferences -------------------------------------------------------------------------------

class PreferencesPage(QWidget):
    def __init__(self, ctx):
        super().__init__()
        self.ctx = ctx
        p = ctx.prefs
        lay = QVBoxLayout(self)
        lay.setContentsMargins(24, 20, 24, 16)
        lay.setSpacing(14)
        lay.addWidget(label("App", h1=True))

        c, l = card()
        l.addWidget(label("Window and tray", h2=True))
        self.autostart = QCheckBox("Start with the computer (in the tray)")
        try:
            self.autostart.setChecked(platform_utils.autostart_enabled())
        except OSError:
            pass
        self.autostart.toggled.connect(self._autostart)
        self.minimized = QCheckBox("Start hidden in the tray")
        self.minimized.setChecked(bool(p["start_minimized"]))
        self.minimized.toggled.connect(lambda v: p.__setitem__("start_minimized", v))
        self.close_tray = QCheckBox("Closing the window keeps the app running in the tray")
        self.close_tray.setChecked(bool(p["close_to_tray"]))
        self.close_tray.toggled.connect(lambda v: p.__setitem__("close_to_tray", v))
        self.notify = QCheckBox("Notifications (tree connected, faults)")
        self.notify.setChecked(bool(p["notifications"]))
        self.notify.toggled.connect(lambda v: p.__setitem__("notifications", v))
        for w in (self.autostart, self.minimized, self.close_tray, self.notify):
            l.addWidget(w)
        lay.addWidget(c)

        c, l = card()
        l.addWidget(label("Schedule", h2=True))
        self.sched = QCheckBox("Turn the tree on and off at set times (while this app runs)")
        self.sched.setChecked(bool(p["schedule"]))
        self.sched.toggled.connect(lambda v: p.__setitem__("schedule", v))
        l.addWidget(self.sched)
        self.on_t = QTimeEdit(QTime.fromString(p["on_time"], "HH:mm"))
        self.on_t.setDisplayFormat("HH:mm")
        self.on_t.timeChanged.connect(lambda t: p.__setitem__("on_time", t.toString("HH:mm")))
        self.off_t = QTimeEdit(QTime.fromString(p["off_time"], "HH:mm"))
        self.off_t.setDisplayFormat("HH:mm")
        self.off_t.timeChanged.connect(lambda t: p.__setitem__("off_time", t.toString("HH:mm")))
        l.addWidget(hstretch(label("On at", muted=True), self.on_t, 20, label("Off at", muted=True), self.off_t, None))
        lay.addWidget(c)

        c, l = card()
        l.addWidget(label("Live streaming", h2=True))
        self.fps = QSpinBox()
        self.fps.setRange(5, 40)
        self.fps.setValue(int(p["live_fps"]))
        self.fps.setSuffix(" frames / s")
        self.fps.valueChanged.connect(self._fps)
        l.addWidget(hstretch(label("Frame rate to the tree", muted=True), self.fps, None))
        l.addWidget(label("Every frame is a USB transfer the tree handles between lamp pulses; lower it if the lamps "
                          "flicker while streaming.", muted=True, wrap=True))
        lay.addWidget(c)

        c, l = card()
        l.addWidget(label("About", h2=True))
        l.addWidget(label("NeonPine Companion %s · Python %s · settings in %s" % (
            __version__, sys.version.split()[0], platform_utils.data_dir()), muted=True, wrap=True))
        l.addWidget(label("Firmware updates use a Python port of minichlink's b003boot programmer (ch32fun, MIT).", muted=True, wrap=True))
        lay.addWidget(c)
        lay.addStretch(1)

    def _autostart(self, on):
        try:
            platform_utils.set_autostart(on)
        except OSError as e:
            self.ctx.message.emit("Couldn't change autostart: %s" % e, "error")

    def _fps(self, v):
        self.ctx.prefs["live_fps"] = v
        self.ctx.client.worker.live_fps = v
