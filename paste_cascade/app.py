"""Bootstrap da aplicacao: QApplication, instancia unica e fiacao dos modulos."""
from __future__ import annotations

import ctypes
import sys

from PySide6.QtCore import QSharedMemory
from PySide6.QtWidgets import QApplication, QMessageBox, QSystemTrayIcon

from . import autostart, config, theme
from .engine import CascadeEngine
from .hud import PasteHud
from .icon import make_app_icon
from .main_window import MainWindow
from .store import ClipStore
from .tray import Tray
from .win_hotkeys import HotkeyManager


def _set_app_user_model_id() -> None:
    """Faz a barra de tarefas mostrar o icone do app (e nao o do Python) ao rodar via pythonw."""
    try:
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("PasteCascade.App")
    except Exception:
        pass


def main() -> int:
    _set_app_user_model_id()
    app = QApplication(sys.argv)
    app.setApplicationName(config.APP_NAME)
    app.setApplicationDisplayName(config.APP_DISPLAY_NAME)

    # Instancia unica (evita atalhos globais duplicados)
    shared = QSharedMemory("PasteCascade_singleton_v1")
    if shared.attach():
        QMessageBox.information(
            None,
            config.APP_DISPLAY_NAME,
            "O Paste Cascade ja esta em execucao (veja a bandeja do sistema).",
        )
        return 0
    shared.create(1)

    icon = make_app_icon()
    app.setWindowIcon(icon)

    store = ClipStore()
    autostart.migrate_legacy()  # autostart ligado com o nome antigo -> nome novo

    # Visual Fluent/Windows 11: Fusion + QSS proprio; claro/escuro/sistema (Configuracoes)
    app.setStyle("Fusion")
    theme.apply(app, store.settings.get("theme", "system"))

    engine = CascadeEngine(store)
    window = MainWindow(store, engine)
    window.setWindowIcon(icon)

    def on_scheme_changed(*_args) -> None:
        theme.apply(app, store.settings.get("theme", "system"))
        window.retheme()

    try:
        app.styleHints().colorSchemeChanged.connect(on_scheme_changed)
    except Exception:
        pass  # Qt sem esse sinal: o tema so' muda ao reiniciar

    hotkeys = HotkeyManager(config.effective_hotkeys(store.settings))
    hotkeys.install_event_filter(app)
    hotkeys.activated.connect(engine.on_hotkey)
    window._hotkeys = hotkeys
    engine.toggle_window_requested.connect(window.toggle_visibility)

    hud = PasteHud()
    engine.hud.connect(hud.show_text)

    # So' usa a bandeja se o sistema a oferece; senao, fechar a janela encerra
    # o app (evita um processo invisivel e impossivel de fechar sem o Gerenciador).
    tray = None
    if QSystemTrayIcon.isSystemTrayAvailable():
        app.setQuitOnLastWindowClosed(False)
        tray = Tray(icon, window, engine, store)
        window._tray = tray
        window._has_tray = True
        tray.show()
    else:
        app.setQuitOnLastWindowClosed(True)

    # Mantem referencias vivas durante toda a execucao
    app._cc_refs = (store, engine, window, hotkeys, tray, shared, hud)

    def on_quit() -> None:
        try:
            store.save()
            store.save_settings()
        except Exception:
            pass
        try:
            hotkeys.unregister_all()
        except Exception:
            pass
        try:
            shared.detach()
        except Exception:
            pass

    app.aboutToQuit.connect(on_quit)

    # Inicia oculto apenas se houver bandeja para reabrir.
    start_hidden = bool(store.settings.get("start_hidden")) and tray is not None
    if not start_hidden:
        window.show()

    if hotkeys.failed:
        eff = config.effective_hotkeys(store.settings)
        labels = ", ".join(eff[h][2] for h in hotkeys.failed)
        window.show()
        window.statusBar().showMessage(
            f"Atencao: nao consegui registrar {labels} (atalho ja em uso por outro app).",
            12000,
        )

    return app.exec()
