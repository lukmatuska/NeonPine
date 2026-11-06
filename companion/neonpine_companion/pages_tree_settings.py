"""Tree settings: everything in the tree's settings page (stored on the tree itself)."""
import json

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDoubleSpinBox, QFileDialog, QGridLayout, QHBoxLayout, QLineEdit,
                               QMessageBox, QPushButton, QRadioButton, QScrollArea, QSlider, QSpinBox, QVBoxLayout, QWidget)

from . import custom
from .device import BUILTIN_NAMES, N_CUSTOM_MAX, SHOW_CUSTOM0, Config
from .widgets import card, hstretch, label


class TreeSettingsPage(QWidget):
    def __init__(self, ctx):
        super().__init__()
        self.ctx = ctx
        self.cfg = Config()
        self.base = None          # the settings the form was loaded from
        self._loading = False

        outer = QVBoxLayout(self)
        outer.setContentsMargins(24, 20, 24, 16)
        head = QHBoxLayout()
        head.addWidget(label("Tree settings", h1=True))
        head.addStretch(1)
        self.dirty_label = label("", muted=True)
        head.addWidget(self.dirty_label)
        self.revert_btn = QPushButton("Revert")
        self.revert_btn.clicked.connect(lambda: self._load(ctx.config))
        self.save_btn = QPushButton("Save to tree")
        self.save_btn.setProperty("primary", True)
        self.save_btn.clicked.connect(self._save)
        head.addWidget(self.revert_btn)
        head.addWidget(self.save_btn)
        outer.addLayout(head)
        self.note = label("", muted=True, wrap=True)
        outer.addWidget(self.note)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        body = QWidget()
        grid = QGridLayout(body)
        grid.setContentsMargins(0, 8, 8, 8)
        grid.setSpacing(14)
        scroll.setWidget(body)
        outer.addWidget(scroll, 1)

        # identity
        c, l = card()
        l.addWidget(label("Name", h2=True))
        l.addWidget(label("Shown in this app and the tray – handy with more than one tree.", muted=True, wrap=True))
        self.name = QLineEdit()
        self.name.setMaxLength(16)
        self.name.setPlaceholderText("NeonPine")
        self.name.textEdited.connect(self._edited)
        l.addWidget(self.name)
        l.addStretch(1)
        grid.addWidget(c, 0, 0)

        # power-up
        c, l = card()
        l.addWidget(label("When plugged in", h2=True))
        self.remember = QRadioButton("Start with the last animation, style and brightness")
        self.fixed = QRadioButton("Always start with:")
        self.remember.toggled.connect(self._edited)
        l.addWidget(self.remember)
        l.addWidget(self.fixed)
        self.pu_show = QComboBox()
        self.pu_style = QComboBox()
        self.pu_style.addItems(["Normal", "Retro flicker"])
        self.pu_level = QSlider(Qt.Horizontal)
        self.pu_level.setRange(8, 255)
        self.pu_level_val = label("")
        self.pu_level.valueChanged.connect(lambda v: (self.pu_level_val.setText("%d %%" % round(v * 100 / 255)), self._edited()))
        self.pu_show.activated.connect(self._edited)
        self.pu_style.activated.connect(self._edited)
        l.addWidget(hstretch(self.pu_show, self.pu_style))
        l.addWidget(hstretch(label("Brightness", muted=True), self.pu_level, self.pu_level_val))
        grid.addWidget(c, 0, 1)

        # tap list
        c, l = card()
        l.addWidget(label("Tap and wave go through", h2=True))
        l.addWidget(label("Which animations the touch pad (and a wave over the light sensor) steps through.", muted=True, wrap=True))
        self.tap_boxes = []
        tg = QGridLayout()
        for k in range(16):
            cb = QCheckBox()
            cb.toggled.connect(self._edited)
            self.tap_boxes.append(cb)
            tg.addWidget(cb, k % 8, k // 8)
        l.addLayout(tg)
        grid.addWidget(c, 1, 0)

        # drift
        c, l = card()
        l.addWidget(label("Drift", h2=True))
        l.addWidget(label("The Drift animation plays these in turn.", muted=True, wrap=True))
        self.drift_boxes = []
        dg = QGridLayout()
        for k in list(range(6)) + list(range(8, 16)):
            cb = QCheckBox()
            cb.toggled.connect(self._edited)
            self.drift_boxes.append((k, cb))
            dg.addWidget(cb, k % 8, 0 if k < 8 else 1)
        l.addLayout(dg)
        self.drift_s = QSpinBox()
        self.drift_s.setRange(5, 65535)
        self.drift_s.setSuffix(" s each")
        self.drift_s.valueChanged.connect(self._edited)
        l.addWidget(hstretch(label("Time per animation", muted=True), self.drift_s, None))
        grid.addWidget(c, 1, 1)

        # timing
        c, l = card()
        l.addWidget(label("Timing", h2=True))
        self.fade = QDoubleSpinBox()
        self.fade.setRange(0, 25.5)
        self.fade.setSingleStep(0.1)
        self.fade.setDecimals(1)
        self.fade.setSuffix(" s")
        self.fade.valueChanged.connect(self._edited)
        l.addWidget(hstretch(label("Crossfade between animations", muted=True), None, self.fade))
        self.sleep = QSpinBox()
        self.sleep.setRange(1, 255)
        self.sleep.setSuffix(" min")
        self.sleep.valueChanged.connect(self._edited)
        l.addWidget(hstretch(label("Sleep timer (dims, then off)", muted=True), None, self.sleep))
        l.addStretch(1)
        grid.addWidget(c, 2, 0)

        # light sensor / dimming
        c, l = card()
        l.addWidget(label("Light sensor and dimming", h2=True))
        self.autolight = QCheckBox("Off in daylight, on at dusk, adapt to the room, wave to switch")
        self.autolight.toggled.connect(self._edited)
        l.addWidget(self.autolight)
        self.dim_duty = QRadioButton("Dim with the pulse width (recommended)")
        self.dim_rail = QRadioButton("Dim with the high voltage (75–105 V, like the simulator)")
        self.dim_duty.toggled.connect(self._edited)
        l.addWidget(self.dim_duty)
        l.addWidget(self.dim_rail)
        l.addStretch(1)
        grid.addWidget(c, 2, 1)

        # backup
        c, l = card()
        l.addWidget(label("Backup", h2=True))
        l.addWidget(label("Settings and custom animations in one file.", muted=True, wrap=True))
        exp = QPushButton("Save a backup…")
        exp.clicked.connect(self._backup)
        imp = QPushButton("Restore a backup…")
        imp.clicked.connect(self._restore)
        dflt = QPushButton("Factory settings")
        dflt.setProperty("danger", True)
        dflt.setToolTip("Settings back to defaults (custom animations stay)")
        dflt.clicked.connect(self._defaults)
        l.addWidget(hstretch(exp, imp, dflt, None))
        grid.addWidget(c, 3, 0, 1, 2)
        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 1)
        grid.setRowStretch(4, 1)

        ctx.configChanged.connect(self._config_from_tree)
        ctx.customsChanged.connect(lambda _: self._labels())
        ctx.connectionChanged.connect(lambda ok: self._enable())
        self._labels()
        self._load(None)
        self._enable()

    def _labels(self):
        names = self.ctx.custom_names()
        for k, cb in enumerate(self.tap_boxes):
            if k < 8:
                cb.setText(BUILTIN_NAMES[k])
                cb.setEnabled(True)
            else:
                j = k - 8
                cb.setText(names[j] if j < len(names) else "Custom %d (empty)" % (j + 1))
                cb.setEnabled(j < len(names))
        for k, cb in self.drift_boxes:
            if k < 8:
                cb.setText(BUILTIN_NAMES[k])
            else:
                j = k - 8
                cb.setText(names[j] if j < len(names) else "Custom %d (empty)" % (j + 1))
                cb.setEnabled(j < len(names))
        cur = self.pu_show.currentData()
        self.pu_show.clear()
        for n in list(range(7)) + [SHOW_CUSTOM0 + j for j in range(len(names))]:
            self.pu_show.addItem(self.ctx.show_name(n), n)
        i = self.pu_show.findData(cur if cur is not None else self.cfg.show)
        self.pu_show.setCurrentIndex(max(0, i))

    def _enable(self):
        ok = self.ctx.connected and self.ctx.config is not None
        self.save_btn.setEnabled(ok and self._dirty())
        self.revert_btn.setEnabled(ok and self._dirty())
        if not self.ctx.connected:
            self.note.setText("No tree connected.")
        elif self.ctx.config is None:
            self.note.setText("This tree's firmware has no settings store – update it on the Firmware page.")
        else:
            self.note.setText("Stored on the tree. Brightness, style and the animation itself are on the Tree page.")

    def _config_from_tree(self, cfg):
        if cfg is not None and (self.base is None or not self._dirty()):
            self._load(cfg)
        self._enable()

    def _load(self, cfg):
        self._loading = True
        self.cfg = cfg.copy() if cfg else Config()
        self.base = cfg.copy() if cfg else None
        c = self.cfg
        self.name.setText(c.name)
        self.remember.setChecked(c.remember)
        self.fixed.setChecked(not c.remember)
        self._labels()
        self.pu_show.setCurrentIndex(max(0, self.pu_show.findData(c.show)))
        self.pu_style.setCurrentIndex(1 if c.style else 0)
        self.pu_level.setValue(c.level)
        self.pu_level_val.setText("%d %%" % round(c.level * 100 / 255))
        for k, cb in enumerate(self.tap_boxes):
            cb.setChecked(bool(c.tap_mask >> k & 1))
        for k, cb in self.drift_boxes:
            cb.setChecked(bool(c.drift_mask >> k & 1))
        self.drift_s.setValue(c.drift_s)
        self.fade.setValue(c.fade_ds / 10)
        self.sleep.setValue(c.sleep_min)
        self.autolight.setChecked(c.autolight)
        self.dim_rail.setChecked(c.dim_rail)
        self.dim_duty.setChecked(not c.dim_rail)
        self._loading = False
        self._edited()

    def _collect(self):
        c = (self.ctx.config or self.cfg).copy()
        c.name = self.name.text().strip()
        c.remember = self.remember.isChecked()
        if self.pu_show.currentData() is not None:
            c.show = self.pu_show.currentData()
        c.style = self.pu_style.currentIndex()
        c.level = self.pu_level.value()
        c.tap_mask = sum(1 << k for k, cb in enumerate(self.tap_boxes) if cb.isChecked())
        c.drift_mask = sum(1 << k for k, cb in self.drift_boxes if cb.isChecked())
        c.drift_s = self.drift_s.value()
        c.fade_ds = round(self.fade.value() * 10)
        c.sleep_min = self.sleep.value()
        c.autolight = self.autolight.isChecked()
        c.dim_rail = self.dim_rail.isChecked()
        return c

    def _dirty(self):
        return self.base is not None and self._collect().pack() != self.base.pack()

    def _edited(self, *args):
        if self._loading:
            return
        fixed = self.fixed.isChecked()
        for w in (self.pu_show, self.pu_style, self.pu_level):
            w.setEnabled(fixed)
        d = self._dirty()
        self.dirty_label.setText("Unsaved changes" if d else "")
        self.save_btn.setEnabled(d and self.ctx.connected)
        self.revert_btn.setEnabled(d)

    def _save(self):
        cfg = self._collect()
        if not cfg.tap_mask:
            QMessageBox.warning(self, "Tap list", "Pick at least one animation for the touch pad.")
            return
        self.ctx.write_config(cfg, True, lambda r: (self._load(r), self.ctx.message.emit("Settings saved on the tree.", "ok")))

    def _defaults(self):
        if QMessageBox.question(self, "Factory settings", "Put the tree's settings back to defaults? (Custom animations stay.)") != QMessageBox.Yes:
            return
        d = Config()
        d.name = self.ctx.config.name if self.ctx.config else ""
        self.ctx.write_config(d, True, lambda r: (self._load(r), self.ctx.message.emit("Defaults restored.", "ok")))

    def _backup(self):
        if not self.ctx.config:
            return
        path, _ = QFileDialog.getSaveFileName(self, "Save backup", "%s-backup.json" % (self.ctx.tree_name.replace(" ", "-") or "neonpine"),
                                              "NeonPine backup (*.json)")
        if not path:
            return
        data = {"format": "neonpine-backup", "version": 1, "settings": self.ctx.config.pack().hex(),
                "animations": [a.to_dict() for a in self.ctx.customs]}
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=1)
            self.ctx.message.emit("Backup saved.", "ok")
        except OSError as e:
            self.ctx.message.emit(str(e), "error")

    def _restore(self):
        path, _ = QFileDialog.getOpenFileName(self, "Restore backup", "", "NeonPine backup (*.json)")
        if not path:
            return
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            cfg = Config.unpack(bytes.fromhex(data["settings"]))
            anims = [custom.CustomAnimation.from_dict(a) for a in data.get("animations", [])][:N_CUSTOM_MAX]
            if cfg is None:
                raise ValueError("bad settings block")
        except (OSError, ValueError, KeyError) as e:
            self.ctx.message.emit("Can't read the backup: %s" % e, "error")
            return
        if QMessageBox.question(self, "Restore", "Replace the tree's settings and its %d custom animations with the backup "
                                "(%d animations)?" % (len(self.ctx.customs), len(anims))) != QMessageBox.Yes:
            return
        self.ctx.upload_customs(anims, ok=lambda: self.ctx.write_config(
            cfg, True, lambda r: (self._load(r), self.ctx.message.emit("Backup restored.", "ok"))))
