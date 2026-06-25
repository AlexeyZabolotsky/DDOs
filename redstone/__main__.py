"""Запуск redstone.

  python -m redstone          — изометрический 3D (tkinter, Minecraft-style)
  python -m redstone --fps    — 3D от первого лица (Ursina)
  python -m redstone.demo     — консольная демонстрация
  python -m redstone.view3d   — то же, что --fps
"""

from __future__ import annotations

import argparse


def main() -> None:
    parser = argparse.ArgumentParser(description="Редстоун — симуляция блоков")
    parser.add_argument(
        "--fps",
        action="store_true",
        help="3D от первого лица (Ursina) вместо изометрического tkinter",
    )
    args = parser.parse_args()

    if args.fps:
        from redstone.view3d.minecraft_fp import run_minecraft_fp

        run_minecraft_fp()
    else:
        from redstone.ui import main as run_ui

        run_ui()


if __name__ == "__main__":
    main()
