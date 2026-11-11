"""Leitura e escrita do clipboard do Windows via Qt (texto / imagem / arquivos)."""
from __future__ import annotations

import hashlib
from typing import Optional, Tuple

from PySide6.QtCore import QMimeData, QUrl
from PySide6.QtGui import QClipboard, QImage

from . import config
from .models import ClipItem, ItemKind


def image_digest(img: QImage) -> Optional[str]:
    """Digest dos PIXELS da imagem (independe do encoding do PNG).

    Dedup/assinatura por dimensoes descartava duas capturas diferentes de mesmo
    tamanho; por conteudo isso nao acontece mais.
    """
    try:
        conv = img.convertToFormat(QImage.Format.Format_ARGB32)
        size = int(conv.sizeInBytes())
        data = bytes(conv.constBits())[:size]
        h = hashlib.sha256()
        h.update(f"{conv.width()}x{conv.height()}:".encode("ascii"))
        h.update(data)
        return h.hexdigest()
    except Exception:
        return None


def read_html(clipboard: QClipboard) -> Optional[str]:
    """HTML do clipboard (formatacao de Word/navegador), ou None."""
    md = clipboard.mimeData()
    if md is None or not md.hasHtml():
        return None
    return md.html() or None


def read_clipboard(clipboard: QClipboard) -> Optional[Tuple[str, object]]:
    """Le o conteudo atual do clipboard.

    Retorna ("text", str) | ("image", QImage) | ("files", list[str]) | None.
    Ordem de prioridade: arquivos > imagem > texto.
    """
    md = clipboard.mimeData()
    if md is None:
        return None

    # 1) Arquivos (Explorer): urls locais
    if md.hasUrls():
        local = []
        for u in md.urls():
            if u.isLocalFile():
                p = u.toLocalFile()
                if p:
                    local.append(p)
        if local:
            return ("files", local)

    # 2) Imagem
    if md.hasImage():
        img = clipboard.image()
        if img is not None and not img.isNull():
            return ("image", img)

    # 3) Texto
    if md.hasText():
        t = md.text()
        if t:
            return ("text", t)

    return None


def write_item_to_clipboard(clipboard: QClipboard, item: ClipItem, plain: bool = False) -> bool:
    """Coloca o item no clipboard do sistema. Retorna True se deu certo.

    plain=True forca texto puro mesmo que o item tenha HTML guardado.
    """
    try:
        if item.kind == ItemKind.TEXT:
            if item.html and not plain:
                md = QMimeData()
                md.setText(item.text or "")
                md.setHtml(item.html)
                clipboard.setMimeData(md)
            else:
                clipboard.setText(item.text or "")
            return True

        if item.kind == ItemKind.IMAGE and item.image_file:
            path = config.blobs_dir() / item.image_file
            img = QImage(str(path))
            if img.isNull():
                return False
            clipboard.setImage(img)
            return True

        if item.kind == ItemKind.FILES and item.files:
            md = QMimeData()
            md.setUrls([QUrl.fromLocalFile(p) for p in item.files])
            # fallback em texto com os caminhos (apps que nao aceitam arquivos)
            md.setText("\n".join(item.files))
            clipboard.setMimeData(md)
            return True
    except Exception:
        return False

    return False
