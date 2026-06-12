"""Мир блоков: хранилище, граф соединений и единый диспетчер команд.

`World` — единая точка, через которую проходят оба способа вызова функций:

* данные внутри блоков (пакеты :class:`~redstone.packet.Packet`);
* нажатия мышки (через :mod:`redstone.mouse`, которые тоже превращаются в
  пакеты).

Оба способа сходятся в :meth:`World.dispatch`.
"""

from __future__ import annotations

import copy
from collections import deque
from typing import Any, Dict, List, Optional

from redstone.block import Block
from redstone.group import Group
from redstone.packet import Action, Coord, Packet


class World:
    """Контейнер блоков и реализация всех операций."""

    def __init__(self) -> None:
        self._blocks: Dict[Coord, Block] = {}
        # Журнал выполненных команд (полезно для отладки / GUI).
        self.log: List[Packet] = []

    # ------------------------------------------------------------------
    # Базовый доступ.
    # ------------------------------------------------------------------
    def get(self, coord: Coord) -> Optional[Block]:
        return self._blocks.get(tuple(coord))

    def require(self, coord: Coord) -> Block:
        block = self.get(coord)
        if block is None:
            raise KeyError(f"в координате {tuple(coord)} нет блока")
        return block

    def __contains__(self, coord: object) -> bool:
        return tuple(coord) in self._blocks  # type: ignore[arg-type]

    def __len__(self) -> int:
        return len(self._blocks)

    @property
    def blocks(self) -> List[Block]:
        return [self._blocks[c] for c in sorted(self._blocks)]

    # ------------------------------------------------------------------
    # Генерация и уничтожение.
    # ------------------------------------------------------------------
    def generate(self, coord: Coord, **opts: Any) -> Block:
        """Создаёт (генерирует) блок. Если блок уже есть — обновляет поля."""
        coord = tuple(coord)  # type: ignore[assignment]
        block = self._blocks.get(coord)
        if block is None:
            block = Block(coord=coord, world=self, **opts)
            self._blocks[coord] = block
            block.state = opts.get("state", "active")
        else:
            for key, value in opts.items():
                setattr(block, key, value)
        return block

    def destroy(self, coord: Coord) -> bool:
        """Уничтожает блок. Возвращает ``True``, если блок существовал."""
        block = self.get(coord)
        if block is None:
            return False
        block.destroy()
        return True

    def _remove_block(self, coord: Coord) -> None:
        self._blocks.pop(tuple(coord), None)

    # ------------------------------------------------------------------
    # Соединение и разъединение (неориентированный граф).
    # ------------------------------------------------------------------
    def connect(self, a: Coord, b: Coord) -> None:
        block_a = self.require(a)
        block_b = self.require(b)
        if block_a.coord == block_b.coord:
            raise ValueError("нельзя соединить блок сам с собой")
        block_a.connections.add(block_b.coord)
        block_b.connections.add(block_a.coord)

    def disconnect(self, a: Coord, b: Coord) -> None:
        block_a = self.get(a)
        block_b = self.get(b)
        if block_a is not None:
            block_a.connections.discard(tuple(b))
        if block_b is not None:
            block_b.connections.discard(tuple(a))

    # ------------------------------------------------------------------
    # Группы и выделение.
    # ------------------------------------------------------------------
    def connected_group(self, coord: Coord) -> Group:
        """Возвращает соединённую группу (компоненту связности) блока."""
        start = self.require(coord)
        seen: set = {start.coord}
        queue: deque = deque([start.coord])
        while queue:
            current = queue.popleft()
            block = self._blocks.get(current)
            if block is None:
                continue
            for nxt in block.connections:
                if nxt not in seen and nxt in self._blocks:
                    seen.add(nxt)
                    queue.append(nxt)
        return Group(self, (self._blocks[c] for c in seen))

    def select(
        self,
        *,
        color: Optional[str] = None,
        state: Optional[str] = None,
        coords: Optional[List[Coord]] = None,
        set_color: Optional[str] = None,
    ) -> Group:
        """Выделяет группу блоков по фильтру.

        :param color: выделить блоки указанного цвета.
        :param state: выделить блоки указанного состояния.
        :param coords: выделить блоки по списку координат.
        :param set_color: присвоить выделенным блокам новый цвет.
        """
        if coords is not None:
            chosen = [self._blocks[tuple(c)] for c in coords if tuple(c) in self._blocks]
        else:
            chosen = [
                b
                for b in self._blocks.values()
                if (color is None or b.color == color)
                and (state is None or b.state == state)
            ]
        group = Group(self, chosen)
        group.select(color=set_color)
        return group

    def deselect_all(self) -> None:
        for block in self._blocks.values():
            block.selected = False

    # ------------------------------------------------------------------
    # Передача данных по соединённой группе.
    # ------------------------------------------------------------------
    def propagate(self, source: Coord, payload: Dict[str, Any]) -> List[Block]:
        """Передаёт ``payload`` от блока-источника по соединениям.

        Передача идёт только через блоки, у которых ``transmitting=True``.
        Заблокированный блок останавливает распространение по своей ветке.
        Возвращает список блоков, сохранивших данные.
        """
        start = self.require(source)
        if not start.transmitting:
            return []

        received: List[Block] = []
        seen: set = {start.coord}
        queue: deque = deque([start.coord])
        while queue:
            current = queue.popleft()
            block = self._blocks.get(current)
            if block is None:
                continue
            block.save(copy.deepcopy(payload), merge=True)
            block.state = "transmitting"
            received.append(block)
            for nxt in block.connections:
                neighbour = self._blocks.get(nxt)
                if neighbour is None or nxt in seen:
                    continue
                # Через заблокированный блок данные дальше не идут.
                if not neighbour.transmitting:
                    continue
                seen.add(nxt)
                queue.append(nxt)
        return received

    # ------------------------------------------------------------------
    # Единый диспетчер: и данные-пакеты, и клики мышки приходят сюда.
    # ------------------------------------------------------------------
    def dispatch(self, packet: Packet) -> Any:
        """Выполняет команду, описанную пакетом ``{state, coord, data}``."""
        if isinstance(packet, dict):
            packet = Packet.from_dict(packet)
        self.log.append(packet)
        action = packet.state
        data = packet.data
        coord = packet.coord

        if action == Action.GENERATE:
            return self.generate(coord, **data.get("opts", {}))

        if action == Action.DESTROY:
            return self.destroy(coord)

        if action == Action.SAVE:
            block = self.require(coord)
            return block.save(data.get("payload", data), merge=data.get("merge", True))

        if action == Action.ERASE:
            block = self.require(coord)
            return block.erase(*data.get("keys", []))

        if action == Action.TRANSMIT:
            block = self.require(coord)
            return block.transmit(data.get("payload", data))

        if action == Action.BLOCK:
            return self.require(coord).block_transmission()

        if action == Action.UNBLOCK:
            return self.require(coord).unblock_transmission()

        if action == Action.SELECT:
            if any(k in data for k in ("color", "state", "coords")):
                return self.select(
                    color=data.get("color"),
                    state=data.get("state"),
                    coords=data.get("coords"),
                    set_color=data.get("set_color"),
                )
            return self.require(coord).select(color=data.get("set_color"))

        if action == Action.DESELECT:
            block = self.get(coord)
            if block is not None:
                block.deselect()
            else:
                self.deselect_all()
            return block

        if action == Action.CONNECT:
            target = tuple(data["target"])
            self.connect(coord, target)
            return self.require(coord)

        if action == Action.DISCONNECT:
            target = tuple(data["target"])
            self.disconnect(coord, target)
            return self.get(coord)

        if action == Action.MOVE:
            delta = tuple(data.get("delta", (0, 0, 0)))
            return self.require(coord).move_group_data(delta)

        raise ValueError(f"неизвестное состояние/действие: {action!r}")

    # ------------------------------------------------------------------
    def snapshot(self) -> List[Dict[str, Any]]:
        """Снимок состояния всех блоков."""
        return [b.snapshot() for b in self.blocks]
