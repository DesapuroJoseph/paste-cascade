"""Configuracao central: caminhos, constantes Win32, atalhos e settings padrao."""
from __future__ import annotations

import os
from pathlib import Path

APP_NAME = "PasteCascade"
APP_DISPLAY_NAME = "Paste Cascade"
VERSION = "1.0.0"


LEGACY_APP_NAME = "CascadeClip"  # nome antigo: pasta de dados e entrada de autostart


def data_dir() -> Path:
    base = os.environ.get("APPDATA") or str(Path.home())
    d = Path(base) / APP_NAME
    if not d.exists():
        _migrate_legacy_data(Path(base) / LEGACY_APP_NAME, d)
    d.mkdir(parents=True, exist_ok=True)
    return d


def _migrate_legacy_data(old: Path, new: Path) -> None:
    """Primeira execucao apos o rename: leva fila, historico e config antigos."""
    if not old.is_dir():
        return
    try:
        old.rename(new)  # rapido; falha se algum arquivo estiver aberto por outro processo
    except OSError:
        try:
            import shutil
            shutil.copytree(old, new)  # copia (a pasta antiga fica; pode ser apagada depois)
        except Exception:
            pass


def blobs_dir() -> Path:
    d = data_dir() / "blobs"
    d.mkdir(parents=True, exist_ok=True)
    return d


def items_path() -> Path:
    return data_dir() / "items.json"


def settings_path() -> Path:
    return data_dir() / "settings.json"


def history_path() -> Path:
    return data_dir() / "history.json"


# ----------------------------------------------------------------------------
# Constantes Win32
# ----------------------------------------------------------------------------
WM_HOTKEY = 0x0312

MOD_ALT = 0x0001
MOD_CONTROL = 0x0002
MOD_SHIFT = 0x0004
MOD_WIN = 0x0008
MOD_NOREPEAT = 0x4000

VK_CONTROL = 0x11
VK_SHIFT = 0x10
VK_MENU = 0x12  # Alt
VK_C = 0x43
VK_V = 0x56
VK_R = 0x52
VK_B = 0x42
VK_U = 0x55
VK_SPACE = 0x20

# ----------------------------------------------------------------------------
# IDs e mapa de atalhos globais
# ----------------------------------------------------------------------------
HK_PUSH = 1     # empurra o clipboard atual para a fila (captura manual)
HK_PASTE = 2    # cola o proximo item da cascata
HK_RESET = 3    # reinicia o cursor da fila para o topo
HK_TOGGLE = 4   # mostra/oculta a janela
HK_BACK = 5     # volta o cursor um item (desfaz um "pulo")
HK_PASTE_PLAIN = 6  # cola o proximo item como texto puro (sem formatacao)

# id -> (modificadores, virtual-key, rotulo legivel)
DEFAULT_HOTKEYS = {
    HK_PUSH:        (MOD_CONTROL | MOD_SHIFT, VK_C, "Ctrl+Shift+C"),
    HK_PASTE:       (MOD_CONTROL | MOD_SHIFT, VK_V, "Ctrl+Shift+V"),
    HK_RESET:       (MOD_CONTROL | MOD_SHIFT, VK_R, "Ctrl+Shift+R"),
    HK_TOGGLE:      (MOD_CONTROL | MOD_SHIFT, VK_SPACE, "Ctrl+Shift+Space"),
    HK_BACK:        (MOD_CONTROL | MOD_SHIFT, VK_B, "Ctrl+Shift+B"),
    HK_PASTE_PLAIN: (MOD_CONTROL | MOD_SHIFT, VK_U, "Ctrl+Shift+U"),
}

# ----------------------------------------------------------------------------
# Settings padrao (sobrescritos por settings.json)
# ----------------------------------------------------------------------------
DEFAULT_SETTINGS = {
    "auto_capture": True,       # capturar automaticamente copias normais (Ctrl+C)
    "consume_on_paste": False,  # True = remove o item apos colar; False = mantem e avanca o cursor
    "loop": False,              # ao chegar no fim da fila, voltar ao inicio
    "max_items": 200,           # limite de itens guardados (0 = ilimitado)
    "history_max": 100,         # itens no historico de copias (0 = desligado)
    "dedup_consecutive": True,  # ignorar copia identica a ultima
    "paste_delay_ms": 130,      # atraso antes de injetar Ctrl+V (deixa soltar as teclas)
    "suppress_ms": 600,         # (legado) janela de supressao por tempo; nao usado pela supressao por conteudo
    "start_hidden": False,      # iniciar minimizado na bandeja
    "hud_enabled": True,        # mostrar aviso flutuante (proximo item) ao colar/voltar
    "theme": "system",          # "system" (segue o Windows) | "light" | "dark"
    "hotkeys": {},              # overrides de atalho: {str(hid): [mods, vk, label]} (vazio = padroes)
}


# ----------------------------------------------------------------------------
# Atalhos configuraveis
# ----------------------------------------------------------------------------
def _vk_name(vk: int) -> str:
    if 0x41 <= vk <= 0x5A or 0x30 <= vk <= 0x39:
        return chr(vk)
    if 0x70 <= vk <= 0x87:
        return f"F{vk - 0x6F}"
    specials = {
        0x20: "Space", 0x2D: "Insert", 0x2E: "Delete", 0x24: "Home", 0x23: "End",
        0x21: "PageUp", 0x22: "PageDown", 0x25: "Left", 0x26: "Up", 0x27: "Right",
        0x28: "Down", 0x09: "Tab", 0x0D: "Enter", 0x08: "Backspace",
    }
    return specials.get(vk, f"0x{vk:02X}")


def format_label(mods: int, vk: int) -> str:
    parts = []
    if mods & MOD_CONTROL:
        parts.append("Ctrl")
    if mods & MOD_ALT:
        parts.append("Alt")
    if mods & MOD_SHIFT:
        parts.append("Shift")
    if mods & MOD_WIN:
        parts.append("Win")
    parts.append(_vk_name(vk))
    return "+".join(parts)


def effective_hotkeys(settings: dict) -> dict:
    """Mapa efetivo id -> (mods, vk, label), aplicando overrides das settings."""
    overrides = (settings or {}).get("hotkeys") or {}
    result = {}
    for hid, default in DEFAULT_HOTKEYS.items():
        ov = overrides.get(str(hid))
        if isinstance(ov, (list, tuple)) and len(ov) >= 2:
            try:
                mods, vk = int(ov[0]), int(ov[1])
                label = ov[2] if len(ov) > 2 and ov[2] else format_label(mods, vk)
                result[hid] = (mods, vk, label)
                continue
            except Exception:
                pass
        result[hid] = default
    return result
