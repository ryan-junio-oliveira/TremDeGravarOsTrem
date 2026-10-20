"""GravaTrem — design system como código.

Tema claro moderno (fonte única dos tokens visuais + QSS montado deles).
`app.py` importa daqui; a especificação humana está em
`docs/DESIGN_SYSTEM.md`. Em caso de divergência, vale este arquivo.

Convenções:
- Nomes em UPPER_SNAKE; todo hex aparece UMA vez neste arquivo.
- Superfícies claras para a UI; `BG0`/`PV_BG` seguem escuros porque
  tooltip, overlay de região e preview de vídeo são superfícies
  escuras por natureza (texto sobre elas usa `INK`).
- QSS é seção por componente, na mesma ordem do doc (§3).
"""

from pathlib import Path

# ---------------------------------------------------------------- 1. cor
# Superfícies (claro -> escuro)
BG = "#edf0f5"        # fundo do app (cinza-azulado claro)
SIDEBAR = "#ffffff"   # sidebar, topbar, FloatBar
PANEL = "#ffffff"     # cards grandes
CARD = "#eef1f6"      # botões/controles sobre o painel
CARD2 = "#e0e6f0"     # hover de controles / nav ativa
INPUT = "#eef1f6"     # campos, scope, caixas de texto
BORDER = "#dbe1ec"    # borda padrão
BORDER_HI = "#b9c4d6"  # borda/hover enfático
BG0 = "#10141d"       # tooltip, overlay (superfície escura)
PV_BG = "#0d1117"     # área do preview (sempre escura, como no OBS)

# Texto
TXT = "#101828"       # primário (~13:1 sobre PANEL)
INK_HOVER = "#232f45"  # hover de botões tinta
MUTED = "#5b6b82"     # secundário
DIM = "#98a2b8"       # captions, desabilitado (só texto grande/caps)
INK = "#e9edf5"       # texto sobre superfícies escuras (tooltip, overlay)
WHITE = "#ffffff"     # ícones checked / texto sobre acentos

# Acentos e status
RED = "#f04452"       # ação primária REC / gravando / erro
RED_HI = "#ff5a68"    # hover do REC (topo do gradiente)
RED_GRAD_DK = "#d92d3b"  # base do gradiente REC
RED_DK = "#c92f34"    # (legado)
RED_PRESSED = "#b91c28"
RED_TINT = "#fee2e2"  # fundo do pill "gravando" / hover do stop
AMBER_TINT = "#fef3c7"  # fundo do pill "pausado"
GREEN = "#16a34a"     # live/sucesso/mic-on (legível sobre branco)
GREEN_DK = "#15803d"
GREEN_TINT = "#dcfce7"  # reservado
BLUE = "#16a34a"      # (legado: alias de GREEN)
MINT_DK = "#15803d"   # (legado: alias de GREEN_DK)
CYAN = "#0284c7"      # info / "pronto" / forma de onda do mic
AMBER = "#b45309"     # aviso / faixa média do VU
SELECT = "#d9e7fd"    # linha selecionada na tabela
SCROLL_HI = "#b9c4d6"  # hover da alça da scrollbar
VU_OFF = "#d8dfea"    # segmento de VU apagado
TRACK_OFF = "#cbd5e1"  # trilho do toggle desligado

# ---------------------------------------------------------------- 2. tipo
FONT_UI = '"Poppins", "Segoe UI Variable", "Segoe UI", sans-serif'
FONT_MONO = '"Cascadia Code", "Consolas", monospace'
# Poppins vai empacotada em assets/fonts/ (Regular 400, Medium 500,
# SemiBold 600, Bold 700) e registrada via QFontDatabase no main().
# Escala (pt): display 22 (timer) · title 14/600 · section 10/600 ·
# body 10 · table 9.5 · pill 9/600 · caps 8/600 +1.2px tracking · micro 8.

# ---------------------------------------------------------------- 3. forma
R_SM = 8    # caixas de texto, pills pequenos
R_MD = 10   # botões, combos, toggles visuais
R_LG = 12   # cards internos, tabelas
R_XL = 14   # cards
R_PILL = 16  # FloatBar
# Espaçamento em grade 4px: 4/8/12/16/20/24. Conteúdo 22/16, rail 308px,
# sidebar 250px, topbar 68px, gaps 10–12px. Ver doc §4.

def _bundle_dir():
    """Pasta base dos assets em dev e no bundle congelado (sem puxar o engine)."""
    import sys
    return Path(getattr(sys, "_MEIPASS", str(Path(__file__).resolve().parent)))


CHEVRON = (_bundle_dir() / "assets" / "chevron-down.png").as_posix()

QSS = f"""
/* base */
QWidget {{ background: {BG}; color: {TXT}; font-family: {FONT_UI}; font-size: 10pt; }}
QMainWindow {{ background: {BG}; }}
/* shell */
QFrame#side {{ background: {SIDEBAR}; border-right: 1px solid {BORDER}; }}
QFrame#topbar {{ background: {SIDEBAR}; border-bottom: 1px solid {BORDER}; }}
/* cards */
QFrame#card {{ background: {PANEL}; border: 1px solid {BORDER}; border-radius: {R_XL}px; }}
QFrame#cardflat {{ background: {CARD}; border: 1px solid {BORDER}; border-radius: {R_LG}px; }}
/* tipografia */
QLabel#brand {{ font-size: 13pt; font-weight: 600; letter-spacing: -0.3px; }}
QLabel#brand span {{ color: {RED}; }}
QLabel#ver {{ color: {DIM}; font-size: 8pt; font-weight: 600; background: {CARD}; border-radius: 6px; padding: 2px 7px; }}
QLabel#caps {{ color: {DIM}; font-size: 8pt; font-weight: 600; letter-spacing: 1.2px; background: transparent; }}
QLabel#mono {{ font-family: {FONT_MONO}; background: transparent; }}
QLabel#desc {{ color: {MUTED}; background: transparent; }}
QLabel#big {{ font-size: 14pt; font-weight: 600; letter-spacing: -0.3px; background: transparent; }}
QLabel#section {{ font-size: 10pt; font-weight: 600; background: transparent; }}
/* navegação */
QPushButton#nav {{ background: transparent; border: none; border-radius: 10px; color: {MUTED}; padding: 10px 14px; font-weight: 600; text-align: left; }}
QPushButton#nav:hover {{ background: {CARD}; color: {TXT}; }}
QPushButton#nav:checked {{ background: {CARD2}; color: {TXT}; border: 1px solid {BORDER}; }}
/* segmento alvo */
QPushButton#seg {{ background: transparent; border: none; color: {MUTED}; padding: 6px 14px; font-weight: 600; font-size: 9.5pt; border-radius: 8px; }}
QPushButton#seg:hover {{ color: {TXT}; }}
QPushButton#seg:checked {{ background: {TXT}; color: {WHITE}; }}
QPushButton#seg:disabled {{ color: {DIM}; }}
QFrame#segwrap {{ background: {CARD}; border: 1px solid {BORDER}; border-radius: 10px; }}
QFrame#vdiv {{ background: {BORDER}; border: none; }}
/* selects e inputs */
QComboBox {{ background: {INPUT}; border: 1px solid {BORDER}; border-radius: 10px; padding: 10px 38px 10px 14px; font-weight: 500; }}
QComboBox:hover {{ border-color: {BORDER_HI}; background: {PANEL}; }}
QComboBox:focus {{ border-color: {CYAN}; background: {PANEL}; }}
QComboBox:disabled {{ color: {DIM}; }}
QComboBox::drop-down {{ subcontrol-origin: padding; subcontrol-position: center right; width: 32px; border: none; background: transparent; }}
QComboBox::down-arrow {{ image: url({CHEVRON}); width: 14px; height: 14px; }}
QComboBox QAbstractItemView {{ background: {PANEL}; color: {TXT}; border: 1px solid {BORDER}; border-radius: 10px; padding: 6px; outline: 0; selection-background-color: {SELECT}; selection-color: {TXT}; }}
QComboBox QAbstractItemView::item {{ min-height: 30px; padding: 6px 12px; border: none; border-radius: 6px; }}
QComboBox QAbstractItemView::item:hover {{ background: {CARD}; }}
QComboBox QAbstractItemView::item:selected {{ background: {SELECT}; color: {TXT}; }}
QCheckBox {{ spacing: 8px; background: transparent; }}
QLabel#hotkey {{ background: {INPUT}; border: 1px solid {BORDER}; border-bottom-width: 2px; border-radius: 7px; padding: 5px 11px; font-family: {FONT_MONO}; font-weight: 700; color: {MUTED}; }}
QLabel#hotkey:disabled {{ color: {DIM}; }}
/* ações primárias (tinta escura + dot vermelho, sem vermelhão) */
QPushButton#start {{ background: {TXT};
    color: white; border: none; border-radius: {R_LG}px; padding: 13px; font-size: 11pt; font-weight: 600; }}
QPushButton#start:hover {{ background: {INK_HOVER}; }}
QPushButton#start:pressed {{ background: {BG0}; }}
QPushButton#stop {{ background: {CARD2}; color: {TXT}; border: 1.5px solid {RED}; border-radius: {R_LG}px;
    padding: 14px; font-size: 11pt; font-weight: 600; }}
QPushButton#stop:hover {{ background: {RED_TINT}; }}
QPushButton#ghost {{ background: {CARD}; color: {MUTED}; border: 1px solid {BORDER}; border-radius: 9px; padding: 8px 14px; font-weight: 500; }}
QPushButton#ghost:hover {{ color: {TXT}; background: {CARD2}; border-color: {BORDER_HI}; }}
QPushButton#ghost:pressed {{ background: {BORDER}; }}
QPushButton#ghost:disabled {{ color: {DIM}; }}
QPushButton#recbtn {{ background: {TXT};
    color: white; border: none; border-radius: 11px; font-size: 10.5pt; font-weight: 600; padding: 9px 18px; }}
QPushButton#recbtn:hover {{ background: {INK_HOVER}; }}
QPushButton#recbtn:pressed {{ background: {BG0}; }}
QPushButton#recbtn:disabled {{ background: {CARD2}; color: {DIM}; }}
QPushButton#iconbtn {{ background: {CARD}; border: 1px solid {BORDER}; border-radius: {R_MD}px; color: {TXT}; }}
QPushButton#iconbtn:hover {{ background: {CARD2}; border-color: {BORDER_HI}; }}
QPushButton#iconbtn:checked {{ background: {GREEN}; border-color: {GREEN}; }}
/* indicadores */
QLabel#pill {{ border-radius: 8px; padding: 5px 12px; font-weight: 600; font-size: 9pt; }}
QLabel#timer {{ font-family: {FONT_MONO}; font-size: 22pt; font-weight: 700; background: transparent; }}
QLabel#statcardnum {{ font-size: 16pt; font-weight: 600; background: transparent; }}
/* tabela */
QTableWidget {{ background: {PANEL}; border: 1px solid {BORDER}; border-radius: {R_LG}px; gridline-color: {BORDER}; alternate-background-color: {CARD}; color: {TXT}; font-size: 9.5pt; outline: 0; }}
QTableWidget::item {{ padding: 8px 10px; border: none; }}
QTableWidget::item:hover {{ background: {BORDER}; }}
QTableWidget::item:selected {{ background: {SELECT}; color: {TXT}; }}
QTableWidget::item:selected:hover {{ background: {SELECT}; }}
QHeaderView::section {{ background: transparent; color: {DIM}; border: none; border-bottom: 1px solid {BORDER}; padding: 10px 8px; font-weight: 600; font-size: 8.5pt; }}
QTableCornerButton::section {{ background: {PANEL}; border: none; }}
/* log viewer */
QPlainTextEdit {{ background: {INPUT}; color: {TXT}; border: 1px solid {BORDER}; border-radius: {R_LG}px; padding: 10px 12px; font-family: {FONT_MONO}; font-size: 9pt; selection-background-color: {SELECT}; selection-color: {TXT}; }}
QPlainTextEdit:focus {{ border-color: {CYAN}; }}
/* overlays e misc */
QScrollArea {{ border: none; background: transparent; }}
QScrollBar:vertical {{ background: transparent; width: 10px; margin: 4px; }}
QToolTip {{ background: {BG0}; color: {INK}; border: 1px solid {BG0}; padding: 6px 10px; border-radius: 6px; }}
QScrollBar::handle:vertical {{ background: {BORDER}; border-radius: 5px; min-height: 30px; }}
QScrollBar::handle:vertical:hover {{ background: {SCROLL_HI}; }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
QFrame#sep {{ background: {BORDER}; }}
QLabel#emptypv {{ background: transparent; color: {DIM}; font-size: 10pt; }}
"""
