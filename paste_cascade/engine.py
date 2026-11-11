"""Motor da cascata: liga atalhos, clipboard e a fila (store)."""
from __future__ import annotations

from PySide6.QtCore import QObject, QTimer, Signal
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import QApplication

from . import clipboard_io, config, win_input
from .models import ItemKind
from .store import ClipStore


def _short(text: str, n: int = 60) -> str:
    t = " ".join((text or "").split())
    return (t[:n] + "…") if len(t) > n else t


class CascadeEngine(QObject):
    status = Signal(str)                 # mensagem curta para a barra de status
    paste_done = Signal()                # colou algo (UI pode atualizar)
    toggle_window_requested = Signal()   # atalho de mostrar/ocultar janela
    hud = Signal(str)                    # aviso flutuante (ja filtrado pela opcao hud_enabled)

    def __init__(self, store: ClipStore) -> None:
        super().__init__()
        self.store = store
        self.clipboard = QGuiApplication.clipboard()
        # Supressao por CONTEUDO: guardamos a assinatura do que NOS escrevemos
        # no clipboard; qualquer dataChanged cujo conteudo == essa assinatura e'
        # a nossa propria colagem e deve ser ignorado (imune a latencia/corrida).
        self._last_written_sig = None
        # Guarda de sobreposicao: no maximo uma colagem em andamento por vez.
        self._pasting = False
        self.clipboard.dataChanged.connect(self._on_clipboard_changed)

    # ------------------------------------------------------- captura passiva
    def _on_clipboard_changed(self) -> None:
        if not self.store.settings.get("auto_capture", True):
            return
        data = clipboard_io.read_clipboard(self.clipboard)
        if data is None:
            return
        sig = self._signature(*data)
        if sig is not None and sig == self._last_written_sig:
            return  # e' a nossa propria escrita (colagem) -> ignorar
        # Captura real do usuario: a assinatura de escrita deixa de valer.
        self._last_written_sig = None
        self._add(data, self._html_for(data))

    def _capture_current(self) -> bool:
        data = clipboard_io.read_clipboard(self.clipboard)
        if data is None:
            return False
        return self._add(data, self._html_for(data))

    def _html_for(self, data):
        # HTML so' faz sentido junto de texto (formatacao de Word/navegador).
        if data[0] != "text":
            return None
        return clipboard_io.read_html(self.clipboard)

    def _add(self, data, html=None) -> bool:
        kind, payload = data
        item = None
        if kind == "text":
            item = self.store.add_text(payload, html)
        elif kind == "image":
            item = self.store.add_image(payload)
        elif kind == "files":
            item = self.store.add_files(payload)
        if item is not None:
            self.status.emit(f"Capturado ({item.kind.value}) — {len(self.store.items)} na fila")
            return True
        return False

    @staticmethod
    def _signature(kind, payload):
        if kind == "text":
            return ("t", payload)
        if kind == "files":
            return ("f", tuple(payload))
        if kind == "image":
            digest = clipboard_io.image_digest(payload)
            return ("i", digest) if digest else None
        return None

    @staticmethod
    def _item_signature(item):
        if item.kind == ItemKind.TEXT:
            return ("t", item.text or "")
        if item.kind == ItemKind.FILES:
            return ("f", tuple(item.files))
        if item.kind == ItemKind.IMAGE and item.image_hash:
            return ("i", item.image_hash)
        return None

    # --------------------------------------------------------------- atalhos
    def on_hotkey(self, hid: int) -> None:
        if hid == config.HK_PUSH:
            self.push_current()
        elif hid == config.HK_PASTE:
            self.paste_next()
        elif hid == config.HK_PASTE_PLAIN:
            self.paste_next(plain=True)
        elif hid == config.HK_BACK:
            self.step_back()
        elif hid == config.HK_RESET:
            self.store.reset_cursor()
            self.status.emit("Fila reiniciada — proximo = 1")
            self._hud("Fila reiniciada\nPróximo: 1")
        elif hid == config.HK_TOGGLE:
            self.toggle_window_requested.emit()

    def step_back(self) -> None:
        if self._pasting:
            return
        if not self.store.retreat():
            self.status.emit("Já está no primeiro item da fila")
            return
        item = self.store.peek()
        total = len(self.store.items)
        pos = f"{self.store.cursor + 1}/{total}"
        self.status.emit(f"Voltou — próximo {pos}")
        if item is not None:
            self._hud(f"◀ Próximo {pos}\n{_short(item.preview)}")

    def push_current(self) -> None:
        before = len(self.store.items)
        # Push manual e' explicito: ignora a supressao por conteudo.
        self._last_written_sig = None
        self._capture_current()
        if len(self.store.items) == before:
            self.status.emit("Nada novo para adicionar")

    def paste_next(self, plain: bool = False) -> None:
        if self._pasting:
            return  # ja ha uma colagem em andamento (evita runaway/duplo-paste)
        item = self.store.peek()
        if item is None:
            self.status.emit("Fila vazia ou concluida — Ctrl+Shift+R para reiniciar")
            QApplication.beep()
            return
        ok = clipboard_io.write_item_to_clipboard(self.clipboard, item, plain=plain)
        if not ok:
            self.status.emit("Falha ao preparar o item para colar")
            return
        # So' arma a supressao quando a escrita deu certo.
        self._last_written_sig = self._item_signature(item)
        self._pasting = True
        delay = int(self.store.settings.get("paste_delay_ms", 130) or 130)
        QTimer.singleShot(delay, lambda: self._do_paste_keys(plain))

    def copy_item(self, item, plain: bool = False) -> bool:
        """Coloca um item no clipboard sem colar (e sem recapturar a propria escrita)."""
        ok = clipboard_io.write_item_to_clipboard(self.clipboard, item, plain=plain)
        if ok:
            self._last_written_sig = self._item_signature(item)
            self.status.emit("Copiado para a área de transferência")
        else:
            self.status.emit("Falha ao copiar o item (arquivo ausente?)")
        return ok

    # ------------------------------------------------------------- internos
    def _hud(self, text: str) -> None:
        if self.store.settings.get("hud_enabled", True):
            self.hud.emit(text)

    def _do_paste_keys(self, plain: bool = False) -> None:
        try:
            win_input.release_modifiers()
            win_input.send_paste()
        except Exception as exc:  # noqa: BLE001
            self._pasting = False
            self.status.emit(
                f"Falha ao injetar Ctrl+V — o app em foco pode exigir admin ({exc})"
            )
            QApplication.beep()
            return  # NAO avanca/consome em caso de falha de injecao

        old = self.store.cursor
        total = len(self.store.items)
        mode = " (texto puro)" if plain else ""
        if self.store.settings.get("consume_on_paste"):
            self.store.consume()
            left = len(self.store.items)
            self.status.emit(f"Colado{mode} e removido — restam {left} na fila")
            head = f"Colado{mode} — restam {left}"
        else:
            self.store.advance()
            if self.store.peek() is None:
                self.status.emit(f"Colado {old + 1}/{total}{mode} — fila concluida")
            else:
                self.status.emit(
                    f"Colado {old + 1}/{total}{mode} — proximo {self.store.cursor + 1}"
                )
            head = f"Colado {old + 1}/{total}{mode}"

        nxt = self.store.peek()
        if nxt is None:
            self._hud(f"{head}\nFila concluída")
        else:
            self._hud(f"{head}\nPróximo: {_short(nxt.preview)}")
        self._pasting = False
        self.paste_done.emit()
