"""Atalhos globais via RegisterHotKey (Win32).

Um QWidget invisivel fornece o HWND usado para registrar os hotkeys. A
entrega de WM_HOTKEY e' feita por um QAbstractNativeEventFilter instalado no
QApplication (ve todo WM_HOTKEY que passa pelo loop de eventos do Qt), em vez
de depender do nativeEvent de um unico widget invisivel — mais confiavel em
sessoes reais do Windows, onde um widget sem janela visivel pode nao receber
nativeEvent de forma consistente dependendo da versao/plataforma do Qt.
"""
from __future__ import annotations

import ctypes
from ctypes import wintypes

from PySide6.QtCore import QAbstractNativeEventFilter, Signal
from PySide6.QtWidgets import QWidget

from . import config

user32 = ctypes.WinDLL("user32", use_last_error=True)
user32.RegisterHotKey.argtypes = (wintypes.HWND, ctypes.c_int, wintypes.UINT, wintypes.UINT)
user32.RegisterHotKey.restype = wintypes.BOOL
user32.UnregisterHotKey.argtypes = (wintypes.HWND, ctypes.c_int)
user32.UnregisterHotKey.restype = wintypes.BOOL


class _HotkeyNativeEventFilter(QAbstractNativeEventFilter):
    """Instalado no QApplication: intercepta WM_HOTKEY antes de qualquer
    widget, para qualquer HWND que o processo tenha registrado hotkeys."""

    def __init__(self, manager: "HotkeyManager") -> None:
        super().__init__()
        self._manager = manager

    def nativeEventFilter(self, eventType, message):  # noqa: N802 (assinatura do Qt)
        try:
            if eventType in (b"windows_generic_MSG", b"windows_dispatcher_MSG"):
                msg = wintypes.MSG.from_address(int(message))
                if msg.message == config.WM_HOTKEY:
                    self._manager.activated.emit(int(msg.wParam))
                    return True, 0
        except Exception:
            pass
        return False, 0


class HotkeyManager(QWidget):
    activated = Signal(int)  # emite o id do atalho

    def __init__(self, hotkeys: dict) -> None:
        super().__init__()
        self.setWindowTitle("PasteCascade Hotkeys")
        self.resize(0, 0)
        self._hotkeys = dict(hotkeys)
        self._registered: list[int] = []
        self.failed: list[int] = []
        # winId() forca a criacao da janela nativa e devolve o HWND
        self._hwnd = int(self.winId())
        self._event_filter = _HotkeyNativeEventFilter(self)
        self._register_all()

    def install_event_filter(self, app) -> None:
        """Instala o filtro global de WM_HOTKEY no QApplication. Chamar uma
        vez, logo apos criar a instancia."""
        app.installNativeEventFilter(self._event_filter)

    def _register_all(self) -> None:
        for hid, (mods, vk, _label) in self._hotkeys.items():
            ok = user32.RegisterHotKey(self._hwnd, hid, mods | config.MOD_NOREPEAT, vk)
            if ok:
                self._registered.append(hid)
            else:
                self.failed.append(hid)

    def rebind(self, hotkeys: dict) -> None:
        """Re-registra os atalhos ao vivo com um novo mapa id -> (mods, vk, label)."""
        self.unregister_all()
        self._hotkeys = dict(hotkeys)
        self.failed = []
        self._register_all()

    def unregister_all(self) -> None:
        for hid in list(self._registered):
            try:
                user32.UnregisterHotKey(self._hwnd, hid)
            except Exception:
                pass
        self._registered.clear()

    def closeEvent(self, event) -> None:  # noqa: N802
        self.unregister_all()
        super().closeEvent(event)
