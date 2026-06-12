"""Преобразование цветов для 3D-рендера."""

from __future__ import annotations


def hex_to_rgb(hex_color: str) -> tuple[int, int, int]:
    value = hex_color.lstrip("#")
    if len(value) == 3:
        value = "".join(ch * 2 for ch in value)
    r, g, b = int(value[0:2], 16), int(value[2:4], 16), int(value[4:6], 16)
    return r, g, b


def hex_to_ursina(hex_color: str) -> tuple[float, float, float, float]:
    r, g, b = hex_to_rgb(hex_color)
    return (r / 255, g / 255, b / 255, 1.0)
