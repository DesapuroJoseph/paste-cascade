"""Aviso flutuante (HUD) que mostra o estado da cascata sem abrir a janela.

Nao rouba o foco (WA_ShowWithoutActivating + WindowDoesNotAcceptFocus), para
nao atrapalhar a colagem no app que esta em primeiro plano.
"""
from __future__ import annotations

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QCursor, QGuiApplication
from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget

HUD_DURATION_MS = 1600


class PasteHud(QWidget):
    def __init__(self) -> None:
        super().__init__(
            None,
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
            | Qt.WindowType.WindowDoesNotAcceptFocus,
        )
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)

        self._label = QLabel(self)
        self._label.setWordWrap(True)
        self._label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._label.setStyleSheet(
            "QLabel { color:#ffffff; background:rgba(30,40,55,220);"
            " padding:10px 16px; border-radius:8px; font-size:13px; }"
        )
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(self._label)
        self.setMaximumWidth(460)

        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self.hide)

    def show_text(self, text: str) -> None:
        self._label.setText(text)
        self.adjustSize()
        self._center_bottom()
        self.show()
        self.raise_()
        self._timer.start(HUD_DURATION_MS)

    def _center_bottom(self) -> None:
        screen = QGuiApplication.screenAt(QCursor.pos()) or QGuiApplication.primaryScreen()
        if screen is None:
            return
        geo = screen.availableGeometry()
        x = geo.x() + (geo.width() - self.width()) // 2
        y = geo.y() + geo.height() - self.height() - 80
        self.move(x, y)
