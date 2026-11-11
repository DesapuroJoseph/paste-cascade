"""Iniciar com o Windows via registro (HKCU\\...\\Run). Sem dependencias extras."""
from __future__ import annotations

import sys
from pathlib import Path

try:
    import winreg  # type: ignore
except ImportError:  # nao-Windows
    winreg = None

_RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
_VALUE = "PasteCascade"
_LEGACY_VALUE = "CascadeClip"  # nome antigo da entrada no registro


def _launch_command() -> str:
    # Executavel congelado (PyInstaller): aponta para o proprio .exe.
    if getattr(sys, "frozen", False):
        return f'"{Path(sys.executable)}"'
    exe = Path(sys.executable)
    pyw = exe.with_name("pythonw.exe")
    runner = pyw if pyw.exists() else exe
    run_pyw = Path(__file__).resolve().parents[1] / "run.pyw"
    if run_pyw.exists():
        return f'"{runner}" "{run_pyw}"'
    return f'"{runner}" -m paste_cascade'


def _has_value(name: str) -> bool:
    if winreg is None:
        return False
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _RUN_KEY) as k:
            winreg.QueryValueEx(k, name)
            return True
    except OSError:  # inclui FileNotFoundError
        return False


def _delete_value(name: str) -> bool:
    if winreg is None:
        return False
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _RUN_KEY, 0, winreg.KEY_SET_VALUE) as k:
            winreg.DeleteValue(k, name)
        return True
    except FileNotFoundError:
        return True  # ja nao existe
    except OSError:
        return False


def is_enabled() -> bool:
    return _has_value(_VALUE) or _has_value(_LEGACY_VALUE)


def enable() -> bool:
    if winreg is None:
        return False
    try:
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, _RUN_KEY) as k:
            winreg.SetValueEx(k, _VALUE, 0, winreg.REG_SZ, _launch_command())
        _delete_value(_LEGACY_VALUE)
        return True
    except OSError:
        return False


def disable() -> bool:
    ok_new = _delete_value(_VALUE)
    ok_old = _delete_value(_LEGACY_VALUE)
    return ok_new and ok_old


def migrate_legacy() -> None:
    """Se o autostart estava ligado com o nome antigo, passa para o nome novo."""
    if _has_value(_LEGACY_VALUE):
        enable()
