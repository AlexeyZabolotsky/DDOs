"""Группы связанных блоков с цветовыми состояниями."""

from __future__ import annotations

import copy
import uuid
from dataclasses import dataclass, field
from typing import Any

from redstone.block import RedstoneBlock
from redstone.message import RedstoneMessage


# Палитра состояний групп
GROUP_COLORS: dict[str, str] = {
    "неактивна": "#808080",
    "активна": "#00C853",
    "выделена": "#FFD600",
    "передача": "#2979FF",
    "блокировка": "#D50000",
    "соединена": "#AA00FF",
    "ошибка": "#FF6D00",
}


@dataclass
class RedstoneGroup:
    """Группа блоков, объединённых соединениями или выделением."""

    group_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    name: str = ""
    состояние: str = "неактивна"
    цвет: str = GROUP_COLORS["неактивна"]
    block_ids: set[str] = field(default_factory=set)

    def to_dict(self) -> dict[str, Any]:
        return {
            "group_id": self.group_id,
            "name": self.name,
            "состояние": self.состояние,
            "цвет": self.цвет,
            "block_ids": sorted(self.block_ids),
        }

    def add_block(self, block: RedstoneBlock, message: RedstoneMessage | None = None) -> None:
        self.block_ids.add(block.block_id)
        block.group_id = self.group_id
        if message:
            block.цвет = message.передаваемые_данные.get("цвет", self.цвет)
            block.состояние = message.состояние or self.состояние
        else:
            block.цвет = self.цвет
            block.состояние = self.состояние

    def remove_block(self, block: RedstoneBlock) -> None:
        self.block_ids.discard(block.block_id)
        if block.group_id == self.group_id:
            block.group_id = None
            block.цвет = GROUP_COLORS["неактивна"]

    def set_state(self, состояние: str, color: str | None = None) -> None:
        self.состояние = состояние
        self.цвет = color or GROUP_COLORS.get(состояние, self.цвет)

    def move_data_across(
        self,
        blocks: dict[str, RedstoneBlock],
        message: RedstoneMessage,
    ) -> list[dict[str, Any]]:
        """
        Перемещает данные по всем соединённым блокам группы.
        Данные текут только если ни один блок на пути не блокирует передачу.
        """
        payload = copy.deepcopy(
            message.передаваемые_данные.get("данные", {})
        )
        if not payload:
            return [{"результат": "ошибка", "причина": "нет данных для перемещения"}]

        results: list[dict[str, Any]] = []
        visited: set[str] = set()
        queue = list(self.block_ids)

        while queue:
            block_id = queue.pop(0)
            if block_id in visited:
                continue
            visited.add(block_id)
            block = blocks.get(block_id)
            if block is None:
                continue
            if block.передача_заблокирована:
                results.append({
                    "результат": "пропущен",
                    "блок": block_id,
                    "причина": "передача заблокирована",
                })
                continue
            block.данные.update(copy.deepcopy(payload))
            block.состояние = message.состояние or "данные_получены"
            block.цвет = self.цвет
            results.append({
                "результат": "получено",
                "блок": block_id,
                "координата": list(block.координата),
            })
            for neighbor_id in block.connections:
                if neighbor_id in self.block_ids and neighbor_id not in visited:
                    queue.append(neighbor_id)

        self.set_state("передача", GROUP_COLORS["передача"])
        return results
