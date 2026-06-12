"""Необязательный GUI на tkinter.

Если tkinter недоступен (как на части серверов), модуль импортируется без
ошибок, а попытка запустить :func:`run` подскажет, чего не хватает. Ядро
(:mod:`redstone.world`, :mod:`redstone.mouse`) работает полностью без GUI.

Запуск (при наличии tkinter и дисплея)::

    python -m redstone.gui
"""

from __future__ import annotations

from typing import Optional

from redstone.mouse import MouseButton, MouseController, MouseEvent, Tool
from redstone.world import World

try:  # tkinter может отсутствовать в headless-окружении
    import tkinter as tk

    _TK_AVAILABLE = True
except Exception:  # pragma: no cover - зависит от окружения
    tk = None  # type: ignore[assignment]
    _TK_AVAILABLE = False


CELL = 56  # размер клетки в пикселях
COLS = 16
ROWS = 12

TOOL_KEYS = {
    "g": Tool.GENERATE,
    "d": Tool.DESTROY,
    "s": Tool.SAVE,
    "e": Tool.ERASE,
    "t": Tool.TRANSMIT,
    "b": Tool.BLOCK,
    "v": Tool.SELECT,
    "c": Tool.CONNECT,
    "x": Tool.DISCONNECT,
    "m": Tool.MOVE,
}


class RedstoneGUI:  # pragma: no cover - требует дисплея
    """Простейший 2D-редактор поля блоков на tkinter."""

    def __init__(self) -> None:
        if not _TK_AVAILABLE:
            raise RuntimeError(
                "tkinter недоступен. Установите python3-tk или используйте "
                "headless-режим: см. redstone.demo и redstone.mouse."
            )
        self.world = World()
        self.mouse = MouseController(self.world, tool=Tool.GENERATE)

        self.root = tk.Tk()
        self.root.title("Redstone — блоки и передача данных")
        self.status = tk.StringVar()
        self.canvas = tk.Canvas(
            self.root, width=COLS * CELL, height=ROWS * CELL, bg="#1d1f21"
        )
        self.canvas.pack()
        tk.Label(self.root, textvariable=self.status, anchor="w").pack(fill="x")

        self.canvas.bind("<Button-1>", lambda e: self._on_click(e, MouseButton.LEFT))
        self.canvas.bind("<Button-3>", lambda e: self._on_click(e, MouseButton.RIGHT))
        for key, tool in TOOL_KEYS.items():
            self.root.bind(key, lambda _e, t=tool: self._set_tool(t))

        self._refresh()

    # ------------------------------------------------------------------
    def _set_tool(self, tool: Tool) -> None:
        self.mouse.select_tool(tool)
        self._refresh()

    def _on_click(self, event: "tk.Event", button: MouseButton) -> None:
        col = event.x // CELL
        row = event.y // CELL
        self.mouse.click(MouseEvent(x=int(col), y=int(row), button=button))
        self._refresh()

    # ------------------------------------------------------------------
    def _refresh(self) -> None:
        self.canvas.delete("all")
        for c in range(COLS):
            for r in range(ROWS):
                self.canvas.create_rectangle(
                    c * CELL, r * CELL, (c + 1) * CELL, (r + 1) * CELL,
                    outline="#33363b",
                )
        for block in self.world.blocks:
            x, y, _z = block.coord
            if not (0 <= x < COLS and 0 <= y < ROWS):
                continue
            fill = block.color or ("#888" if block.transmitting else "#553333")
            self.canvas.create_rectangle(
                x * CELL + 4, y * CELL + 4, (x + 1) * CELL - 4, (y + 1) * CELL - 4,
                fill=fill, outline="#fff" if block.selected else "#000", width=2,
            )
            for nx, ny, _nz in block.connections:
                self.canvas.create_line(
                    x * CELL + CELL / 2, y * CELL + CELL / 2,
                    nx * CELL + CELL / 2, ny * CELL + CELL / 2,
                    fill="#e0b000", width=2,
                )
        self.status.set(
            f"Инструмент: {self.mouse.tool.value}  |  блоков: {len(self.world)}  "
            f"|  клавиши: g d s e t b v c x m"
        )

    def run(self) -> None:
        self.root.mainloop()


def run() -> None:  # pragma: no cover - требует дисплея
    RedstoneGUI().run()


if __name__ == "__main__":  # pragma: no cover
    run()
