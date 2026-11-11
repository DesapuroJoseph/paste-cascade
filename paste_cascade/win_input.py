"""Injecao de teclas via SendInput (Win32).

Usado para "colar" (Ctrl+V) no aplicativo em foco depois de preparar o
clipboard, e para soltar os modificadores que o usuario ainda esteja
segurando ao disparar o atalho global (Ctrl+Shift continuam fisicamente
pressionados no momento em que o WM_HOTKEY chega).

Importante: o INPUT precisa ter o tamanho EXATO que o Windows espera
(40 bytes em x64, 28 em x86); por isso a union inclui MOUSEINPUT, que e' o
maior membro. Sem isso, SendInput retorna 0 (ERROR_INVALID_PARAMETER) e NAO
injeta nada — ou seja, nada e' colado.
"""
from __future__ import annotations

import ctypes
from ctypes import wintypes

from . import config

user32 = ctypes.WinDLL("user32", use_last_error=True)

ULONG_PTR = ctypes.c_size_t
INPUT_KEYBOARD = 1
KEYEVENTF_KEYUP = 0x0002
KEYEVENTF_EXTENDEDKEY = 0x0001

# VKs esquerda/direita explicitos (para soltar AMBOS os lados)
VK_LSHIFT = 0xA0
VK_RSHIFT = 0xA1
VK_LCONTROL = 0xA2
VK_RCONTROL = 0xA3
VK_LMENU = 0xA4
VK_RMENU = 0xA5
# Ctrl/Alt direitos sao "extended keys"
_EXTENDED = {VK_RCONTROL, VK_RMENU}


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [
        ("wVk", wintypes.WORD),
        ("wScan", wintypes.WORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ULONG_PTR),
    ]


class MOUSEINPUT(ctypes.Structure):
    _fields_ = [
        ("dx", wintypes.LONG),
        ("dy", wintypes.LONG),
        ("mouseData", wintypes.DWORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ULONG_PTR),
    ]


class _INPUTunion(ctypes.Union):
    # MOUSEINPUT primeiro: e' o maior membro e dimensiona corretamente o INPUT
    _fields_ = [("mi", MOUSEINPUT), ("ki", KEYBDINPUT)]


class INPUT(ctypes.Structure):
    _fields_ = [("type", wintypes.DWORD), ("u", _INPUTunion)]


# Garante o tamanho correto do INPUT (40 em x64, 28 em x86).
_EXPECTED_INPUT_SIZE = 40 if ctypes.sizeof(ctypes.c_void_p) == 8 else 28
assert ctypes.sizeof(INPUT) == _EXPECTED_INPUT_SIZE, (
    f"sizeof(INPUT)={ctypes.sizeof(INPUT)} (esperado {_EXPECTED_INPUT_SIZE})"
)

user32.SendInput.argtypes = (wintypes.UINT, ctypes.POINTER(INPUT), ctypes.c_int)
user32.SendInput.restype = wintypes.UINT


def _key(vk: int, up: bool, extended: bool = False) -> INPUT:
    flags = 0
    if extended:
        flags |= KEYEVENTF_EXTENDEDKEY
    if up:
        flags |= KEYEVENTF_KEYUP
    ki = KEYBDINPUT(wVk=vk, wScan=0, dwFlags=flags, time=0, dwExtraInfo=0)
    return INPUT(type=INPUT_KEYBOARD, u=_INPUTunion(ki=ki))


def _send(inputs: list) -> int:
    n = len(inputs)
    if n == 0:
        return 0
    arr = (INPUT * n)(*inputs)
    sent = int(user32.SendInput(n, arr, ctypes.sizeof(INPUT)))
    if sent != n:
        raise ctypes.WinError(ctypes.get_last_error())
    return sent


def release_modifiers() -> None:
    """Solta Ctrl/Shift/Alt (ambos os lados) que o usuario possa estar segurando.

    Precede a injecao de Ctrl+V: garante que, no estado do SO, Shift/Alt estejam
    "up" quando o V for injetado — evitando que o Ctrl+V vire Ctrl+Shift+V e que
    o proprio atalho global (Ctrl+Shift+V) seja re-disparado.
    """
    seq = []
    for vk in (VK_LSHIFT, VK_RSHIFT, VK_LCONTROL, VK_RCONTROL, VK_LMENU, VK_RMENU):
        seq.append(_key(vk, up=True, extended=(vk in _EXTENDED)))
    _send(seq)


def send_paste() -> None:
    """Ctrl+V limpo (chame apos release_modifiers)."""
    _send([
        _key(config.VK_CONTROL, False),
        _key(config.VK_V, False),
        _key(config.VK_V, True),
        _key(config.VK_CONTROL, True),
    ])
