"""GravaTrem — o trem que grava os trem da sua tela (PySide6 + motor de `engine.py`).

Uso:
    python -m pip install -r requirements.txt
    python app.py
"""

import math
import os
import shutil
import sys
import threading
import time
import logging
from datetime import datetime
from logging.handlers import RotatingFileHandler
from pathlib import Path

import mss
import numpy as np
import sounddevice as sd
from PySide6.QtCore import Qt, QTimer, QRect, QSize, Signal
from PySide6.QtGui import (QColor, QPainter, QPainterPath, QPen, QBrush, QImage, QPixmap, QIcon,
                           QShortcut, QKeySequence)
from PySide6.QtWidgets import (QApplication, QButtonGroup, QCheckBox, QComboBox, QDialog, QFrame, QHBoxLayout,
                               QLabel, QMainWindow, QMessageBox, QPushButton, QRubberBand, QScrollArea, QSizePolicy,
                               QStackedWidget, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget)

sys.path.insert(0, str(Path(__file__).resolve().parent))
from engine import (HAS_LOOPBACK, LiveMonitor, default_output_folder, load_lang, new_meter,
                    record_screen, resource_path, save_config)

APP_VERSION = "0.0.1"


def app_log_path():
    p = Path(os.environ.get("APPDATA", str(Path.home()))) / "GravaTrem" / "logs"
    p.mkdir(parents=True, exist_ok=True)
    return p / "gravatrem.log"


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    handlers=[RotatingFileHandler(str(app_log_path()), maxBytes=1_000_000, backupCount=3, encoding="utf-8"),
              logging.StreamHandler(sys.stdout)],
)
log = logging.getLogger("trem")

BG = "#1a1e29"
PANEL = "#222836"
CARD = "#2b3245"
CARD_HOVER = "#343c52"
INPUT = "#161a24"
TXT = "#e8eaf0"
MUTED = "#9aa3b5"
DIM = "#6b7385"
BLUE = "#3ddc84"
MINT_DK = "#25b06f"
RED = "#e5484d"
CYAN = "#7bd0ff"
GREEN = "#10b981"
AMBER = "#f59e0b"

QSS = f"""
QWidget {{ background: {BG}; color: {TXT}; font-family: "Segoe UI"; font-size: 10pt; }}
QFrame#panel {{ background: {PANEL}; border-radius: 8px; }}
QFrame#bar {{ background: {PANEL}; }}
QLabel#title {{ font-size: 11pt; font-weight: bold; }}
QLabel#ver {{ color: {DIM}; font-size: 8pt; font-weight: bold; }}
QLabel#caps {{ color: {DIM}; font-size: 8pt; font-weight: bold; }}
QLabel#mono {{ font-family: "Consolas"; }}
QLabel#desc {{ color: {MUTED}; }}
QLabel#big {{ font-size: 12pt; font-weight: bold; }}
QPushButton#tool {{ background: transparent; border: none; border-radius: 8px; color: {TXT}; padding: 6px 2px; }}
QPushButton#tool:hover {{ background: {CARD}; }}
QPushButton#tool:checked {{ background: {BLUE}; }}
QPushButton#tab {{ background: transparent; border: none; color: {TXT}; padding: 6px 12px; font-weight: bold; }}
QPushButton#tab:hover {{ color: {BLUE}; }}
QPushButton#tab:checked {{ color: {BLUE}; }}
QPushButton#tab:disabled {{ color: {DIM}; }}
QPushButton#mode {{ background: {CARD}; border: none; border-radius: 8px; padding: 12px 8px; color: {TXT}; }}
QPushButton#mode:hover {{ background: {CARD_HOVER}; }}
QPushButton#mode:checked {{ background: {BLUE}; color: white; }}
QComboBox {{ background: {INPUT}; border: 1px solid {CARD}; border-radius: 6px; padding: 6px 10px; }}
QComboBox QAbstractItemView {{ background: {INPUT}; selection-background-color: {CARD}; }}
QComboBox:disabled {{ color: {DIM}; }}
QCheckBox {{ spacing: 8px; }}
QCheckBox::indicator {{ width: 15px; height: 15px; border-radius: 4px; border: 1px solid {DIM}; background: {INPUT}; }}
QCheckBox::indicator:checked {{ background: {BLUE}; border: 1px solid {BLUE}; image: none; }}
QLabel#hotkey {{ background: {INPUT}; border-radius: 6px; padding: 7px 10px; font-family: "Consolas"; }}
QPushButton#start {{ background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #f2555a, stop:1 #d63b3b);
    color: white; border: none; border-radius: 8px; padding: 13px; font-size: 12pt; font-weight: bold; }}
QPushButton#start:hover {{ background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #ff656b, stop:1 #e5484d); }}
QPushButton#stop {{ background: {CARD}; color: white; border: 1px solid {BLUE}; border-radius: 8px;
    padding: 13px; font-size: 12pt; font-weight: bold; }}
QPushButton#ghost {{ background: {CARD}; color: {MUTED}; border: none; border-radius: 6px; padding: 7px 14px; }}
QPushButton#ghost:hover {{ color: {TXT}; background: {CARD_HOVER}; }}
QPushButton#recbig {{ background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #f2555a, stop:1 #c92f34);
    color: white; border: 2px solid #f2b8b5; border-radius: 26px; font-size: 10pt; font-weight: bold; }}
QPushButton#recbig:hover {{ background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #ff656b, stop:1 #e5484d); }}
QPushButton#recbig:checked {{ background: {CARD}; border: 3px solid {BLUE}; }}
QLabel#timer {{ font-family: "Consolas"; font-size: 20pt; }}
QScrollBar:vertical {{ background: {INPUT}; width: 10px; border-radius: 5px; }}
QToolTip {{ background: #0e0e10; color: {TXT}; border: 1px solid {CARD}; padding: 4px; }}
QScrollBar::handle:vertical {{ background: {CARD}; border-radius: 5px; min-height: 30px; }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
"""


def _db(peak):
    if peak <= 0.0001:
        return "-inf dB"
    return f"{20.0 * float(np.log10(peak)):+.0f} dB"


# ---------------------------------------------------------------- icones
def draw_icon(name, color_txt, size=26):
    """Desenha icones de linha (estilo Bandicam) via QPainter. Retorna QIcon."""
    px = QPixmap(size, size)
    px.fill(Qt.transparent)
    p = QPainter(px)
    p.setRenderHint(QPainter.Antialiasing)
    c = QColor(color_txt)
    pen = QPen(c, 2, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin)
    p.setPen(pen)
    p.setBrush(Qt.NoBrush)
    s = size
    u = s / 26.0

    def line(x1, y1, x2, y2):
        p.drawLine(int(x1 * u), int(y1 * u), int(x2 * u), int(y2 * u))

    def rect(x, y, w, h, r=2):
        p.drawRoundedRect(int(x * u), int(y * u), int(w * u), int(h * u), r, r)

    if name == "monitor":
        rect(3, 5, 20, 13)
        line(8, 21, 18, 21)
        line(13, 18, 13, 21)
    elif name == "window":
        rect(3, 6, 13, 11)
        p.save()
        p.setPen(QPen(c, 2, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        p.drawRoundedRect(int(10 * u), int(3 * u), int(13 * u), int(11 * u), 2, 2)
        p.restore()
    elif name == "region":
        p.setPen(QPen(c, 2, Qt.DashLine, Qt.RoundCap, Qt.RoundJoin))
        p.drawRoundedRect(int(5 * u), int(6 * u), int(16 * u), int(12 * u), 2, 2)
        p.setPen(pen)
        line(5, 3, 5, 6)
        line(21, 18, 21, 21)
    elif name == "mic":
        p.setBrush(QBrush(c))
        p.setPen(Qt.NoPen)
        p.drawRoundedRect(int(10.5 * u), int(3 * u), int(5 * u), int(10 * u), 2, 2)
        p.setPen(pen)
        p.setBrush(Qt.NoBrush)
        path = QPainterPath()
        path.moveTo(8 * u, 11 * u)
        path.arcTo(5.5 * u, 9.5 * u, 15 * u, 9 * u, 180, 180)
        p.drawPath(path)
        line(13, 18.5, 13, 22)
        line(9.5, 22, 16.5, 22)
    elif name == "camera":
        rect(3, 8, 20, 12)
        p.setBrush(QBrush(c))
        p.setPen(Qt.NoPen)
        p.drawEllipse(int(9.5 * u), int(11 * u), int(7 * u), int(7 * u))
        p.setPen(pen)
        p.setBrush(Qt.NoBrush)
        rect(9, 5, 8, 4)
    elif name == "rec":
        p.setBrush(QBrush(c))
        p.setPen(Qt.NoPen)
        p.drawEllipse(int(6 * u), int(6 * u), int(14 * u), int(14 * u))
    elif name == "stop":
        p.setBrush(QBrush(c))
        p.setPen(Qt.NoPen)
        p.drawRoundedRect(int(7 * u), int(7 * u), int(12 * u), int(12 * u), 2, 2)
    elif name == "home":
        path = QPainterPath()
        path.moveTo(4 * u, 14 * u)
        path.lineTo(13 * u, 5 * u)
        path.lineTo(22 * u, 14 * u)
        p.drawPath(path)
        rect(8, 13, 10, 9)
    elif name == "gear":
        p.drawEllipse(int(9 * u), int(9 * u), int(8 * u), int(8 * u))
        for a in range(0, 360, 45):
            r1, r2 = 4.2 * u, 6.5 * u
            cx, cy = 13 * u, 13 * u
            line(cx + r1 * math.cos(math.radians(a)), cy + r1 * math.sin(math.radians(a)),
                 cx + r2 * math.cos(math.radians(a)), cy + r2 * math.sin(math.radians(a)))
    elif name == "folder":
        rect(3, 8, 20, 12)
        p.drawRoundedRect(int(3 * u), int(5 * u), int(9 * u), int(5 * u), 2, 2)
    elif name == "play":
        path = QPainterPath()
        path.moveTo(9 * u, 6 * u)
        path.lineTo(19 * u, 13 * u)
        path.lineTo(9 * u, 20 * u)
        path.closeSubpath()
        p.drawPath(path)
    elif name == "menu":
        line(6, 8, 20, 8)
        line(6, 13, 20, 13)
        line(6, 18, 20, 18)
    elif name == "close":
        line(7, 7, 19, 19)
        line(19, 7, 7, 19)
    elif name == "mon_solid":
        p.setBrush(QBrush(c))
        p.setPen(Qt.NoPen)
        p.drawRoundedRect(int(3 * u), int(5 * u), int(20 * u), int(12 * u), 3, 3)
        p.drawRoundedRect(int(11 * u), int(17 * u), int(4 * u), int(4 * u), 1, 1)
        p.drawRoundedRect(int(7 * u), int(21 * u), int(12 * u), int(2.6 * u), 1, 1)
    elif name == "win_solid":
        p.setBrush(QBrush(c))
        p.setPen(Qt.NoPen)
        p.drawRoundedRect(int(9 * u), int(3 * u), int(14 * u), int(12 * u), 3, 3)
        p.setBrush(QBrush(QColor(BG)))
        p.drawRoundedRect(int(4 * u), int(7 * u), int(11 * u), int(11 * u), 3, 3)
        p.setBrush(QBrush(c))
        p.drawRoundedRect(int(4 * u), int(7 * u), int(11 * u), int(11 * u), 3, 3)
        p.setBrush(QBrush(QColor(BG)))
        p.drawRoundedRect(int(6 * u), int(9 * u), int(4 * u), int(4 * u), 1, 1)
    elif name == "reg_solid":
        p.setBrush(QBrush(c))
        p.setPen(Qt.NoPen)
        for x, y, w0, h0 in ((4, 4, 7, 3), (15, 4, 7, 3), (4, 19, 7, 3), (15, 19, 7, 3),
                             (4, 7, 3, 6), (4, 14, 3, 5), (19, 7, 3, 6), (19, 14, 3, 5)):
            p.drawRoundedRect(int(x * u), int(y * u), int(w0 * u), int(h0 * u), 1, 1)
    elif name == "mic_solid":
        p.setBrush(QBrush(c))
        p.setPen(Qt.NoPen)
        p.drawRoundedRect(int(10 * u), int(3 * u), int(6 * u), int(10 * u), 3, 3)
        p.setPen(QPen(c, 2.6, Qt.SolidLine, Qt.RoundCap))
        path = QPainterPath()
        path.moveTo(7.5 * u, 11 * u)
        path.arcTo(5 * u, 9.5 * u, 16 * u, 9.5 * u, 180, 180)
        p.drawPath(path)
        line(13, 18.5, 13, 22)
    elif name == "cam_solid":
        p.setBrush(QBrush(c))
        p.setPen(Qt.NoPen)
        p.drawRoundedRect(int(2.5 * u), int(8 * u), int(21 * u), int(12 * u), 4, 4)
        p.drawRoundedRect(int(9 * u), int(5 * u), int(8 * u), int(4 * u), 2, 2)
        p.setBrush(QBrush(QColor(BG)))
        p.drawEllipse(int(9 * u), int(10.5 * u), int(8 * u), int(8 * u))
        p.setBrush(QBrush(c))
        p.drawEllipse(int(11 * u), int(12.5 * u), int(4 * u), int(4 * u))
    p.end()
    return QIcon(px)


def dual_icon(name):
    """QIcon com estado normal (claro) e checked (branco)."""
    ic = QIcon()
    ic.addPixmap(draw_icon(name, TXT).pixmap(26, 26), QIcon.Normal, QIcon.Off)
    ic.addPixmap(draw_icon(name, "#ffffff").pixmap(26, 26), QIcon.Normal, QIcon.On)
    return ic


# ---------------------------------------------------------------- widgets
class VUMeter(QWidget):
    SEGS = 28

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(16)
        self.level = 0.0
        self.hold = 0.0
        self.hold_ts = 0.0

    def set(self, level):
        now = time.time()
        self.level = min(1.0, max(0.0, level))
        if level >= self.hold or now - self.hold_ts > 1.0:
            self.hold = self.level
            self.hold_ts = now
        self.update()

    def paintEvent(self, _e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()
        gap = 2
        segw = (w - gap * (self.SEGS - 1)) / self.SEGS
        lit = round(self.level * self.SEGS)
        for i in range(self.SEGS):
            base = QColor("#1f3b33") if i < 18 else (QColor("#3d2f14") if i < 24 else QColor("#3d1512"))
            on = QColor(GREEN) if i < 18 else (QColor(AMBER) if i < 24 else QColor(RED))
            p.setBrush(on if i < lit else base)
            p.setPen(Qt.NoPen)
            p.drawRoundedRect(int(i * (segw + gap)), 2, int(segw), h - 4, 3, 3)
        x = int(self.hold * w)
        p.setPen(QPen(QColor("white"), 2))
        p.drawLine(x, 0, x, h)


class WaveScope(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(200, 70)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.mic_pts: list = []
        self.sys_pts: list = []

    def paintEvent(self, _e):
        p = QPainter(self)
        p.fillRect(self.rect(), QColor(INPUT))
        mid = self.height() / 2
        p.setPen(QPen(QColor(CARD), 1))
        p.drawLine(0, int(mid), self.width(), int(mid))
        for pts, color, sign in ((self.mic_pts, QColor(CYAN), -1), (self.sys_pts, QColor(BLUE), 1)):
            if not pts:
                continue
            p.setPen(QPen(color, 1))
            n = len(pts)
            step = self.width() / max(1, 139)
            off = self.width() - step * (n - 1)
            amp = mid - 3
            for i in range(1, n):
                p.drawLine(int(off + (i - 1) * step), int(mid + sign * min(1.0, pts[i - 1]) * amp),
                           int(off + i * step), int(mid + sign * min(1.0, pts[i]) * amp))


class RegionPicker(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent, Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        # cobre a area virtual total (todos os monitores), nao so o do app
        from PySide6.QtGui import QGuiApplication
        union = None
        for s in QGuiApplication.screens():
            union = s.geometry() if union is None else union.united(s.geometry())
        if union is not None:
            self.setGeometry(union)
        else:
            self.setWindowState(Qt.WindowFullScreen)
        self.setStyleSheet("background: black;")
        self.setWindowOpacity(0.35)
        self.band = QRubberBand(QRubberBand.Rectangle, self)
        self.origin = None
        self.rect = None

    def mousePressEvent(self, e):
        self.origin = e.pos()
        self.band.setGeometry(QRect(self.origin, self.origin))
        self.band.show()

    def mouseMoveEvent(self, e):
        if self.origin is not None:
            self.band.setGeometry(QRect(self.origin, e.pos()).normalized())

    def mouseReleaseEvent(self, e):
        r = QRect(self.origin, e.pos()).normalized()
        if r.width() >= 64 and r.height() >= 64:
            g = self.geometry()
            self.rect = {"left": g.x() + r.x(), "top": g.y() + r.y(),
                         "width": r.width(), "height": r.height()}
            self.accept()
        else:
            self.reject()

    def keyPressEvent(self, e):
        if e.key() == Qt.Key_Escape:
            self.reject()


# ---------------------------------------------------------------- janela
# ---------------------------------------------------------------- mini toolbar
class FloatBar(QWidget):
    """Barrinha flutuante estilo Bandicam: menu | res | alvo | timer | REC | foto | X."""

    def __init__(self, main):
        super().__init__(None, Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.main = main
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setStyleSheet(f"background: {PANEL}; border-radius: 10px; color: {TXT};")
        lay = QHBoxLayout(self)
        lay.setContentsMargins(10, 6, 10, 6)
        lay.setSpacing(8)
        self.btn_menu = self._ibtn("menu", "Abrir janela principal")
        self.btn_menu.clicked.connect(self.main.bring_front)
        lay.addWidget(self.btn_menu)
        self.lbl_res = QLabel("1440x900")
        self.lbl_res.setObjectName("mono")
        lay.addWidget(self.lbl_res)
        self.lbl_tgt = QLabel("Tela 1")
        lay.addWidget(self.lbl_tgt)
        self.lbl_time = QLabel("00:00:00")
        self.lbl_time.setObjectName("mono")
        lay.addWidget(self.lbl_time)
        self.btn_rec = QPushButton()
        self.btn_rec.setIcon(draw_icon("rec", "#ffffff"))
        self.btn_rec.setIconSize(QSize(20, 20))
        self.btn_rec.setFixedSize(40, 32)
        self.btn_rec.setStyleSheet(f"background: {RED}; border-radius: 8px; color: white;")
        self.btn_rec.setToolTip("Gravar/Parar (F12)")
        self.btn_rec.clicked.connect(self.main.on_toggle)
        lay.addWidget(self.btn_rec)
        self.btn_shot = self._ibtn("camera", "Foto (F11)")
        self.btn_shot.clicked.connect(self.main.screenshot)
        lay.addWidget(self.btn_shot)
        self.btn_x = self._ibtn("close", "Parar e fechar a barra")
        self.btn_x.clicked.connect(self._on_x)
        lay.addWidget(self.btn_x)
        self._drag = None

    def _ibtn(self, name, tip):
        b = QPushButton()
        b.setIcon(dual_icon(name))
        b.setIconSize(QSize(20, 20))
        b.setFixedSize(36, 32)
        b.setStyleSheet(f"background: transparent; border-radius: 6px;"
                        f"QPushButton:hover {{ background: {CARD}; }}")
        b.setToolTip(tip)
        b.setCursor(Qt.PointingHandCursor)
        return b

    def _on_x(self):
        if self.main.stop_event is not None:
            self.main.on_stop()
        self.hide()

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            self._drag = e.globalPosition().toPoint() - self.frameGeometry().topLeft()

    def mouseMoveEvent(self, e):
        if self._drag is not None:
            self.move(e.globalPosition().toPoint() - self._drag)

    def mouseReleaseEvent(self, _e):
        self._drag = None

    def show_bar(self, res, tgt):
        self.lbl_res.setText(res)
        self.lbl_tgt.setText(tgt)
        self.lbl_time.setText("00:00:00")
        scr = QApplication.primaryScreen().geometry()
        self.adjustSize()
        self.move(scr.center().x() - self.width() // 2, scr.top() + 10)
        self.show()
        self.raise_()

    def tick(self, s):
        self.lbl_time.setText(f"{s // 3600:02d}:{(s % 3600) // 60:02d}:{s % 60:02d}")


class Toggle(QCheckBox):
    """Interruptor moderno (track + knob). Drop-in de QCheckBox."""

    def __init__(self, text, parent=None):
        super().__init__(text, parent)
        self.setCursor(Qt.PointingHandCursor)
        self.setMinimumHeight(26)

    def paintEvent(self, _e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        on = self.isChecked()
        tw, th = 38, 22
        y = (self.height() - th) // 2
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(BLUE if on else "#353437"))
        p.drawRoundedRect(0, y, tw, th, th // 2, th // 2)
        kx = tw - th // 2 - 2 if on else th // 2 + 2
        p.setBrush(QColor("white"))
        p.drawEllipse(kx - 8, y + 2, 16, 16)
        p.setPen(QColor(TXT if self.isEnabled() else DIM))
        p.drawText(tw + 10, 0, self.width() - tw - 10, self.height(),
                   Qt.AlignVCenter | Qt.AlignLeft, self.text())


class MainWindow(QMainWindow):
    AMODES = ("both", "mic", "sys", "none")
    CAPMODES = ("full", "win", "reg")
    preview_ready = Signal(QImage, int, int)
    error_sig = Signal(str)

    def __init__(self):
        super().__init__()
        self.cfg, self.t = load_lang()
        self.setWindowTitle("GravaTrem")
        self.resize(960, 730)
        self.setStyleSheet(QSS)
        self.stop_event = None
        self.thread = None
        self.start_ts = 0.0
        self.last_output = None
        self.meter = new_meter()
        self.disp = {"mic": 0.0, "sys": 0.0}
        self.monitor = LiveMonitor(self.meter, int(self.cfg.get("OPTION", "dwSampleRate", fallback="44100")))
        with mss.MSS() as sct:
            mon = sct.monitors[1]
            self.mon_w, self.mon_h = mon["width"], mon["height"]

        central = QWidget()
        self.setCentralWidget(central)
        log.info("ui: central ok")
        root = QVBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        self._titlebar(root)
        self._toolbar(root)
        self._tabs(root)
        self._pages(root)
        log.info("ui: paginas ok")
        self._banner(root)

        QShortcut(QKeySequence("F12"), self, activated=self.on_toggle)
        QShortcut(QKeySequence("F11"), self, activated=self.screenshot)
        self.preview_ready.connect(self._on_preview)
        self.error_sig.connect(self._on_error)
        self._pv_busy = False
        self._pv_last_emit = time.time()
        self.bar = FloatBar(self)
        self.poll = QTimer(self, timeout=self._poll)
        self.poll.start(120)
        # primeiro frame via loop de eventos (sincrono aqui travaria a abertura se o DWM engasgar)
        QTimer.singleShot(150, self._preview_tick)
        self.pv = QTimer(self, timeout=self._preview_tick)
        self.pv.start(50)
        log.info("ui: timers ok, iniciando monitor")
        self._restart_monitor()
        log.info("ui: pronta")

    # ---------- estrutura ----------
    def _titlebar(self, root):
        bar = QFrame()
        bar.setObjectName("bar")
        lay = QHBoxLayout(bar)
        lay.setContentsMargins(14, 6, 14, 4)
        lay.setSpacing(8)
        ico = resource_path("icon.ico")
        if ico.exists():
            logo = QLabel()
            logo.setPixmap(QPixmap(str(ico)).scaled(24, 24, Qt.KeepAspectRatio, Qt.SmoothTransformation))
            lay.addWidget(logo)
        t = QLabel("GravaTrem")
        t.setObjectName("title")
        lay.addWidget(t)
        u = QLabel(f"v{APP_VERSION}")
        u.setObjectName("ver")
        lay.addWidget(u)
        lay.addStretch(1)
        self.stat = QLabel("● PRONTO")
        self.stat.setObjectName("pill")
        self.stat.setStyleSheet(f"background: {CARD}; color: {CYAN};")
        lay.addWidget(self.stat)
        root.addWidget(bar)

    def _toolbtn(self, lay, name, tip, checkable=False):
        b = QPushButton()
        b.setObjectName("tool")
        b.setCheckable(checkable)
        b.setIcon(dual_icon(name))
        b.setIconSize(QSize(20, 20))
        b.setFixedSize(52, 44)
        b.setToolTip(tip)
        lay.addWidget(b)
        return b

    def _toolbar(self, root):
        bar = QFrame()
        bar.setObjectName("bar")
        lay = QHBoxLayout(bar)
        lay.setContentsMargins(12, 2, 12, 6)
        lay.setSpacing(6)
        seg = QWidget()
        seg_lay = QHBoxLayout(seg)
        seg_lay.setContentsMargins(0, 0, 0, 0)
        seg_lay.setSpacing(0)
        lay.addWidget(seg)
        self.seg_btns = {}
        for m, label in (("full", "Tela"), ("win", "Janela"), ("reg", "Região")):
            b = QPushButton(label, checkable=True, cursor=Qt.PointingHandCursor)
            b.clicked.connect(lambda _c, mm=m: self._set_capmode(mm))
            seg_lay.addWidget(b)
            self.seg_btns[m] = b
        self.tb_mic = QPushButton(checkable=True, cursor=Qt.PointingHandCursor)
        self.tb_mic.setIcon(dual_icon("mic_solid"))
        self.tb_mic.setIconSize(QSize(20, 20))
        self.tb_mic.setFixedSize(44, 38)
        self.tb_mic.setToolTip("Microfone ligado/desligado")
        self.tb_mic.clicked.connect(self._toggle_mic)
        lay.addWidget(self.tb_mic)
        lay.addStretch(1)
        self.btn_rec = QPushButton("●\nREC")
        self.btn_rec.setObjectName("recbig")
        self.btn_rec.setFixedSize(52, 52)
        self.btn_rec.clicked.connect(self.on_toggle)
        lay.addWidget(self.btn_rec)
        self.btn_shot = self._toolbtn(lay, "cam_solid", "Capturar imagem (F11)")
        self.btn_shot.clicked.connect(self.screenshot)
        root.addWidget(bar)

    def _paint_seg(self):
        items = list(self.seg_btns.items())
        for i, (m, b) in enumerate(items):
            act = (m == self.capmode)
            bg = BLUE if act else CARD
            fg = "#06301f" if act else TXT
            r_left = 10 if i == 0 else 0
            r_right = 10 if i == len(items) - 1 else 0
            b.setStyleSheet(
                f"background: {bg}; color: {fg}; border: none;"
                f"border-top-left-radius: {r_left}px; border-bottom-left-radius: {r_left}px;"
                f"border-top-right-radius: {r_right}px; border-bottom-right-radius: {r_right}px;"
                f"padding: 9px 20px; font-weight: {'bold' if act else 'normal'};")

    def _tabs(self, root):
        bar = QFrame()
        bar.setObjectName("bar")
        lay = QHBoxLayout(bar)
        lay.setContentsMargins(14, 0, 14, 0)
        lay.setSpacing(2)
        self.tab_group = QButtonGroup(self, exclusive=True)
        self.tab_btns = []
        for i, name in enumerate(["Começar", "Painel", "Sobre"]):
            b = QPushButton(name)
            b.setObjectName("tab")
            b.setCheckable(True)
            b.clicked.connect(lambda _c, ii=i: self._set_tab(ii))
            lay.addWidget(b)
            self.tab_group.addButton(b)
            self.tab_btns.append(b)
        lay.addStretch(1)
        root.addWidget(bar)

    def _pages(self, root):
        self.pages = QStackedWidget()
        root.addWidget(self.pages, stretch=1)
        self._page_home()
        self._page_dashboard()
        self._page_about()
        self.tab_btns[0].setChecked(True)
        self.capmode = self.cfg.get("OPTION", "sCapMode", fallback="full")
        if self.capmode not in self.CAPMODES:
            self.capmode = "full"
        mode0 = self.cfg.get("OPTION", "sAudioMode", fallback="both")
        avail = list(self.AMODES) if HAS_LOOPBACK else ["mic", "none"]
        self.amode = mode0 if mode0 in avail else ("both" if "both" in avail else "mic")
        self._sync_cap_ui()
        self._upd_dev_state()

    def _panel_page(self, right_fixed=None):
        page = QWidget()
        lay = QHBoxLayout(page)
        lay.setContentsMargins(22, 16, 22, 16)
        lay.setSpacing(20)
        left = QVBoxLayout()
        left.setSpacing(12)
        right = QVBoxLayout()
        right.setSpacing(12)
        lay.addLayout(left, stretch=3)
        if right_fixed:
            right.setContentsMargins(0, 0, 12, 0)
            wrap = QWidget()
            wrap.setLayout(right)
            scroll = QScrollArea()
            scroll.setWidgetResizable(True)
            scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
            scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
            scroll.setFrameShape(QFrame.NoFrame)
            scroll.setWidget(wrap)
            scroll.setFixedWidth(right_fixed + 24)
            lay.addWidget(scroll)
        else:
            lay.addLayout(right, stretch=2)
        self.pages.addWidget(page)
        return left, right

    # ---------- paginas ----------
    def _page_home(self):
        left, right = self._panel_page(right_fixed=260)
        self.home_title = QLabel("Gravação de Tela - Tela Cheia")
        self.home_title.setObjectName("big")
        left.addWidget(self.home_title)
        self.home_desc = QLabel("Este modo permite gravar a área total do seu monitor.")
        self.home_desc.setObjectName("desc")
        self.home_desc.setWordWrap(True)
        left.addWidget(self.home_desc)
        self.view = QLabel("Pronto para Capturar")
        self.view.setStyleSheet("background: #0e0e10; qproperty-alignment: AlignCenter; border-radius: 6px;")
        self.view.setMinimumSize(320, 180)
        self.view.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        left.addWidget(self.view, stretch=1)
        self.badge = QLabel(f"● {self.mon_w}x{self.mon_h}")
        self.badge.setObjectName("mono")
        left.addWidget(self.badge)

        self.hk_rec = Toggle("Gravar/Parar")
        self.hk_rec.setChecked(True)
        self.hk_rec.setEnabled(False)
        hkrow1 = QHBoxLayout()
        hkrow1.addWidget(self.hk_rec, stretch=1)
        f12 = QLabel("F12")
        f12.setObjectName("hotkey")
        hkrow1.addWidget(f12)
        right.addLayout(hkrow1)
        self.hk_shot = Toggle("Capturar Imagem")
        self.hk_shot.setChecked(True)
        self.hk_shot.setEnabled(False)
        hkrow2 = QHBoxLayout()
        hkrow2.addWidget(self.hk_shot, stretch=1)
        f11 = QLabel("F11")
        f11.setObjectName("hotkey")
        hkrow2.addWidget(f11)
        right.addLayout(hkrow2)
        sep2 = QFrame()
        sep2.setFixedHeight(1)
        sep2.setStyleSheet(f"background: {CARD};")
        right.addWidget(sep2)
        al = QLabel("ALVO DA GRAVAÇÃO")
        al.setObjectName("caps")
        right.addWidget(al)
        tgt = QHBoxLayout()
        self.tgt_box = QComboBox()
        self.tgt_box.setMinimumWidth(180)
        tgt.addWidget(self.tgt_box, stretch=1)
        self.reg_btn = QPushButton("Definir região")
        self.reg_btn.setObjectName("ghost")
        self.reg_btn.clicked.connect(self._pick_region)
        self.reg_btn.setVisible(False)
        tgt.addWidget(self.reg_btn)
        right.addLayout(tgt)
        self.tgt_box.currentIndexChanged.connect(self._tgt_changed)
        self.always = Toggle("Sempre exibir controle")
        self.always.setToolTip("Mantém esta janela sempre acima das outras (mesmo durante a gravação)")
        self.always.stateChanged.connect(self._toggle_always)
        right.addWidget(self.always)
        self.show_cursor = Toggle("Mostrar cursor do mouse")
        self.show_cursor.setChecked(self.cfg.get("OPTION", "sShowCursor", fallback="1") == "1")
        right.addWidget(self.show_cursor)
        sep3 = QFrame()
        sep3.setFixedHeight(1)
        sep3.setStyleSheet(f"background: {CARD};")
        right.addWidget(sep3)
        aa = QLabel("FONTE DE ÁUDIO")
        aa.setObjectName("caps")
        right.addWidget(aa)
        self.amode_labels = {"both": "Mic + sistema", "mic": "Só mic", "sys": "Só sistema", "none": "Sem áudio"}
        avail_mini = list(("both", "mic", "sys", "none")) if HAS_LOOPBACK else ["mic", "none"]
        self.amode_keys = avail_mini
        self.amode_box = QComboBox()
        self.amode_box.addItems([self.amode_labels[m] for m in avail_mini])
        self.amode_box.currentIndexChanged.connect(self._amode_box_changed)
        right.addWidget(self.amode_box)
        self.dev_names, self.dev_ids = self._mic_devices()
        self.dev_box = QComboBox()
        self.dev_box.addItems(self.dev_names)
        self.dev_box.setToolTip("Microfone")
        right.addWidget(self.dev_box)
        mixrow = QHBoxLayout()
        self.mix_db = QLabel("-inf dB")
        self.mix_db.setObjectName("mono")
        mixrow.addWidget(QLabel("Nível mix:"))
        mixrow.addStretch(1)
        mixrow.addWidget(self.mix_db)
        right.addLayout(mixrow)
        self.mix_vu = VUMeter()
        right.addWidget(self.mix_vu)
        self.mic_db = QLabel("-inf dB")
        self.mic_db.setObjectName("mono")
        microw = QHBoxLayout()
        miclab = QLabel("Mic:")
        microw.addWidget(miclab)
        microw.addStretch(1)
        microw.addWidget(self.mic_db)
        right.addLayout(microw)
        self.mic_vu = VUMeter()
        right.addWidget(self.mic_vu)
        sysrow = QHBoxLayout()
        sysrow.addWidget(QLabel("Sistema:"))
        sysrow.addStretch(1)
        self.sys_db = QLabel("-inf dB")
        self.sys_db.setObjectName("mono")
        sysrow.addWidget(self.sys_db)
        right.addLayout(sysrow)
        self.sys_vu = VUMeter()
        right.addWidget(self.sys_vu)
        self.scope = WaveScope()
        self.scope.setMinimumSize(200, 70)
        right.addWidget(self.scope)
        _mode0 = self.cfg.get("OPTION", "sAudioMode", fallback="both")
        if _mode0 in avail_mini:
            self.amode_box.blockSignals(True)
            self.amode_box.setCurrentIndex(avail_mini.index(_mode0))
            self.amode_box.blockSignals(False)
        vv = QLabel("VÍDEO")
        vv.setObjectName("caps")
        right.addWidget(vv)
        vrow = QHBoxLayout()
        self.fps_box = QComboBox()
        self.fps_box.addItems(["10", "15", "30"])
        self.fps_box.setCurrentText(self.cfg.get("OPTION", "dwFps", fallback="15"))
        self.fps_box.setToolTip("Quadros por segundo")
        vrow.addWidget(self.fps_box, stretch=1)
        self.preset_box = QComboBox()
        self.preset_box.addItems(["Performance", "Equilibrado"])
        self.preset_box.setCurrentText(self.cfg.get("OPTION", "sPresetLabel", fallback="Equilibrado"))
        self.preset_box.setToolTip("Performance = mais FPS, arquivo maior. Equilibrado = melhor compressão.")
        vrow.addWidget(self.preset_box, stretch=1)
        right.addLayout(vrow)
        timerrow = QHBoxLayout()
        timerrow.addWidget(QLabel("Duração:"))
        timerrow.addStretch(1)
        self.timer = QLabel("00:00:00")
        self.timer.setObjectName("mono")
        timerrow.addWidget(self.timer)
        right.addLayout(timerrow)
        self.realfps = QLabel("FPS real: --")
        self.realfps.setObjectName("mono")
        right.addWidget(self.realfps)
        try:
            free = shutil.disk_usage(str(default_output_folder(self.cfg))).free / 1e9
            fl = QLabel(f"Livre: {free:.1f} GB • MP4 H.264 + AAC 44.1 kHz")
            fl.setObjectName("mono")
            fl.setWordWrap(True)
            right.addWidget(fl)
        except Exception:
            pass
        self.btn_start = QPushButton("◉ Iniciar gravação")
        self.btn_start.setObjectName("start")
        self.btn_start.clicked.connect(self.on_toggle)
        right.addWidget(self.btn_start)
        sep = QFrame()
        sep.setFixedHeight(1)
        sep.setStyleSheet(f"background: {CARD};")
        right.addWidget(sep)
        rl = QLabel("ÚLTIMA GRAVAÇÃO")
        rl.setObjectName("caps")
        right.addWidget(rl)
        self.last_name = QLabel("Nenhuma ainda")
        self.last_name.setObjectName("mono")
        self.last_name.setWordWrap(True)
        right.addWidget(self.last_name)
        lastrow = QHBoxLayout()
        self.last_play = QPushButton("▶ Reproduzir")
        self.last_play.setObjectName("ghost")
        self.last_play.clicked.connect(self._play_last)
        self.last_play.setEnabled(False)
        lastrow.addWidget(self.last_play)
        last_open = QPushButton("Abrir pasta")
        last_open.setObjectName("ghost")
        last_open.clicked.connect(self.on_open)
        lastrow.addWidget(last_open)
        lastrow.addStretch(1)
        right.addLayout(lastrow)
        right.addStretch(1)

    # ---------- painel ----------
    @staticmethod
    def _fmt_dur(sec):
        if sec is None:
            return "--"
        sec = int(sec)
        if sec >= 3600:
            return f"{sec // 3600:02d}:{(sec % 3600) // 60:02d}:{sec % 60:02d}"
        return f"{sec // 60:02d}:{sec % 60:02d}"

    @staticmethod
    def _media_duration(path):
        try:
            import av
            with av.open(str(path)) as c:
                if c.duration is not None:
                    return c.duration / 1_000_000
        except Exception:
            pass
        return None

    @staticmethod
    def _media_date(path, st_mtime):
        import re
        m = re.search(r"(\d{8})_(\d{6})", path.name)
        if m:
            return f"{m.group(1)[6:8]}/{m.group(1)[4:6]}/{m.group(1)[:4]} {m.group(2)[:2]}:{m.group(2)[2:4]}"
        return datetime.fromtimestamp(st_mtime).strftime("%d/%m/%Y %H:%M")

    def _page_dashboard(self):
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.setContentsMargins(22, 16, 22, 16)
        lay.setSpacing(12)
        t = QLabel("Painel")
        t.setObjectName("big")
        lay.addWidget(t)
        cards = QHBoxLayout()
        cards.setSpacing(12)
        self.dash_cards = {}
        for key, label in (("n", "Gravações"), ("size", "Espaço usado"),
                           ("time", "Tempo gravado"), ("free", "Livre em disco")):
            f = QFrame()
            f.setObjectName("panel")
            fl = QVBoxLayout(f)
            fl.setContentsMargins(14, 10, 14, 10)
            num = QLabel("--")
            num.setObjectName("big")
            cap = QLabel(label)
            cap.setObjectName("caps")
            fl.addWidget(num)
            fl.addWidget(cap)
            cards.addWidget(f)
            self.dash_cards[key] = num
        lay.addLayout(cards)
        self.dash_table = QTableWidget(0, 4)
        self.dash_table.setHorizontalHeaderLabels(["Arquivo", "Data", "Duração", "Tamanho"])
        self.dash_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.dash_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.dash_table.setSelectionMode(QTableWidget.SingleSelection)
        self.dash_table.verticalHeader().setVisible(False)
        self.dash_table.horizontalHeader().setStretchLastSection(True)
        self.dash_table.itemSelectionChanged.connect(
            lambda: self.dash_play_btn.setEnabled(bool(self.dash_table.selectedItems())))
        self.dash_table.doubleClicked.connect(self._dash_play_selected)
        lay.addWidget(self.dash_table, stretch=1)
        brow = QHBoxLayout()
        refresh = QPushButton("⟳ Atualizar")
        refresh.setObjectName("ghost")
        refresh.clicked.connect(self._refresh_dashboard)
        brow.addWidget(refresh)
        self.dash_play_btn = QPushButton("▶ Reproduzir")
        self.dash_play_btn.setObjectName("ghost")
        self.dash_play_btn.setEnabled(False)
        self.dash_play_btn.clicked.connect(self._dash_play_selected)
        brow.addWidget(self.dash_play_btn)
        openb = QPushButton("Abrir pasta")
        openb.setObjectName("ghost")
        openb.clicked.connect(self.on_open)
        brow.addWidget(openb)
        brow.addStretch(1)
        lay.addLayout(brow)
        self.pages.addWidget(page)

    def _refresh_dashboard(self):
        folder = default_output_folder(self.cfg)
        try:
            files = sorted(folder.glob("*.mp4"), key=lambda p: p.stat().st_mtime, reverse=True)
        except OSError:
            files = []
        total_size, total_dur, rows = 0, 0.0, []
        for p in files[:200]:
            try:
                st = p.stat()
            except OSError:
                continue
            total_size += st.st_size
            dur = self._media_duration(p)
            if dur:
                total_dur += dur
            rows.append((p, st.st_mtime, dur))
        self.dash_cards["n"].setText(str(len(files)))
        self.dash_cards["size"].setText(f"{total_size / 1e6:.1f} MB")
        mins = int(total_dur // 60)
        self.dash_cards["time"].setText(f"{mins // 60}h {mins % 60}min" if mins >= 60 else f"{mins}min")
        try:
            free = shutil.disk_usage(str(folder)).free / 1e9
            self.dash_cards["free"].setText(f"{free:.1f} GB")
        except Exception:
            self.dash_cards["free"].setText("--")
        self.dash_table.setRowCount(0)
        for p, mtime, dur in rows:
            r = self.dash_table.rowCount()
            self.dash_table.insertRow(r)
            name_item = QTableWidgetItem(p.name)
            name_item.setData(Qt.UserRole, str(p))
            self.dash_table.setItem(r, 0, name_item)
            self.dash_table.setItem(r, 1, QTableWidgetItem(self._media_date(p, mtime)))
            self.dash_table.setItem(r, 2, QTableWidgetItem(self._fmt_dur(dur)))
            try:
                size_txt = f"{p.stat().st_size / 1e6:.1f} MB"
            except OSError:
                size_txt = "--"
            self.dash_table.setItem(r, 3, QTableWidgetItem(size_txt))
        self.dash_play_btn.setEnabled(False)

    def _dash_play_selected(self):
        items = self.dash_table.selectedItems()
        if not items:
            return
        path = items[0].data(Qt.UserRole)
        try:
            os.startfile(path)
        except Exception as exc:
            print("play error:", exc)

    def _page_about(self):
        left, right = self._panel_page()
        s = QLabel("Sobre")
        s.setObjectName("big")
        left.addWidget(s)
        info = QLabel(f"GravaTrem v{APP_VERSION} — Trem de Gravar os Trem.\n"
                      "Tela/janela/região (mss) + mic (WASAPI) + sistema (loopback).\nMP4 H.264 + AAC via PyAV.")
        info.setObjectName("desc")
        info.setWordWrap(True)
        left.addWidget(info)
        left.addStretch(1)
        right.addStretch(1)

    def _banner(self, root):
        bar = QFrame()
        bar.setObjectName("bar")
        lay = QHBoxLayout(bar)
        lay.setContentsMargins(14, 7, 14, 7)
        b = QLabel("💡 Grave em 15 FPS para arquivos menores; 30 FPS para tutoriais com movimento.")
        b.setObjectName("desc")
        lay.addWidget(b)
        root.addWidget(bar)

    # ---------- alvos ----------
    def _list_monitors(self):
        with mss.MSS() as sct:
            return [(i, m) for i, m in enumerate(sct.monitors) if i > 0]

    def _list_windows(self):
        import win32gui
        wins = []

        def cb(hwnd, _):
            if not win32gui.IsWindowVisible(hwnd):
                return
            t = win32gui.GetWindowText(hwnd).strip()
            if not t:
                return
            x1, y1, x2, y2 = win32gui.GetWindowRect(hwnd)
            if x2 - x1 >= 200 and y2 - y1 >= 150:
                wins.append((hwnd, t, (x1, y1, x2, y2)))

        win32gui.EnumWindows(cb, None)
        return wins

    def _sync_cap_ui(self):
        self._paint_seg()
        titles = {"full": "Gravação de Tela - Tela Cheia",
                  "win": "Gravação de Tela - Janela",
                  "reg": "Gravação de Tela - Região Livre"}
        descs = {
            "full": "Este modo permite gravar a área total do seu monitor.\n\n1. Selecione um monitor que será capturado.\n2. Clique no botão 'Iniciar gravação' ou pressione F12.",
            "win": "Este modo permite gravar uma janela específica.\n\n1. Selecione a janela na lista.\n2. Clique no botão 'Iniciar gravação' ou pressione F12.",
            "reg": "Este modo permite gravar uma região livre.\n\n1. Escolha 'Definir região' e arraste o retângulo na tela.\n2. Clique no botão 'Iniciar gravação' ou pressione F12."}
        self.home_title.setText(titles[self.capmode])
        self.home_desc.setText(descs[self.capmode])
        self.tgt_box.blockSignals(True)
        self.tgt_box.clear()
        if self.capmode == "full":
            mons = self._list_monitors()
            self.mon_idx = [i for i, _ in mons]
            names = [f"Tela {n - self.mon_idx[0] + 1}" + (" (Principal)" if m.get("is_primary") else "")
                     for n, (i, m) in enumerate(mons)]
            self.tgt_box.addItems(names)
            want = int(self.cfg.get("OPTION", "dwMonitor", fallback="1"))
            self.tgt_box.setCurrentIndex(self.mon_idx.index(want) if want in self.mon_idx else 0)
        elif self.capmode == "win":
            self.win_items = self._list_windows()
            self.tgt_box.addItems([t[:45] for _, t, _ in self.win_items] or ["-"])
            self.tgt_box.addItem("⟳ Atualizar lista…")
        else:
            self.tgt_box.addItems(["Definir região… (clique ao lado)"])
            self._show_region()
        self.reg_btn.setVisible(self.capmode == "reg")
        self.tgt_box.blockSignals(False)
        with mss.MSS() as sct:
            ms = [m for _, m in self._list_monitors()]
        prim = next((m for m in ms if m.get("is_primary")), ms[0])
        self._res_text = f"{prim['width']}x{prim['height']}"

    def _show_region(self):
        r = getattr(self, "region", None)
        if r is None:
            rr = self.cfg.get("OPTION", "sRegion", fallback="")
            if rr:
                try:
                    l, t_, w, h = [int(x) for x in rr.split(",")]
                    self.region = {"left": l, "top": t_, "width": w, "height": h}
                except ValueError:
                    self.region = None
            else:
                self.region = None

    def _set_capmode(self, m):
        self.capmode = m
        self._sync_cap_ui()
        self._paint_seg()
        if m == "reg":
            self._pick_region()

    def _set_tab(self, i):
        self.pages.setCurrentIndex(i)
        self.tab_btns[i].setChecked(True)
        if i == 1 and hasattr(self, "dash_table"):
            self._refresh_dashboard()

    def _toggle_always(self, s):
        # trocar flag com a janela visivel exige show() de novo, senao ela some
        self.setWindowFlag(Qt.WindowStaysOnTopHint, s == 2)
        self.show()
        self.raise_()

    def _tgt_changed(self, idx):
        if self.capmode == "win" and self.tgt_box.itemText(idx) == "⟳ Atualizar lista…":
            self._sync_cap_ui()
        elif self.capmode == "reg":
            self._pick_region()

    def _pick_region(self):
        dlg = RegionPicker(self)
        if dlg.exec():
            self.region = dlg.rect
            r = self.region
            self.cfg.set("OPTION", "sRegion", f"{r['left']},{r['top']},{r['width']},{r['height']}")
            save_config(self.cfg)

    def _current_region(self):
        if self.capmode == "full":
            with mss.MSS() as sct:
                m = sct.monitors[self.mon_idx[self.tgt_box.currentIndex()]]
                return {"left": m["left"], "top": m["top"], "width": m["width"], "height": m["height"]}
        if self.capmode == "win" and getattr(self, "win_items", None) and self.tgt_box.currentIndex() < len(self.win_items):
            import win32gui
            hwnd = self.win_items[self.tgt_box.currentIndex()][0]
            x1, y1, x2, y2 = win32gui.GetWindowRect(hwnd)
            return {"left": x1, "top": y1, "width": max(64, x2 - x1), "height": max(64, y2 - y1)}
        if self.capmode == "reg":
            self._show_region()
            return getattr(self, "region", None)
        return None

    # ---------- audio ----------
    def _mic_devices(self):
        devs = [(i, d["name"]) for i, d in enumerate(sd.query_devices()) if d["max_input_channels"] > 0]
        return ([n for _, n in devs], [i for i, _ in devs])
    def _set_amode(self, m):
        self.amode = m
        if hasattr(self, "amode_box") and m in self.amode_keys:
            self.amode_box.blockSignals(True)
            self.amode_box.setCurrentIndex(self.amode_keys.index(m))
            self.amode_box.blockSignals(False)
        self._upd_dev_state()
        self._restart_monitor()

    def _amode_box_changed(self, i):
        if 0 <= i < len(self.amode_keys):
            self._set_amode(self.amode_keys[i])

    def _toggle_mic(self):
        if not self.tb_mic.isChecked():
            self._prev_amode = self.amode if self.amode in ("mic", "both") else "both"
            self._set_amode("none")
        else:
            if self.amode == "sys":
                target = "both"
            else:
                target = getattr(self, "_prev_amode", "both")
                if target == "none":
                    target = "both"
            self._set_amode(target)

    def _mic_id(self):
        if self.dev_box.currentIndex() >= 0 and self.dev_box.currentText() in self.dev_names:
            return self.dev_ids[self.dev_names.index(self.dev_box.currentText())]
        return None

    def _upd_dev_state(self):
        en = self.amode in ("mic", "both")
        self.dev_box.setEnabled(en)
        self.tb_mic.blockSignals(True)
        self.tb_mic.setChecked(en)
        self.tb_mic.blockSignals(False)
        self.tb_mic.setStyleSheet(f"background: {BLUE if en else 'transparent'}; border-radius: 8px;")

    def _restart_monitor(self):
        mic = self._mic_id() if self.amode in ("mic", "both") else None
        sys_on = self.amode in ("sys", "both")
        if self.amode == "none":
            mic, sys_on = None, False
        self.monitor.start(mic, sys_on)

    # ---------- acoes ----------
    def _on_error(self, msg):
        log.error("dialogo de erro: %s", msg)
        QMessageBox.critical(self, "GravaTrem", msg)

    def bring_front(self):
        self.show()
        self.raise_()
        self.activateWindow()

    def on_toggle(self):
        if self.stop_event is None:
            self.on_record()
        else:
            self.on_stop()

    def on_record(self):
        region = self._current_region()
        if region is None:
            self.stat.setText("● DEFINA O ALVO")
            self.stat.setStyleSheet(f"background: {CARD}; color: {RED};")
            QTimer.singleShot(1500, lambda: (self.stat.setText("● PRONTO"),
                                             self.stat.setStyleSheet(f"background: {CARD}; color: {CYAN};")))
            return
        fps = int(self.fps_box.currentText())
        preset = "ultrafast" if self.preset_box.currentText() == "Performance" else "veryfast"
        mic = self._mic_id() if self.amode in ("mic", "both") else None
        sys_on = self.amode in ("sys", "both")
        rate = int(self.cfg.get("OPTION", "dwSampleRate", fallback="44100"))
        prefix = self.t.get("text_output_prefix", "tela")
        out = default_output_folder(self.cfg) / f"{prefix}_{datetime.now():%Y%m%d_%H%M%S}.mp4"
        self.cfg.set("OPTION", "sAudioMode", self.amode)
        self.cfg.set("OPTION", "dwFps", str(fps))
        self.cfg.set("OPTION", "sPresetLabel", self.preset_box.currentText())
        self.cfg.set("OPTION", "sShowCursor", "1" if self.show_cursor.isChecked() else "0")
        self.cfg.set("OPTION", "sCapMode", self.capmode)
        if self.capmode == "full":
            self.cfg.set("OPTION", "dwMonitor", str(self.mon_idx[self.tgt_box.currentIndex()]))
        save_config(self.cfg)
        self.monitor.stop()
        self.stop_event = threading.Event()
        self.out_path = out
        self.meter = new_meter()
        self.monitor.meter = self.meter
        self._frames = 0
        self._fps_ts = time.time()
        self.thread = threading.Thread(target=self._run,
                                       args=(out, fps, rate, mic, sys_on, region,
                                             self.show_cursor.isChecked(), preset), daemon=True)
        self.thread.start()
        self.start_ts = time.time()
        self.bar.show_bar(f"{region['width']}x{region['height']}", self._target_name())
        self.btn_rec.setText("■\nSTOP")
        self.btn_start.setText("■ Parar gravação")
        self.btn_start.setObjectName("stop")
        self.btn_start.style().unpolish(self.btn_start)
        self.btn_start.style().polish(self.btn_start)
        self.stat.setText("● GRAVANDO")
        self.stat.setStyleSheet(f"background: {CARD}; color: {RED};")

    def _frame_tick(self):
        self._frames += 1

    def _target_name(self):
        if self.capmode == "full":
            return self.tgt_box.currentText()
        if self.capmode == "win":
            t = self.tgt_box.currentText()
            return t[:24] if t != "-" else "Janela"
        r = getattr(self, "region", None)
        if r:
            return f"{r['width']}x{r['height']}"
        return "Região"

    def _run(self, out, fps, rate, mic, sys_on, region, show_cursor, preset):
        try:
            log.info("gravando %s fps=%s audio(mic=%s,sys=%s) regiao=%s cursor=%s preset=%s",
                     out, fps, mic, sys_on, region, show_cursor, preset)
            record_screen(out, fps, rate, mic, sys_on, self.stop_event,
                          meter=self.meter, status_cb=self._frame_tick,
                          region=region, show_cursor=show_cursor, preset=preset)
            log.info("gravacao ok: %s", out)
        except Exception as exc:
            log.exception("falha na gravacao")
            self.error_sig.emit(f"Falha ao gravar:\n{exc}\n\nDetalhes em %APPDATA%\\GravaTrem\\logs\\gravatrem.log")

    def on_stop(self):
        if self.stop_event is not None:
            self.stop_event.set()
            self.thread.join()
            self.stop_event = None
            self.bar.hide()
            self.last_output = self.out_path
            try:
                mb = self.out_path.stat().st_size / 1e6
                self.last_name.setText(f"{self.out_path.name}\n{mb:.1f} MB")
                self.last_play.setEnabled(True)
            except Exception:
                pass
            self.btn_rec.setText("●\nREC")
            self.btn_start.setText("◉ Iniciar gravação")
            self.btn_start.setObjectName("start")
            self.btn_start.style().unpolish(self.btn_start)
            self.btn_start.style().polish(self.btn_start)
            self.stat.setText("● PRONTO")
            self.stat.setStyleSheet(f"background: {CARD}; color: {CYAN};")
            self.timer.setText("00:00:00")
            self.view.setPixmap(QPixmap())
            self.view.setText("Pronto para Capturar")
            self._restart_monitor()
            if hasattr(self, "dash_table"):
                self._refresh_dashboard()

    def _preview_tick(self):
        if self.stop_event is not None:
            return
        now = time.time()
        # se o worker anterior travou (sem emitir ha +1.5s), segue adiante mesmo assim
        if self._pv_busy and now - self._pv_last_emit < 1.5:
            return
        self._pv_busy = True
        region = self._current_region()
        vw, vh = max(320, self.view.width()), max(180, self.view.height())
        threading.Thread(target=self._grab_preview,
                         args=(region, self.show_cursor.isChecked(), vw, vh),
                         daemon=True).start()

    def _grab_preview(self, region, show_cursor, vw, vh):
        try:
            with mss.MSS() as sct:
                mon = sct.monitors[1] if not region else region
                img = sct.grab(mon)
            rgb = np.array(img)[..., :3][..., ::-1].copy()
            if show_cursor:
                from engine import get_cursor_pos, draw_cursor
                pos = get_cursor_pos()
                if pos:
                    rgb = draw_cursor(rgb, pos[0] - mon["left"], pos[1] - mon["top"])
            h, w, _ = rgb.shape
            qimg = QImage(rgb.data, w, h, 3 * w, QImage.Format_RGB888).copy()
            self.preview_ready.emit(qimg, vw, vh)
        except Exception:
            pass
        finally:
            self._pv_last_emit = time.time()
            self._pv_busy = False

    def _on_preview(self, qimg, vw, vh):
        self.view.setPixmap(QPixmap.fromImage(qimg).scaled(vw, vh, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        self.badge.setText(f"● {qimg.width()}x{qimg.height()} · {self._target_name()}")

    def screenshot(self):
        try:
            region = self._current_region() or {"left": 0, "top": 0, "width": 0, "height": 0}
            with mss.MSS() as sct:
                mon = sct.monitors[1] if region.get("width", 0) == 0 else region
                img = sct.grab(mon)
            import PIL.Image
            folder = default_output_folder(self.cfg)
            folder.mkdir(parents=True, exist_ok=True)
            p = folder / f"foto_{datetime.now():%Y%m%d_%H%M%S}.png"
            PIL.Image.fromarray(np.array(img)[..., :3][..., ::-1].copy()).save(p)
            log.info("foto salva: %s", p)
            self.stat.setText("● FOTO SALVA")
            QTimer.singleShot(1500, lambda: self.stat.setText("● GRAVANDO" if self.stop_event else "● PRONTO"))
        except Exception as exc:
            log.exception("falha na foto")
            self.error_sig.emit(f"Falha ao capturar imagem:\n{exc}")

    def _play_last(self):
        if self.last_output is not None:
            try:
                os.startfile(self.last_output)
            except Exception as exc:
                print("play error:", exc)

    def on_open(self):
        folder = default_output_folder(self.cfg)
        folder.mkdir(parents=True, exist_ok=True)
        os.startfile(folder)

    def closeEvent(self, e):
        self.monitor.stop()
        try:
            self.bar.hide()
        except Exception:
            pass
        super().closeEvent(e)

    def _poll(self):
        now = time.time()
        for key, vu, db in (("mic", self.mic_vu, self.mic_db), ("sys", self.sys_vu, self.sys_db)):
            peak, ts = self.meter.get(key, (0.0, 0.0))
            cur = self.disp[key]
            cur = peak if now - ts < 0.25 else cur * 0.75
            self.disp[key] = cur
            vu.set(cur)
            db.setText(_db(cur))
            db.setStyleSheet(f"color: {RED if cur >= 0.99 else TXT};")
        self.scope.mic_pts = list(self.meter["wave_mic"])[-140:]
        self.scope.sys_pts = list(self.meter["wave_sys"])[-140:]
        self.scope.update()
        mixed = min(1.0, self.disp["mic"] + self.disp["sys"])
        self.mix_vu.set(mixed)
        self.mix_db.setText(_db(mixed))
        self.mix_db.setStyleSheet(f"color: {RED if mixed >= 0.99 else (AMBER if mixed >= 0.7 else GREEN)};")
        if self.stop_event is not None:
            s = int(time.time() - self.start_ts)
            self.timer.setText(f"{s // 3600:02d}:{(s % 3600) // 60:02d}:{s % 60:02d}")
            self.bar.tick(s)
            if time.time() - self._fps_ts >= 1.0:
                self.realfps.setText(f"FPS real: {self._frames / (time.time() - self._fps_ts):.1f}")
                self._frames = 0
                self._fps_ts = time.time()


def main():
    log.info("=== GravaTrem v%s iniciando ===", APP_VERSION)
    app = QApplication(sys.argv)
    ico = resource_path("icon.ico")
    if ico.exists():
        app.setWindowIcon(QIcon(str(ico)))
    w = MainWindow()
    w.move(120, 80)
    w.show()
    w.raise_()
    w.activateWindow()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
