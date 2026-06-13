"""Упрощённый движок redstone из исходного кода."""

from __future__ import annotations

import time


class BlockState:
    def __init__(self, r_type="wire", power=0, facing="north"):
        self.type = r_type
        self.power = int(power)
        self.facing = facing
        self.pulse_ticks = 0


class RedstoneEngine:
    TICK_RATE = 20.0

    def __init__(self, block_manager):
        self.block_manager = block_manager
        self.pos_to_state = {}
        self.pending_updates = set()
        self._last_tick_time = time.time()
        self._tick_accum = 0.0

    @staticmethod
    def neighbors(pos):
        x, y, z = pos
        return [(x + 1, y, z), (x - 1, y, z), (x, y + 1, z), (x, y - 1, z), (x, y, z + 1), (x, y, z - 1)]

    def place_component(self, pos, r_type, facing="north"):
        initial_power = 15 if r_type == "torch" else 0
        state = BlockState(r_type=r_type, power=initial_power, facing=facing)
        self.pos_to_state[pos] = state
        block = self.block_manager.get_block_by_coord(pos)
        if block:
            block.redstone = {"type": r_type, "power": initial_power, "facing": facing, "on": initial_power > 0}
            self.block_manager.update_block_color(block)
        self.mark_for_update(pos)
        for n in self.neighbors(pos):
            self.mark_for_update(n)

    def remove_component(self, pos):
        if pos in self.pos_to_state:
            del self.pos_to_state[pos]
            block = self.block_manager.get_block_by_coord(pos)
            if block and hasattr(block, "redstone"):
                delattr(block, "redstone")
                self.block_manager.update_block_color(block)

    def toggle_lever(self, pos):
        st = self.pos_to_state.get(pos)
        if not st or st.type != "lever":
            return
        st.power = 0 if st.power > 0 else 15
        block = self.block_manager.get_block_by_coord(pos)
        if block and hasattr(block, "redstone"):
            block.redstone["on"] = st.power > 0
            block.redstone["power"] = st.power
            self.block_manager.update_block_color(block)
        self.mark_for_update(pos)

    def activate_component(self, pos):
        st = self.pos_to_state.get(pos)
        if not st:
            return
        if st.type == "lever":
            self.toggle_lever(pos)
        elif st.type == "button":
            st.power = 15
            st.pulse_ticks = 10

    def mark_for_update(self, pos):
        self.pending_updates.add(pos)

    def compute_input_power(self, pos):
        max_power = 0
        for n in self.neighbors(pos):
            st = self.pos_to_state.get(n)
            if not st:
                continue
            p = st.power if st.type != "wire" else max(0, st.power - 1)
            max_power = max(max_power, p)
        return max_power

    def tick(self):
        if not self.pending_updates:
            return
        to_process = list(self.pending_updates)
        self.pending_updates.clear()
        changed = []
        for pos in to_process:
            st = self.pos_to_state.get(pos)
            if not st:
                continue
            if st.type == "wire":
                new_power = self.compute_input_power(pos)
                if new_power != st.power:
                    st.power = new_power
                    changed.append(pos)
            elif st.type == "lamp":
                new_power = 15 if self.compute_input_power(pos) > 0 else 0
                if new_power != st.power:
                    st.power = new_power
                    changed.append(pos)
            elif st.type == "torch":
                new_power = 0 if self.compute_input_power(pos) > 0 else 15
                if new_power != st.power:
                    st.power = new_power
                    changed.append(pos)
        for pos in changed:
            block = self.block_manager.get_block_by_coord(pos)
            st = self.pos_to_state.get(pos)
            if block and hasattr(block, "redstone") and st:
                block.redstone["power"] = st.power
                block.redstone["on"] = st.power > 0
                self.block_manager.update_block_color(block)
            for n in self.neighbors(pos):
                self.mark_for_update(n)

    def maybe_tick(self):
        now = time.time()
        dt = now - self._last_tick_time
        self._last_tick_time = now
        self._tick_accum += dt
        while self._tick_accum >= 1.0 / self.TICK_RATE:
            self.tick()
            self._tick_accum -= 1.0 / self.TICK_RATE
