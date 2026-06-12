"""Выделение блоков полем из группы — куб/сфера вокруг центра или связанной компоненты."""

from __future__ import annotations

from typing import TYPE_CHECKING, Literal

from ursina import color

if TYPE_CHECKING:
    from blockworld.systems.block_manager import BlockManager
    from blockworld.systems.fields import FieldShellManager


Shape = Literal["cube", "sphere"]


def _pos_tuple(block_or_pos):
    if isinstance(block_or_pos, (tuple, list)) and len(block_or_pos) >= 3:
        return (int(round(block_or_pos[0])), int(round(block_or_pos[1])), int(round(block_or_pos[2])))
    if block_or_pos is None:
        return None
    if hasattr(block_or_pos, "position"):
        p = block_or_pos.position
        if isinstance(p, tuple):
            return (int(round(p[0])), int(round(p[1])), int(round(p[2])))
        try:
            return (int(round(block_or_pos.x)), int(round(block_or_pos.y)), int(round(block_or_pos.z)))
        except (AttributeError, AssertionError):
            return None
    return None


def blocks_in_field(
    block_manager: "BlockManager",
    center: tuple[int, int, int],
    radius: int,
    shape: Shape = "cube",
) -> list:
    """Все блоки block_manager внутри поля (включая центр при radius>0)."""
    cx, cy, cz = center
    R = int(radius)
    found = []
    for block in block_manager.blocks:
        pos = _pos_tuple(block)
        if pos is None:
            continue
        dx, dy, dz = pos[0] - cx, pos[1] - cy, pos[2] - cz
        if shape == "cube":
            if max(abs(dx), abs(dy), abs(dz)) <= R:
                found.append(block)
        else:
            if dx * dx + dy * dy + dz * dz <= R * R:
                found.append(block)
    return found


def connected_component_from(block_manager: "BlockManager", start_block) -> set:
    """Flood-fill по соседним блокам (6 направлений) и conduct/connect связям."""
    start_pos = _pos_tuple(start_block)
    if start_pos is None:
        return set()

    pos_to_block = {}
    for b in block_manager.blocks:
        p = _pos_tuple(b)
        if p is not None:
            pos_to_block[p] = b

    def neighbors_pos(pos):
        x, y, z = pos
        return [
            (x + 1, y, z), (x - 1, y, z),
            (x, y + 1, z), (x, y - 1, z),
            (x, y, z + 1), (x, y, z - 1),
        ]

    visited: set = set()
    stack = [start_block]
    component = []

    while stack:
        block = stack.pop()
        pos = _pos_tuple(block)
        if pos is None or pos in visited:
            continue
        visited.add(pos)
        component.append(block)

        for npos in neighbors_pos(pos):
            if npos in visited:
                continue
            nb = pos_to_block.get(npos)
            if nb is not None:
                stack.append(nb)

        if hasattr(block, "states"):
            conduct = block.states.get("conduct", {})
            for target in conduct.get("connections", []):
                tb = block_manager.get_block_by_coord(target)
                if tb is not None and tb not in component:
                    stack.append(tb)
            connect = block.states.get("connect", {})
            if connect.get("active") and connect.get("target"):
                tb = block_manager.get_block_by_coord(connect["target"])
                if tb is not None and tb not in component:
                    stack.append(tb)

    return set(component)


class FieldSelector:
  """
  Режим выделения блоков полем:
  - клик по блоку → выделить связанную группу, пересекающуюся с полем
  - или выделить все блоки внутри поля вокруг центра
  """

  CHANNEL_COLORS = ("cyan", "green", "yellow", "red")

  def __init__(self, block_manager: "BlockManager", field_shell_manager: "FieldShellManager"):
    self.block_manager = block_manager
    self.field_shell_manager = field_shell_manager
    self.active = False
    self.radius = 4
    self.shape: Shape = "cube"
    self.channel_key = "cyan"
    self.group_only = True
    self.last_shell = None

  def set_radius(self, r: int) -> None:
    self.radius = max(1, min(16, int(r)))

  def toggle_shape(self) -> Shape:
    self.shape = "sphere" if self.shape == "cube" else "cube"
    return self.shape

  def select_at_block(self, block, show_shell: bool = True) -> list:
    """Выделить блоки: группа ∩ поле вокруг блока."""
    center = _pos_tuple(block)
    if center is None:
      return []

    if self.group_only:
      group = connected_component_from(self.block_manager, block)
      in_field = set(blocks_in_field(self.block_manager, center, self.radius, self.shape))
      selected = [b for b in group if b in in_field]
      if not selected:
        selected = list(group)
    else:
      selected = blocks_in_field(self.block_manager, center, self.radius, self.shape)

    self.block_manager.selected_blocks = list(selected)
    self.block_manager.update_selection_visual()

    if show_shell:
      if self.last_shell is not None:
        self.last_shell.destroy_shell()
      self.last_shell = self.field_shell_manager.spawn(
        center, self.channel_key, radius=self.radius, shape=self.shape
      )

    print(f"Field select: {len(selected)} blocks at {center}, R={self.radius}, {self.shape}")
    return selected

  def select_at_center(self, center: tuple[int, int, int], show_shell: bool = True) -> list:
    selected = blocks_in_field(self.block_manager, center, self.radius, self.shape)
    self.block_manager.selected_blocks = selected
    self.block_manager.update_selection_visual()
    if show_shell:
      if self.last_shell is not None:
        self.last_shell.destroy_shell()
      self.last_shell = self.field_shell_manager.spawn(
        center, self.channel_key, radius=self.radius, shape=self.shape
      )
    return selected

  def clear_shell(self) -> None:
    if self.last_shell is not None:
      self.last_shell.destroy_shell()
      self.last_shell = None

  def cycle_channel(self) -> str:
    idx = self.CHANNEL_COLORS.index(self.channel_key) if self.channel_key in self.CHANNEL_COLORS else 0
    self.channel_key = self.CHANNEL_COLORS[(idx + 1) % len(self.CHANNEL_COLORS)]
    return self.channel_key
