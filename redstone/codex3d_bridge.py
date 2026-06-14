"""Bridge for wiring `redstone.core` logic into a 3D/Ursina scene.

This module is designed for the large Ursina script shared by the user:
it keeps all world mutations in the canonical message format and delegates
execution to ``World.dispatch``.
"""

from __future__ import annotations

import copy
import json
from typing import Any, Dict, Iterable, Optional, Tuple

from redstone.core import Coord, World, СОСТОЯНИЯ, сообщение


def _to_coord(value: Any) -> Coord:
    """Normalize tuple/list/Vec3-like value to integer 3D coordinate."""
    if hasattr(value, "x") and hasattr(value, "y") and hasattr(value, "z"):
        return (int(round(value.x)), int(round(value.y)), int(round(value.z)))
    x, y, z = value
    return (int(round(x)), int(round(y)), int(round(z)))


class Codex3DBridge:
    """Adapter that applies 3D scene states through `redstone.core.World`.

    Typical usage inside Ursina script:
        bridge = Codex3DBridge()
        bridge.apply_state(clicked_block, current_state, state_data)
        bridge.process_conductive_blocks(block_manager.blocks)
    """

    def __init__(self, world: Optional[World] = None) -> None:
        self.world = world or World()
        self._connect_first: Optional[Coord] = None

    def ensure_block(self, coord: Coord, color: str = "#9e9e9e") -> None:
        if coord in self.world.блоки:
            return
        self.world.dispatch(сообщение(СОСТОЯНИЯ["ГЕНЕРАЦИЯ"], coord, {"цвет": color}))

    def apply_state(
        self,
        block_or_coord: Any,
        current_state: Optional[str],
        state_data: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Apply Ursina state (`generate/store/conduct/connect`) via messages."""
        coord = _to_coord(getattr(block_or_coord, "position", block_or_coord))
        payload = state_data or {}
        self.ensure_block(coord)

        if current_state == "generate":
            data: Dict[str, Any] = {"active": True}
            if "value" in payload:
                data["data"] = payload["value"]
            if "direction" in payload:
                data["direction"] = payload["direction"]
            self.world.dispatch(
                сообщение(СОСТОЯНИЯ["СОХРАНЕНИЕ"], coord, {"generate": data})
            )
            return {"status": "applied", "state": "generate", "coord": coord}

        if current_state == "store":
            parsed = self._parse_state_value(payload.get("value"))
            if isinstance(parsed, dict):
                store_data = parsed
            elif parsed is None:
                store_data = {}
            else:
                store_data = {"value": parsed}
            self.world.dispatch(сообщение(СОСТОЯНИЯ["СОХРАНЕНИЕ"], coord, store_data))
            return {"status": "applied", "state": "store", "coord": coord}

        if current_state == "conduct":
            data = {"active": True}
            if "value" in payload:
                data["data"] = payload["value"]
            if "direction" in payload:
                data["direction"] = payload["direction"]
            self.world.dispatch(
                сообщение(СОСТОЯНИЯ["СОХРАНЕНИЕ"], coord, {"conduct": data})
            )
            return {"status": "applied", "state": "conduct", "coord": coord}

        if current_state == "connect":
            if self._connect_first is None:
                self._connect_first = coord
                return {"status": "pending", "coord": coord}
            source = self._connect_first
            self._connect_first = None
            if source == coord:
                return {"status": "ignored_same_block", "coord": coord}
            self.ensure_block(source)
            self.ensure_block(coord)
            self.world.dispatch(
                сообщение(СОСТОЯНИЯ["СОЕДИНЕНИЕ"], source, {"с": list(coord)})
            )
            return {"status": "connected", "source": source, "target": coord}

        return {"status": "ignored", "coord": coord}

    def process_conductive_blocks(self, blocks: Iterable[Any]) -> None:
        """Mirror `conduct` state from Ursina blocks into core transmission."""
        for block in blocks:
            if getattr(block, "state", 0) != 1:
                continue
            states = getattr(block, "states", {}) or {}
            conduct = states.get("conduct", {})
            if not isinstance(conduct, dict) or not conduct.get("active", False):
                continue

            source = _to_coord(getattr(block, "position", block))
            self.ensure_block(source)

            connections = conduct.get("connections", [])
            data = conduct.get("data", {})
            if not isinstance(data, dict):
                data = {"value": data}

            for target in connections:
                target_coord = _to_coord(target)
                self.ensure_block(target_coord)
                if target_coord not in self.world.блоки[source].соединения:
                    self.world.dispatch(
                        сообщение(СОСТОЯНИЯ["СОЕДИНЕНИЕ"], source, {"с": list(target_coord)})
                    )
                self.world.dispatch(сообщение(СОСТОЯНИЯ["ПЕРЕДАЧА"], source, data))

    def snapshot(self) -> Dict[Coord, Dict[str, Any]]:
        """Export current world state in a format convenient for scene sync."""
        out: Dict[Coord, Dict[str, Any]] = {}
        for coord, block in self.world.блоки.items():
            out[coord] = {
                "memory": copy.deepcopy(block.память),
                "signal": copy.deepcopy(block.сигнал),
                "blocked": block.заблокирован,
                "selected": block.выделен,
                "color": block.цвет,
                "connections": sorted(block.соединения),
            }
        return out

    @staticmethod
    def _parse_state_value(value: Any) -> Any:
        if value is None:
            return None
        if isinstance(value, (dict, list, int, float, bool)):
            return value
        if isinstance(value, str):
            text = value.strip()
            if not text:
                return ""
            try:
                return json.loads(text)
            except json.JSONDecodeError:
                return value
        return value
