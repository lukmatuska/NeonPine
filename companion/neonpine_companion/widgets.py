"""Shared widgets: theme, drawn icons, the tree view, sparklines."""
import math
from collections import deque

from PySide6.QtCore import QPointF, QRectF, QSize, Qt, Signal
from PySide6.QtGui import QBrush, QColor, QFont, QIcon, QLinearGradient, QPainter, QPainterPath, QPen, QPixmap, QRadialGradient
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QSizePolicy, QVBoxLayout, QWidget

from . import geometry as G

ACCENT = "#ff7a2f"
ACCENT_HI = "#ff9a5c"
GOOD = "#3ccf7e"
WARN = "#ffb347"
BAD = "#ff5c5c"
NEON = QColor(255, 106, 28)
NEON_CORE = QColor(255, 196, 140)

QSS = """
* { font-size: 10pt; }
QWidget { color: #e4e6e8; }
QMainWindow, QDialog, QMessageBox { background: #0f1113; }
QStackedWidget, QTabWidget > QStackedWidget > QWidget { background: transparent; }
QLabel { background: transparent; }
QLabel[muted="true"] { color: #8b9096; }
QLabel[h1="true"] { font-size: 17pt; font-weight: 600; }
QLabel[h2="true"] { font-size: 12pt; font-weight: 600; }
QFrame[card="true"] { background: #16191c; border: 1px solid #23272c; border-radius: 10px; }
QFrame[card="true"] QLabel, QFrame[card="true"] QCheckBox, QFrame[card="true"] QRadioButton { background: transparent; }
QFrame#sidebar { background: #121417; border-right: 1px solid #1f2327; }
QPushButton { background: #1d2125; border: 1px solid #2b3036; border-radius: 7px; padding: 6px 12px; }
QPushButton:hover { background: #252a2f; border-color: #3a4047; }
QPushButton:pressed { background: #2c3238; }
QPushButton:disabled { color: #5d6268; background: #16191c; border-color: #22262a; }
QPushButton:checked { background: #3a2416; border-color: #ff7a2f; color: #ffd2b8; }
QPushButton[primary="true"] { background: #ff7a2f; border-color: #ff7a2f; color: #1a0d05; font-weight: 600; }
QPushButton[primary="true"]:hover { background: #ff9a5c; }
QPushButton[primary="true"]:disabled { background: #4a3122; color: #8a6a58; border-color: #4a3122; }
QPushButton[danger="true"] { border-color: #6b2b2b; color: #ffb0b0; }
QPushButton[nav="true"] { text-align: left; padding: 9px 12px; border: none; border-radius: 8px; background: transparent; color: #b9bdc2; }
QPushButton[nav="true"]:hover { background: #1b1f23; color: #e4e6e8; }
QPushButton[nav="true"]:checked { background: #24180f; color: #ffb48a; }
QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox, QTimeEdit, QPlainTextEdit {
    background: #121417; border: 1px solid #2b3036; border-radius: 6px; padding: 4px 6px; selection-background-color: #ff7a2f; }
QLineEdit:focus, QSpinBox:focus, QComboBox:focus, QTimeEdit:focus { border-color: #ff7a2f; }
QLineEdit:disabled, QSpinBox:disabled, QDoubleSpinBox:disabled, QComboBox:disabled, QTimeEdit:disabled { color: #5d6268; border-color: #22262a; }
QSlider::sub-page:horizontal:disabled { background: #4a3122; }
QSlider::handle:horizontal:disabled { background: #3a3f44; border-color: #4a3122; }
QComboBox QAbstractItemView { background: #16191c; border: 1px solid #2b3036; selection-background-color: #3a2416; }
QCheckBox, QRadioButton { spacing: 8px; background: transparent; }
QCheckBox::indicator, QRadioButton::indicator { width: 16px; height: 16px; }
QCheckBox::indicator { border: 1px solid #3a4047; border-radius: 4px; background: #121417; }
QCheckBox::indicator:checked { background: #ff7a2f; border-color: #ff7a2f; }
QRadioButton::indicator { border: 1px solid #3a4047; border-radius: 8px; background: #121417; }
QRadioButton::indicator:checked { background: #ff7a2f; border: 3px solid #121417; outline: 1px solid #ff7a2f; }
QSlider::groove:horizontal { height: 4px; background: #2b3036; border-radius: 2px; }
QSlider::sub-page:horizontal { background: #ff7a2f; border-radius: 2px; }
QSlider::handle:horizontal { width: 16px; height: 16px; margin: -6px 0; border-radius: 8px; background: #ffd2b8; border: 2px solid #ff7a2f; }
QSlider::groove:vertical { width: 4px; background: #2b3036; border-radius: 2px; }
QSlider::add-page:vertical { background: #ff7a2f; border-radius: 2px; }
QSlider::handle:vertical { width: 16px; height: 16px; margin: 0 -6px; border-radius: 8px; background: #ffd2b8; border: 2px solid #ff7a2f; }
QProgressBar { background: #121417; border: 1px solid #2b3036; border-radius: 6px; text-align: center; height: 18px; }
QProgressBar::chunk { background: #ff7a2f; border-radius: 5px; }
QListWidget { background: #121417; border: 1px solid #23272c; border-radius: 8px; padding: 4px; }
QListWidget::item { padding: 6px; border-radius: 6px; }
QListWidget::item:selected { background: #2a1b11; color: #ffd2b8; }
QListWidget::item:hover { background: #1b1f23; }
QScrollArea { border: none; background: transparent; }
QScrollBar:vertical { background: transparent; width: 10px; }
QScrollBar::handle:vertical { background: #2b3036; border-radius: 5px; min-height: 30px; }
QScrollBar:horizontal { background: transparent; height: 10px; }
QScrollBar::handle:horizontal { background: #2b3036; border-radius: 5px; min-width: 30px; }
QScrollBar::add-line, QScrollBar::sub-line { width: 0; height: 0; }
QToolTip { background: #1d2125; color: #e4e6e8; border: 1px solid #3a4047; padding: 4px; }
QTabWidget::pane { border: none; }
QTabBar::tab { background: transparent; color: #8b9096; padding: 8px 14px; border-bottom: 2px solid transparent; }
QTabBar::tab:selected { color: #ffb48a; border-bottom-color: #ff7a2f; }
QTabBar::tab:hover { color: #e4e6e8; }
QMenu { background: #16191c; border: 1px solid #2b3036; padding: 4px; }
QMenu::item { padding: 6px 22px 6px 18px; border-radius: 5px; }
QMenu::item:selected { background: #2a1b11; color: #ffd2b8; }
QMenu::separator { height: 1px; background: #2b3036; margin: 4px 8px; }
QMenu::indicator { width: 12px; height: 12px; }
QGroupBox { border: 1px solid #23272c; border-radius: 8px; margin-top: 14px; padding-top: 6px; }
QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 4px; color: #8b9096; }
"""


def dark_palette():
    from PySide6.QtGui import QPalette
    pal = QPalette()
    for role, c in ((QPalette.Window, "#0f1113"), (QPalette.WindowText, "#e4e6e8"), (QPalette.Base, "#121417"),
                    (QPalette.AlternateBase, "#16191c"), (QPalette.Text, "#e4e6e8"), (QPalette.Button, "#1d2125"),
                    (QPalette.ButtonText, "#e4e6e8"), (QPalette.Highlight, ACCENT), (QPalette.HighlightedText, "#1a0d05"),
                    (QPalette.ToolTipBase, "#1d2125"), (QPalette.ToolTipText, "#e4e6e8"), (QPalette.PlaceholderText, "#6b7076"),
                    (QPalette.Link, ACCENT_HI)):
        pal.setColor(role, QColor(c))
    pal.setColor(QPalette.Disabled, QPalette.Text, QColor("#5d6268"))
    pal.setColor(QPalette.Disabled, QPalette.ButtonText, QColor("#5d6268"))
    pal.setColor(QPalette.Disabled, QPalette.WindowText, QColor("#5d6268"))
    return pal


def card(parent=None, margins=14, spacing=8, horizontal=False):
    f = QFrame(parent)
    f.setProperty("card", True)
    lay = (QHBoxLayout if horizontal else QVBoxLayout)(f)
    lay.setContentsMargins(margins, margins, margins, margins)
    lay.setSpacing(spacing)
    return f, lay


def label(text="", muted=False, h1=False, h2=False, wrap=False):
    lb = QLabel(text)
    if muted:
        lb.setProperty("muted", True)
    if h1:
        lb.setProperty("h1", True)
    if h2:
        lb.setProperty("h2", True)
    lb.setWordWrap(wrap)
    return lb


def set_prop(w, name, value):
    w.setProperty(name, value)
    w.style().unpolish(w)
    w.style().polish(w)


# ---- icons -------------------------------------------------------------------------------------

def _pine_path(s):
    p = QPainterPath()
    p.moveTo(s * 0.5, s * 0.06)
    for y, w in ((0.36, 0.20), (0.58, 0.30), (0.84, 0.42)):
        p.lineTo(s * (0.5 + w), s * y)
        p.lineTo(s * (0.5 + w * 0.45), s * y)
    p.lineTo(s * 0.58, s * 0.84)
    p.lineTo(s * 0.58, s * 0.96)
    p.lineTo(s * 0.42, s * 0.96)
    p.lineTo(s * 0.42, s * 0.84)
    for y, w in ((0.84, 0.42), (0.58, 0.30), (0.36, 0.20)):
        p.lineTo(s * (0.5 - w * 0.45), s * y)
        p.lineTo(s * (0.5 - w), s * y)
    p.closeSubpath()
    return p


def app_icon_pixmap(size=256, state="on"):
    """state: on (neon), off (dim), idle (grey, no tree connected)."""
    pm = QPixmap(size, size)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    path = _pine_path(size)
    board = QColor("#1e4a2b") if state != "idle" else QColor("#3a3f44")
    p.fillPath(path, board)
    edge = {"on": QColor(255, 140, 70), "off": QColor(150, 90, 60), "idle": QColor(140, 146, 152)}[state]
    p.setPen(QPen(edge, max(1.0, size / 22), Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
    p.drawPath(path)
    if state != "idle":
        glow = NEON if state == "on" else QColor(140, 70, 30)
        for x, y in ((0.5, 0.25), (0.42, 0.48), (0.58, 0.48), (0.35, 0.72), (0.5, 0.72), (0.65, 0.72)):
            r = size * (0.085 if size >= 32 else 0.11)
            g = QRadialGradient(QPointF(x * size, y * size), r * 1.6)
            g.setColorAt(0, QColor(255, 220, 180) if state == "on" else QColor(200, 130, 90))
            g.setColorAt(0.35, glow)
            g.setColorAt(1, QColor(glow.red(), glow.green(), glow.blue(), 0))
            p.setPen(Qt.NoPen)
            p.setBrush(g)
            p.drawEllipse(QPointF(x * size, y * size), r * 1.6, r * 1.6)
    p.end()
    return pm


def app_icon(state="on"):
    ic = QIcon()
    for s in (16, 20, 24, 32, 48, 64, 128, 256):
        ic.addPixmap(app_icon_pixmap(s, state))
    return ic


def line_icon(kind, color="#b9bdc2", size=20):
    pm = QPixmap(size * 2, size * 2)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    p.scale(2, 2)
    pen = QPen(QColor(color), 1.6, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin)
    p.setPen(pen)
    s = size
    if kind == "tree":
        p.drawPath(_pine_path(s))
    elif kind == "edit":
        path = QPainterPath()
        path.moveTo(s * .2, s * .8)
        path.lineTo(s * .25, s * .62)
        path.lineTo(s * .68, s * .18)
        path.lineTo(s * .82, s * .32)
        path.lineTo(s * .38, s * .76)
        path.closeSubpath()
        p.drawPath(path)
        p.drawLine(QPointF(s * .6, s * .26), QPointF(s * .74, s * .4))
    elif kind == "tune":
        for i, x in enumerate((0.25, 0.5, 0.75)):
            p.drawLine(QPointF(s * x, s * .15), QPointF(s * x, s * .85))
            y = (0.35, 0.65, 0.45)[i]
            p.setBrush(QColor("#0f1113"))
            p.drawEllipse(QPointF(s * x, s * y), s * .09, s * .09)
    elif kind == "live":
        path = QPainterPath()
        path.moveTo(s * .08, s * .5)
        for i, (x, y) in enumerate(((.25, .5), (.33, .2), (.45, .82), (.57, .3), (.66, .62), (.74, .5), (.92, .5))):
            path.lineTo(s * x, s * y)
        p.drawPath(path)
    elif kind == "settings":
        p.drawEllipse(QPointF(s * .5, s * .5), s * .14, s * .14)
        for k in range(8):
            a = k * math.pi / 4
            p.drawLine(QPointF(s * (.5 + .24 * math.cos(a)), s * (.5 + .24 * math.sin(a))),
                       QPointF(s * (.5 + .36 * math.cos(a)), s * (.5 + .36 * math.sin(a))))
        p.drawEllipse(QPointF(s * .5, s * .5), s * .25, s * .25)
    elif kind == "pulse":
        p.drawRoundedRect(QRectF(s * .12, s * .18, s * .76, s * .64), 3, 3)
        path = QPainterPath()
        path.moveTo(s * .2, s * .55)
        for x, y in ((.38, .55), (.45, .32), (.55, .7), (.62, .5), (.8, .5)):
            path.lineTo(s * x, s * y)
        p.drawPath(path)
    elif kind == "chip":
        p.drawRoundedRect(QRectF(s * .26, s * .26, s * .48, s * .48), 2, 2)
        for k in range(3):
            o = .36 + k * .14
            for a, b in (((o, .1), (o, .26)), ((o, .74), (o, .9)), ((.1, o), (.26, o)), ((.74, o), (.9, o))):
                p.drawLine(QPointF(s * a[0], s * a[1]), QPointF(s * b[0], s * b[1]))
    elif kind == "app":
        p.drawRoundedRect(QRectF(s * .14, s * .2, s * .72, s * .6), 3, 3)
        p.drawLine(QPointF(s * .14, s * .36), QPointF(s * .86, s * .36))
        p.drawPoint(QPointF(s * .24, s * .28))
        p.drawPoint(QPointF(s * .32, s * .28))
    p.end()
    pm.setDevicePixelRatio(2)
    return QIcon(pm)


# ---- tree view ---------------------------------------------------------------------------------

def _board_path():
    path = QPainterPath()
    path.moveTo(*G.OUTLINE[0])
    for x, y in G.OUTLINE[1:]:
        path.lineTo(x, y)
    path.closeSubpath()
    return path


class TreeView(QWidget):
    """The board with its ten lamps. Levels are display brightness 0..1 per electrode."""
    electrodePressed = Signal(int, int, int)   # lamp, side (0 left, 1 right), mouse button
    electrodeDragged = Signal(int, int, int)
    touchPadClicked = Signal()

    _board = None

    def __init__(self, parent=None, compact=False, editable=False):
        super().__init__(parent)
        self.compact = compact
        self.editable = editable
        self.left = [0.0] * 10
        self.right = [0.0] * 10
        self.labels = None        # optional per-electrode text (editor: levels)
        self.selected = set()     # (lamp, side)
        self.hover = None
        self.dim_board = False
        self.dragging = None
        self._last_drag = None
        if TreeView._board is None:
            TreeView._board = _board_path()
        self.setMouseTracking(editable or not compact)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setMinimumSize(QSize(60, 70) if compact else QSize(200, 240))

    def sizeHint(self):
        return QSize(120, 140) if self.compact else QSize(420, 520)

    def set_levels(self, left, right):
        self.left = [max(0.0, min(1.0, float(v))) for v in left]
        self.right = [max(0.0, min(1.0, float(v))) for v in right]
        self.update()

    # -- geometry

    def _transform(self):
        x0, y0, x1, y1 = G.BOUNDS
        pad = 1.5 if self.compact else 4.0
        w, h = x1 - x0 + 2 * pad, y1 - y0 + 2 * pad
        s = min(self.width() / w, self.height() / h)
        ox = (self.width() - w * s) / 2 - (x0 - pad) * s
        oy = (self.height() - h * s) / 2 - (y0 - pad) * s
        return s, ox, oy

    def _to_board(self, pos):
        s, ox, oy = self._transform()
        return (pos.x() - ox) / s, (pos.y() - oy) / s

    def electrode_at(self, pos):
        bx, by = self._to_board(pos)
        for i, (x, y) in enumerate(G.LAMPS):
            if x - G.GLASS_HALF_W - 0.8 <= bx <= x + G.GLASS_HALF_W + 0.8 and y - 1.2 <= by <= y + G.GLASS_BOTTOM + 0.6:
                return i, 0 if bx < x else 1
        return None

    def _on_touch_pad(self, pos):
        bx, by = self._to_board(pos)
        x, y, r = G.TOUCH_PAD
        return (bx - x) ** 2 + (by - y) ** 2 <= (r + 1) ** 2

    # -- mouse

    def mousePressEvent(self, e):
        hit = self.electrode_at(e.position())
        if hit and self.editable:
            self.dragging = e.button()
            self._last_drag = hit
            self.electrodePressed.emit(hit[0], hit[1], int(e.button().value))
        elif not self.compact and self._on_touch_pad(e.position()):
            self.touchPadClicked.emit()

    def mouseMoveEvent(self, e):
        hit = self.electrode_at(e.position()) if self.editable else None
        pad = not self.compact and self._on_touch_pad(e.position())
        new_hover = hit or ("pad" if pad else None)
        if new_hover != self.hover:
            self.hover = new_hover
            self.setCursor(Qt.PointingHandCursor if new_hover else Qt.ArrowCursor)
            self.update()
        if self.dragging is not None and hit and hit != self._last_drag:
            self._last_drag = hit
            self.electrodeDragged.emit(hit[0], hit[1], int(self.dragging.value))

    def mouseReleaseEvent(self, e):
        self.dragging = None
        self._last_drag = None

    def leaveEvent(self, e):
        self.hover = None
        self.update()

    # -- painting

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        s, ox, oy = self._transform()
        p.translate(ox, oy)
        p.scale(s, s)
        board = self._board

        # board + silkscreen
        g = QLinearGradient(0, G.BOUNDS[1], 0, G.BOUNDS[3])
        dim = self.dim_board
        g.setColorAt(0, QColor("#1d3b26") if not dim else QColor("#1a2a20"))
        g.setColorAt(1, QColor("#13281a") if not dim else QColor("#121c16"))
        p.fillPath(board, g)
        p.setPen(QPen(QColor("#2d5a3a"), 0.5))
        p.drawPath(board)
        if not self.compact:
            p.save()
            p.setClipPath(board)
            p.setPen(QPen(QColor(235, 240, 235, 170), 3.3))
            p.drawPath(board)
            p.setPen(QPen(QColor("#18331f"), 2.9))
            p.drawPath(board)
            p.restore()
            f = QFont("DejaVu Sans")
            f.setPixelSize(5)
            f.setLetterSpacing(QFont.AbsoluteSpacing, 0.4)
            p.setFont(f)
            p.setPen(QColor(235, 240, 235, 210))
            p.drawText(QRectF(G.LABEL[0] - 20, G.LABEL[1] - 4, 40, 8), Qt.AlignCenter, "NEON PINE")
            tx, ty, tr = G.TOUCH_PAD
            p.setPen(QPen(QColor(235, 240, 235, 200 if self.hover == "pad" else 120), 0.35))
            p.setBrush(QColor(255, 122, 47, 60) if self.hover == "pad" else Qt.NoBrush)
            p.drawEllipse(QPointF(tx, ty), tr + 1.2, tr + 1.2)
            p.setPen(QPen(QColor("#2a4a33"), 0.3))
            p.setBrush(QColor("#1f3d29"))
            p.drawEllipse(QPointF(tx, ty), tr, tr)
            lx, ly = G.LIGHT_SENSOR
            p.setPen(Qt.NoPen)
            p.setBrush(QColor("#7a1d1d"))
            p.drawEllipse(QPointF(lx, ly), 1.5, 1.5)

        # lamps: glass, electrodes, glow
        glows = []
        for i, (x, y) in enumerate(G.LAMPS):
            top, bot, hw = y + G.GLASS_TOP, y + G.GLASS_BOTTOM, G.GLASS_HALF_W
            if not self.compact:
                p.setPen(Qt.NoPen)
                p.setBrush(QColor("#c9a43a"))
                for dx in (-1.5, 1.5):
                    p.drawEllipse(QPointF(x + dx, y), 0.85, 0.85)
                p.setBrush(QColor("#13281a"))
                for dx in (-1.5, 1.5):
                    p.drawEllipse(QPointF(x + dx, y), 0.4, 0.4)
                p.setPen(QPen(QColor(200, 200, 190), 0.35))
                p.drawLine(QPointF(x - 1.5, y), QPointF(x - 0.8, top + 0.8))
                p.drawLine(QPointF(x + 1.5, y), QPointF(x + 0.8, top + 0.8))
            glass = QPainterPath()
            glass.addRoundedRect(QRectF(x - hw, top, 2 * hw, bot - top), hw * 0.9, hw * 0.9)
            gg = QLinearGradient(x - hw, 0, x + hw, 0)
            gg.setColorAt(0, QColor(220, 225, 215, 36))
            gg.setColorAt(0.3, QColor(240, 245, 235, 70))
            gg.setColorAt(1, QColor(200, 205, 195, 26))
            p.fillPath(glass, gg)
            p.setPen(QPen(QColor(220, 225, 215, 90), 0.2))
            p.drawPath(glass)
            for side, lv in ((0, self.left[i]), (1, self.right[i])):
                ex = x + (-0.75 if side == 0 else 0.75)
                p.setPen(QPen(QColor(150, 150, 140, 160), 0.35))
                p.drawLine(QPointF(ex, top + 0.9), QPointF(ex, bot - 1.0))
                if lv > 0.002:
                    glows.append((ex, top, bot, lv))
                if self.editable and ((i, side) in self.selected or self.hover == (i, side)):
                    r = QRectF(ex - 1.05, top + 0.3, 2.1, bot - top - 0.6)
                    p.setBrush(Qt.NoBrush)
                    p.setPen(QPen(QColor(255, 210, 180, 230 if self.hover == (i, side) else 140), 0.25, Qt.DashLine))
                    p.drawRoundedRect(r, 0.8, 0.8)

        # additive neon glow
        p.setCompositionMode(QPainter.CompositionMode_Plus)
        p.setPen(Qt.NoPen)
        for ex, top, bot, lv in glows:
            a = lv ** 0.8
            mid = (top + bot) / 2 + 0.3
            h = (bot - top) * 0.42
            # bloom outside the glass
            rg = QRadialGradient(QPointF(ex, mid), 1.0)
            rg.setColorAt(0, QColor(255, 90, 20, int(150 * a)))
            rg.setColorAt(1, QColor(255, 60, 10, 0))
            p.save()
            p.translate(ex, mid)
            p.scale(2.0 + 2.2 * a, h * (1.15 + 0.4 * a))
            p.translate(-ex, -mid)
            p.setBrush(rg)
            p.drawEllipse(QPointF(ex, mid), 1.0, 1.0)
            p.restore()
            # the glow wrapping the electrode
            rg = QRadialGradient(QPointF(ex, mid), 1.0)
            rg.setColorAt(0, QColor(255, 200, 150, int(255 * a)))
            rg.setColorAt(0.35, QColor(255, 120, 40, int(230 * a)))
            rg.setColorAt(1, QColor(255, 80, 20, 0))
            p.save()
            p.translate(ex, mid)
            p.scale(0.95, h)
            p.translate(-ex, -mid)
            p.setBrush(rg)
            p.drawEllipse(QPointF(ex, mid), 1.0, 1.0)
            p.restore()
        p.setCompositionMode(QPainter.CompositionMode_SourceOver)

        if self.labels:
            f = QFont("DejaVu Sans")
            f.setPixelSize(2)
            f.setBold(True)
            p.setFont(f)
            for i, (x, y) in enumerate(G.LAMPS):
                for side in (0, 1):
                    t = self.labels[side][i]
                    ex = x + (-0.95 if side == 0 else 0.95)
                    r = QRectF(ex - 1.1, y + G.GLASS_BOTTOM + 0.2, 2.2, 2.4)
                    p.setPen(QColor(255, 220, 200) if t not in ("0", "") else QColor(120, 125, 130))
                    p.drawText(r, Qt.AlignCenter, t)
        p.end()


# ---- small widgets -----------------------------------------------------------------------------

class Sparkline(QWidget):
    def __init__(self, color=ACCENT, length=240, lo=None, hi=None, unit="", parent=None):
        super().__init__(parent)
        self.data = deque(maxlen=length)
        self.color = QColor(color)
        self.lo, self.hi, self.unit = lo, hi, unit
        self.marks = []  # (value, color)
        self.setMinimumHeight(70)

    def add(self, v):
        self.data.append(v)
        self.update()

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        r = QRectF(self.rect()).adjusted(2, 4, -2, -4)
        p.setPen(QPen(QColor("#23272c"), 1))
        p.drawRoundedRect(r, 6, 6)
        if len(self.data) < 2:
            return
        vals = list(self.data)
        lo = self.lo if self.lo is not None else min(vals + [m[0] for m in self.marks])
        hi = self.hi if self.hi is not None else max(vals + [m[0] for m in self.marks])
        if hi - lo < 1e-6:
            hi = lo + 1
        span = hi - lo
        lo -= span * 0.08
        hi += span * 0.08
        ymap = lambda v: r.bottom() - (v - lo) / (hi - lo) * r.height()
        for v, c in self.marks:
            p.setPen(QPen(QColor(c), 1, Qt.DashLine))
            p.drawLine(QPointF(r.left(), ymap(v)), QPointF(r.right(), ymap(v)))
        n = self.data.maxlen
        path = QPainterPath()
        for k, v in enumerate(vals):
            pt = QPointF(r.right() - (len(vals) - 1 - k) * r.width() / (n - 1), ymap(v))
            path.lineTo(pt) if k else path.moveTo(pt)
        fill = QPainterPath(path)
        fill.lineTo(r.right(), r.bottom())
        fill.lineTo(r.right() - (len(vals) - 1) * r.width() / (n - 1), r.bottom())
        fill.closeSubpath()
        g = QLinearGradient(0, r.top(), 0, r.bottom())
        c = QColor(self.color)
        c.setAlpha(70)
        g.setColorAt(0, c)
        c.setAlpha(0)
        g.setColorAt(1, c)
        p.fillPath(fill, g)
        p.setPen(QPen(self.color, 1.6))
        p.drawPath(path)


class Dot(QWidget):
    def __init__(self, color="#555", size=10, parent=None):
        super().__init__(parent)
        self.color = QColor(color)
        self.setFixedSize(size + 6, size + 6)
        self.size = size

    def set_color(self, c):
        self.color = QColor(c)
        self.update()

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        c = QPointF(self.width() / 2, self.height() / 2)
        g = QRadialGradient(c, self.size / 2 + 3)
        g.setColorAt(0.45, self.color)
        glow = QColor(self.color)
        glow.setAlpha(0)
        g.setColorAt(1, glow)
        p.setPen(Qt.NoPen)
        p.setBrush(QBrush(g))
        p.drawEllipse(c, self.size / 2 + 3, self.size / 2 + 3)


def hstretch(*widgets, spacing=8):
    w = QWidget()
    lay = QHBoxLayout(w)
    lay.setContentsMargins(0, 0, 0, 0)
    lay.setSpacing(spacing)
    for x in widgets:
        if x is None:
            lay.addStretch(1)
        elif isinstance(x, int):
            lay.addSpacing(x)
        else:
            lay.addWidget(x)
    return w
