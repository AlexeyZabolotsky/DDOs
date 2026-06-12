"""Управление мышкой.

Любая функция блока вызывается не только пакетом данных, но и нажатием
мышки. :class:`MouseController` превращает событие мышки в тот же самый
:class:`~redstone.packet.Packet` и отдаёт его в :meth:`World.dispatch`,
поэтому оба способа полностью эквивалентны.

Модуль не зависит от GUI: событие :class:`MouseEvent` может прийти из
tkinter, pygame, веб-канваса или из теста — контроллеру всё равно.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, Optional, Tuple

from redstone.packet import Action, Coord, Packet
from redstone.world import World


class MouseButton(str, Enum):
    LEFT = "left"
    RIGHT = "right"
    MIDDLE = "middle"


class Tool(str, Enum):
    """Выбранный инструмент — определяет, какую функцию вызовет клик."""

    GENERATE = "generate"
    DESTROY = "destroy"
    SAVE = "save"
    ERASE = "erase"
    TRANSMIT = "transmit"
    BLOCK = "block"          # ЛКМ — заблокировать, ПКМ — разблокировать
    SELECT = "select"        # ЛКМ — группа по связям, ПКМ — по цвету
    CONNECT = "connect"      # два клика: источник → цель
    DISCONNECT = "disconnect"  # два клика: источник → цель
    MOVE = "move"            # перемещение данных соединённой группы


@dataclass
class MouseEvent:
    """Событие мышки в экранных/мировых координатах.

    :param x, y: координаты клика; ``z`` берётся из активного слоя.
    :param button: какая кнопка нажата.
    """

    x: int
    y: int
    button: MouseButton = MouseButton.LEFT
    z: Optional[int] = None


class MouseController:
    """Переводит клики мышки в пакеты и исполняет их в мире."""

    def __init__(self, world: World, *, tool: Tool = Tool.GENERATE, layer: int = 0) -> None:
        self.world = world
        self.tool = tool
        self.layer = layer  # активный слой z для 2D-кликов
        # Полезная нагрузка для инструментов SAVE / TRANSMIT.
        self.payload: Dict[str, Any] = {}
        # Цвет для выделения (инструмент SELECT, ПКМ).
        self.color: Optional[str] = None
        # Смещение для инструмента MOVE.
        self.delta: Coord = (1, 0, 0)
        # Первый клик для двухкликовых инструментов (CONNECT / DISCONNECT).
        self._pending: Optional[Coord] = None

    # ------------------------------------------------------------------
    def select_tool(self, tool: Tool) -> None:
        self.tool = tool
        self._pending = None  # сбрасываем незавершённый двойной клик

    def _coord(self, event: MouseEvent) -> Coord:
        z = self.layer if event.z is None else event.z
        return (int(event.x), int(event.y), int(z))

    # ------------------------------------------------------------------
    def build_packet(self, event: MouseEvent) -> Optional[Packet]:
        """Строит пакет ``{state, coord, data}`` из события мышки.

        Возвращает ``None``, если клик лишь запоминает первую точку
        двухкликового инструмента (соединение/разъединение).
        """
        coord = self._coord(event)
        tool = self.tool

        if tool is Tool.GENERATE:
            return Packet(Action.GENERATE, coord, {})

        if tool is Tool.DESTROY:
            return Packet(Action.DESTROY, coord, {})

        if tool is Tool.SAVE:
            return Packet(Action.SAVE, coord, {"payload": dict(self.payload)})

        if tool is Tool.ERASE:
            return Packet(Action.ERASE, coord, {})

        if tool is Tool.TRANSMIT:
            return Packet(Action.TRANSMIT, coord, {"payload": dict(self.payload)})

        if tool is Tool.BLOCK:
            action = Action.UNBLOCK if event.button is MouseButton.RIGHT else Action.BLOCK
            return Packet(action, coord, {})

        if tool is Tool.SELECT:
            if event.button is MouseButton.RIGHT:
                # Выделение по цвету блока, на который кликнули.
                block = self.world.get(coord)
                ref_color = self.color if self.color is not None else (block.color if block else None)
                return Packet(Action.SELECT, coord, {"color": ref_color})
            return Packet(Action.SELECT, coord, {"set_color": self.color})

        if tool is Tool.MOVE:
            return Packet(Action.MOVE, coord, {"delta": tuple(self.delta)})

        if tool in (Tool.CONNECT, Tool.DISCONNECT):
            if self._pending is None:
                self._pending = coord  # первый клик — запомнили источник
                return None
            source, self._pending = self._pending, None
            action = Action.CONNECT if tool is Tool.CONNECT else Action.DISCONNECT
            return Packet(action, source, {"target": coord})

        raise ValueError(f"неизвестный инструмент: {tool!r}")

    # ------------------------------------------------------------------
    def click(self, event: MouseEvent) -> Any:
        """Обрабатывает клик: строит пакет и исполняет его в мире."""
        packet = self.build_packet(event)
        if packet is None:
            return None
        return self.world.dispatch(packet)
