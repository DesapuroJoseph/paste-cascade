"""Dialogo de configuracoes: remapear atalhos, limites e iniciar com o Windows."""
from __future__ import annotations

from typing import Optional, Tuple

from PySide6.QtCore import Qt, QKeyCombination
from PySide6.QtGui import QKeySequence
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QKeySequenceEdit,
    QLabel,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
)

from . import autostart, config

_ACTION_NAMES = {
    config.HK_PUSH: "Capturar clipboard",
    config.HK_PASTE: "Colar proximo",
    config.HK_PASTE_PLAIN: "Colar sem formatacao",
    config.HK_BACK: "Voltar um item",
    config.HK_RESET: "Reiniciar fila",
    config.HK_TOGGLE: "Mostrar / ocultar janela",
}
_ACTION_ORDER = [
    config.HK_PUSH,
    config.HK_PASTE,
    config.HK_PASTE_PLAIN,
    config.HK_BACK,
    config.HK_RESET,
    config.HK_TOGGLE,
]


# --------------------------------------------------------- conversao Qt <-> Win32
def _qtkey_to_vk(qkey) -> Optional[int]:
    k = int(qkey)
    if 0x41 <= k <= 0x5A or 0x30 <= k <= 0x39:  # A-Z, 0-9
        return k
    f1, f24 = int(Qt.Key.Key_F1), int(Qt.Key.Key_F24)
    if f1 <= k <= f24:
        return 0x70 + (k - f1)
    table = {
        int(Qt.Key.Key_Space): 0x20,
        int(Qt.Key.Key_Insert): 0x2D,
        int(Qt.Key.Key_Delete): 0x2E,
        int(Qt.Key.Key_Home): 0x24,
        int(Qt.Key.Key_End): 0x23,
        int(Qt.Key.Key_PageUp): 0x21,
        int(Qt.Key.Key_PageDown): 0x22,
        int(Qt.Key.Key_Left): 0x25,
        int(Qt.Key.Key_Up): 0x26,
        int(Qt.Key.Key_Right): 0x27,
        int(Qt.Key.Key_Down): 0x28,
        int(Qt.Key.Key_Tab): 0x09,
    }
    return table.get(k)


def _vk_to_qtkey(vk: int):
    if 0x41 <= vk <= 0x5A or 0x30 <= vk <= 0x39:
        return Qt.Key(vk)
    if 0x70 <= vk <= 0x87:
        return Qt.Key(int(Qt.Key.Key_F1) + (vk - 0x70))
    table = {
        0x20: Qt.Key.Key_Space, 0x2D: Qt.Key.Key_Insert, 0x2E: Qt.Key.Key_Delete,
        0x24: Qt.Key.Key_Home, 0x23: Qt.Key.Key_End, 0x21: Qt.Key.Key_PageUp,
        0x22: Qt.Key.Key_PageDown, 0x25: Qt.Key.Key_Left, 0x26: Qt.Key.Key_Up,
        0x27: Qt.Key.Key_Right, 0x28: Qt.Key.Key_Down, 0x09: Qt.Key.Key_Tab,
    }
    return table.get(vk, Qt.Key.Key_unknown)


def _seq_to_win(seq: QKeySequence) -> Optional[Tuple[int, int]]:
    """QKeySequence -> (mods, vk) Win32, ou None se invalido (precisa modificador)."""
    if seq is None or seq.isEmpty():
        return None
    kc = seq[0]
    try:
        qkey = kc.key()
        qmods = kc.keyboardModifiers()
    except AttributeError:
        return None
    mods = 0
    if qmods & Qt.KeyboardModifier.ControlModifier:
        mods |= config.MOD_CONTROL
    if qmods & Qt.KeyboardModifier.ShiftModifier:
        mods |= config.MOD_SHIFT
    if qmods & Qt.KeyboardModifier.AltModifier:
        mods |= config.MOD_ALT
    if qmods & Qt.KeyboardModifier.MetaModifier:
        mods |= config.MOD_WIN
    vk = _qtkey_to_vk(qkey)
    if vk is None or mods == 0:
        return None
    return (mods, vk)


def _win_to_seq(mods: int, vk: int) -> QKeySequence:
    qmods = Qt.KeyboardModifier.NoModifier
    if mods & config.MOD_CONTROL:
        qmods |= Qt.KeyboardModifier.ControlModifier
    if mods & config.MOD_SHIFT:
        qmods |= Qt.KeyboardModifier.ShiftModifier
    if mods & config.MOD_ALT:
        qmods |= Qt.KeyboardModifier.AltModifier
    if mods & config.MOD_WIN:
        qmods |= Qt.KeyboardModifier.MetaModifier
    try:
        return QKeySequence(QKeyCombination(qmods, _vk_to_qtkey(vk)))
    except Exception:
        return QKeySequence()


class SettingsDialog(QDialog):
    def __init__(self, store, hotkeys_mgr, parent=None) -> None:
        super().__init__(parent)
        self.store = store
        self.hotkeys = hotkeys_mgr
        self.failed: list = []
        self.setWindowTitle("Configuracoes — Paste Cascade")
        self.setMinimumWidth(420)
        self._build()

    def _build(self) -> None:
        root = QVBoxLayout(self)

        root.addWidget(QLabel("<b>Atalhos globais</b> (clique e pressione a combinacao)"))
        form = QFormLayout()
        eff = config.effective_hotkeys(self.store.settings)
        self.edits = {}
        for hid in _ACTION_ORDER:
            mods, vk, _label = eff[hid]
            edit = QKeySequenceEdit(_win_to_seq(mods, vk))
            try:
                edit.setMaximumSequenceLength(1)
            except Exception:
                pass
            self.edits[hid] = edit
            form.addRow(_ACTION_NAMES[hid], edit)
        root.addLayout(form)

        btn_defaults = QPushButton("Restaurar atalhos padrao")
        btn_defaults.clicked.connect(self._restore_default_hotkeys)
        root.addWidget(btn_defaults)

        root.addWidget(QLabel("<b>Opcoes</b>"))
        opts = QFormLayout()
        self.combo_theme = QComboBox()
        for label, value in (("Seguir o sistema", "system"), ("Claro", "light"), ("Escuro", "dark")):
            self.combo_theme.addItem(label, value)
        idx = self.combo_theme.findData(self.store.settings.get("theme", "system"))
        self.combo_theme.setCurrentIndex(idx if idx >= 0 else 0)
        opts.addRow("Tema", self.combo_theme)

        self.spin_max = QSpinBox()
        self.spin_max.setRange(0, 10000)
        self.spin_max.setValue(int(self.store.settings.get("max_items", 200) or 0))
        self.spin_max.setToolTip("0 = ilimitado")
        opts.addRow("Maximo de itens guardados", self.spin_max)

        self.spin_hist = QSpinBox()
        self.spin_hist.setRange(0, 2000)
        self.spin_hist.setValue(int(self.store.settings.get("history_max", 100) or 0))
        self.spin_hist.setToolTip("0 = não guardar histórico")
        opts.addRow("Itens no histórico", self.spin_hist)

        self.spin_delay = QSpinBox()
        self.spin_delay.setRange(0, 2000)
        self.spin_delay.setSingleStep(10)
        self.spin_delay.setValue(int(self.store.settings.get("paste_delay_ms", 130) or 0))
        self.spin_delay.setSuffix(" ms")
        self.spin_delay.setToolTip("Atraso antes de injetar Ctrl+V (deixa soltar as teclas)")
        opts.addRow("Atraso da colagem", self.spin_delay)
        root.addLayout(opts)

        self.chk_autostart = QCheckBox("Iniciar com o Windows")
        self.chk_autostart.setChecked(autostart.is_enabled())
        root.addWidget(self.chk_autostart)

        self.chk_start_hidden = QCheckBox("Iniciar minimizado na bandeja")
        self.chk_start_hidden.setChecked(bool(self.store.settings.get("start_hidden")))
        root.addWidget(self.chk_start_hidden)

        self.chk_hud = QCheckBox("Mostrar aviso flutuante ao colar (próximo item)")
        self.chk_hud.setChecked(bool(self.store.settings.get("hud_enabled", True)))
        root.addWidget(self.chk_hud)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

    def _restore_default_hotkeys(self) -> None:
        for hid in _ACTION_ORDER:
            mods, vk, _ = config.DEFAULT_HOTKEYS[hid]
            self.edits[hid].setKeySequence(_win_to_seq(mods, vk))

    def accept(self) -> None:
        chosen = {}
        invalid = []
        for hid in _ACTION_ORDER:
            res = _seq_to_win(self.edits[hid].keySequence())
            if res is None:
                invalid.append(_ACTION_NAMES[hid])
            else:
                chosen[hid] = res
        if invalid:
            QMessageBox.warning(
                self,
                "Atalhos invalidos",
                "Estes atalhos precisam de Ctrl/Shift/Alt + uma tecla:\n\n- "
                + "\n- ".join(invalid),
            )
            return
        combos = list(chosen.values())
        if len(set(combos)) != len(combos):
            QMessageBox.warning(self, "Atalhos repetidos", "Dois atalhos usam a mesma combinacao.")
            return

        overrides = dict(self.store.settings.get("hotkeys") or {})
        for hid, (mods, vk) in chosen.items():
            overrides[str(hid)] = [mods, vk, config.format_label(mods, vk)]
        self.store.settings["hotkeys"] = overrides
        self.store.settings["max_items"] = self.spin_max.value()
        self.store.settings["history_max"] = self.spin_hist.value()
        self.store.settings["paste_delay_ms"] = self.spin_delay.value()
        self.store.settings["start_hidden"] = self.chk_start_hidden.isChecked()
        self.store.settings["hud_enabled"] = self.chk_hud.isChecked()
        self.store.settings["theme"] = self.combo_theme.currentData() or "system"
        self.store.save_settings()

        if self.chk_autostart.isChecked():
            autostart.enable()
        else:
            autostart.disable()

        if self.hotkeys is not None:
            self.hotkeys.rebind(config.effective_hotkeys(self.store.settings))
            self.failed = list(self.hotkeys.failed)

        super().accept()
