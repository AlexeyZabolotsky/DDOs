"""sonnet_3d  –  Ursina 3D world with cell/organism simulation, redstone engine,
brain network and a message-driven core world (redstone.core.World) bridged
through redstone.codex3d_bridge.Codex3DBridge.

All state mutations (generate, store, conduct, connect) are now mirrored to the
canonical World via Codex3DBridge so that redstone.core's signal propagation,
block memory, connections and the full message journal are always up-to-date.
"""

from ursina import *
from ursina.prefabs import first_person_controller as _fpc_module
from ursina.prefabs.first_person_controller import FirstPersonController

# Reset update patch after hot reload (prevents RecursionError)
FirstPersonController.update = _fpc_module.FirstPersonController.__dict__['update']

import numpy as np
from collections import defaultdict
from random import random, uniform, choice
from math import sin, cos, pi, exp
import time
import random
import re
import os

# ── Redstone core world (cursor/3d-codex-eb98) ────────────────────────────────
from redstone.core import World, СОСТОЯНИЯ, сообщение, Coord
from redstone.codex3d_bridge import Codex3DBridge
# ──────────────────────────────────────────────────────────────────────────────

app = Ursina()

_field_overlay_parent = None


def get_field_overlay_parent():
    """Container for field overlays; created lazily (needed after hot reload)."""
    global _field_overlay_parent
    if _field_overlay_parent is not None:
        try:
            _ = _field_overlay_parent.enabled
            return _field_overlay_parent
        except (AssertionError, AttributeError):
            _field_overlay_parent = None
    _field_overlay_parent = Entity(name='field_overlay_parent', eternal=True)
    return _field_overlay_parent

# By default Ursina quits on 'q'. Keep only 'escape' so Shift+R doesn't close.
application.quit_keys = ('escape',)

# Global variables
dragging = False
start_drag_pos = None
start_drag_screen_y = 0
initial_block_ys = []
connecting_blocks = []
gravity_gun_active = False

# Cell Simulation Constants
CELL_TYPES = {
    'stem': {'color': color.green, 'energy': 100, 'replication_rate': 0.1, 'signal_strength': 1.0},
    'worker': {'color': color.blue, 'energy': 50, 'replication_rate': 0.05, 'signal_strength': 0.5},
    'defender': {'color': color.red, 'energy': 150, 'replication_rate': 0.02, 'signal_strength': 0.8},
    'sensor': {'color': color.cyan, 'energy': 30, 'replication_rate': 0.03, 'signal_strength': 1.5},
    'memory': {'color': color.violet, 'energy': 80, 'replication_rate': 0.01, 'signal_strength': 0.3},
    'energy': {'color': color.yellow, 'energy': 200, 'replication_rate': 0.08, 'signal_strength': 0.2}
}

SIGNAL_TYPES = {
    'replicate': {'color': color.green.tint(0.3), 'effect': 'trigger_replication'},
    'energy_transfer': {'color': color.yellow, 'effect': 'transfer_energy'},
    'danger': {'color': color.red, 'effect': 'alert_defenders'},
    'resource_found': {'color': color.cyan, 'effect': 'attract_workers'},
    'memory_store': {'color': color.violet, 'effect': 'store_memory'},
    'differentiate': {'color': color.orange, 'effect': 'change_type'}
}

# Fixed color definitions
STATE_COLORS = {
    'stem': color.green,
    'worker': color.blue,
    'defender': color.red,
    'sensor': color.cyan,
    'memory': color.violet,
    'energy': color.yellow,
    'replicate': color.green.tint(-.2),
    'signal': color.orange,
    'differentiate': color.magenta,
    'absorb': color.pink,
    'default': color.white,
    'active': color.red,
    'inactive': color.gray,
    'selected': color.azure,
    'dying': color.black,
    'healthy': color.lime,
    'low_energy': color.orange,
    'signal_high': color.cyan,
    'signal_medium': color.orange,
    'signal_low': color.yellow,
    'generate_blocks': color.green,
    'generate_data': color.green.tint(-.2),
    'store': color.violet,
    'conduct': color.cyan,
    'connect': color.orange,
}

# Cell grid size
CELL_GRID_SIZE = 30
MAX_CELLS = 500

# Simulation control
simulation_active = True
ui_interaction_mode = False
cell_mode_active = False
current_cell_type = None
cell_data = {}
state_mode_active = False
current_state = None
state_data = {}

# Brain / Neural network control
brain_mode_active = False
current_brain = None
brain_ui_visible = False

# Organism / morphogen / organ simulation
organism = None
organ_mode_active = False
ORGAN_MIN_SIZE = 3
MORPHOGEN_DECAY = 0.15
DNA_BLUEPRINT = [
    {'cond': 'a_high', 'type': 'sensor'},
    {'cond': 'b_high', 'type': 'worker'},
    {'cond': 'ab_balance', 'type': 'memory'},
    {'cond': 'low_both', 'type': 'stem'},
    {'cond': 'default', 'type': 'defender'},
]
ORGAN_TYPE_BY_CELL = {
    'energy': 'energy_plant',
    'sensor': 'sensor_array',
    'worker': 'muscle',
    'defender': 'immune',
    'memory': 'memory_bank',
    'stem': 'growth_zone',
}

# ---------------------------------------------------------------------------
# UI Cursor
# ---------------------------------------------------------------------------
class UICursor(Entity):
    def __init__(self):
        super().__init__(
            parent=camera.ui,
            model='circle',
            scale=0.02,
            color=color.red,
            eternal=True
        )
        self.visible = False

    def update(self):
        if ui_interaction_mode:
            self.position = mouse.position
            self.visible = True
        else:
            self.visible = False

# ---------------------------------------------------------------------------
# Gravity Gun
# ---------------------------------------------------------------------------
class GravityGun:
    def __init__(self, block_manager):
        self.block_manager = block_manager
        self.held_block = None
        self.held_distance = 5
        self.min_distance = 2
        self.max_distance = 20
        self.active = False

        self.beam = Entity(
            model='cube',
            color=color.cyan.tint(0.3),
            scale=(0.1, 0.1, 1),
            visible=False
        )

        self.crosshair = Entity(
            parent=camera.ui,
            model='circle',
            color=color.cyan,
            scale=0.01,
            eternal=True
        )

    def activate(self):
        self.active = True
        self.crosshair.color = color.orange
        print("Gravity Gun activated")

    def deactivate(self):
        self.active = False
        self.release_block()
        self.beam.visible = False
        self.crosshair.color = color.cyan
        print("Gravity Gun deactivated")

    def pick_block(self, block):
        if self.held_block:
            self.release_block()
        self.held_block = block
        self.held_distance = distance(block.position, camera.position)
        self.held_distance = max(self.min_distance, min(self.held_distance, self.max_distance))
        block.color = color.orange
        self.beam.visible = True
        print(f"Picked up block at {block.position}")

    def release_block(self):
        if self.held_block:
            if hasattr(self.block_manager, 'update_block_color'):
                self.block_manager.update_block_color(self.held_block)
            self.held_block = None
            self.beam.visible = False
            print("Block released")

    def update(self):
        if not self.active:
            return
        if self.held_block:
            target_pos = camera.position + camera.forward * self.held_distance
            self.held_block.position = target_pos
            self.beam.visible = True
            beam_start_pos = player.position + Vec3(0, 1.2, 0)
            self.beam.position = beam_start_pos
            self.beam.look_at(self.held_block.position)
            dist = distance(beam_start_pos, self.held_block.position)
            self.beam.scale_z = dist
            self.beam.scale_x = 0.05
            self.beam.scale_y = 0.05
            self.beam.color = color.orange.tint(0.3)
        else:
            hit_info = raycast(camera.world_position, camera.forward, distance=self.max_distance)
            if hit_info and hit_info.hit and hit_info.entity in self.block_manager.blocks:
                self.beam.visible = True
                beam_start_pos = player.position + Vec3(0, 1.2, 0)
                self.beam.position = beam_start_pos
                self.beam.look_at(hit_info.entity.position)
                dist = distance(beam_start_pos, hit_info.entity.position)
                self.beam.scale_z = dist
                self.beam.scale_x = 0.02
                self.beam.scale_y = 0.02
                self.beam.color = color.green.tint(0.3)
            else:
                self.beam.visible = False

# ---------------------------------------------------------------------------
# Redstone Core (in-world Minecraft-style redstone)
# ---------------------------------------------------------------------------

class BlockState:
    def __init__(self, r_type='wire', power=0, facing='north'):
        self.type = r_type
        self.power = int(power)
        self.facing = facing
        self.locked = False
        self.delay = 1
        self.mode = 'compare'
        self.pulse_ticks = 0

    def is_source(self):
        return self.type in ('lever', 'button', 'pressure_plate', 'torch', 'repeater',
                             'comparator', 'and_gate', 'or_gate', 'not_gate')

    def is_wire(self):
        return self.type == 'wire'

    def is_sink(self):
        return self.type == 'lamp'


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
        return [
            (x + 1, y, z), (x - 1, y, z),
            (x, y + 1, z), (x, y - 1, z),
            (x, y, z + 1), (x, y, z - 1),
        ]

    def place_component(self, pos, r_type, facing='north'):
        initial_power = 15 if r_type == 'torch' else 0
        state = BlockState(r_type=r_type, power=initial_power, facing=facing)
        self.pos_to_state[pos] = state
        block = self.block_manager.get_block_by_coord(pos)
        if block:
            block.redstone = {'type': r_type, 'power': initial_power, 'facing': facing, 'on': initial_power > 0}
            self.block_manager.update_block_color(block)
        self.mark_for_update(pos)
        for n in self.neighbors(pos):
            self.mark_for_update(n)

    def remove_component(self, pos):
        if pos in self.pos_to_state:
            del self.pos_to_state[pos]
            block = self.block_manager.get_block_by_coord(pos)
            if block and hasattr(block, 'redstone'):
                delattr(block, 'redstone')
                self.block_manager.update_block_color(block)
            for n in self.neighbors(pos):
                self.mark_for_update(n)

    def toggle_lever(self, pos):
        st = self.pos_to_state.get(pos)
        if not st or st.type != 'lever':
            return
        st.power = 0 if st.power > 0 else 15
        block = self.block_manager.get_block_by_coord(pos)
        if block and hasattr(block, 'redstone'):
            block.redstone['on'] = st.power > 0
            block.redstone['power'] = st.power
            self.block_manager.update_block_color(block)
        self.mark_for_update(pos)
        for n in self.neighbors(pos):
            self.mark_for_update(n)

    def activate_component(self, pos):
        st = self.pos_to_state.get(pos)
        if not st:
            return
        if st.type == 'lever':
            self.toggle_lever(pos)
            return
        if st.type == 'button':
            st.power = 15
            st.pulse_ticks = 10
        elif st.type == 'pressure_plate':
            st.power = 0 if st.power > 0 else 15
        else:
            return
        block = self.block_manager.get_block_by_coord(pos)
        if block and hasattr(block, 'redstone'):
            block.redstone['on'] = st.power > 0
            block.redstone['power'] = st.power
            self.block_manager.update_block_color(block)
        self.mark_for_update(pos)
        for n in self.neighbors(pos):
            self.mark_for_update(n)

    def mark_for_update(self, pos):
        self.pending_updates.add(pos)

    def compute_input_power(self, pos):
        max_power = 0
        for n in self.neighbors(pos):
            st = self.pos_to_state.get(n)
            if not st:
                continue
            p = 0
            if st.type in ('lever', 'button', 'pressure_plate', 'torch', 'repeater',
                           'comparator', 'and_gate', 'or_gate', 'not_gate'):
                p = st.power
            elif st.type == 'wire':
                p = max(0, st.power - 1)
            max_power = max(max_power, p)
            if max_power == 15:
                break
        return max_power

    def get_neighbor_powers(self, pos):
        powers = []
        for n in self.neighbors(pos):
            st = self.pos_to_state.get(n)
            if not st:
                continue
            p = 0
            if st.type in ('lever', 'button', 'pressure_plate', 'torch', 'repeater',
                           'comparator', 'and_gate', 'or_gate', 'not_gate'):
                p = st.power
            elif st.type == 'wire':
                p = max(0, st.power - 1)
            powers.append(p)
        powers.sort(reverse=True)
        return powers

    def compute_wire_power(self, pos):
        return self.compute_input_power(pos)

    def tick(self):
        if not self.pending_updates:
            return
        to_process = list(self.pending_updates)
        self.pending_updates.clear()

        changed = []
        for pos, st in self.pos_to_state.items():
            if st.type == 'button' and st.pulse_ticks > 0:
                st.pulse_ticks -= 1
                if st.pulse_ticks == 0 and st.power != 0:
                    st.power = 0
                    changed.append(pos)

        for pos in to_process:
            st = self.pos_to_state.get(pos)
            if not st:
                continue
            if st.type == 'wire':
                new_power = self.compute_wire_power(pos)
                if new_power != st.power:
                    st.power = new_power
                    changed.append(pos)
            elif st.type == 'lamp':
                new_power = 15 if self.compute_input_power(pos) > 0 else 0
                if new_power != st.power:
                    st.power = new_power
                    changed.append(pos)
            elif st.type == 'torch':
                new_power = 0 if self.compute_input_power(pos) > 0 else 15
                if new_power != st.power:
                    st.power = new_power
                    changed.append(pos)
            elif st.type == 'repeater':
                new_power = 15 if self.compute_input_power(pos) > 0 else 0
                if new_power != st.power:
                    st.power = new_power
                    changed.append(pos)
            elif st.type == 'comparator':
                new_power = self.compute_input_power(pos)
                if new_power != st.power:
                    st.power = new_power
                    changed.append(pos)
            elif st.type == 'and_gate':
                inputs = self.get_neighbor_powers(pos)
                new_power = 15 if len([p for p in inputs if p > 0]) >= 2 else 0
                if new_power != st.power:
                    st.power = new_power
                    changed.append(pos)
            elif st.type == 'or_gate':
                new_power = 15 if self.compute_input_power(pos) > 0 else 0
                if new_power != st.power:
                    st.power = new_power
                    changed.append(pos)
            elif st.type == 'not_gate':
                new_power = 0 if self.compute_input_power(pos) > 0 else 15
                if new_power != st.power:
                    st.power = new_power
                    changed.append(pos)

        if changed:
            for pos in changed:
                block = self.block_manager.get_block_by_coord(pos)
                st = self.pos_to_state.get(pos)
                if block and hasattr(block, 'redstone') and st:
                    block.redstone['power'] = st.power
                    block.redstone['on'] = st.power > 0
                    self.block_manager.update_block_color(block)
                for n in self.neighbors(pos):
                    self.mark_for_update(n)

    def maybe_tick(self):
        now = time.time()
        dt = now - self._last_tick_time
        self._last_tick_time = now
        self._tick_accum += dt
        tick_interval = 1.0 / self.TICK_RATE
        while self._tick_accum >= tick_interval:
            self.tick()
            self._tick_accum -= tick_interval

# ---------------------------------------------------------------------------
# Field overlay shells (semi-transparent voxel hulls)
# ---------------------------------------------------------------------------
FIELD_SHELL_DEFAULT_RADIUS = 4
FIELD_SHELL_CUBE_SCALE = 0.92
FIELD_SHELL_SHAPE = 'cube'
FIELD_SHELL_COLORS = {
    'cyan': color.rgba(130, 210, 255, 75),
    'green': color.rgba(95, 220, 130, 75),
    'yellow': color.rgba(255, 235, 110, 75),
    'red': color.rgba(255, 115, 115, 75),
}


def _field_shell_positions(center, radius, shape='cube'):
    cx, cy, cz = int(round(center[0])), int(round(center[1])), int(round(center[2]))
    R = int(radius)
    out = []
    for dx in range(-R, R + 1):
        for dy in range(-R, R + 1):
            for dz in range(-R, R + 1):
                if shape == 'cube':
                    outer = max(abs(dx), abs(dy), abs(dz))
                    if R > 0 and (R - 1) < outer <= R:
                        out.append((cx + dx, cy + dy, cz + dz))
                else:
                    d2 = dx * dx + dy * dy + dz * dz
                    r_in = max(0, R - 1) ** 2
                    if r_in < d2 <= R * R:
                        out.append((cx + dx, cy + dy, cz + dz))
    return out


class FieldShell:
    def __init__(self, center, radius, channel_key, shape=None):
        self.channel_key = channel_key
        self.radius = int(radius)
        self.shape = shape if shape is not None else FIELD_SHELL_SHAPE
        cx, cy, cz = int(round(center[0])), int(round(center[1])), int(round(center[2]))
        rgba = FIELD_SHELL_COLORS[channel_key]
        self.root = Entity(
            parent=get_field_overlay_parent(),
            name=f'field_{self.shape}_{channel_key}_{id(self)}',
        )
        self._destroyed = False
        self.voxels = []
        s = FIELD_SHELL_CUBE_SCALE
        for pos in _field_shell_positions((cx, cy, cz), self.radius, self.shape):
            v = Entity(
                parent=self.root,
                model='cube',
                color=rgba,
                position=pos,
                scale=s,
                collider=None,
            )
            self.voxels.append(v)
        for v in self.voxels:
            v.render_queue = 1

    def destroy_shell(self):
        if self._destroyed:
            return
        self._destroyed = True
        for v in list(self.voxels):
            try:
                v.visible = False
                v.enabled = False
            except (AssertionError, AttributeError):
                pass
        self.voxels.clear()
        if self.root is not None:
            try:
                self.root.visible = False
                self.root.enabled = False
            except (AssertionError, AttributeError):
                pass
        self.root = None


class FieldShellManager:
    def __init__(self, block_manager):
        self.block_manager = block_manager
        self.shells = []

    def spawn(self, center, channel_key, radius=None, shape=None):
        if channel_key not in FIELD_SHELL_COLORS:
            print(f'Unknown field channel: {channel_key}')
            return None
        r = radius if radius is not None else FIELD_SHELL_DEFAULT_RADIUS
        shell_shape = shape if shape is not None else FIELD_SHELL_SHAPE
        shell = FieldShell(center, r, channel_key, shape=shell_shape)
        self.shells.append(shell)
        print(f'Field ({channel_key}, {shell_shape}) R={r} at {center}, voxels={len(shell.voxels)}')
        return shell

    def spawn_at_crosshair(self, channel_key, radius=None, shape=None):
        hit_info = raycast(camera.world_position, camera.forward, distance=80)
        if hit_info and hit_info.hit and hit_info.entity in self.block_manager.blocks:
            p = hit_info.entity.position
            center = (int(round(p.x)), int(round(p.y)), int(round(p.z)))
        else:
            t = player.position + camera.forward * 6 + Vec3(0, 0.5, 0)
            center = (int(round(t.x)), int(round(t.y)), int(round(t.z)))
        return self.spawn(center, channel_key, radius=radius, shape=shape)

    def clear_all(self):
        if not self.shells:
            print('No field overlays to clear')
            return
        for sh in self.shells:
            sh.destroy_shell()
        self.shells.clear()
        print('All field overlays cleared')

# ---------------------------------------------------------------------------
# Cell System
# ---------------------------------------------------------------------------
class CellSystem:
    def __init__(self, block_manager):
        self.block_manager = block_manager
        self.cells = []
        self.signals = []
        self.simulation_speed = 1.0
        self.energy_sources = []
        self.total_cells = 0
        self.signal_history = []
        self.max_signals = 100
        self.morphogen_field = None
        self.organ_system = None

    def update(self):
        if not simulation_active:
            return
        self.update_cells()
        self.propagate_signals()
        self.process_replication()
        self.process_energy()
        self.process_differentiation()
        self.clean_dead_cells()

    def create_cell(self, position, cell_type='stem', energy=None):
        if self.total_cells >= MAX_CELLS:
            return None
        for cell in self.cells:
            if cell.position == position:
                return cell
        block = self.block_manager.add_block(position=position)
        if not block:
            return None
        cd = {
            'type': cell_type,
            'energy': energy if energy is not None else CELL_TYPES[cell_type]['energy'],
            'max_energy': CELL_TYPES[cell_type]['energy'] * 2,
            'age': 0,
            'replication_timer': 0,
            'replication_rate': CELL_TYPES[cell_type]['replication_rate'],
            'signal_strength': CELL_TYPES[cell_type]['signal_strength'],
            'connections': [],
            'memory': [],
            'state': 'idle',
            'target': None,
            'last_signal': None,
            'is_energy_source': cell_type == 'energy',
            'is_sensor': cell_type == 'sensor',
            'is_memory': cell_type == 'memory',
            'is_defender': cell_type == 'defender',
            'is_worker': cell_type == 'worker',
            'organ_id': None,
            'organ_type': None,
        }
        block.cell_data = cd
        self.cells.append(block)
        self.total_cells += 1
        if cell_type == 'energy':
            self.energy_sources.append(block)
        self.update_cell_appearance(block)
        print(f"Created {cell_type} cell at {position} with energy {cd['energy']}")
        return block

    def update_cell_appearance(self, cell):
        if not hasattr(cell, 'cell_data'):
            return
        cd = cell.cell_data
        base_color = CELL_TYPES[cd['type']]['color']
        energy_ratio = cd['energy'] / cd['max_energy']
        if cd['energy'] <= 0:
            cell.color = STATE_COLORS['dying']
        elif energy_ratio < 0.3:
            cell.color = base_color.tint(-0.3)
        elif energy_ratio > 0.8:
            cell.color = base_color.tint(0.3)
        else:
            cell.color = base_color
        if cd['state'] == 'replicating':
            cell.color = STATE_COLORS['replicate']
        elif cd['state'] == 'signaling':
            cell.color = STATE_COLORS['signal']
        elif cd['state'] == 'differentiating':
            cell.color = STATE_COLORS['differentiate']
        elif cd['state'] == 'absorbing':
            cell.color = STATE_COLORS['absorb']

    def update_cells(self):
        for cell in self.cells[:]:
            if not self.is_cell_valid(cell) or not hasattr(cell, 'cell_data'):
                continue
            cd = cell.cell_data
            cd['age'] += 1
            energy_consumption = 0.1
            if cd['state'] != 'idle':
                energy_consumption += 0.05
            cd['energy'] -= energy_consumption
            cd['replication_timer'] += cd['replication_rate']
            if (cd['replication_timer'] >= 1.0 and
                    cd['energy'] > cd['max_energy'] * 0.7 and
                    self.total_cells < MAX_CELLS):
                self.trigger_replication(cell)
                cd['replication_timer'] = 0
            if cd['energy'] <= 0:
                cd['state'] = 'dying'
            self.update_cell_appearance(cell)

    def trigger_replication(self, parent_cell):
        if not hasattr(parent_cell, 'cell_data'):
            return
        cd = parent_cell.cell_data
        adj_positions = [
            (parent_cell.x + 1, parent_cell.y, parent_cell.z),
            (parent_cell.x - 1, parent_cell.y, parent_cell.z),
            (parent_cell.x, parent_cell.y + 1, parent_cell.z),
            (parent_cell.x, parent_cell.y - 1, parent_cell.z),
            (parent_cell.x, parent_cell.y, parent_cell.z + 1),
            (parent_cell.x, parent_cell.y, parent_cell.z - 1)
        ]
        for pos in adj_positions:
            if self.is_position_empty(pos):
                new_cell = self.create_cell(pos, cd['type'], cd['energy'] * 0.5)
                if new_cell:
                    cd['energy'] *= 0.5
                    cd['connections'].append(new_cell.position)
                    new_cell.cell_data['connections'].append(parent_cell.position)
                    self.create_signal(parent_cell, new_cell, 'replicate', 1.0)
                    print(f"Cell at {parent_cell.position} replicated to {pos}")
                    return True
        return False

    def create_signal(self, source, target, signal_type, strength=1.0):
        if not hasattr(source, 'cell_data') or not hasattr(target, 'cell_data'):
            return
        signal = {
            'source': source,
            'target': target,
            'type': signal_type,
            'strength': strength * source.cell_data['signal_strength'],
            'progress': 0.0,
            'max_progress': 1.0,
            'effect': SIGNAL_TYPES[signal_type]['effect'],
            'color': SIGNAL_TYPES[signal_type]['color']
        }
        self.signals.append(signal)
        source.cell_data['last_signal'] = signal_type
        source.cell_data['state'] = 'signaling'
        self.signal_history.append({
            'type': signal_type,
            'source': source.position,
            'target': target.position,
            'time': time.time()
        })
        if len(self.signal_history) > self.max_signals:
            self.signal_history.pop(0)

    def propagate_signals(self):
        signals_to_remove = []
        for signal in self.signals:
            signal['progress'] += 0.1 * self.simulation_speed
            if signal['progress'] >= signal['max_progress']:
                self.apply_signal_effect(signal)
                signals_to_remove.append(signal)
                if self.should_clone_signal(signal):
                    self.clone_signal(signal)
        for signal in signals_to_remove:
            if signal in self.signals:
                self.signals.remove(signal)

    def apply_signal_effect(self, signal):
        target = signal['target']
        if not hasattr(target, 'cell_data'):
            return
        cd = target.cell_data
        if signal['effect'] == 'trigger_replication':
            cd['replication_rate'] *= 1.1
            cd['state'] = 'replicating'
        elif signal['effect'] == 'transfer_energy':
            source_cd = signal['source'].cell_data
            transfer_amount = min(10, source_cd['energy'] * 0.1)
            source_cd['energy'] -= transfer_amount
            cd['energy'] += transfer_amount
            cd['state'] = 'absorbing'
        elif signal['effect'] == 'alert_defenders':
            cd['state'] = 'alerted'
        elif signal['effect'] == 'attract_workers':
            if cd['type'] == 'worker':
                cd['state'] = 'moving'
                cd['target'] = signal['source'].position
        elif signal['effect'] == 'store_memory':
            if cd['type'] == 'memory':
                cd['memory'].append(signal['type'])
                if len(cd['memory']) > 10:
                    cd['memory'].pop(0)
        elif signal['effect'] == 'change_type':
            cd['state'] = 'differentiating'
        self.update_cell_appearance(target)

    def should_clone_signal(self, signal):
        if not hasattr(signal['target'], 'cell_data'):
            return False
        cd = signal['target'].cell_data
        if signal['type'] == 'replicate' and signal['strength'] > 0.5:
            return True
        elif signal['type'] == 'danger' and cd['type'] == 'defender':
            return True
        elif signal['type'] == 'resource_found' and cd['type'] == 'sensor':
            return True
        return False

    def clone_signal(self, original_signal):
        source = original_signal['target']
        signal_type = original_signal['type']
        if not self.is_cell_valid(source):
            return
        nearby_cells = self.get_nearby_cells(source, radius=2)
        original_source = original_signal.get('source')
        for cell in nearby_cells:
            if not self.is_cell_valid(cell):
                continue
            if cell != source and (original_source is None or cell != original_source):
                try:
                    cloned_strength = original_signal['strength'] * 0.7
                    self.create_signal(source, cell, signal_type, cloned_strength)
                    pos = cell.position if hasattr(cell, 'position') else "unknown"
                    print(f"Cloned {signal_type} signal to {pos}")
                except (AssertionError, AttributeError):
                    continue

    def is_cell_valid(self, cell):
        if cell is None:
            return False
        try:
            _ = cell.enabled
            pos = cell.position
            return pos is not None
        except (AssertionError, AttributeError):
            return False

    def get_nearby_cells(self, cell, radius=1):
        if not self.is_cell_valid(cell):
            return []
        nearby = []
        for other_cell in self.cells[:]:
            if other_cell == cell:
                continue
            if not self.is_cell_valid(other_cell):
                continue
            try:
                dist = self.cell_distance(cell, other_cell)
                if dist <= radius:
                    nearby.append(other_cell)
            except (AssertionError, AttributeError):
                continue
        return nearby

    def cell_distance(self, cell1, cell2):
        try:
            if hasattr(cell1, 'position') and isinstance(cell1.position, tuple):
                pos1 = cell1.position
            else:
                pos1 = (cell1.x, cell1.y, cell1.z)
            if hasattr(cell2, 'position') and isinstance(cell2.position, tuple):
                pos2 = cell2.position
            else:
                pos2 = (cell2.x, cell2.y, cell2.z)
            return abs(pos1[0] - pos2[0]) + abs(pos1[1] - pos2[1]) + abs(pos1[2] - pos2[2])
        except (AssertionError, AttributeError):
            return float('inf')

    def process_replication(self):
        for cell in self.cells[:]:
            if not self.is_cell_valid(cell) or not hasattr(cell, 'cell_data'):
                continue
            cd = cell.cell_data
            if cd['state'] == 'replicating' and cd['energy'] > cd['max_energy'] * 0.6:
                self.trigger_replication(cell)
                cd['state'] = 'idle'

    def process_energy(self):
        for source in self.energy_sources[:]:
            if not self.is_cell_valid(source) or not hasattr(source, 'cell_data'):
                continue
            source_cd = source.cell_data
            source_cd['energy'] = min(source_cd['max_energy'], source_cd['energy'] + 1)
            nearby_cells = self.get_nearby_cells(source, radius=2)
            for cell in nearby_cells:
                if not self.is_cell_valid(cell) or not hasattr(cell, 'cell_data'):
                    continue
                cell_cd = cell.cell_data
                transfer = min(0.5, source_cd['energy'] * 0.01)
                source_cd['energy'] -= transfer
                cell_cd['energy'] += transfer
                if random.random() < 0.1:
                    self.create_signal(source, cell, 'energy_transfer', 0.5)

    def process_differentiation(self):
        mf = self.morphogen_field
        for cell in self.cells[:]:
            if not self.is_cell_valid(cell) or not hasattr(cell, 'cell_data'):
                continue
            cd = cell.cell_data
            if cd['state'] != 'differentiating':
                continue
            if mf:
                new_type = mf.decide_cell_fate(cell, cd['type'])
            else:
                nearby = self.get_nearby_cells(cell, radius=2)
                nearby_types = [o.cell_data['type'] for o in nearby
                                if self.is_cell_valid(o) and hasattr(o, 'cell_data')]
                new_type = max(set(nearby_types), key=nearby_types.count) if nearby_types else cd['type']
            if new_type != cd['type'] and new_type in CELL_TYPES:
                cd['type'] = new_type
                cd['signal_strength'] = CELL_TYPES[new_type]['signal_strength']
                cd['is_energy_source'] = new_type == 'energy'
                cd['is_sensor'] = new_type == 'sensor'
                cd['is_memory'] = new_type == 'memory'
                cd['is_defender'] = new_type == 'defender'
                cd['is_worker'] = new_type == 'worker'
                if new_type == 'energy' and cell not in self.energy_sources:
                    self.energy_sources.append(cell)
                try:
                    print(f"Cell at {_pos_tuple(cell)} -> {new_type} (morphogen/DNA)")
                except Exception:
                    print(f"Cell differentiated to {new_type}")
            self.update_cell_appearance(cell)
            cd['state'] = 'idle'

    def clean_dead_cells(self):
        dead_cells = []
        for cell in self.cells[:]:
            if not self.is_cell_valid(cell):
                dead_cells.append(cell)
                continue
            if hasattr(cell, 'cell_data') and cell.cell_data['energy'] <= 0:
                dead_cells.append(cell)
        for cell in dead_cells:
            self.remove_cell(cell)

    def remove_cell(self, cell):
        cell_position = cell.position if hasattr(cell, 'position') else None
        if cell in self.cells:
            self.cells.remove(cell)
        if hasattr(cell, 'cell_data') and cell.cell_data['is_energy_source']:
            if cell in self.energy_sources:
                self.energy_sources.remove(cell)
        self.block_manager.remove_block(cell)
        self.total_cells -= 1
        print(f"Cell at {cell_position} died")

    def is_position_empty(self, position):
        for cell in self.cells:
            if not self.is_cell_valid(cell):
                continue
            try:
                if cell.position == position:
                    return False
            except (AssertionError, AttributeError):
                continue
        for block in self.block_manager.blocks:
            if block.position == position and block.states.get('is_terrain', False):
                return False
        return True

    def create_cell_colony(self, center_pos, size=5):
        colony = []
        energy_cell = self.create_cell(center_pos, 'energy')
        if energy_cell:
            colony.append(energy_cell)
        for x in range(-size, size + 1):
            for z in range(-size, size + 1):
                if x == 0 and z == 0:
                    continue
                if random.random() < 0.3:
                    pos = (center_pos[0] + x, center_pos[1], center_pos[2] + z)
                    cell = self.create_cell(pos, 'stem')
                    if cell:
                        colony.append(cell)
        return colony

    def get_cell_stats(self):
        stats = {
            'total': self.total_cells,
            'by_type': defaultdict(int),
            'total_energy': 0,
            'avg_energy': 0,
            'signals_active': len(self.signals),
            'signals_total': len(self.signal_history)
        }
        valid_cell_count = 0
        for cell in self.cells:
            if not self.is_cell_valid(cell) or not hasattr(cell, 'cell_data'):
                continue
            cd = cell.cell_data
            stats['by_type'][cd['type']] += 1
            stats['total_energy'] += cd['energy']
            valid_cell_count += 1
        if valid_cell_count > 0:
            stats['avg_energy'] = stats['total_energy'] / valid_cell_count
        return stats

# ---------------------------------------------------------------------------
# Organism layer: morphogens, organs, resource flow, homeostasis
# ---------------------------------------------------------------------------

def _pos_tuple(block_or_pos):
    if isinstance(block_or_pos, (tuple, list)) and len(block_or_pos) >= 3:
        return (int(round(block_or_pos[0])), int(round(block_or_pos[1])), int(round(block_or_pos[2])))
    if block_or_pos is None:
        return None
    if hasattr(block_or_pos, 'position'):
        p = block_or_pos.position
        if isinstance(p, tuple):
            return (int(round(p[0])), int(round(p[1])), int(round(p[2])))
        try:
            return (int(round(block_or_pos.x)), int(round(block_or_pos.y)), int(round(block_or_pos.z)))
        except (AssertionError, AttributeError):
            return None
    return None


def _cell_neighbors_pos(pos):
    x, y, z = pos
    return [
        (x + 1, y, z), (x - 1, y, z),
        (x, y + 1, z), (x, y - 1, z),
        (x, y, z + 1), (x, y, z - 1),
    ]


class MorphogenField:
    def __init__(self, decay=MORPHOGEN_DECAY):
        self.sources = []
        self.decay = decay

    def add_source(self, position, morphogen_type='A', strength=1.0):
        pos = _pos_tuple(position)
        if pos is None:
            return
        self.sources.append({'type': morphogen_type, 'pos': pos, 'strength': float(strength)})

    def concentration_at(self, position, morphogen_type='A'):
        pos = _pos_tuple(position)
        if pos is None:
            return 0.0
        total = 0.0
        for src in self.sources:
            if src['type'] != morphogen_type:
                continue
            dx = pos[0] - src['pos'][0]
            dy = pos[1] - src['pos'][1]
            dz = pos[2] - src['pos'][2]
            dist = (dx * dx + dy * dy + dz * dz) ** 0.5
            total += src['strength'] * exp(-dist * self.decay)
        return total

    def decide_cell_fate(self, cell, current_type='stem'):
        pos = _pos_tuple(cell)
        if pos is None:
            return current_type
        ca = self.concentration_at(pos, 'A')
        cb = self.concentration_at(pos, 'B')
        for rule in DNA_BLUEPRINT:
            cond = rule['cond']
            if cond == 'a_high' and ca > cb + 0.25 and ca > 0.35:
                return rule['type']
            if cond == 'b_high' and cb > ca + 0.25 and cb > 0.35:
                return rule['type']
            if cond == 'ab_balance' and abs(ca - cb) < 0.2 and (ca + cb) > 0.4:
                return rule['type']
            if cond == 'low_both' and ca < 0.25 and cb < 0.25:
                return rule['type']
            if cond == 'default':
                return rule['type']
        return current_type


class ResourceFlowGraph:
    def __init__(self, block_manager, cell_system):
        self.block_manager = block_manager
        self.cell_system = cell_system
        self._pos_to_block = {}

    def _rebuild_index(self):
        self._pos_to_block.clear()
        for block in self.block_manager.blocks:
            pos = _pos_tuple(block)
            if pos is not None:
                self._pos_to_block[pos] = block

    def _conduct_edges(self):
        edges = []
        for block in self.block_manager.blocks:
            conduct = block.states.get('conduct', {}) if hasattr(block, 'states') else {}
            if not conduct.get('active', False):
                continue
            src = _pos_tuple(block)
            if src is None:
                continue
            for target in conduct.get('connections', []):
                tgt = _pos_tuple(target)
                if tgt is not None:
                    edges.append((src, tgt))
            connect = block.states.get('connect', {})
            if connect.get('active') and connect.get('target'):
                tgt = _pos_tuple(connect['target'])
                if tgt is not None:
                    edges.append((src, tgt))
        return edges

    def _cell_at_pos(self, pos):
        for cell in self.cell_system.cells:
            if not self.cell_system.is_cell_valid(cell):
                continue
            if _pos_tuple(cell) == pos and hasattr(cell, 'cell_data'):
                return cell
        return None

    def tick(self, flow_amount=0.4):
        self._rebuild_index()
        edges = self._conduct_edges()
        if not edges:
            return
        sources = []
        for cell in self.cell_system.cells:
            if not self.cell_system.is_cell_valid(cell) or not hasattr(cell, 'cell_data'):
                continue
            cd = cell.cell_data
            if cd['type'] == 'energy' and cd['energy'] > 5:
                sources.append(_pos_tuple(cell))
        if not sources:
            return
        adj = defaultdict(list)
        for a, b in edges:
            adj[a].append(b)
            adj[b].append(a)
        visited = set()
        for src_pos in sources:
            if src_pos is None or src_pos in visited:
                continue
            queue = [(src_pos, 0)]
            visited.add(src_pos)
            while queue:
                pos, depth = queue.pop(0)
                if depth > 12:
                    continue
                donor = self._cell_at_pos(pos)
                for npos in adj.get(pos, []):
                    if npos in visited:
                        continue
                    visited.add(npos)
                    queue.append((npos, depth + 1))
                    receiver = self._cell_at_pos(npos)
                    if donor and receiver and donor is not receiver:
                        dcd = donor.cell_data
                        rcd = receiver.cell_data
                        transfer = min(flow_amount, dcd['energy'] * 0.05)
                        if transfer > 0 and rcd['energy'] < rcd['max_energy']:
                            dcd['energy'] -= transfer
                            rcd['energy'] = min(rcd['max_energy'], rcd['energy'] + transfer)


class Organ:
    _next_id = 1

    def __init__(self, members, organ_type='growth_zone'):
        self.id = Organ._next_id
        Organ._next_id += 1
        self.members = list(members)
        self.organ_type = organ_type
        self.energy_pool = 0.0
        self.active = True

    @staticmethod
    def infer_type_from_members(members):
        if not members:
            return 'growth_zone'
        counts = defaultdict(int)
        for cell in members:
            if hasattr(cell, 'cell_data'):
                counts[cell.cell_data['type']] += 1
        if not counts:
            return 'growth_zone'
        dominant = max(counts, key=counts.get)
        return ORGAN_TYPE_BY_CELL.get(dominant, 'growth_zone')

    def centroid(self):
        pts = [_pos_tuple(c) for c in self.members if _pos_tuple(c)]
        if not pts:
            return (0, 0, 0)
        n = len(pts)
        return (sum(p[0] for p in pts) // n, sum(p[1] for p in pts) // n, sum(p[2] for p in pts) // n)

    def tick(self, cell_system, brain=None):
        if not self.active or len(self.members) < ORGAN_MIN_SIZE:
            return
        valid = [c for c in self.members if cell_system.is_cell_valid(c) and hasattr(c, 'cell_data')]
        if len(valid) < ORGAN_MIN_SIZE:
            self.active = False
            return
        self.members = valid
        if self.organ_type == 'energy_plant':
            for cell in valid:
                cd = cell.cell_data
                boost = min(2.0, self.energy_pool * 0.1 + 0.5)
                cd['energy'] = min(cd['max_energy'], cd['energy'] + boost)
            self.energy_pool = max(0, self.energy_pool - 0.3) + len(valid) * 0.05
        elif self.organ_type == 'sensor_array':
            for cell in valid[:3]:
                nearby = cell_system.get_nearby_cells(cell, radius=3)
                for other in nearby:
                    if hasattr(other, 'cell_data') and other.cell_data['type'] == 'energy':
                        cell_system.create_signal(cell, other, 'resource_found', 0.6)
        elif self.organ_type == 'muscle':
            for cell in valid:
                if cell.cell_data['energy'] > 30:
                    cell.cell_data['state'] = 'moving'
        elif self.organ_type == 'immune':
            for cell in valid:
                cell.cell_data['state'] = 'alerted'
        elif self.organ_type == 'memory_bank':
            for cell in valid:
                cd = cell.cell_data
                if cd['type'] == 'memory' and len(cd['memory']) < 12:
                    cd['memory'].append(f'organ{self.id}')
        elif self.organ_type == 'growth_zone':
            for cell in valid:
                if cell.cell_data['type'] == 'stem' and cell.cell_data['energy'] > cell.cell_data['max_energy'] * 0.65:
                    cell.cell_data['state'] = 'replicating'
        if brain and hasattr(brain, 'feed_organ_sensors'):
            brain.feed_organ_sensors(self)


class OrganSystem:
    def __init__(self, cell_system):
        self.cell_system = cell_system
        self.organs = []
        self.cell_to_organ = {}

    def _cell_adjacency_graph(self):
        pos_to_cell = {}
        for cell in self.cell_system.cells:
            if not self.cell_system.is_cell_valid(cell):
                continue
            pos = _pos_tuple(cell)
            if pos is not None:
                pos_to_cell[pos] = cell
        graph = defaultdict(list)
        for pos, cell in pos_to_cell.items():
            for npos in _cell_neighbors_pos(pos):
                if npos in pos_to_cell:
                    graph[pos].append(pos_to_cell[npos])
        return graph, pos_to_cell

    def detect_connected_components(self):
        graph, pos_to_cell = self._cell_adjacency_graph()
        seen = set()
        components = []
        for pos, start_cell in pos_to_cell.items():
            if pos in seen:
                continue
            stack = [start_cell]
            cluster = []
            while stack:
                cell = stack.pop()
                p = _pos_tuple(cell)
                if p is None or p in seen:
                    continue
                seen.add(p)
                cluster.append(cell)
                for nb in graph.get(p, []):
                    np = _pos_tuple(nb)
                    if np is not None and np not in seen:
                        stack.append(nb)
            if len(cluster) >= ORGAN_MIN_SIZE:
                components.append(cluster)
        return components

    def detect_and_update(self):
        self.organs.clear()
        self.cell_to_organ.clear()
        for cluster in self.detect_connected_components():
            organ_type = Organ.infer_type_from_members(cluster)
            organ = Organ(cluster, organ_type)
            self.organs.append(organ)
            for cell in cluster:
                self.cell_to_organ[id(cell)] = organ
                if hasattr(cell, 'cell_data'):
                    cell.cell_data['organ_id'] = organ.id
                    cell.cell_data['organ_type'] = organ_type

    def sync_brain_regions(self, brain):
        if brain is None or not self.organs:
            return
        for organ in self.organs:
            brain.connect_organ(organ)

    def get_stats(self):
        by_type = defaultdict(int)
        for o in self.organs:
            by_type[o.organ_type] += 1
        return {'count': len(self.organs), 'by_type': dict(by_type)}


class Organism:
    def __init__(self, cell_system, block_manager):
        self.cell_system = cell_system
        self.block_manager = block_manager
        self.morphogen_field = MorphogenField()
        self.organ_system = OrganSystem(cell_system)
        self.resource_flow = ResourceFlowGraph(block_manager, cell_system)
        cell_system.morphogen_field = self.morphogen_field
        cell_system.organ_system = self.organ_system
        self.stress = 0.0
        self.viability = 1.0
        self.metabolism_scale = 1.0
        self._tick = 0
        self.morphogen_field.add_source((7, 1, 7), 'A', 1.2)
        self.morphogen_field.add_source((12, 1, 3), 'B', 0.9)
        self.morphogen_field.add_source((3, 1, 12), 'B', 0.7)

    def tick(self):
        if not simulation_active:
            return
        self._tick += 1
        self.resource_flow.tick()
        if self._tick % 20 == 0:
            self.organ_system.detect_and_update()
            self.organ_system.sync_brain_regions(self.block_manager.brain)
        for organ in self.organ_system.organs:
            organ.tick(self.cell_system, self.block_manager.brain)
        self.homeostasis()
        self.run_reflexes()
        if brain_mode_active and self._tick % 5 == 0:
            self.block_manager.brain.step()
            self.block_manager.brain.hebbian_update()

    def homeostasis(self):
        stats = self.cell_system.get_cell_stats()
        total = max(1, stats['total'])
        avg_e = stats['avg_energy']
        self.stress = max(0.0, 1.0 - avg_e / 80.0)
        self.viability = min(1.0, avg_e / 50.0) if total > 0 else 0.0
        if avg_e < 25:
            self.metabolism_scale = 0.6
            self.pain_broadcast()
        else:
            self.metabolism_scale = 1.0
        for cell in self.cell_system.cells:
            if not self.cell_system.is_cell_valid(cell) or not hasattr(cell, 'cell_data'):
                continue
            cd = cell.cell_data
            drain = 0.1 * self.metabolism_scale
            if self.stress > 0.5:
                drain += 0.05
            cd['energy'] -= drain * 0.5

    def pain_broadcast(self):
        defenders = [c for c in self.cell_system.cells
                     if self.cell_system.is_cell_valid(c) and hasattr(c, 'cell_data')
                     and c.cell_data['type'] == 'defender']
        if not defenders:
            return
        source = defenders[0]
        for cell in self.cell_system.cells[:8]:
            if cell is source or not self.cell_system.is_cell_valid(cell):
                continue
            self.cell_system.create_signal(source, cell, 'danger', 0.8)

    def run_reflexes(self):
        for organ in self.organ_system.organs:
            if organ.organ_type != 'sensor_array':
                continue
            for cell in organ.members:
                if not self.cell_system.is_cell_valid(cell):
                    continue
                for other in self.cell_system.get_nearby_cells(cell, radius=2):
                    if not hasattr(other, 'cell_data'):
                        continue
                    if other.cell_data['type'] == 'defender' and other.cell_data['energy'] < 20:
                        self.cell_system.create_signal(cell, other, 'danger', 1.0)

    def place_morphogen_at_crosshair(self, morphogen_type='A'):
        hit_info = raycast(camera.world_position, camera.forward, distance=80)
        if hit_info and hit_info.hit:
            p = hit_info.entity.position
            pos = (int(round(p.x)), int(round(p.y)), int(round(p.z)))
        else:
            t = player.position + camera.forward * 6
            pos = (int(round(t.x)), int(round(t.y)), int(round(t.z)))
        self.morphogen_field.add_source(pos, morphogen_type, 1.0)
        print(f'Morphogen {morphogen_type} source at {pos}')

    def get_stats(self):
        ostats = self.organ_system.get_stats()
        return {
            'organs': ostats['count'],
            'organ_types': ostats['by_type'],
            'stress': self.stress,
            'viability': self.viability,
            'morphogen_sources': len(self.morphogen_field.sources),
        }

# ---------------------------------------------------------------------------
# Assembler System
# ---------------------------------------------------------------------------
class Assembler:
    NUMBER_OF_REGISTERS = 15
    OPCODES = {
        "ADD": 1, "SUB": 2, "NOT": 3, "AND": 4, "OR": 5,
        "LS": 6, "RS": 7,
        "LD": 8, "LDI": 9, "STR": 10,
        "BRE": 11, "BRLT": 12
    }

    def __init__(self):
        self.int_branch_labels = {}
        self.mem_cell_branch_labels = {}
        self.unused_registers = list(range(1, self.NUMBER_OF_REGISTERS))
        self.immediate_registers = {}
        self.programs_dir = "programs"
        self.machine_code_dir = "programs/machine code"
        self._ensure_directories()

    def _ensure_directories(self):
        if not os.path.exists(self.programs_dir):
            os.makedirs(self.programs_dir)
        if not os.path.exists(self.machine_code_dir):
            os.makedirs(self.machine_code_dir)

    class RegisterInfo:
        def __init__(self, value=0, cycle_last_written=0):
            self.value = value
            self.cycle_last_written = cycle_last_written

        def __str__(self):
            return f"Value: {self.value}, Cycle last written: {self.cycle_last_written}"

    def reset(self):
        self.int_branch_labels = {}
        self.mem_cell_branch_labels = {}
        self.unused_registers = list(range(1, self.NUMBER_OF_REGISTERS))
        self.immediate_registers = {}

    def read_file_into_list(self, filename):
        filepath = os.path.join(self.programs_dir, filename + ".txt")
        if not os.path.exists(filepath):
            raise FileNotFoundError(f"Program file not found: {filepath}")
        results = []
        with open(filepath, 'r') as input_file:
            for line in input_file:
                line = line[:-1] if line[-1] == '\n' else line
                if len(line) > 0:
                    parts = re.split(" |, ", line)
                    results.append(parts)
        return results

    def begins_with_label(self, instruction):
        return str(instruction[0])[-1] == ':'

    def get_opcode_str(self, instruction):
        return instruction[1] if self.begins_with_label(instruction) else instruction[0]

    def get_opcode(self, instruction):
        opcode_str = self.get_opcode_str(instruction)
        try:
            return self.OPCODES[opcode_str]
        except Exception:
            return -1

    def is_branch_instruction(self, instruction):
        return self.get_opcode_str(instruction)[:2] == "BR"

    def get_operands_start_index(self, instruction):
        return 2 if self.begins_with_label(instruction) else 1

    def get_operands(self, instruction):
        return instruction[self.get_operands_start_index(instruction):]

    def is_operand_immediate(self, operand):
        return operand[0] == '#'

    def get_operand_value(self, operand):
        value_str = operand[1:]
        try:
            return int(value_str)
        except Exception:
            raise Exception("Operand must consist of an R or #, followed only by an integer.")

    def get_cycle_of_first_branch_or_label(self, instructions):
        for i, instruction in enumerate(instructions):
            if self.begins_with_label(instruction) or self.is_branch_instruction(instruction):
                return i
        return -1

    def scan_for_immediate_registers(self, instructions):
        instruction_cycle = 0
        while instruction_cycle < len(instructions):
            instruction = instructions[instruction_cycle]
            opcode = self.get_opcode(instruction)
            if opcode >= self.OPCODES["ADD"] and opcode <= self.OPCODES["LDI"]:
                operands = self.get_operands(instruction)
                write_back_operand = operands[0]
                if self.is_operand_immediate(write_back_operand):
                    raise Exception(f"i {instruction_cycle}, operand 0: must be a register.")
                write_back_reg_number = self.get_operand_value(write_back_operand)
                if write_back_reg_number in self.unused_registers:
                    self.unused_registers.remove(write_back_reg_number)
                first_branch_cycle = self.get_cycle_of_first_branch_or_label(instructions)
                value = self.get_operand_value(operands[1])
                if write_back_reg_number in self.immediate_registers.keys():
                    if opcode == self.OPCODES["LDI"]:
                        if (first_branch_cycle > -1 and instruction_cycle >= first_branch_cycle):
                            self.immediate_registers.pop(write_back_reg_number)
                        else:
                            reg_info = self.immediate_registers[write_back_reg_number]
                            reg_info.value = value
                            reg_info.cycle_last_written = instruction_cycle
                    else:
                        self.immediate_registers.pop(write_back_reg_number)
                elif opcode == self.OPCODES["LDI"]:
                    reg_info = self.RegisterInfo(value=value, cycle_last_written=instruction_cycle)
                    self.immediate_registers[write_back_reg_number] = reg_info
            instruction_cycle += 1

    def remove_zero_ldis(self, instructions):
        instruction_cycle = 0
        while instruction_cycle < len(instructions):
            instruction = instructions[instruction_cycle]
            opcode = self.get_opcode(instruction)
            operands = self.get_operands(instruction)
            if opcode == self.OPCODES["LDI"] and not self.begins_with_label(instruction):
                value = self.get_operand_value(operands[1])
                if value == 0:
                    write_back_reg_number = self.get_operand_value(operands[0])
                    if write_back_reg_number in self.immediate_registers.keys():
                        self.immediate_registers[write_back_reg_number].cycle_last_written = 0
                        instructions.pop(instruction_cycle)
                        instruction_cycle -= 1
            instruction_cycle += 1

    def find_existing_immediate_register(self, immediate_value, instruction_cycle):
        for reg_num in self.immediate_registers.keys():
            register_info = self.immediate_registers[reg_num]
            if register_info.value == immediate_value:
                if register_info.cycle_last_written < instruction_cycle:
                    return reg_num
        return -1

    def replace_operand(self, instructions, instr_cycle, op_index, new_value):
        start_index = self.get_operands_start_index(instructions[instr_cycle])
        instructions[instr_cycle][start_index + op_index] = new_value

    def increment_last_writtens(self):
        for reg_num in self.immediate_registers.keys():
            self.immediate_registers[reg_num].cycle_last_written += 1

    def create_new_ldi(self, instructions, immediate_value):
        if len(self.unused_registers) < 1:
            raise Exception("Run out of registers to use.")
        register = self.unused_registers[-1]
        self.unused_registers.pop()
        reg_info = self.RegisterInfo(value=immediate_value, cycle_last_written=0)
        if immediate_value != 0:
            self.increment_last_writtens()
            instruction = ["LDI", f"R{register}", f"#{immediate_value}"]
            instructions.insert(0, instruction)
        self.immediate_registers[register] = reg_info
        return register

    def convert_immediate_operands(self, instructions):
        instruction_cycle = 0
        while instruction_cycle < len(instructions):
            instruction = instructions[instruction_cycle]
            opcode = self.get_opcode(instruction)
            operands = self.get_operands(instruction)
            if opcode != self.OPCODES["LDI"]:
                for operand_index in range(len(operands)):
                    operand = operands[operand_index]
                    if self.is_operand_immediate(operand):
                        operand_value = self.get_operand_value(operand)
                        register_num = self.find_existing_immediate_register(operand_value, instruction_cycle)
                        if register_num == -1:
                            register_num = self.create_new_ldi(instructions, operand_value)
                            if operand_value != 0:
                                instruction_cycle += 1
                        self.replace_operand(instructions, instruction_cycle, operand_index, f"R{register_num}")
            instruction_cycle += 1

    def replace_instruction(self, instructions, instr_cycle, new_instruction):
        instructions[instr_cycle] = new_instruction

    def convert_custom_branches(self, instructions):
        for instruction_cycle in range(len(instructions)):
            instruction = instructions[instruction_cycle]
            opcode_str = self.get_opcode_str(instruction)
            operands = self.get_operands(instruction)
            target_operand = operands[0]
            remaining_operands = operands[1:]
            replacement_instr = []
            if opcode_str == "BRZ":
                replacement_instr = ["BRE", target_operand, remaining_operands[0], "#0"]
            elif opcode_str == "BRU":
                replacement_instr = ["BRE", target_operand, "R1", "R1"]
            elif opcode_str == "BRGT":
                replacement_instr = ["BRLT", target_operand, remaining_operands[1], remaining_operands[0]]
            if len(replacement_instr) > 0:
                if self.begins_with_label(instruction):
                    replacement_instr.insert(0, instruction[0])
                self.replace_instruction(instructions, instruction_cycle, replacement_instr)

    def convert_cycle_to_custom_hex(self, instr_cycle):
        first_bit = (instr_cycle // 15) + 1
        second_bit = (instr_cycle % 15) + 1
        combined_hex = hex(first_bit) + hex(second_bit)[2:]
        return combined_hex

    def convert_cycle_to_instruction_cell_int(self, instr_cycle):
        return int(self.convert_cycle_to_custom_hex(instr_cycle), 16)

    def get_instruction_label(self, instruction):
        if self.begins_with_label(instruction):
            return instruction[0][:-1]
        raise Exception("Instruction must begin with a label to call get_instruction_label()")

    def calculate_branch_labels(self, instructions):
        for instruction_cycle, instruction in enumerate(instructions):
            if self.begins_with_label(instruction):
                label = self.get_instruction_label(instruction)
                self.int_branch_labels[label] = instruction_cycle

    def increment_branch_labels(self, amount):
        for label in self.int_branch_labels.keys():
            self.int_branch_labels[label] += amount

    def add_label_ldi_instructions(self, instructions):
        increment_amount = 0
        for label in self.int_branch_labels.keys():
            instr_cycle = self.int_branch_labels[label]
            mem_cell = self.convert_cycle_to_instruction_cell_int(instr_cycle)
            if self.find_existing_immediate_register(mem_cell, instr_cycle) == -1:
                increment_amount += 1
        self.increment_branch_labels(increment_amount)
        for label in self.int_branch_labels.keys():
            instr_cycle = self.int_branch_labels[label]
            mem_cell = self.convert_cycle_to_instruction_cell_int(instr_cycle)
            if self.find_existing_immediate_register(mem_cell, instr_cycle) == -1:
                self.create_new_ldi(instructions, mem_cell)

    def remove_label_declarations(self, instructions):
        for instruction_cycle in range(len(instructions)):
            if self.begins_with_label(instructions[instruction_cycle]):
                instructions[instruction_cycle].pop(0)

    def convert_branch_labels(self, instructions):
        for instruction_cycle in range(len(instructions)):
            instruction = instructions[instruction_cycle]
            operands = self.get_operands(instruction)
            for operand_index in range(len(operands)):
                operand = operands[operand_index]
                if operand in self.int_branch_labels.keys():
                    pointer_instr_cycle = self.int_branch_labels[operand]
                    mem_cell = self.convert_cycle_to_instruction_cell_int(pointer_instr_cycle)
                    existing_register = self.find_existing_immediate_register(mem_cell, instruction_cycle)
                    self.replace_operand(instructions, instruction_cycle, operand_index, f"R{existing_register}")

    def remove_comments(self, instructions):
        instr_index = 0
        while instr_index < len(instructions):
            if instructions[instr_index][0][0:2] == "//":
                instructions.pop(instr_index)
            else:
                instr_index += 1

    def convert_syntax(self, instructions):
        self.remove_comments(instructions)
        self.scan_for_immediate_registers(instructions)
        self.remove_zero_ldis(instructions)
        self.convert_custom_branches(instructions)
        self.convert_immediate_operands(instructions)
        self.calculate_branch_labels(instructions)
        self.add_label_ldi_instructions(instructions)
        self.remove_label_declarations(instructions)
        self.convert_branch_labels(instructions)

    def convert_opcodes(self, instructions):
        for instruction_cycle in range(len(instructions)):
            opcode = self.get_opcode(instructions[instruction_cycle])
            instructions[instruction_cycle][0] = opcode

    def convert_operands(self, instructions):
        for instruction_cycle in range(len(instructions)):
            instruction = instructions[instruction_cycle]
            start_offset = 2 if self.begins_with_label(instruction) else 1
            for operand_index in range(start_offset, len(instruction)):
                operand_value = self.get_operand_value(instruction[operand_index])
                if operand_value <= 15:
                    if instruction[0] == self.OPCODES["LDI"] and operand_index == 2:
                        instructions[instruction_cycle][operand_index] = 0
                        instructions[instruction_cycle].append(operand_value)
                    else:
                        instructions[instruction_cycle][operand_index] = operand_value
                else:
                    if instruction[0] == self.OPCODES["LDI"]:
                        hex_version = hex(operand_value)
                        digit_1 = int(hex_version[2], 16)
                        digit_2 = int(hex_version[3], 16)
                        instructions[instruction_cycle][operand_index] = digit_1
                        instructions[instruction_cycle].append(digit_2)
                    else:
                        raise Exception("Direct operands must be between 1 and 15.")

    def pad_to_equal_width(self, instructions):
        for instruction_cycle in range(len(instructions)):
            instruction = instructions[instruction_cycle]
            if len(instruction) < 4:
                for _ in range(4 - len(instruction)):
                    instructions[instruction_cycle].append(0)

    def convert_to_machine_code(self, instructions):
        self.convert_opcodes(instructions)
        self.convert_operands(instructions)
        self.pad_to_equal_width(instructions)

    def write_to_file(self, instructions, filename):
        filepath = os.path.join(self.machine_code_dir, filename + "_converted.txt")
        with open(filepath, 'w') as output_file:
            instrs_output = []
            counter = 0
            for instruction in instructions:
                instruction_str = "".join(f" {bit}" for bit in instruction)
                instr_hex = self.convert_cycle_to_custom_hex(counter)
                bit_1 = int(instr_hex[2], 16)
                bit_2 = int(instr_hex[3], 16)
                new_instr_hex = f"{bit_1} {bit_2}"
                joined = f"instr {new_instr_hex}:{instruction_str}"
                if instruction != instructions[-1]:
                    joined += "\n"
                instrs_output.append(joined)
                counter += 1
            output_file.writelines(instrs_output)

    def assemble(self, filename):
        self.reset()
        try:
            instructions = self.read_file_into_list(filename)
            self.convert_syntax(instructions)
            self.convert_to_machine_code(instructions)
            self.write_to_file(instructions, filename)
            return True, instructions, None
        except Exception as e:
            return False, None, str(e)

    def get_available_programs(self):
        if not os.path.exists(self.programs_dir):
            return []
        return [f[:-4] for f in os.listdir(self.programs_dir) if f.endswith('.txt')]

# ---------------------------------------------------------------------------
# Processor (Harvard-architecture CPU)
# ---------------------------------------------------------------------------
class Processor:
    OPCODES = {
        1: "ADD", 2: "SUB", 3: "NOT", 4: "AND", 5: "OR",
        6: "LS", 7: "RS",
        8: "LD", 9: "LDI", 10: "STR",
        11: "BRE", 12: "BRLT"
    }
    OPCODE_TO_NUM = {v: k for k, v in OPCODES.items()}

    def __init__(self):
        self.registers = [0] * 15
        self.data_memory = [0] * 60
        self.instruction_memory = [0] * 30
        self.secondary_storage = {}
        self.page_frames = [None, None]
        self.page_frame_loaded = [False, False]
        self.page_frame_pages = [None, None]
        self.program_counter = 0
        self.current_page = 0
        self.start_block = 0
        self.end_block = 0
        self.running = False
        self.paused = False
        self.cycle_count = 0
        self.current_instruction = None
        self.execution_history = []
        self.machine_code_dir = "programs/machine code"

    def reset(self):
        self.registers = [0] * 15
        self.data_memory = [0] * 60
        self.instruction_memory = [0] * 30
        self.program_counter = 0
        self.current_page = 0
        self.running = False
        self.paused = False
        self.cycle_count = 0
        self.current_instruction = None
        self.execution_history = []
        self.page_frames = [None, None]
        self.page_frame_loaded = [False, False]
        self.page_frame_pages = [None, None]

    def load_machine_code(self, filename):
        filepath = os.path.join(self.machine_code_dir, filename + "_converted.txt")
        if not os.path.exists(filepath):
            return False, f"Machine code file not found: {filepath}"
        try:
            self.secondary_storage = {}
            with open(filepath, 'r') as f:
                for line in f:
                    line = line.strip()
                    if not line.startswith("instr "):
                        continue
                    parts = line.split(":")
                    if len(parts) != 2:
                        continue
                    header = parts[0].replace("instr ", "").strip()
                    page_parts = header.split()
                    if len(page_parts) < 2:
                        continue
                    page = int(page_parts[0])
                    offset = int(page_parts[1])
                    instr_parts = parts[1].strip().split()
                    if len(instr_parts) < 4:
                        continue
                    instruction = [int(x) for x in instr_parts[:4]]
                    if page not in self.secondary_storage:
                        self.secondary_storage[page] = [None] * 15
                    if 1 <= offset <= 15:
                        self.secondary_storage[page][offset - 1] = instruction
            return True, "Machine code loaded successfully"
        except Exception as e:
            return False, f"Error loading machine code: {str(e)}"

    def load_page_to_frame(self, page_num, frame_num):
        if page_num not in self.secondary_storage:
            return False
        self.page_frames[frame_num] = self.secondary_storage[page_num].copy()
        self.page_frame_loaded[frame_num] = True
        self.page_frame_pages[frame_num] = page_num
        return True

    def get_instruction_from_memory(self):
        if self.program_counter >= 15:
            return None
        base_idx = self.program_counter * 2
        if base_idx + 1 >= len(self.instruction_memory):
            return None
        opcode = self.instruction_memory[base_idx]
        op1 = self.instruction_memory[base_idx + 1] if base_idx + 1 < len(self.instruction_memory) else 0
        if base_idx + 3 < len(self.instruction_memory):
            op2 = self.instruction_memory[base_idx + 2]
            op3 = self.instruction_memory[base_idx + 3]
        else:
            op2, op3 = 0, 0
        return [opcode, op1, op2, op3]

    def store_instruction_to_memory(self, instruction, index):
        base_idx = index * 4
        if base_idx + 3 < len(self.instruction_memory):
            self.instruction_memory[base_idx] = instruction[0]
            self.instruction_memory[base_idx + 1] = instruction[1]
            self.instruction_memory[base_idx + 2] = instruction[2]
            self.instruction_memory[base_idx + 3] = instruction[3]

    def demand_page(self, page_num):
        for i in range(2):
            if self.page_frame_loaded[i] and self.page_frame_pages[i] == page_num:
                return i
        for i in range(2):
            if not self.page_frame_loaded[i]:
                if self.load_page_to_frame(page_num, i):
                    return i
        if self.load_page_to_frame(page_num, 0):
            return 0
        return -1

    def load_program_to_instruction_memory(self, start_block, end_block):
        self.start_block = start_block
        self.end_block = end_block
        self.current_page = start_block
        frame_num = self.demand_page(start_block)
        if frame_num == -1:
            return False
        page_data = self.page_frames[frame_num]
        for i in range(min(15, len(page_data))):
            if page_data[i] is not None:
                self.store_instruction_to_memory(page_data[i], i)
        self.program_counter = 0
        return True

    def execute_instruction(self, instruction):
        if len(instruction) < 4:
            return False
        opcode, op1, op2, op3 = instruction[0], instruction[1], instruction[2], instruction[3]

        def get_reg(r):
            return self.registers[r - 1] if 1 <= r <= 15 else 0

        def set_reg(r, v):
            if 1 <= r <= 15:
                self.registers[r - 1] = v & 0xF

        def get_mem(addr):
            return self.data_memory[addr] if 0 <= addr < 60 else 0

        def set_mem(addr, v):
            if 0 <= addr < 60:
                self.data_memory[addr] = v & 0xF

        def branch_to(addr):
            target_page = ((addr >> 4) & 0xF) - 1
            target_offset = (addr & 0xF) - 1
            if target_page < 0:
                target_page = 0
            if target_offset < 0:
                target_offset = 0
            fn = self.demand_page(target_page)
            if fn != -1:
                self.current_page = target_page
                pd = self.page_frames[fn]
                for i in range(min(15, len(pd))):
                    if pd[i] is not None:
                        self.store_instruction_to_memory(pd[i], i)
                self.program_counter = target_offset
                return True
            return False

        if opcode == 1:
            set_reg(op1, get_reg(op2) + get_reg(op3))
        elif opcode == 2:
            set_reg(op1, get_reg(op2) - get_reg(op3))
        elif opcode == 3:
            set_reg(op1, (~get_reg(op2)) & 0xF)
        elif opcode == 4:
            set_reg(op1, get_reg(op2) & get_reg(op3))
        elif opcode == 5:
            set_reg(op1, get_reg(op2) | get_reg(op3))
        elif opcode == 6:
            set_reg(op1, (get_reg(op2) << 1) & 0xF)
        elif opcode == 7:
            set_reg(op1, (get_reg(op2) >> 1) & 0xF)
        elif opcode == 8:
            set_reg(op1, get_mem(get_reg(op2)))
        elif opcode == 9:
            set_reg(op1, (op2 << 4) | op3)
        elif opcode == 10:
            set_mem(get_reg(op2), get_reg(op1))
        elif opcode == 11:
            if get_reg(op2) == get_reg(op3):
                return branch_to(get_reg(op1))
        elif opcode == 12:
            if get_reg(op2) < get_reg(op3):
                return branch_to(get_reg(op1))
        return True

    def step(self):
        if not self.running or self.paused:
            return False
        instruction = self.get_instruction_from_memory()
        if instruction is None or instruction[0] == 0:
            self.running = False
            return False
        self.current_instruction = instruction.copy()
        branch_taken = self.execute_instruction(instruction)
        if not branch_taken:
            self.program_counter += 1
            if self.program_counter >= 15:
                self.current_page += 1
                if self.current_page > self.end_block:
                    self.running = False
                    return False
                frame_num = self.demand_page(self.current_page)
                if frame_num != -1:
                    page_data = self.page_frames[frame_num]
                    for i in range(min(15, len(page_data))):
                        if page_data[i] is not None:
                            self.store_instruction_to_memory(page_data[i], i)
                    self.program_counter = 0
                else:
                    self.running = False
                    return False
        self.cycle_count += 1
        self.execution_history.append({
            'cycle': self.cycle_count,
            'pc': self.program_counter,
            'page': self.current_page,
            'instruction': instruction.copy(),
            'registers': self.registers.copy()
        })
        return True

    def run(self, start_block=0, end_block=0):
        if not self.load_program_to_instruction_memory(start_block, end_block):
            return False
        self.running = True
        self.paused = False
        self.cycle_count = 0
        return True

    def stop(self):
        self.running = False
        self.paused = False

    def pause(self):
        self.paused = True

    def resume(self):
        self.paused = False

    def get_state(self):
        return {
            'registers': self.registers.copy(),
            'data_memory': self.data_memory.copy(),
            'instruction_memory': self.instruction_memory.copy(),
            'program_counter': self.program_counter,
            'current_page': self.current_page,
            'running': self.running,
            'paused': self.paused,
            'cycle_count': self.cycle_count,
            'current_instruction': self.current_instruction
        }

    def get_register(self, reg_num):
        return self.registers[reg_num - 1] if 1 <= reg_num <= 15 else 0

    def set_register(self, reg_num, value):
        if 1 <= reg_num <= 15:
            self.registers[reg_num - 1] = value & 0xF

    def get_data_memory_cell(self, addr):
        return self.data_memory[addr] if 0 <= addr < 60 else 0

    def set_data_memory_cell(self, addr, value):
        if 0 <= addr < 60:
            self.data_memory[addr] = value & 0xF

# ---------------------------------------------------------------------------
# Brain / Neural Network
# ---------------------------------------------------------------------------
class BrainNetwork:
    def __init__(self, block_manager: 'BlockManager'):
        self.block_manager = block_manager
        self.neurons = {}
        self.connections = {}
        self.activation_threshold = 0.5
        self.decay = 0.1
        self.regions = {}
        self.plasticity_rate = 0.02
        self.organ_links = {}
        self._last_activations = {}

    def add_neuron(self, block, neuron_type='hidden'):
        if not hasattr(block, 'block_id'):
            return False
        bid = block.block_id
        self.neurons[bid] = {'type': neuron_type}
        if not hasattr(block, 'block_data'):
            block.block_data = {}
        block.block_data.setdefault('activation', 0.0)
        block.block_data['neuron_type'] = neuron_type
        if neuron_type == 'input':
            block.color = color.azure
        elif neuron_type == 'output':
            block.color = color.magenta
        else:
            block.color = color.lime
        return True

    def add_connection(self, from_block, to_block, weight=1.0):
        if not hasattr(from_block, 'block_id') or not hasattr(to_block, 'block_id'):
            return False
        from_id = from_block.block_id
        to_id = to_block.block_id
        if from_id not in self.neurons or to_id not in self.neurons:
            return False
        self.connections[(from_id, to_id)] = float(weight)
        from_block.block_data.setdefault('out_connections', [])
        if to_id not in from_block.block_data['out_connections']:
            from_block.block_data['out_connections'].append(to_id)
        to_block.block_data.setdefault('in_connections', [])
        if from_id not in to_block.block_data['in_connections']:
            to_block.block_data['in_connections'].append(from_id)
        return True

    def step(self):
        if not self.neurons:
            return
        current_activations = {}
        for block in self.block_manager.blocks:
            if not hasattr(block, 'block_id'):
                continue
            bid = block.block_id
            if bid not in self.neurons:
                continue
            act = 0.0
            if hasattr(block, 'block_data') and 'activation' in block.block_data:
                act = float(block.block_data['activation'])
            if self.neurons[bid]['type'] == 'input':
                if hasattr(block, 'state') and block.state == 1:
                    act = 1.0
            current_activations[bid] = act
        new_activations = dict(current_activations)
        for (from_id, to_id), weight in self.connections.items():
            if from_id not in current_activations or to_id not in current_activations:
                continue
            new_activations[to_id] += current_activations[from_id] * weight
        for block in self.block_manager.blocks:
            if not hasattr(block, 'block_id'):
                continue
            bid = block.block_id
            if bid not in self.neurons:
                continue
            raw_act = new_activations.get(bid, 0.0)
            act = 1.0 if raw_act >= self.activation_threshold else max(0.0, raw_act - self.decay)
            block.block_data['activation'] = act
            n_type = self.neurons[bid]['type']
            if n_type == 'input':
                base_color = color.azure
            elif n_type == 'output':
                base_color = color.magenta
            else:
                base_color = color.lime
            block.color = base_color.tint(-0.5 + act * 0.5)
        self._last_activations = dict(current_activations)

    def add_region(self, name, blocks=None):
        if blocks is None:
            blocks = []
        self.regions[name] = [b.block_id for b in blocks if hasattr(b, 'block_id')]
        return True

    def connect_organ(self, organ):
        if organ is None or not organ.members:
            return
        role_map = {
            'sensor_array': 'input',
            'muscle': 'output',
            'immune': 'output',
            'memory_bank': 'hidden',
            'energy_plant': 'hidden',
            'growth_zone': 'hidden',
        }
        ntype = role_map.get(organ.organ_type, 'hidden')
        region_name = f"organ_{organ.id}_{organ.organ_type}"
        linked_blocks = []
        for cell in organ.members:
            if not hasattr(cell, 'block_id'):
                continue
            self.add_neuron(cell, ntype)
            linked_blocks.append(cell)
        self.add_region(region_name, linked_blocks)
        self.organ_links[organ.id] = {'region': region_name, 'type': ntype}

    def feed_organ_sensors(self, organ):
        if organ.organ_type != 'sensor_array':
            return
        for cell in organ.members:
            if hasattr(cell, 'block_id') and cell.block_id in self.neurons:
                if hasattr(cell, 'cell_data') and cell.cell_data.get('state') == 'signaling':
                    if not hasattr(cell, 'block_data'):
                        cell.block_data = {}
                    cell.block_data['activation'] = 1.0

    def hebbian_update(self):
        if not self._last_activations:
            return
        for (from_id, to_id), weight in list(self.connections.items()):
            pre = self._last_activations.get(from_id, 0.0)
            post = self._last_activations.get(to_id, 0.0)
            if pre > 0.4 and post > 0.4:
                self.connections[(from_id, to_id)] = min(3.0, weight + self.plasticity_rate)
            elif pre < 0.1 and post < 0.1:
                self.connections[(from_id, to_id)] = max(0.1, weight - self.plasticity_rate * 0.5)

    def attention_gate(self, region_name, strength=1.5):
        ids = self.regions.get(region_name, [])
        for bid in ids:
            if bid in self.neurons:
                self.neurons[bid]['attention'] = strength

    def reset(self):
        self._last_activations = {}
        for block in self.block_manager.blocks:
            if hasattr(block, 'block_id') and block.block_id in self.neurons:
                block.block_data['activation'] = 0.0
                n_type = self.neurons[block.block_id]['type']
                if n_type == 'input':
                    block.color = color.azure
                elif n_type == 'output':
                    block.color = color.magenta
                else:
                    block.color = color.lime

# ---------------------------------------------------------------------------
# Block Manager  (with Codex3DBridge / World integration)
# ---------------------------------------------------------------------------
class BlockManager:
    def __init__(self):
        self.blocks = []
        self.selected_blocks = []
        self.hovered_block = None
        self.brain = BrainNetwork(self)
        # ── core World bridge (cursor/3d-codex-eb98) ──────────────────────────
        self.bridge = Codex3DBridge()

    # ── helpers ───────────────────────────────────────────────────────────────
    def _coord(self, block_or_pos) -> Coord:
        """Normalize any position-like value to integer (x, y, z)."""
        if isinstance(block_or_pos, tuple):
            return (int(round(block_or_pos[0])), int(round(block_or_pos[1])), int(round(block_or_pos[2])))
        p = getattr(block_or_pos, 'position', block_or_pos)
        if hasattr(p, 'x'):
            return (int(round(p.x)), int(round(p.y)), int(round(p.z)))
        return (int(round(p[0])), int(round(p[1])), int(round(p[2])))

    def world_dispatch(self, state_key: str, coord, data: dict = None):
        """Fire a redstone.core message for the given СОСТОЯНИЯ key."""
        try:
            self.bridge.world.dispatch(
                сообщение(СОСТОЯНИЯ[state_key], self._coord(coord), data or {})
            )
        except (KeyError, ValueError) as exc:
            print(f"world_dispatch error: {exc}")

    # ── visual ────────────────────────────────────────────────────────────────
    def update_block_color(self, block):
        if gravity_gun.held_block == block:
            block.color = color.orange
            return
        if hasattr(block, 'cell_data'):
            return
        if hasattr(block, 'redstone'):
            r = block.redstone
            r_type = r.get('type')
            p = int(r.get('power', 0))
            if r_type == 'lever':
                block.color = color.orange if r.get('on', False) else color.gray
            elif r_type == 'button':
                block.color = color.rgb(180, 120, 70) if p > 0 else color.rgb(110, 75, 45)
            elif r_type == 'pressure_plate':
                block.color = color.lime if p > 0 else color.rgb(90, 130, 90)
            elif r_type == 'wire':
                t = max(0.0, min(1.0, p / 15.0))
                block.color = color.rgba(int(255 * (0.6 + 0.4 * t)), int(40 + 120 * t), int(40 * (1.0 - 0.5 * t)), 255)
            elif r_type == 'lamp':
                block.color = color.yellow if p > 0 else color.gray
            elif r_type == 'torch':
                block.color = color.rgb(255, 160, 60) if p > 0 else color.rgb(90, 50, 35)
            elif r_type == 'repeater':
                block.color = color.red if p > 0 else color.rgb(120, 45, 45)
            elif r_type == 'comparator':
                t = max(0.0, min(1.0, p / 15.0))
                block.color = color.rgba(int(90 + 120 * t), int(90 + 120 * t), int(180 + 60 * t), 255)
            elif r_type == 'and_gate':
                block.color = color.rgb(40, 180, 220) if p > 0 else color.rgb(35, 80, 95)
            elif r_type == 'or_gate':
                block.color = color.rgb(200, 120, 255) if p > 0 else color.rgb(95, 60, 120)
            elif r_type == 'not_gate':
                block.color = color.rgb(255, 90, 90) if p > 0 else color.rgb(120, 55, 55)
            return
        if block.states.get('is_terrain', False):
            block.color = color.gray
        elif block in self.selected_blocks:
            block.color = STATE_COLORS['selected']
        elif block.states.get('generate', {}).get('active', False):
            block.color = STATE_COLORS['generate_blocks']
        elif block.states.get('store', {}).get('active', False):
            block.color = STATE_COLORS['store']
        elif block.states.get('conduct', {}).get('active', False):
            block.color = STATE_COLORS['conduct']
        elif block.states.get('connect', {}).get('active', False):
            block.color = STATE_COLORS['connect']
        else:
            block.color = STATE_COLORS['default']

    # ── block lifecycle ───────────────────────────────────────────────────────
    def add_block(self, position=None, color=color.white, is_terrain=False):
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
            color=color,
            model='cube',
            position=position,
            texture='white_cube',
            parent=scene,
            origin_y=0.5,
            collider='box'
        )
        box.states = {'is_terrain': is_terrain}
        box.block_data = {}
        box.state = 0
        box.block_id = len(self.blocks)
        self.blocks.append(box)
        # Mirror to core World
        coord = self._coord(position)
        self.bridge.world.dispatch(
            сообщение(СОСТОЯНИЯ["ГЕНЕРАЦИЯ"], coord, {"цвет": "#9e9e9e"})
        )
        return box

    def get_air_position_at_crosshair(self):
        start_pos = player.position
        direction = camera.forward
        target_pos = start_pos + direction * 10
        target_pos = (round(target_pos.x), round(target_pos.y), round(target_pos.z))
        if target_pos[1] < 2:
            target_pos = (target_pos[0], 2, target_pos[2])
        return target_pos

    def remove_block(self, block):
        coord = self._coord(block.position) if hasattr(block, 'position') else None
        if block in self.blocks:
            self.blocks.remove(block)
        if block in self.selected_blocks:
            self.selected_blocks.remove(block)
        if coord and coord in self.bridge.world.блоки:
            try:
                self.bridge.world.dispatch(сообщение(СОСТОЯНИЯ["УНИЧТОЖЕНИЕ"], coord))
            except Exception:
                pass
        destroy(block)

    def update_selection_visual(self):
        for box in self.blocks:
            if not hasattr(box, 'states'):
                continue
            if box in self.selected_blocks:
                box.color = STATE_COLORS['selected']
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

    # ── signal / generate (also dispatch through core World) ─────────────────
    def send_signal(self, source_coord, target_coord, signal_data):
        source_block = self.get_block_by_coord(source_coord)
        target_block = self.get_block_by_coord(target_coord)
        if not source_block or not target_block:
            return False
        if hasattr(source_block, 'state') and source_block.state == 1:
            if 'conduct' in source_block.states and source_block.states['conduct'].get('active', False):
                if not hasattr(target_block, 'received_signals'):
                    target_block.received_signals = []
                sig = {'from': source_coord, 'to': target_coord, 'data': signal_data, 'time': time.time()}
                target_block.received_signals.append(sig)
                original_color = target_block.color
                target_block.color = STATE_COLORS['signal']
                invoke(lambda b=target_block, c=original_color: setattr(b, 'color', c), delay=0.5)
                # Mirror through core World
                src_c = self._coord(source_coord)
                tgt_c = self._coord(target_coord)
                self.bridge.ensure_block(src_c)
                self.bridge.ensure_block(tgt_c)
                if tgt_c not in self.bridge.world.блоки[src_c].соединения:
                    self.bridge.world.dispatch(
                        сообщение(СОСТОЯНИЯ["СОЕДИНЕНИЕ"], src_c, {"с": list(tgt_c)})
                    )
                data_payload = signal_data if isinstance(signal_data, dict) else {"value": signal_data}
                self.bridge.world.dispatch(сообщение(СОСТОЯНИЯ["ПЕРЕДАЧА"], src_c, data_payload))
                print(f"Signal sent from {source_coord} to {target_coord} with data: {signal_data}")
                return True
        return False

    def generate_at_position(self, source_coord, target_coord, generate_data=None):
        source_block = self.get_block_by_coord(source_coord)
        if not source_block:
            return False
        if hasattr(source_block, 'state') and source_block.state == 1:
            if 'generate' in source_block.states and source_block.states['generate'].get('active', False):
                if self.get_block_by_coord(target_coord) is None:
                    new_block = self.add_block(position=target_coord)
                    if new_block:
                        if generate_data:
                            if isinstance(generate_data, dict):
                                new_block.block_data = generate_data.copy()
                            else:
                                new_block.block_data = {'value': generate_data}
                        # Mirror: ГЕНЕРАЦИЯ already fired in add_block; store data in core World
                        tgt_c = self._coord(target_coord)
                        if generate_data:
                            mem = generate_data.copy() if isinstance(generate_data, dict) else {"value": generate_data}
                            self.bridge.world.dispatch(сообщение(СОСТОЯНИЯ["СОХРАНЕНИЕ"], tgt_c, mem))
                        print(f"Generated block at {target_coord} from {source_coord}")
                        return True
                else:
                    target_block = self.get_block_by_coord(target_coord)
                    if generate_data:
                        if isinstance(generate_data, dict):
                            target_block.block_data.update(generate_data)
                        else:
                            target_block.block_data['value'] = generate_data
                        tgt_c = self._coord(target_coord)
                        mem = generate_data.copy() if isinstance(generate_data, dict) else {"value": generate_data}
                        self.bridge.ensure_block(tgt_c)
                        self.bridge.world.dispatch(сообщение(СОСТОЯНИЯ["СОХРАНЕНИЕ"], tgt_c, mem))
                        print(f"Generated data at {target_coord} from {source_coord}: {generate_data}")
                        return True
        return False

# ---------------------------------------------------------------------------
# Advanced UI
# ---------------------------------------------------------------------------
class AdvancedUI(Entity):
    def __init__(self, cell_system, **kwargs):
        super().__init__(parent=camera.ui)
        self.cell_system = cell_system

        self.ui_panel = Entity(
            parent=self,
            model='quad',
            scale=(0.8, 0.8),
            position=(-0.6, -0.3, -1),
            color=color.dark_gray.tint(0.1),
            visible=False
        )

        self.mini_info_panel = Entity(
            parent=self,
            model='quad',
            scale=(0.25, 0.35),
            position=(0.8, 0.4, -1),
            color=color.dark_gray.tint(0.2),
            visible=False
        )

        self.mini_info_text = Text(
            parent=self.mini_info_panel,
            text='',
            position=(-0.4, 0.1),
            scale=1.5,
            color=color.white
        )

        self.tabs = {}
        self.active_tab = None
        self.content_panels = {
            'Cells': Entity(parent=self.ui_panel),
            'Signals': Entity(parent=self.ui_panel),
            'Simulation': Entity(parent=self.ui_panel),
            'State Input': Entity(parent=self.ui_panel),
            'Assembler': Entity(parent=self.ui_panel),
            'Brain': Entity(parent=self.ui_panel),
        }

        self.stats_panel = Entity(parent=self.ui_panel)
        self.cell_stats_text = Text(
            parent=self.stats_panel,
            text='',
            position=(0.5, 0.7),
            scale=1.2,
            color=color.cyan
        )

        self.gravity_gun_display = Text(
            parent=self.mini_info_panel,
            text='Gravity Gun: OFF',
            position=(-0.4, -0.2),
            scale=1.2,
            color=color.gray
        )

        self.state_mode_display = Text(
            parent=self.mini_info_panel,
            text='State Mode: OFF',
            position=(-0.4, -0.35),
            scale=1.2,
            color=color.gray
        )

        self.state_display = Text(
            parent=self.mini_info_panel,
            text='Current Mode: None',
            position=(-0.4, -0.5),
            scale=1.2,
            color=color.yellow
        )

        self.data_input = InputField(
            parent=self.ui_panel,
            scale=(0.8, 0.08),
            position=(0.04, 0.3),
            visible=False
        )
        self.data_input.submit_on = ['enter', 'tab']
        self.data_input.on_submit = self.submit_data

        self.data_input_label = Text(
            parent=self.ui_panel,
            text='Enter Data:',
            position=(-0.4, -0.2),
            scale=1.0,
            color=color.white,
            visible=False
        )

        self.direction_buttons = {}

        self.console_panel = Entity(
            parent=self.ui_panel,
            model='quad',
            scale=(0.9, 0.3),
            position=(0.0, -0.6, -1),
            color=color.dark_gray.tint(0.2),
            visible=False
        )

        self.console_label = Text(
            parent=self.console_panel,
            text='Console Commands (Format: coord/id, data_dict, state):',
            position=(-0.45, 0.1),
            scale=1.2,
            color=color.white,
            visible=False
        )

        self.console_input = InputField(
            parent=self.console_panel,
            scale=(0.85, 0.08),
            position=(0.0, -0.05, -1),
            visible=False
        )
        self.console_input.submit_on = ['enter']
        self.console_input.on_submit = self.process_console_command

        self.console_output = Text(
            parent=self.console_panel,
            text='',
            position=(-0.45, -0.15),
            scale=1.0,
            color=color.cyan,
            visible=False
        )

        self.create_state_input_panel()
        self.set_ui_visible(False)
        self.mouse_hovered_button = None
        self.cell_mode_active = False

        self.brain_info_text = Text(
            parent=self.mini_info_panel,
            text='Brain: OFF',
            position=(-0.4, -0.05),
            scale=1.0,
            color=color.gray
        )

        brain_panel = self.content_panels['Brain']
        Text(parent=brain_panel, text='Brain Neural Bloks', position=(0.0, 0.33), scale=2.0, color=color.white)
        Button(parent=brain_panel, text='MARK SELECTED AS INPUT NEURONS', scale=(0.7, 0.06), position=(0.0, 0.18), color=color.azure, on_click=self.mark_selected_as_input_neurons)
        Button(parent=brain_panel, text='MARK SELECTED AS HIDDEN NEURONS', scale=(0.7, 0.06), position=(0.0, 0.08), color=color.lime, on_click=self.mark_selected_as_hidden_neurons)
        Button(parent=brain_panel, text='MARK SELECTED AS OUTPUT NEURONS', scale=(0.7, 0.06), position=(0.0, -0.02), color=color.magenta, on_click=self.mark_selected_as_output_neurons)
        Button(parent=brain_panel, text='CONNECT SELECTED IN CHAIN', scale=(0.7, 0.06), position=(0.0, -0.12), color=color.orange, on_click=self.connect_selected_chain)
        Button(parent=brain_panel, text='BRAIN STEP', scale=(0.7, 0.06), position=(0.0, -0.22), color=color.yellow, on_click=self.brain_step)
        brain_panel.visible = False

    def create_state_input_panel(self):
        state_input_panel = self.content_panels['State Input']
        state_input_panel.enabled = True
        Text(parent=state_input_panel, text='State Input Controls:', position=(0.0, 0.25), scale=2.0, color=color.white)
        states = [
            ('CONNECT BLOCKS', self.set_connect_state),
            ('CONDUCT SIGNALS', self.set_conduct_state),
            ('GENERATE BLOCKS', self.set_generate_state),
            ('STORE DATA', self.set_store_state),
        ]
        for i, (name, func) in enumerate(states):
            Button(
                parent=state_input_panel,
                text=name,
                scale=(0.6, 0.06),
                position=(0.0, 0.15 - i * 0.08),
                color=STATE_COLORS.get(name.split()[0].lower(), color.gray),
                on_click=func
            )

    # ── Brain helpers ─────────────────────────────────────────────────────────
    def _ensure_brain(self):
        global brain_mode_active, current_brain, block_manager
        if not hasattr(block_manager, 'brain') or block_manager.brain is None:
            block_manager.brain = BrainNetwork(block_manager)
        current_brain = block_manager.brain
        brain_mode_active = True
        self.brain_info_text.text = 'Brain: ON'
        self.brain_info_text.color = color.green

    def toggle_brain_ui_overlay(self):
        global brain_ui_visible, state_mode_active, current_state
        self._ensure_brain()
        brain_ui_visible = not brain_ui_visible
        main_visible = self.ui_panel.visible
        if 'Brain' in self.content_panels:
            self.content_panels['Brain'].visible = main_visible and brain_ui_visible
        if 'State Input' in self.content_panels:
            self.content_panels['State Input'].visible = main_visible and not brain_ui_visible
        if brain_ui_visible:
            self.data_input.visible = False
            self.data_input_label.visible = False
        else:
            needs_input = state_mode_active and current_state in ("generate", "store", "conduct")
            self.data_input.visible = main_visible and needs_input
            self.data_input_label.visible = main_visible and needs_input
        if brain_ui_visible:
            self.brain_info_text.text = 'Brain UI: ON'
            self.brain_info_text.color = color.orange
        else:
            self.brain_info_text.text = 'Brain: ON'
            self.brain_info_text.color = color.green

    def mark_selected_as_input_neurons(self):
        self._ensure_brain()
        for b in block_manager.selected_blocks:
            block_manager.brain.add_neuron(b, 'input')

    def mark_selected_as_hidden_neurons(self):
        self._ensure_brain()
        for b in block_manager.selected_blocks:
            block_manager.brain.add_neuron(b, 'hidden')

    def mark_selected_as_output_neurons(self):
        self._ensure_brain()
        for b in block_manager.selected_blocks:
            block_manager.brain.add_neuron(b, 'output')

    def connect_selected_chain(self):
        self._ensure_brain()
        blocks = list(block_manager.selected_blocks)
        if len(blocks) < 2:
            return
        for i in range(len(blocks) - 1):
            block_manager.brain.add_connection(blocks[i], blocks[i + 1], weight=1.0)

    def brain_step(self):
        self._ensure_brain()
        block_manager.brain.step()

    # ── state setters ─────────────────────────────────────────────────────────
    def set_direction(self, direction):
        global state_data
        if isinstance(state_data, dict):
            state_data['direction'] = direction
        else:
            state_data = {'direction': direction}
        print(f"Direction set to: {direction}")

    def submit_data(self):
        global state_data
        if isinstance(state_data, dict):
            state_data['value'] = self.data_input.text
        else:
            state_data = {'value': self.data_input.text}
        self.update_state_display()
        print(f"Data submitted: {state_data}")
        self.data_input.visible = False
        self.data_input_label.visible = False

    def update_state_display(self):
        global current_state, state_data
        display_text = f"Current Mode: {current_state if current_state else 'None'}"
        if state_data:
            if 'value' in state_data:
                display_text += f"\nData: {state_data['value']}"
            if 'direction' in state_data:
                display_text += f"\nDirection: {state_data['direction']}"
        self.state_display.text = display_text

    def set_generate_state(self):
        global current_state, state_data, state_mode_active
        current_state = "generate"
        state_data = {}
        state_mode_active = True
        self.state_mode_display.text = 'State Mode: ON'
        self.state_mode_display.color = color.blue
        self.data_input.visible = True
        self.data_input_label.visible = True
        self.data_input.active = True
        self.data_input.text = ''
        self.data_input_label.text = 'Enter generation data:'
        self.update_state_display()

    def set_store_state(self):
        global current_state, state_data, state_mode_active
        current_state = "store"
        state_data = {}
        state_mode_active = True
        self.state_mode_display.text = 'State Mode: ON'
        self.state_mode_display.color = color.blue
        self.data_input.visible = True
        self.data_input_label.visible = True
        self.data_input.active = True
        self.data_input.text = ''
        self.data_input_label.text = 'Enter data to store:'
        self.update_state_display()

    def set_conduct_state(self):
        global current_state, state_data, state_mode_active
        current_state = "conduct"
        state_data = {}
        state_mode_active = True
        self.state_mode_display.text = 'State Mode: ON'
        self.state_mode_display.color = color.blue
        self.data_input.visible = True
        self.data_input_label.visible = True
        self.data_input.active = True
        self.data_input.text = ''
        self.data_input_label.text = 'Enter signal data:'
        self.update_state_display()

    def set_connect_state(self):
        global current_state, state_data, state_mode_active
        current_state = "connect"
        state_data = {}
        state_mode_active = True
        self.state_mode_display.text = 'State Mode: ON'
        self.state_mode_display.color = color.blue
        self.data_input.visible = False
        self.data_input_label.visible = False
        self.update_state_display()

    def toggle_state_mode(self):
        global state_mode_active
        state_mode_active = not state_mode_active
        self.state_mode_display.text = f'State Mode: {"ON" if state_mode_active else "OFF"}'
        self.state_mode_display.color = color.blue if state_mode_active else color.gray

    def switch_tab(self, tab_name):
        for panel in self.content_panels.values():
            panel.enabled = False
        if tab_name in self.content_panels:
            self.content_panels[tab_name].enabled = True
        for name, tab in self.tabs.items():
            tab.color = color.blue if name == tab_name else color.gray
        self.active_tab = tab_name

    def process_console_command(self):
        command = self.console_input.text.strip()
        if not command:
            return
        try:
            parts = command.split(',', 2)
            if len(parts) != 3:
                self.console_output.text = "Error: Format must be 'coord/id, data_dict, state'"
                self.console_output.color = color.red
                return
            block_identifier = parts[0].strip()
            block = None
            if block_identifier.startswith('(') and block_identifier.endswith(')'):
                coord_str = block_identifier[1:-1]
                coord_parts = [int(x.strip()) for x in coord_str.split(',')]
                if len(coord_parts) == 3:
                    block = block_manager.get_block_by_coord(tuple(coord_parts))
            else:
                try:
                    block = block_manager.get_block_by_id(int(block_identifier))
                except ValueError:
                    pass
            if not block:
                self.console_output.text = f"Error: Block not found at {block_identifier}"
                self.console_output.color = color.red
                return
            import json as _json
            data_str = parts[1].strip()
            try:
                block_data = _json.loads(data_str)
                if isinstance(block_data, dict):
                    block.block_data.update(block_data)
                else:
                    block.block_data['value'] = block_data
            except Exception:
                block.block_data['value'] = data_str
            state_str = parts[2].strip()
            try:
                block.state = int(state_str)
                if block.state not in [0, 1]:
                    block.state = 0
            except ValueError:
                block.state = 0
            if block.state == 1:
                if 'conduct' in block.states and block.states['conduct'].get('active', False):
                    block.color = STATE_COLORS['conduct']
                elif 'generate' in block.states and block.states['generate'].get('active', False):
                    block.color = STATE_COLORS['generate_blocks']
                else:
                    block.color = STATE_COLORS['active']
            else:
                block.color = STATE_COLORS['inactive']
            # Mirror block_data into core World memory
            coord = block_manager._coord(block.position)
            block_manager.bridge.ensure_block(coord)
            if block.block_data:
                block_manager.bridge.world.dispatch(
                    сообщение(СОСТОЯНИЯ["СОХРАНЕНИЕ"], coord, block.block_data)
                )
            self.console_output.text = f"Success: Block {block_identifier}\nData: {block.block_data}\nState: {block.state}"
            self.console_output.color = color.green
        except Exception as e:
            self.console_output.text = f"Error: {str(e)}"
            self.console_output.color = color.red
            print(f"Console command error: {e}")

    def toggle_ui_mode(self):
        global ui_interaction_mode, dragging
        ui_interaction_mode = not ui_interaction_mode
        if dragging:
            dragging = False
        self.set_ui_visible(ui_interaction_mode)
        self.mini_info_panel.visible = not ui_interaction_mode
        ui_cursor.visible = ui_interaction_mode
        mouse.locked = not ui_interaction_mode
        if hasattr(self, 'console_panel'):
            self.console_panel.visible = ui_interaction_mode
            self.console_label.visible = ui_interaction_mode
            self.console_input.visible = ui_interaction_mode
            self.console_output.visible = ui_interaction_mode
        for block in block_manager.blocks:
            if hasattr(block, 'visible'):
                block.visible = True
            if hasattr(block, 'enabled'):
                block.enabled = True

    def toggle_gravity_gun(self):
        global gravity_gun_active
        gravity_gun_active = not gravity_gun_active
        if gravity_gun_active:
            gravity_gun.activate()
            self.gravity_gun_display.text = 'Gravity Gun: ON'
            self.gravity_gun_display.color = color.orange
        else:
            gravity_gun.deactivate()
            self.gravity_gun_display.text = 'Gravity Gun: OFF'
            self.gravity_gun_display.color = color.gray

    def toggle_cell_mode(self):
        self.cell_mode_active = not self.cell_mode_active

    def set_ui_visible(self, visible):
        self.ui_panel.visible = visible
        if hasattr(self, 'console_panel'):
            self.console_panel.visible = visible
            self.console_label.visible = visible
            self.console_input.visible = visible
            self.console_output.visible = visible
        for child in self.ui_panel.children:
            if hasattr(child, 'enabled') and child.parent == self.ui_panel:
                child.enabled = visible
        if visible:
            if 'Brain' in self.content_panels:
                self.content_panels['Brain'].visible = brain_ui_visible
            if 'State Input' in self.content_panels:
                self.content_panels['State Input'].visible = not brain_ui_visible
        else:
            if 'Brain' in self.content_panels:
                self.content_panels['Brain'].visible = False
            if 'State Input' in self.content_panels:
                self.content_panels['State Input'].visible = False

    # ── mini-panel updates ────────────────────────────────────────────────────
    def update_mini_info_panel(self):
        if ui_interaction_mode or not self.mini_info_panel.visible:
            return
        hit_info = raycast(camera.world_position, camera.forward, distance=50)
        if hit_info and hit_info.hit and hit_info.entity in block_manager.blocks:
            block = hit_info.entity
            if hasattr(block, 'cell_data'):
                cd = block.cell_data
                self.mini_info_text.text = (
                    f'Cell Type: {cd["type"]}\n'
                    f'Energy: {cd["energy"]:.1f}/{cd["max_energy"]}\n'
                    f'Age: {cd["age"]}\n'
                    f'State: {cd["state"]}\n'
                    f'Connections: {len(cd["connections"])}'
                )
            else:
                coord = block_manager._coord(block.position)
                world_block = block_manager.bridge.world.блоки.get(coord)
                mem_str = str(world_block.память) if world_block else '—'
                self.mini_info_text.text = f'Block\nCoord: {coord}\nWorld mem:\n{mem_str[:60]}'
        else:
            stats = self.cell_system.get_cell_stats()
            info_text = (
                f'Total Cells: {stats["total"]}\n'
                f'Active Signals: {stats["signals_active"]}\n'
                f'Avg Energy: {stats["avg_energy"]:.1f}\n'
                f'Max Cells: {MAX_CELLS}'
            )
            if organism is not None:
                ost = organism.get_stats()
                info_text += f'\nOrgans: {ost["organs"]}\nStress: {ost["stress"]:.2f}\nViability: {ost["viability"]:.2f}'
            self.mini_info_text.text = info_text

    def update_stats_display(self):
        stats = self.cell_system.get_cell_stats()
        stats_text = f'CELL STATISTICS\nTotal: {stats["total"]}/{MAX_CELLS}\nActive Signals: {stats["signals_active"]}\n'
        for cell_type, count in stats['by_type'].items():
            stats_text += f'{cell_type}: {count}\n'
        if organism is not None:
            ost = organism.get_stats()
            stats_text += f'\nORGANISM\nOrgans: {ost["organs"]}\nMorphogens: {ost["morphogen_sources"]}\n'
            for ot, n in ost.get('organ_types', {}).items():
                stats_text += f'  {ot}: {n}\n'
            stats_text += f'Stress: {ost["stress"]:.2f}\nViability: {ost["viability"]:.2f}\n'
        # Core World stats
        world_size = len(block_manager.bridge.world.блоки)
        journal_size = len(block_manager.bridge.world.журнал)
        stats_text += f'\nWorld blocks: {world_size}\nMsg journal: {journal_size}'
        self.cell_stats_text.text = stats_text

    def update(self):
        self.update_mini_info_panel()
        self.update_stats_display()

    # ── misc cell helpers kept for compatibility ───────────────────────────────
    def stimulate_cell(self):
        hit_info = raycast(camera.world_position, camera.forward, distance=50)
        if hit_info and hit_info.hit and hasattr(hit_info.entity, 'cell_data'):
            cell = hit_info.entity
            cell.cell_data['energy'] = min(cell.cell_data['max_energy'], cell.cell_data['energy'] + 20)

    def transfer_energy(self):
        hit_info = raycast(camera.world_position, camera.forward, distance=50)
        if hit_info and hit_info.hit and hasattr(hit_info.entity, 'cell_data'):
            cell = hit_info.entity
            if self.cell_system.energy_sources:
                source = self.cell_system.energy_sources[0]
                self.cell_system.create_signal(source, cell, 'energy_transfer', 1.0)

    def trigger_replication(self):
        hit_info = raycast(camera.world_position, camera.forward, distance=50)
        if hit_info and hit_info.hit and hasattr(hit_info.entity, 'cell_data'):
            hit_info.entity.cell_data['state'] = 'replicating'

    def create_colony(self):
        hit_info = raycast(camera.world_position, camera.forward, distance=50)
        if hit_info and hit_info.hit:
            position = hit_info.entity.position + hit_info.normal
            position = (round(position.x), round(position.y), round(position.z))
        else:
            position = player.position + player.forward * 5
            position = (round(position.x), round(position.y), round(position.z))
        self.cell_system.create_cell_colony(position)

    def boost_all_cells(self):
        for cell in self.cell_system.cells:
            if hasattr(cell, 'cell_data'):
                cell.cell_data['energy'] = min(cell.cell_data['max_energy'], cell.cell_data['energy'] + 30)

    def speed_up(self):
        self.cell_system.simulation_speed = min(3.0, self.cell_system.simulation_speed + 0.5)

    def slow_down(self):
        self.cell_system.simulation_speed = max(0.1, self.cell_system.simulation_speed - 0.5)

    def clear_selected_cells(self):
        block_manager.selected_blocks.clear()
        block_manager.update_selection_visual()

    def set_cell_type(self, cell_type):
        self.selected_cell_type = cell_type

    def set_signal_type(self, signal_type):
        self.selected_signal_type = signal_type

    def load_available_programs(self):
        try:
            programs = assembler.get_available_programs()
            if programs:
                self.console_output.text = f'Loaded {len(programs)} program(s): {", ".join(programs)}'
            else:
                self.console_output.text = 'No programs found.'
        except Exception as e:
            self.console_output.text = f'Error loading programs: {str(e)}'

# ---------------------------------------------------------------------------
# Player / scene utilities
# ---------------------------------------------------------------------------
def _entity_node_alive(ent):
    if ent is None:
        return False
    try:
        _ = ent.enabled
        return True
    except (AssertionError, AttributeError):
        return False


def _purge_duplicate_players(keep_player):
    for ent in list(scene.entities):
        if isinstance(ent, FirstPersonController) and ent is not keep_player:
            try:
                ent.visible = False
                ent.disable()
            except (AssertionError, AttributeError):
                pass


class SafeFirstPersonController(FirstPersonController):
    def update(self):
        if not _entity_node_alive(self) or not _entity_node_alive(getattr(self, 'camera_pivot', None)):
            return
        try:
            super().update()
        except (AssertionError, AttributeError):
            return

# ---------------------------------------------------------------------------
# Scene setup
# ---------------------------------------------------------------------------
sky = Sky()
player = SafeFirstPersonController()
_purge_duplicate_players(player)

# Initialize game systems
block_manager = BlockManager()
cell_system = CellSystem(block_manager)
organism = Organism(cell_system, block_manager)
gravity_gun = GravityGun(block_manager)
assembler = Assembler()
advanced_ui = AdvancedUI(cell_system)
redstone_engine = RedstoneEngine(block_manager)
field_shell_manager = FieldShellManager(block_manager)
current_redstone_tool = None
ui_cursor = UICursor()

# Terrain
for x in range(15):
    for z in range(15):
        block_manager.add_block(position=(x, 0, z), color=color.gray, is_terrain=True)

# Initial colony + energy sources
cell_system.create_cell_colony((7, 1, 7))
cell_system.create_cell((12, 1, 3), 'energy')
cell_system.create_cell((3, 1, 12), 'energy')

# Demo field overlays
field_shell_manager.spawn((7, 4, 7), 'cyan', radius=5, shape='cube')
field_shell_manager.spawn((12, 3, 11), 'green', radius=3)
field_shell_manager.spawn((4, 3, 12), 'yellow', radius=3)
field_shell_manager.spawn((10, 3, 4), 'red', radius=3)

print('sonnet_3d ready.')
print('Fields: F5–F8 colors, Shift+F9 clear')
print('Organism: O morphogen A, Shift+O morphogen B; P re-detect organs')
print('Redstone: 1-9,0,- select tools, Shift+RMB place, Shift+LMB activate')
print('UI: U open, Shift+R toggle Brain overlay')
print('World dispatch: block_manager.world_dispatch("СОСТОЯНИЕ", coord, data)')

# ---------------------------------------------------------------------------
# State application  (integrates Codex3DBridge)
# ---------------------------------------------------------------------------
def apply_state_to_block(block):
    """Apply current_state to a clicked block, mirroring to core World."""
    global connecting_blocks, current_state, state_data

    if not (ui_interaction_mode or state_mode_active):
        return

    # Delegate to Codex3DBridge – this keeps the core World in sync
    result = block_manager.bridge.apply_state(block, current_state, state_data)

    # Also update the Ursina block's own .states dict so existing render/logic works
    if current_state == "generate":
        if 'generate' not in block.states:
            block.states['generate'] = {'active': False, 'data': None, 'direction': 'up',
                                         'cooldown': 1.0, 'last_gen_time': 0, 'target_coord': None}
        block.states['generate']['active'] = True
        block.state = 1
        if state_data and 'value' in state_data:
            block.states['generate']['data'] = state_data['value']
        if state_data and 'direction' in state_data:
            block.states['generate']['direction'] = state_data['direction']
        block.color = STATE_COLORS['generate_blocks']
        print(f"Generate state applied: {block.states['generate']['data']}, dir={block.states['generate']['direction']}, world={result}")

    elif current_state == "store":
        if 'store' not in block.states:
            block.states['store'] = {'active': False, 'data': None}
        block.states['store']['active'] = True
        if state_data and 'value' in state_data:
            block.states['store']['data'] = state_data['value']
            if not hasattr(block, 'block_data'):
                block.block_data = {}
            import json as _json
            try:
                parsed_data = _json.loads(state_data['value'])
                block.block_data.update(parsed_data)
            except Exception:
                block.block_data['value'] = state_data['value']
        block.color = STATE_COLORS['store']
        print(f"Store state applied: {block.states['store']['data']}, world={result}")

    elif current_state == "conduct":
        if 'conduct' not in block.states:
            block.states['conduct'] = {'active': False, 'data': None, 'direction': 'all', 'connections': []}
        block.states['conduct']['active'] = True
        block.state = 1
        if state_data and 'value' in state_data:
            block.states['conduct']['data'] = state_data['value']
        if state_data and 'direction' in state_data:
            block.states['conduct']['direction'] = state_data['direction']
        block.color = STATE_COLORS['conduct']
        print(f"Conduct state applied: {block.states['conduct']['data']}, world={result}")

    elif current_state == "connect":
        # Codex3DBridge tracks _connect_first internally; on the second block it
        # fires СОЕДИНЕНИЕ in the World.  We mirror visuals here.
        connecting_blocks.append(block)
        if len(connecting_blocks) == 2:
            source, target = connecting_blocks
            if 'connect' not in source.states:
                source.states['connect'] = {'target': None, 'active': False}
            source.states['connect'] = {'target': target.position, 'active': True}
            if 'conduct' not in source.states:
                source.states['conduct'] = {'active': False, 'connections': []}
            if 'connections' not in source.states['conduct']:
                source.states['conduct']['connections'] = []
            source.states['conduct']['connections'].append(target.position)
            source.color = STATE_COLORS['connect']
            print(f"Connected {source.position} → {target.position}, world={result}")
            connecting_blocks.clear()
        else:
            block.color = color.yellow

# ---------------------------------------------------------------------------
# Input handler
# ---------------------------------------------------------------------------
def input(key):
    global ui_interaction_mode, cell_mode_active, gravity_gun_active, state_mode_active
    global current_state, dragging, start_drag_pos, start_drag_screen_y
    global initial_block_ys, current_redstone_tool

    if key == 'u':
        advanced_ui.toggle_ui_mode()
        return

    if key == 'r' and held_keys['shift'] and ui_interaction_mode:
        advanced_ui.toggle_brain_ui_overlay()
        return

    if key == 'c' and not held_keys['shift']:
        advanced_ui.toggle_cell_mode()
        return

    if key == 'o' and organism is not None:
        mtype = 'B' if held_keys['shift'] else 'A'
        organism.place_morphogen_at_crosshair(mtype)
        return

    if key == 'p' and not held_keys['shift'] and organism is not None:
        organism.organ_system.detect_and_update()
        organism.organ_system.sync_brain_regions(block_manager.brain)
        print('Organs:', organism.get_stats())
        return

    # Redstone tool selection
    redstone_key_map = {
        '1': 'lever', '2': 'wire', '3': 'lamp', '4': 'torch',
        '5': 'repeater', '6': 'comparator', '7': 'button',
        '8': 'pressure_plate', '9': 'and_gate', '0': 'or_gate', '-': 'not_gate',
    }
    if key in redstone_key_map and not ui_interaction_mode:
        current_redstone_tool = redstone_key_map[key]
        print(f'Redstone tool: {current_redstone_tool}')
        return

    # Field overlay shells
    if not ui_interaction_mode:
        if key == 'f5':
            field_shell_manager.spawn_at_crosshair('cyan')
            return
        if key == 'f6':
            field_shell_manager.spawn_at_crosshair('green')
            return
        if key == 'f7':
            field_shell_manager.spawn_at_crosshair('yellow')
            return
        if key == 'f8':
            field_shell_manager.spawn_at_crosshair('red')
            return
        if key == 'f9' and held_keys['shift']:
            field_shell_manager.clear_all()
            return

    # Gravity Gun toggle
    if key == 'g' and held_keys['shift']:
        gravity_gun_active = not gravity_gun_active
        if gravity_gun_active:
            gravity_gun.activate()
            advanced_ui.gravity_gun_display.text = 'Gravity Gun: ON'
            advanced_ui.gravity_gun_display.color = color.orange
            if dragging:
                dragging = False
        else:
            gravity_gun.deactivate()
            advanced_ui.gravity_gun_display.text = 'Gravity Gun: OFF'
            advanced_ui.gravity_gun_display.color = color.gray
            dragging = False
            start_drag_pos = None
            start_drag_screen_y = None
            initial_block_ys = []
            if block_manager.selected_blocks:
                block_manager.update_selection_visual()
        return

    if ui_interaction_mode:
        if key == 'escape':
            advanced_ui.toggle_ui_mode()
        return

    # Gravity gun mouse controls
    if gravity_gun_active and not ui_interaction_mode:
        if key == 'scroll up':
            gravity_gun.held_distance = max(gravity_gun.min_distance, gravity_gun.held_distance - 0.5)
        elif key == 'scroll down':
            gravity_gun.held_distance = min(gravity_gun.max_distance, gravity_gun.held_distance + 0.5)
        if key == 'middle mouse down':
            if gravity_gun.held_block:
                gravity_gun.release_block()
            else:
                hit_info = raycast(camera.world_position, camera.forward, distance=gravity_gun.max_distance)
                if hit_info and hit_info.hit and hit_info.entity in block_manager.blocks:
                    gravity_gun.pick_block(hit_info.entity)
        elif key == 'right mouse down':
            new_block = block_manager.add_block()
            if new_block:
                gravity_gun.pick_block(new_block)
        return

    # World interaction – right mouse
    if key == 'right mouse down' and not gravity_gun_active:
        if held_keys['shift'] and current_redstone_tool:
            hit_info = raycast(camera.world_position, camera.forward, distance=50)
            if hit_info and hit_info.hit:
                target = hit_info.entity.position + hit_info.normal
                target = (round(target.x), round(target.y), round(target.z))
            else:
                target = block_manager.get_air_position_at_crosshair()
            block = block_manager.get_block_by_coord(target)
            if not block:
                block = block_manager.add_block(position=target)
            if block:
                redstone_engine.place_component(target, current_redstone_tool)
            return
        if advanced_ui.cell_mode_active and hasattr(advanced_ui, 'selected_cell_type'):
            hit_info = raycast(camera.world_position, camera.forward, distance=50)
            if hit_info and hit_info.hit:
                position = hit_info.entity.position + hit_info.normal
                position = (round(position.x), round(position.y), round(position.z))
            else:
                position = block_manager.get_air_position_at_crosshair()
            cell_system.create_cell(position, advanced_ui.selected_cell_type)
        else:
            hit_info = raycast(camera.world_position, camera.forward, distance=50)
            if hit_info and hit_info.hit:
                position = hit_info.entity.position + hit_info.normal
                position = (round(position.x), round(position.y), round(position.z))
            else:
                position = block_manager.get_air_position_at_crosshair()
            block_manager.add_block(position=position)

    # World interaction – left mouse
    if key == 'left mouse down' and not gravity_gun_active:
        hit_info = raycast(camera.world_position, camera.forward, distance=50)
        if hit_info and hit_info.hit and hit_info.entity in block_manager.blocks:
            block = hit_info.entity
            if held_keys['shift'] and hasattr(block, 'redstone') and block.redstone.get('type') in ('lever', 'button', 'pressure_plate'):
                redstone_engine.activate_component(tuple(block.position))
                return
            if state_mode_active:
                apply_state_to_block(block)
            if block in block_manager.selected_blocks:
                block_manager.selected_blocks.remove(block)
            else:
                block_manager.selected_blocks.append(block)
            block_manager.update_selection_visual()
            dragging = True
            if mouse.world_point:
                start_drag_pos = mouse.world_point
            start_drag_screen_y = mouse.y
            initial_block_ys = [b.y for b in block_manager.selected_blocks]

    if key == 'left mouse up':
        dragging = False

    if key == 'delete':
        for block in block_manager.selected_blocks[:]:
            if hasattr(block, 'cell_data'):
                cell_system.remove_cell(block)
            else:
                if hasattr(block, 'redstone'):
                    redstone_engine.remove_component(tuple(block.position))
                block_manager.remove_block(block)
        block_manager.selected_blocks.clear()

    # State shortcuts (only when not in gravity-gun mode)
    if not ui_interaction_mode and not gravity_gun_active:
        if key == 'g' and not held_keys['shift']:
            advanced_ui.set_generate_state()
        elif key == 's' and not held_keys['shift']:
            advanced_ui.set_store_state()
        elif key == 'c' and not held_keys['shift']:
            advanced_ui.set_conduct_state()
        elif key == 'x':
            advanced_ui.set_connect_state()
        elif key == 'escape':
            global state_data
            current_state = None
            state_data = {}
            state_mode_active = False
            advanced_ui.state_mode_display.text = 'State Mode: OFF'
            advanced_ui.state_mode_display.color = color.gray
            advanced_ui.data_input.visible = False
            advanced_ui.data_input_label.visible = False
            advanced_ui.data_input.text = ''
            advanced_ui.update_state_display()

    # Send signal to hovered cell (Shift+S)
    if key == 's' and held_keys['shift']:
        hit_info = raycast(camera.world_position, camera.forward, distance=50)
        if hit_info and hit_info.hit and hasattr(hit_info.entity, 'cell_data'):
            if hasattr(advanced_ui, 'selected_signal_type'):
                target = hit_info.entity
                source = None
                min_dist = float('inf')
                for cell in cell_system.cells:
                    if cell != target:
                        dist = cell_system.cell_distance(cell, target)
                        if dist < min_dist:
                            min_dist = dist
                            source = cell
                if source:
                    cell_system.create_signal(source, target, advanced_ui.selected_signal_type, 1.0)

# ---------------------------------------------------------------------------
# Main update loop
# ---------------------------------------------------------------------------
def update():
    global dragging, start_drag_pos, start_drag_screen_y, initial_block_ys

    # Redstone fixed-tick simulation
    redstone_engine.maybe_tick()

    # Cell system
    cell_system.update()

    # Organism (organs, morphogens, resource flow, homeostasis, reflexes)
    if organism is not None:
        organism.tick()

    # ── Codex3DBridge: mirror conduct blocks into core World ──────────────────
    block_manager.bridge.process_conductive_blocks(block_manager.blocks)
    # ──────────────────────────────────────────────────────────────────────────

    # Gravity gun
    gravity_gun.update()

    # UI
    advanced_ui.update()
    ui_cursor.update()

    # Gravity gun display
    if gravity_gun_active:
        if gravity_gun.held_block:
            advanced_ui.gravity_gun_display.text = f'Gravity Gun: HOLDING (Dist: {gravity_gun.held_distance:.1f})'
            advanced_ui.gravity_gun_display.color = color.orange
        else:
            advanced_ui.gravity_gun_display.text = 'Gravity Gun: READY'
            advanced_ui.gravity_gun_display.color = color.green
    else:
        advanced_ui.gravity_gun_display.text = 'Gravity Gun: OFF'
        advanced_ui.gravity_gun_display.color = color.gray

    # Block hover tracking
    block_manager.hovered_block = None
    for box in block_manager.blocks:
        if box.hovered:
            block_manager.hovered_block = box
            break

    # Block dragging
    if dragging and block_manager.selected_blocks and not ui_interaction_mode and not gravity_gun_active:
        if held_keys['shift'] and start_drag_screen_y:
            delta_y = (mouse.y - start_drag_screen_y) * 0.1
            for i, block in enumerate(block_manager.selected_blocks):
                if i < len(initial_block_ys):
                    block.y = initial_block_ys[i] + delta_y
        elif start_drag_pos and mouse.world_point:
            delta = mouse.world_point - start_drag_pos
            for block in block_manager.selected_blocks:
                block.position += delta
            start_drag_pos = mouse.world_point

    # Process block signals and generation (state = 1)
    for block in block_manager.blocks:
        if not hasattr(block, 'state'):
            continue
        if block.state == 1 and 'conduct' in block.states and block.states['conduct'].get('active', False):
            conduct_data = block.states['conduct']
            for target_coord in conduct_data.get('connections', []):
                block_manager.send_signal(block.position, target_coord, conduct_data.get('data', {}))
        if block.state == 1 and 'generate' in block.states and block.states['generate'].get('active', False):
            generate_data = block.states['generate']
            current_time = time.time()
            if current_time - generate_data.get('last_gen_time', 0) >= generate_data.get('cooldown', 1.0):
                target_coord = generate_data.get('target_coord')
                if not target_coord:
                    direction = generate_data.get('direction', 'up')
                    x, y, z = block.position
                    offsets = {
                        'up': (x, y + 1, z), 'down': (x, y - 1, z),
                        'north': (x, y, z + 1), 'south': (x, y, z - 1),
                        'east': (x + 1, y, z), 'west': (x - 1, y, z),
                    }
                    target_coord = offsets.get(direction, (x, y + 1, z))
                block_manager.generate_at_position(block.position, target_coord, generate_data.get('data'))
                generate_data['last_gen_time'] = current_time


# ---------------------------------------------------------------------------
# Signal visualization
# ---------------------------------------------------------------------------
def visualize_signals():
    for signal in cell_system.signals:
        if hasattr(signal['source'], 'position') and hasattr(signal['target'], 'position'):
            start = signal['source'].position
            end = signal['target'].position
            progress = signal['progress'] / signal['max_progress']
            current_pos = (
                start[0] + (end[0] - start[0]) * progress,
                start[1] + (end[1] - start[1]) * progress,
                start[2] + (end[2] - start[2]) * progress,
            )
            sphere = Entity(model='sphere', position=current_pos, scale=0.2,
                            color=signal['color'], eternal=False)
            invoke(destroy, sphere, delay=0.1)


def update_with_visuals():
    update()
    visualize_signals()
