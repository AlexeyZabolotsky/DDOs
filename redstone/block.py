"""Блок редстоуна и его функции.

У каждого блока есть полный набор функций из задания. Кросс-блочные
операции (соединение, передача, перемещение группы) блок выполняет через
ссылку на :class:`~redstone.world.World`, но вызываются они как методы
самого блока — «функции у каждого блока».
"""

from __future__ import annotations

import copy
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Set

from redstone.packet import Coord

if TYPE_CHECKING:  # pragma: no cover
    from redstone.group import Group
    from redstone.world import World


def _deep_merge(dst: Dict[str, Any], src: Dict[str, Any]) -> Dict[str, Any]:
    """Рекурсивно сливает ``src`` в ``dst`` (словари любой вложенности)."""
    for key, value in src.items():
        if isinstance(value, dict) and isinstance(dst.get(key), dict):
            _deep_merge(dst[key], value)
        else:
            dst[key] = copy.deepcopy(value)
    return dst


@dataclass
class Block:
    """Один блок в мире.

    :param coord: координата блока ``(x, y, z)``.
    :param color: цвет / визуальное состояние (используется при выделении).
    :param state: функциональное состояние блока.
    :param data:  сохранённые данные (словарь любой глубины вложенности).
    :param transmitting: разрешена ли передача данных через блок.
    :param selected: выделен ли блок.
    """

    coord: Coord
    color: Optional[str] = None
    state: str = "idle"
    data: Dict[str, Any] = field(default_factory=dict)
    transmitting: bool = True
    selected: bool = False
    connections: Set[Coord] = field(default_factory=set)
    world: Optional["World"] = field(default=None, repr=False)

    # ------------------------------------------------------------------
    # Генерация и уничтожение.
    # ------------------------------------------------------------------
    def destroy(self) -> None:
        """Уничтожает блок: разрывает связи и удаляет из мира."""
        if self.world is None:
            return
        for other_coord in list(self.connections):
            self.disconnect(other_coord)
        self.world._remove_block(self.coord)
        self.state = "destroyed"

    def spawn(self, coord: Coord, **opts: Any) -> "Block":
        """Генерация: блок создаёт (порождает) новый блок в координате."""
        if self.world is None:
            raise RuntimeError("блок не привязан к миру")
        return self.world.generate(coord, **opts)

    # ------------------------------------------------------------------
    # Сохранение и стирание данных.
    # ------------------------------------------------------------------
    def save(self, payload: Dict[str, Any], *, merge: bool = True) -> "Block":
        """Сохраняет данные в блок.

        :param merge: при ``True`` — глубокое слияние с уже сохранёнными
            данными; при ``False`` — полная замена.
        """
        if not isinstance(payload, dict):
            raise TypeError("payload должен быть словарём")
        if merge:
            _deep_merge(self.data, payload)
        else:
            self.data = copy.deepcopy(payload)
        self.state = "stored"
        return self

    def erase(self, *keys: str) -> "Block":
        """Стирает данные.

        Без аргументов очищает всё; с ключами — удаляет указанные верхние
        ключи.
        """
        if keys:
            for key in keys:
                self.data.pop(key, None)
        else:
            self.data.clear()
        if not self.data:
            self.state = "idle"
        return self

    # ------------------------------------------------------------------
    # Передача данных и блокировка передачи.
    # ------------------------------------------------------------------
    def block_transmission(self) -> "Block":
        """Блокирует передачу данных через блок."""
        self.transmitting = False
        return self

    def unblock_transmission(self) -> "Block":
        """Снимает блокировку передачи."""
        self.transmitting = True
        return self

    def transmit(self, payload: Dict[str, Any]) -> List["Block"]:
        """Передаёт данные по соединённой группе блоков.

        Возвращает список блоков, которые приняли данные. Заблокированные
        блоки данные не пропускают и не сохраняют.
        """
        if self.world is None:
            raise RuntimeError("блок не привязан к миру")
        return self.world.propagate(self.coord, payload)

    # ------------------------------------------------------------------
    # Соединение и разъединение.
    # ------------------------------------------------------------------
    def connect(self, other: "Coord | Block") -> "Block":
        """Соединяет блок с другим блоком."""
        if self.world is None:
            raise RuntimeError("блок не привязан к миру")
        other_coord = other.coord if isinstance(other, Block) else other
        self.world.connect(self.coord, other_coord)
        return self

    def disconnect(self, other: "Coord | Block") -> "Block":
        """Разъединяет блок с другим блоком."""
        if self.world is None:
            raise RuntimeError("блок не привязан к миру")
        other_coord = other.coord if isinstance(other, Block) else other
        self.world.disconnect(self.coord, other_coord)
        return self

    # ------------------------------------------------------------------
    # Выделение (в том числе по цвету).
    # ------------------------------------------------------------------
    def select(self, color: Optional[str] = None) -> "Group":
        """Выделяет всю соединённую группу блока.

        :param color: если задан — всем блокам группы присваивается этот
            цвет (выделение цветом / изменение состояния группы).
        """
        if self.world is None:
            raise RuntimeError("блок не привязан к миру")
        group = self.world.connected_group(self.coord)
        group.select(color=color)
        return group

    def deselect(self) -> "Block":
        """Снимает выделение с блока."""
        self.selected = False
        return self

    # ------------------------------------------------------------------
    # Перемещение данных соединённой группы.
    # ------------------------------------------------------------------
    def move_group_data(self, delta: Coord) -> "Group":
        """Перемещает данные соединённой группы на смещение ``delta``."""
        if self.world is None:
            raise RuntimeError("блок не привязан к миру")
        group = self.world.connected_group(self.coord)
        group.move_data(delta)
        return group

    # ------------------------------------------------------------------
    # Сериализация в формат «ключ: значение».
    # ------------------------------------------------------------------
    def snapshot(self) -> Dict[str, Any]:
        """Возвращает состояние блока словарём."""
        return {
            "coord": tuple(self.coord),
            "color": self.color,
            "state": self.state,
            "data": copy.deepcopy(self.data),
            "transmitting": self.transmitting,
            "selected": self.selected,
            "connections": sorted(self.connections),
        }
