"""Tema visual inspirado no Gerenciador de Tarefas do Windows 11 (Fluent).

Segue o esquema claro/escuro do sistema e gera o QSS global. Os icones usam a
fonte "Segoe Fluent Icons" (Win11) com fallback para "Segoe MDL2 Assets" (Win10).
"""
from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFont, QGuiApplication

ICON_FONT_FAMILIES = ["Segoe Fluent Icons", "Segoe MDL2 Assets"]
TEXT_FONT_FAMILIES = ["Segoe UI Variable Text", "Segoe UI"]

# Glifos (mesmos codepoints em Segoe Fluent Icons e Segoe MDL2 Assets)
GLYPH = {
    "menu": "",
    "paste": "",
    "reset": "",
    "add": "",
    "undo": "",
    "delete": "",
    "pin": "",
    "unpin": "",
    "settings": "",
    "history": "",
    "queue": "",
    "search": "",
    "copy": "",
    "edit": "",
    "up": "",
    "down": "",
    "warning": "",
    "text": "",
    "image": "",
    "files": "",
    "back": "",
    "enqueue": "",
    "duplicate": "",
    "clear": "",
}


@dataclass(frozen=True)
class Theme:
    name: str
    bg: str            # fundo da janela
    nav: str           # fundo do menu lateral
    surface: str       # cards / paineis
    surface_hover: str
    border: str
    text: str
    muted: str
    accent: str
    accent_hover: str
    on_accent: str
    accent_subtle: str  # fundo de selecao
    danger: str
    warn: str
    kind_text: str
    kind_image: str
    kind_files: str


LIGHT = Theme(
    name="light",
    bg="#F3F3F3", nav="#EEEEEE", surface="#FFFFFF", surface_hover="#F6F6F6",
    border="#E3E3E3", text="#1B1B1B", muted="#6B6B6B",
    accent="#0067C0", accent_hover="#1975C5", on_accent="#FFFFFF",
    accent_subtle="#E3EFFA", danger="#C42B1C", warn="#9D5D00",
    kind_text="#0067C0", kind_image="#8E3FB0", kind_files="#B7791F",
)

DARK = Theme(
    name="dark",
    bg="#202020", nav="#1B1B1B", surface="#2B2B2B", surface_hover="#323232",
    border="#3C3C3C", text="#FFFFFF", muted="#A6A6A6",
    accent="#60CDFF", accent_hover="#7AD5FF", on_accent="#00263A",
    accent_subtle="#1F3A4D", danger="#FF99A4", warn="#FCE100",
    kind_text="#60CDFF", kind_image="#D6A5F0", kind_files="#F7C873",
)

_current: Theme = LIGHT


def current() -> Theme:
    return _current


def system_is_dark() -> bool:
    try:
        return QGuiApplication.styleHints().colorScheme() == Qt.ColorScheme.Dark
    except Exception:
        return False


def icon_font(px: int = 16) -> QFont:
    f = QFont()
    f.setFamilies(ICON_FONT_FAMILIES)
    f.setPixelSize(px)
    return f


def text_font(pt: float = 10.0) -> QFont:
    f = QFont()
    f.setFamilies(TEXT_FONT_FAMILIES)
    f.setPointSizeF(pt)
    return f


def qcolor(hex_color: str) -> QColor:
    return QColor(hex_color)


def _check_icon_path(t: Theme) -> str:
    """Gera (uma vez por tema) o PNG do 'visto' usado nos checkboxes marcados."""
    from PySide6.QtGui import QPainter, QPen, QPixmap
    from PySide6.QtCore import QPointF
    from . import config

    d = config.data_dir() / "assets"
    d.mkdir(parents=True, exist_ok=True)
    path = d / f"check_{t.name}.png"
    pm = QPixmap(36, 36)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    pen = QPen(QColor(t.on_accent), 4)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    p.setPen(pen)
    p.drawPolyline([QPointF(9, 19), QPointF(15, 25), QPointF(27, 11)])
    p.end()
    pm.save(str(path), "PNG")
    return path.as_posix()


def _chevron_icon_path(t: Theme) -> str:
    """PNG da setinha (v) do QComboBox."""
    from PySide6.QtGui import QPainter, QPen, QPixmap
    from PySide6.QtCore import QPointF
    from . import config

    d = config.data_dir() / "assets"
    d.mkdir(parents=True, exist_ok=True)
    path = d / f"chevron_{t.name}.png"
    pm = QPixmap(36, 36)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    pen = QPen(QColor(t.muted), 3.5)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    p.setPen(pen)
    p.drawPolyline([QPointF(9, 13), QPointF(18, 22), QPointF(27, 13)])
    p.end()
    pm.save(str(path), "PNG")
    return path.as_posix()


def build_qss(t: Theme) -> str:
    check = _check_icon_path(t)
    chevron = _chevron_icon_path(t)
    icon_fam = ", ".join(f'"{f}"' for f in ICON_FONT_FAMILIES)
    text_fam = ", ".join(f'"{f}"' for f in TEXT_FONT_FAMILIES)
    return f"""
* {{ font-family: {text_fam}; font-size: 13px; color: {t.text}; }}
QMainWindow, QDialog, QWidget#root {{ background: {t.bg}; }}
QToolTip {{ background: {t.surface}; color: {t.text}; border: 1px solid {t.border};
           padding: 4px 8px; border-radius: 6px; }}

/* ---- menu lateral ---- */
QWidget#nav {{ background: {t.nav}; border-right: 1px solid {t.border}; }}
QPushButton#navItem {{ background: transparent; border: none; border-radius: 6px;
    padding: 0; margin: 1px 6px; }}
QLabel#ico {{ font-family: {icon_fam}; font-size: 16px; }}
QPushButton#navItem:hover {{ background: {t.surface_hover}; }}
QPushButton#navItem:checked {{ background: {t.surface}; font-weight: 600; }}
QPushButton#navIcon {{ background: transparent; border: none; border-radius: 6px;
    font-family: {icon_fam}; font-size: 16px; padding: 9px; margin: 1px 6px; }}
QPushButton#navIcon:hover {{ background: {t.surface_hover}; }}

/* ---- cabecalho ---- */
QLabel#title {{ font-size: 22px; font-weight: 600; }}
QLabel#subtitle {{ color: {t.muted}; }}
QLabel#chip {{ background: {t.accent_subtle}; color: {t.accent}; border-radius: 10px;
    padding: 3px 10px; font-weight: 600; }}
QLabel#sectionTitle {{ font-weight: 600; font-size: 14px; }}
QLabel#muted {{ color: {t.muted}; }}

/* ---- botoes ---- */
QPushButton, QToolButton {{ background: {t.surface}; border: 1px solid {t.border};
    border-radius: 6px; padding: 6px 14px; }}
QPushButton:hover, QToolButton:hover {{ background: {t.surface_hover}; }}
QPushButton:pressed, QToolButton:pressed {{ background: {t.border}; }}
QPushButton:disabled, QToolButton:disabled {{ color: {t.muted}; background: {t.bg}; }}
QPushButton#primary {{ background: {t.accent}; color: {t.on_accent}; border: 1px solid {t.accent};
    font-weight: 600; }}
QPushButton#primary:hover {{ background: {t.accent_hover}; }}
QPushButton#primary:disabled {{ background: {t.border}; color: {t.muted}; border-color: {t.border}; }}
QPushButton#danger {{ color: {t.danger}; }}
QPushButton[glyph="true"] {{ font-family: {icon_fam}; font-size: 15px; padding: 6px 10px; }}

/* ---- campos ---- */
QLineEdit, QSpinBox, QKeySequenceEdit, QPlainTextEdit, QTextEdit {{
    background: {t.surface}; border: 1px solid {t.border}; border-bottom: 1px solid {t.muted};
    border-radius: 6px; padding: 6px 10px; selection-background-color: {t.accent};
    selection-color: {t.on_accent}; }}
QLineEdit:focus, QSpinBox:focus, QKeySequenceEdit:focus, QPlainTextEdit:focus {{
    border-bottom: 2px solid {t.accent}; }}

QSpinBox::up-button, QSpinBox::down-button {{ width: 0; border: none; }}

QComboBox {{ background: {t.surface}; border: 1px solid {t.border};
    border-bottom: 1px solid {t.muted}; border-radius: 6px; padding: 6px 10px; }}
QComboBox:hover {{ background: {t.surface_hover}; }}
QComboBox::drop-down {{ border: none; width: 26px; }}
QComboBox::down-arrow {{ image: url({chevron}); width: 12px; height: 12px; }}
QComboBox QAbstractItemView {{ background: {t.surface}; border: 1px solid {t.border};
    border-radius: 6px; selection-background-color: {t.accent_subtle};
    selection-color: {t.text}; outline: 0; padding: 4px; }}

QCheckBox {{ spacing: 8px; }}
QCheckBox::indicator {{ width: 18px; height: 18px; border-radius: 4px;
    border: 1px solid {t.muted}; background: {t.surface}; }}
QCheckBox::indicator:checked {{ background: {t.accent}; border-color: {t.accent};
    image: url({check}); }}
QCheckBox::indicator:hover {{ border-color: {t.accent}; }}

/* ---- lista e paineis ---- */
QListWidget {{ background: transparent; border: none; outline: none; }}
QFrame#card {{ background: {t.surface}; border: 1px solid {t.border}; border-radius: 8px; }}
QFrame#bar {{ background: {t.surface}; border-top: 1px solid {t.border}; }}

QScrollBar:vertical {{ background: transparent; width: 10px; margin: 2px; }}
QScrollBar::handle:vertical {{ background: {t.border}; border-radius: 3px; min-height: 30px; }}
QScrollBar::handle:vertical:hover {{ background: {t.muted}; }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
QScrollBar:horizontal {{ height: 0; }}

QMenu {{ background: {t.surface}; border: 1px solid {t.border}; border-radius: 8px; padding: 4px; }}
QMenu::item {{ padding: 7px 24px 7px 14px; border-radius: 4px; margin: 1px 2px; }}
QMenu::item:selected {{ background: {t.surface_hover}; }}
QMenu::item:disabled {{ color: {t.muted}; }}
QMenu::separator {{ height: 1px; background: {t.border}; margin: 4px 8px; }}

QStatusBar {{ background: {t.bg}; color: {t.muted}; }}
QStatusBar::item {{ border: none; }}
QMessageBox {{ background: {t.bg}; }}
"""


THEME_MODES = ("system", "light", "dark")
_applying = False


def apply(app, mode: str = "system") -> Theme:
    """Aplica o tema: 'system' (segue o Windows), 'light' ou 'dark'; gera o QSS global."""
    global _current, _applying
    if mode not in THEME_MODES:
        mode = "system"
    hints = None
    try:
        hints = QGuiApplication.styleHints()
    except Exception:
        pass

    # Alinha tambem o esquema do Qt (paleta de dialogos nativos). A flag evita
    # reentrada, ja que mudar o esquema dispara colorSchemeChanged.
    if hints is not None and not _applying:
        _applying = True
        try:
            wanted = {
                "system": Qt.ColorScheme.Unknown,
                "light": Qt.ColorScheme.Light,
                "dark": Qt.ColorScheme.Dark,
            }[mode]
            hints.setColorScheme(wanted)
        except Exception:
            pass  # Qt < 6.8: so' o QSS muda
        finally:
            _applying = False

    if mode == "dark":
        dark = True
    elif mode == "light":
        dark = False
    else:
        dark = system_is_dark()
    _current = DARK if dark else LIGHT
    app.setStyleSheet(build_qss(_current))
    return _current
