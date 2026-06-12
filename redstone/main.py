"""Точка входа: GUI или демо из командной строки."""

from __future__ import annotations

import argparse


def main() -> None:
    parser = argparse.ArgumentParser(description="Система редстоуна на Python")
    parser.add_argument(
        "--demo", action="store_true", help="Запустить консольную демонстрацию API"
    )
    parser.add_argument(
        "--z", type=int, default=0, help="Слой Z для отображения в GUI"
    )
    args = parser.parse_args()

    if args.demo:
        from redstone.demo import run_demo
        run_demo()
    else:
        from redstone.gui import RedstoneGUI
        RedstoneGUI(z_layer=args.z).run()


if __name__ == "__main__":
    main()
