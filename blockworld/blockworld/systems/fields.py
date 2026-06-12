"""Полевые оболочки (field shells) — полупрозрачные воксельные hull."""

from __future__ import annotations

from ursina import Entity, camera, color, raycast

from blockworld.constants import (
    FIELD_SHELL_COLORS,
    FIELD_SHELL_CUBE_SCALE,
    FIELD_SHELL_DEFAULT_RADIUS,
    FIELD_SHELL_SHAPE,
)

_field_overlay_parent = None


def get_field_overlay_parent():
    global _field_overlay_parent
    if _field_overlay_parent is not None:
        try:
            _ = _field_overlay_parent.enabled
            return _field_overlay_parent
        except (AssertionError, AttributeError):
            _field_overlay_parent = None
    _field_overlay_parent = Entity(name="field_overlay_parent", eternal=True)
    return _field_overlay_parent


def _field_shell_positions(center, radius, shape="cube"):
    cx, cy, cz = int(round(center[0])), int(round(center[1])), int(round(center[2]))
    R = int(radius)
    out = []
    for dx in range(-R, R + 1):
        for dy in range(-R, R + 1):
            for dz in range(-R, R + 1):
                if shape == "cube":
                    outer = max(abs(dx), abs(dy), abs(dz))
                    if R > 0 and (R - 1) < outer <= R:
                        out.append((cx + dx, cy + dy, cz + dz))
                else:
                    d2 = dx * dx + dy * dy + dz * dz
                    r_in = max(0, R - 1) ** 2
                    if r_in < d2 <= R * R:
                        out.append((cx + dx, cy + dy, cz + dz))
    return out


class FieldShell:
    def __init__(self, center, radius, channel_key, shape=None):
        self.channel_key = channel_key
        self.radius = int(radius)
        self.shape = shape if shape is not None else FIELD_SHELL_SHAPE
        cx, cy, cz = int(round(center[0])), int(round(center[1])), int(round(center[2]))
        rgba = FIELD_SHELL_COLORS[channel_key]
        self.root = Entity(
            parent=get_field_overlay_parent(),
            name=f"field_{self.shape}_{channel_key}_{id(self)}",
        )
        self._destroyed = False
        self.voxels = []
        s = FIELD_SHELL_CUBE_SCALE
        for pos in _field_shell_positions((cx, cy, cz), self.radius, self.shape):
            v = Entity(
                parent=self.root,
                model="cube",
                color=rgba,
                position=pos,
                scale=s,
                collider=None,
            )
            self.voxels.append(v)
        for v in self.voxels:
            v.render_queue = 1

    def destroy_shell(self):
        if self._destroyed:
            return
        self._destroyed = True
        for v in list(self.voxels):
            try:
                v.visible = False
                v.enabled = False
            except (AssertionError, AttributeError):
                pass
        self.voxels.clear()
        if self.root is not None:
            try:
                self.root.visible = False
                self.root.enabled = False
            except (AssertionError, AttributeError):
                pass
        self.root = None


class FieldShellManager:
    def __init__(self, block_manager):
        self.block_manager = block_manager
        self.shells = []

    def spawn(self, center, channel_key, radius=None, shape=None):
        if channel_key not in FIELD_SHELL_COLORS:
            return None
        r = radius if radius is not None else FIELD_SHELL_DEFAULT_RADIUS
        shell_shape = shape if shape is not None else FIELD_SHELL_SHAPE
        shell = FieldShell(center, r, channel_key, shape=shell_shape)
        self.shells.append(shell)
        return shell

    def spawn_at_crosshair(self, channel_key, radius=None, shape=None, player=None):
        hit_info = raycast(camera.world_position, camera.forward, distance=80)
        if hit_info and hit_info.hit and hit_info.entity in self.block_manager.blocks:
            p = hit_info.entity.position
            center = (int(round(p.x)), int(round(p.y)), int(round(p.z)))
        else:
            from ursina import Vec3
            t = player.position + camera.forward * 6 + Vec3(0, 0.5, 0) if player else camera.forward * 6
            center = (int(round(t.x)), int(round(t.y)), int(round(t.z)))
        return self.spawn(center, channel_key, radius=radius, shape=shape)

    def clear_all(self):
        for sh in self.shells:
            sh.destroy_shell()
        self.shells.clear()
