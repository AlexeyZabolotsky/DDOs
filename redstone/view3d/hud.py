"""HUD в стиле Minecraft: прицел, хотбар, подсказки."""

from __future__ import annotations

from ursina import Button, Entity, Text, camera, color, destroy

from redstone.block import BlockType
from redstone.message import Action


HOTBAR_SLOTS: list[dict[str, str]] = [
    {"label": "Выделение", "action": Action.SELECT_GROUP.value, "тип": BlockType.RELAY.value},
    {"label": "Генератор", "action": Action.GENERATE.value, "тип": BlockType.GENERATOR.value},
    {"label": "Реле", "action": Action.GENERATE.value, "тип": BlockType.RELAY.value},
    {"label": "Хранилище", "action": Action.GENERATE.value, "тип": BlockType.STORAGE.value},
    {"label": "Шлюз", "action": Action.GENERATE.value, "тип": BlockType.GATE.value},
    {"label": "Соединитель", "action": Action.GENERATE.value, "тип": BlockType.CONNECTOR.value},
    {"label": "Соединение", "action": Action.CONNECT.value, "тип": BlockType.CONNECTOR.value},
    {"label": "Передача", "action": Action.TRANSFER.value, "тип": BlockType.RELAY.value},
    {"label": "Перемещение", "action": Action.MOVE_DATA.value, "тип": BlockType.STORAGE.value},
]

SLOT_COLORS = [
    color.yellow, color.red, color.gray, color.brown,
    color.light_gray, color.gold, color.azure, color.orange, color.violet,
]


class MinecraftHUD:
    """Элементы интерфейса поверх 3D-сцены."""

    def __init__(self) -> None:
        self.selected_slot = 0
        self._slots: list[Button] = []
        self._status = Text(
            text="",
            position=(-0.86, 0.46),
            origin=(-0.5, 0.5),
            scale=1.1,
            background=True,
        )
        self._hint = Text(
            text=self._default_hint(),
            position=(0, 0.48),
            origin=(0, 0.5),
            scale=0.9,
            background=True,
        )
        self._crosshair_h = Entity(
            model="quad",
            scale=(0.02, 0.003),
            color=color.white,
            parent=camera.ui,
            z=-1,
        )
        self._crosshair_v = Entity(
            model="quad",
            scale=(0.003, 0.02),
            color=color.white,
            parent=camera.ui,
            z=-1,
        )
        self._build_hotbar()

    def _default_hint(self) -> str:
        return (
            "WASD — движение | Пробел — прыжок | ЛКМ — действие | ПКМ — уничтожить | "
            "1-9 — слот | Shift/Ctrl/Alt — модификаторы | Esc — курсор"
        )

    def _build_hotbar(self) -> None:
        slot_w = 0.08
        start_x = -((len(HOTBAR_SLOTS) - 1) * slot_w) / 2
        for index, slot in enumerate(HOTBAR_SLOTS):
            x = start_x + index * slot_w
            btn = Button(
                parent=camera.ui,
                model="quad",
                color=SLOT_COLORS[index % len(SLOT_COLORS)],
                scale=(0.075, 0.075),
                position=(x, -0.42),
                text=str(index + 1),
                text_origin=(0, 0),
            )
            btn.slot_index = index
            self._slots.append(btn)
        self._update_selection()

    def _update_selection(self) -> None:
        for index, btn in enumerate(self._slots):
            btn.highlight_color = color.white if index == self.selected_slot else color.dark_gray
            btn.color = SLOT_COLORS[index % len(SLOT_COLORS)]

    def select_slot(self, index: int) -> dict[str, str]:
        self.selected_slot = max(0, min(len(HOTBAR_SLOTS) - 1, index))
        self._update_selection()
        return HOTBAR_SLOTS[self.selected_slot]

    def current_slot(self) -> dict[str, str]:
        return HOTBAR_SLOTS[self.selected_slot]

    def set_status(self, text: str) -> None:
        self._status.text = text

    def destroy(self) -> None:
        destroy(self._status)
        destroy(self._hint)
        destroy(self._crosshair_h)
        destroy(self._crosshair_v)
        for slot in self._slots:
            destroy(slot)
