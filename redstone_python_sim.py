#!/usr/bin/env python3
"""
Мини-движок "редстоуна" на Python:
- генерация/уничтожение блоков;
- сохранение/стирание данных;
- передача данных и блокировка передачи;
- выделение и состояние (цвет) групп блоков;
- соединение/разъединение блоков и групп;
- перемещение данных по соединенным группам;
- запуск функций через внутренние данные блока и через клики мыши.
"""

from __future__ import annotations

import copy
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

try:
    import tkinter as tk
    from tkinter import messagebox
except ModuleNotFoundError:  # GUI часть опциональна для headless-среды
    tk = None  # type: ignore[assignment]
    messagebox = None  # type: ignore[assignment]


STATE_KEYS = ("состояние", "состояни", "state")
COORD_KEYS = (
    "координата воздействия",
    "координата_воздействия",
    "impact_coordinate",
    "coordinate",
)
PAYLOAD_KEYS = (
    "передаваемые данные",
    "передаваемые_данные",
    "payload",
    "data",
)

STATE_TO_COLOR = {
    "generated": "#808080",
    "saved": "#4f83ff",
    "erased": "#1c1c1c",
    "active": "#e53935",
    "idle": "#8d99ae",
    "locked": "#ff9800",
    "group_red": "#f44336",
    "group_green": "#4caf50",
    "group_blue": "#2196f3",
    "group_yellow": "#fbc02d",
}


class PacketFormatError(ValueError):
    """Ошибка формата пакета передачи/команды."""


def deep_merge_dict(base: dict[str, Any], incoming: dict[str, Any]) -> dict[str, Any]:
    result = copy.deepcopy(base)
    for key, value in incoming.items():
        if (
            key in result
            and isinstance(result[key], dict)
            and isinstance(value, dict)
        ):
            result[key] = deep_merge_dict(result[key], value)
        else:
            result[key] = copy.deepcopy(value)
    return result


def _extract_first(details: dict[str, Any], keys: tuple[str, ...], default: Any) -> Any:
    for key in keys:
        if key in details:
            return details[key]
    return default


def _normalize_coord(raw: Any) -> tuple[int, int, int]:
    if isinstance(raw, (tuple, list)) and len(raw) == 3:
        return int(raw[0]), int(raw[1]), int(raw[2])
    if isinstance(raw, str):
        parts = [item.strip() for item in raw.split(",")]
        if len(parts) == 3:
            return int(parts[0]), int(parts[1]), int(parts[2])
    raise PacketFormatError(
        "Координата воздействия должна быть в формате x,y,z или [x, y, z]."
    )


@dataclass
class TransferPacket:
    operation: str
    state: str
    impact_coordinate: tuple[int, int, int]
    payload: dict[str, Any]

    @classmethod
    def from_mapping(cls, mapping: dict[str, Any]) -> "TransferPacket":
        if not isinstance(mapping, dict) or len(mapping) != 1:
            raise PacketFormatError("Пакет должен быть в формате: ключ: { ... }")
        operation, details = next(iter(mapping.items()))
        if not isinstance(details, dict):
            raise PacketFormatError("Значение ключа пакета должно быть словарем.")

        state = str(_extract_first(details, STATE_KEYS, "idle"))
        coord_raw = _extract_first(details, COORD_KEYS, (0, 0, 0))
        payload = _extract_first(details, PAYLOAD_KEYS, {})
        if not isinstance(payload, dict):
            raise PacketFormatError("Поле передаваемых данных должно быть словарем.")

        return cls(
            operation=str(operation),
            state=state,
            impact_coordinate=_normalize_coord(coord_raw),
            payload=payload,
        )

    def to_mapping(self) -> dict[str, Any]:
        return {
            self.operation: {
                "состояние": self.state,
                "координата воздействия": list(self.impact_coordinate),
                "передаваемые данные": copy.deepcopy(self.payload),
            }
        }


@dataclass
class Block:
    block_id: int
    coordinate: tuple[int, int, int]
    data: dict[str, Any] = field(default_factory=dict)
    generated: bool = True
    transfer_locked: bool = False
    connections: set[int] = field(default_factory=set)
    saved_snapshot: dict[str, Any] | None = None
    color: str = STATE_TO_COLOR["generated"]

    def set_state(self, state: str) -> None:
        self.data["state"] = state
        if state in STATE_TO_COLOR:
            self.color = STATE_TO_COLOR[state]

    def generate(self, initial_data: dict[str, Any] | None = None, state: str = "generated") -> None:
        self.generated = True
        if initial_data:
            self.data = deep_merge_dict(self.data, initial_data)
        self.set_state(state)

    def destroy(self) -> None:
        self.generated = False
        self.connections.clear()
        self.data.clear()
        self.saved_snapshot = None
        self.color = "#2b2b2b"

    def save(self) -> None:
        self.saved_snapshot = copy.deepcopy(self.data)
        self.set_state("saved")

    def erase(self) -> None:
        self.data.clear()
        self.set_state("erased")

    def lock_transfer(self) -> None:
        self.transfer_locked = True
        self.set_state("locked")

    def unlock_transfer(self) -> None:
        self.transfer_locked = False
        if self.data.get("state") == "locked":
            self.set_state("idle")

    def connect(self, other_block_id: int) -> None:
        self.connections.add(other_block_id)

    def disconnect(self, other_block_id: int) -> None:
        self.connections.discard(other_block_id)

    def receive(self, packet: TransferPacket) -> None:
        self.data["last_operation"] = packet.operation
        self.data["last_impact_coordinate"] = list(packet.impact_coordinate)
        existing_payload = self.data.get("payload", {})
        if not isinstance(existing_payload, dict):
            existing_payload = {}
        self.data["payload"] = deep_merge_dict(existing_payload, packet.payload)
        self.set_state(packet.state)
        history = self.data.setdefault("history", [])
        history.append(packet.to_mapping())

    def queue_internal_command(self, command_packet: dict[str, Any]) -> None:
        queue = self.data.setdefault("internal_commands", [])
        queue.append(copy.deepcopy(command_packet))

    def pop_internal_commands(self) -> list[dict[str, Any]]:
        queue = self.data.get("internal_commands", [])
        self.data["internal_commands"] = []
        return queue if isinstance(queue, list) else []

    def serialize(self) -> dict[str, Any]:
        return {
            "block_id": self.block_id,
            "coordinate": list(self.coordinate),
            "generated": self.generated,
            "transfer_locked": self.transfer_locked,
            "connections": sorted(self.connections),
            "data": copy.deepcopy(self.data),
            "saved_snapshot": copy.deepcopy(self.saved_snapshot),
            "color": self.color,
        }


class RedstoneEngine:
    def __init__(self) -> None:
        self.blocks: dict[int, Block] = {}
        self.coord_to_id: dict[tuple[int, int, int], int] = {}
        self.groups: dict[int, set[int]] = {}
        self.group_state: dict[int, str] = {}
        self.next_block_id = 1
        self.next_group_id = 1

    def get_block_by_coord(self, coord: tuple[int, int, int]) -> Block | None:
        block_id = self.coord_to_id.get(coord)
        return self.blocks.get(block_id) if block_id else None

    def generate_block(self, coord: tuple[int, int, int], initial_data: dict[str, Any] | None = None) -> Block:
        existing = self.get_block_by_coord(coord)
        if existing:
            existing.generate(initial_data=initial_data)
            return existing

        block = Block(block_id=self.next_block_id, coordinate=coord)
        if initial_data:
            block.data = deep_merge_dict(block.data, initial_data)
        self.blocks[block.block_id] = block
        self.coord_to_id[coord] = block.block_id
        self.next_block_id += 1
        return block

    def destroy_block(self, block_id: int) -> bool:
        block = self.blocks.get(block_id)
        if not block:
            return False
        for neighbor_id in list(block.connections):
            neighbor = self.blocks.get(neighbor_id)
            if neighbor:
                neighbor.disconnect(block_id)
        for group_id, member_ids in self.groups.items():
            member_ids.discard(block_id)
        self.coord_to_id.pop(block.coordinate, None)
        block.destroy()
        del self.blocks[block_id]
        return True

    def save_block(self, block_id: int) -> bool:
        block = self.blocks.get(block_id)
        if not block:
            return False
        block.save()
        return True

    def erase_block(self, block_id: int) -> bool:
        block = self.blocks.get(block_id)
        if not block:
            return False
        block.erase()
        return True

    def connect_blocks(self, first_id: int, second_id: int) -> bool:
        if first_id == second_id:
            return False
        first = self.blocks.get(first_id)
        second = self.blocks.get(second_id)
        if not first or not second:
            return False
        first.connect(second_id)
        second.connect(first_id)
        return True

    def disconnect_blocks(self, first_id: int, second_id: int) -> bool:
        first = self.blocks.get(first_id)
        second = self.blocks.get(second_id)
        if not first or not second:
            return False
        first.disconnect(second_id)
        second.disconnect(first_id)
        return True

    def create_group(self, block_ids: list[int], state: str = "group_green") -> int:
        valid_ids = {block_id for block_id in block_ids if block_id in self.blocks}
        if not valid_ids:
            raise ValueError("Нельзя создать группу без существующих блоков.")
        group_id = self.next_group_id
        self.next_group_id += 1
        self.groups[group_id] = valid_ids
        self.group_state[group_id] = state
        self.set_group_state(group_id, state)
        return group_id

    def set_group_state(self, group_id: int, state: str) -> None:
        if group_id not in self.groups:
            raise ValueError(f"Группа {group_id} не существует.")
        self.group_state[group_id] = state
        color = STATE_TO_COLOR.get(state, "#9c27b0")
        for block_id in self.groups[group_id]:
            block = self.blocks.get(block_id)
            if block:
                block.data["group_state"] = state
                block.color = color

    def connect_groups(self, first_group_id: int, second_group_id: int) -> int:
        first_members = self.groups.get(first_group_id, set())
        second_members = self.groups.get(second_group_id, set())
        connection_count = 0
        for first_id in first_members:
            for second_id in second_members:
                if self.connect_blocks(first_id, second_id):
                    connection_count += 1
        return connection_count

    def disconnect_groups(self, first_group_id: int, second_group_id: int) -> int:
        first_members = self.groups.get(first_group_id, set())
        second_members = self.groups.get(second_group_id, set())
        disconnection_count = 0
        for first_id in first_members:
            for second_id in second_members:
                if self.disconnect_blocks(first_id, second_id):
                    disconnection_count += 1
        return disconnection_count

    def transfer_data(self, source_block_id: int, packet_mapping: dict[str, Any]) -> set[int]:
        packet = TransferPacket.from_mapping(packet_mapping)
        source = self.blocks.get(source_block_id)
        if not source:
            return set()
        if source.transfer_locked:
            return set()

        visited: set[int] = {source_block_id}
        queue: list[int] = [source_block_id]

        while queue:
            current_id = queue.pop(0)
            current_block = self.blocks.get(current_id)
            if not current_block:
                continue
            current_block.receive(packet)
            if current_block.transfer_locked:
                continue
            for neighbor_id in current_block.connections:
                if neighbor_id not in visited and neighbor_id in self.blocks:
                    visited.add(neighbor_id)
                    queue.append(neighbor_id)
        return visited

    def move_data_in_connected_groups(self, source_group_id: int, packet_mapping: dict[str, Any]) -> set[int]:
        members = self.groups.get(source_group_id, set())
        reached: set[int] = set()
        for block_id in members:
            reached |= self.transfer_data(block_id, packet_mapping)
        return reached

    def dispatch_command_packet(self, block_id: int, packet_mapping: dict[str, Any]) -> str:
        packet = TransferPacket.from_mapping(packet_mapping)
        payload = packet.payload

        if packet.operation == "generate":
            target_coord = packet.impact_coordinate
            self.generate_block(target_coord, initial_data=payload)
            return f"generate: блок создан/обновлен в {target_coord}"

        if packet.operation == "destroy":
            target_id = int(payload.get("target_block_id", block_id))
            ok = self.destroy_block(target_id)
            return f"destroy: {'ok' if ok else 'block_not_found'} ({target_id})"

        if packet.operation == "save":
            target_id = int(payload.get("target_block_id", block_id))
            ok = self.save_block(target_id)
            return f"save: {'ok' if ok else 'block_not_found'} ({target_id})"

        if packet.operation == "erase":
            target_id = int(payload.get("target_block_id", block_id))
            ok = self.erase_block(target_id)
            return f"erase: {'ok' if ok else 'block_not_found'} ({target_id})"

        if packet.operation == "lock_transfer":
            target_id = int(payload.get("target_block_id", block_id))
            block = self.blocks.get(target_id)
            if not block:
                return f"lock_transfer: block_not_found ({target_id})"
            block.lock_transfer()
            return f"lock_transfer: ok ({target_id})"

        if packet.operation == "unlock_transfer":
            target_id = int(payload.get("target_block_id", block_id))
            block = self.blocks.get(target_id)
            if not block:
                return f"unlock_transfer: block_not_found ({target_id})"
            block.unlock_transfer()
            return f"unlock_transfer: ok ({target_id})"

        if packet.operation == "transfer":
            reached = self.transfer_data(block_id, packet.to_mapping())
            return f"transfer: reached={sorted(reached)}"

        if packet.operation == "connect":
            target_id = int(payload["target_block_id"])
            ok = self.connect_blocks(block_id, target_id)
            return f"connect: {'ok' if ok else 'failed'} ({block_id}<->{target_id})"

        if packet.operation == "disconnect":
            target_id = int(payload["target_block_id"])
            ok = self.disconnect_blocks(block_id, target_id)
            return f"disconnect: {'ok' if ok else 'failed'} ({block_id}<->{target_id})"

        if packet.operation == "create_group":
            block_ids = payload.get("block_ids", [block_id])
            state = str(payload.get("state", "group_green"))
            group_id = self.create_group([int(item) for item in block_ids], state=state)
            return f"create_group: group_id={group_id}"

        if packet.operation == "set_group_state":
            group_id = int(payload["group_id"])
            state = str(payload.get("state", "group_blue"))
            self.set_group_state(group_id, state=state)
            return f"set_group_state: group_id={group_id}, state={state}"

        if packet.operation == "move_group_data":
            group_id = int(payload["group_id"])
            reached = self.move_data_in_connected_groups(group_id, packet.to_mapping())
            return f"move_group_data: reached={sorted(reached)}"

        raise PacketFormatError(f"Неизвестная операция: {packet.operation}")

    def process_internal_commands(self, block_id: int) -> list[str]:
        block = self.blocks.get(block_id)
        if not block:
            return [f"Блок {block_id} не найден."]
        results = []
        for command_packet in block.pop_internal_commands():
            try:
                result = self.dispatch_command_packet(block_id, command_packet)
            except Exception as exc:  # noqa: BLE001
                result = f"Ошибка команды {command_packet}: {exc}"
            results.append(result)
        return results

    def save_to_file(self, path: Path) -> None:
        payload = {
            "next_block_id": self.next_block_id,
            "next_group_id": self.next_group_id,
            "blocks": [block.serialize() for block in self.blocks.values()],
            "groups": {str(group_id): sorted(block_ids) for group_id, block_ids in self.groups.items()},
            "group_state": {str(group_id): state for group_id, state in self.group_state.items()},
        }
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    def load_from_file(self, path: Path) -> None:
        payload = json.loads(path.read_text(encoding="utf-8"))
        self.blocks.clear()
        self.coord_to_id.clear()
        self.groups.clear()
        self.group_state.clear()

        self.next_block_id = int(payload.get("next_block_id", 1))
        self.next_group_id = int(payload.get("next_group_id", 1))

        for item in payload.get("blocks", []):
            block = Block(
                block_id=int(item["block_id"]),
                coordinate=tuple(item["coordinate"]),
                data=item.get("data", {}),
                generated=bool(item.get("generated", True)),
                transfer_locked=bool(item.get("transfer_locked", False)),
                connections=set(item.get("connections", [])),
                saved_snapshot=item.get("saved_snapshot"),
                color=item.get("color", STATE_TO_COLOR["generated"]),
            )
            self.blocks[block.block_id] = block
            self.coord_to_id[block.coordinate] = block.block_id

        self.groups = {int(group_id): set(ids) for group_id, ids in payload.get("groups", {}).items()}
        self.group_state = {int(group_id): state for group_id, state in payload.get("group_state", {}).items()}


class RedstoneUI:
    GRID_W = 12
    GRID_H = 10
    CELL = 48

    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("Redstone Python Simulator")
        self.engine = RedstoneEngine()
        self.selected_ids: set[int] = set()
        self.last_clicked_coord: tuple[int, int, int] | None = None

        self.canvas = tk.Canvas(
            root,
            width=self.GRID_W * self.CELL,
            height=self.GRID_H * self.CELL,
            bg="#202124",
            highlightthickness=0,
        )
        self.canvas.grid(row=0, column=0, rowspan=20, sticky="nsew")
        self.canvas.bind("<Button-1>", self.on_left_click)
        self.canvas.bind("<Button-3>", self.on_right_click)
        self.canvas.bind("<Double-Button-1>", self.on_double_left_click)

        panel = tk.Frame(root, padx=8, pady=8)
        panel.grid(row=0, column=1, sticky="n")

        self.log = tk.Text(panel, width=58, height=18)
        self.log.grid(row=0, column=0, columnspan=2, pady=(0, 8))
        self.log.insert(
            "1.0",
            "Клики мыши:\n"
            "- ЛКМ: создать/выбрать блок\n"
            "- Shift + ЛКМ: мультивыбор\n"
            "- ПКМ: уничтожить блок\n"
            "- Двойной ЛКМ: блокировка/разблокировка передачи\n\n",
        )

        self.packet_input = tk.Text(panel, width=58, height=12)
        self.packet_input.grid(row=1, column=0, columnspan=2, pady=(0, 8))
        self.packet_input.insert(
            "1.0",
            json.dumps(
                {
                    "transfer": {
                        "состояние": "active",
                        "координата воздействия": [0, 0, 0],
                        "передаваемые данные": {
                            "signal": 15,
                            "nested": {"deep": {"value": 1}},
                        },
                    }
                },
                ensure_ascii=False,
                indent=2,
            ),
        )

        buttons = [
            ("Сохранить блок(и)", self.save_selected),
            ("Стереть данные блок(ов)", self.erase_selected),
            ("Соединить 2 выбранных", self.connect_selected_pair),
            ("Разъединить 2 выбранных", self.disconnect_selected_pair),
            ("Создать группу", self.create_group_from_selected),
            ("Передать пакет", self.send_packet_from_selected),
            ("Пакет -> внутр. команда", self.enqueue_command_to_selected),
            ("Выполнить внутр. команды", self.execute_commands_selected),
            ("Передать по группе", self.move_data_by_group),
            ("Сохранить схему в JSON", self.save_scene),
            ("Загрузить схему из JSON", self.load_scene),
            ("Сбросить выбор", self.clear_selection),
        ]

        for index, (title, callback) in enumerate(buttons, start=2):
            tk.Button(panel, text=title, width=27, command=callback).grid(
                row=index,
                column=0 if index % 2 == 0 else 1,
                sticky="ew",
                padx=3,
                pady=2,
            )

        self.group_state_var = tk.StringVar(value="group_green")
        states = ("group_green", "group_red", "group_blue", "group_yellow")
        tk.OptionMenu(panel, self.group_state_var, *states).grid(
            row=14, column=0, sticky="ew", padx=3, pady=4
        )
        tk.Button(panel, text="Применить цвет группы", command=self.paint_group_state).grid(
            row=14, column=1, sticky="ew", padx=3, pady=4
        )

        self.status_var = tk.StringVar(value="Готово.")
        tk.Label(panel, textvariable=self.status_var, anchor="w", justify="left").grid(
            row=15, column=0, columnspan=2, sticky="ew", pady=(8, 0)
        )

        self.draw()

    def append_log(self, text: str) -> None:
        self.log.insert("end", text + "\n")
        self.log.see("end")
        self.status_var.set(text)

    def draw(self) -> None:
        self.canvas.delete("all")
        for x in range(self.GRID_W):
            for y in range(self.GRID_H):
                left = x * self.CELL
                top = y * self.CELL
                right = left + self.CELL
                bottom = top + self.CELL
                self.canvas.create_rectangle(left, top, right, bottom, outline="#3c4043")

        for block in self.engine.blocks.values():
            x, y, _ = block.coordinate
            left = x * self.CELL + 4
            top = y * self.CELL + 4
            right = left + self.CELL - 8
            bottom = top + self.CELL - 8
            width = 3 if block.block_id in self.selected_ids else 1
            outline = "#ffee58" if block.block_id in self.selected_ids else "#111111"
            self.canvas.create_rectangle(
                left,
                top,
                right,
                bottom,
                fill=block.color,
                outline=outline,
                width=width,
            )
            self.canvas.create_text(
                left + 12,
                top + 10,
                text=str(block.block_id),
                fill="#ffffff",
                font=("Arial", 9, "bold"),
            )

    def event_to_coord(self, event: tk.Event) -> tuple[int, int, int]:
        x = int(event.x // self.CELL)
        y = int(event.y // self.CELL)
        x = max(0, min(self.GRID_W - 1, x))
        y = max(0, min(self.GRID_H - 1, y))
        return (x, y, 0)

    def on_left_click(self, event: tk.Event) -> None:
        coord = self.event_to_coord(event)
        self.last_clicked_coord = coord
        block = self.engine.get_block_by_coord(coord)
        append_mode = bool(event.state & 0x0001)  # Shift

        if not block:
            block = self.engine.generate_block(coord)
            self.append_log(f"Создан блок {block.block_id} @ {coord}")

        if append_mode:
            if block.block_id in self.selected_ids:
                self.selected_ids.discard(block.block_id)
            else:
                self.selected_ids.add(block.block_id)
        else:
            self.selected_ids = {block.block_id}
        self.draw()

    def on_right_click(self, event: tk.Event) -> None:
        coord = self.event_to_coord(event)
        block = self.engine.get_block_by_coord(coord)
        if not block:
            return
        self.engine.destroy_block(block.block_id)
        self.selected_ids.discard(block.block_id)
        self.append_log(f"Уничтожен блок {block.block_id} @ {coord}")
        self.draw()

    def on_double_left_click(self, event: tk.Event) -> None:
        coord = self.event_to_coord(event)
        block = self.engine.get_block_by_coord(coord)
        if not block:
            return
        if block.transfer_locked:
            block.unlock_transfer()
            self.append_log(f"Передача РАЗблокирована у блока {block.block_id}")
        else:
            block.lock_transfer()
            self.append_log(f"Передача заблокирована у блока {block.block_id}")
        self.draw()

    def selected_blocks(self) -> list[Block]:
        return [self.engine.blocks[block_id] for block_id in self.selected_ids if block_id in self.engine.blocks]

    def save_selected(self) -> None:
        for block in self.selected_blocks():
            self.engine.save_block(block.block_id)
            self.append_log(f"Сохранен блок {block.block_id}")
        self.draw()

    def erase_selected(self) -> None:
        for block in self.selected_blocks():
            self.engine.erase_block(block.block_id)
            self.append_log(f"Стерты данные блока {block.block_id}")
        self.draw()

    def connect_selected_pair(self) -> None:
        ids = sorted(self.selected_ids)
        if len(ids) != 2:
            self.append_log("Нужно выбрать ровно 2 блока для соединения.")
            return
        if self.engine.connect_blocks(ids[0], ids[1]):
            self.append_log(f"Соединены блоки {ids[0]} и {ids[1]}")
        else:
            self.append_log("Не удалось соединить блоки.")

    def disconnect_selected_pair(self) -> None:
        ids = sorted(self.selected_ids)
        if len(ids) != 2:
            self.append_log("Нужно выбрать ровно 2 блока для разъединения.")
            return
        if self.engine.disconnect_blocks(ids[0], ids[1]):
            self.append_log(f"Разъединены блоки {ids[0]} и {ids[1]}")
        else:
            self.append_log("Не удалось разъединить блоки.")

    def create_group_from_selected(self) -> None:
        if not self.selected_ids:
            self.append_log("Выберите блоки для группы.")
            return
        group_id = self.engine.create_group(
            list(self.selected_ids), state=self.group_state_var.get()
        )
        self.append_log(f"Создана группа {group_id} из блоков {sorted(self.selected_ids)}")
        self.draw()

    def paint_group_state(self) -> None:
        if not self.selected_ids:
            self.append_log("Нужно выбрать хотя бы один блок группы.")
            return
        selected = next(iter(self.selected_ids))
        candidate_groups = [
            group_id
            for group_id, members in self.engine.groups.items()
            if selected in members
        ]
        if not candidate_groups:
            self.append_log("Выбранный блок не входит в группу.")
            return
        group_id = candidate_groups[0]
        self.engine.set_group_state(group_id, self.group_state_var.get())
        self.append_log(f"Группа {group_id} окрашена в состояние {self.group_state_var.get()}")
        self.draw()

    def parse_packet_input(self) -> dict[str, Any]:
        raw = self.packet_input.get("1.0", "end").strip()
        if not raw:
            raise PacketFormatError("Поле пакета пустое.")
        packet_mapping = json.loads(raw)
        TransferPacket.from_mapping(packet_mapping)  # валидация
        return packet_mapping

    def send_packet_from_selected(self) -> None:
        if not self.selected_ids:
            self.append_log("Выберите исходный блок для передачи.")
            return
        try:
            packet_mapping = self.parse_packet_input()
            source_id = next(iter(self.selected_ids))
            reached = self.engine.transfer_data(source_id, packet_mapping)
            self.append_log(f"Передача выполнена. Достигнуты блоки: {sorted(reached)}")
            self.draw()
        except Exception as exc:  # noqa: BLE001
            self.append_log(f"Ошибка передачи: {exc}")

    def enqueue_command_to_selected(self) -> None:
        if not self.selected_ids:
            self.append_log("Выберите блок, куда добавить внутреннюю команду.")
            return
        try:
            packet_mapping = self.parse_packet_input()
            block = self.selected_blocks()[0]
            block.queue_internal_command(packet_mapping)
            self.append_log(f"Команда добавлена внутрь блока {block.block_id}")
        except Exception as exc:  # noqa: BLE001
            self.append_log(f"Ошибка добавления команды: {exc}")

    def execute_commands_selected(self) -> None:
        if not self.selected_ids:
            self.append_log("Выберите блок для выполнения внутренних команд.")
            return
        block = self.selected_blocks()[0]
        results = self.engine.process_internal_commands(block.block_id)
        if not results:
            self.append_log(f"У блока {block.block_id} нет внутренних команд.")
        for line in results:
            self.append_log(line)
        self.draw()

    def move_data_by_group(self) -> None:
        if not self.selected_ids:
            self.append_log("Выберите блок группы-источника.")
            return
        block_id = next(iter(self.selected_ids))
        candidate_groups = [
            group_id
            for group_id, members in self.engine.groups.items()
            if block_id in members
        ]
        if not candidate_groups:
            self.append_log("Выбранный блок не состоит в группе.")
            return
        source_group = candidate_groups[0]
        try:
            packet_mapping = self.parse_packet_input()
            reached = self.engine.move_data_in_connected_groups(source_group, packet_mapping)
            self.append_log(
                f"Перемещение данных по соединенным группам от {source_group}: {sorted(reached)}"
            )
            self.draw()
        except Exception as exc:  # noqa: BLE001
            self.append_log(f"Ошибка передачи группы: {exc}")

    def save_scene(self) -> None:
        path = Path("redstone_state.json")
        self.engine.save_to_file(path)
        self.append_log(f"Сцена сохранена: {path}")

    def load_scene(self) -> None:
        path = Path("redstone_state.json")
        if not path.exists():
            messagebox.showwarning("Нет файла", f"Файл {path} не найден.")
            return
        self.engine.load_from_file(path)
        self.selected_ids.clear()
        self.append_log(f"Сцена загружена: {path}")
        self.draw()

    def clear_selection(self) -> None:
        self.selected_ids.clear()
        self.append_log("Выбор сброшен.")
        self.draw()


def main() -> None:
    if tk is None:
        raise SystemExit(
            "Tkinter не установлен. Для GUI установите python3-tk и запустите снова."
        )
    root = tk.Tk()
    root.geometry("1240x700")
    app = RedstoneUI(root)
    app.append_log("Готово: можно создавать блоки и отправлять пакеты.")
    root.mainloop()


if __name__ == "__main__":
    main()
