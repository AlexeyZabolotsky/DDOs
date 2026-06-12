"""Redstone — модель блоков с передачей данных в формате "ключ: значение".

Пакет реализует «редстоун»-подобную систему блоков на чистом Python (без
внешних зависимостей). У каждого блока есть набор функций:

* генерация и уничтожение блока;
* сохранение и стирание данных;
* передача данных и блокировка передачи;
* выделение группы блоков (в том числе по цвету / состоянию);
* соединение и разъединение блоков;
* перемещение данных соединённых групп блоков.

Любая функция вызывается двумя способами:

1. Через данные внутри блоков — пакетом :class:`~redstone.packet.Packet`
   формата ``{state, coord, data}`` (см. :mod:`redstone.packet`).
2. Нажатием мышки — событием :class:`~redstone.mouse.MouseEvent`, которое
   контроллер мышки превращает в такой же пакет.

Оба пути сходятся в единый диспетчер :meth:`redstone.world.World.dispatch`,
поэтому поведение всегда одинаково.
"""

from redstone.packet import Packet, Action
from redstone.block import Block
from redstone.group import Group
from redstone.world import World
from redstone.mouse import MouseEvent, MouseButton, MouseController, Tool

__all__ = [
    "Packet",
    "Action",
    "Block",
    "Group",
    "World",
    "MouseEvent",
    "MouseButton",
    "MouseController",
    "Tool",
]
