"""Icone da bandeja do sistema."""
from __future__ import annotations

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication, QMenu, QSystemTrayIcon

from . import config


class Tray(QSystemTrayIcon):
    def __init__(self, icon: QIcon, window, engine, store) -> None:
        super().__init__(icon)
        self.window = window
        self.engine = engine
        self.store = store
        self._hidden_notified = False
        self.setToolTip(config.APP_DISPLAY_NAME)

        menu = QMenu()
        menu.addAction("Mostrar / ocultar janela", self.window.toggle_visibility)
        menu.addAction("Colar proximo", lambda: self.engine.paste_next())
        menu.addAction("Reiniciar fila", self.store.reset_cursor)
        self.act_auto = menu.addAction("Auto-captura (Ctrl+C)")
        self.act_auto.setCheckable(True)
        self.act_auto.setChecked(bool(self.store.settings.get("auto_capture", True)))
        self.act_auto.toggled.connect(self._toggle_auto)
        menu.addSeparator()
        menu.addAction("Configuracoes...", self.window._open_settings)
        menu.addAction("Sair", self._quit)
        self.setContextMenu(menu)

        self.activated.connect(self._on_activated)

    def _on_activated(self, reason) -> None:
        if reason == QSystemTrayIcon.ActivationReason.Trigger:
            self.window.toggle_visibility()

    def _toggle_auto(self, checked: bool) -> None:
        self.store.settings["auto_capture"] = bool(checked)
        self.store.save_settings()
        self.window.sync_toggles()
        self.window._update_status_label()

    def sync_auto(self) -> None:
        self.act_auto.blockSignals(True)
        self.act_auto.setChecked(bool(self.store.settings.get("auto_capture", True)))
        self.act_auto.blockSignals(False)

    def notify_hidden_once(self) -> None:
        if not self._hidden_notified and self.supportsMessages():
            self._hidden_notified = True
            self.showMessage(
                config.APP_DISPLAY_NAME,
                "Continuo rodando na bandeja. Clique no icone para reabrir.",
                QSystemTrayIcon.MessageIcon.Information,
                2500,
            )

    def _quit(self) -> None:
        self.window._really_quit = True
        QApplication.quit()
