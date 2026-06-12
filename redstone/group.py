"""Группа блoков — результат выделения или соединённый компонент.

Группа умеет выделять блоки (в том числе цветом), снимать выделение и
перемещать данные соединённой группы как единое целое.
"""

from __future__ import annotations

import copy
from typing import TYPE_CHECKING, Any, Dict, Iterable, Iterator, List, Optional

from redstone.packet import Coord

if TYPE_CHECKING:  # pragma: no cover
    from redstone.block import Block
    from redstone.world import World


class Group:
    """Набор блоков, с которыми можно работать как с единым целым."""

    def __init__(self, world: "World", blocks: Iterable["Block"]) -> None:
        self.world = world
        # Сохраняем уникальные блоки в стабильном порядке (по координате).
        seen: Dict[Coord, "Block"] = {}
        for block in blocks:
            seen[block.coord] = block
        self._blocks: List["Block"] = [seen[c] for c in sorted(seen)]

    # ------------------------------------------------------------------
    def __iter__(self) -> Iterator["Block"]:
        return iter(self._blocks)

    def __len__(self) -> int:
        return len(self._blocks)

    def __bool__(self) -> bool:
        return bool(self._blocks)

    @property
    def coords(self) -> List[Coord]:
        return [b.coord for b in self._blocks]

    # ------------------------------------------------------------------
    # Выделение (в том числе цветом / сменой состояния).
    # ------------------------------------------------------------------
    def select(self, color: Optional[str] = None) -> "Group":
        for block in self._blocks:
            block.selected = True
            if color is not None:
                block.color = color
        return self

    def deselect(self) -> "Group":
        for block in self._blocks:
            block.selected = False
        return self

    def set_color(self, color: str) -> "Group":
        for block in self._blocks:
            block.color = color
        return self

    # ------------------------------------------------------------------
    # Перемещение данных соединённой группы.
    # ------------------------------------------------------------------
    def move_data(self, delta: Coord) -> "Group":
        """Перемещает данные группы на смещение ``delta = (dx, dy, dz)``.

        Данные каждого блока переносятся в блок, находящийся по смещённой
        координате (если он есть в мире). Исходные блоки очищаются. Так
        «двигаются» данные соединённой группы, а сами блоки остаются на
        местах.
        """
        dx, dy, dz = delta
        # Сначала снимаем все данные, чтобы перенос не зависел от порядка
        # обхода и не перетирал ещё не перенесённые блоки.
        pending: List[tuple] = []
        for block in self._blocks:
            x, y, z = block.coord
            target = (x + dx, y + dy, z + dz)
            pending.append((target, copy.deepcopy(block.data)))
            block.data = {}
            block.state = "idle"

        for target, payload in pending:
            dst = self.world.get(target)
            if dst is not None and payload:
                dst.save(payload, merge=True)
        return self

    # ------------------------------------------------------------------
    def snapshot(self) -> List[Dict[str, Any]]:
        return [b.snapshot() for b in self._blocks]

    def __repr__(self) -> str:  # pragma: no cover - косметика
        return f"Group({self.coords!r})"
