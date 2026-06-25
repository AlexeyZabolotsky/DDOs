"""3D Minecraft-клиент редстоуна: камера от первого лица (Ursina).

Та же логика блоков, что и в ``redstone.ui`` / ``redstone.core.World``:
все действия — сообщения ``{состояние, координата, данные}`` через
``World.dispatch``.
"""

from __future__ import annotations

import json
from typing import Dict, Optional, Tuple

from ursina import (
    AmbientLight,
    Button,
    DirectionalLight,
    Entity,
    Sky,
    Text,
    Ursina,
    Vec3,
    application,
    camera,
    color,
    destroy,
    held_keys,
    mouse,
    raycast,
    scene,
    window,
)
from ursina.prefabs import first_person_controller as _fpc_module
from ursina.prefabs.first_person_controller import FirstPersonController

FirstPersonController.update = _fpc_module.FirstPersonController.__dict__["update"]

from redstone.core import Coord, World, СОСТОЯНИЯ, сообщение
from redstone.ui import ИНСТРУМЕНТЫ, _ПО_КУБУ

REACH = 8.0
СЕТКА = 16

_active: Optional["MinecraftFPApp"] = None


def _hex_to_color(hex_: str):
    try:
        s = hex_.lstrip("#")
        if len(s) == 3:
            s = "".join(c * 2 for c in s)
        r, g, b = (int(s[i : i + 2], 16) for i in (0, 2, 4))
        return color.rgb(r, g, b)
    except (ValueError, IndexError):
        return color.rgb(158, 158, 158)


def _ask_json(title: str, prompt: str) -> Optional[dict]:
    try:
        import tkinter as tk
        from tkinter import simpledialog

        root = tk.Tk()
        root.withdraw()
        answer = simpledialog.askstring(title, prompt, parent=root)
        root.destroy()
    except Exception:
        return {}
    if answer is None:
        return None
    if not answer.strip():
        return {}
    data = json.loads(answer)
    if not isinstance(data, dict):
        raise ValueError("ожидается JSON-объект")
    return data


class MinecraftFPApp:
    """Полноэкранный 3D-мир с управлением от первого лица."""

    def __init__(self) -> None:
        self.world = World()
        self.world.наблюдатели.append(lambda _msg: self.sync_voxels())

        self.instrument = СОСТОЯНИЯ["ГЕНЕРАЦИЯ"]
        self.block_color = "#8d6e63"
        self.select_color = "#ffd54f"

        self._voxels: Dict[Coord, Entity] = {}
        self._first_point: Optional[Coord] = None
        self._drag_start: Optional[Coord] = None
        self._player: Optional[Entity] = None
        self._hud: Optional[Text] = None
        self._status: Optional[Text] = None
        self._hotbar: list[Text] = []

    def run(self) -> None:
        global _active
        _active = self

        application.quit_keys = ("escape",)
        app = Ursina(
            title="Редстоун 3D — от первого лица",
            borderless=False,
            fullscreen=False,
            development_mode=False,
        )
        window.color = color.rgb(135, 206, 235)
        window.fps_counter.enabled = True
        window.exit_button.visible = False

        Sky(color=color.rgb(120, 180, 255))
        DirectionalLight(direction=Vec3(1, -1, 0.5), shadows=False)
        AmbientLight(color=color.rgba(180, 180, 180, 0.45))

        self._build_terrain()
        self._spawn_player()
        self._build_hud()
        self._seed_demo()
        self.sync_voxels()

        mouse.locked = True
        self.set_status("WASD — движение · 1-9 — инструменты · ЛКМ — действие · ПКМ — снести")
        app.run()

    def _build_terrain(self) -> None:
        for x in range(СЕТКА):
            for z in range(СЕТКА):
                ground = Button(
                    parent=scene,
                    model="cube",
                    position=(x + 0.5, -0.5, z + 0.5),
                    scale=1,
                    color=color.rgb(60, 120, 60),
                    texture="white_cube",
                    collider="box",
                )
                ground.name = "terrain"
                ground.block_coord = None  # type: ignore[attr-defined]

    def _spawn_player(self) -> None:
        self._player = FirstPersonController(
            position=(СЕТКА / 2, 2, СЕТКА / 2),
            speed=6,
            jump_height=2,
        )
        camera.fov = 80

    def _build_hud(self) -> None:
        self._hud = Text(
            text="",
            position=(-0.85, 0.45),
            scale=1.2,
            origin=(-0.5, 0.5),
            background=True,
        )
        self._status = Text(
            text="",
            position=(0, -0.47),
            origin=(0, 0),
            scale=1.1,
            background=True,
        )
        y = -0.42
        for i, (label, state) in enumerate(ИНСТРУМЕНТЫ[:9]):
            t = Text(
                text=f"{i + 1}:{label[:4]}",
                position=(-0.75 + i * 0.19, y),
                scale=1.0,
                origin=(-0.5, 0),
                background=True,
            )
            self._hotbar.append(t)
        self._refresh_hud()

    def _seed_demo(self) -> None:
        for x in range(3):
            self.dispatch(сообщение(СОСТОЯНИЯ["ГЕНЕРАЦИЯ"], (x + 4, 0, 4), {"цвет": "#795548"}))
        self.dispatch(сообщение(СОСТОЯНИЯ["СОЕДИНЕНИЕ"], (4, 0, 4), {"с": [5, 0, 4]}))
        self.dispatch(сообщение(СОСТОЯНИЯ["СОЕДИНЕНИЕ"], (5, 0, 4), {"с": [6, 0, 4]}))

    def set_status(self, text: str) -> None:
        if self._status:
            self._status.text = text[:120]

    def select_instrument(self, state: str) -> None:
        self.instrument = state
        self._first_point = None
        self._refresh_hud()
        self.set_status(f"Инструмент: {state}")

    def _refresh_hud(self) -> None:
        if self._hud:
            self._hud.text = (
                f"Блоков: {len(self.world.блоки)}  |  "
                f"Журнал: {len(self.world.журнал)}  |  "
                f"Цвет блока: {self.block_color}"
            )
        for i, (_, state) in enumerate(ИНСТРУМЕНТЫ[:9]):
            if i < len(self._hotbar):
                active = state == self.instrument
                self._hotbar[i].color = color.yellow if active else color.white

    def dispatch(self, msg: dict) -> None:
        try:
            self.world.dispatch(msg)
            self.set_status(f"→ {json.dumps(msg, ensure_ascii=False, default=list)}")
            self._refresh_hud()
        except (KeyError, ValueError) as exc:
            self.set_status(f"Ошибка: {exc}")

    def _hit(self):
        ignore = [self._player] if self._player else []
        return raycast(camera.world_position, camera.forward, distance=REACH, ignore=ignore)

    def _coord_from_entity(self, ent) -> Optional[Coord]:
        if ent is None or not hasattr(ent, "block_coord"):
            return None
        c = getattr(ent, "block_coord", None)
        return tuple(c) if c is not None else None

    def _placement_coord(self, hit) -> Optional[Coord]:
        if hit.hit and hasattr(hit.entity, "block_coord"):
            c = hit.entity.block_coord
            if c is not None:
                n = hit.normal
                return (
                    int(round(c[0] + n.x)),
                    int(round(c[1] + n.y)),
                    int(round(c[2] + n.z)),
                )
        if hit.hit:
            p = hit.entity.position + hit.normal
            return (int(round(p.x - 0.5)), int(round(p.y - 0.5)), int(round(p.z - 0.5)))
        target = camera.world_position + camera.forward * 4
        return (int(round(target.x)), max(0, int(round(target.y))), int(round(target.z)))

    def _target_coord(self, hit) -> Optional[Coord]:
        c = self._coord_from_entity(hit.entity if hit.hit else None)
        if c is not None:
            return c
        if hit.hit:
            p = hit.entity.position
            return (int(round(p.x - 0.5)), int(round(p.y - 0.5)), int(round(p.z - 0.5)))
        return None

    def apply_instrument_lmb(self, hit) -> None:
        s = self.instrument
        cube = self._target_coord(hit)
        cell = self._placement_coord(hit)

        if s == СОСТОЯНИЯ["ГЕНЕРАЦИЯ"]:
            target = (cube[0], cube[1] + 1, cube[2]) if cube and cube in self.world.блоки else cell
            if target:
                self.dispatch(сообщение(s, target, {"цвет": self.block_color}))
            return

        target = cube if (s in _ПО_КУБУ and cube) else cell
        if target is None:
            return

        if s == СОСТОЯНИЯ["УНИЧТОЖЕНИЕ"]:
            self.dispatch(сообщение(s, cube or target))
        elif s in (СОСТОЯНИЯ["БЛОКИРОВКА"], СОСТОЯНИЯ["РАЗБЛОКИРОВКА"]):
            self.dispatch(сообщение(s, target))
        elif s == СОСТОЯНИЯ["СОХРАНЕНИЕ"]:
            data = _ask_json("Сохранение", "JSON данных для блока:")
            if data is not None:
                self.dispatch(сообщение(s, target, data))
        elif s == СОСТОЯНИЯ["СТИРАНИЕ"]:
            self.dispatch(сообщение(s, target, {}))
        elif s == СОСТОЯНИЯ["ПЕРЕДАЧА"]:
            data = _ask_json("Передача", '{"сигнал": {"уровень": 15}}:') or {"сигнал": {"уровень": 15}}
            if data is not None:
                self.dispatch(сообщение(s, target, data))
        elif s == СОСТОЯНИЯ["СНЯТИЕ_ВЫДЕЛЕНИЯ"]:
            self.dispatch(сообщение(s, target, {"все": True}))
        elif s in (СОСТОЯНИЯ["СОЕДИНЕНИЕ"], СОСТОЯНИЯ["РАЗЪЕДИНЕНИЕ"]):
            point = cube or target
            if self._first_point is None:
                self._first_point = point
                self.set_status(f"{s}: первый блок {point}, кликните второй")
            else:
                first, self._first_point = self._first_point, None
                self.dispatch(сообщение(s, first, {"с": list(point)}))
        elif s in (СОСТОЯНИЯ["ВЫДЕЛЕНИЕ"], СОСТОЯНИЯ["ПЕРЕМЕЩЕНИЕ"]):
            self._drag_start = cell

    def finish_drag(self, hit) -> None:
        if self._drag_start is None:
            return
        start = self._drag_start
        end = self._placement_coord(hit) or start
        self._drag_start = None

        if self.instrument == СОСТОЯНИЯ["ВЫДЕЛЕНИЕ"]:
            self.dispatch(сообщение(
                СОСТОЯНИЯ["ВЫДЕЛЕНИЕ"], start,
                {"область": [list(start), list(end)], "цвет": self.select_color},
            ))
        elif self.instrument == СОСТОЯНИЯ["ПЕРЕМЕЩЕНИЕ"]:
            shift = tuple(end[i] - start[i] for i in range(3))
            anchor = self._target_coord(hit) or start
            self.dispatch(сообщение(СОСТОЯНИЯ["ПЕРЕМЕЩЕНИЕ"], anchor, {"сдвиг": list(shift)}))

    def destroy_at_cursor(self, hit) -> None:
        c = self._target_coord(hit)
        if c and c in self.world.блоки:
            self.dispatch(сообщение(СОСТОЯНИЯ["УНИЧТОЖЕНИЕ"], c))

    def sync_voxels(self) -> None:
        existing = set(self._voxels)
        current = set(self.world.блоки)

        for removed in existing - current:
            destroy(self._voxels.pop(removed))

        for coord in current - existing:
            self._voxels[coord] = self._make_voxel(coord)

        for coord in current & existing:
            self._update_voxel(coord)

        self._refresh_hud()

    def _make_voxel(self, coord: Coord) -> Entity:
        x, y, z = coord
        ent = Button(
            parent=scene,
            model="cube",
            position=(x + 0.5, y + 0.5, z + 0.5),
            scale=1,
            texture="white_cube",
            collider="box",
            highlight_color=color.clear,
        )
        ent.block_coord = coord  # type: ignore[attr-defined]
        self._update_voxel(coord, ent)
        return ent

    def _update_voxel(self, coord: Coord, ent: Optional[Entity] = None) -> None:
        ent = ent or self._voxels.get(coord)
        block = self.world.блоки.get(coord)
        if ent is None or block is None:
            return
        base = _hex_to_color(block.цвет)
        if block.выделен:
            ent.color = color.lerp(base, _hex_to_color(self.select_color), 0.45)
        elif block.сигнал is not None:
            ent.color = color.lerp(base, color.red, 0.35)
        else:
            ent.color = base
        if block.заблокирован:
            ent.color = color.lerp(ent.color, color.orange, 0.3)

    def on_input(self, key: str) -> None:
        if key == "escape":
            mouse.locked = not mouse.locked
            return

        if key.isdigit() and key != "0":
            idx = int(key) - 1
            if 0 <= idx < len(ИНСТРУМЕНТЫ):
                self.select_instrument(ИНСТРУМЕНТЫ[idx][1])
            return

        if key == "0" and len(ИНСТРУМЕНТЫ) >= 10:
            self.select_instrument(ИНСТРУМЕНТЫ[9][1])
        if key == "-" and len(ИНСТРУМЕНТЫ) >= 11:
            self.select_instrument(ИНСТРУМЕНТЫ[10][1])
        if key == "=" and len(ИНСТРУМЕНТЫ) >= 12:
            self.select_instrument(ИНСТРУМЕНТЫ[11][1])

        if key == "c" and not held_keys["shift"]:
            try:
                import tkinter as tk
                from tkinter import colorchooser

                root = tk.Tk()
                root.withdraw()
                picked = colorchooser.askcolor(self.block_color, parent=root)[1]
                root.destroy()
                if picked:
                    self.block_color = picked
                    self._refresh_hud()
            except Exception:
                pass

        if key == "f5":
            self.world.save("redstone_world.json")
            self.set_status("Сохранено: redstone_world.json")
        if key == "f9":
            try:
                self.world = World.load("redstone_world.json")
                self.world.наблюдатели.append(lambda _m: self.sync_voxels())
                self.sync_voxels()
                self.set_status("Загружено: redstone_world.json")
            except OSError as exc:
                self.set_status(f"Нет файла: {exc}")

        if not mouse.locked:
            return

        hit = self._hit()
        if key == "left mouse down":
            if self.instrument in (СОСТОЯНИЯ["ВЫДЕЛЕНИЕ"], СОСТОЯНИЯ["ПЕРЕМЕЩЕНИЕ"]):
                self._drag_start = self._placement_coord(hit)
            else:
                self.apply_instrument_lmb(hit)
        elif key == "left mouse up":
            if self.instrument in (СОСТОЯНИЯ["ВЫДЕЛЕНИЕ"], СОСТОЯНИЯ["ПЕРЕМЕЩЕНИЕ"]):
                self.finish_drag(hit)
        elif key == "right mouse down":
            self.destroy_at_cursor(hit)


def input(key: str) -> None:
    if _active:
        _active.on_input(key)


def run_minecraft_fp() -> None:
    MinecraftFPApp().run()


if __name__ == "__main__":
    run_minecraft_fp()
