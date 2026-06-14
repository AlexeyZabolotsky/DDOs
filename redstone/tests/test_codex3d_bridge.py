"""Tests for Codex3DBridge (integration helper for 3D script)."""

from redstone.codex3d_bridge import Codex3DBridge


class _FakeBlock:
    def __init__(self, position, state=0, states=None):
        self.position = position
        self.state = state
        self.states = states or {}


def test_store_state_writes_world_memory():
    bridge = Codex3DBridge()
    b = _FakeBlock((1, 2, 3))

    result = bridge.apply_state(b, "store", {"value": '{"meta":{"v":1}}'})

    assert result["status"] == "applied"
    assert bridge.world.блоки[(1, 2, 3)].память == {"meta": {"v": 1}}


def test_connect_state_creates_bidirectional_link():
    bridge = Codex3DBridge()
    a = _FakeBlock((0, 0, 0))
    b = _FakeBlock((1, 0, 0))

    pending = bridge.apply_state(a, "connect", {})
    connected = bridge.apply_state(b, "connect", {})

    assert pending["status"] == "pending"
    assert connected["status"] == "connected"
    assert (1, 0, 0) in bridge.world.блоки[(0, 0, 0)].соединения
    assert (0, 0, 0) in bridge.world.блоки[(1, 0, 0)].соединения


def test_process_conductive_blocks_transmits_signal():
    bridge = Codex3DBridge()
    source = _FakeBlock(
        (0, 0, 0),
        state=1,
        states={"conduct": {"active": True, "data": {"signal": {"level": 9}}, "connections": [(1, 0, 0)]}},
    )
    target = _FakeBlock((1, 0, 0))

    bridge.process_conductive_blocks([source, target])

    assert bridge.world.блоки[(1, 0, 0)].сигнал == {"signal": {"level": 9}}
