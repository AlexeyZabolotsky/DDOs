"""Процедурные пиксельные текстуры в стиле Minecraft."""

from __future__ import annotations

import random
from typing import Sequence

from ursina import Texture

try:
    from PIL import Image
except ImportError:  # pragma: no cover
    Image = None  # type: ignore


def _noise_pixel(base: Sequence[int], spread: int = 18) -> tuple[int, int, int]:
    return tuple(
        max(0, min(255, c + random.randint(-spread, spread)))
        for c in base
    )


def pixel_texture(
    base_rgb: Sequence[int],
    name: str = "block",
    size: int = 16,
    spread: int = 18,
) -> Texture:
    """Создаёт шумовую пиксельную текстуру 16×16."""
    if Image is None:
        raise ImportError("Для 3D-режима установите pillow: pip install pillow")

    img = Image.new("RGB", (size, size))
    pixels = img.load()
    for y in range(size):
        for x in range(size):
            pixels[x, y] = _noise_pixel(base_rgb, spread)
    tex = Texture(img)
    tex.name = name
    return tex


# Палитра блоков (как в Minecraft)
GRASS = pixel_texture((95, 159, 53), "grass", spread=22)
DIRT = pixel_texture((134, 96, 67), "dirt")
STONE = pixel_texture((125, 125, 125), "stone", spread=12)
REDSTONE = pixel_texture((168, 28, 28), "redstone")
GOLD = pixel_texture((229, 192, 0), "gold")
IRON = pixel_texture((200, 200, 200), "iron", spread=10)
WOOD = pixel_texture((160, 118, 52), "wood")
GLASS = pixel_texture((175, 215, 237), "glass", spread=8)
OBSIDIAN = pixel_texture((20, 18, 30), "obsidian", spread=6)

BLOCK_TYPE_TEXTURE = {
    "генератор": REDSTONE,
    "реле": STONE,
    "хранилище": WOOD,
    "шлюз": IRON,
    "соединитель": GOLD,
}
