"""Simple data-driven "redstone" block network.

The module models blocks that can be created, destroyed, connected, grouped,
locked, and used to pass arbitrary nested dictionary data. Every operation can
be called directly through Python methods or dispatched from a data packet with
keys like:

    {
        "состояние": "save",
        "координата воздействия": (1, 2, 3),
        "передаваемые данные": {"any": {"nested": "dict"}}
    }

Mouse input is represented by :meth:`RedstoneWorld.click`, which can either use
an explicit payload or a block's ``state["click_actions"]`` mapping.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping
import copy


Coordinate = tuple[int, int, int]
NestedData = dict[str, Any]


STATE_KEYS = ("состояние", "состояни", "state", "status")
COORDINATE_KEYS = (
    "координата воздействия",
    "impact_coordinate",
    "coordinate",
    "координата",
)
DATA_KEYS = (
    "передаваемые данные",
    "transmitted_data",
    "data",
    "payload",
)
ACTION_KEYS = ("действие", "action", "command", "функция", "function")
TARGET_KEYS = (
    "цель",
    "target",
    "target_coordinate",
    "координата цели",
)


ACTION_ALIASES = {
    "generate": "generate",
    "create": "generate",
    "spawn": "generate",
    "создать": "generate",
    "сгенерировать": "generate",
    "генерация": "generate",
    "destroy": "destroy",
    "delete": "destroy",
    "remove": "destroy",
    "уничтожить": "destroy",
    "удалить": "destroy",
    "save": "save",
    "store": "save",
    "сохранить": "save",
    "erase": "erase",
    "clear": "erase",
    "wipe": "erase",
    "стереть": "erase",
    "очистить": "erase",
    "transfer": "transfer",
    "send": "transfer",
    "pass": "transfer",
    "передать": "transfer",
    "передача": "transfer",
    "lock_transfer": "lock_transfer",
    "lock": "lock_transfer",
    "block_transfer": "lock_transfer",
    "заблокировать": "lock_transfer",
    "заблокировать_передачу": "lock_transfer",
    "unlock_transfer": "unlock_transfer",
    "unlock": "unlock_transfer",
    "unblock_transfer": "unlock_transfer",
    "разблокировать": "unlock_transfer",
    "разблокировать_передачу": "unlock_transfer",
    "select_group": "select_group",
    "group": "select_group",
    "выделить_группу": "select_group",
    "группа": "select_group",
    "connect": "connect",
    "link": "connect",
    "соединить": "connect",
    "disconnect": "disconnect",
    "unlink": "disconnect",
    "разъединить": "disconnect",
    "разединить": "disconnect",
    "connect_group": "connect_group",
    "соединить_группы": "connect_group",
    "disconnect_group": "disconnect_group",
    "разъединить_группы": "disconnect_group",
    "разединить_группы": "disconnect_group",
    "move_group_data": "move_group_data",
    "move_connected_group_data": "move_group_data",
    "переместить_данные_группы": "move_group_data",
}


@dataclass
class RedstoneBlock:
    """A block with state, nested data, connections, and group membership."""

    coordinate: Coordinate
    state: NestedData = field(default_factory=dict)
    data: NestedData = field(default_factory=dict)
    locked_transfer: bool = False
    connections: set[Coordinate] = field(default_factory=set)
    group_ids: set[str] = field(default_factory=set)

    def save(self, data: Mapping[str, Any], *, merge: bool = True) -> None:
        """Save arbitrary nested dictionary data in the block."""

        if merge:
            deep_merge(self.data, copy.deepcopy(dict(data)))
        else:
            self.data = copy.deepcopy(dict(data))

    def erase(self, keys: Iterable[str] | None = None) -> None:
        """Erase either selected top-level keys or the full block data."""

        if keys is None:
            self.data.clear()
            return

        for key in keys:
            self.data.pop(key, None)

    def lock_transfer(self) -> None:
        self.locked_transfer = True

    def unlock_transfer(self) -> None:
        self.locked_transfer = False

    def snapshot(self) -> NestedData:
        """Return a serializable snapshot of the block."""

        return {
            "coordinate": self.coordinate,
            "state": copy.deepcopy(self.state),
            "data": copy.deepcopy(self.data),
            "locked_transfer": self.locked_transfer,
            "connections": sorted(self.connections),
            "group_ids": sorted(self.group_ids),
        }


@dataclass
class RedstoneGroup:
    """A named selection of blocks with color/state and group links."""

    group_id: str
    coordinates: set[Coordinate] = field(default_factory=set)
    color: str | None = None
    state: NestedData = field(default_factory=dict)
    connected_groups: set[str] = field(default_factory=set)

    def snapshot(self) -> NestedData:
        return {
            "group_id": self.group_id,
            "coordinates": sorted(self.coordinates),
            "color": self.color,
            "state": copy.deepcopy(self.state),
            "connected_groups": sorted(self.connected_groups),
        }


class RedstoneWorld:
    """Container and dispatcher for redstone-like block operations."""

    def __init__(self) -> None:
        self.blocks: dict[Coordinate, RedstoneBlock] = {}
        self.groups: dict[str, RedstoneGroup] = {}

    def generate_block(
        self,
        coordinate: Coordinate | Iterable[int] | Mapping[str, int],
        *,
        state: Mapping[str, Any] | str | None = None,
        data: Mapping[str, Any] | None = None,
        replace: bool = False,
    ) -> RedstoneBlock:
        """Create a block at a coordinate."""

        normalized = normalize_coordinate(coordinate)
        if normalized in self.blocks and not replace:
            raise ValueError(f"block already exists at {normalized}")

        block = RedstoneBlock(
            coordinate=normalized,
            state=normalize_state(state),
            data=copy.deepcopy(dict(data or {})),
        )
        self.blocks[normalized] = block
        return block

    def destroy_block(self, coordinate: Coordinate | Iterable[int] | Mapping[str, int]) -> RedstoneBlock:
        """Destroy a block and remove all block/group connections to it."""

        normalized = normalize_coordinate(coordinate)
        block = self.require_block(normalized)

        for connected in list(block.connections):
            if connected in self.blocks:
                self.blocks[connected].connections.discard(normalized)

        for group_id in list(block.group_ids):
            group = self.groups.get(group_id)
            if group is not None:
                group.coordinates.discard(normalized)

        del self.blocks[normalized]
        return block

    def save_block(
        self,
        coordinate: Coordinate | Iterable[int] | Mapping[str, int],
        data: Mapping[str, Any],
        *,
        merge: bool = True,
    ) -> RedstoneBlock:
        block = self.require_block(coordinate)
        block.save(data, merge=merge)
        return block

    def erase_block(
        self,
        coordinate: Coordinate | Iterable[int] | Mapping[str, int],
        keys: Iterable[str] | None = None,
    ) -> RedstoneBlock:
        block = self.require_block(coordinate)
        block.erase(keys)
        return block

    def connect(
        self,
        left: Coordinate | Iterable[int] | Mapping[str, int],
        right: Coordinate | Iterable[int] | Mapping[str, int],
        *,
        bidirectional: bool = True,
    ) -> None:
        """Connect two existing blocks."""

        left_coord = normalize_coordinate(left)
        right_coord = normalize_coordinate(right)
        self.require_block(left_coord).connections.add(right_coord)
        self.require_block(right_coord)
        if bidirectional:
            self.blocks[right_coord].connections.add(left_coord)

    def disconnect(
        self,
        left: Coordinate | Iterable[int] | Mapping[str, int],
        right: Coordinate | Iterable[int] | Mapping[str, int],
        *,
        bidirectional: bool = True,
    ) -> None:
        """Disconnect two blocks if such connection exists."""

        left_coord = normalize_coordinate(left)
        right_coord = normalize_coordinate(right)
        self.require_block(left_coord).connections.discard(right_coord)
        self.require_block(right_coord)
        if bidirectional:
            self.blocks[right_coord].connections.discard(left_coord)

    def transfer_data(
        self,
        source: Coordinate | Iterable[int] | Mapping[str, int],
        target: Coordinate | Iterable[int] | Mapping[str, int] | None = None,
        data: Mapping[str, Any] | None = None,
    ) -> list[RedstoneBlock]:
        """Transfer nested data from one block to a target or all connections."""

        source_coord = normalize_coordinate(source)
        source_block = self.require_block(source_coord)
        if source_block.locked_transfer:
            raise PermissionError(f"source block {source_coord} has locked transfer")

        if target is None:
            targets = sorted(source_block.connections)
        else:
            target_coord = normalize_coordinate(target)
            if target_coord not in source_block.connections:
                raise ValueError(f"block {target_coord} is not connected to {source_coord}")
            targets = [target_coord]

        payload = copy.deepcopy(dict(data if data is not None else source_block.data))
        updated: list[RedstoneBlock] = []
        for target_coord in targets:
            target_block = self.require_block(target_coord)
            if target_block.locked_transfer:
                raise PermissionError(f"target block {target_coord} has locked transfer")
            target_block.save(payload, merge=True)
            updated.append(target_block)
        return updated

    def lock_transfer(
        self,
        coordinate: Coordinate | Iterable[int] | Mapping[str, int],
        locked: bool = True,
    ) -> RedstoneBlock:
        block = self.require_block(coordinate)
        block.locked_transfer = locked
        return block

    def select_group(
        self,
        group_id: str,
        coordinates: Iterable[Coordinate | Iterable[int] | Mapping[str, int]],
        *,
        color: str | None = None,
        state: Mapping[str, Any] | str | None = None,
    ) -> RedstoneGroup:
        """Select a group of blocks and optionally mark it by color/state."""

        normalized_coordinates = {normalize_coordinate(coordinate) for coordinate in coordinates}
        for coordinate in normalized_coordinates:
            self.require_block(coordinate)

        group = self.groups.get(group_id, RedstoneGroup(group_id=group_id))
        group.coordinates = normalized_coordinates
        group.color = color
        group.state = normalize_state(state)
        self.groups[group_id] = group

        for block in self.blocks.values():
            block.group_ids.discard(group_id)

        for coordinate in normalized_coordinates:
            block = self.blocks[coordinate]
            block.group_ids.add(group_id)
            if color is not None:
                block.state["color"] = color
            if group.state:
                deep_merge(block.state, copy.deepcopy(group.state))

        return group

    def connect_group(self, left_group_id: str, right_group_id: str, *, bidirectional: bool = True) -> None:
        self.require_group(left_group_id).connected_groups.add(right_group_id)
        self.require_group(right_group_id)
        if bidirectional:
            self.groups[right_group_id].connected_groups.add(left_group_id)

    def disconnect_group(self, left_group_id: str, right_group_id: str, *, bidirectional: bool = True) -> None:
        self.require_group(left_group_id).connected_groups.discard(right_group_id)
        self.require_group(right_group_id)
        if bidirectional:
            self.groups[right_group_id].connected_groups.discard(left_group_id)

    def move_connected_group_data(
        self,
        source_group_id: str,
        target_group_id: str,
        data: Mapping[str, Any] | None = None,
        *,
        clear_source: bool = False,
    ) -> list[RedstoneBlock]:
        """Move or copy data from one connected group to another connected group."""

        source_group = self.require_group(source_group_id)
        target_group = self.require_group(target_group_id)
        if target_group_id not in source_group.connected_groups:
            raise ValueError(f"group {target_group_id!r} is not connected to {source_group_id!r}")

        payload = copy.deepcopy(dict(data)) if data is not None else self.collect_group_data(source_group_id)
        updated: list[RedstoneBlock] = []
        for coordinate in sorted(target_group.coordinates):
            block = self.require_block(coordinate)
            if block.locked_transfer:
                raise PermissionError(f"target block {coordinate} has locked transfer")
            block.save(payload, merge=True)
            updated.append(block)

        if clear_source:
            for coordinate in sorted(source_group.coordinates):
                self.require_block(coordinate).erase()

        return updated

    def collect_group_data(self, group_id: str) -> NestedData:
        """Collect data from all blocks in a group under coordinate string keys."""

        group = self.require_group(group_id)
        return {
            coordinate_to_key(coordinate): copy.deepcopy(self.require_block(coordinate).data)
            for coordinate in sorted(group.coordinates)
        }

    def dispatch(self, packet: Mapping[str, Any]) -> Any:
        """Execute an operation described by a state/data packet."""

        packet_dict = dict(packet)
        coordinate = get_first(packet_dict, COORDINATE_KEYS)
        state = get_first(packet_dict, STATE_KEYS)
        data = get_first(packet_dict, DATA_KEYS, default={})
        if data is None:
            data = {}
        if not isinstance(data, Mapping):
            raise TypeError("transmitted data must be a mapping")

        action = normalize_action(
            get_first(packet_dict, ACTION_KEYS)
            or get_first(data, ACTION_KEYS)
            or state
        )
        if action is None:
            raise ValueError("packet has no supported action")

        if action == "generate":
            if coordinate is None:
                coordinate = get_first(data, COORDINATE_KEYS)
            if coordinate is None:
                raise ValueError("generate action requires an impact coordinate")
            return self.generate_block(
                coordinate,
                state=data.get("block_state", data.get("state")),
                data=data.get("block_data", data.get("data", {})),
                replace=bool(data.get("replace", False)),
            )

        if coordinate is None and action not in {"connect_group", "disconnect_group", "move_group_data"}:
            raise ValueError(f"{action} action requires an impact coordinate")

        if action == "destroy":
            return self.destroy_block(coordinate)

        if action == "save":
            return self.save_block(
                coordinate,
                strip_control_keys(data),
                merge=bool(data.get("merge", True)),
            )

        if action == "erase":
            keys = data.get("keys")
            return self.erase_block(coordinate, keys=keys)

        if action == "transfer":
            target = get_first(data, TARGET_KEYS)
            payload = data.get("value", data.get("data", strip_control_keys(data)))
            return self.transfer_data(coordinate, target=target, data=payload)

        if action == "lock_transfer":
            return self.lock_transfer(coordinate, True)

        if action == "unlock_transfer":
            return self.lock_transfer(coordinate, False)

        if action == "select_group":
            group_id = require_string(data.get("group_id") or data.get("group") or data.get("группа"), "group_id")
            coordinates = data.get("coordinates") or data.get("координаты") or [coordinate]
            color = data.get("color") or data.get("цвет")
            group_state = data.get("group_state") or data.get("state") or data.get("состояние")
            return self.select_group(group_id, coordinates, color=color, state=group_state)

        if action == "connect":
            target = get_first(data, TARGET_KEYS)
            if target is None:
                raise ValueError("connect action requires a target coordinate")
            return self.connect(coordinate, target, bidirectional=bool(data.get("bidirectional", True)))

        if action == "disconnect":
            target = get_first(data, TARGET_KEYS)
            if target is None:
                raise ValueError("disconnect action requires a target coordinate")
            return self.disconnect(coordinate, target, bidirectional=bool(data.get("bidirectional", True)))

        if action == "connect_group":
            left = require_string(data.get("left_group") or data.get("from_group") or data.get("source_group"), "left_group")
            right = require_string(data.get("right_group") or data.get("to_group") or data.get("target_group"), "right_group")
            return self.connect_group(left, right, bidirectional=bool(data.get("bidirectional", True)))

        if action == "disconnect_group":
            left = require_string(data.get("left_group") or data.get("from_group") or data.get("source_group"), "left_group")
            right = require_string(data.get("right_group") or data.get("to_group") or data.get("target_group"), "right_group")
            return self.disconnect_group(left, right, bidirectional=bool(data.get("bidirectional", True)))

        if action == "move_group_data":
            source_group = require_string(data.get("source_group") or data.get("from_group"), "source_group")
            target_group = require_string(data.get("target_group") or data.get("to_group"), "target_group")
            payload = data.get("value", data.get("data"))
            return self.move_connected_group_data(
                source_group,
                target_group,
                data=payload,
                clear_source=bool(data.get("clear_source", False)),
            )

        raise ValueError(f"unsupported action {action!r}")

    def click(
        self,
        coordinate: Coordinate | Iterable[int] | Mapping[str, int],
        *,
        button: str = "left",
        payload: Mapping[str, Any] | None = None,
    ) -> Any:
        """Execute a mouse-click operation for a block."""

        normalized = normalize_coordinate(coordinate)
        block = self.require_block(normalized)
        if payload is None:
            click_actions = block.state.get("click_actions", {})
            if not isinstance(click_actions, Mapping) or button not in click_actions:
                raise ValueError(f"block {normalized} has no action for {button!r} click")
            payload = {
                "состояние": click_actions[button],
                "координата воздействия": normalized,
                "передаваемые данные": {},
                "mouse_button": button,
            }
        else:
            payload = {
                **dict(payload),
                "координата воздействия": get_first(payload, COORDINATE_KEYS, normalized),
                "mouse_button": button,
            }
        return self.dispatch(payload)

    def require_block(self, coordinate: Coordinate | Iterable[int] | Mapping[str, int]) -> RedstoneBlock:
        normalized = normalize_coordinate(coordinate)
        if normalized not in self.blocks:
            raise KeyError(f"block does not exist at {normalized}")
        return self.blocks[normalized]

    def require_group(self, group_id: str) -> RedstoneGroup:
        if group_id not in self.groups:
            raise KeyError(f"group {group_id!r} does not exist")
        return self.groups[group_id]

    def snapshot(self) -> NestedData:
        """Return a serializable snapshot of the full world."""

        return {
            "blocks": {
                coordinate_to_key(coordinate): block.snapshot()
                for coordinate, block in sorted(self.blocks.items())
            },
            "groups": {
                group_id: group.snapshot()
                for group_id, group in sorted(self.groups.items())
            },
        }

    def clear(self) -> None:
        """Erase every block and group from the world."""

        self.blocks.clear()
        self.groups.clear()


def normalize_coordinate(coordinate: Coordinate | Iterable[int] | Mapping[str, int]) -> Coordinate:
    if isinstance(coordinate, Mapping):
        try:
            return int(coordinate["x"]), int(coordinate["y"]), int(coordinate["z"])
        except KeyError as error:
            raise ValueError("coordinate mapping must contain x, y, z") from error

    if isinstance(coordinate, str):
        parts = [part.strip() for part in coordinate.split(",")]
        if len(parts) != 3:
            raise ValueError("coordinate string must be formatted as 'x,y,z'")
        return int(parts[0]), int(parts[1]), int(parts[2])

    parts = tuple(coordinate)
    if len(parts) != 3:
        raise ValueError("coordinate must contain exactly x, y, z")
    return int(parts[0]), int(parts[1]), int(parts[2])


def normalize_state(state: Mapping[str, Any] | str | None) -> NestedData:
    if state is None:
        return {}
    if isinstance(state, str):
        return {"value": state}
    if not isinstance(state, Mapping):
        raise TypeError("state must be a mapping, string, or None")
    return copy.deepcopy(dict(state))


def normalize_action(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    return ACTION_ALIASES.get(value.strip().lower())


def deep_merge(target: NestedData, source: Mapping[str, Any]) -> NestedData:
    """Recursively merge source into target."""

    for key, value in source.items():
        if (
            key in target
            and isinstance(target[key], dict)
            and isinstance(value, Mapping)
        ):
            deep_merge(target[key], value)
        else:
            target[key] = copy.deepcopy(value)
    return target


def get_first(mapping: Mapping[str, Any], keys: Iterable[str], default: Any = None) -> Any:
    for key in keys:
        if key in mapping:
            return mapping[key]
    return default


def strip_control_keys(data: Mapping[str, Any]) -> NestedData:
    """Remove command metadata so only payload data is saved/transferred."""

    control_keys = set(ACTION_KEYS + TARGET_KEYS + COORDINATE_KEYS + DATA_KEYS)
    control_keys.update(
        {
            "block_state",
            "block_data",
            "replace",
            "merge",
            "keys",
            "coordinates",
            "координаты",
            "group",
            "group_id",
            "группа",
            "color",
            "цвет",
            "group_state",
            "left_group",
            "right_group",
            "from_group",
            "to_group",
            "source_group",
            "target_group",
            "clear_source",
            "bidirectional",
            "value",
        }
    )
    return {key: copy.deepcopy(value) for key, value in data.items() if key not in control_keys}


def coordinate_to_key(coordinate: Coordinate) -> str:
    return f"{coordinate[0]},{coordinate[1]},{coordinate[2]}"


def require_string(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{name} must be a non-empty string")
    return value
