"""Armazenamento: fila + historico + cursor da cascata + lixeira (desfazer) + persistencia."""
from __future__ import annotations

import dataclasses
import json
import os
import tempfile
import time
from pathlib import Path
from typing import Optional

from PySide6.QtCore import QObject, Signal
from PySide6.QtGui import QImage

from . import config
from .clipboard_io import image_digest
from .models import ClipItem, ItemKind

MAX_HTML_CHARS = 200_000   # HTML maior que isso e' descartado (fica so' o texto)
TRASH_DEPTH = 20           # quantas remocoes podem ser desfeitas


class ClipStore(QObject):
    changed = Signal()          # a fila mudou (adicao/remocao/reordenacao)
    cursor_changed = Signal()   # apenas o cursor da cascata mudou
    history_changed = Signal()  # o historico mudou

    def __init__(self) -> None:
        super().__init__()
        self.items: list[ClipItem] = []
        self.history: list[ClipItem] = []   # mais antigo primeiro
        self.cursor: int = 0
        self.settings: dict = dict(config.DEFAULT_SETTINGS)
        self._next_id: int = 1
        # Lixeira: cada entrada e' um grupo de remocoes [(indice, item), ...]
        self._trash: list[list[tuple[int, ClipItem]]] = []
        self.load()

    # ------------------------------------------------------------------ ids
    def _alloc_id(self) -> int:
        i = self._next_id
        self._next_id += 1
        return i

    # ---------------------------------------------------------- persistencia
    def load(self) -> None:
        # ---- settings ----
        try:
            sp = config.settings_path()
            if sp.exists():
                data = json.loads(sp.read_text(encoding="utf-8"))
                if isinstance(data, dict):
                    merged = dict(config.DEFAULT_SETTINGS)
                    for k, v in data.items():
                        if k in config.DEFAULT_SETTINGS:
                            merged[k] = v
                    self.settings = merged
        except Exception:
            self.settings = dict(config.DEFAULT_SETTINGS)

        # ---- fila (parsing defensivo: erro de metadado NUNCA descarta os itens) ----
        items: list[ClipItem] = []
        cursor = 0
        next_id = 1
        loaded_ok = False
        ip = config.items_path()
        if ip.exists():
            raw = self._read_json(ip)
            if isinstance(raw, dict):
                items = self._parse_items(raw.get("items"))
                try:
                    cursor = int(raw.get("cursor", 0))
                except Exception:
                    cursor = 0
                try:
                    next_id = int(raw.get("next_id", 0))
                except Exception:
                    next_id = 0
                loaded_ok = True

        # ---- historico ----
        history: list[ClipItem] = []
        hist_ok = True  # arquivo ausente conta como ok; corrompido, nao
        hp = config.history_path()
        if hp.exists():
            raw = self._read_json(hp)
            if isinstance(raw, dict):
                history = self._parse_items(raw.get("items"))
            else:
                hist_ok = False

        max_id = max([it.id for it in items] + [it.id for it in history], default=0)
        self._next_id = max(next_id, max_id + 1)
        self.items = items
        self.history = history
        self.cursor = cursor
        self._clamp_cursor()
        self._migrate_image_hashes()

        # GC de blobs orfaos SO' quando tudo carregou bem (nunca apos falha,
        # para nao apagar imagens de dados que so' nao puderam ser lidos).
        if loaded_ok and hist_ok:
            self._collect_blobs()
        self._sweep_tmp()

    def _read_json(self, path: Path):
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            self._quarantine(path)  # JSON invalido -> guarda copia, nao sobrescreve
            return None

    @staticmethod
    def _parse_items(raw_list) -> list[ClipItem]:
        out: list[ClipItem] = []
        if not isinstance(raw_list, list):
            return out
        for d in raw_list:
            try:
                out.append(ClipItem.from_dict(d))
            except Exception:
                continue
        return out

    def _migrate_image_hashes(self) -> None:
        """Imagens antigas (sem image_hash) ganham o digest a partir do PNG."""
        cache: dict[str, Optional[str]] = {}
        for it in self.items + self.history:
            if it.kind != ItemKind.IMAGE or it.image_hash or not it.image_file:
                continue
            if it.image_file not in cache:
                try:
                    img = QImage(str(config.blobs_dir() / it.image_file))
                    cache[it.image_file] = None if img.isNull() else image_digest(img)
                except Exception:
                    cache[it.image_file] = None
            it.image_hash = cache[it.image_file]

    def save(self) -> None:
        try:
            payload = {
                "version": config.VERSION,
                "cursor": self.cursor,
                "next_id": self._next_id,
                "items": [it.to_dict() for it in self.items],
            }
            self._atomic_write(
                config.items_path(), json.dumps(payload, ensure_ascii=False, indent=2)
            )
        except Exception:
            pass

    def save_history(self) -> None:
        try:
            payload = {
                "version": config.VERSION,
                "items": [it.to_dict() for it in self.history],
            }
            self._atomic_write(
                config.history_path(), json.dumps(payload, ensure_ascii=False)
            )
        except Exception:
            pass

    def save_settings(self) -> None:
        try:
            self._atomic_write(
                config.settings_path(),
                json.dumps(self.settings, ensure_ascii=False, indent=2),
            )
        except Exception:
            pass

    @staticmethod
    def _atomic_write(path: Path, text: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(text)
            os.replace(tmp, path)  # atomico no Windows, substitui destino
        except Exception:
            try:
                if os.path.exists(tmp):
                    os.remove(tmp)
            except OSError:
                pass
            raise

    def _quarantine(self, path: Path) -> None:
        try:
            bak = path.with_name(f"{path.stem}.corrupt-{int(time.time())}.json")
            os.replace(str(path), str(bak))
        except Exception:
            pass

    def _collect_blobs(self) -> None:
        """Apaga PNGs que nao sao mais referenciados (fila, historico ou lixeira)."""
        try:
            referenced = set()
            groups = [self.items, self.history] + [[it for _, it in g] for g in self._trash]
            for group in groups:
                for it in group:
                    if it.kind == ItemKind.IMAGE and it.image_file:
                        referenced.add(it.image_file)
            for p in config.blobs_dir().glob("*.png"):
                if p.name not in referenced:
                    try:
                        p.unlink()
                    except OSError:
                        pass
        except Exception:
            pass

    def _sweep_tmp(self) -> None:
        try:
            for p in config.data_dir().glob("*.tmp"):
                try:
                    p.unlink()
                except OSError:
                    pass
        except Exception:
            pass

    # ------------------------------------------------------------- utilidades
    @staticmethod
    def missing_files(item: ClipItem) -> list:
        """Caminhos de um item FILES que nao existem mais (lista vazia = tudo ok)."""
        if item.kind != ItemKind.FILES:
            return []
        return [p for p in item.files if not os.path.exists(p)]

    @staticmethod
    def _same_content(a: ClipItem, b: ClipItem) -> bool:
        if a.kind != b.kind:
            return False
        if a.kind == ItemKind.TEXT:
            return a.text == b.text and a.html == b.html
        if a.kind == ItemKind.FILES:
            return list(a.files) == list(b.files)
        if a.kind == ItemKind.IMAGE:
            return bool(a.image_hash) and a.image_hash == b.image_hash
        return False

    @staticmethod
    def _text_preview(text: str, n: int = 200) -> str:
        t = " ".join(text.split())
        return (t[:n] + "…") if len(t) > n else t

    # -------------------------------------------------------------- captura
    def add_text(self, text: str, html: Optional[str] = None) -> Optional[ClipItem]:
        if text is None:
            return None
        if html is not None and len(html) > MAX_HTML_CHARS:
            html = None
        item = ClipItem(
            id=0,
            kind=ItemKind.TEXT,
            text=text,
            html=html,
            preview=self._text_preview(text),
        )
        return self._capture(item)

    def add_files(self, paths: list) -> Optional[ClipItem]:
        paths = [p for p in paths if p]
        if not paths:
            return None
        first = os.path.basename(paths[0].rstrip("/\\")) or paths[0]
        extra = f" (+{len(paths) - 1})" if len(paths) > 1 else ""
        item = ClipItem(
            id=0,
            kind=ItemKind.FILES,
            files=paths,
            preview=f"{len(paths)} arquivo(s): {first}{extra}",
        )
        return self._capture(item)

    def add_image(self, image: QImage) -> Optional[ClipItem]:
        if image is None or image.isNull():
            return None
        w, h = int(image.width()), int(image.height())
        digest = image_digest(image)
        probe = ClipItem(id=0, kind=ItemKind.IMAGE, image_hash=digest)
        if self._is_dup_of_last(probe):
            return None
        item_id = self._alloc_id()
        fname = f"img_{item_id}.png"
        try:
            if not image.save(str(config.blobs_dir() / fname), "PNG"):
                return None
        except Exception:
            return None
        item = ClipItem(
            id=item_id,
            kind=ItemKind.IMAGE,
            image_file=fname,
            width=w,
            height=h,
            image_hash=digest,
            preview=f"Imagem {w}x{h}",
        )
        self._append(item)
        return item

    def _is_dup_of_last(self, item: ClipItem) -> bool:
        if self.settings.get("dedup_consecutive") and self.items:
            return self._same_content(self.items[-1], item)
        return False

    def _capture(self, item: ClipItem) -> Optional[ClipItem]:
        if self._is_dup_of_last(item):
            return None
        item.id = self._alloc_id()
        self._append(item)
        return item

    def _append(self, item: ClipItem, record: bool = True) -> None:
        self.items.append(item)
        self._enforce_limit()
        self.save()
        self.changed.emit()
        if record:
            self._record_history(item)

    def _enforce_limit(self) -> None:
        """Remove os mais antigos NAO fixados alem do limite."""
        maxn = int(self.settings.get("max_items", 200) or 0)
        if maxn <= 0 or len(self.items) <= maxn:
            return
        excess = len(self.items) - maxn
        keep: list[ClipItem] = []
        before_cursor = 0
        for idx, it in enumerate(self.items):
            if excess > 0 and not it.pinned:
                excess -= 1
                if idx < self.cursor:
                    before_cursor += 1
            else:
                keep.append(it)
        self.items = keep
        self.cursor = max(0, self.cursor - before_cursor)
        self._collect_blobs()

    # ------------------------------------------------------------- historico
    def _record_history(self, item: ClipItem) -> None:
        maxn = int(self.settings.get("history_max", 100) or 0)
        if maxn <= 0:
            return
        if self.history and self._same_content(self.history[-1], item):
            return
        self.history.append(dataclasses.replace(item, id=self._alloc_id(), pinned=False))
        trimmed = False
        while len(self.history) > maxn:
            self.history.pop(0)
            trimmed = True
        if trimmed:
            self._collect_blobs()
        self.save_history()
        self.history_changed.emit()

    def enqueue_from_history(self, hist_ids: list) -> int:
        """Copia itens do historico para o fim da fila. Retorna quantos entraram."""
        by_id = {it.id: it for it in self.history}
        n = 0
        for hid in hist_ids:
            src = by_id.get(hid)
            if src is None:
                continue
            copy = dataclasses.replace(
                src, id=self._alloc_id(), pinned=False, created=time.time()
            )
            self._append(copy, record=False)
            n += 1
        return n

    def remove_history(self, hist_ids: list) -> None:
        ids = set(hist_ids)
        before = len(self.history)
        self.history = [it for it in self.history if it.id not in ids]
        if len(self.history) != before:
            self._collect_blobs()
            self.save_history()
            self.history_changed.emit()

    def clear_history(self) -> None:
        if not self.history:
            return
        self.history = []
        self._collect_blobs()
        self.save_history()
        self.history_changed.emit()

    # ----------------------------------------------------- remocao / desfazer
    def _push_trash(self, group: list) -> None:
        if group:
            self._trash.append(group)
            if len(self._trash) > TRASH_DEPTH:
                del self._trash[0]

    def remove_at(self, index: int) -> None:
        self.remove_many([index])

    def remove_many(self, indices: list) -> None:
        idxs = sorted({i for i in indices if 0 <= i < len(self.items)})
        if not idxs:
            return
        self._push_trash([(i, self.items[i]) for i in idxs])
        self.cursor -= sum(1 for i in idxs if i < self.cursor)
        for i in reversed(idxs):
            self.items.pop(i)
        self._clamp_cursor()
        self.save()
        self.changed.emit()

    def clear(self) -> None:
        """Remove tudo que NAO esta fixado (desfazivel)."""
        idxs = [i for i, it in enumerate(self.items) if not it.pinned]
        if not idxs:
            return
        self.remove_many(idxs)
        self.cursor = 0
        self.save()
        self.cursor_changed.emit()

    def can_undo(self) -> bool:
        return bool(self._trash)

    def undo_remove(self) -> int:
        """Restaura o ultimo grupo removido. Retorna quantos itens voltaram."""
        if not self._trash:
            return 0
        group = self._trash.pop()
        was_done = self.cursor >= len(self.items)
        first_idx = None
        for idx, it in sorted(group, key=lambda t: t[0]):
            idx = min(idx, len(self.items))
            self.items.insert(idx, it)
            if first_idx is None:
                first_idx = idx
            if idx <= self.cursor:
                self.cursor += 1
        if was_done and first_idx is not None:
            self.cursor = first_idx  # fila estava concluida: restaurado volta a ser colavel
        self._clamp_cursor()
        self.save()
        self.changed.emit()
        return len(group)

    # ------------------------------------------------------------- edicao
    def set_pinned(self, indices: list, value: bool) -> None:
        changed = False
        for i in indices:
            if 0 <= i < len(self.items) and self.items[i].pinned != value:
                self.items[i].pinned = value
                changed = True
        if changed:
            self.save()
            self.changed.emit()

    def edit_text(self, index: int, text: str) -> bool:
        if not (0 <= index < len(self.items)):
            return False
        it = self.items[index]
        if it.kind != ItemKind.TEXT:
            return False
        self.items[index] = dataclasses.replace(
            it, text=text, html=None, preview=self._text_preview(text)
        )
        self.save()
        self.changed.emit()
        return True

    def duplicate(self, index: int) -> bool:
        if not (0 <= index < len(self.items)):
            return False
        src = self.items[index]
        copy = dataclasses.replace(src, id=self._alloc_id(), pinned=False, created=time.time())
        self.items.insert(index + 1, copy)
        if index + 1 <= self.cursor:
            self.cursor += 1  # mantem o cursor no mesmo item (ou no fim, se concluida)
        self.save()
        self.changed.emit()
        return True

    def move(self, src: int, dst: int) -> None:
        if src == dst:
            return
        if not (0 <= src < len(self.items)):
            return
        dst = max(0, min(dst, len(self.items) - 1))
        cur = self.items[self.cursor] if 0 <= self.cursor < len(self.items) else None
        it = self.items.pop(src)
        self.items.insert(dst, it)
        if cur is not None:
            self.cursor = self.items.index(cur)
        self.save()
        self.changed.emit()

    def reorder_by_ids(self, ids: list) -> None:
        by_id = {it.id: it for it in self.items}
        new = [by_id[i] for i in ids if i in by_id]
        if len(new) == len(self.items):
            cur = self.items[self.cursor] if 0 <= self.cursor < len(self.items) else None
            self.items = new
            self.cursor = new.index(cur) if cur is not None else len(new)
            self.save()
            self.changed.emit()
        else:
            # ids inconsistentes (edge de multi-selecao no drag): a view pode ter
            # reordenado visualmente — forca ressincronizacao com a ordem real.
            self.changed.emit()

    # ------------------------------------------------------- cursor / cascata
    def _clamp_cursor(self) -> None:
        if not self.items:
            self.cursor = 0
        else:
            self.cursor = max(0, min(self.cursor, len(self.items)))

    def peek(self) -> Optional[ClipItem]:
        if 0 <= self.cursor < len(self.items):
            return self.items[self.cursor]
        return None

    def advance(self) -> None:
        """Avanca o cursor apos colar (modo manter + cursor)."""
        self.cursor += 1
        if self.cursor >= len(self.items):
            if self.settings.get("loop") and self.items:
                self.cursor = 0
            else:
                self.cursor = len(self.items)  # sentinela de "fim"
        self.save()
        self.cursor_changed.emit()

    def consume(self) -> None:
        """Remove o item recem-colado (modo consumir). Nao vai para a lixeira:
        o item foi usado e continua no historico."""
        if 0 <= self.cursor < len(self.items):
            self.items.pop(self.cursor)
            if self.settings.get("loop") and self.items:
                self.cursor = self.cursor % len(self.items)
            self._clamp_cursor()
            self._collect_blobs()
            self.save()
            self.changed.emit()

    def reset_cursor(self) -> None:
        self.cursor = 0
        self.save()
        self.cursor_changed.emit()

    def retreat(self) -> bool:
        """Volta o cursor um item. Retorna False se ja estava no primeiro."""
        n = len(self.items)
        if n == 0:
            return False
        if self.cursor <= 0:
            if not self.settings.get("loop"):
                return False
            new = n - 1  # loop: do inicio volta para o fim
        else:
            new = min(self.cursor, n) - 1  # cursor == n (fim) volta para o ultimo
        self.cursor = new
        self.save()
        self.cursor_changed.emit()
        return True

    def set_cursor(self, index: int) -> None:
        if 0 <= index <= len(self.items):
            self.cursor = index
            self.save()
            self.cursor_changed.emit()
