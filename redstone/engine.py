"""Движок редстоуна: обработка сообщений и событий мыши."""

from __future__ import annotations

import copy
from typing import Any, Callable

from redstone.block import RedstoneBlock, BlockType
from redstone.group import GROUP_COLORS, RedstoneGroup
from redstone.message import Action, RedstoneMessage
from redstone.world import RedstoneWorld


MouseCallback = Callable[[dict[str, Any]], None]


class RedstoneEngine:
    """
    Центральный движок.

    Принимает команды:
    - через RedstoneMessage (данные внутри блоков)
    - через handle_mouse (нажатие мыши по координатам)
    """

    def __init__(self) -> None:
        self.world = RedstoneWorld()
        self._event_log: list[dict[str, Any]] = []
        self._mouse_mode: Action = Action.SELECT_GROUP
        self._mouse_callbacks: list[MouseCallback] = []
        self._pending_group: RedstoneGroup | None = None
        self._connect_source: RedstoneBlock | None = None

    @property
    def event_log(self) -> list[dict[str, Any]]:
        return list(self._event_log)

    def on_mouse(self, callback: MouseCallback) -> None:
        self._mouse_callbacks.append(callback)

    def set_mouse_mode(self, action: Action) -> None:
        self._mouse_mode = action

    def process(self, message: RedstoneMessage | dict[str, Any]) -> dict[str, Any]:
        """Обрабатывает сообщение в формате ключ: значение."""
        if isinstance(message, dict):
            message = RedstoneMessage.from_dict(message)
        coord = message.координата_воздействия
        if coord is None:
            return self._log({"результат": "ошибка", "причина": "нет координаты"})
        return self._dispatch_at(coord, message)

    def handle_mouse(
        self,
        x: int,
        y: int,
        z: int,
        button: int = 1,
        modifiers: dict[str, bool] | None = None,
    ) -> dict[str, Any]:
        """
        Обрабатывает нажатие мыши.

        button: 1 — левая, 3 — правая
        modifiers: shift, ctrl, alt
        """
        modifiers = modifiers or {}
        action = self._resolve_mouse_action(button, modifiers)
        payload: dict[str, Any] = {"действие": action.value, "кнопка": button}
        if modifiers.get("shift"):
            payload["цвет"] = GROUP_COLORS["выделена"]
        if modifiers.get("ctrl"):
            payload["заблокировать"] = button == 1

        message = RedstoneMessage(
            состояние=action.value,
            координата_воздействия=(x, y, z),
            передаваемые_данные=payload,
        )
        result = self._dispatch_at((x, y, z), message, from_mouse=True)
        for cb in self._mouse_callbacks:
            cb({"координата": (x, y, z), "действие": action.value, "результат": result})
        return result

    def _resolve_mouse_action(self, button: int, modifiers: dict[str, bool]) -> Action:
        if modifiers.get("alt"):
            return Action.BLOCK_TRANSFER if button == 1 else Action.ERASE
        if modifiers.get("ctrl"):
            return Action.CONNECT if button == 1 else Action.DISCONNECT
        if modifiers.get("shift"):
            return Action.SAVE if button == 1 else Action.MOVE_DATA
        if button == 3:
            return Action.DESTROY
        return self._mouse_mode

    def _dispatch_at(
        self,
        coord: tuple[int, int, int],
        message: RedstoneMessage,
        from_mouse: bool = False,
    ) -> dict[str, Any]:
        action = message.get_action()
        x, y, z = coord

        if action == Action.GENERATE:
            result = self._action_generate(x, y, z, message)
        elif action == Action.DESTROY:
            result = self._action_destroy(x, y, z, message)
        else:
            block = self.world.get(x, y, z)
            if block is None:
                if from_mouse and action == Action.SELECT_GROUP:
                    result = self._action_generate(x, y, z, message)
                else:
                    result = {"результат": "ошибка", "причина": "блок не найден"}
            elif action == Action.SELECT_GROUP:
                result = self._action_select_group(block, message)
            elif action == Action.CONNECT:
                result = self._action_connect(block, message)
            elif action == Action.DISCONNECT:
                result = self._action_disconnect(block, message)
            elif action == Action.MOVE_DATA:
                result = self._action_move_data_group(block, message)
            else:
                result = block.dispatch(message) or {"результат": "нет действия"}

        return self._log(result)

    def _action_generate(
        self, x: int, y: int, z: int, message: RedstoneMessage
    ) -> dict[str, Any]:
        existing = self.world.get(x, y, z)
        if existing:
            return existing.генерация(message)
        block_type_raw = message.передаваемые_данные.get("тип", BlockType.RELAY.value)
        block = self.world.place(x, y, z, block_type=BlockType(block_type_raw))
        return block.генерация(message)

    def _action_destroy(
        self, x: int, y: int, z: int, message: RedstoneMessage
    ) -> dict[str, Any]:
        block = self.world.get(x, y, z)
        if block is None:
            return {"результат": "ошибка", "причина": "блок не найден"}
        info = block.уничтожение(message)
        self.world.remove(x, y, z)
        return info

    def _action_select_group(
        self, block: RedstoneBlock, message: RedstoneMessage
    ) -> dict[str, Any]:
        group_id = message.передаваемые_данные.get("group_id")
        group = self.world.get_or_create_group(group_id)
        color = message.передаваемые_данные.get(
            "цвет", GROUP_COLORS.get(message.состояние or "выделена", group.цвет)
        )
        group.set_state(str(message.состояние or "выделена"), color)
        group.add_block(block, message)
        component = self.world.find_connected_component(block)
        for bid in component:
            neighbor = self.world.get_by_id(bid)
            if neighbor:
                group.add_block(neighbor, message)
        return {
            "результат": "группа_выделена",
            "group": group.to_dict(),
            "блок": block.выделение_группы(message, group.group_id, group.цвет),
        }

    def _action_connect(
        self, block: RedstoneBlock, message: RedstoneMessage
    ) -> dict[str, Any]:
        target_id = message.передаваемые_данные.get("цель")
        if target_id:
            target = self.world.get_by_id(str(target_id))
            if target is None:
                return {"результат": "ошибка", "причина": "целевой блок не найден"}
            self.world.connect_blocks(block, target)
            block.соединение(message, target.block_id)
            target.соединение(message, block.block_id)
            self._connect_source = None
            return {"результат": "соединено", "a": block.block_id, "b": target.block_id}

        if self._connect_source is None:
            self._connect_source = block
            block.состояние = "ожидание_соединения"
            return {"результат": "выбран_источник", "блок": block.block_id}
        if self._connect_source.block_id == block.block_id:
            return {"результат": "ошибка", "причина": "нельзя соединить блок с собой"}
        self.world.connect_blocks(self._connect_source, block)
        self._connect_source.соединение(message, block.block_id)
        block.соединение(message, self._connect_source.block_id)
        src = self._connect_source.block_id
        self._connect_source = None
        return {"результат": "соединено", "a": src, "b": block.block_id}

    def _action_disconnect(
        self, block: RedstoneBlock, message: RedstoneMessage
    ) -> dict[str, Any]:
        target_id = message.передаваемые_данные.get("цель")
        if not target_id and block.connections:
            target_id = next(iter(block.connections))
        if not target_id:
            return {"результат": "ошибка", "причина": "нет соединений"}
        target = self.world.get_by_id(str(target_id))
        if target is None:
            return {"результат": "ошибка", "причина": "целевой блок не найден"}
        self.world.disconnect_blocks(block, target)
        block.разъединение(message, target.block_id)
        target.разъединение(message, block.block_id)
        return {"результат": "разъединено", "a": block.block_id, "b": target.block_id}

    def _action_move_data_group(
        self, block: RedstoneBlock, message: RedstoneMessage
    ) -> dict[str, Any]:
        if not block.group_id:
            group = self.world.create_group(состояние="передача")
            component = self.world.find_connected_component(block)
            for bid in component:
                b = self.world.get_by_id(bid)
                if b:
                    group.add_block(b)
        else:
            group = self.world.groups[block.group_id]
        blocks_by_id = {b.block_id: b for b in self.world._by_id.values()}
        moved = group.move_data_across(blocks_by_id, message)
        return {"результат": "данные_перемещены_по_группе", "детали": moved}

    def inject_block_command(
        self, x: int, y: int, z: int, command: dict[str, Any]
    ) -> dict[str, Any]:
        """Записывает команду внутрь блока и выполняет её."""
        block = self.world.get(x, y, z)
        if block is None:
            return {"результат": "ошибка", "причина": "блок не найден"}
        block.данные["команда"] = copy.deepcopy(command)
        if "параметры" in command:
            block.данные["параметры"] = copy.deepcopy(command["параметры"])
        internal = RedstoneMessage.from_dict(command)
        internal.координата_воздействия = (x, y, z)
        result = block.dispatch(internal) or block.apply_internal_data(internal)
        return self._log(result or {"результат": "выполнено"})

    def transfer_between(
        self,
        src: tuple[int, int, int],
        dst: tuple[int, int, int],
        data: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Передаёт данные между двумя блоками по координатам."""
        src_block = self.world.get(*src)
        dst_block = self.world.get(*dst)
        if src_block is None or dst_block is None:
            return {"результат": "ошибка", "причина": "блок не найден"}
        outgoing = src_block.передача(
            RedstoneMessage(
                координата_воздействия=src,
                передаваемые_данные={"данные": data or src_block.данные},
            )
        )
        if outgoing is None or outgoing.get("результат") == "отклонено":
            return outgoing or {"результат": "отклонено"}
        if dst_block.передача_заблокирована:
            return {"результат": "отклонено", "причина": "приём заблокирован"}
        payload = outgoing.get("данные", {})
        dst_block.данные.update(copy.deepcopy(payload))
        dst_block.состояние = "данные_получены"
        return {
            "результат": "передано",
            "от": list(src),
            "к": list(dst),
            "данные": payload,
        }

    def _log(self, entry: dict[str, Any] | None) -> dict[str, Any]:
        if entry is None:
            entry = {"результат": "пусто"}
        self._event_log.append(copy.deepcopy(entry))
        return entry
