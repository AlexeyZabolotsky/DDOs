"""Применение параметров из popup к блоку."""

from __future__ import annotations

import json
from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from blockworld.systems.block_manager import BlockManager
    from blockworld.systems.redstone import RedstoneEngine
    from blockworld.systems.cells import CellSystem


def apply_block_params(
    block,
    params: dict[str, Any],
    block_manager: "BlockManager",
    redstone_engine: "RedstoneEngine | None" = None,
    cell_system: "CellSystem | None" = None,
    brain=None,
) -> None:
    direction = params.get("direction", "up")
    value = params.get("value", "")
    active = params.get("active", 0)
    state_mode = params.get("state_mode")

    if state_mode == "connect":
        block.states.setdefault("connect", {})["active"] = True
        block.states["connect"]["target"] = None
        block.color = __import__("blockworld.constants", fromlist=["STATE_COLORS"]).STATE_COLORS["connect"]
    elif state_mode == "conduct":
        block.states.setdefault("conduct", {"active": False, "data": None, "direction": "all", "connections": []})
        block.states["conduct"]["active"] = True
        block.states["conduct"]["direction"] = direction
        if value:
            block.states["conduct"]["data"] = value
        block.state = active
    elif state_mode == "generate":
        block.states.setdefault("generate", {"active": False, "data": None, "direction": "up", "cooldown": 1.0, "last_gen_time": 0})
        block.states["generate"]["active"] = True
        block.states["generate"]["direction"] = direction
        if value:
            block.states["generate"]["data"] = value
        block.state = active
    elif state_mode == "store":
        block.states.setdefault("store", {"active": False, "data": None})
        block.states["store"]["active"] = True
        if value:
            block.states["store"]["data"] = value
            try:
                block.block_data.update(json.loads(value))
            except (json.JSONDecodeError, TypeError):
                block.block_data["value"] = value
    elif state_mode is None:
        for key in ("connect", "conduct", "generate", "store"):
            if key in block.states:
                block.states[key]["active"] = False

    if value and state_mode not in ("store", "conduct", "generate"):
        try:
            block.block_data.update(json.loads(value))
        except (json.JSONDecodeError, TypeError):
            block.block_data["value"] = value

    block.state = active

    rtype = params.get("redstone_type")
    if rtype and redstone_engine is not None:
        pos = tuple(int(round(x)) for x in block.position)
        redstone_engine.place_component(pos, rtype)
        if hasattr(block, "redstone"):
            block.redstone["power"] = params.get("power", 0)

    cell_type = params.get("cell_type")
    if cell_system is not None and cell_type:
        if not hasattr(block, "cell_data"):
            block.cell_data = {
                "type": cell_type,
                "energy": 50,
                "max_energy": 100,
                "age": 0,
                "state": "idle",
                "connections": [],
                "memory": [],
            }
            if block not in cell_system.cells:
                cell_system.cells.append(block)
                cell_system.total_cells += 1
        else:
            block.cell_data["type"] = cell_type

    neuron_type = params.get("neuron_type")
    if neuron_type and neuron_type != "(нет)" and brain is not None:
        brain.add_neuron(block, neuron_type)
        block.block_data["neuron_type"] = neuron_type

    block_manager.update_block_color(block)
