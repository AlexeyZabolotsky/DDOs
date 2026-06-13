"""Система клеток — упрощённая версия."""

from __future__ import annotations

import random
import time
from collections import defaultdict

from blockworld.constants import CELL_TYPES, MAX_CELLS, STATE_COLORS


class CellSystem:
    def __init__(self, block_manager):
        self.block_manager = block_manager
        self.cells = []
        self.signals = []
        self.simulation_speed = 1.0
        self.total_cells = 0
        self.signal_history = []

    def update(self):
        for cell in self.cells[:]:
            if not self._valid(cell) or not hasattr(cell, "cell_data"):
                continue
            cd = cell.cell_data
            cd["age"] += 1
            cd["energy"] -= 0.1
            if cd["energy"] <= 0:
                self.remove_cell(cell)
            else:
                self._update_appearance(cell)

    def _valid(self, cell):
        try:
            _ = cell.enabled
            return cell.position is not None
        except (AttributeError, AssertionError):
            return False

    def _update_appearance(self, cell):
        cd = cell.cell_data
        base = CELL_TYPES[cd["type"]]["color"]
        ratio = cd["energy"] / cd["max_energy"]
        if ratio < 0.3:
            cell.color = base.tint(-0.3)
        elif ratio > 0.8:
            cell.color = base.tint(0.3)
        else:
            cell.color = base

    def create_cell(self, position, cell_type="stem", energy=None):
        if self.total_cells >= MAX_CELLS:
            return None
        for cell in self.cells:
            if cell.position == position:
                return cell
        block = self.block_manager.add_block(position=position)
        if not block:
            return None
        block.cell_data = {
            "type": cell_type,
            "energy": energy if energy is not None else CELL_TYPES[cell_type]["energy"],
            "max_energy": CELL_TYPES[cell_type]["energy"] * 2,
            "age": 0,
            "state": "idle",
            "connections": [],
            "memory": [],
        }
        self.cells.append(block)
        self.total_cells += 1
        self._update_appearance(block)
        return block

    def remove_cell(self, cell):
        if cell in self.cells:
            self.cells.remove(cell)
        self.block_manager.remove_block(cell)
        self.total_cells -= 1

    def create_cell_colony(self, center_pos, size=5):
        self.create_cell(center_pos, "energy")
        for x in range(-size, size + 1):
            for z in range(-size, size + 1):
                if x == 0 and z == 0:
                    continue
                if random.random() < 0.3:
                    self.create_cell((center_pos[0] + x, center_pos[1], center_pos[2] + z), "stem")

    def get_cell_stats(self):
        stats = {"total": self.total_cells, "by_type": defaultdict(int), "avg_energy": 0, "signals_active": len(self.signals)}
        total_e = 0
        n = 0
        for cell in self.cells:
            if self._valid(cell) and hasattr(cell, "cell_data"):
                cd = cell.cell_data
                stats["by_type"][cd["type"]] += 1
                total_e += cd["energy"]
                n += 1
        if n:
            stats["avg_energy"] = total_e / n
        return stats

    def create_signal(self, source, target, signal_type, strength=1.0):
        self.signals.append({
            "source": source, "target": target, "type": signal_type,
            "strength": strength, "progress": 0.0, "max_progress": 1.0,
        })
        self.signal_history.append({"type": signal_type, "time": time.time()})
