"""Icone do Paste Cascade, desenhado em vetor (nitido em qualquer tamanho).

Conceito: tres folhas em cascata (cada uma mais a frente e mais clara) sobre um
quadrado arredondado grafite (paleta neutra: preto, cinza e branco).

Uso como script (gera o .ico multi-tamanho e um PNG grande em assets/):
    py -m paste_cascade.icon
"""
from __future__ import annotations

import struct
import sys
from pathlib import Path

from PySide6.QtCore import QBuffer, QByteArray, QIODevice, QPointF, QRectF, Qt
from PySide6.QtGui import (
    QBrush,
    QColor,
    QIcon,
    QImage,
    QLinearGradient,
    QPainter,
    QPen,
    QPixmap,
)

ICON_SIZES = (16, 20, 24, 32, 40, 48, 64, 96, 128, 256)
_BASE = 256.0  # o desenho e' feito num espaco 256x256 e escalado


def render_icon(size: int) -> QImage:
    img = QImage(size, size, QImage.Format.Format_ARGB32)
    img.fill(Qt.GlobalColor.transparent)
    p = QPainter(img)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
    p.scale(size / _BASE, size / _BASE)
    detail = size >= 40  # em tamanhos pequenos, so' as formas principais

    # ---- fundo: quadrado arredondado com gradiente ----
    bg = QLinearGradient(QPointF(20, 10), QPointF(236, 246))
    bg.setColorAt(0.0, QColor("#3C3C3C"))
    bg.setColorAt(1.0, QColor("#161616"))
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QBrush(bg))
    p.drawRoundedRect(QRectF(4, 4, 248, 248), 58, 58)

    # brilho suave no topo
    gloss = QLinearGradient(QPointF(0, 4), QPointF(0, 200))
    gloss.setColorAt(0.0, QColor(255, 255, 255, 28))
    gloss.setColorAt(0.5, QColor(255, 255, 255, 6))
    gloss.setColorAt(1.0, QColor(255, 255, 255, 0))
    p.setBrush(QBrush(gloss))
    p.drawRoundedRect(QRectF(4, 4, 248, 248), 58, 58)

    # ---- tres folhas em cascata (de tras para frente) ----
    cards = [  # (x, y, alpha)
        (30, 34, 70),
        (60, 78, 150),
        (90, 122, 255),
    ]
    w, h, r = 138.0, 98.0, 20.0
    for i, (x, y, alpha) in enumerate(cards):
        # sombra
        if detail:
            p.setBrush(QColor(0, 0, 0, 70))
            p.drawRoundedRect(QRectF(x + 3, y + 7, w, h), r, r)
        p.setBrush(QColor(255, 255, 255, alpha))
        p.drawRoundedRect(QRectF(x, y, w, h), r, r)

        front = i == len(cards) - 1
        if detail and not front:
            # "linha" discreta nas folhas de tras, so' para sugerir conteudo
            p.setBrush(QColor(0, 0, 0, 45))
            p.drawRoundedRect(QRectF(x + 20, y + 22, 70, 9), 4.5, 4.5)

    # ---- detalhes da folha da frente ----
    fx, fy = cards[-1][0], cards[-1][1]
    if detail:
        # presilha (clip) no topo da folha da frente
        p.setBrush(QColor("#0E0E0E"))
        p.drawRoundedRect(QRectF(fx + w / 2 - 26, fy - 12, 52, 24), 9, 9)
        p.setBrush(QColor("#6A6A6A"))
        p.drawRoundedRect(QRectF(fx + w / 2 - 12, fy - 5, 24, 9), 4.5, 4.5)
        # linhas de texto
        line = QLinearGradient(QPointF(fx, 0), QPointF(fx + w, 0))
        line.setColorAt(0.0, QColor("#2A2A2A"))
        line.setColorAt(1.0, QColor("#8C8C8C"))
        p.setBrush(QBrush(line))
        p.drawRoundedRect(QRectF(fx + 20, fy + 30, 98, 11), 5.5, 5.5)
        p.drawRoundedRect(QRectF(fx + 20, fy + 54, 70, 11), 5.5, 5.5)
    else:
        # versao simplificada: duas barras grossas
        line = QLinearGradient(QPointF(fx, 0), QPointF(fx + w, 0))
        line.setColorAt(0.0, QColor("#2A2A2A"))
        line.setColorAt(1.0, QColor("#8C8C8C"))
        p.setBrush(QBrush(line))
        p.drawRoundedRect(QRectF(fx + 18, fy + 26, 102, 18), 9, 9)
        p.drawRoundedRect(QRectF(fx + 18, fy + 56, 70, 18), 9, 9)

    p.end()
    return img


def make_app_icon() -> QIcon:
    """QIcon com varios tamanhos (janela, bandeja, barra de tarefas)."""
    icon = QIcon()
    for s in ICON_SIZES:
        icon.addPixmap(QPixmap.fromImage(render_icon(s)))
    return icon


def _png_bytes(img: QImage) -> bytes:
    ba = QByteArray()
    buf = QBuffer(ba)
    buf.open(QIODevice.OpenModeFlag.WriteOnly)
    img.save(buf, "PNG")
    buf.close()
    return bytes(ba)


def save_ico(path: Path, sizes=ICON_SIZES) -> None:
    """Grava um .ico multi-tamanho com entradas PNG (suportado desde o Vista)."""
    entries = [(s, _png_bytes(render_icon(s))) for s in sizes]
    header = struct.pack("<HHH", 0, 1, len(entries))
    offset = 6 + 16 * len(entries)
    directory = b""
    blobs = b""
    for s, data in entries:
        dim = 0 if s >= 256 else s
        directory += struct.pack("<BBBBHHII", dim, dim, 0, 0, 1, 32, len(data), offset)
        blobs += data
        offset += len(data)
    Path(path).write_bytes(header + directory + blobs)


def main() -> int:
    out = Path(__file__).resolve().parent.parent / "assets"
    out.mkdir(exist_ok=True)
    save_ico(out / "paste_cascade.ico")
    render_icon(512).save(str(out / "icon_512.png"), "PNG")
    print(f"Gerado: {out / 'paste_cascade.ico'} e icon_512.png")
    return 0


if __name__ == "__main__":
    sys.exit(main())
