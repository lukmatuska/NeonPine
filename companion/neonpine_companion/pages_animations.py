"""Animations: the keyframe editor for custom animations, and tuning of the built-in ones."""
import math
import os
import time

from PySide6.QtCore import QSize, Qt, QTimer
from PySide6.QtGui import QIcon, QKeySequence, QPixmap, QShortcut
from PySide6.QtWidgets import (QAbstractItemView, QButtonGroup, QCheckBox, QComboBox, QFileDialog, QGridLayout, QHBoxLayout,
                               QLineEdit, QListWidget, QListWidgetItem, QMenu, QMessageBox, QProgressBar, QPushButton,
                               QSlider, QSpinBox, QTabWidget, QVBoxLayout, QWidget)

from . import builtin, custom, platform_utils
from .custom import LEVELS, MAX_ANIMS, CustomAnimation, Key
from .device import BUILTIN_HINTS, BUILTIN_NAMES, N_BASIC, ModeParams
from .mirror import Mirror
from .widgets import TreeView, card, hstretch, label

Q = 4096


def key_frame(k):
    return [v * 273 for v in k.left], [v * 273 for v in k.right]


class Thumbs:
    """Renders small tree pictures for the timeline."""

    def __init__(self):
        self.view = TreeView(compact=True)
        self.view.resize(64, 76)
        self.view.setAttribute(Qt.WA_DontShowOnScreen)

    def icon(self, e1, e2):
        self.view.set_levels(*Mirror.display(e1, e2, level=1.0))
        pm = QPixmap(self.view.size())
        pm.fill(Qt.transparent)
        self.view.render(pm)
        icon = QIcon(pm)
        icon.addPixmap(pm, QIcon.Selected)  # no selection tint
        return icon


class AnimationsPage(QWidget):
    def __init__(self, ctx):
        super().__init__()
        lay = QVBoxLayout(self)
        lay.setContentsMargins(24, 20, 24, 16)
        lay.addWidget(label("Animations", h1=True))
        self.tabs = QTabWidget()
        self.editor = CustomEditor(ctx)
        self.tuning = TuningPanel(ctx)
        self.tabs.addTab(self.editor, "My animations")
        self.tabs.addTab(self.tuning, "Built-in tuning")
        self.tabs.currentChanged.connect(lambda i: self.editor.set_preview(False) if i else None)
        lay.addWidget(self.tabs, 1)

    def activated(self):
        pass


# ---- custom keyframe editor ----------------------------------------------------------------------

class CustomEditor(QWidget):
    def __init__(self, ctx):
        super().__init__()
        self.ctx = ctx
        self.anims = []
        self.cur = -1
        self.key = 0
        self.playing = False
        self.t = 0.0
        self._last_tick = time.monotonic()
        self.undo_stack, self.redo_stack = [], []
        self.thumbs = Thumbs()
        self.offered_tree = False
        self.lib_path = os.path.join(platform_utils.data_dir(), "library.json")
        self._save_timer = QTimer(self)
        self._save_timer.setSingleShot(True)
        self._save_timer.timeout.connect(self._save_library)

        root = QHBoxLayout(self)
        root.setContentsMargins(0, 12, 0, 0)
        root.setSpacing(16)

        # left: animation list + sync
        left = QVBoxLayout()
        left.setSpacing(8)
        self.list = QListWidget()
        self.list.setFixedWidth(230)
        self.list.currentRowChanged.connect(self._select_anim)
        left.addWidget(self.list, 1)
        self.new_btn = QPushButton("New")
        self.new_menu = QMenu(self)
        self.new_menu.addAction("Blank", lambda: self._add(CustomAnimation("Animation %d" % (len(self.anims) + 1),
                                                                              [Key([0] * 10, [0] * 10, 600)])))
        pat = self.new_menu.addMenu("From a pattern")
        for name, fn in custom.GENERATORS.items():
            pat.addAction(name, lambda fn=fn: self._add(fn()))
        bi = self.new_menu.addMenu("From a built-in animation")
        for m in range(N_BASIC):
            bi.addAction(BUILTIN_NAMES[m], lambda m=m: self._add_from_builtin(m))
        self.new_btn.setMenu(self.new_menu)
        dup = QPushButton("Duplicate")
        dup.clicked.connect(self._duplicate_anim)
        rm = QPushButton("Delete")
        rm.setProperty("danger", True)
        rm.clicked.connect(self._delete_anim)
        left.addWidget(hstretch(self.new_btn, dup, rm))
        up = QPushButton("Move up")
        up.clicked.connect(lambda: self._move_anim(-1))
        down = QPushButton("Move down")
        down.clicked.connect(lambda: self._move_anim(1))
        left.addWidget(hstretch(up, down, None))
        imp = QPushButton("Import…")
        imp.clicked.connect(self._import)
        exp = QPushButton("Export…")
        exp.clicked.connect(self._export)
        left.addWidget(hstretch(imp, exp, None))

        sc, sl = card(margins=12, spacing=6)
        sl.addWidget(label("On the tree", h2=True))
        self.sync_label = label("", muted=True, wrap=True)
        sl.addWidget(self.sync_label)
        self.storage = QProgressBar()
        self.storage.setTextVisible(True)
        sl.addWidget(self.storage)
        self.upload_btn = QPushButton("Upload to tree")
        self.upload_btn.setProperty("primary", True)
        self.upload_btn.clicked.connect(self._upload)
        self.load_btn = QPushButton("Load from tree")
        self.load_btn.clicked.connect(self._load_from_tree)
        sl.addWidget(self.upload_btn)
        sl.addWidget(self.load_btn)
        sc.setFixedWidth(230)
        left.addWidget(sc)
        root.addLayout(left)

        # center: name, tree canvas, paint tools, timeline
        center = QVBoxLayout()
        center.setSpacing(8)
        self.name = QLineEdit()
        self.name.setMaxLength(custom.NAME_LEN)
        self.name.setPlaceholderText("Name (12 characters)")
        self.name.textEdited.connect(self._rename)
        self.length = label("", muted=True)
        center.addWidget(hstretch(self.name, self.length))
        self.canvas = TreeView(editable=True)
        self.canvas.electrodePressed.connect(self._paint_press)
        self.canvas.electrodeDragged.connect(self._paint_drag)
        center.addWidget(self.canvas, 1)

        center.addWidget(label("Left click paints with the brush, right click erases. Ctrl+Z / Ctrl+Y undo / redo, space plays.",
                               muted=True, wrap=True))

        self.timeline = QListWidget()
        self.timeline.setViewMode(QListWidget.IconMode)
        self.timeline.setFlow(QListWidget.LeftToRight)
        self.timeline.setWrapping(False)
        self.timeline.setIconSize(QSize(64, 76))
        self.timeline.setGridSize(QSize(84, 118))
        self.timeline.setFixedHeight(140)
        self.timeline.setMovement(QListWidget.Snap)
        self.timeline.setDragDropMode(QAbstractItemView.InternalMove)
        self.timeline.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.timeline.currentRowChanged.connect(self._select_key)
        self.timeline.model().rowsMoved.connect(self._keys_reordered)
        center.addWidget(self.timeline)
        kb = QHBoxLayout()
        for txt, fn in (("+ Add key", self._add_key), ("Duplicate key", self._dup_key), ("Delete key", self._del_key),
                        ("◀ Move", lambda: self._move_key(-1)), ("Move ▶", lambda: self._move_key(1))):
            b = QPushButton(txt)
            b.clicked.connect(fn)
            kb.addWidget(b)
        kb.addStretch(1)
        center.addLayout(kb)
        root.addLayout(center, 1)

        # right: key properties + preview
        right = QVBoxLayout()
        right.setSpacing(12)
        kc, kl = card()
        self.key_title = label("Key", h2=True)
        kl.addWidget(self.key_title)
        kl.addWidget(label("Duration until the next key", muted=True))
        self.dur = QSpinBox()
        self.dur.setRange(20, custom.MAX_KEY_MS)
        self.dur.setSingleStep(50)
        self.dur.setSuffix(" ms")
        self.dur.editingFinished.connect(self._set_duration)
        all_btn = QPushButton("Use for all keys")
        all_btn.clicked.connect(self._duration_all)
        kl.addWidget(self.dur)
        kl.addWidget(all_btn)
        kl.addWidget(label("Transition to the next key", muted=True))
        self.trans = QComboBox()
        self.trans.addItems(["Hold (jump)", "Linear fade", "Smooth fade"])
        self.trans.activated.connect(self._set_transition)
        kl.addWidget(self.trans)
        kc.setFixedWidth(240)
        right.addWidget(kc)

        tc, tl = card()
        tl.addWidget(label("Paint", h2=True))
        self.brush = QSlider(Qt.Horizontal)
        self.brush.setRange(0, LEVELS)
        self.brush.setValue(LEVELS)
        self.brush_val = label("15")
        self.brush_val.setMinimumWidth(22)
        self.brush.valueChanged.connect(lambda v: self.brush_val.setText(str(v)))
        tl.addWidget(hstretch(label("Brush", muted=True), self.brush, self.brush_val))
        self.mode_group = QButtonGroup(self)
        modes = []
        for i, (txt, tip) in enumerate((("Electrode", "Paint single electrodes"), ("Whole lamp", "Paint both electrodes of a lamp"))):
            b = QPushButton(txt)
            b.setCheckable(True)
            b.setToolTip(tip)
            b.setChecked(i == 0)
            self.mode_group.addButton(b, i)
            modes.append(b)
        tl.addWidget(hstretch(*modes))
        tg = QGridLayout()
        tg.setSpacing(6)
        for i, (txt, fn, tip) in enumerate((("All", self._tool_all, "Every electrode to the brush level"),
                                            ("Clear", self._tool_clear, "Every electrode off"),
                                            ("Invert", self._tool_invert, "15 - level"),
                                            ("Swap L / R", self._tool_swap, "Swap left and right electrodes"),
                                            ("Copy previous", self._tool_prev, "Copy the previous key"))):
            b = QPushButton(txt)
            b.setToolTip(tip)
            b.clicked.connect(fn)
            tg.addWidget(b, i // 2, i % 2)
        tl.addLayout(tg)
        tc.setFixedWidth(240)
        right.addWidget(tc)

        pc, pl = card()
        pl.addWidget(label("Preview", h2=True))
        self.play_btn = QPushButton("▶  Play")
        self.play_btn.setCheckable(True)
        self.play_btn.toggled.connect(self._play)
        pl.addWidget(self.play_btn)
        self.pos = label("", muted=True)
        pl.addWidget(self.pos)
        self.on_tree = QCheckBox("Show on the tree (live)")
        self.on_tree.setToolTip("Streams what you see here to the tree – including the key you are painting")
        self.on_tree.toggled.connect(self.set_preview)
        pl.addWidget(self.on_tree)
        pl.addWidget(label("Up to 8 animations, %d levels per electrode. Keys loop: the last one fades into the first." % (LEVELS + 1),
                           muted=True, wrap=True))
        pc.setFixedWidth(240)
        right.addWidget(pc)
        right.addStretch(1)
        root.addLayout(right)

        QShortcut(QKeySequence.Undo, self, self._undo)
        QShortcut(QKeySequence.Redo, self, self._redo)
        QShortcut(QKeySequence("Ctrl+Y"), self, self._redo)
        QShortcut(QKeySequence("Space"), self, lambda: self.play_btn.toggle())

        self.timer = QTimer(self)
        self.timer.timeout.connect(self._tick)
        self.timer.start(33)

        ctx.customsChanged.connect(self._tree_customs)
        ctx.connectionChanged.connect(lambda ok: self._sync_state())
        ctx.liveChanged.connect(self._live_changed)
        self._load_library()

    # -- library (kept on disk, so nothing is lost while the tree is unplugged)

    def _load_library(self):
        try:
            self.anims = custom.load_json(self.lib_path)
        except (OSError, ValueError, KeyError):
            self.anims = []
        self._refresh_list(0 if self.anims else -1)

    def _save_library(self):
        try:
            custom.save_json(self.lib_path, self.anims)
        except OSError as e:
            self.ctx.message.emit("Couldn't save the animation library: %s" % e, "error")

    def _changed(self, list_too=False):
        self._save_timer.start(800)
        if list_too:
            self._refresh_list(self.cur)
        else:
            it = self.list.item(self.cur)
            if it and self.anim:
                it.setText(self._list_text(self.anim))
        self._sync_state()
        self._show_key()

    @property
    def anim(self):
        return self.anims[self.cur] if 0 <= self.cur < len(self.anims) else None

    @staticmethod
    def _list_text(a):
        return "%s\n%d keys · %.1f s" % (a.name or "(unnamed)", len(a.keys), a.total_ms / 1000)

    def _refresh_list(self, select):
        self.list.blockSignals(True)
        self.list.clear()
        for a in self.anims:
            self.list.addItem(QListWidgetItem(self._list_text(a)))
        self.list.blockSignals(False)
        select = min(select, len(self.anims) - 1)
        self.cur = -1
        if select >= 0:
            self.list.setCurrentRow(select)
        else:
            self._select_anim(-1)
        self._sync_state()

    # -- animations

    def _select_anim(self, row):
        self.cur = row
        self.undo_stack.clear()
        self.redo_stack.clear()
        a = self.anim
        enabled = a is not None
        for w in (self.name, self.canvas, self.timeline, self.dur, self.trans, self.play_btn):
            w.setEnabled(enabled)
        self.name.setText(a.name if a else "")
        self.key = 0
        self.t = 0.0
        self._rebuild_timeline()
        self._show_key()

    def _add(self, a):
        if len(self.anims) >= MAX_ANIMS:
            self.ctx.message.emit("The tree holds up to %d custom animations." % MAX_ANIMS, "error")
            return
        a.name = a.name[:custom.NAME_LEN]
        self.anims.append(a)
        self._refresh_list(len(self.anims) - 1)
        self._changed(True)

    def _add_from_builtin(self, m):
        params = self.ctx.config.params if self.ctx.config else [ModeParams() for _ in range(N_BASIC)]
        period = {0: 4000, 1: 13000, 2: 5400, 3: 5200, 4: 4800, 5: 1000}[m] * 64 // max(1, params[m].speed)
        step = max(60, min(400, period // 40))
        self._add(custom.from_builtin(m, params, seconds=min(30.0, period / 1000), step_ms=step,
                                      name=("My " + BUILTIN_NAMES[m].lower())[:custom.NAME_LEN]))

    def _duplicate_anim(self):
        if self.anim:
            a = self.anim.copy()
            a.name = (a.name[:9] + " 2")[:custom.NAME_LEN]
            self._add(a)

    def _delete_anim(self):
        if not self.anim:
            return
        if QMessageBox.question(self, "Delete", "Delete “%s”?" % self.anim.name) != QMessageBox.Yes:
            return
        del self.anims[self.cur]
        self._refresh_list(max(0, self.cur - 1))
        self._changed(True)

    def _move_anim(self, d):
        j = self.cur + d
        if self.anim and 0 <= j < len(self.anims):
            self.anims[self.cur], self.anims[j] = self.anims[j], self.anims[self.cur]
            self._refresh_list(j)
            self._changed(True)

    def _rename(self, text):
        if self.anim:
            self.anim.name = text
            self._changed()

    def _import(self):
        path, _ = QFileDialog.getOpenFileName(self, "Import animations", "", "NeonPine animations (*.json);;All files (*)")
        if not path:
            return
        try:
            new = custom.load_json(path)
        except (OSError, ValueError, KeyError) as e:
            self.ctx.message.emit("Can't import: %s" % e, "error")
            return
        room = MAX_ANIMS - len(self.anims)
        for a in new[:room]:
            a.name = a.name[:custom.NAME_LEN]
            self.anims.append(a)
        self._refresh_list(len(self.anims) - 1)
        self._changed(True)
        if len(new) > room:
            self.ctx.message.emit("Imported %d of %d (the tree holds %d)." % (room, len(new), MAX_ANIMS), "info")

    def _export(self):
        if not self.anims:
            return
        path, _ = QFileDialog.getSaveFileName(self, "Export animations", "neonpine-animations.json", "NeonPine animations (*.json)")
        if path:
            try:
                custom.save_json(path, self.anims)
                self.ctx.message.emit("Exported %d animations." % len(self.anims), "ok")
            except OSError as e:
                self.ctx.message.emit(str(e), "error")

    # -- sync with the tree

    def _capacity(self):
        st = self.ctx.status
        return ((st.store_pages if st and st.store_pages else 16) - 1) * 64

    def _sync_state(self):
        used = custom.blob_size(self.anims)
        cap = self._capacity()
        self.storage.setRange(0, cap)
        self.storage.setValue(min(used, cap))
        self.storage.setFormat("%d of %d bytes" % (used, cap))
        over = used > cap
        self.storage.setStyleSheet("QProgressBar::chunk { background: %s; }" % ("#ff5c5c" if over else "#ff7a2f"))
        ctx = self.ctx
        can = ctx.connected and ctx.status is not None and ctx.status.has_store
        same = can and custom.pack_blob(self.anims) == custom.pack_blob(ctx.customs)
        self.upload_btn.setEnabled(can and not same and not over)
        self.load_btn.setEnabled(can and bool(ctx.customs) and not same)
        if not ctx.connected:
            self.sync_label.setText("No tree connected. Your animations are kept on this computer.")
        elif not can:
            self.sync_label.setText("This tree's firmware can't store animations – update it on the Firmware page.")
        elif over:
            self.sync_label.setText("Too big for the tree: remove keys or animations.")
        elif same:
            self.sync_label.setText("In sync – the tree has these %d animations." % len(self.anims))
        else:
            self.sync_label.setText("Changes not on the tree yet (the tree has %d animations)." % len(ctx.customs))

    def _tree_customs(self, customs):
        if not self.anims and customs:
            self.anims = [a.copy() for a in customs]
            self._refresh_list(0)
            self._save_library()
        elif customs and not self.offered_tree and custom.pack_blob(self.anims) != custom.pack_blob(customs):
            self.offered_tree = True
            self.ctx.message.emit("The tree has different animations than the editor – “Load from tree” brings them in.", "info")
        self._sync_state()

    def _upload(self):
        if self.playing:
            self.play_btn.setChecked(False)
        self.upload_btn.setEnabled(False)
        self.sync_label.setText("Uploading…")
        self.ctx.upload_customs(self.anims, ok=lambda: (self.ctx.message.emit("Animations uploaded to the tree.", "ok"), self._sync_state()),
                                err=lambda e: self._sync_state())

    def _load_from_tree(self):
        if QMessageBox.question(self, "Load from tree", "Replace the editor's animations with the %d on the tree?"
                                % len(self.ctx.customs)) != QMessageBox.Yes:
            return
        self.anims = [a.copy() for a in self.ctx.customs]
        self._refresh_list(0)
        self._save_library()

    # -- keys / timeline

    def _rebuild_timeline(self):
        self.timeline.blockSignals(True)
        self.timeline.clear()
        a = self.anim
        if a:
            for i, k in enumerate(a.keys):
                it = QListWidgetItem(self.thumbs.icon(*key_frame(k)), "%d · %d ms" % (i + 1, k.duration))
                it.setTextAlignment(Qt.AlignHCenter | Qt.AlignTop)
                self.timeline.addItem(it)
            self.timeline.setCurrentRow(min(self.key, len(a.keys) - 1))
        self.timeline.blockSignals(False)

    def _update_thumb(self, i):
        a = self.anim
        it = self.timeline.item(i)
        if a and it and i < len(a.keys):
            k = a.keys[i]
            it.setIcon(self.thumbs.icon(*key_frame(k)))
            it.setText("%d · %d ms" % (i + 1, k.duration))

    def _select_key(self, row):
        if row >= 0:
            self.key = row
            if self.playing:
                self.play_btn.setChecked(False)
            self._show_key()

    def _keys_reordered(self, *args):
        a = self.anim
        if not a:
            return
        # the list widget moved its items: rebuild the key order from the item labels
        order = [int(self.timeline.item(i).text().split(" ")[0]) - 1 for i in range(self.timeline.count())]
        self._push_undo()
        a.keys = [a.keys[i] for i in order]
        self.key = self.timeline.currentRow()
        self._rebuild_timeline()
        self._changed()

    def _add_key(self):
        a = self.anim
        if not a or len(a.keys) >= 255:
            return
        self._push_undo()
        k = a.keys[self.key].copy()
        a.keys.insert(self.key + 1, k)
        self.key += 1
        self._rebuild_timeline()
        self._changed()

    def _dup_key(self):
        self._add_key()

    def _del_key(self):
        a = self.anim
        if not a or len(a.keys) <= 1:
            return
        self._push_undo()
        del a.keys[self.key]
        self.key = min(self.key, len(a.keys) - 1)
        self._rebuild_timeline()
        self._changed()

    def _move_key(self, d):
        a = self.anim
        j = self.key + d
        if a and 0 <= j < len(a.keys):
            self._push_undo()
            a.keys[self.key], a.keys[j] = a.keys[j], a.keys[self.key]
            self.key = j
            self._rebuild_timeline()
            self._changed()

    def _set_duration(self):
        a = self.anim
        if a and a.keys[self.key].duration != self.dur.value():
            self._push_undo()
            a.keys[self.key].duration = self.dur.value()
            self._update_thumb(self.key)
            self._changed()

    def _duration_all(self):
        a = self.anim
        if a:
            self._push_undo()
            for k in a.keys:
                k.duration = self.dur.value()
            self._rebuild_timeline()
            self._changed()

    def _set_transition(self, i):
        a = self.anim
        if a:
            self._push_undo()
            a.keys[self.key].transition = i
            self._changed()

    def _show_key(self):
        a = self.anim
        if not a:
            self.canvas.labels = None
            self.canvas.set_levels([0] * 10, [0] * 10)
            self.key_title.setText("Key")
            self.length.setText("")
            self.pos.setText("")
            return
        self.key = max(0, min(self.key, len(a.keys) - 1))
        k = a.keys[self.key]
        self.key_title.setText("Key %d of %d" % (self.key + 1, len(a.keys)))
        self.dur.blockSignals(True)
        self.dur.setValue(k.duration)
        self.dur.blockSignals(False)
        self.trans.setCurrentIndex(k.transition)
        self.length.setText("%.2f s loop" % (a.total_ms / 1000))
        if not self.playing:
            self.canvas.labels = ([str(v) for v in k.left], [str(v) for v in k.right])
            self.canvas.set_levels(*Mirror.display(*key_frame(k), level=1.0))

    # -- painting

    def _paint(self, lamp, side, button):
        a = self.anim
        if not a:
            return
        if self.playing:
            self.play_btn.setChecked(False)
        k = a.keys[self.key]
        v = self.brush.value() if button == Qt.LeftButton.value else 0
        sides = (0, 1) if self.mode_group.checkedId() == 1 else (side,)
        for s in sides:
            (k.left if s == 0 else k.right)[lamp] = v
        self._update_thumb(self.key)
        self._changed()

    def _paint_press(self, lamp, side, button):
        if self.anim:
            self._push_undo()
        self._paint(lamp, side, button)

    def _paint_drag(self, lamp, side, button):
        self._paint(lamp, side, button)

    def _tool(self, fn):
        a = self.anim
        if not a:
            return
        self._push_undo()
        fn(a.keys[self.key])
        self._update_thumb(self.key)
        self._changed()

    def _tool_all(self):
        v = self.brush.value()
        self._tool(lambda k: (k.left.__setitem__(slice(None), [v] * 10), k.right.__setitem__(slice(None), [v] * 10)))

    def _tool_clear(self):
        self._tool(lambda k: (k.left.__setitem__(slice(None), [0] * 10), k.right.__setitem__(slice(None), [0] * 10)))

    def _tool_invert(self):
        self._tool(lambda k: (k.left.__setitem__(slice(None), [LEVELS - v for v in k.left]),
                              k.right.__setitem__(slice(None), [LEVELS - v for v in k.right])))

    def _tool_swap(self):
        def f(k):
            k.left, k.right = k.right, k.left
        self._tool(f)

    def _tool_prev(self):
        a = self.anim
        if a and len(a.keys) > 1:
            src = a.keys[self.key - 1]
            self._tool(lambda k: (k.left.__setitem__(slice(None), src.left), k.right.__setitem__(slice(None), src.right)))

    # -- undo

    def _push_undo(self):
        if self.anim:
            self.undo_stack.append((self.cur, self.anim.copy(), self.key))
            del self.undo_stack[:-60]
            self.redo_stack.clear()

    def _restore(self, src, dst):
        if not src:
            return
        cur, snap, key = src.pop()
        if cur != self.cur or not self.anim:
            return
        dst.append((self.cur, self.anim.copy(), self.key))
        self.anims[self.cur] = snap
        self.key = key
        self.name.setText(snap.name)
        self._rebuild_timeline()
        self._changed()

    def _undo(self):
        self._restore(self.undo_stack, self.redo_stack)

    def _redo(self):
        self._restore(self.redo_stack, self.undo_stack)

    # -- playback / live preview

    def _play(self, on):
        self.playing = on
        self.play_btn.setText("❚❚  Pause" if on else "▶  Play")
        if on and self.anim:
            self.t = sum(k.duration for k in self.anim.keys[:self.key])
            self.canvas.labels = None
        self._last_tick = time.monotonic()
        self._show_key()

    def set_preview(self, on):
        if not on and self.on_tree.isChecked():
            self.on_tree.blockSignals(True)
            self.on_tree.setChecked(False)
            self.on_tree.blockSignals(False)
        if on:
            self.ctx.start_live("animation editor")
        else:
            self.ctx.stop_live("animation editor")

    def _live_changed(self, owner):
        if owner != "animation editor" and self.on_tree.isChecked():
            self.on_tree.blockSignals(True)
            self.on_tree.setChecked(False)
            self.on_tree.blockSignals(False)

    def _tick(self):
        now = time.monotonic()
        dt, self._last_tick = (now - self._last_tick) * 1000, now
        a = self.anim
        if not a:
            return
        if self.playing:
            self.t = (self.t + dt) % a.total_ms
            e1, e2 = a.frame(self.t)
            self.canvas.set_levels(*Mirror.display(e1, e2, level=1.0))
            i, _ = a.key_at(int(self.t))
            self.pos.setText("%.2f / %.2f s · key %d" % (self.t / 1000, a.total_ms / 1000, i + 1))
        else:
            e1, e2 = key_frame(a.keys[self.key])
            self.pos.setText("Paused on key %d" % (self.key + 1))
        if self.on_tree.isChecked():
            self.ctx.push_live("animation editor", [v / 4095 for v in e1], [v / 4095 for v in e2])


# ---- built-in tuning ---------------------------------------------------------------------------

SPEED_MIN, SPEED_MAX = 8, 255


def speed_to_slider(sp):
    return round(24 * math.log2(max(SPEED_MIN, sp) / 64))


def slider_to_speed(v):
    return max(SPEED_MIN, min(SPEED_MAX, round(64 * 2 ** (v / 24))))


class TuningPanel(QWidget):
    def __init__(self, ctx):
        super().__init__()
        self.ctx = ctx
        self.cfg = None
        self.mode = 0
        self._t0 = time.monotonic()
        self._apply_timer = QTimer(self)
        self._apply_timer.setSingleShot(True)
        self._apply_timer.timeout.connect(lambda: self._send(False))
        self._save_timer = QTimer(self)
        self._save_timer.setSingleShot(True)
        self._save_timer.timeout.connect(lambda: self._send(True))
        self._last_apply = 0

        root = QHBoxLayout(self)
        root.setContentsMargins(0, 12, 0, 0)
        root.setSpacing(16)
        self.list = QListWidget()
        self.list.setFixedWidth(230)
        for m in range(N_BASIC):
            it = QListWidgetItem("%s\n%s" % (BUILTIN_NAMES[m], BUILTIN_HINTS[m]))
            it.setToolTip(BUILTIN_HINTS[m])
            self.list.addItem(it)
        self.list.setWordWrap(True)
        self.list.currentRowChanged.connect(self._select)
        root.addWidget(self.list)

        mid = QVBoxLayout()
        self.preview = TreeView()
        mid.addWidget(self.preview, 1)
        mid.addWidget(label("Preview: what this animation looks like with these settings.", muted=True))
        root.addLayout(mid, 1)

        c, cl = card()
        self.title = label("", h2=True)
        cl.addWidget(self.title)
        self.speed = QSlider(Qt.Horizontal)
        self.speed.setRange(speed_to_slider(SPEED_MIN), speed_to_slider(SPEED_MAX))
        self.speed_val = label("")
        self.gain = QSlider(Qt.Horizontal)
        self.gain.setRange(0, 255)
        self.gain_val = label("")
        self.offset = QSlider(Qt.Horizontal)
        self.offset.setRange(-128, 127)
        self.offset_val = label("")
        for name, s, v, tip in (("Speed", self.speed, self.speed_val, "How fast the animation runs"),
                                ("Brightness", self.gain, self.gain_val, "Scales the animation's levels"),
                                ("Base glow", self.offset, self.offset_val, "Adds to (or takes from) every level")):
            cl.addWidget(label(name, muted=True))
            s.setToolTip(tip)
            v.setMinimumWidth(52)
            s.valueChanged.connect(self._changed)
            cl.addWidget(hstretch(s, v))
        reset = QPushButton("Reset this animation")
        reset.clicked.connect(self._reset)
        cl.addWidget(reset)
        self.show_btn = QPushButton("Play it on the tree")
        self.show_btn.clicked.connect(lambda: ctx.cmd(lambda t, m=self.mode: t.set_show(m)))
        cl.addWidget(self.show_btn)
        self.save_state = label("", muted=True, wrap=True)
        cl.addWidget(self.save_state)
        cl.addStretch(1)
        c.setFixedWidth(280)
        root.addWidget(c)

        ctx.configChanged.connect(self._config)
        ctx.connectionChanged.connect(lambda ok: self._config(ctx.config))
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._tick)
        self.timer.start(33)
        self._config(None)
        self.list.setCurrentRow(0)

    def _config(self, cfg):
        if self._save_timer.isActive() or self._apply_timer.isActive():
            return  # our own pending edits win
        self.cfg = (cfg or self.ctx.config).copy() if (cfg or self.ctx.config) else (self.cfg or None)
        if self.cfg is None:
            from .device import Config
            self.cfg = Config()
        can = self.ctx.connected and self.ctx.config is not None
        self.show_btn.setEnabled(self.ctx.connected)
        self.save_state.setText("Changes are saved on the tree." if can else
                                "No tree with editable settings connected – changes only show in the preview.")
        self._select(self.mode)

    def _select(self, m):
        if m < 0:
            return
        self.mode = m
        self.title.setText(BUILTIN_NAMES[m])
        p = self.cfg.params[m]
        for s, v in ((self.speed, speed_to_slider(p.speed)), (self.gain, p.gain), (self.offset, p.offset)):
            s.blockSignals(True)
            s.setValue(v)
            s.blockSignals(False)
        self._labels()

    def _labels(self):
        p = self.cfg.params[self.mode]
        self.speed_val.setText("×%.2f" % (p.speed / 64))
        self.gain_val.setText("%d %%" % round(p.gain * 100 / 128))
        self.offset_val.setText("%+d %%" % round(p.offset * 100 / 256))

    def _changed(self):
        p = self.cfg.params[self.mode]
        p.speed = slider_to_speed(self.speed.value())
        p.gain = self.gain.value()
        p.offset = self.offset.value()
        self._labels()
        if self.ctx.connected and self.ctx.config is not None:
            self.save_state.setText("Saving…")
            if not self._apply_timer.isActive():
                self._apply_timer.start(max(0, int(150 - (time.monotonic() - self._last_apply) * 1000)))
            self._save_timer.start(900)

    def _reset(self):
        self.cfg.params[self.mode] = ModeParams()
        self._select(self.mode)
        self._changed()

    def _send(self, persist):
        if not (self.ctx.connected and self.ctx.config is not None):
            return
        self._last_apply = time.monotonic()
        cfg = self.ctx.config.copy()
        cfg.params = [ModeParams(p.speed, p.gain, p.offset) for p in self.cfg.params]
        done = (lambda r: self.save_state.setText("Saved on the tree.")) if persist else None
        self.ctx.write_config(cfg, persist, done)

    def _tick(self):
        now = time.monotonic()
        dt, self._t0 = (now - self._t0) * 1000, now
        if not self.isVisible():
            return
        # virtual time at the mode's speed, evaluated at 1x: dragging the speed slider doesn't jump
        p = self.cfg.params[self.mode]
        self.vt = getattr(self, "vt", 20000.0) + dt * p.speed / 64
        params = [ModeParams(64, q.gain, q.offset) for q in self.cfg.params]
        e1, e2 = builtin.mode_frame(self.mode, int(self.vt), params)
        level = builtin.rail(self.mode, int(self.vt), params) / 4096 if self.mode == builtin.BREATHE else 1.0
        self.preview.set_levels(*Mirror.display(e1, e2, level=level))
