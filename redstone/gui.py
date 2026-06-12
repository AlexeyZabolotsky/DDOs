"""Графический интерфейс: управление редстоуном мышью."""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import Any

from redstone.engine import RedstoneEngine
from redstone.message import Action
from redstone.group import GROUP_COLORS


class RedstoneGUI:
    """2D-срез мира (плоскость X-Y при фиксированном Z) с управлением мышью."""

    CELL = 48
    GRID_W = 16
    GRID_H = 12

    def __init__(self, engine: RedstoneEngine | None = None, z_layer: int = 0) -> None:
        self.engine = engine or RedstoneEngine()
        self.z_layer = z_layer
        self._shift = False
        self._ctrl = False
        self._alt = False

        self.root = tk.Tk()
        self.root.title("Редстоун — управление блоками")
        self._build_ui()

    def _build_ui(self) -> None:
        toolbar = ttk.Frame(self.root, padding=4)
        toolbar.pack(fill=tk.X)

        modes = [
            ("Выделение", Action.SELECT_GROUP),
            ("Генерация", Action.GENERATE),
            ("Передача", Action.TRANSFER),
            ("Соединение", Action.CONNECT),
            ("Перемещение", Action.MOVE_DATA),
        ]
        self._mode_var = tk.StringVar(value=Action.SELECT_GROUP.value)
        for label, action in modes:
            ttk.Radiobutton(
                toolbar,
                text=label,
                value=action.value,
                variable=self._mode_var,
                command=lambda a=action: self.engine.set_mouse_mode(a),
            ).pack(side=tk.LEFT, padx=4)

        ttk.Label(toolbar, text="Z:").pack(side=tk.LEFT, padx=(12, 2))
        self._z_var = tk.IntVar(value=self.z_layer)
        ttk.Spinbox(
            toolbar, from_=-5, to=5, width=4, textvariable=self._z_var,
            command=self._on_z_change,
        ).pack(side=tk.LEFT)

        self.canvas = tk.Canvas(
            self.root,
            width=self.GRID_W * self.CELL,
            height=self.GRID_H * self.CELL,
            bg="#1e1e1e",
            highlightthickness=0,
        )
        self.canvas.pack(padx=8, pady=4)
        self.canvas.bind("<Button-1>", self._on_left)
        self.canvas.bind("<Button-3>", self._on_right)
        self.root.bind("<KeyPress-Shift_L>", lambda _: setattr(self, "_shift", True))
        self.root.bind("<KeyRelease-Shift_L>", lambda _: setattr(self, "_shift", False))
        self.root.bind("<KeyPress-Control_L>", lambda _: setattr(self, "_ctrl", True))
        self.root.bind("<KeyRelease-Control_L>", lambda _: setattr(self, "_ctrl", False))
        self.root.bind("<KeyPress-Alt_L>", lambda _: setattr(self, "_alt", True))
        self.root.bind("<KeyRelease-Alt_L>", lambda _: setattr(self, "_alt", False))

        self.log = tk.Text(self.root, height=8, wrap=tk.WORD, font=("Consolas", 10))
        self.log.pack(fill=tk.BOTH, expand=True, padx=8, pady=(0, 8))

        hint = (
            "ЛКМ — действие | ПКМ — уничтожение | "
            "Shift+ЛКМ — сохранение | Shift+ПКМ — перемещение по группе | "
            "Ctrl+ЛКМ — соединение | Ctrl+ПКМ — разъединение | "
            "Alt+ЛКМ — блокировка передачи | Alt+ПКМ — стирание"
        )
        ttk.Label(self.root, text=hint, wraplength=760).pack(padx=8, pady=(0, 8))

        self._draw_grid()
        self.engine.on_mouse(self._on_engine_event)

    def _on_z_change(self) -> None:
        self.z_layer = int(self._z_var.get())
        self._redraw()

    def _modifiers(self) -> dict[str, bool]:
        return {"shift": self._shift, "ctrl": self._ctrl, "alt": self._alt}

    def _cell_from_event(self, event: tk.Event) -> tuple[int, int]:
        x = event.x // self.CELL
        y = event.y // self.CELL
        return int(x), int(y)

    def _on_left(self, event: tk.Event) -> None:
        x, y = self._cell_from_event(event)
        result = self.engine.handle_mouse(x, y, self.z_layer, button=1, modifiers=self._modifiers())
        self._append_log(result)
        self._redraw()

    def _on_right(self, event: tk.Event) -> None:
        x, y = self._cell_from_event(event)
        result = self.engine.handle_mouse(x, y, self.z_layer, button=3, modifiers=self._modifiers())
        self._append_log(result)
        self._redraw()

    def _on_engine_event(self, payload: dict[str, Any]) -> None:
        pass

    def _append_log(self, entry: dict[str, Any]) -> None:
        self.log.insert(tk.END, f"{entry}\n")
        self.log.see(tk.END)

    def _draw_grid(self) -> None:
        for x in range(self.GRID_W + 1):
            px = x * self.CELL
            self.canvas.create_line(px, 0, px, self.GRID_H * self.CELL, fill="#333")
        for y in range(self.GRID_H + 1):
            py = y * self.CELL
            self.canvas.create_line(0, py, self.GRID_W * self.CELL, py, fill="#333")

    def _redraw(self) -> None:
        self.canvas.delete("block")
        for (bx, by, bz), block in self.engine.world.blocks.items():
            if bz != self.z_layer:
                continue
            x0 = bx * self.CELL + 2
            y0 = by * self.CELL + 2
            x1 = x0 + self.CELL - 4
            y1 = y0 + self.CELL - 4
            color = block.цвет or GROUP_COLORS.get("неактивна")
            self.canvas.create_rectangle(
                x0, y0, x1, y1, fill=color, outline="#fff", width=2, tags="block"
            )
            label = str(block.состояние)[:6]
            self.canvas.create_text(
                (x0 + x1) // 2, (y0 + y1) // 2,
                text=label, fill="#000", font=("Arial", 8), tags="block",
            )
            if block.передача_заблокирована:
                self.canvas.create_line(x0, y0, x1, y1, fill="#D50000", width=2, tags="block")

    def run(self) -> None:
        self.root.mainloop()
