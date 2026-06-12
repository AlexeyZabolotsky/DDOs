"""Простой выпадающий список для Ursina (Button + список опций)."""

from __future__ import annotations

from ursina import Button, Entity, Text, color, destroy


class SimpleDropdown(Entity):
    """Клик по кнопке раскрывает список; выбор закрывает меню."""

    def __init__(self, parent=None, options=None, position=(0, 0), scale=(0.22, 0.04), **kwargs):
        super().__init__(parent=parent, position=position, **kwargs)
        self.options = list(options or [])
        self._index = 0
        self._open = False
        self._menu_items: list[Button] = []

        self.main_btn = Button(
            parent=self,
            text=self.options[0] if self.options else "",
            scale=scale,
            position=(0, 0),
            color=color.dark_gray,
            on_click=self._toggle,
        )
        self.text = self.options[0] if self.options else ""
        self.on_select = None

    @property
    def text(self) -> str:
        return self.options[self._index] if self.options else ""

    @text.setter
    def text(self, value: str) -> None:
        if value in self.options:
            self._index = self.options.index(value)
            self.main_btn.text = value

    def _toggle(self) -> None:
        if self._open:
            self._close_menu()
        else:
            self._open_menu()

    def _open_menu(self) -> None:
        self._close_menu()
        self._open = True
        item_h = 0.035
        for i, opt in enumerate(self.options):
            y = -(i + 1) * item_h
            btn = Button(
                parent=self,
                text=opt,
                scale=(self.main_btn.scale_x, item_h),
                position=(0, y),
                color=color.rgb(50, 50, 60),
                z=-0.1,
            )
            btn.option_value = opt
            btn.on_click = self._make_select(opt)
            self._menu_items.append(btn)

    def _make_select(self, opt):
        def _select():
            self._index = self.options.index(opt)
            self.main_btn.text = opt
            self._close_menu()
            if self.on_select:
                self.on_select(opt)
        return _select

    def _close_menu(self) -> None:
        self._open = False
        for item in self._menu_items:
            destroy(item)
        self._menu_items.clear()
