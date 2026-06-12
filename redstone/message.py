"""Формат передачи данных: ключ — значение."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class Action(str, Enum):
    """Доступные действия над блоками и группами."""

    GENERATE = "генерация"
    DESTROY = "уничтожение"
    SAVE = "сохранение"
    ERASE = "стирание"
    TRANSFER = "передача"
    BLOCK_TRANSFER = "блокировка_передачи"
    SELECT_GROUP = "выделение_группы"
    CONNECT = "соединение"
    DISCONNECT = "разъединение"
    MOVE_DATA = "перемещение_данных"


@dataclass
class RedstoneMessage:
    """
    Сообщение редстоуна.

    Формат:
        {
            "состояние": <значение>,
            "координата_воздействия": [x, y, z],
            "передаваемые_данные": {<любая вложенность>}
        }
    """

    состояние: Any = None
    координата_воздействия: tuple[int, int, int] | None = None
    передаваемые_данные: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> RedstoneMessage:
        coord = data.get("координата_воздействия")
        if coord is not None:
            coord = tuple(coord)
        return cls(
            состояние=data.get("состояние"),
            координата_воздействия=coord,
            передаваемые_данные=dict(data.get("передаваемые_данные", {})),
        )

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {}
        if self.состояние is not None:
            result["состояние"] = self.состояние
        if self.координата_воздействия is not None:
            result["координата_воздействия"] = list(self.координата_воздействия)
        if self.передаваемые_данные:
            result["передаваемые_данные"] = self.передаваемые_данные
        return result

    def get_action(self) -> Action | None:
        """Извлекает действие из передаваемых данных."""
        raw = self.передаваемые_данные.get("действие")
        if raw is None:
            raw = self.передаваемые_данные.get("action")
        if raw is None and isinstance(self.состояние, str):
            raw = self.состояние
        if raw is None:
            return None
        try:
            return Action(raw)
        except ValueError:
            return None

    def nested(self, *keys: str, default: Any = None) -> Any:
        """Доступ к вложенным передаваемым данным."""
        node: Any = self.передаваемые_данные
        for key in keys:
            if not isinstance(node, dict):
                return default
            node = node.get(key, default)
        return node
