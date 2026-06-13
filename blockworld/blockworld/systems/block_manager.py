"""Менеджер блоков — размещение, выделение, цвета, сигналы."""

from __future__ import annotations

import time

from ursina import Button, camera, color, destroy, raycast

from blockworld.constants import STATE_COLORS


class BlockManager:
    def __init__(self):
        self.blocks = []
        self.selected_blocks = []
        self.hovered_block = None
        self.brain = None

    def update_block_color(self, block):
        if hasattr(block, "cell_data"):
            return
        if hasattr(block, "redstone"):
            r = block.redstone
            r_type = r.get("type")
            p = int(r.get("power", 0))
            if r_type == "lever":
                block.color = color.orange if r.get("on", False) else color.gray
                return
            if r_type == "wire":
                t = max(0.0, min(1.0, p / 15.0))
                block.color = color.rgba(int(255 * (0.6 + 0.4 * t)), int(40 + 120 * t), int(40 * (1.0 - 0.5 * t)), 255)
                return
            if r_type == "lamp":
                block.color = color.yellow if p > 0 else color.gray
                return
        if block.states.get("is_terrain", False):
            block.color = color.gray
        elif block in self.selected_blocks:
            block.color = STATE_COLORS["selected"]
        elif block.states.get("generate", {}).get("active", False):
            block.color = STATE_COLORS["generate_blocks"]
        elif block.states.get("store", {}).get("active", False):
            block.color = STATE_COLORS["store"]
        elif block.states.get("conduct", {}).get("active", False):
            block.color = STATE_COLORS["conduct"]
        elif block.states.get("connect", {}).get("active", False):
            block.color = STATE_COLORS["connect"]
        else:
            block.color = STATE_COLORS["default"]

    def add_block(self, position=None, color_=color.white, is_terrain=False):
        if position is None:
            hit_info = raycast(camera.world_position, camera.forward, distance=50)
            if hit_info and hit_info.hit:
                position = hit_info.entity.position + hit_info.normal
                position = (round(position.x), round(position.y), round(position.z))
            else:
                position = self.get_air_position_at_crosshair()
        if any(b.position == position for b in self.blocks):
            return None
        box = Button(
            color=color_,
            model="cube",
            position=position,
            texture="white_cube",
            parent=__import__("ursina").scene,
            origin_y=0.5,
            collider="box",
        )
        box.states = {"is_terrain": is_terrain}
        box.block_data = {}
        box.state = 0
        box.block_id = len(self.blocks)
        self.blocks.append(box)
        return box

    def get_air_position_at_crosshair(self, player=None):
        from ursina import Vec3
        start_pos = player.position if player else camera.world_position
        direction = camera.forward
        target_pos = start_pos + direction * 10
        target_pos = (round(target_pos.x), round(target_pos.y), round(target_pos.z))
        if target_pos[1] < 2:
            target_pos = (target_pos[0], 2, target_pos[2])
        return target_pos

    def remove_block(self, block):
        if block in self.blocks:
            self.blocks.remove(block)
        if block in self.selected_blocks:
            self.selected_blocks.remove(block)
        destroy(block)

    def update_selection_visual(self):
        for box in self.blocks:
            if not hasattr(box, "states"):
                continue
            if box in self.selected_blocks:
                box.color = STATE_COLORS["selected"]
            else:
                self.update_block_color(box)

    def get_block_by_coord(self, coord):
        for block in self.blocks:
            if block.position == coord:
                return block
        return None

    def get_block_by_id(self, block_id):
        if 0 <= block_id < len(self.blocks):
            return self.blocks[block_id]
        return None

    def send_signal(self, source_coord, target_coord, signal_data):
        source_block = self.get_block_by_coord(source_coord)
        target_block = self.get_block_by_coord(target_coord)
        if not source_block or not target_block:
            return False
        if hasattr(source_block, "state") and source_block.state == 1:
            if source_block.states.get("conduct", {}).get("active", False):
                if not hasattr(target_block, "received_signals"):
                    target_block.received_signals = []
                target_block.received_signals.append({
                    "from": source_coord, "to": target_coord,
                    "data": signal_data, "time": time.time(),
                })
                original_color = target_block.color
                target_block.color = STATE_COLORS["signal"]
                from ursina import invoke
                invoke(lambda b=target_block, c=original_color: setattr(b, "color", c), delay=0.5)
                return True
        return False

    def generate_at_position(self, source_coord, target_coord, generate_data=None):
        source_block = self.get_block_by_coord(source_coord)
        if not source_block or source_block.state != 1:
            return False
        if not source_block.states.get("generate", {}).get("active", False):
            return False
        if self.get_block_by_coord(target_coord) is None:
            new_block = self.add_block(position=target_coord)
            if new_block and generate_data:
                if isinstance(generate_data, dict):
                    new_block.block_data = generate_data.copy()
                else:
                    new_block.block_data = {"value": generate_data}
            return new_block is not None
        target_block = self.get_block_by_coord(target_coord)
        if generate_data:
            if isinstance(generate_data, dict):
                target_block.block_data.update(generate_data)
            else:
                target_block.block_data["value"] = generate_data
        return True
