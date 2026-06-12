"""Блок редстоуна с функциями жизненного цикла и передачи данных."""

from __future__ import annotations

import copy
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable

from redstone.message import Action, RedstoneMessage


class BlockType(str, Enum):
    GENERATOR = "генератор"
    RELAY = "реле"
    STORAGE = "хранилище"
    GATE = "шлюз"
    CONNECTOR = "соединитель"


BlockHandler = Callable[["RedstoneBlock", RedstoneMessage], dict[str, Any] | None]


@dataclass
class RedstoneBlock:
    """Один блок в мире редстоуна."""

    x: int
    y: int
    z: int
    block_type: BlockType = BlockType.RELAY
    block_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    состояние: Any = "неактивен"
    цвет: str = "#808080"
    данные: dict[str, Any] = field(default_factory=dict)
    сохранённые_данные: dict[str, Any] = field(default_factory=dict)
    передача_заблокирована: bool = False
    group_id: str | None = None
    connections: set[str] = field(default_factory=set)

    @property
    def координата(self) -> tuple[int, int, int]:
        return (self.x, self.y, self.z)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.block_id,
            "координата": list(self.координата),
            "тип": self.block_type.value,
            "состояние": self.состояние,
            "цвет": self.цвет,
            "данные": copy.deepcopy(self.данные),
            "сохранённые_данные": copy.deepcopy(self.сохранённые_данные),
            "передача_заблокирована": self.передача_заблокирована,
            "group_id": self.group_id,
            "connections": sorted(self.connections),
        }

    # --- Функции блока ---

    def генерация(self, message: RedstoneMessage) -> dict[str, Any]:
        """Создаёт/активирует блок, заполняя его начальными данными."""
        payload = message.передаваемые_данные
        self.состояние = message.состояние or payload.get("состояние", "активен")
        self.цвет = payload.get("цвет", self.цвет)
        if "данные" in payload:
            self.данные.update(copy.deepcopy(payload["данные"]))
        if "тип" in payload:
            self.block_type = BlockType(payload["тип"])
        self.передача_заблокирована = False
        return {"результат": "сгенерирован", "блок": self.to_dict()}

    def уничтожение(self, message: RedstoneMessage) -> dict[str, Any]:
        """Деактивирует блок и очищает рабочие данные."""
        snapshot = self.to_dict()
        self.состояние = message.состояние or "уничтожен"
        self.данные.clear()
        self.передача_заблокирована = True
        self.connections.clear()
        self.group_id = None
        return {"результат": "уничтожен", "было": snapshot}

    def сохранение(self, message: RedstoneMessage) -> dict[str, Any]:
        """Сохраняет текущие данные блока."""
        keys = message.передаваемые_данные.get("ключи")
        if keys:
            self.сохранённые_данные = {
                k: copy.deepcopy(self.данные[k])
                for k in keys
                if k in self.данные
            }
        else:
            self.сохранённые_данные = copy.deepcopy(self.данные)
        if message.передаваемые_данные.get("данные"):
            self.сохранённые_данные.update(
                copy.deepcopy(message.передаваемые_данные["данные"])
            )
        return {
            "результат": "сохранено",
            "сохранённые_данные": copy.deepcopy(self.сохранённые_данные),
        }

    def стирание(self, message: RedstoneMessage) -> dict[str, Any]:
        """Стирает рабочие или сохранённые данные."""
        target = message.передаваемые_данные.get("цель", "рабочие")
        keys = message.передаваемые_данные.get("ключи")
        if target == "сохранённые":
            store = self.сохранённые_данные
        else:
            store = self.данные
        if keys:
            for key in keys:
                store.pop(key, None)
        else:
            store.clear()
        return {"результат": "стёрто", "цель": target}

    def передача(self, message: RedstoneMessage) -> dict[str, Any] | None:
        """Передаёт данные из блока (если передача не заблокирована)."""
        if self.передача_заблокирована:
            return {
                "результат": "отклонено",
                "причина": "передача заблокирована",
            }
        outgoing = message.передаваемые_данные.get(
            "данные", copy.deepcopy(self.данные)
        )
        self.состояние = message.состояние or self.состояние
        return {
            "результат": "передано",
            "от": self.block_id,
            "координата": list(self.координата),
            "данные": copy.deepcopy(outgoing),
        }

    def блокировка_передачи(self, message: RedstoneMessage) -> dict[str, Any]:
        """Блокирует или разблокирует передачу данных."""
        lock = message.передаваемые_данные.get("заблокировать", True)
        self.передача_заблокирована = bool(lock)
        self.состояние = message.состояние or (
            "передача_заблокирована" if self.передача_заблокирована else "передача_разрешена"
        )
        return {
            "результат": "блокировка_обновлена",
            "передача_заблокирована": self.передача_заблокирована,
        }

    def выделение_группы(
        self, message: RedstoneMessage, group_id: str, color: str
    ) -> dict[str, Any]:
        """Включает блок в выделенную группу с цветом состояния."""
        self.group_id = group_id
        self.цвет = message.передаваемые_данные.get("цвет", color)
        self.состояние = message.состояние or "выделен"
        return {
            "результат": "выделен",
            "group_id": group_id,
            "цвет": self.цвет,
        }

    def соединение(self, message: RedstoneMessage, target_id: str) -> dict[str, Any]:
        """Соединяет блок с другим по id."""
        self.connections.add(target_id)
        self.состояние = message.состояние or "соединён"
        return {
            "результат": "соединён",
            "с": target_id,
            "connections": sorted(self.connections),
        }

    def разъединение(self, message: RedstoneMessage, target_id: str) -> dict[str, Any]:
        """Разъединяет блок от другого."""
        self.connections.discard(target_id)
        self.состояние = message.состояние or "разъединён"
        return {
            "результат": "разъединён",
            "от": target_id,
            "connections": sorted(self.connections),
        }

    def перемещение_данных(self, message: RedstoneMessage) -> dict[str, Any]:
        """Перемещает данные внутри блока или из сохранённого слоя."""
        src = message.передаваемые_данные.get("источник", "данные")
        dst = message.передаваемые_данные.get("назначение", "данные")
        payload = message.передаваемые_данные.get("данные", {})
        source_map = {
            "данные": self.данные,
            "сохранённые": self.сохранённые_данные,
        }
        if src not in source_map or dst not in source_map:
            return {"результат": "ошибка", "причина": "неизвестный слой"}
        if payload:
            moved = copy.deepcopy(payload)
        elif src == dst:
            return {"результат": "ошибка", "причина": "источник совпадает с назначением"}
        else:
            moved = copy.deepcopy(source_map[src])
            source_map[src].clear()
        source_map[dst].update(moved)
        self.состояние = message.состояние or "данные_перемещены"
        return {
            "результат": "перемещено",
            "источник": src,
            "назначение": dst,
            "данные": copy.deepcopy(moved),
        }

    def apply_internal_data(self, message: RedstoneMessage) -> dict[str, Any] | None:
        """Применяет данные, уже находящиеся внутри блока (ключ: значение)."""
        embedded = self.данные.get("команда")
        if embedded is None:
            return None
        if isinstance(embedded, dict):
            internal = RedstoneMessage.from_dict(embedded)
        else:
            internal = RedstoneMessage(
                состояние=embedded,
                координата_воздействия=self.координата,
                передаваемые_данные=copy.deepcopy(self.данные.get("параметры", {})),
            )
        internal.координата_воздействия = internal.координата_воздействия or self.координата
        return ACTION_MAP.get(internal.get_action(), lambda *_: None)(self, internal)

    def dispatch(self, message: RedstoneMessage) -> dict[str, Any] | None:
        """Маршрутизирует действие к соответствующей функции блока."""
        action = message.get_action()
        if action is None:
            return self.apply_internal_data(message)
        handler = ACTION_MAP.get(action)
        if handler is None:
            return {"результат": "ошибка", "причина": f"неизвестное действие: {action}"}
        return handler(self, message)


def _wrap(method_name: str) -> BlockHandler:
    def handler(block: RedstoneBlock, message: RedstoneMessage) -> dict[str, Any] | None:
        return getattr(block, method_name)(message)

    return handler


ACTION_MAP: dict[Action, BlockHandler] = {
    Action.GENERATE: _wrap("генерация"),
    Action.DESTROY: _wrap("уничтожение"),
    Action.SAVE: _wrap("сохранение"),
    Action.ERASE: _wrap("стирание"),
    Action.TRANSFER: _wrap("передача"),
    Action.BLOCK_TRANSFER: _wrap("блокировка_передачи"),
    Action.MOVE_DATA: _wrap("перемещение_данных"),
}
