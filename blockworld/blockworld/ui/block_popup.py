"""Всплывающее окно параметров блока — выпадающие списки и поля ввода по клику мыши."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Callable

from ursina import Button, Entity, InputField, Text, camera, color, destroy, mouse

from blockworld.ui.simple_dropdown import SimpleDropdown

if TYPE_CHECKING:
    from blockworld.systems.block_manager import BlockManager


STATE_OPTIONS = ["(нет)", "connect", "conduct", "generate", "store"]
DIRECTION_OPTIONS = ["up", "down", "north", "south", "east", "west", "all"]
REDSTONE_TYPES = [
    "lever", "wire", "lamp", "torch", "repeater", "comparator",
    "button", "pressure_plate", "and_gate", "or_gate", "not_gate",
]
CELL_TYPES = ["stem", "worker", "defender", "sensor", "memory", "energy"]
NEURON_TYPES = ["(нет)", "input", "hidden", "output"]


class BlockParameterPopup(Entity):
    """Панель параметров блока в позиции курсора (screen space)."""

    PANEL_SCALE = (0.42, 0.52)

    def __init__(
        self,
        block_manager: "BlockManager",
        on_apply: Callable[[Any, dict[str, Any]], None] | None = None,
    ):
        super().__init__(parent=camera.ui, enabled=False, eternal=True)
        self.block_manager = block_manager
        self.on_apply = on_apply
        self.target_block = None
        self._widgets: list = []

        self.bg = Entity(
            parent=self,
            model="quad",
            color=color.rgba(30, 30, 35, 230),
            scale=self.PANEL_SCALE,
            z=-0.5,
        )
        self.title = Text(
            parent=self,
            text="Параметры блока",
            scale=1.4,
            origin=(0, 0),
            y=0.22,
            color=color.white,
        )

        self._row_y = 0.14
        self._row_step = 0.075

        self._add_label("Режим / состояние:")
        self.state_dd = self._add_dropdown(STATE_OPTIONS, self._on_state_change)

        self._add_label("Направление:")
        self.direction_dd = self._add_dropdown(DIRECTION_OPTIONS, None)

        self._add_label("Значение / данные:")
        self.value_input = InputField(
            parent=self,
            scale=(0.34, 0.045),
            position=(0, self._next_row()),
        )

        self._add_label("Redstone тип:")
        self.redstone_dd = self._add_dropdown(REDSTONE_TYPES, None)

        self._add_label("Сила (0-15):")
        self.power_input = InputField(
            parent=self,
            scale=(0.12, 0.045),
            position=(-0.1, self._next_row()),
            default_value="0",
        )

        self._add_label("Тип клетки:")
        self.cell_dd = self._add_dropdown(CELL_TYPES, None)

        self._add_label("Нейрон:")
        self.neuron_dd = self._add_dropdown(NEURON_TYPES, None)

        self._add_label("Активен (0/1):")
        self.active_input = InputField(
            parent=self,
            scale=(0.08, 0.045),
            position=(-0.14, self._next_row()),
            default_value="0",
        )

        apply_y = self._next_row() - 0.02
        Button(
            parent=self,
            text="Применить",
            scale=(0.16, 0.05),
            position=(-0.1, apply_y),
            color=color.green.tint(-0.2),
            on_click=self.apply,
        )
        Button(
            parent=self,
            text="Закрыть",
            scale=(0.14, 0.05),
            position=(0.12, apply_y),
            color=color.red.tint(-0.3),
            on_click=self.close,
        )

        self.enabled = False

    def _add_label(self, text: str) -> None:
        t = Text(
            parent=self,
            text=text,
            scale=0.9,
            origin=(-0.5, 0),
            x=-0.19,
            y=self._row_y,
            color=color.light_gray,
        )
        self._widgets.append(t)
        self._row_y -= 0.028

    def _next_row(self) -> float:
        y = self._row_y
        self._row_y -= self._row_step
        return y

    def _add_dropdown(self, options: list[str], on_select) -> SimpleDropdown:
        y = self._next_row()
        dd = SimpleDropdown(
            parent=self,
            options=options,
            position=(0.08, y),
            scale=(0.22, 0.04),
        )
        if on_select:
            dd.on_select = on_select
        self._widgets.append(dd)
        return dd

    def _on_state_change(self, value: str) -> None:
        pass

    def show_for_block(self, block) -> None:
        self.target_block = block
        pos = block.position if hasattr(block, "position") else (0, 0, 0)
        self.title.text = f"Блок {pos}"

        current_state = "(нет)"
        for key in ("connect", "conduct", "generate", "store"):
            if block.states.get(key, {}).get("active"):
                current_state = key
                break
        if current_state in STATE_OPTIONS:
            self.state_dd.text = current_state

        direction = "up"
        for key in ("generate", "conduct"):
            st = block.states.get(key, {})
            if st.get("active") and "direction" in st:
                direction = st["direction"]
                break
        if direction in DIRECTION_OPTIONS:
            self.direction_dd.text = direction

        if hasattr(block, "block_data") and block.block_data:
            self.value_input.text = str(block.block_data.get("value", ""))
        else:
            self.value_input.text = ""

        if hasattr(block, "redstone") and block.redstone:
            rt = block.redstone.get("type", "wire")
            self.redstone_dd.text = rt if rt in REDSTONE_TYPES else "wire"
            self.power_input.text = str(int(block.redstone.get("power", 0)))
        else:
            self.redstone_dd.text = "wire"
            self.power_input.text = "0"

        if hasattr(block, "cell_data") and block.cell_data:
            ct = block.cell_data.get("type", "stem")
            self.cell_dd.text = ct if ct in CELL_TYPES else "stem"
        else:
            self.cell_dd.text = "stem"

        nt = "(нет)"
        if hasattr(block, "block_data") and block.block_data.get("neuron_type"):
            nt = block.block_data["neuron_type"]
        self.neuron_dd.text = nt if nt in NEURON_TYPES else "(нет)"

        self.active_input.text = str(int(getattr(block, "state", 0)))

        mx, my = mouse.position
        self.position = (
            max(-0.55, min(0.55, mx)),
            max(-0.35, min(0.42, my)),
            -1,
        )
        self.enabled = True
        for child in self.children:
            child.enabled = True

    def close(self) -> None:
        self.enabled = False
        self.target_block = None

    def apply(self) -> None:
        if self.target_block is None:
            return
        params = self.collect_params()
        if self.on_apply:
            self.on_apply(self.target_block, params)
        self.block_manager.update_block_color(self.target_block)
        print(f"Applied params to {self.target_block.position}: {params}")
        self.close()

    def collect_params(self) -> dict[str, Any]:
        state = self.state_dd.text
        if state == "(нет)":
            state = None
        try:
            power = int(self.power_input.text or "0")
        except ValueError:
            power = 0
        power = max(0, min(15, power))
        try:
            active = int(self.active_input.text or "0")
        except ValueError:
            active = 0
        active = 1 if active else 0
        return {
            "state_mode": state,
            "direction": self.direction_dd.text,
            "value": self.value_input.text,
            "redstone_type": self.redstone_dd.text,
            "power": power,
            "cell_type": self.cell_dd.text,
            "neuron_type": self.neuron_dd.text,
            "active": active,
        }

    def destroy_popup(self) -> None:
        self.close()
        destroy(self)
