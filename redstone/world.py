"""Трёхмерный мир блоков редстоуна."""

from __future__ import annotations

from typing import Any

from redstone.block import BlockType, RedstoneBlock
from redstone.group import RedstoneGroup


class RedstoneWorld:
    """Хранит блоки по координатам и управляет группами."""

    def __init__(self) -> None:
        self._blocks: dict[tuple[int, int, int], RedstoneBlock] = {}
        self._by_id: dict[str, RedstoneBlock] = {}
        self._groups: dict[str, RedstoneGroup] = {}

    @property
    def blocks(self) -> dict[tuple[int, int, int], RedstoneBlock]:
        return self._blocks

    @property
    def groups(self) -> dict[str, RedstoneGroup]:
        return self._groups

    def get(self, x: int, y: int, z: int) -> RedstoneBlock | None:
        return self._blocks.get((x, y, z))

    def get_by_id(self, block_id: str) -> RedstoneBlock | None:
        return self._by_id.get(block_id)

    def place(
        self,
        x: int,
        y: int,
        z: int,
        block_type: BlockType = BlockType.RELAY,
        **kwargs: Any,
    ) -> RedstoneBlock:
        coord = (x, y, z)
        if coord in self._blocks:
            raise ValueError(f"Блок уже существует в {coord}")
        block = RedstoneBlock(x=x, y=y, z=z, block_type=block_type, **kwargs)
        self._blocks[coord] = block
        self._by_id[block.block_id] = block
        return block

    def remove(self, x: int, y: int, z: int) -> RedstoneBlock | None:
        block = self._blocks.pop((x, y, z), None)
        if block is None:
            return None
        self._by_id.pop(block.block_id, None)
        if block.group_id and block.group_id in self._groups:
            self._groups[block.group_id].remove_block(block)
        for other in self._by_id.values():
            other.connections.discard(block.block_id)
        return block

    def create_group(self, name: str = "", состояние: str = "выделена") -> RedstoneGroup:
        group = RedstoneGroup(name=name, состояние=состояние)
        self._groups[group.group_id] = group
        return group

    def get_or_create_group(self, group_id: str | None) -> RedstoneGroup:
        if group_id and group_id in self._groups:
            return self._groups[group_id]
        group = RedstoneGroup()
        self._groups[group.group_id] = group
        return group

    def connect_blocks(self, block_a: RedstoneBlock, block_b: RedstoneBlock) -> None:
        block_a.connections.add(block_b.block_id)
        block_b.connections.add(block_a.block_id)

    def disconnect_blocks(self, block_a: RedstoneBlock, block_b: RedstoneBlock) -> None:
        block_a.connections.discard(block_b.block_id)
        block_b.connections.discard(block_a.block_id)

    def find_connected_component(self, start: RedstoneBlock) -> set[str]:
        """Возвращает id всех блоков, связанных с начальным."""
        visited: set[str] = set()
        stack = [start.block_id]
        while stack:
            bid = stack.pop()
            if bid in visited:
                continue
            visited.add(bid)
            block = self._by_id.get(bid)
            if block is None:
                continue
            for neighbor in block.connections:
                if neighbor not in visited:
                    stack.append(neighbor)
        return visited

    def to_dict(self) -> dict[str, Any]:
        return {
            "блоки": [b.to_dict() for b in self._blocks.values()],
            "группы": [g.to_dict() for g in self._groups.values()],
        }
