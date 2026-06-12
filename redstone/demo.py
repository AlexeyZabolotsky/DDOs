"""Демонстрация всех функций без GUI.

Запуск::

    python -m redstone.demo

Скрипт показывает, что каждая функция вызывается обоими способами:
пакетом данных и «нажатием мышки» (через :class:`MouseController`).
"""

from __future__ import annotations

from redstone import (
    Action,
    MouseButton,
    MouseController,
    MouseEvent,
    Packet,
    Tool,
    World,
)


def banner(title: str) -> None:
    print("\n" + "=" * 60)
    print(title)
    print("=" * 60)


def main() -> None:
    world = World()
    mouse = MouseController(world)

    banner("1. Генерация блоков — нажатием мышки")
    mouse.select_tool(Tool.GENERATE)
    for x in range(4):
        mouse.click(MouseEvent(x=x, y=0))
    print("блоки:", [b.coord for b in world.blocks])

    banner("2. Генерация блока — через данные (пакет)")
    world.dispatch(Packet(Action.GENERATE, (0, 1, 0), {"opts": {"color": "red"}}))
    print("блок (0,1,0):", world.get((0, 1, 0)).snapshot())

    banner("3. Соединение блоков — мышкой (два клика) и пакетом")
    mouse.select_tool(Tool.CONNECT)
    mouse.click(MouseEvent(x=0, y=0))  # источник
    mouse.click(MouseEvent(x=1, y=0))  # цель
    world.dispatch(Packet(Action.CONNECT, (1, 0, 0), {"target": (2, 0, 0)}))
    world.dispatch(Packet(Action.CONNECT, (2, 0, 0), {"target": (3, 0, 0)}))
    print("связи (1,0,0):", sorted(world.get((1, 0, 0)).connections))

    banner("4. Сохранение данных (любая вложенность) — пакетом")
    payload = {"user": {"id": 7, "roles": ["admin", {"scope": "all"}]}, "ttl": 60}
    world.dispatch(Packet(Action.SAVE, (0, 0, 0), {"payload": payload}))
    print("данные (0,0,0):", world.get((0, 0, 0)).data)

    banner("5. Передача данных по соединённой группе — мышкой")
    mouse.select_tool(Tool.TRANSMIT)
    mouse.payload = {"signal": {"power": 15}}
    received = mouse.click(MouseEvent(x=0, y=0))
    print("приняли данные:", [b.coord for b in received])

    banner("6. Блокировка передачи — мышкой, затем повторная передача")
    mouse.select_tool(Tool.BLOCK)
    mouse.click(MouseEvent(x=2, y=0))  # блокируем блок (2,0,0)
    mouse.select_tool(Tool.TRANSMIT)
    mouse.payload = {"signal": {"power": 7}}
    received = mouse.click(MouseEvent(x=0, y=0))
    print("после блокировки приняли:", [b.coord for b in received])

    banner("7. Выделение группы цветом (состояние) — мышкой")
    mouse.select_tool(Tool.SELECT)
    mouse.color = "green"
    group = mouse.click(MouseEvent(x=0, y=0))
    print("выделено блоков:", len(group), "цвет:", [b.color for b in group])

    banner("8. Выделение по цвету — пакетом")
    green = world.dispatch(Packet(Action.SELECT, (0, 0, 0), {"color": "green"}))
    print("блоков цвета green:", green.coords)

    banner("9. Перемещение данных соединённой группы — пакетом")
    world.dispatch(Packet(Action.GENERATE, (0, 2, 0)))
    world.dispatch(Packet(Action.GENERATE, (1, 2, 0)))
    world.dispatch(Packet(Action.CONNECT, (0, 2, 0), {"target": (1, 2, 0)}))
    world.dispatch(Packet(Action.SAVE, (0, 2, 0), {"payload": {"v": 1}}))
    world.dispatch(Packet(Action.SAVE, (1, 2, 0), {"payload": {"v": 2}}))
    world.dispatch(Packet(Action.GENERATE, (0, 3, 0)))
    world.dispatch(Packet(Action.GENERATE, (1, 3, 0)))
    world.dispatch(Packet(Action.MOVE, (0, 2, 0), {"delta": (0, 1, 0)}))
    print("данные (0,3,0):", world.get((0, 3, 0)).data)
    print("данные (1,3,0):", world.get((1, 3, 0)).data)
    print("данные (0,2,0) после переноса:", world.get((0, 2, 0)).data)

    banner("10. Стирание данных и уничтожение блока")
    world.dispatch(Packet(Action.ERASE, (0, 0, 0)))
    print("данные (0,0,0) после стирания:", world.get((0, 0, 0)).data)
    world.dispatch(Packet(Action.DESTROY, (3, 0, 0)))
    print("блок (3,0,0) существует:", (3, 0, 0) in world)

    banner("Итог: всего блоков и журнал команд")
    print("блоков в мире:", len(world))
    print("выполнено команд:", len(world.log))


if __name__ == "__main__":
    main()
