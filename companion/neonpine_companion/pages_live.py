"""Live: drive the tree from the PC - music, CPU load, painting by hand."""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QButtonGroup, QComboBox, QHBoxLayout, QProgressBar, QPushButton, QSlider, QStackedWidget,
                               QVBoxLayout, QWidget)

from .mirror import Mirror
from .visualizers import HAVE_AUDIO, CpuSource, LiveDriver, MusicSource
from .widgets import TreeView, card, hstretch, label

OWNER = "Live page"


class PaintSource:
    def __init__(self):
        self.left = [0.0] * 10
        self.right = [0.0] * 10

    def frame(self):
        return self.left, self.right


class LivePage(QWidget):
    def __init__(self, ctx):
        super().__init__()
        self.ctx = ctx
        self.music = MusicSource(self) if HAVE_AUDIO else None
        self.cpu = CpuSource()
        self.paint = PaintSource()
        self.driver = LiveDriver(self)
        self.driver.frame.connect(self._frame)

        root = QHBoxLayout(self)
        root.setContentsMargins(24, 20, 24, 20)
        root.setSpacing(20)

        left = QVBoxLayout()
        left.addWidget(label("Live", h1=True))
        left.addWidget(label("Drive the tree from this computer. When the stream stops, the tree goes back to its animation.",
                             muted=True, wrap=True))
        self.view = TreeView(editable=True)
        self.view.electrodePressed.connect(self._paint)
        self.view.electrodeDragged.connect(self._paint)
        left.addWidget(self.view, 1)
        root.addLayout(left, 5)

        right = QVBoxLayout()
        right.setSpacing(12)
        c, cl = card()
        cl.addWidget(label("Source", h2=True))
        self.group = QButtonGroup(self)
        row = QHBoxLayout()
        for i, name in enumerate(("Off", "Music", "CPU load", "Paint")):
            b = QPushButton(name)
            b.setCheckable(True)
            self.group.addButton(b, i)
            row.addWidget(b)
        self.group.button(0).setChecked(True)
        self.group.idClicked.connect(self._source)
        cl.addLayout(row)
        self.opts = QStackedWidget()
        cl.addWidget(self.opts)
        right.addWidget(c)

        # options per source
        off = QWidget()
        ol = QVBoxLayout(off)
        ol.setContentsMargins(0, 6, 0, 0)
        ol.addWidget(label("Pick a source above. Only one thing can drive the tree at a time – the animation editor's live "
                           "preview counts too.", muted=True, wrap=True))
        ol.addStretch(1)
        self.opts.addWidget(off)

        mus = QWidget()
        ml = QVBoxLayout(mus)
        ml.setContentsMargins(0, 6, 0, 0)
        if self.music:
            ml.addWidget(label("Input", muted=True))
            self.inputs = QComboBox()
            for name, dev in MusicSource.inputs():
                self.inputs.addItem(name, dev)
            self.inputs.currentIndexChanged.connect(lambda _: self._source(self.group.checkedId()))
            ml.addWidget(self.inputs)
            ml.addWidget(label("Style", muted=True))
            self.style = QComboBox()
            self.style.addItem("Spectrum – bass at the bottom, treble at the star", "bands")
            self.style.addItem("Level meter – fills up from the bottom", "meter")
            self.style.addItem("Beat – the whole tree pulses", "pulse")
            self.style.currentIndexChanged.connect(lambda _: setattr(self.music, "style", self.style.currentData()))
            ml.addWidget(self.style)
            ml.addWidget(label("Sensitivity", muted=True))
            self.gain = QSlider(Qt.Horizontal)
            self.gain.setRange(-20, 30)
            self.gain.setValue(0)
            self.gain.valueChanged.connect(lambda v: setattr(self.music, "gain", 10 ** (v / 20)))
            ml.addWidget(self.gain)
            self.meter = QProgressBar()
            self.meter.setRange(0, 100)
            self.meter.setTextVisible(False)
            self.meter.setFixedHeight(8)
            self.music.level.connect(lambda v: self.meter.setValue(int(min(1.0, v) * 100)))
            ml.addWidget(self.meter)
            ml.addWidget(label("Tip: to react to what the PC plays, pick a monitor / loopback input "
                               "(Linux: “Monitor of …”, Windows: enable “Stereo Mix”).", muted=True, wrap=True))
        else:
            ml.addWidget(label("Music needs Qt Multimedia, which this installation doesn't have.", muted=True, wrap=True))
        ml.addStretch(1)
        self.opts.addWidget(mus)

        cpuw = QWidget()
        cpl = QVBoxLayout(cpuw)
        cpl.setContentsMargins(0, 6, 0, 0)
        cpl.addWidget(label("The tree fills up from the bottom with the CPU load – the right electrodes trail behind.",
                            muted=True, wrap=True))
        self.cpu_label = label("")
        cpl.addWidget(self.cpu_label)
        cpl.addStretch(1)
        self.opts.addWidget(cpuw)

        pw = QWidget()
        pl = QVBoxLayout(pw)
        pl.setContentsMargins(0, 6, 0, 0)
        pl.addWidget(label("Click or drag over the electrodes – the tree follows. Right click erases.", muted=True, wrap=True))
        pl.addWidget(label("Brush", muted=True))
        self.brush = QSlider(Qt.Horizontal)
        self.brush.setRange(0, 100)
        self.brush.setValue(100)
        pl.addWidget(self.brush)
        allb = QPushButton("All on")
        allb.clicked.connect(lambda: self._fill(self.brush.value() / 100))
        clr = QPushButton("Clear")
        clr.clicked.connect(lambda: self._fill(0.0))
        pl.addWidget(hstretch(allb, clr, None))
        pl.addStretch(1)
        self.opts.addWidget(pw)

        self.state = label("", muted=True, wrap=True)
        right.addWidget(self.state)
        right.addStretch(1)
        root.addLayout(right, 4)

        ctx.liveChanged.connect(self._live_changed)
        ctx.connectionChanged.connect(lambda ok: self._update_state())
        self._update_state()

    def _source(self, i):
        if self.music:
            self.music.stop()
        self.opts.setCurrentIndex(i)
        src = None
        if i == 1 and self.music:
            try:
                self.music.start(self.inputs.currentData() if self.inputs.count() else None)
                src = self.music
            except RuntimeError as e:
                self.ctx.message.emit(str(e), "error")
        elif i == 2:
            src = self.cpu
        elif i == 3:
            src = self.paint
        self.driver.run(src)
        if src:
            self.ctx.start_live(OWNER)
        else:
            self.ctx.stop_live(OWNER)
            self.view.set_levels([0] * 10, [0] * 10)
        self._update_state()

    def _live_changed(self, owner):
        if owner not in (None, OWNER) and self.group.checkedId() != 0:
            self.group.button(0).setChecked(True)
            self._source(0)
        self._update_state()

    def _update_state(self):
        if self.group.checkedId() == 0:
            self.state.setText("")
        elif not self.ctx.connected:
            self.state.setText("No tree connected – showing the preview only.")
        else:
            self.state.setText("Streaming to the tree at %d frames per second." % self.ctx.client.worker.live_fps)

    def _frame(self, left, right):
        self.ctx.push_live(OWNER, left, right)
        self.view.set_levels(*Mirror.display([v * 4095 for v in left], [v * 4095 for v in right], level=1.0))
        if self.group.checkedId() == 2:
            self.cpu_label.setText("CPU %d %%" % round(self.cpu.load * 100))

    def _paint(self, lamp, side, button):
        if self.group.checkedId() != 3:
            self.group.button(3).setChecked(True)
            self._source(3)
        v = self.brush.value() / 100 if button == Qt.LeftButton.value else 0.0
        (self.paint.left if side == 0 else self.paint.right)[lamp] = v

    def _fill(self, v):
        self.paint.left = [v] * 10
        self.paint.right = [v] * 10
