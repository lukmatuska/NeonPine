"""Home: the tree as it glows right now, quick controls, the animation picker."""
import sys
import time

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import (QFrame, QGridLayout, QHBoxLayout, QPushButton, QScrollArea, QSlider, QVBoxLayout,
                               QWidget)

from . import builtin
from .device import BUILTIN_HINTS, BUILTIN_NAMES, SHOW_CUSTOM0, SHOW_LIVE, ModeParams
from .mirror import Mirror
from .widgets import TreeView, card, hstretch, label, set_prop


class AnimCard(QFrame):
    clicked = Signal(int)

    def __init__(self, show, name, hint, parent=None):
        super().__init__(parent)
        self.show = show
        self.setProperty("card", True)
        self.setCursor(Qt.PointingHandCursor)
        self.setToolTip(hint)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(8, 8, 8, 8)
        lay.setSpacing(4)
        self.view = TreeView(compact=True)
        self.view.setFixedHeight(92)
        self.view.setAttribute(Qt.WA_TransparentForMouseEvents)
        lay.addWidget(self.view)
        self.name = label(name)
        self.name.setAlignment(Qt.AlignCenter)
        lay.addWidget(self.name)
        self.setFixedWidth(118)

    def set_active(self, on):
        self.setStyleSheet("QFrame[card=\"true\"] { border: 1px solid %s; background: %s; }"
                           % (("#ff7a2f", "#1f1611") if on else ("#23272c", "#16191c")))

    def mousePressEvent(self, e):
        self.clicked.emit(self.show)


class HomePage(QWidget):
    def __init__(self, ctx):
        super().__init__()
        self.ctx = ctx
        self.cards = []
        self._t0 = time.monotonic()
        self._busy_slider = False

        outer = QHBoxLayout(self)
        outer.setContentsMargins(24, 20, 24, 20)
        outer.setSpacing(22)

        # left: the tree
        left = QVBoxLayout()
        self.title = label("NeonPine", h1=True)
        self.subtitle = label("Looking for your tree…", muted=True)
        left.addWidget(self.title)
        left.addWidget(self.subtitle)
        self.tree = TreeView()
        self.tree.setToolTip("Click the touch pad to go to the next animation")
        self.tree.touchPadClicked.connect(lambda: ctx.cmd(lambda t: t.command("wave")))
        left.addWidget(self.tree, 1)
        self.hint = label("", muted=True, wrap=True)
        self.hint.setAlignment(Qt.AlignCenter)
        left.addWidget(self.hint)
        outer.addLayout(left, 5)

        # right: controls + animations
        right = QVBoxLayout()
        right.setSpacing(14)

        c, cl = card()
        row = QHBoxLayout()
        self.power = QPushButton("Turn off")
        self.power.setMinimumWidth(110)
        self.power.clicked.connect(self._toggle_power)
        self.state = label("", h2=True)
        row.addWidget(self.state, 1)
        row.addWidget(self.power)
        cl.addLayout(row)
        cl.addWidget(label("Brightness", muted=True))
        self.bright = QSlider(Qt.Horizontal)
        self.bright.setRange(8, 255)
        self.bright_val = label("100 %")
        self.bright_val.setMinimumWidth(44)
        self.bright.sliderPressed.connect(lambda: setattr(self, "_busy_slider", True))
        self.bright.sliderReleased.connect(self._bright_release)
        self.bright.valueChanged.connect(self._bright_changed)
        cl.addWidget(hstretch(self.bright, self.bright_val))
        toggles = QHBoxLayout()
        self.retro = QPushButton("Retro flicker")
        self.retro.setCheckable(True)
        self.retro.setToolTip("Shorter strike pulses: the neon flickers like an old sign (touch: triple tap)")
        self.retro.clicked.connect(lambda on: ctx.cmd(lambda t: t.set_style(on)))
        self.sleep = QPushButton("Sleep timer")
        self.sleep.setCheckable(True)
        self.sleep.setToolTip("Dims slowly, then switches the tree off (touch: double tap)")
        self.sleep.clicked.connect(lambda on: ctx.cmd(lambda t: t.set_sleep(on)))
        toggles.addWidget(self.retro)
        toggles.addWidget(self.sleep)
        toggles.addStretch(1)
        cl.addLayout(toggles)
        right.addWidget(c)

        right.addWidget(label("Animations", h2=True))
        self.grid_host = QWidget()
        self.grid = QGridLayout(self.grid_host)
        self.grid.setContentsMargins(0, 0, 0, 0)
        self.grid.setSpacing(10)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(self.grid_host)
        right.addWidget(scroll, 1)
        self.live_note = label("", muted=True, wrap=True)
        right.addWidget(self.live_note)
        outer.addLayout(right, 6)

        self._build_cards()
        self._thumb_mirror = Mirror()

        ctx.connectionChanged.connect(self._conn)
        ctx.statusChanged.connect(self._status)
        ctx.customsChanged.connect(lambda _: self._build_cards())
        ctx.configChanged.connect(lambda _: self._status(ctx.status))

        self.timer = QTimer(self)
        self.timer.timeout.connect(self._tick)
        self.timer.start(33)
        self._frame_no = 0
        self._conn(False)

    def _build_cards(self):
        for c in self.cards:
            c.setParent(None)
            c.deleteLater()
        self.cards = []
        items = [(n, BUILTIN_NAMES[n], BUILTIN_HINTS[n]) for n in range(8)]
        items += [(SHOW_CUSTOM0 + k, a.name or "Custom %d" % (k + 1), "Your animation (%d keys, %.1f s)" % (len(a.keys), a.total_ms / 1000))
                  for k, a in enumerate(self.ctx.customs)]
        cols = 4
        for k, (n, name, hint) in enumerate(items):
            c = AnimCard(n, name, hint)
            c.clicked.connect(self._pick)
            self.grid.addWidget(c, k // cols, k % cols)
            self.cards.append(c)
        self.grid.setRowStretch(len(items) // cols + 1, 1)
        self._status(self.ctx.status)

    def _pick(self, n):
        if not self.ctx.connected:
            return
        if self.ctx.live_owner:
            self.ctx.message.emit("Live mode is on (%s) – stop it on the Live page first." % self.ctx.live_owner, "info")
            return
        self.ctx.cmd(lambda t: t.set_show(n))

    def _toggle_power(self):
        st = self.ctx.status
        if st:
            on = not st.is_on
            self.ctx.cmd(lambda t: t.set_power(on))

    def _bright_changed(self, v):
        self.bright_val.setText("%d %%" % round(v * 100 / 255))
        if not self._busy_slider and self.ctx.connected and self.ctx.status and v != self.ctx.status.user_level:
            self._send_bright(v)

    def _bright_release(self):
        self._busy_slider = False
        self._send_bright(self.bright.value())

    def _send_bright(self, v):
        self.ctx.cmd(lambda t: t.set_brightness(v))

    def _conn(self, ok):
        for w in (self.power, self.bright, self.retro, self.sleep):
            w.setEnabled(ok)
        if not ok:
            self.title.setText("NeonPine")
            err = self.ctx.last_error
            if err and "access" in err:
                self.subtitle.setText("No permission for the USB device.")
                self.hint.setText("Install the udev rule:  sudo cp firmware/tools/99-neonpine.rules /etc/udev/rules.d/ "
                                  "&& sudo udevadm control --reload && sudo udevadm trigger  – then replug the tree."
                                  if sys.platform.startswith("linux") else err)
            else:
                self.subtitle.setText("Plug your NeonPine into a USB port.")
                self.hint.setText("The tree appears here a few seconds after it is plugged in (after its 5 s bootloader wait).")
            self.state.setText("Not connected")
            self.tree.set_levels([0] * 10, [0] * 10)
            self.tree.dim_board = True

    def _status(self, st):
        ctx = self.ctx
        if st is None or not ctx.connected:
            return
        self.tree.dim_board = False
        self.title.setText(ctx.tree_name)
        parts = ["firmware v%d" % st.fw_version, "HV %.0f V" % st.hv]
        if st.fault:
            parts.append("FAULT")
        self.subtitle.setText(" · ".join(parts))
        if not st.is_on:
            self.state.setText("Off")
        elif st.daylight_off:
            self.state.setText("Off for daylight")
        else:
            self.state.setText(ctx.show_name(st.show))
        self.power.setText("Turn off" if st.is_on else "Turn on")
        set_prop(self.power, "primary", not st.is_on)
        if not self._busy_slider and not self.bright.isSliderDown():
            self.bright.blockSignals(True)
            self.bright.setValue(st.user_level)
            self.bright.blockSignals(False)
            self.bright_val.setText("%d %%" % round(st.user_level * 100 / 255))
        self.retro.setChecked(st.style == 1)
        self.sleep.setChecked(st.sleep_on)
        self.sleep.setText("Sleep timer · %d min" % st.sleep_min if st.sleep_on else "Sleep timer")
        for c in self.cards:
            c.set_active(c.show == st.show)
        if st.show == SHOW_LIVE:
            self.live_note.setText("Live: the app is driving the tree%s." % (" (" + ctx.live_owner + ")" if ctx.live_owner else ""))
        else:
            self.live_note.setText("")
        self.hint.setText("Touch pad on the tree: tap = next · double tap = sleep timer · triple tap = retro · hold = brightness · hold 3 s = off/on")

    def _tick(self):
        if not self.isVisible():
            return
        l, r = self.ctx.mirror.frame()
        self.tree.set_levels(l, r)
        self._frame_no += 1
        if self._frame_no % 3:
            return  # thumbnails at ~10 fps
        t = int((time.monotonic() - self._t0) * 1000) + 20000
        params = (self.ctx.config.params if self.ctx.config else [ModeParams() for _ in range(6)])
        m = self._thumb_mirror
        if self.ctx.config is not None and getattr(self, "_thumb_cfg_src", None) is not self.ctx.config:
            self._thumb_cfg_src = self.ctx.config
            m.cfg = self.ctx.config.copy()
            m.cfg.drift_s, m.cfg.fade_ds = 6, 15
        elif getattr(self, "_thumb_cfg_src", None) is None:
            m.cfg.drift_s, m.cfg.fade_ds = 6, 15
        m.customs = self.ctx.customs
        for c in self.cards:
            if c.show < 6:
                e1, e2 = builtin.mode_frame(c.show, t, params)
            elif c.show == 7:
                e1, e2 = builtin.mode_frame(0, t, params)
            elif c.show == 6:
                e1, e2, _ = m.anim_frame(6, 6, 4096, t)
            else:
                k = c.show - SHOW_CUSTOM0
                if k >= len(self.ctx.customs):
                    continue
                e1, e2 = self.ctx.customs[k].frame(t)
            c.view.set_levels(*Mirror.display(e1, e2, level=1.0))
