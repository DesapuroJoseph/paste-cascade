"""Modelo de dados dos itens da fila."""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class ItemKind(str, Enum):
    TEXT = "text"
    IMAGE = "image"
    FILES = "files"


@dataclass
class ClipItem:
    id: int
    kind: ItemKind
    text: Optional[str] = None
    image_file: Optional[str] = None       # nome do PNG dentro de blobs/
    files: list = field(default_factory=list)  # lista de caminhos absolutos
    preview: str = ""
    width: int = 0                          # imagens: dimensoes
    height: int = 0
    image_hash: Optional[str] = None        # imagens: digest dos pixels (p/ dedup/assinatura)
    html: Optional[str] = None              # texto: versao HTML original (formatacao), se houver
    pinned: bool = False                    # fixado: nao sai no "Limpar" nem no limite de itens
    created: float = field(default_factory=lambda: time.time())

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "kind": self.kind.value,
            "text": self.text,
            "image_file": self.image_file,
            "files": list(self.files),
            "preview": self.preview,
            "width": self.width,
            "height": self.height,
            "image_hash": self.image_hash,
            "html": self.html,
            "pinned": self.pinned,
            "created": self.created,
        }

    @staticmethod
    def from_dict(d: dict) -> "ClipItem":
        return ClipItem(
            id=int(d["id"]),
            kind=ItemKind(d.get("kind", "text")),
            text=d.get("text"),
            image_file=d.get("image_file"),
            files=list(d.get("files") or []),
            preview=d.get("preview", ""),
            width=int(d.get("width", 0) or 0),
            height=int(d.get("height", 0) or 0),
            image_hash=d.get("image_hash") or None,
            html=d.get("html") or None,
            pinned=bool(d.get("pinned", False)),
            created=float(d.get("created", 0.0) or 0.0),
        )
