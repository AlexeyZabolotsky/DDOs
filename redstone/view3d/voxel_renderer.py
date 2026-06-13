"""Синхронизация мира RedstoneEngine с 3D-вокселями."""

from __future__ import annotations

from typing import Any

from ursina import Entity, color, destroy

from redstone.block import RedstoneBlock, BlockType
from redstone.engine import RedstoneEngine
from redstone.view3d.colors_util import hex_to_ursina
from redstone.view3d.textures import BLOCK_TYPE_TEXTURE, GRASS, DIRT, STONE


class VoxelRenderer:
    """Отображает блоки движка как кубы Minecraft."""

    def __init__(self, engine: RedstoneEngine) -> None:
        self.engine = engine
        self._blocks: dict[tuple[int, int, int], Entity] = {}
        self._terrain: list[Entity] = []
        self._highlights: list[Entity] = []
        self._connection_lines: list[Entity] = []

    def build_terrain(self, radius: int = 20) -> None:
        """Создаёт платформу травы/земли/камня как в Minecraft."""
        for entity in self._terrain:
            destroy(entity)
        self._terrain.clear()

        for x in range(-radius, radius):
            for z in range(-radius, radius):
                self._terrain.append(
                    Entity(
                        model="cube",
                        texture=GRASS,
                        position=(x, 0, z),
                        collider="box",
                        name="terrain",
                    )
                )
                self._terrain.append(
                    Entity(
                        model="cube",
                        texture=DIRT,
                        position=(x, -1, z),
                        collider="box",
                        name="terrain",
                    )
                )
                if (x + z) % 5 == 0:
                    self._terrain.append(
                        Entity(
                            model="cube",
                            texture=STONE,
                            position=(x, -2, z),
                            collider="box",
                            name="terrain",
                        )
                    )

    def sync_all(self) -> None:
        """Полная синхронизация блоков и линий соединений."""
        world_coords = set(self.engine.world.blocks.keys())
        rendered = set(self._blocks.keys())

        for coord in rendered - world_coords:
            self._remove_block(coord)

        for coord in world_coords:
            block = self.engine.world.blocks[coord]
            self._upsert_block(block)

        self._sync_connections()

    def sync_coordinate(self, x: int, y: int, z: int) -> None:
        block = self.engine.world.get(x, y, z)
        if block is None:
            self._remove_block((x, y, z))
        else:
            self._upsert_block(block)
        self._sync_connections()

    def highlight(self, position: tuple[float, float, float] | None) -> None:
        """Подсветка блока под прицелом (белая рамка)."""
        for entity in self._highlights:
            destroy(entity)
        self._highlights.clear()
        if position is None:
            return
        outline = Entity(
            model="cube",
            position=position,
            scale=1.02,
            color=color.rgba(255, 255, 255, 80),
            alpha=0.35,
        )
        outline.shader = None
        self._highlights.append(outline)

    def _upsert_block(self, block: RedstoneBlock) -> None:
        coord = block.координата
        texture = BLOCK_TYPE_TEXTURE.get(block.block_type.value, STONE)
        tint = hex_to_ursina(block.цвет)

        if coord in self._blocks:
            entity = self._blocks[coord]
            entity.texture = texture
            entity.color = tint
            entity.position = (block.x, block.y + 0.5, block.z)
        else:
            entity = Entity(
                model="cube",
                texture=texture,
                color=tint,
                position=(block.x, block.y + 0.5, block.z),
                collider="box",
                name="redstone_block",
            )
            self._blocks[coord] = entity

        if block.передача_заблокирована:
            entity.color = color.rgba(213, 0, 0, 220)

    def _remove_block(self, coord: tuple[int, int, int]) -> None:
        entity = self._blocks.pop(coord, None)
        if entity:
            destroy(entity)

    def _sync_connections(self) -> None:
        for line in self._connection_lines:
            destroy(line)
        self._connection_lines.clear()

        drawn: set[tuple[str, str]] = set()
        for block in self.engine.world.blocks.values():
            for target_id in block.connections:
                pair = tuple(sorted((block.block_id, target_id)))
                if pair in drawn:
                    continue
                drawn.add(pair)
                target = self.engine.world.get_by_id(target_id)
                if target is None:
                    continue
                start = (block.x, block.y + 0.5, block.z)
                end = (target.x, target.y + 0.5, target.z)
                mid = (
                    (start[0] + end[0]) / 2,
                    (start[1] + end[1]) / 2 + 0.15,
                    (start[2] + end[2]) / 2,
                )
                line = Entity(
                    model="cube",
                    color=color.azure,
                    position=mid,
                    scale=(0.08, 0.08, abs(start[0] - end[0]) + abs(start[2] - end[2]) or 0.5),
                )
                self._connection_lines.append(line)

    def placement_position(
        self, hit_entity: Entity | None, normal: Any
    ) -> tuple[int, int, int] | None:
        """Вычисляет координату для установки блока по лучу."""
        if hit_entity is None:
            return None
        pos = hit_entity.position
        nx, ny, nz = (
            int(round(normal.x)),
            int(round(normal.y)),
            int(round(normal.z)),
        )
        if hit_entity.name == "terrain":
            base = (int(round(pos.x)), int(round(pos.y)), int(round(pos.z)))
        else:
            base = (
                int(round(pos.x)),
                int(round(pos.y - 0.5)),
                int(round(pos.z)),
            )
        return (base[0] + nx, base[1] + ny, base[2] + nz)

    def target_coordinate(
        self, hit_entity: Entity | None
    ) -> tuple[int, int, int] | None:
        if hit_entity is None or hit_entity.name != "redstone_block":
            return None
        pos = hit_entity.position
        return (
            int(round(pos.x)),
            int(round(pos.y - 0.5)),
            int(round(pos.z)),
        )
