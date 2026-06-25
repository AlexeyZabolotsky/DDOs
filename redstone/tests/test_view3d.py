"""Тесты 3D-клиента (без запуска Ursina)."""

from redstone.view3d.minecraft_fp import _hex_to_color


def test_hex_to_color():
    c = _hex_to_color("#ff0000")
    assert c[0] == 255
    assert c[1] == 0
    assert c[2] == 0


if __name__ == "__main__":
    test_hex_to_color()
    print("OK test_hex_to_color")
