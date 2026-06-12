import unittest

from redstone_blocks import RedstoneWorld


class RedstoneWorldTest(unittest.TestCase):
    def test_generate_save_erase_destroy_from_russian_packets(self):
        world = RedstoneWorld()

        block = world.dispatch(
            {
                "состояние": "создать",
                "координата воздействия": {"x": 1, "y": 2, "z": 3},
                "передаваемые данные": {
                    "block_state": {"kind": "lamp"},
                    "block_data": {"power": {"level": 1}},
                },
            }
        )

        self.assertEqual(block.coordinate, (1, 2, 3))
        self.assertEqual(block.state["kind"], "lamp")
        self.assertEqual(block.data["power"]["level"], 1)

        world.dispatch(
            {
                "действие": "сохранить",
                "координата воздействия": (1, 2, 3),
                "передаваемые данные": {
                    "power": {"enabled": True},
                    "meta": {"owner": {"name": "player"}},
                },
            }
        )

        self.assertEqual(
            world.require_block((1, 2, 3)).data,
            {
                "power": {"level": 1, "enabled": True},
                "meta": {"owner": {"name": "player"}},
            },
        )

        world.dispatch(
            {
                "состояние": "стереть",
                "координата воздействия": (1, 2, 3),
                "передаваемые данные": {"keys": ["meta"]},
            }
        )
        self.assertNotIn("meta", world.require_block((1, 2, 3)).data)

        destroyed = world.dispatch(
            {
                "состояние": "уничтожить",
                "координата воздействия": (1, 2, 3),
                "передаваемые данные": {},
            }
        )
        self.assertEqual(destroyed.coordinate, (1, 2, 3))
        self.assertEqual(world.blocks, {})

    def test_transfer_data_respects_block_connections_and_locks(self):
        world = RedstoneWorld()
        world.generate_block((0, 0, 0), data={"signal": {"level": 15}})
        world.generate_block((1, 0, 0), data={"old": True})
        world.connect((0, 0, 0), (1, 0, 0))

        world.dispatch(
            {
                "состояние": "передать",
                "координата воздействия": (0, 0, 0),
                "передаваемые данные": {"цель": (1, 0, 0), "data": {"signal": {"pulse": 2}}},
            }
        )

        self.assertEqual(
            world.require_block((1, 0, 0)).data,
            {"old": True, "signal": {"pulse": 2}},
        )

        world.dispatch(
            {
                "состояние": "заблокировать_передачу",
                "координата воздействия": (0, 0, 0),
                "передаваемые данные": {},
            }
        )

        with self.assertRaises(PermissionError):
            world.transfer_data((0, 0, 0), (1, 0, 0), {"signal": {"pulse": 3}})

        world.dispatch(
            {
                "состояние": "разблокировать_передачу",
                "координата воздействия": (0, 0, 0),
                "передаваемые данные": {},
            }
        )
        world.transfer_data((0, 0, 0), (1, 0, 0), {"signal": {"pulse": 3}})
        self.assertEqual(world.require_block((1, 0, 0)).data["signal"]["pulse"], 3)

    def test_group_selection_color_connection_and_group_data_move(self):
        world = RedstoneWorld()
        for coordinate in [(0, 0, 0), (0, 1, 0), (5, 0, 0)]:
            world.generate_block(coordinate)
        world.save_block((0, 0, 0), {"a": {"nested": 1}})
        world.save_block((0, 1, 0), {"b": 2})

        source = world.select_group(
            "source",
            [(0, 0, 0), (0, 1, 0)],
            color="red",
            state={"selected": True},
        )
        target = world.dispatch(
            {
                "состояние": "выделить_группу",
                "координата воздействия": (5, 0, 0),
                "передаваемые данные": {"group_id": "target", "color": "blue"},
            }
        )
        world.connect_group("source", "target")

        moved_blocks = world.move_connected_group_data("source", "target", clear_source=True)

        self.assertEqual(source.color, "red")
        self.assertEqual(target.color, "blue")
        self.assertEqual(world.require_block((0, 0, 0)).state["color"], "red")
        self.assertEqual(world.require_block((0, 1, 0)).state["selected"], True)
        self.assertEqual(len(moved_blocks), 1)
        self.assertEqual(
            world.require_block((5, 0, 0)).data,
            {"0,0,0": {"a": {"nested": 1}}, "0,1,0": {"b": 2}},
        )
        self.assertEqual(world.require_block((0, 0, 0)).data, {})
        self.assertEqual(world.require_block((0, 1, 0)).data, {})

    def test_mouse_click_uses_block_action_or_explicit_payload(self):
        world = RedstoneWorld()
        world.generate_block(
            (9, 9, 9),
            state={"click_actions": {"left": "lock_transfer", "right": "unlock_transfer"}},
        )

        world.click((9, 9, 9), button="left")
        self.assertTrue(world.require_block((9, 9, 9)).locked_transfer)

        world.click((9, 9, 9), button="right")
        self.assertFalse(world.require_block((9, 9, 9)).locked_transfer)

        world.click(
            (9, 9, 9),
            payload={
                "состояние": "сохранить",
                "передаваемые данные": {"clicked": {"button": "middle"}},
            },
            button="middle",
        )
        self.assertEqual(world.require_block((9, 9, 9)).data["clicked"]["button"], "middle")


if __name__ == "__main__":
    unittest.main()
