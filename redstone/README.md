# Redstone — блоки с передачей данных

Модель «редстоун»-подобной системы блоков на чистом Python (без внешних
зависимостей, стандартная библиотека). У каждого блока есть полный набор
функций, и каждая функция вызывается **двумя способами** — данными внутри
блоков и нажатием мышки.

## Функции каждого блока

| Функция | Метод блока | Метод мира | Действие пакета |
|---|---|---|---|
| Генерация | `block.spawn(coord)` | `world.generate(coord)` | `generate` |
| Уничтожение | `block.destroy()` | `world.destroy(coord)` | `destroy` |
| Сохранение данных | `block.save(payload)` | — | `save` |
| Стирание данных | `block.erase(*keys)` | — | `erase` |
| Передача данных | `block.transmit(payload)` | `world.propagate(...)` | `transmit` |
| Блокировка передачи | `block.block_transmission()` | — | `block` |
| Снятие блокировки | `block.unblock_transmission()` | — | `unblock` |
| Выделение группы (в т.ч. цветом) | `block.select(color)` | `world.select(color=..., state=...)` | `select` |
| Соединение | `block.connect(other)` | `world.connect(a, b)` | `connect` |
| Разъединение | `block.disconnect(other)` | `world.disconnect(a, b)` | `disconnect` |
| Перемещение данных группы | `block.move_group_data(delta)` | — | `move` |

## Формат передачи данных — «ключ: значение»

```python
{
    "state": "save",          # состояние / действие
    "coord": (x, y, z),       # координата воздействия
    "data":  {                # передаваемые данные, любая глубина вложенности
        "payload": {"user": {"id": 7, "roles": ["admin", {"scope": "all"}]}}
    }
}
```

Это `redstone.packet.Packet`. Координату можно задавать и отдельными ключами
`x, y, z` (см. `Packet.from_dict`).

## Два способа вызова — один диспетчер

Оба пути сходятся в `World.dispatch(packet)`, поэтому поведение одинаково.

```python
from redstone import World, Packet, Action, MouseController, MouseEvent, Tool

world = World()

# 1) Через данные внутри блоков (пакет)
world.dispatch(Packet(Action.GENERATE, (0, 0, 0)))
world.dispatch(Packet(Action.GENERATE, (1, 0, 0)))
world.dispatch(Packet(Action.CONNECT, (0, 0, 0), {"target": (1, 0, 0)}))
world.dispatch(Packet(Action.TRANSMIT, (0, 0, 0), {"payload": {"power": 15}}))

# 2) Нажатием мышки (то же самое, через MouseController)
mouse = MouseController(world, tool=Tool.SELECT)
mouse.color = "green"
mouse.click(MouseEvent(x=0, y=0))   # выделит группу цветом
```

## Запуск

```bash
# Демонстрация всех функций (headless, без GUI)
python -m redstone.demo

# Тесты
python -m unittest discover -s redstone/tests -p "test_*.py"

# Необязательный GUI (нужен tkinter и дисплей)
python -m redstone.gui
```

## Модули

- `redstone/packet.py` — формат `{state, coord, data}` и перечень действий `Action`.
- `redstone/block.py` — блок и его функции.
- `redstone/group.py` — группа блоков: выделение, цвет, перемещение данных.
- `redstone/world.py` — хранилище блоков, граф соединений, диспетчер команд.
- `redstone/mouse.py` — перевод кликов мышки в пакеты (без привязки к GUI).
- `redstone/gui.py` — необязательный 2D-редактор на tkinter.
- `redstone/demo.py` — демонстрация.
- `redstone/tests/` — тесты.
