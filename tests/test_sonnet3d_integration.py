"""Integration tests for sonnet_3d: verifies that BlockManager's Codex3DBridge
keeps the core World in sync with Ursina-side state mutations.

These tests run without Ursina by stubbing the minimal Ursina API surface used
by BlockManager (Button, camera, player, raycast, destroy, invoke, scene,
distance, color, Vec3, held_keys, mouse).
"""

import sys
import types
import importlib
from unittest.mock import MagicMock, patch


# ---------------------------------------------------------------------------
# Minimal Ursina stub – must be installed before importing main
# ---------------------------------------------------------------------------
def _make_ursina_stub():
    ursina = types.ModuleType("ursina")

    class Vec3:
        def __init__(self, x=0, y=0, z=0):
            self.x, self.y, self.z = x, y, z
        def __add__(self, other):
            return Vec3(self.x + other.x, self.y + other.y, self.z + other.z)
        def __mul__(self, s):
            return Vec3(self.x * s, self.y * s, self.z * s)
        __rmul__ = __mul__

    class FakeColor:
        def __init__(self, r=0, g=0, b=0, a=255):
            self.r, self.g, self.b, self.a = r, g, b, a
        def tint(self, t):
            return FakeColor()
        def rgba(self, *a):
            return FakeColor()
        def rgb(self, *a):
            return FakeColor()

    _white = FakeColor(255, 255, 255)
    _gray  = FakeColor(128, 128, 128)

    color_mod = types.SimpleNamespace(
        white=_white, gray=_gray, green=FakeColor(0,255,0), blue=FakeColor(0,0,255),
        red=FakeColor(255,0,0), cyan=FakeColor(0,255,255), violet=FakeColor(148,0,211),
        yellow=FakeColor(255,255,0), orange=FakeColor(255,165,0), magenta=FakeColor(255,0,255),
        lime=FakeColor(0,255,0), azure=FakeColor(0,127,255), pink=FakeColor(255,192,203),
        black=FakeColor(0,0,0), dark_gray=FakeColor(64,64,64),
        rgba=lambda r,g,b,a: FakeColor(r,g,b,a),
        rgb=lambda r,g,b: FakeColor(r,g,b),
    )

    class FakeEntity:
        _counter = 0
        def __init__(self, **kwargs):
            FakeEntity._counter += 1
            self.__dict__.update(kwargs)
            self.children = []
            self.enabled = True
            self.visible = True
        def disable(self):
            self.enabled = False

    class FakeButton(FakeEntity):
        def __init__(self, **kwargs):
            super().__init__(**kwargs)
            self.hovered = False
            self.states = {}
            self.block_data = {}
            self.state = 0
            self.block_id = 0

    class FakeInputField(FakeEntity):
        def __init__(self, **kwargs):
            super().__init__(**kwargs)
            self.text = ""
            self.active = False
            self.submit_on = []
            self.on_submit = None

    class FakeText(FakeEntity):
        def __init__(self, **kwargs):
            super().__init__(**kwargs)
            self.text = kwargs.get("text", "")

    ursina.Ursina = lambda: None
    ursina.Entity = FakeEntity
    ursina.Button = FakeButton
    ursina.Text = FakeText
    ursina.InputField = FakeInputField
    ursina.Sky = lambda: None
    ursina.Vec3 = Vec3
    ursina.color = color_mod
    ursina.camera = types.SimpleNamespace(
        ui=FakeEntity(),
        world_position=Vec3(),
        forward=Vec3(0, 0, 1),
        position=Vec3(),
    )
    ursina.mouse = types.SimpleNamespace(
        locked=False, position=Vec3(), world_point=None, x=0.0, y=0.0,
    )
    ursina.held_keys = {}
    ursina.scene = types.SimpleNamespace(entities=[])
    ursina.application = types.SimpleNamespace(quit_keys=('escape',))
    ursina.distance = lambda a, b: 0.0
    ursina.raycast = lambda *a, **kw: None
    ursina.destroy = lambda *a, **kw: None
    ursina.invoke = lambda *a, **kw: None

    # prefabs
    fpc_mod = types.ModuleType("ursina.prefabs.first_person_controller")
    class FPC:
        def update(self): pass
        def __init__(self, **kw): pass
    FPC.update = FPC.__dict__["update"]
    fpc_mod.FirstPersonController = FPC

    prefabs_mod = types.ModuleType("ursina.prefabs")
    prefabs_mod.first_person_controller = fpc_mod

    sys.modules["ursina"] = ursina
    sys.modules["ursina.prefabs"] = prefabs_mod
    sys.modules["ursina.prefabs.first_person_controller"] = fpc_mod

    return ursina, FakeButton


_ursina_stub, _FakeButton = _make_ursina_stub()
# Patch numpy to avoid import issues if not installed
if "numpy" not in sys.modules:
    sys.modules["numpy"] = MagicMock()


# ---------------------------------------------------------------------------
# Import the parts of main we want to test without running the Ursina app
# ---------------------------------------------------------------------------
from redstone.core import World, СОСТОЯНИЯ, сообщение
from redstone.codex3d_bridge import Codex3DBridge


# ---------------------------------------------------------------------------
# Minimal BlockManager clone (only the bridge-related parts)
# ---------------------------------------------------------------------------
class _MinimalBlockManager:
    def __init__(self):
        self.blocks = []
        self.selected_blocks = []
        self.hovered_block = None
        self.bridge = Codex3DBridge()

    def _coord(self, pos):
        if isinstance(pos, tuple):
            return (int(round(pos[0])), int(round(pos[1])), int(round(pos[2])))
        p = getattr(pos, 'position', pos)
        if hasattr(p, 'x'):
            return (int(round(p.x)), int(round(p.y)), int(round(p.z)))
        return (int(round(p[0])), int(round(p[1])), int(round(p[2])))

    def world_dispatch(self, state_key, coord, data=None):
        try:
            self.bridge.world.dispatch(
                сообщение(СОСТОЯНИЯ[state_key], self._coord(coord), data or {})
            )
        except (KeyError, ValueError) as exc:
            raise

    def add_block(self, position=None, **kwargs):
        b = _FakeButton()
        b.position = position if position else (0, 0, 0)
        b.states = {'is_terrain': kwargs.get('is_terrain', False)}
        b.block_data = {}
        b.state = 0
        b.block_id = len(self.blocks)
        self.blocks.append(b)
        coord = self._coord(b.position)
        self.bridge.world.dispatch(
            сообщение(СОСТОЯНИЯ["ГЕНЕРАЦИЯ"], coord, {"цвет": "#9e9e9e"})
        )
        return b

    def remove_block(self, block):
        coord = self._coord(block.position)
        if block in self.blocks:
            self.blocks.remove(block)
        if coord in self.bridge.world.блоки:
            self.bridge.world.dispatch(сообщение(СОСТОЯНИЯ["УНИЧТОЖЕНИЕ"], coord))

    def update_block_color(self, block):
        pass

    def get_block_by_coord(self, coord):
        for b in self.blocks:
            if b.position == coord:
                return b
        return None


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_add_block_registers_in_world():
    bm = _MinimalBlockManager()
    block = bm.add_block(position=(3, 1, 5))
    coord = (3, 1, 5)
    assert coord in bm.bridge.world.блоки, "Block should be registered in core World"


def test_remove_block_removes_from_world():
    bm = _MinimalBlockManager()
    block = bm.add_block(position=(1, 0, 1))
    bm.remove_block(block)
    assert (1, 0, 1) not in bm.bridge.world.блоки, "Block should be removed from core World"


def test_apply_state_store_via_bridge():
    bm = _MinimalBlockManager()
    block = bm.add_block(position=(2, 0, 2))
    result = bm.bridge.apply_state(block, "store", {"value": '{"key": 42}'})
    assert result["status"] == "applied"
    core_block = bm.bridge.world.блоки.get((2, 0, 2))
    assert core_block is not None
    assert core_block.память.get("key") == 42


def test_apply_state_connect_via_bridge():
    bm = _MinimalBlockManager()
    a = bm.add_block(position=(0, 0, 0))
    b = bm.add_block(position=(1, 0, 0))
    r1 = bm.bridge.apply_state(a, "connect", {})
    r2 = bm.bridge.apply_state(b, "connect", {})
    assert r1["status"] == "pending"
    assert r2["status"] == "connected"
    assert (1, 0, 0) in bm.bridge.world.блоки[(0, 0, 0)].соединения
    assert (0, 0, 0) in bm.bridge.world.блоки[(1, 0, 0)].соединения


def test_process_conductive_blocks_updates_world_signal():
    bm = _MinimalBlockManager()
    src = bm.add_block(position=(0, 0, 0))
    tgt = bm.add_block(position=(1, 0, 0))
    src.state = 1
    src.states['conduct'] = {
        'active': True,
        'data': {'signal': {'level': 7}},
        'connections': [(1, 0, 0)],
    }
    bm.bridge.process_conductive_blocks(bm.blocks)
    world_tgt = bm.bridge.world.блоки.get((1, 0, 0))
    assert world_tgt is not None
    assert world_tgt.сигнал == {'signal': {'level': 7}}


def test_world_dispatch_helper():
    bm = _MinimalBlockManager()
    bm.add_block(position=(5, 5, 5))
    bm.world_dispatch("СОХРАНЕНИЕ", (5, 5, 5), {"foo": "bar"})
    core_block = bm.bridge.world.блоки[(5, 5, 5)]
    assert core_block.память.get("foo") == "bar"


def test_world_journal_grows_with_mutations():
    bm = _MinimalBlockManager()
    initial = len(bm.bridge.world.журнал)
    bm.add_block(position=(9, 0, 0))
    bm.add_block(position=(10, 0, 0))
    bm.bridge.apply_state(
        bm.get_block_by_coord((9, 0, 0)), "connect", {}
    )
    bm.bridge.apply_state(
        bm.get_block_by_coord((10, 0, 0)), "connect", {}
    )
    assert len(bm.bridge.world.журнал) >= initial + 3


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print(f"OK  {fn.__name__}")
    print(f"\nAll {len(fns)} integration tests passed.")
