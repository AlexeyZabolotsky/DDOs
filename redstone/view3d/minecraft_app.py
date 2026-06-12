"""3D-клиент редстоуна: камера от первого лица, воксели, HUD как в Minecraft."""

from __future__ import annotations

from typing import Any

from ursina import (
    AmbientLight,
    DirectionalLight,
    Entity,
    Sky,
    Ursina,
    Vec3,
    camera,
    color,
    held_keys,
    mouse,
    raycast,
    time,
    window,
)

from redstone.block import BlockType
from redstone.engine import RedstoneEngine
from redstone.message import Action
from redstone.view3d.hud import MinecraftHUD
from redstone.view3d.voxel_renderer import VoxelRenderer

_active: "MinecraftRedstoneApp | None" = None


class MinecraftRedstoneApp:
    """
    Полноценный 3D-интерфейс в стиле Minecraft.

    - Камера от первого лица (WASD + мышь)
    - Воксельный мир с травой/землёй
    - Хотбар и прицел
    - Все действия редстоуна через ЛКМ/ПКМ и модификаторы
    """

    REACH = 8.0

    def __init__(self) -> None:
        self.engine = RedstoneEngine()
        self.renderer = VoxelRenderer(self.engine)
        self.hud = MinecraftHUD()
        self._player: Entity | None = None
        self._shift = False
        self._ctrl = False
        self._alt = False
        self._last_status = ""

    def run(self) -> None:
        global _active
        _active = self

        app = Ursina(
            title="Редстоун 3D — Minecraft",
            borderless=False,
            fullscreen=False,
            development_mode=False,
        )
        window.color = color.rgb(135, 206, 235)
        window.fps_counter.enabled = True
        window.exit_button.visible = False

        Sky(color=color.rgb(120, 180, 255))
        DirectionalLight(direction=Vec3(1, -1, 0.5), shadows=False)
        AmbientLight(color=color.rgba(180, 180, 180, 0.4))

        self.renderer.build_terrain(radius=22)
        self._spawn_player()
        self._seed_demo_blocks()
        self.renderer.sync_all()

        mouse.locked = True
        self.hud.set_status("Добро пожаловать в мир редстоуна")
        app.run()

    def _spawn_player(self) -> None:
        self._player = Entity(
            model="cube",
            visible=False,
            collider="box",
            scale=(0.6, 1.8, 0.6),
            position=(0, 2, -6),
        )
        camera.parent = self._player
        camera.position = (0, 0.8, 0)
        camera.rotation = (0, 0, 0)
        camera.fov = 80
        self._player.velocity = Vec3(0, 0, 0)
        self._player.grounded = False
        self._player.speed = 6
        self._player.jump_height = 2

    def _seed_demo_blocks(self) -> None:
        demos = [
            (2, 1, 0, BlockType.GENERATOR),
            (3, 1, 0, BlockType.RELAY),
            (4, 1, 0, BlockType.STORAGE),
        ]
        for x, y, z, btype in demos:
            self.engine.process({
                "состояние": "активен",
                "координата_воздействия": [x, y, z],
                "передаваемые_данные": {
                    "действие": Action.GENERATE.value,
                    "тип": btype.value,
                },
            })

    def _modifiers(self) -> dict[str, bool]:
        return {
            "shift": self._shift or held_keys["shift"],
            "ctrl": self._ctrl or held_keys["control"],
            "alt": self._alt or held_keys["alt"],
        }

    def on_input(self, key: str) -> None:
        if key == "escape":
            mouse.locked = not mouse.locked
            return

        if key in ("shift", "left shift", "right shift"):
            self._shift = True
        if key in ("control", "left control", "right control"):
            self._ctrl = True
        if key in ("alt", "left alt", "right alt"):
            self._alt = True

        if key in ("shift up", "left shift up", "right shift up"):
            self._shift = False
        if key in ("control up", "left control up", "right control up"):
            self._ctrl = False
        if key in ("alt up", "left alt up", "right alt up"):
            self._alt = False

        if key.isdigit() and key != "0":
            slot = self.hud.select_slot(int(key) - 1)
            self.engine.set_mouse_mode(Action(slot["action"]))
            self.hud.set_status(f"Слот {key}: {slot['label']}")

        if key == "left mouse down" and mouse.locked:
            self._handle_click(button=1)
        if key == "right mouse down" and mouse.locked:
            self._handle_click(button=3)

    def _handle_click(self, button: int) -> None:
        hit = raycast(
            camera.world_position,
            camera.forward,
            distance=self.REACH,
            ignore=[self._player],
            debug=False,
        )
        modifiers = self._modifiers()
        slot = self.hud.current_slot()

        if button == 3:
            coord = self.renderer.target_coordinate(hit.entity if hit.hit else None)
            if coord is None:
                return
            result = self.engine.handle_mouse(*coord, button=3, modifiers=modifiers)
            self._apply_result(result, coord)
            return

        action = Action(slot["action"])
        self.engine.set_mouse_mode(action)

        if action == Action.GENERATE:
            if not hit.hit:
                return
            coord = self.renderer.placement_position(hit.entity, hit.normal)
            if coord is None or self.engine.world.get(*coord):
                return
            result = self.engine.process({
                "состояние": "активен",
                "координата_воздействия": list(coord),
                "передаваемые_данные": {
                    "действие": Action.GENERATE.value,
                    "тип": slot["тип"],
                },
            })
            self._apply_result(result, coord)
            return

        coord = self.renderer.target_coordinate(hit.entity if hit.hit else None)
        if coord is None:
            return

        if action == Action.TRANSFER:
            result = self.engine.process({
                "координата_воздействия": list(coord),
                "передаваемые_данные": {
                    "действие": Action.TRANSFER.value,
                    "данные": {"импульс": 1},
                },
            })
        else:
            result = self.engine.handle_mouse(*coord, button=1, modifiers=modifiers)

        self._apply_result(result, coord)

    def _apply_result(self, result: dict[str, Any], coord: tuple[int, int, int]) -> None:
        self.renderer.sync_all()
        text = f"{coord} → {result.get('результат', result)}"
        if text != self._last_status:
            self.hud.set_status(text)
            self._last_status = text

    def on_update(self) -> None:
        if self._player is None:
            return
        self._move_player()
        self._update_highlight()

    def _move_player(self) -> None:
        p = self._player
        direction = Vec3(
            held_keys["d"] - held_keys["a"],
            0,
            held_keys["w"] - held_keys["s"],
        )
        if direction.length() > 0:
            direction = direction.normalized()
        move = direction * p.speed * time.dt

        if p.grounded and held_keys["space"]:
            p.velocity = Vec3(p.velocity.x, p.jump_height, p.velocity.z)

        p.velocity = Vec3(
            p.velocity.x,
            p.velocity.y - 18 * time.dt,
            p.velocity.z,
        )

        if direction.length() > 0:
            p.position += camera.right * move.x + camera.forward * move.z

        ground_hit = raycast(
            p.position + Vec3(0, 1, 0),
            Vec3(0, -1, 0),
            distance=2,
            ignore=[p],
        )
        if ground_hit.hit and ground_hit.distance < 1.1:
            p.y = ground_hit.entity.y + 1.4
            p.velocity = Vec3(p.velocity.x, 0, p.velocity.z)
            p.grounded = True
        else:
            p.y += p.velocity.y * time.dt
            p.grounded = False

        if mouse.locked:
            p.rotation_y += mouse.velocity[0] * 40
            camera.rotation_x -= mouse.velocity[1] * 40
            camera.rotation_x = max(-89, min(89, camera.rotation_x))

    def _update_highlight(self) -> None:
        hit = raycast(
            camera.world_position,
            camera.forward,
            distance=self.REACH,
            ignore=[self._player],
        )
        if hit.hit:
            self.renderer.highlight(tuple(hit.entity.position))
        else:
            self.renderer.highlight(None)


def update() -> None:
    if _active:
        _active.on_update()


def input(key: str) -> None:
    if _active:
        _active.on_input(key)


def run_minecraft_3d() -> None:
    MinecraftRedstoneApp().run()


if __name__ == "__main__":
    run_minecraft_3d()
