"""Janela principal no estilo do Gerenciador de Tarefas do Windows 11.

Menu lateral (Fila / Historico / Configuracoes), lista em cards com arrastar
para reordenar, painel de detalhes e menu de contexto.
"""
from __future__ import annotations

import time
from typing import Optional

from PySide6.QtCore import QRectF, QSize, Qt, Signal
from PySide6.QtGui import (
    QColor,
    QFontMetrics,
    QIcon,
    QKeySequence,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
    QShortcut,
)
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QButtonGroup,
    QCheckBox,
    QFrame,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QStackedWidget,
    QStyle,
    QStyledItemDelegate,
    QVBoxLayout,
    QWidget,
)

from . import config, theme
from .models import ClipItem, ItemKind
from .settings_dialog import SettingsDialog
from .store import ClipStore

ID_ROLE = Qt.ItemDataRole.UserRole
ROLE = int(Qt.ItemDataRole.UserRole) + 1  # dict com os dados de exibicao
NAV_WIDE = 200
NAV_NARROW = 54


# ============================================================================
# Icones por glifo (Segoe Fluent Icons)
# ============================================================================
def glyph_icon(name: str, color: str, px: int = 16) -> QIcon:
    dpr = 2
    pm = QPixmap(px * dpr, px * dpr)
    pm.setDevicePixelRatio(dpr)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.TextAntialiasing)
    p.setFont(theme.icon_font(px))
    p.setPen(QColor(color))
    p.drawText(QRectF(0, 0, px, px), Qt.AlignmentFlag.AlignCenter, theme.GLYPH[name])
    p.end()
    return QIcon(pm)


# ============================================================================
# Delegate: cada item da lista e' um "card"
# ============================================================================
class ItemDelegate(QStyledItemDelegate):
    HEIGHT = 68

    def sizeHint(self, option, index):  # noqa: N802
        return QSize(option.rect.width(), self.HEIGHT)

    def paint(self, p: QPainter, option, index) -> None:  # noqa: N802
        d = index.data(ROLE)
        if not d:
            return
        t = theme.current()
        p.save()
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.TextAntialiasing)

        r = QRectF(option.rect.adjusted(2, 3, -2, -3))
        selected = bool(option.state & QStyle.StateFlag.State_Selected)
        hover = bool(option.state & QStyle.StateFlag.State_MouseOver)
        fill = t.accent_subtle if selected else (t.surface_hover if hover else t.surface)
        is_next = bool(d.get("next"))
        p.setBrush(QColor(fill))
        p.setPen(QPen(QColor(t.accent if is_next else t.border), 1.5 if is_next else 1))
        p.drawRoundedRect(r, 8, 8)

        if is_next:  # barra de destaque na esquerda
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(t.accent))
            p.drawRoundedRect(QRectF(r.left() + 1, r.top() + 14, 3, r.height() - 28), 1.5, 1.5)

        x = r.left() + 10
        if d.get("index") is not None:
            f = theme.text_font(10)
            f.setBold(is_next)
            p.setFont(f)
            p.setPen(QColor(t.accent if is_next else t.muted))
            p.drawText(QRectF(x, r.top(), 30, r.height()), Qt.AlignmentFlag.AlignCenter, str(d["index"]))
            x += 36

        # tile do tipo (ou miniatura da imagem)
        tile = QRectF(x, r.center().y() - 20, 40, 40)
        kind = d.get("kind", "text")
        kcolor = {"text": t.kind_text, "image": t.kind_image, "files": t.kind_files}.get(kind, t.muted)
        thumb: Optional[QPixmap] = d.get("thumb")
        if thumb is not None and not thumb.isNull():
            path = QPainterPath()
            path.addRoundedRect(tile, 8, 8)
            p.setClipPath(path)
            p.drawPixmap(
                int(tile.x() + (tile.width() - thumb.width()) / 2),
                int(tile.y() + (tile.height() - thumb.height()) / 2),
                thumb,
            )
            p.setClipping(False)
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.setPen(QPen(QColor(t.border), 1))
            p.drawRoundedRect(tile, 8, 8)
        else:
            c = QColor(kcolor)
            c.setAlpha(40)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(c)
            p.drawRoundedRect(tile, 8, 8)
            p.setFont(theme.icon_font(18))
            p.setPen(QColor(kcolor))
            p.drawText(tile, Qt.AlignmentFlag.AlignCenter, theme.GLYPH.get(kind, theme.GLYPH["text"]))
        x = tile.right() + 12

        # elementos da direita (desenhados da direita para a esquerda)
        right = r.right() - 12

        def draw_glyph(name: str, color: str) -> None:
            nonlocal right
            p.setFont(theme.icon_font(14))
            p.setPen(QColor(color))
            p.drawText(QRectF(right - 18, r.top(), 18, r.height()), Qt.AlignmentFlag.AlignCenter, theme.GLYPH[name])
            right -= 24

        if d.get("pinned"):
            draw_glyph("pin", t.accent)
        if d.get("missing"):
            draw_glyph("warning", t.warn)
        if is_next:
            txt = "PRÓXIMO"
            f = theme.text_font(8)
            f.setBold(True)
            w = QFontMetrics(f).horizontalAdvance(txt) + 18
            chip = QRectF(right - w, r.center().y() - 10, w, 20)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(t.accent))
            p.drawRoundedRect(chip, 10, 10)
            p.setFont(f)
            p.setPen(QColor(t.on_accent))
            p.drawText(chip, Qt.AlignmentFlag.AlignCenter, txt)
            right -= w + 8

        width = max(40.0, right - x)
        f1 = theme.text_font(10)
        f1.setBold(is_next)
        p.setFont(f1)
        p.setPen(QColor(t.text))
        text1 = QFontMetrics(f1).elidedText(d.get("preview") or "(vazio)", Qt.TextElideMode.ElideRight, int(width))
        p.drawText(QRectF(x, r.top() + 11, width, 22), Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, text1)

        f2 = theme.text_font(8.5)
        p.setFont(f2)
        p.setPen(QColor(t.warn if d.get("missing") else t.muted))
        text2 = QFontMetrics(f2).elidedText(d.get("sub", ""), Qt.TextElideMode.ElideRight, int(width))
        p.drawText(QRectF(x, r.top() + 35, width, 20), Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, text2)
        p.restore()


class ReorderList(QListWidget):
    """Lista com reordenacao por arrastar que avisa ao soltar."""

    reordered = Signal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setItemDelegate(ItemDelegate(self))
        self.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        self.setDefaultDropAction(Qt.DropAction.MoveAction)
        self.setDropIndicatorShown(True)
        self.setMouseTracking(True)
        self.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)

    def dropEvent(self, e) -> None:  # noqa: N802
        super().dropEvent(e)
        self.reordered.emit()


# ============================================================================
# Painel de detalhes
# ============================================================================
class DetailPanel(QFrame):
    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("card")
        self.setMinimumWidth(300)
        self.setMaximumWidth(380)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(16, 14, 16, 14)
        lay.setSpacing(8)

        self.title = QLabel("Detalhes")
        self.title.setObjectName("sectionTitle")
        self.meta = QLabel("")
        self.meta.setObjectName("muted")
        self.meta.setWordWrap(True)

        self.stack = QStackedWidget()
        self.text = QPlainTextEdit()
        self.text.setReadOnly(True)
        self.image = QLabel()
        self.image.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignHCenter)
        self.empty = QLabel("Selecione um item para ver os detalhes.")
        self.empty.setObjectName("muted")
        self.empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty.setWordWrap(True)
        for w in (self.empty, self.text, self.image):
            self.stack.addWidget(w)

        lay.addWidget(self.title)
        lay.addWidget(self.meta)
        lay.addWidget(self.stack, 1)
        self._pix: Optional[QPixmap] = None
        self.show_item(None, "", [])

    def show_item(self, item: Optional[ClipItem], meta: str, missing: list) -> None:
        self._pix = None
        if item is None:
            self.title.setText("Detalhes")
            self.meta.setText("")
            self.stack.setCurrentWidget(self.empty)
            return
        self.meta.setText(meta)
        if item.kind == ItemKind.TEXT:
            self.title.setText("Texto")
            self.text.setPlainText((item.text or "")[:20000])
            self.stack.setCurrentWidget(self.text)
        elif item.kind == ItemKind.IMAGE:
            self.title.setText("Imagem")
            pm = QPixmap(str(config.blobs_dir() / (item.image_file or "")))
            if pm.isNull():
                self.empty.setText("Imagem não encontrada no disco.")
                self.stack.setCurrentWidget(self.empty)
            else:
                self._pix = pm
                self._rescale()
                self.stack.setCurrentWidget(self.image)
        else:
            self.title.setText("Arquivos")
            miss = set(missing)
            lines = [("⚠ " if p in miss else "") + p for p in item.files]
            self.text.setPlainText("\n".join(lines))
            self.stack.setCurrentWidget(self.text)

    def _rescale(self) -> None:
        if self._pix is None:
            return
        size = self.stack.size()
        self.image.setPixmap(
            self._pix.scaled(
                max(40, size.width() - 4),
                max(40, size.height() - 4),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        )

    def resizeEvent(self, e) -> None:  # noqa: N802
        super().resizeEvent(e)
        self._rescale()


# ============================================================================
# Botao do menu lateral
# ============================================================================
class NavButton(QPushButton):
    def __init__(self, glyph: str, text: str, checkable: bool = True) -> None:
        super().__init__()
        self.setObjectName("navItem")
        self.setCheckable(checkable)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedHeight(40)
        self._text = text
        lay = QHBoxLayout(self)
        lay.setContentsMargins(11, 0, 11, 0)
        lay.setSpacing(12)
        self.ico = QLabel(theme.GLYPH[glyph])
        self.ico.setObjectName("ico")
        self.ico.setFixedWidth(20)
        self.ico.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl = QLabel(text)
        for w in (self.ico, self.lbl):
            w.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        lay.addWidget(self.ico)
        lay.addWidget(self.lbl, 1)

    def set_collapsed(self, collapsed: bool) -> None:
        self.lbl.setVisible(not collapsed)
        self.setToolTip(self._text if collapsed else "")


# ============================================================================
# Janela principal
# ============================================================================
class MainWindow(QMainWindow):
    PAGE_QUEUE = 0
    PAGE_HISTORY = 1

    def __init__(self, store: ClipStore, engine) -> None:
        super().__init__()
        self.store = store
        self.engine = engine
        self._tray = None
        self._has_tray = False
        self._hotkeys = None
        self._really_quit = False
        self._rebuilding = False
        self._thumbs: dict[str, QPixmap] = {}
        self._icon_buttons: list[tuple[QPushButton, str, str]] = []
        self._nav_collapsed = False
        self.setWindowTitle(f"{config.APP_DISPLAY_NAME}")
        self.resize(1020, 700)
        self.setMinimumSize(900, 540)
        self._build_ui()
        self._wire()
        self.retheme()
        self.refresh()
        self.refresh_history()
        self._switch_page(self.PAGE_QUEUE)

    # ------------------------------------------------------------ helpers UI
    def _icon_btn(self, name: str, tip: str = "", text: str = "", role: str = "text",
                  object_name: str = "") -> QPushButton:
        b = QPushButton(text)
        if tip:
            b.setToolTip(tip)
        if object_name:
            b.setObjectName(object_name)
        b.setCursor(Qt.CursorShape.PointingHandCursor)
        b.setIconSize(QSize(16, 16))
        if text:  # garante largura para icone + texto + padding do QSS
            b.setMinimumWidth(max(96, 6 * len(text) + 52))
        else:     # so' icone: botao quadrado e compacto
            b.setFixedWidth(40)
        self._icon_buttons.append((b, name, role))
        return b

    def retheme(self) -> None:
        """Refaz os icones nas cores do tema atual e repinta as listas."""
        t = theme.current()
        for b, name, role in self._icon_buttons:
            color = t.on_accent if role == "on_accent" else (t.danger if role == "danger" else t.text)
            b.setIcon(glyph_icon(name, color))
        self.btn_menu.setIcon(glyph_icon("menu", t.text))
        for lst in (self.q_list, self.h_list):
            lst.viewport().update()

    # --------------------------------------------------------------- montagem
    def _build_ui(self) -> None:
        root = QWidget()
        root.setObjectName("root")
        h = QHBoxLayout(root)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(0)

        # ---- menu lateral ----
        self.nav = QWidget()
        self.nav.setObjectName("nav")
        self.nav.setFixedWidth(NAV_WIDE)
        nl = QVBoxLayout(self.nav)
        nl.setContentsMargins(0, 8, 0, 8)
        nl.setSpacing(2)
        self.btn_menu = QPushButton()
        self.btn_menu.setObjectName("navIcon")
        self.btn_menu.setIconSize(QSize(16, 16))
        self.btn_menu.setFixedHeight(40)
        self.btn_menu.setToolTip("Expandir / recolher menu")
        self.btn_menu.setCursor(Qt.CursorShape.PointingHandCursor)
        nl.addWidget(self.btn_menu)
        nl.addSpacing(6)
        self.nav_queue = NavButton("queue", "Fila")
        self.nav_history = NavButton("history", "Histórico")
        self.nav_settings = NavButton("settings", "Configurações", checkable=False)
        group = QButtonGroup(self)
        group.setExclusive(True)
        for b in (self.nav_queue, self.nav_history):
            group.addButton(b)
            nl.addWidget(b)
        nl.addStretch(1)
        nl.addWidget(self.nav_settings)
        self._nav_buttons = (self.nav_queue, self.nav_history, self.nav_settings)
        h.addWidget(self.nav)

        # ---- conteudo ----
        content = QWidget()
        cl = QVBoxLayout(content)
        cl.setContentsMargins(24, 18, 24, 10)
        cl.setSpacing(10)

        head = QHBoxLayout()
        head.setSpacing(12)
        self.lbl_title = QLabel("Fila de colagem")
        self.lbl_title.setObjectName("title")
        self.chip = QLabel("")
        self.chip.setObjectName("chip")
        head.addWidget(self.lbl_title)
        head.addWidget(self.chip)
        head.addStretch(1)
        self.search = QLineEdit()
        self.search.setPlaceholderText("Filtrar itens…")
        self.search.setClearButtonEnabled(True)
        self.search.setFixedWidth(260)
        head.addWidget(self.search)
        cl.addLayout(head)

        self.info = QLabel(self._hotkey_hint_text())
        self.info.setObjectName("subtitle")
        self.info.setWordWrap(True)
        cl.addWidget(self.info)

        self.pages = QStackedWidget()
        self.pages.addWidget(self._build_queue_page())
        self.pages.addWidget(self._build_history_page())
        cl.addWidget(self.pages, 1)
        h.addWidget(content, 1)

        self.setCentralWidget(root)
        self.lbl_status = QLabel()
        self.statusBar().addPermanentWidget(self.lbl_status)
        self.statusBar().setSizeGripEnabled(False)

    def _build_list_and_detail(self):
        lst = ReorderList()
        detail = DetailPanel()
        row = QHBoxLayout()
        row.setSpacing(12)
        row.addWidget(lst, 1)
        row.addWidget(detail)
        return lst, detail, row

    def _build_queue_page(self) -> QWidget:
        page = QWidget()
        v = QVBoxLayout(page)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(10)

        bar = QHBoxLayout()
        bar.setSpacing(8)
        self.btn_paste = self._icon_btn("paste", "Cola o próximo item da fila", "Colar próximo",
                                        role="on_accent", object_name="primary")
        self.btn_reset = self._icon_btn("reset", "Volta ao primeiro item", "Reiniciar")
        self.btn_push = self._icon_btn("add", "Adiciona o conteúdo atual do clipboard", "Capturar agora")
        for b in (self.btn_paste, self.btn_reset, self.btn_push):
            bar.addWidget(b)
        bar.addStretch(1)
        self.btn_up = self._icon_btn("up", "Subir (Ctrl+↑)")
        self.btn_down = self._icon_btn("down", "Descer (Ctrl+↓)")
        self.btn_pin = self._icon_btn("pin", "Fixar / desafixar")
        self.btn_remove = self._icon_btn("delete", "Remover (Del)")
        self.btn_clear = self._icon_btn("clear", "Limpar tudo, exceto fixados (Ctrl+Z desfaz)")
        self.btn_undo = self._icon_btn("undo", "Desfazer a última remoção (Ctrl+Z)")
        for b in (self.btn_up, self.btn_down, self.btn_pin, self.btn_remove, self.btn_clear, self.btn_undo):
            bar.addWidget(b)
        v.addLayout(bar)

        self.q_list, self.q_detail, row = self._build_list_and_detail()
        v.addLayout(row, 1)

        opts = QHBoxLayout()
        opts.setSpacing(20)
        self.chk_auto = QCheckBox("Auto-captura (todo Ctrl+C)")
        self.chk_consume = QCheckBox("Remover ao colar")
        self.chk_loop = QCheckBox("Repetir em loop")
        for c in (self.chk_auto, self.chk_consume, self.chk_loop):
            opts.addWidget(c)
        opts.addStretch(1)
        hint = QLabel("Arraste para reordenar")
        hint.setObjectName("muted")
        opts.addWidget(hint)
        v.addLayout(opts)
        return page

    def _build_history_page(self) -> QWidget:
        page = QWidget()
        v = QVBoxLayout(page)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(10)
        bar = QHBoxLayout()
        bar.setSpacing(8)
        self.btn_enqueue = self._icon_btn("add", "Copia os itens selecionados para o fim da fila",
                                          "Adicionar à fila", role="on_accent", object_name="primary")
        self.btn_copy_h = self._icon_btn("copy", "Coloca o item no clipboard", "Copiar")
        bar.addWidget(self.btn_enqueue)
        bar.addWidget(self.btn_copy_h)
        bar.addStretch(1)
        self.btn_remove_h = self._icon_btn("delete", "Remover do histórico (Del)")
        self.btn_clear_h = self._icon_btn("delete", "Limpar o histórico", "Limpar histórico")
        bar.addWidget(self.btn_remove_h)
        bar.addWidget(self.btn_clear_h)
        v.addLayout(bar)

        self.h_list, self.h_detail, row = self._build_list_and_detail()
        self.h_list.setDragDropMode(QAbstractItemView.DragDropMode.NoDragDrop)
        v.addLayout(row, 1)
        hint = QLabel("Tudo o que você copia fica aqui (últimos itens). Duplo clique adiciona à fila.")
        hint.setObjectName("muted")
        v.addWidget(hint)
        return page

    # ----------------------------------------------------------------- sinais
    def _wire(self) -> None:
        self.btn_menu.clicked.connect(self._toggle_nav)
        self.nav_queue.clicked.connect(lambda: self._switch_page(self.PAGE_QUEUE))
        self.nav_history.clicked.connect(lambda: self._switch_page(self.PAGE_HISTORY))
        self.nav_settings.clicked.connect(self._open_settings)

        self.btn_paste.clicked.connect(lambda: self.engine.paste_next())
        self.btn_reset.clicked.connect(self.store.reset_cursor)
        self.btn_push.clicked.connect(self.engine.push_current)
        self.btn_up.clicked.connect(lambda: self._move(-1))
        self.btn_down.clicked.connect(lambda: self._move(1))
        self.btn_pin.clicked.connect(self._toggle_pin)
        self.btn_remove.clicked.connect(self._remove_selected)
        self.btn_clear.clicked.connect(self._clear_all)
        self.btn_undo.clicked.connect(self._undo)

        self.chk_auto.toggled.connect(lambda v: self._set_setting("auto_capture", v))
        self.chk_consume.toggled.connect(lambda v: self._set_setting("consume_on_paste", v))
        self.chk_loop.toggled.connect(lambda v: self._set_setting("loop", v))

        self.search.textChanged.connect(self._apply_filter)

        self.q_list.reordered.connect(self._on_reordered)
        self.q_list.itemDoubleClicked.connect(self._on_double_click)
        self.q_list.itemSelectionChanged.connect(self._update_queue_detail)
        self.q_list.customContextMenuRequested.connect(self._queue_menu)

        self.btn_enqueue.clicked.connect(self._enqueue_selected_history)
        self.btn_copy_h.clicked.connect(self._copy_selected_history)
        self.btn_remove_h.clicked.connect(self._remove_selected_history)
        self.btn_clear_h.clicked.connect(self._clear_history)
        self.h_list.itemDoubleClicked.connect(lambda _i: self._enqueue_selected_history())
        self.h_list.itemSelectionChanged.connect(self._update_history_detail)
        self.h_list.customContextMenuRequested.connect(self._history_menu)

        self.store.changed.connect(self.refresh)
        self.store.cursor_changed.connect(self._on_cursor_changed)
        self.store.history_changed.connect(self.refresh_history)
        self.engine.status.connect(self._on_status)

        QShortcut(QKeySequence.StandardKey.Delete, self.q_list, activated=self._remove_selected)
        QShortcut(QKeySequence.StandardKey.Delete, self.h_list, activated=self._remove_selected_history)
        QShortcut(QKeySequence("Ctrl+Up"), self.q_list, activated=lambda: self._move(-1))
        QShortcut(QKeySequence("Ctrl+Down"), self.q_list, activated=lambda: self._move(1))
        QShortcut(QKeySequence.StandardKey.Undo, self, activated=self._undo_shortcut)
        QShortcut(QKeySequence("Ctrl+F"), self, activated=lambda: self.search.setFocus())

    # ----------------------------------------------------------- navegacao
    def _toggle_nav(self) -> None:
        self._nav_collapsed = not self._nav_collapsed
        self.nav.setFixedWidth(NAV_NARROW if self._nav_collapsed else NAV_WIDE)
        for b in self._nav_buttons:
            b.set_collapsed(self._nav_collapsed)

    def _switch_page(self, page: int) -> None:
        self.pages.setCurrentIndex(page)
        (self.nav_queue if page == self.PAGE_QUEUE else self.nav_history).setChecked(True)
        self.lbl_title.setText("Fila de colagem" if page == self.PAGE_QUEUE else "Histórico")
        self.chip.setVisible(page == self.PAGE_QUEUE)
        self.search.clear()
        self._apply_filter()
        self._update_status_label()

    # ----------------------------------------------------------------- acoes
    def _set_setting(self, key: str, value) -> None:
        self.store.settings[key] = bool(value)
        self.store.save_settings()
        if self._tray is not None:
            self._tray.sync_auto()
        self._update_status_label()

    def _selected_rows(self) -> list:
        return sorted(self.q_list.row(i) for i in self.q_list.selectedItems())

    def _msg(self, text: str, ms: int = 6000) -> None:
        self.statusBar().showMessage(text, ms)

    def _move(self, delta: int) -> None:
        row = self.q_list.currentRow()
        if row < 0:
            return
        dst = row + delta
        if dst < 0 or dst >= len(self.store.items):
            return
        self.store.move(row, dst)  # dispara changed -> refresh
        self.q_list.setCurrentRow(dst)

    def _toggle_pin(self) -> None:
        rows = self._selected_rows()
        if not rows:
            return
        all_pinned = all(self.store.items[r].pinned for r in rows)
        self.store.set_pinned(rows, not all_pinned)
        self._msg(f"{len(rows)} item(ns) {'desafixado(s)' if all_pinned else 'fixado(s)'}")

    def _remove_selected(self) -> None:
        if self.pages.currentIndex() != self.PAGE_QUEUE:
            return
        rows = self._selected_rows()
        if not rows:
            return
        self.store.remove_many(rows)
        self._msg(f"{len(rows)} item(ns) removido(s) — Ctrl+Z desfaz")

    def _clear_all(self) -> None:
        keep = sum(1 for it in self.store.items if it.pinned)
        n = len(self.store.items) - keep
        if n <= 0:
            self._msg("Nada para limpar" + (" (só há itens fixados)" if keep else ""))
            return
        self.store.clear()
        extra = f"; {keep} fixado(s) mantido(s)" if keep else ""
        self._msg(f"Fila limpa ({n} item(ns){extra}) — Ctrl+Z desfaz")

    def _undo(self) -> None:
        n = self.store.undo_remove()
        self._msg(f"{n} item(ns) restaurado(s)" if n else "Nada para desfazer")

    def _undo_shortcut(self) -> None:
        w = QApplication.focusWidget()
        if isinstance(w, (QLineEdit, QPlainTextEdit)):
            w.undo()
            return
        self._undo()

    def _on_reordered(self) -> None:
        if self._rebuilding:
            return
        ids = []
        for i in range(self.q_list.count()):
            v = self.q_list.item(i).data(ID_ROLE)
            if v is not None:
                ids.append(int(v))
        self.store.reorder_by_ids(ids)

    def _on_double_click(self, item: QListWidgetItem) -> None:
        row = self.q_list.row(item)
        if 0 <= row < len(self.store.items):
            self.store.set_cursor(row)

    def _on_status(self, msg: str) -> None:
        self.statusBar().showMessage(msg, 5000)
        self._update_status_label()

    def _on_cursor_changed(self) -> None:
        self.refresh()
        c = self.store.cursor
        if 0 <= c < self.q_list.count():
            self.q_list.scrollToItem(self.q_list.item(c))

    # ------------------------------------------------------------ menu de contexto
    def _queue_menu(self, pos) -> None:
        rows = self._selected_rows()
        if not rows:
            return
        single = len(rows) == 1
        items = [self.store.items[r] for r in rows]
        menu = QMenu(self)
        a_next = menu.addAction("Definir como próximo")
        a_next.setEnabled(single)
        a_copy = menu.addAction("Copiar para a área de transferência")
        a_copy.setEnabled(single)
        a_plain = menu.addAction("Copiar como texto puro")
        a_plain.setEnabled(single and items[0].kind == ItemKind.TEXT and bool(items[0].html))
        a_edit = menu.addAction("Editar texto…")
        a_edit.setEnabled(single and items[0].kind == ItemKind.TEXT)
        menu.addSeparator()
        all_pinned = all(it.pinned for it in items)
        a_pin = menu.addAction("Desafixar" if all_pinned else "Fixar")
        a_dup = menu.addAction("Duplicar")
        a_dup.setEnabled(single)
        a_top = menu.addAction("Mover para o topo")
        a_top.setEnabled(single and rows[0] > 0)
        a_end = menu.addAction("Mover para o fim")
        a_end.setEnabled(single and rows[0] < len(self.store.items) - 1)
        menu.addSeparator()
        a_del = menu.addAction("Remover")
        act = menu.exec(self.q_list.viewport().mapToGlobal(pos))
        if act is None:
            return
        if act is a_next:
            self.store.set_cursor(rows[0])
        elif act is a_copy:
            self.engine.copy_item(items[0])
        elif act is a_plain:
            self.engine.copy_item(items[0], plain=True)
        elif act is a_edit:
            self._edit_text(rows[0])
        elif act is a_pin:
            self.store.set_pinned(rows, not all_pinned)
        elif act is a_dup:
            self.store.duplicate(rows[0])
        elif act is a_top:
            self.store.move(rows[0], 0)
        elif act is a_end:
            self.store.move(rows[0], len(self.store.items) - 1)
        elif act is a_del:
            self._remove_selected()

    def _edit_text(self, row: int) -> None:
        it = self.store.items[row]
        text, ok = QInputDialog.getMultiLineText(self, "Editar texto", "Conteúdo do item:", it.text or "")
        if ok and text != (it.text or ""):
            self.store.edit_text(row, text)
            self._msg("Texto editado (a formatação original foi descartada)")

    def _history_menu(self, pos) -> None:
        if not self.h_list.selectedItems():
            return
        single = len(self.h_list.selectedItems()) == 1
        menu = QMenu(self)
        a_add = menu.addAction("Adicionar à fila")
        a_copy = menu.addAction("Copiar para a área de transferência")
        a_copy.setEnabled(single)
        menu.addSeparator()
        a_del = menu.addAction("Remover do histórico")
        act = menu.exec(self.h_list.viewport().mapToGlobal(pos))
        if act is a_add:
            self._enqueue_selected_history()
        elif act is a_copy:
            self._copy_selected_history()
        elif act is a_del:
            self._remove_selected_history()

    # ---------------------------------------------------------------- historico
    def _selected_history_ids(self) -> list:
        return [int(i.data(ID_ROLE)) for i in self.h_list.selectedItems()]

    def _history_by_id(self, hid: int) -> Optional[ClipItem]:
        for it in self.store.history:
            if it.id == hid:
                return it
        return None

    def _enqueue_selected_history(self) -> None:
        ids = self._selected_history_ids()
        # na ordem em que aparecem (mais antigo -> mais novo) para manter a sequencia
        order = {it.id: n for n, it in enumerate(self.store.history)}
        ids.sort(key=lambda i: order.get(i, 0))
        n = self.store.enqueue_from_history(ids)
        if n:
            self._msg(f"{n} item(ns) adicionado(s) ao fim da fila")

    def _copy_selected_history(self) -> None:
        ids = self._selected_history_ids()
        if len(ids) == 1:
            it = self._history_by_id(ids[0])
            if it is not None:
                self.engine.copy_item(it)

    def _remove_selected_history(self) -> None:
        if self.pages.currentIndex() != self.PAGE_HISTORY:
            return
        ids = self._selected_history_ids()
        if ids:
            self.store.remove_history(ids)

    def _clear_history(self) -> None:
        if not self.store.history:
            return
        ans = QMessageBox.question(
            self, config.APP_DISPLAY_NAME, "Limpar todo o histórico? Isso não pode ser desfeito."
        )
        if ans == QMessageBox.StandardButton.Yes:
            self.store.clear_history()

    # ------------------------------------------------------------- dados -> view
    @staticmethod
    def _describe(it: ClipItem) -> tuple:
        if it.kind == ItemKind.TEXT:
            return ("Texto formatado" if it.html else "Texto", f"{len(it.text or '')} caractere(s)")
        if it.kind == ItemKind.IMAGE:
            return ("Imagem", f"{it.width}×{it.height}")
        return ("Arquivos", f"{len(it.files)} arquivo(s)")

    def _thumb(self, it: ClipItem) -> Optional[QPixmap]:
        if it.kind != ItemKind.IMAGE or not it.image_file:
            return None
        pm = self._thumbs.get(it.image_file)
        if pm is None:
            raw = QPixmap(str(config.blobs_dir() / it.image_file))
            if raw.isNull():
                return None
            pm = raw.scaled(40, 40, Qt.AspectRatioMode.KeepAspectRatio,
                            Qt.TransformationMode.SmoothTransformation)
            self._thumbs[it.image_file] = pm
        return pm

    def _item_data(self, it: ClipItem, index: Optional[int], is_next: bool) -> dict:
        label, extra = self._describe(it)
        missing = ClipStore.missing_files(it)
        sub = f"{label} · {extra}"
        if missing:
            sub = f"{len(missing)} de {len(it.files)} arquivo(s) não encontrado(s)"
        if it.created:
            sub += " · " + time.strftime("%H:%M", time.localtime(it.created))
        return {
            "kind": it.kind.value,
            "preview": it.preview,
            "sub": sub,
            "index": index,
            "next": is_next,
            "pinned": it.pinned,
            "missing": bool(missing),
            "thumb": self._thumb(it),
            "search": (it.text or it.preview or "").lower() + " " + sub.lower(),
        }

    def _meta_text(self, it: ClipItem) -> str:
        label, extra = self._describe(it)
        out = f"{label} · {extra}"
        if it.created:
            out += "\nCapturado em " + time.strftime("%d/%m/%Y %H:%M:%S", time.localtime(it.created))
        miss = ClipStore.missing_files(it)
        if miss:
            out += f"\n⚠ {len(miss)} arquivo(s) não encontrado(s)"
        if it.pinned:
            out += "\nFixado"
        return out

    # ------------------------------------------------------------- atualizar
    def refresh(self) -> None:
        self._rebuilding = True
        sel_ids = {int(i.data(ID_ROLE)) for i in self.q_list.selectedItems()}
        scroll = self.q_list.verticalScrollBar().value()
        self.q_list.clear()
        cursor = self.store.cursor
        for idx, it in enumerate(self.store.items):
            lw = QListWidgetItem()
            lw.setData(ID_ROLE, it.id)
            lw.setData(ROLE, self._item_data(it, idx + 1, idx == cursor))
            lw.setToolTip((it.text or it.preview or "")[:600])
            self.q_list.addItem(lw)
            if it.id in sel_ids:
                lw.setSelected(True)
        self.q_list.verticalScrollBar().setValue(scroll)
        self._rebuilding = False
        self.sync_toggles()
        self._apply_filter()
        self._update_status_label()
        self._update_queue_detail()
        self.btn_undo.setEnabled(self.store.can_undo())

    def refresh_history(self) -> None:
        sel_ids = {int(i.data(ID_ROLE)) for i in self.h_list.selectedItems()}
        scroll = self.h_list.verticalScrollBar().value()
        self.h_list.clear()
        for it in reversed(self.store.history):  # mais recente primeiro
            lw = QListWidgetItem()
            lw.setData(ID_ROLE, it.id)
            lw.setData(ROLE, self._item_data(it, None, False))
            lw.setToolTip((it.text or it.preview or "")[:600])
            self.h_list.addItem(lw)
            if it.id in sel_ids:
                lw.setSelected(True)
        self.h_list.verticalScrollBar().setValue(scroll)
        self._apply_filter()
        self._update_history_detail()

    def _update_queue_detail(self) -> None:
        if self._rebuilding:
            return
        rows = self._selected_rows()
        if len(rows) == 1 and 0 <= rows[0] < len(self.store.items):
            it = self.store.items[rows[0]]
            self.q_detail.show_item(it, self._meta_text(it), ClipStore.missing_files(it))
        else:
            self.q_detail.show_item(None, "", [])

    def _update_history_detail(self) -> None:
        ids = self._selected_history_ids()
        it = self._history_by_id(ids[0]) if len(ids) == 1 else None
        if it is not None:
            self.h_detail.show_item(it, self._meta_text(it), ClipStore.missing_files(it))
        else:
            self.h_detail.show_item(None, "", [])

    def sync_toggles(self) -> None:
        pairs = (
            (self.chk_auto, "auto_capture"),
            (self.chk_consume, "consume_on_paste"),
            (self.chk_loop, "loop"),
        )
        for chk, key in pairs:
            chk.blockSignals(True)
            chk.setChecked(bool(self.store.settings.get(key)))
            chk.blockSignals(False)

    def _update_status_label(self) -> None:
        total = len(self.store.items)
        if total == 0:
            pos, chip = "fila vazia", "Fila vazia"
        elif self.store.peek() is None:
            pos, chip = f"concluída ({total}/{total})", "Concluída"
        else:
            pos = f"próximo {self.store.cursor + 1}/{total}"
            chip = f"Próximo {self.store.cursor + 1} de {total}"
        auto = "ON" if self.store.settings.get("auto_capture") else "OFF"
        self.lbl_status.setText(f"Auto-captura: {auto}   |   Cascata: {pos}")
        self.chip.setText(chip)

    # ------------------------------------------------------- busca / config
    def _hotkey_hint_text(self) -> str:
        hk = config.effective_hotkeys(self.store.settings)
        return (
            f"{hk[config.HK_PASTE][2]} colar próximo  ·  "
            f"{hk[config.HK_PASTE_PLAIN][2]} colar sem formatação  ·  "
            f"{hk[config.HK_BACK][2]} voltar um item  ·  "
            f"{hk[config.HK_PUSH][2]} capturar  ·  "
            f"{hk[config.HK_RESET][2]} reiniciar  ·  "
            f"{hk[config.HK_TOGGLE][2]} mostrar/ocultar"
        )

    def _update_hotkey_hint(self) -> None:
        self.info.setText(self._hotkey_hint_text())

    def _apply_filter(self, *args) -> None:
        text = self.search.text().strip().lower()
        for lst in (self.q_list, self.h_list):
            for i in range(lst.count()):
                it = lst.item(i)
                d = it.data(ROLE) or {}
                it.setHidden(bool(text) and text not in d.get("search", ""))
        # com filtro ativo a ordem visual != ordem real: desliga o arrastar
        self.q_list.setDragDropMode(
            QAbstractItemView.DragDropMode.NoDragDrop if text
            else QAbstractItemView.DragDropMode.InternalMove
        )

    def _open_settings(self) -> None:
        dlg = SettingsDialog(self.store, self._hotkeys, self)
        if not dlg.exec():
            return
        theme.apply(QApplication.instance(), self.store.settings.get("theme", "system"))
        self.retheme()
        self._update_hotkey_hint()
        self._update_status_label()
        if self._tray is not None:
            self._tray.sync_auto()
        if getattr(dlg, "failed", None):
            eff = config.effective_hotkeys(self.store.settings)
            labels = ", ".join(eff[h][2] for h in dlg.failed)
            self.statusBar().showMessage(
                f"Atenção: não consegui registrar {labels} (em uso por outro app).", 10000
            )
        else:
            self.statusBar().showMessage("Configurações aplicadas.", 4000)

    # ------------------------------------------------------------- janela
    def toggle_visibility(self) -> None:
        if self.isVisible() and not self.isMinimized():
            self.hide()
        else:
            self.showNormal()
            self.raise_()
            self.activateWindow()

    def closeEvent(self, e) -> None:  # noqa: N802
        # Sem bandeja (ou encerramento real), fechar a janela encerra o app;
        # com bandeja, apenas esconde.
        if self._really_quit or not self._has_tray:
            e.accept()
            return
        e.ignore()
        self.hide()
        if self._tray is not None:
            self._tray.notify_hidden_once()
