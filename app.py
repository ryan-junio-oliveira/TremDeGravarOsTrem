"""GravaTrem — o trem que grava os trem da sua tela (PySide6 + motor de `engine.py`).

Uso:
    python -m pip install -r requirements.txt
    python app.py
"""

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
from PySide6.QtGui import (QColor, QFontDatabase, QPainter, QPen, QImage, QPixmap, QIcon,
                           QShortcut, QKeySequence)
from PySide6.QtWidgets import (QApplication, QButtonGroup, QCheckBox, QComboBox, QDialog, QFileDialog, QFrame, QHBoxLayout,
                               QHeaderView, QLabel, QMainWindow, QMessageBox, QPlainTextEdit, QPushButton, QRubberBand,
                               QScrollArea, QSizePolicy, QStackedWidget, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget)

sys.path.insert(0, str(Path(__file__).resolve().parent))
from engine import (HAS_LOOPBACK, LiveMonitor, default_output_folder, load_lang, new_meter,
                    output_folder_configured, record_screen, resource_path, save_config)

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

# Tokens visuais e QSS: fonte única em theme.py (especificação em docs/DESIGN_SYSTEM.md).
from theme import (AMBER, AMBER_TINT, BG0, BORDER, CARD, CARD2, CYAN, DIM, GREEN,
                   INK, INK_HOVER, INPUT, MUTED, PANEL, PV_BG, RED, RED_HI, RED_TINT, SIDEBAR,
                   TRACK_OFF, TXT, VU_OFF, WHITE, QSS)

try:
    import qtawesome as qta
except ImportError:  # build sem a dependência: a UI cai para texto
    qta = None
    log.warning("qtawesome ausente; ícones FontAwesome desabilitados")


def fa_icon(name, color=None):
    """QIcon FontAwesome sólido (`fa5s.*`) com fallback para ícone vazio."""
    if qta is None:
        return QIcon()
    try:
        return qta.icon(name, color=color or TXT)
    except Exception:
        return QIcon()


def fa_label(name, color=None, size=16):
    """QLabel só-ícone (para compor linhas ícone + texto)."""
    lab = QLabel()
    lab.setStyleSheet("background: transparent; border: none;")
    lab.setFixedSize(size + 4, size + 4)
    lab.setAlignment(Qt.AlignCenter)
    try:
        if qta is not None:
            lab.setPixmap(qta.icon(name, color=color or MUTED).pixmap(size, size))
    except Exception:
        pass
    return lab


def _db(peak):
    if peak <= 0.0001:
        return "-inf dB"
    return f"{20.0 * float(np.log10(peak)):+.0f} dB"



# ---------------------------------------------------------------- widgets
class VUMeter(QWidget):
    SEGS = 28

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(10)
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
        gap = 3
        segw = (w - gap * (self.SEGS - 1)) / self.SEGS
        lit = round(self.level * self.SEGS)
        for i in range(self.SEGS):
            base = QColor(VU_OFF)
            if i < 18:
                on = QColor(GREEN)
            elif i < 24:
                on = QColor(AMBER)
            else:
                on = QColor(RED)
            p.setBrush(on if i < lit else base)
            p.setPen(Qt.NoPen)
            p.drawRoundedRect(int(i * (segw + gap)), 1, max(2, int(segw)), h - 2, 3, 3)
        x = min(w - 2, int(self.hold * w))
        p.setPen(QPen(QColor(TXT), 2))
        p.drawLine(x, 0, x, h)


class WaveScope(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(200, 64)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.mic_pts: list = []
        self.sys_pts: list = []

    def paintEvent(self, _e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(INPUT))
        p.drawRoundedRect(self.rect(), 10, 10)
        mid = self.height() / 2
        p.setPen(QPen(QColor(BORDER), 1))
        p.drawLine(8, int(mid), self.width() - 8, int(mid))
        for pts, color, sign in ((self.mic_pts, QColor(CYAN), -1), (self.sys_pts, QColor(GREEN), 1)):
            if not pts:
                continue
            p.setPen(QPen(color, 1.5))
            n = len(pts)
            step = (self.width() - 16) / max(1, 139)
            off = self.width() - 8 - step * (n - 1)
            amp = mid - 6
            for i in range(1, n):
                p.drawLine(int(off + (i - 1) * step), int(mid + sign * min(1.0, pts[i - 1]) * amp),
                           int(off + i * step), int(mid + sign * min(1.0, pts[i]) * amp))


class RegionPicker(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent, Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        from PySide6.QtGui import QGuiApplication
        union = None
        for s in QGuiApplication.screens():
            union = s.geometry() if union is None else union.united(s.geometry())
        if union is not None:
            self.setGeometry(union)
        else:
            self.setWindowState(Qt.WindowFullScreen)
        self.setStyleSheet("background: black;")
        self.setWindowOpacity(0.45)
        self.setCursor(Qt.CrossCursor)
        self.band = QRubberBand(QRubberBand.Rectangle, self)
        self.band.setStyleSheet(f"QRubberBand {{ border: 2px solid {RED}; background: rgba(240,68,82,0.12); border-radius: 4px; }}")
        self.origin = None
        self.rect = None
        self.hint = QLabel("Arraste para selecionar a região  •  ESC cancela", self)
        self.hint.setStyleSheet(f"background: {BG0}; color: {INK}; border: 1px solid {BORDER};"
                                "border-radius: 10px; padding: 10px 18px; font-weight: 700;")
        self.hint.adjustSize()
        if union is not None:
            self.hint.move(union.width() // 2 - self.hint.width() // 2, 24)
        self.hint.show()

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
    """Barrinha flutuante moderna: pill escura com timer mono + REC."""

    def __init__(self, main):
        super().__init__(None, Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.main = main
        self.setAttribute(Qt.WA_TranslucentBackground)
        outer = QHBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        pill = QFrame()
        pill.setStyleSheet(f"QFrame {{ background: {SIDEBAR}; border: 1px solid {BORDER}; border-radius: 16px; }}")
        lay = QHBoxLayout(pill)
        lay.setContentsMargins(12, 8, 12, 8)
        lay.setSpacing(10)
        self.btn_menu = self._ibtn("fa5s.bars", "Abrir janela principal")
        self.btn_menu.clicked.connect(self.main.bring_front)
        lay.addWidget(self.btn_menu)
        dot = QLabel("●")
        dot.setStyleSheet(f"color: {RED}; background: transparent; font-size: 12pt;")
        lay.addWidget(dot)
        self.lbl_res = QLabel("1440x900")
        self.lbl_res.setObjectName("mono")
        self.lbl_res.setStyleSheet(f"color: {MUTED}; background: transparent;")
        lay.addWidget(self.lbl_res)
        self.lbl_tgt = QLabel("Tela 1")
        self.lbl_tgt.setStyleSheet(f"background: {CARD}; border-radius: 6px; padding: 3px 9px; font-weight: 700;")
        lay.addWidget(self.lbl_tgt)
        self.lbl_time = QLabel("00:00:00")
        self.lbl_time.setObjectName("mono")
        self.lbl_time.setStyleSheet("background: transparent; font-size: 12pt; font-weight: 700;")
        lay.addWidget(self.lbl_time)
        self.btn_pause = self._ibtn("fa5s.pause", "Pausar / retomar")
        self.btn_pause.setEnabled(False)
        self.btn_pause.clicked.connect(self.main.on_pause_toggle)
        lay.addWidget(self.btn_pause)
        self.btn_rec = QPushButton("● REC")
        self.btn_rec.setFixedSize(86, 36)
        self.btn_rec.setStyleSheet(f"QPushButton {{ background: {TXT}; border-radius: 10px; color: white; font-weight: 800; }}"
                                   f"QPushButton:hover {{ background: {INK_HOVER}; }}"
                                   f"QPushButton:disabled {{ background: {CARD2}; color: {DIM}; }}")
        self.btn_rec.setToolTip("Gravar/Parar (F12)")
        self.btn_rec.setCursor(Qt.PointingHandCursor)
        self.btn_rec.clicked.connect(self.main.on_toggle)
        lay.addWidget(self.btn_rec)
        self.btn_shot = self._ibtn("fa5s.camera", "Foto (F11)")
        self.btn_shot.clicked.connect(self.main.screenshot)
        lay.addWidget(self.btn_shot)
        self.btn_x = self._ibtn("fa5s.times", "Parar e fechar a barra")
        self.btn_x.clicked.connect(self._on_x)
        lay.addWidget(self.btn_x)
        outer.addWidget(pill)
        self._drag = None

    def _ibtn(self, name, tip):
        b = QPushButton()
        b.setIcon(fa_icon(name, TXT))
        b.setIconSize(QSize(20, 20))
        b.setFixedSize(38, 36)
        b.setStyleSheet(f"QPushButton {{ background: {CARD}; border: 1px solid {BORDER}; border-radius: 9px; }}"
                        f"QPushButton:hover {{ background: {CARD2}; }}")
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
        self.setMinimumHeight(28)

    def paintEvent(self, _e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        on = self.isChecked()
        tw, th = 40, 22
        y = (self.height() - th) // 2
        p.setPen(Qt.NoPen)
        if on:
            p.setBrush(QColor(GREEN))
        else:
            p.setBrush(QColor(TRACK_OFF))
        p.drawRoundedRect(0, y, tw, th, th // 2, th // 2)
        kx = tw - 11 if on else 11
        p.setBrush(QColor(WHITE))
        # sombra sutil do knob
        p.setPen(Qt.NoPen)
        p.setOpacity(0.25 if self.isEnabled() else 0.15)
        p.drawEllipse(kx - 8, y + 3, 16, 16)
        p.setOpacity(1.0 if self.isEnabled() else 0.55)
        # borda do knob no tema claro (knob branco sobre trilho claro)
        p.setPen(QPen(QColor(BORDER), 1) if not on else Qt.NoPen)
        p.drawEllipse(kx - 8, y + 2, 16, 16)
        p.setPen(QColor(TXT if self.isEnabled() else DIM))
        p.drawText(tw + 12, 0, self.width() - tw - 12, self.height(),
                   Qt.AlignVCenter | Qt.AlignLeft, self.text())


class MainWindow(QMainWindow):
    AMODES = ("both", "mic", "sys", "none")
    CAPMODES = ("full", "win", "reg")
    preview_ready = Signal(QImage, int, int)
    error_sig = Signal(str)

    def __init__(self):
        super().__init__()
        self.cfg, self.t = load_lang()
        self.setWindowTitle("TremDeGravarOsTrem")
        self.resize(1180, 780)
        self.setMinimumSize(1020, 640)
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
        root = QHBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        self._sidebar(root)
        main_col = QVBoxLayout()
        main_col.setContentsMargins(0, 0, 0, 0)
        main_col.setSpacing(0)
        root.addLayout(main_col, stretch=1)
        self._topbar(main_col)
        self._pages(main_col)
        log.info("ui: paginas ok")

        QShortcut(QKeySequence("F12"), self, activated=self.on_toggle)
        QShortcut(QKeySequence("F11"), self, activated=self.screenshot)
        self.preview_ready.connect(self._on_preview)
        self.error_sig.connect(self._on_error)
        self._pv_busy = False
        self._pv_last_emit = time.time()
        self.bar = FloatBar(self)
        self.poll = QTimer(self, timeout=self._poll)
        self.poll.start(120)
        self.log_timer = QTimer(self, timeout=self._tick_logs)
        self.log_timer.start(2000)
        # primeiro frame via loop de eventos (sincrono aqui travaria a abertura se o DWM engasgar)
        QTimer.singleShot(150, self._preview_tick)
        self.pv = QTimer(self, timeout=self._preview_tick)
        self.pv.start(50)
        log.info("ui: timers ok, iniciando monitor")
        self._restart_monitor()
        log.info("ui: pronta")
        QTimer.singleShot(600, self._maybe_ask_output_folder)

    # ---------- estrutura ----------
    def _sidebar(self, root):
        side = QFrame()
        side.setObjectName("side")
        side.setFixedWidth(250)
        lay = QVBoxLayout(side)
        lay.setContentsMargins(16, 18, 16, 16)
        lay.setSpacing(8)
        # marca
        brand_row = QHBoxLayout()
        brand_row.setSpacing(10)
        ico = resource_path("icon.ico")
        if ico.exists():
            logo = QLabel()
            logo.setStyleSheet("background: transparent; border: none;")
            logo.setPixmap(QPixmap(str(ico)).scaled(36, 36, Qt.KeepAspectRatio, Qt.SmoothTransformation))
            brand_row.addWidget(logo)
        bt = QVBoxLayout()
        bt.setSpacing(0)
        bname = QLabel("TremDeGravarOsTrem")
        bname.setObjectName("brand")
        bname.setStyleSheet("background: transparent; border: none; font-size: 10.5pt;")
        bt.addWidget(bname)
        vrow = QHBoxLayout()
        vrow.setSpacing(6)
        vrow.setContentsMargins(0, 2, 0, 0)
        u = QLabel(f"v{APP_VERSION}")
        u.setObjectName("ver")
        vrow.addWidget(u)
        vrow.addStretch(1)
        bt.addLayout(vrow)
        brand_row.addLayout(bt, stretch=1)
        lay.addLayout(brand_row)
        lay.addSpacing(10)
        cap = QLabel("MENU")
        cap.setObjectName("caps")
        lay.addWidget(cap)
        self.tab_group = QButtonGroup(self, exclusive=True)
        self.tab_btns = []
        for i, (name, icon) in enumerate([("Gravar", "fa5s.video"), ("Gravações", "fa5s.film"),
                                           ("Logs", "fa5s.file-alt"), ("Sobre", "fa5s.cog")]):
            b = QPushButton(f"  {name}")
            b.setObjectName("nav")
            b.setCheckable(True)
            b.setIcon(fa_icon(icon, TXT))
            b.setIconSize(QSize(20, 20))
            b.setCursor(Qt.PointingHandCursor)
            b.clicked.connect(lambda _c, ii=i: self._set_tab(ii))
            lay.addWidget(b)
            self.tab_group.addButton(b)
            self.tab_btns.append(b)
        lay.addSpacing(6)
        # status card
        stat_card = QFrame()
        stat_card.setObjectName("card")
        sl = QVBoxLayout(stat_card)
        sl.setContentsMargins(14, 12, 14, 12)
        sl.setSpacing(6)
        sl.addWidget(self._caps_label("STATUS"))
        self.stat = QLabel("● PRONTO")
        self.stat.setObjectName("pill")
        self.stat.setStyleSheet(f"background: {CARD}; color: {CYAN};")
        sl.addWidget(self.stat)
        trow = QHBoxLayout()
        trow.setSpacing(6)
        self.side_timer = QLabel("00:00:00")
        self.side_timer.setObjectName("mono")
        self.side_timer.setStyleSheet(f"background: transparent; color: {MUTED}; font-size: 11pt; font-weight: 700;")
        trow.addWidget(self.side_timer)
        trow.addStretch(1)
        self.side_fps = QLabel("")
        self.side_fps.setObjectName("mono")
        self.side_fps.setStyleSheet(f"background: transparent; color: {DIM};")
        trow.addWidget(self.side_fps)
        sl.addLayout(trow)
        lay.addWidget(stat_card)
        lay.addStretch(1)
        tipf = QFrame()
        tipf.setObjectName("cardflat")
        tiprow = QHBoxLayout(tipf)
        tiprow.setContentsMargins(12, 10, 12, 10)
        tiprow.setSpacing(10)
        tiprow.addWidget(fa_label("fa5s.lightbulb", AMBER, 16))
        tip = QLabel("15 FPS = arquivos menores; 30 FPS = movimento suave.")
        tip.setObjectName("desc")
        tip.setWordWrap(True)
        tiprow.addWidget(tip, stretch=1)
        lay.addWidget(tipf)
        openb = QPushButton("Abrir pasta")
        openb.setObjectName("ghost")
        openb.setCursor(Qt.PointingHandCursor)
        openb.setIcon(fa_icon("fa5s.folder-open", MUTED))
        openb.setIconSize(QSize(16, 16))
        openb.clicked.connect(self.on_open)
        lay.addWidget(openb)
        root.addWidget(side)

    @staticmethod
    def _caps_label(text):
        l = QLabel(text)
        l.setObjectName("caps")
        return l

    def _toolbtn(self, lay, name, tip, checkable=False):
        b = QPushButton()
        b.setObjectName("iconbtn")
        b.setCheckable(checkable)
        b.setIcon(fa_icon(name, TXT))
        b.setIconSize(QSize(20, 20))
        b.setFixedSize(42, 40)
        b.setToolTip(tip)
        b.setCursor(Qt.PointingHandCursor)
        lay.addWidget(b)
        return b

    def _topbar(self, root):
        bar = QFrame()
        bar.setObjectName("topbar")
        bar.setFixedHeight(68)
        lay = QHBoxLayout(bar)
        lay.setContentsMargins(20, 12, 20, 12)
        lay.setSpacing(10)
        self.segwrap = QFrame()
        self.segwrap.setObjectName("segwrap")
        seg_lay = QHBoxLayout(self.segwrap)
        seg_lay.setContentsMargins(4, 4, 4, 4)
        seg_lay.setSpacing(2)
        self.seg_btns = {}
        self.seg_icons = {"full": "fa5s.desktop", "win": "fa5s.window-maximize", "reg": "fa5s.vector-square"}
        for m, label in (("full", "Tela"), ("win", "Janela"), ("reg", "Região")):
            b = QPushButton(label, checkable=True, cursor=Qt.PointingHandCursor)
            b.setObjectName("seg")
            b.setIcon(fa_icon(self.seg_icons[m], MUTED))
            b.setIconSize(QSize(13, 13))
            b.clicked.connect(lambda _c, mm=m: self._set_capmode(mm))
            seg_lay.addWidget(b)
            self.seg_btns[m] = b
        lay.addWidget(self.segwrap)
        self.topdiv = QFrame()
        self.topdiv.setObjectName("vdiv")
        self.topdiv.setFixedWidth(1)
        lay.addWidget(self.topdiv)
        lay.addStretch(1)
        self.tb_mic = QPushButton(checkable=True, cursor=Qt.PointingHandCursor)
        self.tb_mic.setObjectName("iconbtn")
        self.tb_mic.setIcon(fa_icon("fa5s.microphone", TXT))
        self.tb_mic.setIconSize(QSize(20, 20))
        self.tb_mic.setFixedSize(44, 40)
        self.tb_mic.setToolTip("Microfone ligado/desligado")
        self.tb_mic.clicked.connect(self._toggle_mic)
        lay.addWidget(self.tb_mic)
        self.btn_shot = self._toolbtn(lay, "fa5s.camera", "Capturar foto PNG (F11)")
        self.btn_shot.clicked.connect(self.screenshot)
        self.btn_go = QPushButton("REC")
        self.btn_go.setObjectName("recbtn")
        self.btn_go.setIcon(fa_icon("fa5s.circle", RED))
        self.btn_go.setIconSize(QSize(10, 10))
        self.btn_go.setFixedSize(96, 40)
        self.btn_go.setCursor(Qt.PointingHandCursor)
        self.btn_go.setToolTip("Iniciar gravação (F12)")
        self.btn_go.clicked.connect(self.on_toggle)
        lay.addWidget(self.btn_go)
        self.btn_pause = QPushButton("Pausar")
        self.btn_pause.setObjectName("ghost")
        self.btn_pause.setIcon(fa_icon("fa5s.pause", MUTED))
        self.btn_pause.setIconSize(QSize(13, 13))
        self.btn_pause.setFixedSize(108, 40)
        self.btn_pause.setCursor(Qt.PointingHandCursor)
        self.btn_pause.setToolTip("Pausar / retomar gravação")
        self.btn_pause.setEnabled(False)
        self.btn_pause.clicked.connect(self.on_pause_toggle)
        lay.addWidget(self.btn_pause)
        self.btn_stop = QPushButton("Parar")
        self.btn_stop.setObjectName("ghost")
        self.btn_stop.setIcon(fa_icon("fa5s.square", DIM))
        self.btn_stop.setIconSize(QSize(12, 12))
        self.btn_stop.setFixedSize(100, 40)
        self.btn_stop.setCursor(Qt.PointingHandCursor)
        self.btn_stop.setToolTip("Parar e salvar gravação")
        self.btn_stop.setEnabled(False)
        self.btn_stop.clicked.connect(self.on_stop)
        lay.addWidget(self.btn_stop)
        root.addWidget(bar)

    def _paint_seg(self):
        for m, b in self.seg_btns.items():
            act = (m == self.capmode)
            b.setChecked(act)
            # ícone acompanha o estado: visível no pill tinta e no fundo claro
            b.setIcon(fa_icon(self.seg_icons[m], WHITE if act else MUTED))
            b.setIconSize(QSize(13, 13))

    def _pages(self, root):
        self.pages = QStackedWidget()
        self.pages.setStyleSheet("QStackedWidget { background: transparent; }")
        root.addWidget(self.pages, stretch=1)
        self._page_home()
        self._page_dashboard()
        self._page_logs()
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

    def _card(self, title=None):
        f = QFrame()
        f.setObjectName("card")
        lay = QVBoxLayout(f)
        lay.setContentsMargins(16, 14, 16, 14)
        lay.setSpacing(10)
        if title:
            lay.addWidget(self._caps_label(title))
        return f, lay

    def _sep(self):
        s = QFrame()
        s.setObjectName("sep")
        s.setFixedHeight(1)
        return s

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
            right.setContentsMargins(0, 0, 4, 0)
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
        left, right = self._panel_page(right_fixed=308)
        self.home_title = QLabel("Pronto para gravar")
        self.home_title.setObjectName("big")
        left.addWidget(self.home_title)
        self.home_desc = QLabel("Escolha o alvo no topo, ajuste o áudio e aperte REC — F12 grava, F11 tira foto.")
        self.home_desc.setObjectName("desc")
        self.home_desc.setWordWrap(True)
        left.addWidget(self.home_desc)
        # preview card
        pv_card, pv_lay = self._card()
        self.pv_card = pv_card
        head = QHBoxLayout()
        head.setSpacing(8)
        self.live_dot = QLabel("● PREVIEW")
        self.live_dot.setObjectName("mono")
        self.live_dot.setStyleSheet(f"background: transparent; color: {GREEN}; font-weight: 800;")
        head.addWidget(self.live_dot)
        head.addStretch(1)
        self.badge = QLabel(f"● {self.mon_w}x{self.mon_h}")
        self.badge.setObjectName("mono")
        self.badge.setStyleSheet(f"background: {CARD}; border-radius: 6px; padding: 3px 10px; color: {MUTED};")
        head.addWidget(self.badge)
        pv_lay.addLayout(head)
        self.view = QLabel("Pronto para Capturar")
        self.view.setObjectName("emptypv")
        self.view.setStyleSheet(f"background: {PV_BG}; qproperty-alignment: AlignCenter; border-radius: 10px; border: 1px solid {VU_OFF};")
        self.view.setMinimumSize(420, 236)
        self.view.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        pv_lay.addWidget(self.view, stretch=1)
        foot = QHBoxLayout()
        foot.setSpacing(10)
        self.timer = QLabel("00:00:00")
        self.timer.setObjectName("timer")
        foot.addWidget(self.timer)
        foot.addStretch(1)
        self.realfps = QLabel("FPS real: --")
        self.realfps.setObjectName("mono")
        self.realfps.setStyleSheet(f"background: transparent; color: {MUTED};")
        foot.addWidget(self.realfps)
        pv_lay.addLayout(foot)
        left.addWidget(pv_card, stretch=1)

        # alvo card
        tgt_card, tgt_lay = self._card("ALVO DA GRAVAÇÃO")
        self.tgt_box = QComboBox()
        self.tgt_box.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        self.tgt_box.setMinimumContentsLength(16)
        tgt_lay.addWidget(self.tgt_box)
        self.reg_btn = QPushButton("Definir região")
        self.reg_btn.setIcon(fa_icon("fa5s.crop", MUTED))
        self.reg_btn.setIconSize(QSize(16, 16))
        self.reg_btn.setObjectName("ghost")
        self.reg_btn.clicked.connect(self._pick_region)
        self.reg_btn.setVisible(False)
        tgt_lay.addWidget(self.reg_btn)
        right.addWidget(tgt_card)
        self.tgt_box.currentIndexChanged.connect(self._tgt_changed)
        # atalhos card
        hk_card, hk_lay = self._card("ATALHOS")
        self.hk_rec = Toggle("Gravar / Parar")
        self.hk_rec.setChecked(True)
        self.hk_rec.setEnabled(False)
        hkrow1 = QHBoxLayout()
        hkrow1.addWidget(self.hk_rec, stretch=1)
        f12 = QLabel("F12")
        f12.setObjectName("hotkey")
        hkrow1.addWidget(f12)
        hk_lay.addLayout(hkrow1)
        self.hk_shot = Toggle("Capturar imagem")
        self.hk_shot.setChecked(True)
        self.hk_shot.setEnabled(False)
        hkrow2 = QHBoxLayout()
        hkrow2.addWidget(self.hk_shot, stretch=1)
        f11 = QLabel("F11")
        f11.setObjectName("hotkey")
        hkrow2.addWidget(f11)
        hk_lay.addLayout(hkrow2)
        right.addWidget(hk_card)
        vid_card, vid_lay = self._card("VÍDEO E JANELA")
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
        vid_lay.addLayout(vrow)
        self.always = Toggle("Sempre no topo")
        self.always.setToolTip("Mantém esta janela sempre acima das outras (mesmo durante a gravação)")
        self.always.stateChanged.connect(self._toggle_always)
        vid_lay.addWidget(self.always)
        self.show_cursor = Toggle("Mostrar cursor do mouse")
        self.show_cursor.setChecked(self.cfg.get("OPTION", "sShowCursor", fallback="1") == "1")
        vid_lay.addWidget(self.show_cursor)
        try:
            free = shutil.disk_usage(str(default_output_folder(self.cfg))).free / 1e9
            frow = QHBoxLayout()
            frow.setSpacing(8)
            frow.addWidget(fa_label("fa5s.hdd", MUTED, 15))
            fl = QLabel(f"Livre: {free:.1f} GB  •  MP4 H.264 + AAC 44.1 kHz")
            fl.setObjectName("mono")
            fl.setStyleSheet(f"background: transparent; color: {MUTED};")
            fl.setWordWrap(True)
            fl.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
            frow.addWidget(fl, stretch=1)
            vid_lay.addLayout(frow)
        except Exception:
            pass
        right.addWidget(vid_card)
        # audio card
        aud_card, aud_lay = self._card("FONTE DE ÁUDIO")
        self.amode_labels = {"both": "Mic + sistema", "mic": "Só mic", "sys": "Só sistema", "none": "Sem áudio"}
        self.amode_icons = {"both": "fa5s.headset", "mic": "fa5s.microphone",
                            "sys": "fa5s.volume-up", "none": "fa5s.volume-mute"}
        avail_mini = list(("both", "mic", "sys", "none")) if HAS_LOOPBACK else ["mic", "none"]
        self.amode_keys = avail_mini
        self.amode_box = QComboBox()
        for m in avail_mini:
            self.amode_box.addItem(fa_icon(self.amode_icons[m], MUTED), self.amode_labels[m])
        self.amode_box.currentIndexChanged.connect(self._amode_box_changed)
        aud_lay.addWidget(self.amode_box)
        self.dev_names, self.dev_ids = self._mic_devices()
        self.dev_box = QComboBox()
        self.dev_box.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        self.dev_box.setMinimumContentsLength(14)
        self.dev_box.addItems(self.dev_names)
        self.dev_box.setToolTip("Microfone")
        aud_lay.addWidget(self.dev_box)
        self.split_tracks = Toggle("Trilhas separadas (estilo OBS)")
        self.split_tracks.setToolTip("Grava 3 faixas AAC: mix + mic isolado + sistema isolado.\nSó vale com Mic + sistema; com uma fonte só, grava faixa única.")
        self.split_tracks.setChecked(self.cfg.get("OPTION", "sSplitTracks", fallback="0") == "1")
        aud_lay.addWidget(self.split_tracks)
        for key, title in (("mix", "Mix"), ("mic", "Mic"), ("sys", "Sistema")):
            row = QHBoxLayout()
            lab = QLabel(title)
            lab.setStyleSheet("background: transparent;")
            row.addWidget(lab)
            row.addStretch(1)
            db = QLabel("-inf dB")
            db.setObjectName("mono")
            db.setStyleSheet("background: transparent;")
            row.addWidget(db)
            aud_lay.addLayout(row)
            vu = VUMeter()
            aud_lay.addWidget(vu)
            if key == "mix":
                self.mix_db, self.mix_vu = db, vu
            elif key == "mic":
                self.mic_db, self.mic_vu = db, vu
            else:
                self.sys_db, self.sys_vu = db, vu
        self.scope = WaveScope()
        aud_lay.addWidget(self.scope)
        _mode0 = self.cfg.get("OPTION", "sAudioMode", fallback="both")
        if _mode0 in avail_mini:
            self.amode_box.blockSignals(True)
            self.amode_box.setCurrentIndex(avail_mini.index(_mode0))
            self.amode_box.blockSignals(False)
        right.addWidget(aud_card)
        # output folder card
        out_card, out_lay = self._card("PASTA DE SAÍDA")
        self.out_label = QLabel("")
        self.out_label.setObjectName("mono")
        self.out_label.setStyleSheet(f"background: {INPUT}; border: 1px solid {BORDER}; border-radius: 8px; padding: 8px 10px; color: {MUTED};")
        self.out_label.setWordWrap(True)
        # Ignored horizontal: o path longo quebra linha em vez de estourar o rail
        self.out_label.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        out_lay.addWidget(self.out_label)
        outrow = QHBoxLayout()
        choose_btn = QPushButton("Escolher…")
        choose_btn.setIcon(fa_icon("fa5s.folder-open", MUTED))
        choose_btn.setIconSize(QSize(16, 16))
        choose_btn.setObjectName("ghost")
        choose_btn.setCursor(Qt.PointingHandCursor)
        choose_btn.clicked.connect(self._choose_out_folder)
        outrow.addWidget(choose_btn, stretch=1)
        def_btn = QPushButton("Padrão")
        def_btn.setObjectName("ghost")
        def_btn.setToolTip("Voltar para Documentos\\TremDeGravarOsTrem")
        def_btn.clicked.connect(self._reset_out_folder)
        outrow.addWidget(def_btn, stretch=1)
        out_lay.addLayout(outrow)
        right.addWidget(out_card)
        self._refresh_out_label()
        # record card
        rec_card, rec_lay = self._card("GRAVAÇÃO")
        self.btn_start = QPushButton("Iniciar gravação")
        self.btn_start.setIcon(fa_icon("fa5s.circle", RED))
        self.btn_start.setIconSize(QSize(14, 14))
        self.btn_start.setObjectName("start")
        self.btn_start.setCursor(Qt.PointingHandCursor)
        self.btn_start.clicked.connect(self.on_toggle)
        rec_lay.addWidget(self.btn_start)
        rec_lay.addWidget(self._caps_label("ÚLTIMA GRAVAÇÃO"))
        self.last_name = QLabel("Nenhuma ainda")
        self.last_name.setObjectName("mono")
        self.last_name.setStyleSheet(f"background: {INPUT}; border: 1px solid {BORDER}; border-radius: 8px; padding: 8px 10px;")
        self.last_name.setWordWrap(True)
        self.last_name.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        rec_lay.addWidget(self.last_name)
        self.last_play = QPushButton("Reproduzir")
        self.last_play.setIcon(fa_icon("fa5s.play", MUTED))
        self.last_play.setIconSize(QSize(14, 14))
        self.last_play.setObjectName("ghost")
        self.last_play.clicked.connect(self._play_last)
        self.last_play.setEnabled(False)
        rec_lay.addWidget(self.last_play)
        last_open = QPushButton("Abrir pasta")
        last_open.setIcon(fa_icon("fa5s.folder-open", MUTED))
        last_open.setIconSize(QSize(16, 16))
        last_open.setObjectName("ghost")
        last_open.clicked.connect(self.on_open)
        rec_lay.addWidget(last_open)
        right.addWidget(rec_card)
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
    def _media_tracks(path):
        """Quantas faixas de áudio o MP4 tem (1 mixada ou 3 no modo multitrilha)."""
        try:
            import av
            with av.open(str(path)) as c:
                return sum(1 for s in c.streams if s.type == "audio")
        except Exception:
            return 0

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
        head = QHBoxLayout()
        t = QLabel("Gravações")
        t.setObjectName("big")
        head.addWidget(t)
        head.addStretch(1)
        sub = QLabel("Histórico, espaço e duração")
        sub.setObjectName("desc")
        head.addWidget(sub)
        lay.addLayout(head)
        cards = QHBoxLayout()
        cards.setSpacing(12)
        self.dash_cards = {}
        for key, label, ic, col in (("n", "Gravações", "fa5s.film", TXT), ("size", "Espaço usado", "fa5s.hdd", AMBER),
                                    ("time", "Tempo gravado", "fa5s.clock", CYAN), ("free", "Livre em disco", "fa5s.database", GREEN)):
            f = QFrame()
            f.setObjectName("card")
            fl = QVBoxLayout(f)
            fl.setContentsMargins(16, 12, 16, 12)
            fl.setSpacing(2)
            top = fa_label(ic, col, 20)
            fl.addWidget(top)
            num = QLabel("--")
            num.setObjectName("statcardnum")
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
        self.dash_table.setShowGrid(False)
        self.dash_table.setAlternatingRowColors(True)
        self.dash_table.verticalHeader().setVisible(False)
        self.dash_table.verticalHeader().setDefaultSectionSize(42)
        self.dash_table.verticalHeader().setMinimumSectionSize(36)
        hh = self.dash_table.horizontalHeader()
        hh.setStretchLastSection(False)
        hh.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        for c in (1, 2, 3):
            hh.setSectionResizeMode(c, QHeaderView.ResizeMode.ResizeToContents)
        self.dash_table.itemSelectionChanged.connect(
            lambda: self.dash_play_btn.setEnabled(bool(self.dash_table.selectedItems())))
        self.dash_table.doubleClicked.connect(self._dash_play_selected)
        self.dash_empty = QLabel("Nenhuma gravação ainda\nAperte REC na aba Gravar para começar",
                                 self.dash_table.viewport())
        self.dash_empty.setObjectName("desc")
        self.dash_empty.setAlignment(Qt.AlignCenter)
        self.dash_empty.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.dash_table.viewport().installEventFilter(self)
        lay.addWidget(self.dash_table, stretch=1)
        brow = QHBoxLayout()
        refresh = QPushButton("Atualizar")
        refresh.setIcon(fa_icon("fa5s.sync-alt", MUTED))
        refresh.setIconSize(QSize(14, 14))
        refresh.setObjectName("ghost")
        refresh.clicked.connect(self._refresh_dashboard)
        brow.addWidget(refresh)
        self.dash_play_btn = QPushButton("Reproduzir")
        self.dash_play_btn.setIcon(fa_icon("fa5s.play", MUTED))
        self.dash_play_btn.setIconSize(QSize(14, 14))
        self.dash_play_btn.setObjectName("ghost")
        self.dash_play_btn.setEnabled(False)
        self.dash_play_btn.clicked.connect(self._dash_play_selected)
        brow.addWidget(self.dash_play_btn)
        openb = QPushButton("Abrir pasta")
        openb.setObjectName("ghost")
        openb.setIcon(fa_icon("fa5s.folder-open", MUTED))
        openb.setIconSize(QSize(16, 16))
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
        self._layout_dash_empty()

    def _layout_dash_empty(self):
        empty = self.dash_table.rowCount() == 0
        self.dash_empty.setVisible(empty)
        if empty:
            self.dash_empty.setGeometry(self.dash_table.viewport().rect())

    def eventFilter(self, obj, ev):
        if hasattr(self, "dash_table") and obj is self.dash_table.viewport():
            if ev.type() == ev.Type.Resize:
                self._layout_dash_empty()
        return super().eventFilter(obj, ev)

    def _dash_play_selected(self):
        items = self.dash_table.selectedItems()
        if not items:
            return
        path = items[0].data(Qt.UserRole)
        try:
            os.startfile(path)
        except Exception as exc:
            print("play error:", exc)

    def _page_logs(self):
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.setContentsMargins(22, 16, 22, 16)
        lay.setSpacing(12)
        head = QHBoxLayout()
        t = QLabel("Logs")
        t.setObjectName("big")
        head.addWidget(t)
        head.addStretch(1)
        sub = QLabel("Diagnóstico da aplicação")
        sub.setObjectName("desc")
        head.addWidget(sub)
        lay.addLayout(head)
        bar = QHBoxLayout()
        bar.setSpacing(10)
        self.log_filter = QComboBox()
        self.log_filter.addItem(fa_icon("fa5s.list", MUTED), "Tudo")
        self.log_filter.addItem(fa_icon("fa5s.info-circle", CYAN), "INFO")
        self.log_filter.addItem(fa_icon("fa5s.exclamation-triangle", AMBER), "Avisos")
        self.log_filter.addItem(fa_icon("fa5s.exclamation-circle", RED), "Erros")
        self.log_filter.setMinimumWidth(150)
        self.log_filter.currentIndexChanged.connect(lambda _i: self._refresh_logs())
        bar.addWidget(self.log_filter)
        self.log_auto = Toggle("Automático")
        self.log_auto.setChecked(True)
        self.log_auto.setMinimumWidth(150)
        self.log_auto.setToolTip("Atualiza sozinho a cada 2 s enquanto esta aba está aberta")
        bar.addWidget(self.log_auto)
        bar.addStretch(1)
        refresh = QPushButton("Atualizar")
        refresh.setObjectName("ghost")
        refresh.setCursor(Qt.PointingHandCursor)
        refresh.setIcon(fa_icon("fa5s.sync-alt", MUTED))
        refresh.setIconSize(QSize(14, 14))
        refresh.clicked.connect(self._refresh_logs)
        bar.addWidget(refresh)
        openb = QPushButton("Abrir pasta")
        openb.setObjectName("ghost")
        openb.setCursor(Qt.PointingHandCursor)
        openb.setIcon(fa_icon("fa5s.folder-open", MUTED))
        openb.setIconSize(QSize(16, 16))
        openb.clicked.connect(lambda: os.startfile(str(app_log_path().parent)))
        bar.addWidget(openb)
        lay.addLayout(bar)
        self.log_view = QPlainTextEdit()
        self.log_view.setReadOnly(True)
        self.log_view.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        lay.addWidget(self.log_view, stretch=1)
        self.log_path_label = QLabel("")
        self.log_path_label.setObjectName("mono")
        self.log_path_label.setStyleSheet(f"background: transparent; color: {MUTED};")
        lay.addWidget(self.log_path_label)
        self.pages.addWidget(page)

    @staticmethod
    def _log_tail(max_lines=400):
        try:
            p = app_log_path()
            if not p.exists():
                return []
            with open(p, encoding="utf-8", errors="replace") as f:
                return f.read().splitlines()[-max_lines:]
        except OSError:
            return []

    def _refresh_logs(self):
        lines = self._log_tail()
        mode = self.log_filter.currentIndex()
        if mode == 1:
            lines = [l for l in lines if " INFO " in l]
        elif mode == 2:
            lines = [l for l in lines if "WARNING" in l]
        elif mode == 3:
            lines = [l for l in lines if "ERROR" in l or "Traceback" in l or "CRITICAL" in l]
        if lines:
            self.log_view.setPlainText("\n".join(lines))
            self.log_view.verticalScrollBar().setValue(self.log_view.verticalScrollBar().maximum())
        else:
            self.log_view.setPlainText("Log ainda vazio — grave algo ou force um erro para ver as linhas aqui.")
        try:
            p = app_log_path()
            size = f"{p.stat().st_size / 1024:.0f} KB" if p.exists() else "--"
            self.log_path_label.setText(f"{p}  •  {size}")
            self.log_path_label.setToolTip(str(p))
        except OSError:
            self.log_path_label.setText("")

    def _tick_logs(self):
        if (hasattr(self, "log_view") and self.pages.currentIndex() == 2
                and self.log_auto.isChecked()):
            self._refresh_logs()

    def _page_about(self):
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.setContentsMargins(22, 16, 22, 16)
        lay.setSpacing(12)
        s = QLabel("Sobre")
        s.setObjectName("big")
        lay.addWidget(s)
        card, cl = self._card()
        hrow = QHBoxLayout()
        hrow.setSpacing(14)
        ico = resource_path("icon.ico")
        if ico.exists():
            logo = QLabel()
            logo.setStyleSheet("background: transparent;")
            logo.setPixmap(QPixmap(str(ico)).scaled(56, 56, Qt.KeepAspectRatio, Qt.SmoothTransformation))
            hrow.addWidget(logo)
        tt = QVBoxLayout()
        tt.setSpacing(2)
        name = QLabel(f"GravaTrem v{APP_VERSION}")
        name.setObjectName("section")
        tt.addWidget(name)
        sub = QLabel("Trem de Gravar os Trem — tela, janela ou região + mic e sistema → MP4 H.264 + AAC via PyAV.")
        sub.setObjectName("desc")
        sub.setWordWrap(True)
        tt.addWidget(sub)
        hrow.addLayout(tt, stretch=1)
        cl.addLayout(hrow)
        brow = QHBoxLayout()
        gh = QPushButton("Ver código")
        gh.setObjectName("ghost")
        gh.setCursor(Qt.PointingHandCursor)
        gh.setIcon(fa_icon("fa5s.code", MUTED))
        gh.setIconSize(QSize(16, 16))
        gh.clicked.connect(lambda: __import__("webbrowser").open("https://github.com/ryan-junio-oliveira/TremDeGravarOsTrem"))
        brow.addWidget(gh)
        logs = QPushButton("Abrir logs")
        logs.setObjectName("ghost")
        logs.setIcon(fa_icon("fa5s.folder-open", MUTED))
        logs.setIconSize(QSize(16, 16))
        logs.clicked.connect(lambda: os.startfile(str(app_log_path().parent)))
        brow.addWidget(logs)
        brow.addStretch(1)
        cl.addLayout(brow)
        lay.addWidget(card)
        lay.addStretch(1)
        self.pages.addWidget(page)

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
        titles = {"full": "Pronto para gravar — Tela cheia",
                  "win": "Pronto para gravar — Janela",
                  "reg": "Pronto para gravar — Região livre"}
        descs = {
            "full": "Selecione o monitor e aperte REC ou F12.",
            "win": "Escolha a janela na lista e aperte REC ou F12.",
            "reg": "Clique em “Definir região”, arraste o retângulo e aperte REC."}
        self.home_title.setText(titles[self.capmode])
        self.home_desc.setText(descs[self.capmode])
        self.tgt_box.blockSignals(True)
        self.tgt_box.clear()
        if self.capmode == "full":
            mons = self._list_monitors()
            self.mon_idx = [i for i, _ in mons]
            names = [f"Tela {n + 1}" + (" (Principal)" if m.get("is_primary") else "")
                     for n, (i, m) in enumerate(mons)]
            self.tgt_box.addItems(names)
            want = int(self.cfg.get("OPTION", "dwMonitor", fallback="1"))
            self.tgt_box.setCurrentIndex(self.mon_idx.index(want) if want in self.mon_idx else 0)
        elif self.capmode == "win":
            self.win_items = self._list_windows()
            self.tgt_box.addItems([t[:45] for _, t, _ in self.win_items] or ["-"])
            self.tgt_box.addItem("Atualizar lista…")
            self.tgt_box.setItemIcon(self.tgt_box.count() - 1, fa_icon("fa5s.sync-alt", MUTED))
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
        # seletor de alvo só existe na Gravar (única com preview + ajustes)
        self.segwrap.setVisible(i == 0)
        self.topdiv.setVisible(i == 0)
        if i == 1 and hasattr(self, "dash_table"):
            self._refresh_dashboard()
        elif i == 2 and hasattr(self, "log_view"):
            self._refresh_logs()

    def _toggle_always(self, s):
        # trocar flag com a janela visivel exige show() de novo, senao ela some
        self.setWindowFlag(Qt.WindowStaysOnTopHint, s == 2)
        self.show()
        self.raise_()

    def _tgt_changed(self, idx):
        if self.capmode == "win" and self.tgt_box.itemText(idx) == "Atualizar lista…":
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
        if en:
            self.tb_mic.setIcon(fa_icon("fa5s.microphone", WHITE))
            self.tb_mic.setStyleSheet(f"QPushButton#iconbtn {{ background: {GREEN}; border: 1px solid {GREEN}; }}")
        else:
            self.tb_mic.setIcon(fa_icon("fa5s.microphone", TXT))
            self.tb_mic.setStyleSheet("")
        if hasattr(self, "split_tracks"):
            both = self.amode == "both"
            self.split_tracks.setEnabled(both)
            self.split_tracks.setToolTip(
                "Grava 3 faixas AAC: mix + mic isolado + sistema isolado.\nSó vale com Mic + sistema; com uma fonte só, grava faixa única."
                if both else "Trilhas separadas exigem Mic + sistema.")

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
        elif self.pause_event.is_set():
            self.on_resume()
        else:
            self.on_stop()

    def on_pause_toggle(self):
        if self.stop_event is None:
            return
        if self.pause_event.is_set():
            self.on_resume()
        else:
            self.on_pause()

    def _rec_state(self):
        if self.stop_event is None:
            return "idle"
        return "paused" if self.pause_event.is_set() else "rec"

    def _rec_elapsed(self):
        s = time.time() - self.start_ts - self._paused_total
        if self._rec_state() == "paused":
            s -= time.time() - self._pause_start
        return max(0.0, s)

    @staticmethod
    def _fmt_hms(s):
        s = int(s)
        return f"{s // 3600:02d}:{(s % 3600) // 60:02d}:{s % 60:02d}"

    def _sync_rec_ui(self):
        """Centraliza todos os visuais de estado idle/rec/paused."""
        st = self._rec_state()
        rec, paused = st == "rec", st == "paused"
        active = rec or paused
        self.btn_go.setEnabled(not active)
        self.btn_pause.setEnabled(active)
        self.btn_stop.setEnabled(active)
        self.bar.btn_pause.setEnabled(active)
        if paused:
            self.btn_pause.setText("Retomar")
            self.btn_pause.setIcon(fa_icon("fa5s.play", TXT))
            self.btn_pause.setIconSize(QSize(13, 13))
        else:
            self.btn_pause.setText("Pausar")
            self.btn_pause.setIcon(fa_icon("fa5s.pause", TXT if active else MUTED))
            self.btn_pause.setIconSize(QSize(13, 13))
        self.bar.btn_pause.setIcon(fa_icon("fa5s.play" if paused else "fa5s.pause",
                                           TXT if active else DIM))
        self.btn_stop.setIcon(fa_icon("fa5s.square", RED if active else DIM))
        self.btn_start.setText("Parar gravação" if rec else
                               ("Retomar gravação" if paused else "Iniciar gravação"))
        self.btn_start.setIcon(fa_icon("fa5s.square", WHITE) if rec else
                               (fa_icon("fa5s.play", WHITE) if paused
                                else fa_icon("fa5s.circle", RED)))
        self.btn_start.setObjectName("stop" if rec else "start")
        self.btn_start.style().unpolish(self.btn_start)
        self.btn_start.style().polish(self.btn_start)
        if rec:
            pill, pbg, dot = "● GRAVANDO", RED_TINT, RED
        elif paused:
            pill, pbg, dot = "❚❚ PAUSADO", AMBER_TINT, AMBER
        else:
            pill, pbg, dot = "● PRONTO", CARD, CYAN
        self.stat.setText(pill)
        self.stat.setStyleSheet(f"background: {pbg}; color: {dot};")
        if hasattr(self, "live_dot"):
            self.live_dot.setText(pill)
            self.live_dot.setStyleSheet(f"background: transparent; color: {dot}; font-weight: 800;")
        if hasattr(self, "pv_card"):
            if st == "idle":
                self.pv_card.setStyleSheet("")
            else:
                self.pv_card.setStyleSheet(
                    f"QFrame#card {{ background: {PANEL}; border: 1.5px solid {dot}; border-radius: 14px; }}")
        self.setWindowTitle("TremDeGravarOsTrem")

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
        self.dev_names, self.dev_ids = self._mic_devices()
        mic = self._mic_id() if self.amode in ("mic", "both") else None
        sys_on = self.amode in ("sys", "both")
        if self.amode in ("mic", "both") and not self.dev_names:
            self.error_sig.emit("Nenhum microfone encontrado.\nTroque a fonte de áudio para prosseguir.")
            return
        if self.amode in ("mic", "both") and mic is None:
            self.error_sig.emit("Microfone selecionado não está mais disponível.\nEscolha outro na lista e tente de novo.")
            self.dev_box.clear()
            self.dev_box.addItems(self.dev_names)
            return
        try:
            free_gb = shutil.disk_usage(str(default_output_folder(self.cfg))).free / 1e9
        except OSError:
            free_gb = 99.0
        if free_gb < 0.5:
            box = QMessageBox(self)
            box.setWindowTitle("Pouco espaço em disco")
            box.setText(f"Só há {free_gb * 1024:.0f} MB livres na pasta de saída.\nGravar mesmo assim?")
            go = box.addButton("Gravar mesmo assim", QMessageBox.AcceptRole)
            box.addButton("Cancelar", QMessageBox.RejectRole)
            box.exec()
            if box.clickedButton() != go:
                return
        split = self.split_tracks.isChecked() and self.amode == "both"
        rate = int(self.cfg.get("OPTION", "dwSampleRate", fallback="44100"))
        prefix = self.t.get("text_output_prefix", "tela")
        out = default_output_folder(self.cfg) / f"{prefix}_{datetime.now():%Y%m%d_%H%M%S}.mp4"
        self.cfg.set("OPTION", "sAudioMode", self.amode)
        self.cfg.set("OPTION", "dwFps", str(fps))
        self.cfg.set("OPTION", "sPresetLabel", self.preset_box.currentText())
        self.cfg.set("OPTION", "sShowCursor", "1" if self.show_cursor.isChecked() else "0")
        self.cfg.set("OPTION", "sSplitTracks", "1" if self.split_tracks.isChecked() else "0")
        self.cfg.set("OPTION", "sCapMode", self.capmode)
        if self.capmode == "full":
            self.cfg.set("OPTION", "dwMonitor", str(self.mon_idx[self.tgt_box.currentIndex()]))
        save_config(self.cfg)
        self.monitor.stop()
        self.stop_event = threading.Event()
        self.pause_event = threading.Event()
        self._paused_total = 0.0
        self._pause_start = None
        self.out_path = out
        self.meter = new_meter()
        self.monitor.meter = self.meter
        self._frames = 0
        self._fps_ts = time.time()
        self.thread = threading.Thread(target=self._run,
                                       args=(out, fps, rate, mic, sys_on, region,
                                             self.show_cursor.isChecked(), preset, split,
                                             self.pause_event, self._on_record_preview), daemon=True)
        self.thread.start()
        self.start_ts = time.time()
        self.bar.show_bar(f"{region['width']}x{region['height']}", self._target_name())
        self.segwrap.setEnabled(False)
        self._sync_rec_ui()

    def on_pause(self):
        if self.stop_event is None or self.pause_event.is_set():
            return
        self.pause_event.set()
        self._pause_start = time.time()
        self._sync_rec_ui()
        log.info("rec: pausado")

    def on_resume(self):
        if self.stop_event is None or not self.pause_event.is_set():
            return
        self.pause_event.clear()
        self._paused_total += time.time() - self._pause_start
        self._pause_start = None
        self._sync_rec_ui()
        log.info("rec: retomado")

    def _on_record_preview(self, rgb, w, h):
        """Preview ao vivo vindo do worker (conversão p/ QImage aqui, na thread)."""
        try:
            qimg = QImage(rgb.data, w, h, 3 * w, QImage.Format_RGB888).copy()
            self.preview_ready.emit(qimg, self._vw, self._vh)
        except Exception:
            pass

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

    def _run(self, out, fps, rate, mic, sys_on, region, show_cursor, preset, split,
               pause_event, preview_cb):
        try:
            log.info("gravando %s fps=%s audio(mic=%s,sys=%s,split=%s) regiao=%s cursor=%s preset=%s",
                     out, fps, mic, sys_on, split, region, show_cursor, preset)
            record_screen(out, fps, rate, mic, sys_on, self.stop_event,
                          meter=self.meter, status_cb=self._frame_tick,
                          region=region, show_cursor=show_cursor, preset=preset,
                          split_tracks=split, pause_event=pause_event,
                          preview_cb=preview_cb)
            log.info("gravacao ok: %s", out)
        except Exception as exc:
            log.exception("falha na gravacao")
            self.error_sig.emit(f"Falha ao gravar:\n{exc}\n\nDetalhes em %APPDATA%\\GravaTrem\\logs\\gravatrem.log")

    def on_stop(self):
        if self.stop_event is not None:
            self.stop_event.set()
            self.pause_event.clear()
            self.thread.join()
            self.stop_event = None
            self.bar.hide()
            self.segwrap.setEnabled(True)
            self.last_output = self.out_path
            try:
                mb = self.out_path.stat().st_size / 1e6
                ntrk = self._media_tracks(self.out_path)
                tag = f" • {ntrk} faixas" if ntrk > 1 else ""
                self.last_name.setText(f"{self.out_path.name}\n{mb:.1f} MB{tag}")
                self.last_play.setEnabled(True)
            except Exception:
                pass
            self._sync_rec_ui()
            self.stat.setText("● SALVO")
            self.stat.setStyleSheet(f"background: {CARD}; color: {GREEN};")
            QTimer.singleShot(2000, self._restore_idle_pill)
            self.setWindowTitle("TremDeGravarOsTrem")
            self.timer.setText("00:00:00")
            if hasattr(self, "side_timer"):
                self.side_timer.setText("00:00:00")
            self.view.setPixmap(QPixmap())
            self.view.setText("Pronto para Capturar")
            self._restart_monitor()
            if hasattr(self, "dash_table"):
                self._refresh_dashboard()

    def _restore_idle_pill(self):
        if self.stop_event is None:
            self.stat.setText("● PRONTO")
            self.stat.setStyleSheet(f"background: {CARD}; color: {CYAN};")

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
        pm = QPixmap.fromImage(qimg).scaled(vw, vh - 8, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        self.view.setPixmap(pm)
        self.view.setStyleSheet(f"background: {PV_BG}; qproperty-alignment: AlignCenter; border-radius: 10px;")
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

    # ---------- pasta de saida ----------
    def _refresh_out_label(self):
        folder = default_output_folder(self.cfg)
        custom = output_folder_configured(self.cfg)
        tag = "" if custom else " (padrão)"
        self.out_label.setText(f"{folder}{tag}")
        self.out_label.setToolTip(str(folder))

    def _choose_out_folder(self):
        cur = str(default_output_folder(self.cfg))
        picked = QFileDialog.getExistingDirectory(self, "Escolher pasta de saída", cur)
        if not picked:
            return
        self.cfg.set("OPTION", "sOutputFolder", picked)
        save_config(self.cfg)
        self._refresh_out_label()
        log.info("pasta de saida: %s", picked)
        if hasattr(self, "dash_table"):
            self._refresh_dashboard()

    def _reset_out_folder(self):
        self.cfg.set("OPTION", "sOutputFolder", "")
        save_config(self.cfg)
        self._refresh_out_label()
        log.info("pasta de saida: padrao")

    def _maybe_ask_output_folder(self):
        """Na primeira execução (sem pasta configurada), oferece escolher o diretório."""
        if output_folder_configured(self.cfg):
            return
        default = default_output_folder(self.cfg)
        box = QMessageBox(self)
        box.setWindowTitle("Onde salvar os vídeos?")
        box.setText(f"Os vídeos cairão em:\n{default}\n\nQuer escolher outra pasta agora?")
        choose = box.addButton("Escolher pasta…", QMessageBox.AcceptRole)
        box.addButton("Usar padrão", QMessageBox.RejectRole)
        box.exec()
        if box.clickedButton() == choose:
            self._choose_out_folder()

    def closeEvent(self, e):
        if self.stop_event is not None:
            box = QMessageBox(self)
            box.setWindowTitle("Sair durante a gravação?")
            box.setText("Há uma gravação em andamento.\nParar, salvar e sair?")
            yes = box.addButton("Parar e sair", QMessageBox.AcceptRole)
            box.addButton("Continuar gravando", QMessageBox.RejectRole)
            box.exec()
            if box.clickedButton() != yes:
                e.ignore()
                return
            self.on_stop()
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
            db.setStyleSheet(f"background: transparent; color: {RED if cur >= 0.99 else TXT};")
        self.scope.mic_pts = list(self.meter["wave_mic"])[-140:]
        self.scope.sys_pts = list(self.meter["wave_sys"])[-140:]
        self.scope.update()
        mixed = min(1.0, self.disp["mic"] + self.disp["sys"])
        self.mix_vu.set(mixed)
        self.mix_db.setText(_db(mixed))
        self.mix_db.setStyleSheet(f"background: transparent; color: {RED if mixed >= 0.99 else (AMBER if mixed >= 0.7 else GREEN)};")
        if hasattr(self, "view"):
            self._vw, self._vh = max(320, self.view.width()), max(180, self.view.height())
        if self.stop_event is not None:
            st = self._rec_state()
            s = int(self._rec_elapsed())
            txt = self._fmt_hms(s)
            self.timer.setText(txt)
            if hasattr(self, "side_timer"):
                self.side_timer.setText(txt)
            self.bar.tick(s)
            self.setWindowTitle(f"{'❚❚' if st == 'paused' else '●'} {txt} — TremDeGravarOsTrem"
                                + (" (pausado)" if st == "paused" else ""))
            if st == "paused":
                self.realfps.setText("Pausado")
                if hasattr(self, "side_fps"):
                    self.side_fps.setText("pausado")
            elif time.time() - self._fps_ts >= 1.0:
                try:
                    mb = self.out_path.stat().st_size / 1e6
                    size_txt = f" • {mb:.1f} MB"
                except OSError:
                    size_txt = ""
                fps_txt = f"FPS real: {self._frames / (time.time() - self._fps_ts):.1f}"
                self.realfps.setText(fps_txt + size_txt)
                if hasattr(self, "side_fps"):
                    self.side_fps.setText(fps_txt.replace("FPS real: ", "") + size_txt)
                self._frames = 0
                self._fps_ts = time.time()


def load_fonts():
    """Registra a Poppins empacotada (assets/fonts/); cai para Segoe UI se falhar."""
    for weight in ("Regular", "Medium", "SemiBold", "Bold"):
        try:
            QFontDatabase.addApplicationFont(str(resource_path(f"assets/fonts/Poppins-{weight}.ttf")))
        except Exception as exc:
            log.warning("fonte Poppins-%s indisponivel: %s", weight, exc)


def main():
    log.info("=== GravaTrem v%s iniciando ===", APP_VERSION)
    app = QApplication(sys.argv)
    load_fonts()
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
