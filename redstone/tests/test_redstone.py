"""Тесты ядра redstone: все функции через данные и через мышку."""

import unittest

from redstone import (
    Action,
    MouseButton,
    MouseController,
    MouseEvent,
    Packet,
    Tool,
    World,
)


class PacketFormatTest(unittest.TestCase):
    def test_to_from_dict_roundtrip(self):
        p = Packet(Action.SAVE, (1, 2, 3), {"a": {"b": {"c": 1}}})
        d = p.to_dict()
        self.assertEqual(d["state"], "save")
        self.assertEqual(d["coord"], (1, 2, 3))
        p2 = Packet.from_dict(d)
        self.assertEqual(p2.coord, (1, 2, 3))
        self.assertEqual(p2.data, {"a": {"b": {"c": 1}}})

    def test_from_dict_xyz_keys(self):
        p = Packet.from_dict({"state": "generate", "x": 1, "y": 2, "z": 3})
        self.assertEqual(p.coord, (1, 2, 3))

    def test_nested_get(self):
        p = Packet(Action.SAVE, (0, 0, 0), {"a": {"b": 42}})
        self.assertEqual(p.get("a.b"), 42)
        self.assertIsNone(p.get("a.x"))

    def test_invalid_coord(self):
        with self.assertRaises(ValueError):
            Packet(Action.GENERATE, (1, 2))

    def test_data_must_be_dict(self):
        with self.assertRaises(TypeError):
            Packet(Action.SAVE, (0, 0, 0), [1, 2, 3])


class GenerateDestroyTest(unittest.TestCase):
    def test_generate_and_destroy(self):
        w = World()
        b = w.generate((0, 0, 0), color="red")
        self.assertIn((0, 0, 0), w)
        self.assertEqual(b.color, "red")
        self.assertTrue(w.destroy((0, 0, 0)))
        self.assertNotIn((0, 0, 0), w)
        self.assertFalse(w.destroy((0, 0, 0)))

    def test_destroy_breaks_connections(self):
        w = World()
        w.generate((0, 0, 0))
        w.generate((1, 0, 0))
        w.connect((0, 0, 0), (1, 0, 0))
        w.destroy((0, 0, 0))
        self.assertEqual(w.get((1, 0, 0)).connections, set())

    def test_block_spawns_block(self):
        w = World()
        a = w.generate((0, 0, 0))
        b = a.spawn((1, 0, 0))
        self.assertIn((1, 0, 0), w)
        self.assertIs(b.world, w)


class SaveEraseTest(unittest.TestCase):
    def test_save_deep_merge(self):
        w = World()
        b = w.generate((0, 0, 0))
        b.save({"a": {"b": 1}})
        b.save({"a": {"c": 2}})
        self.assertEqual(b.data, {"a": {"b": 1, "c": 2}})

    def test_save_replace(self):
        w = World()
        b = w.generate((0, 0, 0))
        b.save({"a": 1})
        b.save({"x": 2}, merge=False)
        self.assertEqual(b.data, {"x": 2})

    def test_erase_keys_and_all(self):
        w = World()
        b = w.generate((0, 0, 0))
        b.save({"a": 1, "b": 2})
        b.erase("a")
        self.assertEqual(b.data, {"b": 2})
        b.erase()
        self.assertEqual(b.data, {})
        self.assertEqual(b.state, "idle")


class TransmissionTest(unittest.TestCase):
    def _line(self):
        w = World()
        for x in range(4):
            w.generate((x, 0, 0))
        for x in range(3):
            w.connect((x, 0, 0), (x + 1, 0, 0))
        return w

    def test_transmit_whole_group(self):
        w = self._line()
        received = w.get((0, 0, 0)).transmit({"power": 15})
        self.assertEqual(len(received), 4)
        for x in range(4):
            self.assertEqual(w.get((x, 0, 0)).data["power"], 15)

    def test_block_stops_propagation(self):
        w = self._line()
        w.get((2, 0, 0)).block_transmission()
        received = w.get((0, 0, 0)).transmit({"power": 9})
        coords = {b.coord for b in received}
        self.assertEqual(coords, {(0, 0, 0), (1, 0, 0)})
        self.assertEqual(w.get((3, 0, 0)).data, {})

    def test_unblock_restores(self):
        w = self._line()
        b = w.get((2, 0, 0))
        b.block_transmission()
        b.unblock_transmission()
        received = w.get((0, 0, 0)).transmit({"power": 1})
        self.assertEqual(len(received), 4)

    def test_blocked_source_transmits_nothing(self):
        w = self._line()
        w.get((0, 0, 0)).block_transmission()
        self.assertEqual(w.get((0, 0, 0)).transmit({"p": 1}), [])


class ConnectGroupTest(unittest.TestCase):
    def test_connected_group(self):
        w = World()
        for x in range(3):
            w.generate((x, 0, 0))
        w.generate((9, 9, 9))  # отдельный блок
        w.connect((0, 0, 0), (1, 0, 0))
        w.connect((1, 0, 0), (2, 0, 0))
        group = w.connected_group((0, 0, 0))
        self.assertEqual(set(group.coords), {(0, 0, 0), (1, 0, 0), (2, 0, 0)})

    def test_disconnect_splits_group(self):
        w = World()
        for x in range(3):
            w.generate((x, 0, 0))
        w.connect((0, 0, 0), (1, 0, 0))
        w.connect((1, 0, 0), (2, 0, 0))
        w.disconnect((1, 0, 0), (2, 0, 0))
        group = w.connected_group((0, 0, 0))
        self.assertEqual(set(group.coords), {(0, 0, 0), (1, 0, 0)})

    def test_cannot_connect_self(self):
        w = World()
        w.generate((0, 0, 0))
        with self.assertRaises(ValueError):
            w.connect((0, 0, 0), (0, 0, 0))


class SelectTest(unittest.TestCase):
    def test_select_connected_group_with_color(self):
        w = World()
        w.generate((0, 0, 0))
        w.generate((1, 0, 0))
        w.connect((0, 0, 0), (1, 0, 0))
        group = w.get((0, 0, 0)).select(color="blue")
        self.assertTrue(all(b.selected for b in group))
        self.assertTrue(all(b.color == "blue" for b in group))

    def test_select_by_color(self):
        w = World()
        w.generate((0, 0, 0), color="red")
        w.generate((1, 0, 0), color="red")
        w.generate((2, 0, 0), color="green")
        group = w.select(color="red")
        self.assertEqual(set(group.coords), {(0, 0, 0), (1, 0, 0)})

    def test_select_by_state(self):
        w = World()
        w.generate((0, 0, 0))
        w.get((0, 0, 0)).save({"a": 1})  # state -> stored
        w.generate((1, 0, 0))
        group = w.select(state="stored")
        self.assertEqual(group.coords, [(0, 0, 0)])


class MoveGroupDataTest(unittest.TestCase):
    def test_move_data_shifts_payloads(self):
        w = World()
        w.generate((0, 0, 0))
        w.generate((1, 0, 0))
        w.connect((0, 0, 0), (1, 0, 0))
        w.get((0, 0, 0)).save({"v": 1})
        w.get((1, 0, 0)).save({"v": 2})
        # цели для переноса
        w.generate((0, 1, 0))
        w.generate((1, 1, 0))
        w.get((0, 0, 0)).move_group_data((0, 1, 0))
        self.assertEqual(w.get((0, 1, 0)).data, {"v": 1})
        self.assertEqual(w.get((1, 1, 0)).data, {"v": 2})
        self.assertEqual(w.get((0, 0, 0)).data, {})


class DispatchTest(unittest.TestCase):
    def test_dispatch_all_actions(self):
        w = World()
        w.dispatch(Packet(Action.GENERATE, (0, 0, 0)))
        w.dispatch(Packet(Action.GENERATE, (1, 0, 0)))
        w.dispatch(Packet(Action.CONNECT, (0, 0, 0), {"target": (1, 0, 0)}))
        w.dispatch(Packet(Action.SAVE, (0, 0, 0), {"payload": {"k": {"deep": 1}}}))
        self.assertEqual(w.get((0, 0, 0)).data, {"k": {"deep": 1}})
        w.dispatch(Packet(Action.TRANSMIT, (0, 0, 0), {"payload": {"sig": 1}}))
        self.assertEqual(w.get((1, 0, 0)).data["sig"], 1)
        w.dispatch(Packet(Action.BLOCK, (1, 0, 0)))
        self.assertFalse(w.get((1, 0, 0)).transmitting)
        w.dispatch(Packet(Action.UNBLOCK, (1, 0, 0)))
        self.assertTrue(w.get((1, 0, 0)).transmitting)
        w.dispatch(Packet(Action.DISCONNECT, (0, 0, 0), {"target": (1, 0, 0)}))
        self.assertEqual(w.get((0, 0, 0)).connections, set())
        w.dispatch(Packet(Action.ERASE, (0, 0, 0)))
        self.assertEqual(w.get((0, 0, 0)).data, {})
        w.dispatch(Packet(Action.DESTROY, (1, 0, 0)))
        self.assertNotIn((1, 0, 0), w)

    def test_dispatch_accepts_plain_dict(self):
        w = World()
        w.dispatch({"state": "generate", "coord": (5, 5, 5)})
        self.assertIn((5, 5, 5), w)

    def test_unknown_action(self):
        w = World()
        with self.assertRaises(ValueError):
            w.dispatch(Packet("dance", (0, 0, 0)))


class MouseTest(unittest.TestCase):
    def test_generate_destroy_by_mouse(self):
        w = World()
        m = MouseController(w, tool=Tool.GENERATE)
        m.click(MouseEvent(x=2, y=3))
        self.assertIn((2, 3, 0), w)
        m.select_tool(Tool.DESTROY)
        m.click(MouseEvent(x=2, y=3))
        self.assertNotIn((2, 3, 0), w)

    def test_connect_two_clicks(self):
        w = World()
        m = MouseController(w, tool=Tool.GENERATE)
        m.click(MouseEvent(x=0, y=0))
        m.click(MouseEvent(x=1, y=0))
        m.select_tool(Tool.CONNECT)
        self.assertIsNone(m.click(MouseEvent(x=0, y=0)))  # первый клик
        m.click(MouseEvent(x=1, y=0))  # второй клик
        self.assertIn((1, 0, 0), w.get((0, 0, 0)).connections)

    def test_block_unblock_by_buttons(self):
        w = World()
        w.generate((0, 0, 0))
        m = MouseController(w, tool=Tool.BLOCK)
        m.click(MouseEvent(x=0, y=0, button=MouseButton.LEFT))
        self.assertFalse(w.get((0, 0, 0)).transmitting)
        m.click(MouseEvent(x=0, y=0, button=MouseButton.RIGHT))
        self.assertTrue(w.get((0, 0, 0)).transmitting)

    def test_select_color_by_mouse(self):
        w = World()
        w.generate((0, 0, 0))
        w.generate((1, 0, 0))
        w.connect((0, 0, 0), (1, 0, 0))
        m = MouseController(w, tool=Tool.SELECT)
        m.color = "purple"
        group = m.click(MouseEvent(x=0, y=0))
        self.assertTrue(all(b.color == "purple" for b in group))

    def test_transmit_by_mouse_uses_payload(self):
        w = World()
        for x in range(3):
            w.generate((x, 0, 0))
        for x in range(2):
            w.connect((x, 0, 0), (x + 1, 0, 0))
        m = MouseController(w, tool=Tool.TRANSMIT)
        m.payload = {"power": 11}
        received = m.click(MouseEvent(x=0, y=0))
        self.assertEqual(len(received), 3)

    def test_layer_sets_z(self):
        w = World()
        m = MouseController(w, tool=Tool.GENERATE, layer=5)
        m.click(MouseEvent(x=1, y=1))
        self.assertIn((1, 1, 5), w)

    def test_event_z_overrides_layer(self):
        w = World()
        m = MouseController(w, tool=Tool.GENERATE, layer=5)
        m.click(MouseEvent(x=1, y=1, z=9))
        self.assertIn((1, 1, 9), w)


if __name__ == "__main__":
    unittest.main()
