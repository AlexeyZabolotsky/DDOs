"""Формат передачи данных между блоками.

Данные, описывающие состояния и воздействия, имеют единый формат
«ключ: значение»::

    {
        "state": <значение состояния / действия>,
        "coord": (x, y, z),                # координата воздействия
        "data":  {... любая степень вложенности ...}
    }

Этот формат используется и для команд (что сделать), и для полезной
нагрузки (что передать/сохранить).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, Optional, Tuple

Coord = Tuple[int, int, int]


class Action(str, Enum):
    """Значения поля ``state`` — функции каждого блока.

    Наследование от ``str`` позволяет одинаково работать как с
    ``Action.GENERATE``, так и со строкой ``"generate"``.
    """

    GENERATE = "generate"            # генерация блока
    DESTROY = "destroy"              # уничтожение блока
    SAVE = "save"                    # сохранение данных
    ERASE = "erase"                  # стирание данных
    TRANSMIT = "transmit"            # передача данных
    BLOCK = "block"                  # блокировка передачи
    UNBLOCK = "unblock"              # снятие блокировки передачи
    SELECT = "select"                # выделение группы блоков (в т.ч. по цвету)
    DESELECT = "deselect"            # снятие выделения
    CONNECT = "connect"              # соединение блоков
    DISCONNECT = "disconnect"        # разъединение блоков
    MOVE = "move"                    # перемещение данных соединённой группы


def _ensure_coord(value: Any) -> Coord:
    """Приводит координату к кортежу из трёх целых ``(x, y, z)``."""
    if value is None:
        raise ValueError("coord (координата воздействия) обязательна")
    seq = tuple(value)
    if len(seq) != 3:
        raise ValueError(f"coord должна содержать ровно 3 значения, получено: {seq!r}")
    return (int(seq[0]), int(seq[1]), int(seq[2]))


@dataclass
class Packet:
    """Единица передачи данных формата ``{state, coord, data}``.

    :param state: значение состояния / действия (см. :class:`Action`).
    :param coord: координата воздействия ``(x, y, z)``.
    :param data:  передаваемые данные — словарь любой глубины вложенности.
    """

    state: str
    coord: Coord
    data: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        # Нормализуем state к строковому значению (поддержка Action и str).
        self.state = self.state.value if isinstance(self.state, Action) else str(self.state)
        self.coord = _ensure_coord(self.coord)
        if self.data is None:
            self.data = {}
        if not isinstance(self.data, dict):
            raise TypeError("data должна быть словарём (любой глубины вложенности)")

    # ------------------------------------------------------------------
    # Сериализация формата «ключ: значение».
    # ------------------------------------------------------------------
    def to_dict(self) -> Dict[str, Any]:
        """Возвращает пакет как словарь формата ``{state, coord, data}``."""
        return {
            "state": self.state,
            "coord": tuple(self.coord),
            "data": self.data,
        }

    @classmethod
    def from_dict(cls, raw: Dict[str, Any]) -> "Packet":
        """Создаёт пакет из словаря формата ``{state, coord, data}``.

        Принимает координату как под ключом ``coord``, так и в виде
        отдельных ключей ``x``, ``y``, ``z`` (как в исходном описании
        «координата воздействия: x,y,z»).
        """
        if "coord" in raw:
            coord = raw["coord"]
        elif {"x", "y", "z"} <= set(raw):
            coord = (raw["x"], raw["y"], raw["z"])
        else:
            raise ValueError("в пакете нет координаты (coord или x,y,z)")
        return cls(state=raw["state"], coord=coord, data=raw.get("data", {}))

    def get(self, path: str, default: Any = None) -> Any:
        """Достаёт значение из вложенных данных по пути ``"a.b.c"``."""
        node: Any = self.data
        for key in path.split("."):
            if not isinstance(node, dict) or key not in node:
                return default
            node = node[key]
        return node

    def __repr__(self) -> str:  # pragma: no cover - косметика
        return f"Packet(state={self.state!r}, coord={self.coord}, data={self.data!r})"
