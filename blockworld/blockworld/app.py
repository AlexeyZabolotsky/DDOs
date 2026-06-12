"""
Blockworld 3D — симуляция блоков с выделением полем и popup-параметрами.

Объединяет функционал пользовательского Ursina-кода и HUD из redstone/view3d.
"""

from __future__ import annotations

import time

from ursina import (
    Sky,
    Ursina,
    Vec3,
    application,
    camera,
    color,
    destroy,
    held_keys,
    invoke,
    mouse,
    raycast,
    scene,
)
from ursina.prefabs import first_person_controller as _fpc_module
from ursina.prefabs.first_person_controller import FirstPersonController

FirstPersonController.update = _fpc_module.FirstPersonController.__dict__["update"]

from blockworld.params import apply_block_params
from blockworld.systems.block_manager import BlockManager
from blockworld.systems.cells import CellSystem
from blockworld.systems.fields import FieldShellManager
from blockworld.systems.redstone import RedstoneEngine
from blockworld.ui.block_popup import BlockParameterPopup
from blockworld.ui.extended_hud import ExtendedHUD
from blockworld.ui.field_selector import FieldSelector

# --- globals ---
app = Ursina()
application.quit_keys = ("escape",)

dragging = False
start_drag_pos = None
start_drag_screen_y = 0
initial_block_ys = []
connecting_blocks = []
ui_interaction_mode = False
state_mode_active = False
current_state = None
state_data = {}
simulation_active = True
current_redstone_tool = "wire"

block_manager = BlockManager()
cell_system = CellSystem(block_manager)
redstone_engine = RedstoneEngine(block_manager)
field_shell_manager = FieldShellManager(block_manager)
field_selector = FieldSelector(block_manager, field_shell_manager)
hud = ExtendedHUD()
block_popup = BlockParameterPopup(
    block_manager,
    on_apply=lambda b, p: apply_block_params(b, p, block_manager, redstone_engine, cell_system, getattr(block_manager, "brain", None)),
)

try:
    from blockworld.systems.brain import BrainNetwork
    block_manager.brain = BrainNetwork(block_manager)
except ImportError:
    block_manager.brain = None


def _entity_alive(ent):
    if ent is None:
        return False
    try:
        _ = ent.enabled
        return True
    except (AssertionError, AttributeError):
        return False


class SafeFirstPersonController(FirstPersonController):
    def update(self):
        if not _entity_alive(self) or not _entity_alive(getattr(self, "camera_pivot", None)):
            return
        try:
            super().update()
        except (AssertionError, AttributeError):
            return


sky = Sky()
player = SafeFirstPersonController()

for x in range(15):
    for z in range(15):
        block_manager.add_block(position=(x, 0, z), color_=color.gray, is_terrain=True)

cell_system.create_cell_colony((7, 1, 7))
field_shell_manager.spawn((7, 4, 7), "cyan", radius=5, shape="cube")


def apply_state_to_block(block):
    global connecting_blocks, current_state, state_data
    if not (ui_interaction_mode or state_mode_active):
        return
    if current_state == "generate":
        block.states.setdefault("generate", {"active": False, "data": None, "direction": "up", "cooldown": 1.0, "last_gen_time": 0})
        block.states["generate"]["active"] = True
        block.state = 1
        if state_data and "value" in state_data:
            block.states["generate"]["data"] = state_data["value"]
        block.color = color.green
    elif current_state == "store":
        block.states.setdefault("store", {"active": False, "data": None})
        block.states["store"]["active"] = True
        if state_data and "value" in state_data:
            block.states["store"]["data"] = state_data["value"]
            block.block_data["value"] = state_data["value"]
    elif current_state == "conduct":
        block.states.setdefault("conduct", {"active": False, "data": None, "direction": "all", "connections": []})
        block.states["conduct"]["active"] = True
        block.state = 1
    elif current_state == "connect":
        connecting_blocks.append(block)
        if len(connecting_blocks) == 2:
            source, target = connecting_blocks
            source.states["connect"] = {"target": target.position, "active": True}
            source.states.setdefault("conduct", {"active": False, "connections": []})
            source.states["conduct"].setdefault("connections", []).append(target.position)
            connecting_blocks = []


def _hit_block():
    hit = raycast(camera.world_position, camera.forward, distance=50)
    if hit and hit.hit and hit.entity in block_manager.blocks:
        return hit.entity
    return None


def _handle_left_click():
    global dragging, start_drag_pos, start_drag_screen_y, initial_block_ys
    block = _hit_block()
    if block is None:
        return

    mode = hud.current_mode()

    if mode == "field_select" or (held_keys["f"] and not ui_interaction_mode):
        selected = field_selector.select_at_block(block)
        hud.set_field_info(f"Поле: {len(selected)} блоков, R={field_selector.radius}, {field_selector.shape}")
        return

    if mode == "params":
        block_popup.show_for_block(block)
        return

    if held_keys["shift"] and hasattr(block, "redstone"):
        redstone_engine.activate_component(tuple(block.position))
        return

    if state_mode_active:
        apply_state_to_block(block)

    if mode == "connect":
        current_state_local = "connect"
        globals()["current_state"] = current_state_local
        apply_state_to_block(block)
    elif mode == "conduct":
        globals()["current_state"] = "conduct"
        globals()["state_mode_active"] = True
        apply_state_to_block(block)
    elif mode == "generate":
        globals()["current_state"] = "generate"
        globals()["state_mode_active"] = True
        apply_state_to_block(block)
    elif mode == "store":
        globals()["current_state"] = "store"
        globals()["state_mode_active"] = True
        apply_state_to_block(block)
    elif mode == "redstone" and current_redstone_tool:
        pos = tuple(int(round(x)) for x in block.position)
        redstone_engine.place_component(pos, current_redstone_tool)
    elif mode == "cell":
        cell_system.create_cell(tuple(int(round(x)) for x in block.position), "stem")
    else:
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


def input(key):
    global ui_interaction_mode, dragging, current_state, state_data, state_mode_active, current_redstone_tool

    if key == "e":
        block = _hit_block()
        if block:
            block_popup.show_for_block(block)
        return

    if key == "u":
        ui_interaction_mode = not ui_interaction_mode
        mouse.locked = not ui_interaction_mode
        hud.set_status(f"UI mode: {'ON' if ui_interaction_mode else 'OFF'}")
        return

    if key.isdigit() and key != "0":
        slot = hud.select_slot(int(key) - 1)
        mode = slot["mode"]
        if mode in ("connect", "conduct", "generate", "store"):
            globals()["current_state"] = mode
            globals()["state_mode_active"] = True
        elif mode == "field_select":
            field_selector.active = True
        return

    if key == "f" and not ui_interaction_mode:
        block = _hit_block()
        if block:
            field_selector.select_at_block(block)
        return

    if key == "scroll up" and field_selector.active:
        field_selector.set_radius(field_selector.radius + 1)
        hud.set_field_info(f"R={field_selector.radius} {field_selector.shape}")
        return
    if key == "scroll down" and field_selector.active:
        field_selector.set_radius(field_selector.radius - 1)
        hud.set_field_info(f"R={field_selector.radius} {field_selector.shape}")
        return

    if key == "tab":
        shape = field_selector.toggle_shape()
        hud.set_field_info(f"Форма поля: {shape}")
        return

    if key == "f5":
        field_shell_manager.spawn_at_crosshair("cyan", player=player)
        return
    if key == "f9" and held_keys["shift"]:
        field_shell_manager.clear_all()
        field_selector.clear_shell()
        return

    redstone_keys = {
        "1": "lever", "2": "wire", "3": "lamp", "4": "torch",
        "5": "repeater", "6": "comparator", "7": "button",
        "8": "pressure_plate", "9": "and_gate", "0": "or_gate", "-": "not_gate",
    }
    if key in redstone_keys and held_keys["shift"]:
        current_redstone_tool = redstone_keys[key]
        hud.set_status(f"Redstone: {current_redstone_tool}")
        return

    if ui_interaction_mode:
        if key == "escape":
            ui_interaction_mode = False
            mouse.locked = True
        return

    if key == "right mouse down":
        hit = raycast(camera.world_position, camera.forward, distance=50)
        if hit and hit.hit:
            pos = hit.entity.position + hit.normal
            pos = (round(pos.x), round(pos.y), round(pos.z))
        else:
            pos = block_manager.get_air_position_at_crosshair(player)
        if held_keys["shift"] and current_redstone_tool:
            block = block_manager.get_block_by_coord(pos) or block_manager.add_block(position=pos)
            if block:
                redstone_engine.place_component(pos, current_redstone_tool)
        else:
            block_manager.add_block(position=pos)
        return

    if key == "left mouse down":
        _handle_left_click()
        return

    if key == "left mouse up":
        dragging = False
        return

    if key == "delete":
        for block in block_manager.selected_blocks[:]:
            if hasattr(block, "cell_data"):
                cell_system.remove_cell(block)
            else:
                if hasattr(block, "redstone"):
                    redstone_engine.remove_component(tuple(block.position))
                block_manager.remove_block(block)
        block_manager.selected_blocks.clear()

    if key == "escape":
        block_popup.close()
        state_mode_active = False
        current_state = None


def update():
    global dragging, start_drag_pos

    redstone_engine.maybe_tick()
    if simulation_active:
        cell_system.update()

    stats = cell_system.get_cell_stats()
    hud.set_status(
        f"Cells: {stats['total']} | Selected: {len(block_manager.selected_blocks)} | "
        f"Mode: {hud.current_mode()}"
    )

    if dragging and block_manager.selected_blocks and not ui_interaction_mode:
        if held_keys["shift"] and start_drag_screen_y:
            delta_y = (mouse.y - start_drag_screen_y) * 0.1
            for i, block in enumerate(block_manager.selected_blocks):
                if i < len(initial_block_ys):
                    block.y = initial_block_ys[i] + delta_y
        elif start_drag_pos and mouse.world_point:
            delta = mouse.world_point - start_drag_pos
            for block in block_manager.selected_blocks:
                block.position += delta
            start_drag_pos = mouse.world_point

    for block in block_manager.blocks:
        if not hasattr(block, "state") or block.state != 1:
            continue
        if block.states.get("conduct", {}).get("active"):
            for target_coord in block.states["conduct"].get("connections", []):
                block_manager.send_signal(block.position, target_coord, block.states["conduct"].get("data", {}))
        if block.states.get("generate", {}).get("active"):
            gd = block.states["generate"]
            now = time.time()
            if now - gd.get("last_gen_time", 0) >= gd.get("cooldown", 1.0):
                x, y, z = block.position
                d = gd.get("direction", "up")
                dirs = {"up": (0, 1, 0), "down": (0, -1, 0), "north": (0, 0, 1), "south": (0, 0, -1), "east": (1, 0, 0), "west": (-1, 0, 0)}
                dx, dy, dz = dirs.get(d, (0, 1, 0))
                target = (x + dx, y + dy, z + dz)
                block_manager.generate_at_position(block.position, target, gd.get("data"))
                gd["last_gen_time"] = now


def run():
    print("Blockworld: E — параметры блока | F — выделение полем | 2 — режим поля | Tab — форма")
    app.run()


if __name__ == "__main__":
    run()
