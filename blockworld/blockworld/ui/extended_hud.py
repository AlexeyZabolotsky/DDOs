"""HUD: хотбар из репозитория redstone + режимы симуляции пользователя."""

from __future__ import annotations

from ursina import Button, Entity, Text, camera, color, destroy

# Режимы инструментов (слоты хотбара)
TOOL_SLOTS: list[dict[str, str]] = [
    {"label": "Выделение", "mode": "select"},
    {"label": "Поле/группа", "mode": "field_select"},
    {"label": "Параметры", "mode": "params"},
    {"label": "Connect", "mode": "connect"},
    {"label": "Conduct", "mode": "conduct"},
    {"label": "Generate", "mode": "generate"},
    {"label": "Store", "mode": "store"},
    {"label": "Redstone", "mode": "redstone"},
    {"label": "Клетка", "mode": "cell"},
]

SLOT_COLORS = [
    color.azure, color.cyan, color.yellow, color.orange,
    color.lime, color.green, color.violet, color.red, color.magenta,
]


class ExtendedHUD:
    """Хотбар + статус + подсказки (стиль Minecraft из redstone/view3d/hud.py)."""

    def __init__(self) -> None:
        self.selected_slot = 0
        self._slots: list[Button] = []
        self._status = Text(
            text="Blockworld — клик по блоку: выделение | E — параметры | F — поле группы",
            position=(-0.86, 0.46),
            origin=(-0.5, 0.5),
            scale=0.95,
            background=True,
        )
        self._hint = Text(
            text=self._default_hint(),
            position=(0, 0.48),
            origin=(0, 0.5),
            scale=0.75,
            background=True,
        )
        self._field_info = Text(
            text="",
            position=(-0.86, 0.38),
            origin=(-0.5, 0.5),
            scale=0.85,
            color=color.cyan,
            background=True,
        )
        self._crosshair_h = Entity(
            model="quad", scale=(0.02, 0.003), color=color.white, parent=camera.ui, z=-1,
        )
        self._crosshair_v = Entity(
            model="quad", scale=(0.003, 0.02), color=color.white, parent=camera.ui, z=-1,
        )
        self._build_hotbar()

    def _default_hint(self) -> str:
        return (
            "1-9 слот | U UI | E параметры | F поле-группа | G generate | "
            "Shift+ЛКМ redstone | Scroll поле R | Esc"
        )

    def _build_hotbar(self) -> None:
        slot_w = 0.085
        start_x = -((len(TOOL_SLOTS) - 1) * slot_w) / 2
        for index, slot in enumerate(TOOL_SLOTS):
            x = start_x + index * slot_w
            btn = Button(
                parent=camera.ui,
                model="quad",
                color=SLOT_COLORS[index % len(SLOT_COLORS)],
                scale=(0.078, 0.078),
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

    def select_slot(self, index: int) -> dict[str, str]:
        self.selected_slot = max(0, min(len(TOOL_SLOTS) - 1, index))
        self._update_selection()
        slot = TOOL_SLOTS[self.selected_slot]
        self.set_status(f"Слот {self.selected_slot + 1}: {slot['label']}")
        return slot

    def current_slot(self) -> dict[str, str]:
        return TOOL_SLOTS[self.selected_slot]

    def current_mode(self) -> str:
        return TOOL_SLOTS[self.selected_slot]["mode"]

    def set_status(self, text: str) -> None:
        self._status.text = text

    def set_field_info(self, text: str) -> None:
        self._field_info.text = text

    def destroy(self) -> None:
        destroy(self._status)
        destroy(self._hint)
        destroy(self._field_info)
        destroy(self._crosshair_h)
        destroy(self._crosshair_v)
        for slot in self._slots:
            destroy(slot)
